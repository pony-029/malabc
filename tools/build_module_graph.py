# -*- coding: utf-8 -*-
"""从 `check_import_graph` 的模块级边生成模块边界图（Mermaid）。

为什么是 Mermaid 而不是再画一张 archify：
    模块边界图的价值在**边**（谁 import 谁、有几条），而 archify 的
    architecture 图需要手工布局 10 个组、还要维护 EN 版与 SVG。Mermaid
    在 GitHub/VS Code 里直接渲染，边由 `check_import_graph.scan()` 现算，
    不会出现“图画好了、边是手写的”这种双事实源。

口径（写进产物，避免读者误解）：
    - 只取**模块级** import（import 期图），函数内 import 不计；
    - 排除 tests / tools / harness / ci-examples / setup（开发设施，不是运行时模块）；
    - 节点是**聚合组**，不是 139 个单文件；
    - 组内边不画，跨组边标数字。

用法：
    python tools/build_module_graph.py
    python tools/build_module_graph.py --check
    python tools/build_module_graph.py --json
"""
import argparse
import io
import json
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "docs", "architecture", "MODULE_GRAPH.md")

sys.path.insert(0, HERE)
import check_import_graph as cig  # noqa: E402

#: 顶层模块名 -> 聚合组；None = 开发设施，不进运行时边界图。
GROUP = {
    "matlabc": "core", "matlabc_boot": "core", "matlabc_help": "core",
    "gui": "core", "entity_model": "core", "pyast_frontend": "core",
    "unified_graph": "core", "concurrency": "core", "matlabc_task": "core",
    "frontends": "frontends",
    "renderers": "renderers",
    "matlabc_lsp": "lsp",
    "matlabc_mcp": "ai", "matlabc_ask": "ai", "ai_cli": "ai",
    "agent_loop": "flow", "matlabc_flow": "flow",
    "analyzer_memory": "flow",
    "binfmt": "binary", "callrel": "binary", "binhops": "binary",
    "translate": "translate",
    "analyzer": "analyzer", "fe_audit": "analyzer",
    "tests": None, "tools": None, "harness": None,
    "ci-examples": None, "setup": None,
}

LABEL = {
    "core": "核心 / 单文件内核",
    "frontends": "多语言前端",
    "renderers": "渲染与输出",
    "lsp": "LSP 服务端",
    "ai": "AI / MCP",
    "flow": "修复闭环",
    "binary": "二进制分析",
    "translate": "MATLAB→C 移植",
    "analyzer": "分析/审计",
}
ORDER = ("core", "frontends", "renderers", "lsp", "ai", "flow",
         "binary", "translate", "analyzer")


def _top(mod):
    return (mod or "").split(".")[0]


def collect():
    files = cig.read_repo(ROOT)
    built = cig.scan(files)
    known = built.get("known") or {}
    groups = {}
    for mod in known:
        g = GROUP.get(_top(mod))
        if g:
            groups.setdefault(g, []).append(mod)
    edges = Counter()
    for src, dsts in (built.get("edges_mod") or {}).items():
        gs = GROUP.get(_top(src))
        if not gs:
            continue
        for dst in dsts:
            gd = GROUP.get(_top(dst))
            if gd and gd != gs:
                edges[(gs, gd)] += 1
    return groups, edges, built


def _mermaid(groups, edges):
    lines = ["```mermaid", "graph LR"]
    for g in ORDER:
        if g not in groups:
            continue
        lines.append('  %s["%s<br/>%d modules"]'
                     % (g, LABEL.get(g, g), len(groups[g])))
    for (a, b), n in sorted(edges.items(),
                            key=lambda kv: (-kv[1], kv[0][0], kv[0][1])):
        lines.append("  %s -->|%d| %s" % (a, n, b))
    lines.append("```")
    return "\n".join(lines)


def render():
    groups, edges, built = collect()
    out_deg = Counter()
    in_deg = Counter()
    for (a, b), n in edges.items():
        out_deg[a] += n
        in_deg[b] += n
    lines = [
        "# malabc 模块边界图（自动生成）",
        "",
        "> 由 `python tools/build_module_graph.py` 从 `check_import_graph` 的",
        "> **模块级 import** 边现算；不要手改。",
        "",
        "- 运行时模块：%d 个；跨组边：%d 条；模块级环：%d"
        % (sum(len(v) for v in groups.values()),
           sum(edges.values()), len(built.get("self_mod") or [])),
        "- 排除：tests / tools / harness / ci-examples / setup（开发设施）",
        "- 口径：只画 import 期边；函数内惰性 import 不计入",
        "",
        "## 图",
        "",
        _mermaid(groups, edges),
        "",
        "## 分组明细",
        "",
        "| 组 | 模块数 | 出边 | 入边 | 代表模块 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for g in ORDER:
        if g not in groups:
            continue
        mods = sorted(groups[g])
        sample = ", ".join(mods[:5])
        if len(mods) > 5:
            sample += " …"
        lines.append("| **%s** (`%s`) | %d | %d | %d | `%s` |"
                     % (LABEL.get(g, g), g, len(mods),
                        out_deg.get(g, 0), in_deg.get(g, 0), sample))
    lines += [
        "",
        "## 怎么读",
        "",
        "- `core -->|14| renderers`：内核在 import 期直接依赖 14 条渲染边；",
        "  渲染器只消费模型，不应反向 import 内核（`check_import_graph` G1 守环）。",
        "- `flow -->|1| ai`、`ai -->|1| lsp`：闭环/AI/LSP 之间只有少量窄边；",
        "  新增跨组依赖时，先问“能不能走惰性通道”，再决定是否登记。",
        "- 没有箭头的组 = 当前没有 import 期跨组依赖，不代表永远不会有。",
        "",
        "## 重新生成",
        "",
        "```bash",
        "python tools/build_module_graph.py",
        "python tools/build_module_graph.py --check   # 产物过期即红",
        "```",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成模块边界图（Mermaid）")
    ap.add_argument("--check", action="store_true", help="只校验产物是否最新")
    ap.add_argument("--json", action="store_true", help="打印分组/边统计")
    args = ap.parse_args(argv)
    text = render()
    if args.json:
        groups, edges, _ = collect()
        print(json.dumps({
            "groups": dict((g, len(v)) for g, v in groups.items()),
            "edges": dict(("%s->%s" % k, n) for k, n in edges.items()),
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.check:
        cur = ""
        if os.path.isfile(OUT):
            with io.open(OUT, "r", encoding="utf-8") as fh:
                cur = fh.read()
        if cur != text:
            print("MODULE_GRAPH.md 已过期，请重跑 tools/build_module_graph.py")
            return 1
        print("build_module_graph: OK（MODULE_GRAPH.md 与 import 图一致）")
        return 0
    d = os.path.dirname(OUT)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(OUT, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(text)
    print("wrote %s（%d bytes）" % (OUT, os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
