# -*- coding: utf-8 -*-
"""渲染工具：**不依赖任何分析结果**的纯字符串 / 路径辅助。

从 `matlabc.py` 搬出（R132，P2 的第一步）。判据：`--browse` 站点逐字节不变。

为什么先搬这七个：依赖分析显示它们 **deps=0**（`_src_href_from_rel` 只依赖同文件的
`_page_rel`），而 22 个渲染函数依赖它们。先有这一层，后续渲染函数搬出时才不会
反向依赖 `matlabc`（`check_import_graph` 的 G1 禁止 `renderers` 模块级 import 产品文件）。
"""

def _mermaid_label(s):
    """Mermaid 节点 label 转义（反斜杠与引号）。"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _dot_label(s):
    """Graphviz DOT 字符串转义（反斜杠与引号）。"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _page_rel(rel):
    """源码页相对 src 目录的页面路径（raw，不编码），既用于写盘也用于 href。

    关键修复：此前对相对路径做 urllib.parse.quote 编码，导致含 '+' 的文件
    以字面量 '%2B…' 落盘，而浏览器 / 文件协议会把 href 中的 '%2B' 解码回
    '+'，于是 MATLAB 包目录（+pkg）、类文件夹（@Cls）等含 '+' 的链接指向了
    磁盘上不存在的文件。这里统一用**原始相对路径**，写盘与 href 完全一致，
    彻底消除该断链问题。
    """
    return rel + ".html"


def _html_esc(s):
    """极简 HTML 转义（避免引入额外依赖，保持与既有页面一致）。"""
    return ("" if s is None else str(s)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _compliance_score(summary):
    """合规得分（0-100）：按官方严重度加权扣分（error 最重）。

    权重沿用官方「errors > warnings > suggestions」的优先级：
    每个 error 扣 8 分、warning 扣 3 分、suggestion 扣 1 分，下限 0。
    """
    pen = summary.get("error", 0) * 8 + summary.get("warning", 0) * 3 \
        + summary.get("suggestion", 0) * 1
    return max(0, 100 - pen)


def _shp_str(shp):
    if shp is None:
        return '?'
    if not shp:
        return '标量'
    # 形状可能来自 _es_eval 的任意标记：正常为 [('c',n)/('u',)], 但特殊结构体
    # 标记（如 ('struct',)）或意外标量/字符串会破坏逐维下标访问，这里统一防御，
    # 避免 IndexError 使整个报告生成崩溃（P224-Y）。
    if isinstance(shp, str):
        return shp
    try:
        _dims = list(shp)
    except TypeError:
        return str(shp)
    out = []
    for d in _dims:
        if isinstance(d, str):
            out.append(d)
            continue
        try:
            _tag = d[0]
        except (TypeError, IndexError):
            out.append(str(d))
            continue
        if _tag == 'c':
            try:
                out.append(str(d[1]))
            except (TypeError, IndexError):
                out.append('?')
        elif _tag == 'u':
            out.append('?')
        elif _tag == 'struct':
            out.append('结构体')
        else:
            try:
                out.append('size(%s,%d)' % (d[1], d[2]))
            except (TypeError, IndexError):
                out.append('?')
    return '×'.join(out)


def _src_href_from_rel(rel):
    return f"src/{_page_rel(rel)}"
