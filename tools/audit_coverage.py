# -*- coding: utf-8 -*-
"""覆盖度量：每个 MCP 工具，**判据**与**全场景**各自真的调用过它吗？

为什么单独一个工具
==================

`check_tool_discoverability` 只保证「工具在 README 里出现」，
而"出现"与"被测"是两件事。第 2 版复盘里我用**子串匹配**审计过一次，
结论是 19/19 全覆盖 —— 而那是个假数：`matlabc_cbridge` 出现在注释里
也算"提到"。改成**数真实调用点**（`_call(sess, "matlabc_x")` /
`_MCP.t_x(`），差距立刻显形。

判据来源：
    tools/lsp_selftest.py   进程内直接调 `_MCP.t_xxx(...)`
    tools/rsi_scenarios.py  走协议 `_call(sess, "matlabc_xxx", ...)`

用法：
    python tools/audit_coverage.py
    python tools/audit_coverage.py --json

退出码：
    0  = 两个来源都覆盖到全部工具
    1  = 有工具没被任何一方真正调用（**这是可见性，不是门禁**）
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def _read(name):
    return io.open(os.path.join(HERE, name), "r", encoding="utf-8").read()


def collect():
    import matlabc_mcp as M
    names = [t["name"] for t in M.TOOLS]

    sel = _read("lsp_selftest.py")
    sc = _read("rsi_scenarios.py")

    # 判据：进程内调用 `_MCP.t_xxx(` —— 注意要把 `t_` 前缀**去掉**再拼，
    # 否则得到 `matlabc_t_impact`，永远匹配不上（第一版就是这样，
    # 于是"判据"那一列全是空 —— 全空也是个可疑信号，值得先怀疑自己）。
    judged = set("matlabc_" + m[2:] for m in
                 re.findall(r"_MCP\.(t_[a-z_]+)\s*\(", sel))
    # 场景：走协议 `_call(<any>, "matlabc_xxx"`（排除 tools/call 的裸字符串）
    scenario = set(re.findall(r'_call\([^,]+,\s*"(matlabc_[a-z_]+)"', sc))

    rows = []
    for n in names:
        rows.append({"tool": n,
                     "judged": n in judged,
                     "scenario": n in scenario})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    if args.help:
        sys.stdout.write(__doc__)
        return 0

    rows = collect()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0 if all(r["judged"] or r["scenario"] for r in rows) else 1

    print("%-22s %-6s %-6s" % ("工具", "判据", "场景"))
    for r in rows:
        print("%-22s %-8s %-8s"
              % (r["tool"],
                 "✓" if r["judged"] else "·",
                 "✓" if r["scenario"] else "·"))
    both = [r for r in rows if r["judged"] and r["scenario"]]
    none = [r["tool"] for r in rows if not r["judged"] and not r["scenario"]]
    judged_only = [r["tool"] for r in rows if r["judged"] and not r["scenario"]]
    print("")
    print("合计 %d 个工具：两处都覆盖 %d / 仅判据 %d / 仅场景 %d / 都没有 %d"
          % (len(rows), len(both), len(judged_only),
             len([r for r in rows if r["scenario"] and not r["judged"]]),
             len(none)))
    if none:
        print("都没有：" + "、".join(none))
    return 0 if not none else 1


if __name__ == "__main__":
    sys.exit(main())
