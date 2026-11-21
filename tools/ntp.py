# -*- coding: utf-8 -*-
"""**神经调度协议 NTP**：小脑 -> 大脑的上行报文。

    python tools/ntp.py --selftest
    python tools/ntp.py --from-hw-brain "E:/temp/matlabc/bigmat" --profile tools/targets/mcu_256k.json

## 规范要求（ANE v0.9.0 第五章 5.2）

上行报文必须是**结构化**的，且只传特征不传全量上下文：

    {
      "ntp_version": "1.1",
      "direction": "uplink",
      "signal_type": "UNKNOWN",
      "error_code": "E-CORE-0427",
      "feature_vector": [...],
      "context_digest": "sha256:...",
      "tried_rules": [...],
      "memory_hits": [...],
      "constraints": [...],
      "budget_hint": {"max_tokens", "max_latency_ms", "priority"}
    }

## 与本仓现状的差距（这是本轮要补的）

`brain_llm.py` 现在实现的是 **ANE5 极简格式**（约 70 字节）：
    ANE5/q=/E=S1..S4/V=score|repeat|open|unknown/K=ids

它满足了「体积小」，但**丢了规范明确要求的四样东西**：
    tried_rules     —— 我试过哪些规则（大脑才能不重复试）
    memory_hits     —— 命中了哪些历史经验（避免重复咨询）
    constraints     —— 有哪些硬约束（D0 不可变 / 目标环境受限）
    budget_hint     —— 预算提示（这是控制成本的关键）

没有 `tried_rules`，大脑会**重走小脑已经走过的路**——每次升级都在付重复的钱。

## 本工具的做法

不推翻 ANE5，而是**分层**：
* `build()` 产出完整 NTP 结构（面向人读与审计）；
* `compact()` 产出 ANE5 极简单行（面向传输，省字节）；
* `validate()` 校验两者**信息一致**：ANE5 里缺的字段必须在 NTP 里有。

这样体积与信息量不再二选一。

## 无推测（硬边界）

规范第四条 4.4：本地规则未命中时小脑**必须**抛 `UnknownSignal`，
禁止猜、禁止降级成"看起来对"。本工具在 `build()` 里强制：
`signal_type` 只能是 UNKNOWN / S1..S4 之一；`error_code` 必填。
缺任何一项直接抛 ValueError —— 不给"先发个空的再说"的机会。

退出码：0=通过 1=自证失败 2=缺输入
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

NTP_VERSION = "1.1"
SIGNALS = ("UNKNOWN", "S1", "S2", "S3", "S4")
#: error_code 形如 E-CORE-0427：E-<模块>-<四位数字>
CODE_RE = re.compile(r"^E-[A-Z]{2,8}-\d{4}$")


class UnknownSignal(Exception):
    """小脑规则未命中时**必须**抛这个，而不是编一个结论。

    规范 4.4「无推测」：抛异常是可审计的失败，猜一个值是污染的记录。
    """


def build(signal_type, error_code, feature_vector, context_text,
          tried_rules, memory_hits=None, constraints=None,
          max_tokens=1200, max_latency_ms=8000, priority="D1"):
    """构造符合规范的 NTP 上行报文。缺关键字段一律抛错（不猜）。"""
    if signal_type not in SIGNALS:
        raise ValueError("signal_type 只能是 %s（实得 %r）"
                         % ("/".join(SIGNALS), signal_type))
    if not error_code or not CODE_RE.match(str(error_code)):
        raise ValueError("error_code 必须是 E-<模块>-<四位数字>（实得 %r）"
                         % (error_code,))
    if not isinstance(feature_vector, (list, tuple)) or len(feature_vector) < 2:
        raise ValueError("feature_vector 至少 2 维（规范要求特征化，不给原文本）")
    if not tried_rules:
        # 一条都没试过就升级，说明小脑根本没工作 —— 这是"该拦住"的情形
        raise ValueError("tried_rules 不能为空：没有尝试记录就意味着小脑被绕过")
    digest = hashlib.sha256(
        (context_text or "").encode("utf-8")).hexdigest()
    return {
        "ntp_version": NTP_VERSION,
        "direction": "uplink",
        "signal_type": signal_type,
        "error_code": error_code,
        "feature_vector": [round(float(x), 4) for x in feature_vector],
        "context_digest": "sha256:" + digest,
        "tried_rules": list(tried_rules),
        "memory_hits": list(memory_hits or []),
        "constraints": list(constraints or []),
        "budget_hint": {"max_tokens": int(max_tokens),
                        "max_latency_ms": int(max_latency_ms),
                        "priority": priority},
    }


def compact(msg):
    """ANE5 极简单行（省字节），但**只压缩冗余**，不丢上面那四样。

    格式：ANE5/q=<sig>/E=<code>/V=<fv>/T=<n>/M=<n>/C=<k>/B=<tok>
      V 是特征向量的维度数，T/M/C 是三个列表的长度 ——
      具体内容留在 NTP 里，传输时只带"有多少"，大脑按需回取。
    """
    return ("ANE5/q=%s/E=%s/V=%d/T=%d/M=%d/C=%d/B=%d"
            % (msg["signal_type"], msg["error_code"],
               len(msg["feature_vector"]), len(msg["tried_rules"]),
               len(msg["memory_hits"]), len(msg["constraints"]),
               msg["budget_hint"]["max_tokens"]))


def validate(msg, raw=None):
    """校验报文合规。返回 (errors, warnings)。"""
    errs, warns = [], []
    for k in ("ntp_version", "direction", "signal_type", "error_code",
              "feature_vector", "context_digest", "tried_rules",
              "memory_hits", "constraints", "budget_hint"):
        if k not in msg:
            errs.append("缺字段 %s" % k)
    if msg.get("direction") != "uplink":
        errs.append("direction 必须是 uplink（下行另有约定）")
    if msg.get("signal_type") not in SIGNALS:
        errs.append("signal_type 非法")
    if not CODE_RE.match(str(msg.get("error_code", ""))):
        errs.append("error_code 格式不符合 E-<模块>-<四位>")
    cd = str(msg.get("context_digest", ""))
    if not cd.startswith("sha256:") or len(cd) != 71:
        errs.append("context_digest 必须是 sha256: + 64 位十六进制")
    bh = msg.get("budget_hint") or {}
    if not isinstance(bh.get("max_tokens"), int) or bh["max_tokens"] <= 0:
        errs.append("budget_hint.max_tokens 必须是正整数")
    if not bh.get("priority"):
        errs.append("budget_hint.priority 缺失")

    # **体积与信息一致性**：ANE5 行必须能还原出关键计数
    if raw:
        m = re.match(r"^ANE5/q=(\w+)/E=([\w-]+)/V=(\d+)/T=(\d+)/M=(\d+)/C=(\d+)/B=(\d+)$",
                     raw)
        if not m:
            errs.append("ANE5 行格式不合规")
        else:
            if int(m.group(3)) != len(msg.get("feature_vector") or []):
                errs.append("ANE5 的 V 与 NTP 的特征维度不一致")
            if int(m.group(4)) != len(msg.get("tried_rules") or []):
                errs.append("ANE5 的 T 与 NTP 的 tried_rules 数量不一致")
            if int(m.group(5)) != len(msg.get("memory_hits") or []):
                errs.append("ANE5 的 M 与 memory_hits 数量不一致")
    # 空 tried_rules 虽不判错，但值得提醒：可能小脑被绕过了
    if not msg.get("tried_rules"):
        warns.append("tried_rules 为空 —— 请确认小脑确实跑过")
    return errs, warns


def _selftest():
    """两向自证：合规的必须过；缺 tried_rules / 猜 signal 必须被判错。"""
    good = bad = 0
    base = dict(signal_type="S3", error_code="E-MEM-0042",
                feature_vector=[0.1, 0.9], context_text="ctx",
                tried_rules=["rule_a"])

    try:
        m = build(**base)
        good += 1
    except ValueError as e:
        m = None
        bad += 1
        print("  [selftest] 合规报文被拒：%s" % e)

    if m:
        errs, _w = validate(m, compact(m))
        if not errs:
            good += 1
        else:
            bad += 1
            print("  [selftest] 合规报文校验未过：%r" % (errs,))

        # ANE5 与 NTP 必须信息一致：篡改 V 应被抓
        raw = compact(m).replace("/V=2/", "/V=5/")
        errs2, _w2 = validate(m, raw)
        if any("V" in x for x in errs2):
            good += 1
        else:
            bad += 1
            print("  [selftest] ANE5 与 NTP 不一致未被抓到")

    # 无推测：没试过规则就升级 -> 必须拒绝
    try:
        build(signal_type="S1", error_code="E-X-0001",
              feature_vector=[0.1, 0.2], context_text="",
              tried_rules=[])
        bad += 1
        print("  [selftest] 空 tried_rules 未被拒绝（无推测边界失效）")
    except ValueError:
        good += 1

    # signal_type 乱写 -> 必须拒绝
    try:
        build(signal_type="MAYBE", error_code="E-X-0001",
              feature_vector=[0.1, 0.2], context_text="",
              tried_rules=["r"])
        bad += 1
        print("  [selftest] 非法 signal_type 未被拒绝")
    except ValueError:
        good += 1

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def _from_hw_brain(src, profile):
    """把 hw_brain 的升级项翻译成 NTP 报文（真实场景演示）。"""
    import hw_brain as HB
    r = HB.collect(src, profile)
    v = HB.verdict(r)
    if v["decidable"]:
        print("[ntp] 小脑可自决，无需上行（这正是规范想要的结果）")
        return 0
    sig = "S3" if any(x["signal"] == "S3" for x in v["escalate"]) else \
        (v["escalate"][0]["signal"] if v["escalate"][0]["signal"] in SIGNALS
         else "UNKNOWN")
    fv = [r["unknown_shape"] / 10.0, r["scalar_fallback"] / 56.0,
          r["ops_total"] / 56.0, len(r["violations"]) / 4.0]
    try:
        msg = build(signal_type=sig,
                    error_code="E-MEM-%04d" % min(9999, r["unknown_shape"]),
                    feature_vector=fv,
                    context_text=json.dumps(r["signals"], sort_keys=True),
                    tried_rules=["mem_sections", "mem_callchain",
                                 "op_backends"],
                    constraints=["D0_IMMUTABLE", "TARGET_ENV_LIMITED"],
                    max_tokens=1200, priority="D1")
    except ValueError as e:
        print("[ntp] 构造失败：%s" % e)
        return 2
    errs, warns = validate(msg, compact(msg))
    print("[ntp] 信号 %s ｜ %d 项升级" % (sig, len(v["escalate"])))
    print("  紧凑行（%d 字节）：%s" % (len(compact(msg)), compact(msg)))
    print("  完整报文字段：%s" % ", ".join(sorted(msg)))
    for e in errs:
        print("  [E] %s" % e)
    for w in warns:
        print("  [W] %s" % w)
    return 0 if not errs else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="NTP 上行报文")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--from-hw-brain", metavar="MIR目录")
    ap.add_argument("--profile")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if ns.from_hw_brain:
        if not ns.profile or not os.path.isfile(ns.profile):
            print("ntp: 缺输入（--profile 不存在）")
            return 2
        if not os.path.isdir(ns.from_hw_brain):
            print("ntp: 缺输入（MIR 目录不存在）")
            return 2
        return _from_hw_brain(ns.from_hw_brain, ns.profile)
    print("ntp: 缺输入（用 --selftest 或 --from-hw-brain）")
    return 2


if __name__ == "__main__":
    sys.exit(main())
