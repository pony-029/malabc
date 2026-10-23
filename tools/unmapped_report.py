# -*- coding: utf-8 -*-
"""unmapped_report —— 按函数排行"还差多少"，并给出原因构成。

为什么需要它：真实工程里 `TODO(unmapped)` 只有一个总数（YALMIP 是 1343），
看不出**该先动哪个函数**。排行榜把"要改哪几行"变成可执行清单。

与 `parity_report` 的分工：
    parity_report   回答"哪些函数两边算过且一致"（对拍）
    unmapped_report 回答"哪些函数最值得先补"（排序 + 归因）

用法：
    python tools/unmapped_report.py --mir E:\\m2c\\yalmip.mir --top 15
    python tools/unmapped_report.py --mir x.mir --include-rejected  # 连被拒函数一起看

    默认**排除被整函数拒绝的**函数：它们的未映射语句永远不可达，
    排进榜单会把"该做什么"指向死路（YALMIP 的 dualize 就是这样占榜首八轮的）。

退出码：
    0  正常输出（本工具不判红，只出清单）
    2  参数或文件不可用
"""
import io
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import mir_eval  # noqa: E402


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--mir" not in argv:
        print("用法: python tools/unmapped_report.py --mir <x.mir> [--top N]")
        return 2
    path = argv[argv.index("--mir") + 1]
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 12
    if not os.path.isfile(path):
        print("找不到 %s" % path)
        return 2

    funcs = mir_eval.parse(io.open(path, encoding="utf-8").read())
    rows = []
    include_rej = "--include-rejected" in argv
    for f in funcs:
        rejected = getattr(f, "reject", None)
        if rejected and not include_rej:
            continue          # 被拒函数：这些语句永远到不了，不该混进"待办"
        if not f.unmapped:
            continue
        rows.append((int(f.unmapped), f.name))   # unmapped 是**计数**

    rows.sort(key=lambda r: (-r[0], r[1]))
    total_rej = sum(1 for f in funcs if getattr(f, "reject", None))
    total_un = sum(r[0] for r in rows)
    print("函数 %d ｜ 被整函数拒绝 %d ｜ **可做**（未拒但有未映射）%d（合计 %d 条）"
          % (len(funcs), total_rej, len(rows), total_un))
    if total_rej:
        print("  注：被拒函数的未映射语句永远不可达，本表默认不列它们；"
              "加 --include-rejected 可看全量")
    print("")
    print("%-40s %6s" % ("函数", "未映射条数"))
    for n, name in rows[:top]:
        print("%-40s %6d" % (name[:40], n))
    return 0


def _kind(line):
    """粗归因（与 mir.py 的 `# why:` 同口径，这里按原文再判一次）。"""
    t = (line or "").strip()
    if "{" in t or "}" in t:
        return "cell"
    if ".(" in t.replace(" ", "") or any(
            ch == "." for ch in t) and "(" in t:
        return "struct"
    if t.startswith(("if", "while", "switch", "try")):
        return "cond/control"
    if "(" in t and ("," in t or ":" in t):
        return "slice2d/call"
    return "other"


if __name__ == "__main__":
    sys.exit(main())
