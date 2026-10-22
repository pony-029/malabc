# -*- coding: utf-8 -*-
"""发版门清单 check —— 一道门写了却从不参与发布，等于给自己看的笔记。

为什么要有它
============
R413 把"新增一道门要同时改的六处"写进了 CONTRIBUTING，其中第六处
（`release.py` 的 `GATES`）是**唯一不会红**的一处：前五处各有门守着，
而"门没进发版清单"没有任何东西会报。

于是有了这条：`tools/check_*.py` 里的每一个脚本，要么出现在 `GATES`，
要么在 `EXEMPT` 里**写明理由**。两向都查 —— 陈旧豁免（登记了却已经在
`GATES` 里）同样算缺陷。

判据族 **RG1–RG5**。

    RG4  某道门比**它自己的历史中位数**慢 `SLOW_RATIO` 倍以上时点名提示
         （不判负）—— 单次数字看不出退化，趋势能。
    RG3  每个门都要在 `releases/gates-last-run.json` 里有"上次真跑"的记录，
         且不能太久以前（`STALE_DAYS`）。一道门存在却从没被跑过、
         或半年没跑过，与不存在在效果上一样。

用法：
    python tools/check_release_gates.py
    python tools/check_release_gates.py --selftest   # 两向自证

退出码：
    0  = 清单与文件一致（RG1–RG2 全绿）
    1  = 有门没进发版清单，或豁免陈旧 / 无理由
    2  = 缺输入（找不到 release.py 或 tools/）
"""
import io
import json
import os
import re
import sys

ROW_SIGNATURE = "RG1–RG5"

#: 发版墙钟预算（毫秒）。超过就判红 —— 它保护的是"发版前真的全跑一遍"这个习惯。
BUDGET_MS = 5000

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
STAMPS = os.path.join(REPO, "releases", "gates-last-run.json")
#: 超过这么多天没跑，就当成"实际上没在守"（提示，不判负）。
STALE_DAYS = 30
#: 比历史中位数慢这么多倍就提示（不判负）。
SLOW_RATIO = 1.5
HISTORY = os.path.join(REPO, "releases", "gates-history.jsonl")
RELEASE = os.path.join(HERE, "release.py")

#: 明确不进发版清单的门 —— **必须写理由**（空理由按无理由处理）。
#: 典型是"总入口"与"太重、只在 CI 跑"的那几个。
#: 只在 CI／手工跑的门。`GATES` 的承诺是"几秒内跑完"，下面这些单次就慢得多，
#: 或者依赖夹具/基线快照 —— 把它们塞进发版流程只会让人开始跳过门。
CI_ONLY = (
    "check_baseline", "check_binfmt_fixtures", "check_boundary_reverse",
    "check_browse_clean_manifest", "check_c_frontend_shapes",
    "check_doc_flags", "check_facts_replay", "check_flag_coverage",
    "check_flow_diagrams", "check_flow_figures", "check_import_graph",
    "check_incremental_parity", "check_ir_attribution",
    "check_kernel_snapshot", "check_known_red", "check_legal_parity",
    "check_matlab_grammar", "check_operator_impl", "check_parity_registry",
    "check_patch_ops", "check_py_js_frontend_shapes", "check_unified_graph",
    # 依赖 golden 夹具 + 可选 C 编译器；进发版快跑清单会把“没编译器”
    # 与“门本身慢”混在一起，故只在 CI / 手工跑。
    # 依赖 docs/architecture 的生成物（HTML/SVG）；发版清单只收几秒内的快门，
    # 生成物对账放在 CI 更合适。
    "check_architecture_docs",
)

EXEMPT = {
    "check_all": "总入口：它调用其它门，自己不被当门调用",
}
for _n in CI_ONLY:
    EXEMPT[_n] = "只在 CI / 手工跑：慢或需夹具（GATES 只收几秒内的快门）"


def _gates():
    """从 release.py 里取出 GATES 元组里的名字。"""
    src = io.open(RELEASE, encoding="utf-8").read()
    m = re.search(r"GATES\s*=\s*\((.*?)\)", src, re.S)
    if not m:
        return None
    return re.findall(r'"([a-z0-9_]+)"', m.group(1))


def _files():
    return sorted(n[:-3] for n in os.listdir(HERE)
                  if n.startswith("check_") and n.endswith(".py"))


def check():
    """返回 (问题列表, 统计)。"""
    gates = _gates()
    if gates is None:
        return [u"E0 release.py 里解析不到 GATES"], {}
    files = _files()
    problems = []

    # RG1：GATES 里列了但文件不存在（陈旧行）
    for g in gates:
        if not os.path.isfile(os.path.join(HERE, g + ".py")):
            problems.append(u"RG1 GATES 列了 %s，但脚本不存在" % g)

    # RG2：每个 check_*.py 要么在 GATES，要么有理由地豁免
    for f in files:
        if f in gates:
            if f in EXEMPT:
                problems.append(
                    u"RG2 %s 已在 GATES 里，EXEMPT 里的登记陈旧" % f)
            continue
        if f in EXEMPT:
            if not EXEMPT[f].strip():
                problems.append(u"RG2 %s 的豁免没写理由" % f)
            continue
        problems.append(
            u"RG2 %s 不在发版门清单里，也没登记豁免 —— 它从没在发布时跑过" % f)

    # RG3：有没有"从没跑过"的门
    try:
        stamps = json.loads(io.open(STAMPS, encoding="utf-8").read())
    except (IOError, OSError, ValueError):
        stamps = None
    if stamps is None:
        print("  （提示）还没有 releases/gates-last-run.json —— "
              "跑一次 tools/release.py 就会生成；本次不判负")
    else:
        import datetime
        now = datetime.datetime.now()
        for g in gates:
            if g not in stamps:
                problems.append(
                    u"RG3 %s 在 GATES 里，但没有跑过的记录" % g)
                continue
            at = (stamps.get(g) or {}).get("at") or ""
            try:
                age = (now - datetime.datetime.strptime(
                    at, "%Y-%m-%dT%H:%M:%S")).days
            except (ValueError, TypeError):
                age = -1
            if age > STALE_DAYS:
                # **只提示不判负**：本仓的门是发版时跑，两次发版间隔可能很长；
                # 判负会逼着人为凑一次发布，那是更坏的结果。
                print(u"  （提示）%s 上次跑是 %d 天前，建议重跑一次" % (g, age))

    # RG4：与自己的历史比 —— 只提示，不判负（机器负载会影响单次读数）
    try:
        rows = [json.loads(x) for x in
                io.open(HISTORY, encoding="utf-8").read().splitlines()
                if x.strip()][-20:]
    except (IOError, OSError, ValueError):
        rows = []
    if len(rows) >= 3:
        now = rows[-1].get("gates") or {}
        for g in gates:
            series = [(r.get("gates") or {}).get(g) for r in rows[:-1]]
            series = sorted(v for v in series if isinstance(v, int) and v > 0)
            cur = now.get(g)
            if not series or not isinstance(cur, int):
                continue
            med = series[len(series) // 2]
            if med > 0 and cur > med * SLOW_RATIO:
                print(u"RG4 （提示）%s 这次 %dms，历史中位 %dms（%.1f 倍）"
                      % (g, cur, med, float(cur) / med))

    stats = {"gates": len(gates), "files": len(files),
             "exempt": len(EXEMPT)}
    # RG5：最近一次发版的墙钟预算
    hist = os.path.join(HERE, "..", "releases", "gates-history.jsonl")
    try:
        rows = [json.loads(x) for x in
                io.open(hist, encoding="utf-8").read().splitlines() if x.strip()]
        last = rows[-1] if rows else {}
    except (IOError, OSError, ValueError):
        last = {}
    total = int(last.get("total_ms") or 0)
    if total > BUDGET_MS:
        problems.append(u"RG5 上次发版墙钟 %d ms > 预算 %d ms —— 超出后"
                        u"\"跑一遍全量\"这个习惯会先崩" % (total, BUDGET_MS))
    stats["budget_ms"] = BUDGET_MS
    stats["last_total_ms"] = total

    return problems, stats


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--selftest" in argv:
        return selftest()

    if not os.path.isfile(RELEASE):
        print("找不到 release.py：%s" % RELEASE)
        return 2

    problems, stats = check()
    if problems:
        # problems 里的元素是**字符串**（带判据前缀）——早先按元组解包，
        # 于是"有问题的时候"这条路径必崩，用 traceback 替代了报告。
        for msg in problems:
            print("  - %s" % msg)
        print("check_release_gates: %d 项不合规" % len(problems))
        return 1

    print("check_release_gates: OK（RG1–RG5 全绿；%d 道门在发版清单里，"
          "%d 个豁免带理由，%d 个 check 脚本）"
          % (stats["gates"], stats["exempt"], stats["files"]))
    return 0


def selftest():
    """两向自证：造"漏登记"与"陈旧豁免"两种坏样本，确认判据会红。"""
    good = bad = 0

    def chk(cond, name):
        nonlocal good, bad
        if cond:
            good += 1
        else:
            bad += 1
            print("  [FAIL] %s" % name)

    real_gates = _gates()
    chk(bool(real_gates), "能从 release.py 解析出 GATES")
    chk("check_help_contract" in (real_gates or []), "GATES 里确实有已知的门")

    # 造一个临时 tools/：release.py 只列 a，实际有 a/b/c
    import shutil
    import tempfile
    d = tempfile.mkdtemp(prefix="rg_")
    try:
        for name in ("check_a.py", "check_b.py", "check_c.py"):
            io.open(os.path.join(d, name), "w", encoding="utf-8").write(
                u"pass\n")
        io.open(os.path.join(d, "release.py"), "w", encoding="utf-8").write(
            u'GATES = ("check_a", "check_missing")\n')

        # 用临时目录替换模块级路径后复用 check()
        global HERE, RELEASE, EXEMPT
        old = (HERE, RELEASE, dict(EXEMPT))
        HERE, RELEASE = d, os.path.join(d, "release.py")
        EXEMPT = {"check_b": "太重，只在 CI 跑"}
        problems, _ = check()
        chk(any(m.startswith("RG1 ") for m in problems),
            "RG1 会报 GATES 里的陈旧行（check_missing）")
        chk(any("check_c" in m for m in problems),
            "RG2 会报没登记也没豁免的 check_c.py")
        chk(not any("check_b" in m for m in problems),
            "RG2 不报有理由的豁免")

        EXEMPT = {"check_b": ""}
        problems2, _ = check()
        chk(any("没写理由" in m for m in problems2), "RG2 会报空理由的豁免")

        EXEMPT = {"check_a": "多余"}
        problems3, _ = check()
        chk(any("陈旧" in m for m in problems3), "RG2 会报陈旧豁免")

        HERE, RELEASE, EXEMPT = old[0], old[1], old[2]
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print("SELFTEST COUNTS {\"bad\": %d, \"good\": %d}" % (bad, good))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
