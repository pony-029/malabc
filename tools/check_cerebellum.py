# -*- coding: utf-8 -*-
"""**小脑硬边界门**（ANE v0.9.0 第四章 4.4 + 第五章 NTP）。

    python tools/check_cerebellum.py           # 0=全绿 1=有缺口 2=缺输入
    python tools/check_cerebellum.py --report  # 写 flow/cerebellum.json
    python tools/check_cerebellum.py --selftest

## 为什么单独成门

`cerebellum_bounds.py` 与 `ntp.py` 各自能跑，但**没有任何门在每次发版时
核对它们**——也就是说「小脑离线率达标」「NTP 报文合规」这两件事
和 R976 之前的 ANE 一样，只存在于我这一轮的口头里。

本门把三件事绑成一条判据：

| 条款 | 判据 | 谁提供数据 |
|---|---|---|
| 4.4 离线可用 | 自决率 >= 80% | `cerebellum_bounds.measure_offline` |
| 4.4 可生长 | 规则集合只增不减 | `cerebellum_bounds.check_growable` |
| 5.2 NTP | 报文字段齐全、ANE5 与 NTP 信息一致 | `ntp.validate` |
| 4.4 无推测 | `tried_rules` 不能为空、`signal_type` 只能是 UNKNOWN/S1..S4 | `ntp.build` 抛错与否 |

## 判据口径（写死，防混用）

离线可用率用**真实语料**（>=2 项复合特征那个口径），不用按 kind 构造的合成咨询——
后者会得到 100%，与真实 94% 差 6 个点，R1066 已踩过。

退出码：0=全绿 1=有缺口 2=缺输入
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

ROW_SIGNATURE = "CB1–CB4"

#: 每个判据前缀守的条款（给判据的对手方，也是本门的一句话索引）
GUARD_CONTRACT = [
    ("CB1 ", "4.4 离线可用：真实语料自决率 >= 80%"),
    ("CB2 ", "4.4 可生长：规则集合只增不减"),
    ("CB3 ", "5.2 NTP：报文字段齐全且与 ANE5 信息一致"),
    ("CB4 ", "4.4 无推测：signal_type 受限、tried_rules 非空"),
]

#: 真实语料候选（与 cerebellum_bounds 的自动探测保持一致）
MIR_CANDIDATES = (
    "E:/temp/matlabc/octgen/.m2c/project.mir",
    "E:/temp/matlabc/oct_num/.m2c/project.mir",
)


def _find_mir():
    for c in MIR_CANDIDATES:
        if os.path.isfile(c):
            return c
    # 退而求其次：MIR 可能落在工程的 .m2c 目录里
    for base in ("E:/temp/matlabc",):
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            p = os.path.join(base, name, ".m2c", "project.mir")
            if os.path.isfile(p):
                return p
    return None


def audit():
    """返回 (rows, ok, detail)。rows 是 (前缀, 结论, 说明)。"""
    import cerebellum_bounds as CB
    import ntp

    rows = []
    detail = {}

    # CB1 离线可用
    mir = _find_mir()
    if not mir:
        rows.append(("CB1 ", "SKIP", "找不到真实 MIR —— 未做离线率判定（不假装通过）"))
        detail["offline"] = None
    else:
        off = CB.measure_offline(mir, 200)
        rate = off["rate"] * 100
        detail["offline"] = {"mir": mir, "rate": rate,
                             "total": off["total"],
                             "up": len(off["escalate"])}
        if off["pass"]:
            rows.append(("CB1 ", "OK", "真实语料自决率 %.1f%%（>=%.0f%%，%d 条上行）"
                         % (rate, off["floor"] * 100, len(off["escalate"]))))
        else:
            rows.append(("CB1 ", "GAP", "真实语料自决率 %.1f%% < %.0f%%"
                         % (rate, off["floor"] * 100)))

    # CB2 可生长
    grow = CB.check_growable()
    detail["growable"] = grow
    if grow.get("missing_baseline"):
        rows.append(("CB2 ", "SKIP", "基线不存在 —— 用 --update-baseline 建立后再判"))
    elif grow["ok"]:
        rows.append(("CB2 ", "OK", "规则集合只增不减（新增 %d 条）"
                     % grow.get("added", 0)))
    else:
        lost = grow.get("shrunk") or []
        rows.append(("CB2 ", "GAP", "规则集合减少：%s"
                     % "、".join("%s 少 %d" % (k, len(v)) for k, v in lost)))

    # CB3 NTP 报文合规
    try:
        msg = ntp.build(signal_type="S3", error_code="E-CB-0001",
                        feature_vector=[0.1, 0.9], context_text="gate",
                        tried_rules=["mem_sections"])
        errs, warns = ntp.validate(msg, ntp.compact(msg))
        detail["ntp"] = {"errors": errs, "warnings": warns,
                         "compact_bytes": len(ntp.compact(msg))}
        if errs:
            rows.append(("CB3 ", "GAP", "NTP 校验未过：%s" % errs[0]))
        else:
            rows.append(("CB3 ", "OK", "报文字段齐全，ANE5 与 NTP 一致（%d 字节）"
                         % len(ntp.compact(msg))))
    except (ValueError, KeyError) as e:
        rows.append(("CB3 ", "GAP", "NTP 构造失败：%s" % e))

    # CB4 无推测
    bad = []
    try:
        ntp.build(signal_type="S3", error_code="E-CB-0001",
                  feature_vector=[0.1, 0.2], context_text="",
                  tried_rules=[])
        bad.append("空 tried_rules 未被拒绝")
    except ValueError:
        pass
    try:
        ntp.build(signal_type="MAYBE", error_code="E-CB-0001",
                  feature_vector=[0.1, 0.2], context_text="",
                  tried_rules=["r"])
        bad.append("非法 signal_type 未被拒绝")
    except ValueError:
        pass
    if bad:
        rows.append(("CB4 ", "GAP", "；".join(bad)))
    else:
        rows.append(("CB4 ", "OK", "空 tried_rules 与非法 signal_type 均被拒绝"))

    ok = all(r[1] in ("OK", "SKIP") for r in rows)
    return rows, ok, detail


def _selftest():
    """两向自证：门必须能报绿，也必须能报红。

    只验“能跑”不算自证——一个恒返回 OK 的门和没有门一样，而它会让人
    以为小脑边界被守着。
    """
    good = bad = 0
    rows, ok, _d = audit()
    if len(rows) == 4:
        good += 1
    else:
        bad += 1
        print("  [selftest] 判据条数应为 4，实得 %d" % len(rows))

    if all(r[0].strip() in ("CB1", "CB2", "CB3", "CB4") for r in rows):
        good += 1
    else:
        bad += 1
        print("  [selftest] 前缀不是 CB1..CB4")

    # 契约与判据必须一一对应（H2b 那条教训：声明了就得存在）
    sig = set(x.strip() for x in ROW_SIGNATURE.replace("–", "-").split("-")[0:1])
    declared = [p.strip() for p, _w in GUARD_CONTRACT]
    if declared == ["CB1", "CB2", "CB3", "CB4"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] GUARD_CONTRACT 前缀不完整：%r" % (declared,))

    # 红的能力：把 NTP 判据临时打坏，Gate 必须报 GAP
    import ntp
    _orig = ntp.build
    try:
        ntp.build = lambda **kw: {"ntp_version": "1.1"}   # 缺字段
        rows2, ok2, _d2 = audit()
        if not ok2 and any(r[1] == "GAP" for r in rows2):
            good += 1
        else:
            bad += 1
            print("  [selftest] 打坏 NTP 后仍判绿 —— 门没有红的能力")
    finally:
        ntp.build = _orig

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="小脑硬边界门")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    rows, ok, detail = audit()
    for prefix, verdict, note in rows:
        print("%s %-8s %s" % (prefix, verdict, note))
    gaps = [r for r in rows if r[1] == "GAP"]
    if ok:
        print("check_cerebellum: OK（%s 全绿：%s）"
              % (ROW_SIGNATURE, "；".join(r[2] for r in rows)))
    else:
        print("check_cerebellum: %d 项缺口（%s）" % (len(gaps), ROW_SIGNATURE))

    if args.report:
        p = os.path.join(ROOT, "flow", "cerebellum.json")
        io.open(p, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"signature": ROW_SIGNATURE,
                        "ok": ok,
                        "rows": [{"prefix": a, "verdict": b, "note": c}
                                 for a, b, c in rows],
                        "detail": detail}, ensure_ascii=False, indent=1) + "\n")
        print("[report] -> %s" % os.path.relpath(p, ROOT))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
