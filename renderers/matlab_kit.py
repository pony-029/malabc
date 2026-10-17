# -*- coding: utf-8 -*-
"""渲染工具：三个**零模块级依赖**的纯函数。

从 `matlabc.py` 搬出（R156，P2 第一批）。判据：

- `--json`：`tools/json_diff.py before after --ignore generated_at` → rc=0
- `--browse`：`tools/tree_diff.py A B --ignore-line "generated_at|生成时间"
  --ignore-file "manifest\\.json"` → rc=0

为什么先搬这三个：依赖分析（`globs ∩ Load`）实测它们 **deps=0**，且各自只有
1 处调用（都在 `render_markdown_report` 里）。它们不 import `matlabc`，
所以 `renderers/` 不会反向依赖产品文件（`check_import_graph` 的 G1）。
"""

def render_tree(files, root, rel):
    """生成目录树文本。files: [(rel, kind)]"""
    lines_out = []
    tree = {}
    for r, _ in files:
        parts = r.split("/")
        node = tree
        for p in parts:
            node = node.setdefault(p, {})
    # 递归绘制
    def walk(node, prefix, is_last, is_root=False):
        items = list(node.items())
        for i, (name, sub) in enumerate(items):
            if is_root:
                lines_out.append(f"📁 {name}/")
            else:
                conn = "└── " if i == len(items) - 1 else "├── "
                lines_out.append(prefix + conn + name)
            nxt_prefix = prefix + ("    " if i == len(items) - 1 else "│   ")
            walk(sub, nxt_prefix, i == len(items) - 1)
    lines_out.append(f"{root}/")
    walk(tree, "", True, False)
    return "\n".join(lines_out)


def render_call_chain(outgoing, incoming, nodes, max_entries=50):
    """生成「从入口到末端」的调用树文本行列表（树形缩进，标注调用层级）。

    入口 = 项目内没有被任何函数调用的函数（通常是主函数/脚本/回调入口）。
    自顶向下展示「谁先执行、再调用了谁」，直观反映从头到尾的执行路径；
    每行标注调用深度（距入口的层级），便于快速判断执行先后顺序。
    """
    lines = []
    if not nodes:
        return lines
    entries = sorted(n for n in nodes if not incoming.get(n))
    if not entries:
        entries = sorted(nodes)[:1]  # 全是环，任取其一作为入口
    for entry in entries[:max_entries]:
        lines.append("【入口】" + entry)
        visited = set()

        def walk(node, depth, stack):
            for callee in sorted(outgoing.get(node, ())):
                indent = "    " * (depth + 1)
                lines.append(indent + "└── [%d] %s" % (depth + 1, callee))
                if callee in stack:
                    lines.append(indent + "    (循环调用，已截断)")
                    continue
                if callee in visited:
                    lines.append(indent + "    (已在当前链路出现，已截断)")
                    continue
                visited.add(callee)
                walk(callee, depth + 1, stack + (callee,))

        visited.add(entry)
        walk(entry, 0, (entry,))
        lines.append("")
    if len(entries) > max_entries:
        lines.append("（入口函数过多，仅展示前 %d 个；完整关系见 Mermaid / DOT 图）" % max_entries)
    return lines


def render_call_detail(outgoing, incoming, nodes, max_nodes=300,
                       label_to_func=None, ambiguous=None):
    """逐函数列出：它调用了谁、被谁调用（双向关系）。

    label_to_func: 节点标签 -> MatlabFunction，用于显示类型 / 文件；
    ambiguous: 集合，元素为 "调用方标签:被调短名"，命中则提示该调用存在同名歧义。
    """
    lines = []
    shown = 0
    for node in sorted(nodes):
        lines.append("#### `" + node + "`")
        func = label_to_func.get(node) if label_to_func else None
        if func is not None:
            kind = getattr(func, "kind", "")
            src = func.mfile.rel if func.mfile else "?"
            lines.append("- 类型：%s · 文件：`%s`" % (kind, src))
        outs = sorted(outgoing.get(node, ()))
        ins = sorted(incoming.get(node, ()))
        if outs:
            lines.append("- 调用了（%d）：" % len(outs) + "、".join("`%s`" % c for c in outs))
        else:
            lines.append("- 调用了：无（末端 / 叶子函数）")
        if ins:
            lines.append("- 被调用（%d）：" % len(ins) + "、".join("`%s`" % c for c in ins))
        else:
            lines.append("- 被调用：无（入口函数）")
        if ambiguous and node in ambiguous:
            lines.append("- ⚠ 该函数存在**同名函数歧义**：部分被调名在多处定义，"
                         "链接已尽量就近解析，可能并非你期望的目标。")
        lines.append("")
        shown += 1
        if shown >= max_nodes:
            lines.append("（参与调用的函数过多，仅展示前 %d 个）" % max_nodes)
            break
    return lines
