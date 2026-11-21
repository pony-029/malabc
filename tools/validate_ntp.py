# -*- coding: utf-8 -*-
"""**规范点名的校验器**：NTP 报文 + 转换台账（ANE v0.9.0 §5.2 / §43.9 / §43.10）。

    python tools/validate_ntp.py --ledger <conversion.json>
    python tools/validate_ntp.py --ntp <msg.json>
    python tools/validate_ntp.py --selftest

## 为什么这个文件名是固定的

规范 43.9 明确写了「契约见 `schemas/conversion-1.0.schema.json`，
由 `tools/validate_ntp.py` 兜底并自动落盘校验」。本仓此前**没有这个文件**——
也就是说规范点名的那一环，在实现里根本不存在。

按规范起名，是为了让「规范说有什么」和「仓库里有什么」能一字对上。

## 校验什么

### 转换台账（43.9 + 43.10）

字段齐全：`conversion_version` / `conversion_id` / `organism_id` /
`fitness_tier` / `target_tier` / `stages` / `gray_release` /
`data_migration` / `non_convertible` / `completion` / `conversion_digest`

**态约束（43.10，逐条可判）**：

| 规则 | 判据 |
|---|---|
| E1 | `BLOCKED` 阶段的 `exit_verified` 必须为 `false` |
| E2 | `EXIT_VERIFIED` 阶段的 `exit_verified` 必须为 `true` |
| E3 | `completion` 里各项全为 true 时，所有阶段必须是 `EXIT_VERIFIED` 或 `SKIPPED` |
| E4 | `gray_release.mode == "RETIRED"` 时，`completion.conformity_passed` 必须为 true |

**为什么 E1/E2 必须机检**：`exit_verified` 与 `state` 是两个字段，
人写台账时最容易一个改了另一个没改 —— 而那种不一致会让"阶段已通过"
这句话毫无意义。

### NTP 报文（5.2）

复用 `tools/ntp.py` 的 `validate()`，不重写第二套判据。

退出码：0=全部合规 1=有不合规 2=缺输入
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

LEDGER_FIELDS = ("conversion_version", "conversion_id", "organism_id",
                 "fitness_tier", "target_tier", "stages", "gray_release",
                 "data_migration", "non_convertible", "completion",
                 "conversion_digest")

STAGE_STATES = ("NOT_STARTED", "IN_PROGRESS", "BLOCKED",
                "EXIT_VERIFIED", "ROLLED_BACK", "SKIPPED")

COMPLETION_KEYS = ("conformity_passed", "old_retired_or_declared",
                   "ledger_archived", "human_signoff", "observation_cycle_done")


def validate_ledger(d):
    """校验转换台账。返回 (errors, warnings)。"""
    errs, warns = [], []

    for k in LEDGER_FIELDS:
        if k not in d:
            errs.append("缺字段 %s" % k)
    if errs:
        return errs, warns          # 缺字段时后面的判定没有意义

    if str(d["conversion_version"]) != "1.0":
        errs.append("conversion_version 必须是 1.0（实得 %r）"
                    % (d["conversion_version"],))
    if not str(d["conversion_id"]).startswith("conv-"):
        errs.append("conversion_id 必须以 conv- 开头")

    cd = str(d["conversion_digest"])
    if not cd.startswith("sha256:") or len(cd) != 71:
        errs.append("conversion_digest 必须是 sha256: + 64 位十六进制")

    # stages
    stages = d["stages"]
    if not isinstance(stages, list) or not stages:
        errs.append("stages 必须是非空数组")
        stages = []
    for s in stages:
        sid = s.get("stage_id", "?")
        st = s.get("state")
        ev = s.get("exit_verified")
        if st not in STAGE_STATES:
            errs.append("%s 的 state=%r 不在枚举内" % (sid, st))
            continue
        # E1 / E2
        if st == "BLOCKED" and ev is not False:
            errs.append("E1 %s 是 BLOCKED，但 exit_verified=%r（必须 false）"
                        % (sid, ev))
        if st == "EXIT_VERIFIED" and ev is not True:
            errs.append("E2 %s 是 EXIT_VERIFIED，但 exit_verified=%r（必须 true）"
                        % (sid, ev))
        if not s.get("evidence_ref"):
            warns.append("%s 没有 evidence_ref，阶段结论无据" % sid)

    # E3
    comp = d["completion"]
    if all(comp.get(k) is True for k in COMPLETION_KEYS):
        bad = [s.get("stage_id") for s in stages
               if s.get("state") not in ("EXIT_VERIFIED", "SKIPPED")]
        if bad:
            errs.append("E3 completion 全为 true，但阶段 %s 未 EXIT_VERIFIED/SKIPPED"
                        % bad)

    # E4
    gr = d["gray_release"]
    if gr.get("mode") == "RETIRED" and comp.get("conformity_passed") is not True:
        errs.append("E4 灰台已 RETIRED，但 conformity_passed 不为 true")

    # data_migration 四温
    temps = [m.get("temperature") for m in (d.get("data_migration") or [])
             if isinstance(m, dict)]
    for need in ("HOT", "WARM", "COLD", "FROZEN"):
        if need not in temps:
            warns.append("data_migration 缺少 %s 温度的策略（规范 41.1 要求四温齐备）"
                         % need)

    return errs, warns


def _selftest():
    """两向自证：合规台账必须过；E1/E2/E3/E4 各造一个反例必须被抓。

    只验"能跑"不算自证 —— 一个永远返回空 errors 的校验器，
    会让所有台账"看起来合规"，而那正是这类工具最坏的失效方式。
    """
    good = bad = 0
    base = {
        "conversion_version": "1.0",
        "conversion_id": "conv-test-01",
        "organism_id": "org-t",
        "fitness_tier": "T2",
        "target_tier": "L4",
        "stages": [
            {"stage_id": "OBSERVE", "state": "EXIT_VERIFIED",
             "exit_verified": True, "evidence_ref": "trace:a"},
            {"stage_id": "MEMORY", "state": "IN_PROGRESS",
             "exit_verified": False, "evidence_ref": "review:b"},
        ],
        "gray_release": {"mode": "SHADOW", "current_step": "SHADOW",
                         "diff_ratio": 0.01, "rollback_ready": True},
        "data_migration": [{"temperature": t, "strategy": "x", "forbidden": False}
                           for t in ("HOT", "WARM", "COLD", "FROZEN")],
        "non_convertible": [{"component": "rt-loop",
                             "disposition": "keep", "declared_external": False}],
        "completion": {k: False for k in COMPLETION_KEYS},
        "conversion_digest": "sha256:" + "0" * 64,
    }

    e, _w = validate_ledger(dict(base))
    if not e:
        good += 1
    else:
        bad += 1
        print("  [selftest] 合规台账被拒：%r" % (e,))

    t1 = json.loads(json.dumps(base))
    t1["stages"][1] = {"stage_id": "MEMORY", "state": "BLOCKED",
                       "exit_verified": True, "evidence_ref": "x"}
    if any("E1" in x for x in validate_ledger(t1)[0]):
        good += 1
    else:
        bad += 1
        print("  [selftest] E1（BLOCKED 却 exit_verified=true）未被抓")

    t2 = json.loads(json.dumps(base))
    t2["stages"][0]["exit_verified"] = False
    if any("E2" in x for x in validate_ledger(t2)[0]):
        good += 1
    else:
        bad += 1
        print("  [selftest] E2（EXIT_VERIFIED 却 exit_verified=false）未被抓")

    t3 = json.loads(json.dumps(base))
    for k in COMPLETION_KEYS:
        t3["completion"][k] = True
    if any("E3" in x for x in validate_ledger(t3)[0]):
        good += 1
    else:
        bad += 1
        print("  [selftest] E3（completion 全真但阶段未完成）未被抓")

    t4 = json.loads(json.dumps(base))
    t4["gray_release"]["mode"] = "RETIRED"
    if any("E4" in x for x in validate_ledger(t4)[0]):
        good += 1
    else:
        bad += 1
        print("  [selftest] E4（RETIRED 但 conformity 未过）未被抓")

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="NTP 与转换台账校验")
    ap.add_argument("--ledger", help="转换台账 JSON（43.9）")
    ap.add_argument("--ntp", help="NTP 上行报文 JSON（5.2）")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not ns.ledger and not ns.ntp:
        print("validate_ntp: 缺输入（--ledger 或 --ntp 至少给一个）")
        return 2

    rc = 0
    if ns.ledger:
        if not os.path.isfile(ns.ledger):
            print("validate_ntp: 缺输入（%s 不存在）" % ns.ledger)
            return 2
        try:
            d = json.load(io.open(ns.ledger, encoding="utf-8"))
        except ValueError as e:
            print("validate_ntp: 台账不是合法 JSON（%s）" % e)
            return 2
        errs, warns = validate_ledger(d)
        print("[台账] %s ｜ 错误 %d ｜ 警告 %d"
              % (os.path.basename(ns.ledger), len(errs), len(warns)))
        for x in errs:
            print("  [E] %s" % x)
        for x in warns:
            print("  [W] %s" % x)
        if errs:
            rc = 1

    if ns.ntp:
        if not os.path.isfile(ns.ntp):
            print("validate_ntp: 缺输入（%s 不存在）" % ns.ntp)
            return 2
        import ntp as NTP
        try:
            msg = json.load(io.open(ns.ntp, encoding="utf-8"))
        except ValueError as e:
            print("validate_ntp: NTP 不是合法 JSON（%s）" % e)
            return 2
        errs2, warns2 = NTP.validate(msg)
        print("[NTP] %s ｜ 错误 %d ｜ 警告 %d"
              % (os.path.basename(ns.ntp), len(errs2), len(warns2)))
        for x in errs2:
            print("  [E] %s" % x)
        for x in warns2:
            print("  [W] %s" % x)
        if errs2:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
