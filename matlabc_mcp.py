#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matlabc MCP server —— 把 MATLAB 工程理解能力交给任意 AI Agent。

为什么是 MCP 而不是再加几个命令
================================

编辑器里的 LSP **只服务于"人正在看的那一行"**：F12、悬停、大纲 —— 都是以
光标为圆心的一次查询。而 Agent 的工作方式是**从一个任务出发**：

    「把 callpop 改成支持整数变量，告诉我谁会受影响」

这句话需要的是：它调用了谁、谁调用了它、来路有几条、哪些地方解析不到。
这些能力**项目里全都有**（`_impact` / `_heat` / `_references`），**只是没有
一个 Agent 能调用的入口** —— LSP 的 stdio 协议是给编辑器的，Agent 说不上话。

MCP（Model Context Protocol）正好是这一层的标准：JSON-RPC、stdio 传输、
工具带 schema。所以这里**不重写分析**，只做一层"翻译"：

    MCP 工具调用  ->  复用 matlabc_lsp 里的查询函数  ->  Markdown 文本

文本而不是 JSON：读它的是语言模型，表格和缩进比嵌套字段好读得多。

用法
====

    python matlabc_mcp.py --root C:\\path\\to\\project

在 Agent 侧配置（Claude Desktop / Cursor / CodeBuddy 等）：

    {
      "mcpServers": {
        "matlabc": {
          "command": "python",
          "args": ["E:/matlabc/malabc/matlabc_mcp.py",
                   "--root", "C:/Temp/yalmip"]
        }
      }
    }

传输是 **JSON lines**（每条消息一行，MCP 的 stdio transport 约定），
与 LSP 的 `Content-Length` 头不同 —— 这一点容易写错。


工具分层（设计约束，不是随手加的）
==================================

**快工具**（毫秒级，走结构层 `analyze(no_checks=True)`）：

    matlabc_stats         工程规模
    matlabc_outline       文件里有什么
    matlabc_search        按名字找
    matlabc_impact        谁调用它 / 它调用谁
    matlabc_heat          先看哪几个
    matlabc_definition    跳到定义
    matlabc_references    被谁引用
    matlabc_fields        字段读写溯源

**慢工具**（首次数十秒，需要完整检查 `_run_json`）：

    matlabc_diagnostics   工程体检

分层不是性能细节，而是**给模型的预算提示**：description 里明写
「首次约 1 分钟」，模型才会在「只是想看看结构」时不误调它。
把慢操作混进快工具，会让每一个简单问题都变慢。

三条硬约束
----------

1. **一个工具回答一个完整问题**，而不是镜像一个函数。
   `matlabc_fields` 返回的是「6 个基名，不是同一个结构体」这样的结论，
   不是 `{writes: [...], reads: [...]}` 这样的原始结构。

2. **输出是 Markdown**。读它的是语言模型，表格比嵌套字段省 token。

3. **每个工具都有判据**，且判据用临时语料自建 —— 不依赖任何本地工程。
"""

import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matlabc_lsp as L                      # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "matlabc"
SERVER_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# 工程加载：**懒加载**。MCP 客户端启动时会立刻 initialize，如果那时就分析
# 整个工程（YALMIP 约 70 秒），客户端多半会先超时。改为首次工具调用再做。
# --------------------------------------------------------------------------

def _ensure_loaded():
    """确保 root/result 就绪；返回 (ok, message)。"""
    root = L._STATE.get("root")
    if not root:
        return False, "未指定工程目录（启动时用 --root）"
    if L._STATE.get("result") is not None:
        return True, ""
    try:
        from analyzer.api import analyze
    except Exception as exc:                 # pragma: no cover
        return False, "无法加载分析器：%r" % (exc,)
    try:
        L._STATE["result"] = analyze(root, no_checks=True)
    except Exception as exc:
        return False, "分析失败：%r" % (exc,)
    L._STATE["field_index"] = None
    return True, ""


def _uri(path):
    p = os.path.abspath(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return "file://" + p


def _resolve(p):
    """相对路径按工程根解析。Agent 传 `solver/a.m` 是常态，
    要求它每次拼绝对路径既啰嗦又容易错。"""
    if not p:
        return ""
    if os.path.isabs(p):
        return p
    root = L._STATE.get("root") or ""
    return os.path.join(root, p) if root else os.path.abspath(p)


def _rel(path):
    root = L._STATE.get("root") or ""
    try:
        return os.path.relpath(os.path.abspath(path),
                               root).replace(os.sep, "/")
    except ValueError:
        return os.path.basename(path)


def _text(s):
    return {"content": [{"type": "text", "text": s}]}


def _err(s):
    return {"content": [{"type": "text", "text": s}], "isError": True}


# --------------------------------------------------------------------------
# 工具实现：每个函数返回 Markdown 文本
# --------------------------------------------------------------------------

def t_outline(args):
    path = _resolve(args.get("path"))
    if not path or not os.path.isfile(path):
        return _err("找不到文件：%s" % path)
    syms = L._document_symbols(_uri(path))
    if not syms:
        return _text("`%s` 里没有识别到 function。" % os.path.basename(path))
    rows = ["# %s" % _rel(path), "",
            "| 函数 | 行 |", "| --- | --- |"]
    for s in syms:
        rows.append("| `%s` | %d |" % (s["name"],
                                       s["range"]["start"]["line"] + 1))
    return _text("\n".join(rows))


def t_impact(args):
    name = args.get("name") or ""
    info = L._impact(name)
    if info is None:
        return _text("`%s` 不是本工程里的函数（或还没有分析到它）。" % name)
    if info.get("pending"):
        return _text("工程索引还在建立，请稍后重试。")
    # `target` 是**名字字符串**，位置在 `definitions` 里
    # —— 顶层既没有 `rel` 也没有 `line`，直接取会得到空串。
    tg = (info.get("definitions") or [{}])[0]
    out = ["# `%s` 的影响面" % name, "",
           "`%s:%d` · 调用者 %d · 下游 %d"
           % (tg.get("rel", ""), tg.get("line", 0),
              info.get("total", 0), info.get("down_total", 0)), ""]
    chains = info.get("chains") or []
    # 没有调用者时，「来路」只会列出它自己 —— 那是噪音，不是信息。
    if chains and info.get("direct"):
        out.append("## 来路（入口 → 目标，%d 条）" % len(chains))
        out.append("")
        for ch in chains[:12]:
            out.append("- " + " → ".join(
                "`%s`(%s:%d)" % (n["name"], n["rel"], n["line"]) for n in ch))
        if len(chains) > 12:
            out.append("- … 另有 %d 条" % (len(chains) - 12))
        out.append("")
    direct = info.get("direct") or []
    out.append("## 直接调用者（%d）" % len(direct))
    out.append("")
    for d in direct[:20]:
        out.append("- `%s`　%s:%d" % (d["name"], d["rel"], d["line"]))
    if not direct:
        out.append("- （无 —— 它是入口）")
    out.append("")
    down = info.get("down") or []
    out.append("## 它调用（%d）" % (info.get("down_total") or 0))
    out.append("")
    for d in down[:20]:
        out.append("- `%s`　%s:%d　第 %d 层"
                   % (d["name"], d["rel"], d["line"], d.get("level", 1)))
    if not down:
        out.append("- （无 —— 它是叶子）")
    if info.get("unresolved"):
        out.append("")
        out.append("另有 %d 处调用**解析不到**（外部函数或动态调用），"
                   "这部分影响面无法自动推断。" % info["unresolved"])
        names = info.get("unresolved_names") or []
        if names:
            out.append("未能解析的名字：" + "、".join(
                "`%s`" % n for n in names[:15]))
    return _text("\n".join(out))


def t_heat(args):
    try:
        limit = int(args.get("limit") or 15)
    except (TypeError, ValueError):
        limit = 15
    dirs = args.get("dir") or None
    rows = L._heat(max(1, min(limit, 200)), prefix=dirs)
    if rows is None:
        return _text("工程索引还在建立，请稍后重试。")
    if not rows:
        return _text("该范围内没有可排行的函数。")
    out = ["# 热点函数（复杂度 × (1 + 调用者数)）", "",
           "| # | 函数 | 位置 | 复杂度 | 调用者 | 得分 |",
           "| --- | --- | --- | --- | --- | --- |"]
    for i, r in enumerate(rows):
        out.append("| %d | `%s` | `%s:%d` | %d | %d | %d |"
                   % (i + 1, r["name"], r["rel"], r["line"],
                      r["complexity"], r["callers"], r["score"]))
    out.append("")
    out.append("两项都高才算热点：只复杂但没人调用是死角，"
               "被到处调用但只有一行是封装。")
    return _text("\n".join(out))


def t_definition(args):
    path = _resolve(args.get("path"))
    if not path or not os.path.isfile(path):
        return _err("找不到文件：%s" % path)
    res = L._definition(_uri(path), {"line": int(args.get("line") or 0),
                                     "character": int(args.get("character") or 0)})
    if not res:
        return _text("该位置没有可跳转的定义（可能是注释、关键字，"
                     "或解析不到的调用）。")
    out = []
    for r in res:
        p = L._uri_to_path(r["uri"])
        out.append("- `%s:%d`" % (_rel(p), r["range"]["start"]["line"] + 1))
    return _text("\n".join(out))


def t_references(args):
    path = _resolve(args.get("path"))
    if not path or not os.path.isfile(path):
        return _err("找不到文件：%s" % path)
    res = L._references(_uri(path), {"line": int(args.get("line") or 0),
                                     "character": int(args.get("character") or 0)},
                        True)
    if not res:
        return _text("没有找到引用（函数级引用需要它被其他函数调用过）。")
    out = ["# 引用（%d 处）" % len(res), ""]
    for r in res[:60]:
        p = L._uri_to_path(r["uri"])
        out.append("- `%s:%d`" % (_rel(p), r["range"]["start"]["line"] + 1))
    if len(res) > 60:
        out.append("- … 另有 %d 处" % (len(res) - 60))
    return _text("\n".join(out))


def _ensure_payload():
    """拿到带**检查结果**的 payload（`heuristics`）。

    与 `_ensure_loaded` 不同：结构层（`analyze(no_checks=True)`）只给
    文件/函数/边，**不含诊断**；诊断必须跑完整一遍 `_run_json`。
    YALMIP 实测约 70 秒，所以只在真正需要时付这个代价 —— 也就是
    `matlabc_diagnostics` 被调用的那一刻。
    """
    if L._STATE.get("payload"):
        return True, 0.0
    root = L._STATE.get("root")
    if not root:
        return False, 0.0
    import time
    t0 = time.time()
    try:
        L._STATE["payload"] = L._run_json(root)
    except Exception as exc:
        return False, time.time() - t0
    return True, time.time() - t0


def t_diagnostics(args):
    """工程体检：按类别分组列出诊断（HTML 报告里那一栏）。"""
    path = _resolve(args.get("path"))
    ok, secs = _ensure_payload()
    if not ok:
        return _text("诊断需要完整分析，当前工程还没准备好（或分析失败）。")
    payload = L._STATE.get("payload") or {}
    items = payload.get("heuristics") or []
    if path:
        base = os.path.basename(path)
        rel = _rel(path) if os.path.isabs(path) else path
        items = [h for h in items
                 if h.get("file") in (rel, base)]
    if not items:
        return _text("没有诊断项 —— 这份代码在当前规则下是干净的。"
                     if not path else
                     "`%s` 没有诊断项。" % os.path.basename(path))

    by_kind = {}
    for h in items:
        by_kind.setdefault(h.get("kind") or "?", []).append(h)

    out = ["# 诊断（%d 项%s）" % (len(items),
                                 "，全量分析 %.0fs" % secs if secs > 1 else ""),
           ""]
    # **按严重度再按类别**：错误比警告先看，同类聚在一起才好修。
    order = sorted(by_kind.items(),
                   key=lambda kv: (0 if (kv[1][0].get("level") == "error")
                                   else 1, -len(kv[1])))
    for kind, lst in order:
        lvl = lst[0].get("level") or "info"
        out.append("## %s（%d · %s）" % (kind, len(lst), lvl))
        out.append("")
        for h in lst[:12]:
            out.append("- `%s:%d`　`%s`　%s"
                       % (h.get("file", ""), int(h.get("line") or 0),
                          h.get("func", "") or "-", h.get("msg", "")))
        if len(lst) > 12:
            out.append("- … 另有 %d 处同类" % (len(lst) - 12))
        out.append("")
    out.append("提示：`path` 参数可只看单个文件；"
               "首次调用会跑完整检查，之后走缓存。")
    return _text("\n".join(out))


def t_fields(args):
    """结构体字段的**跨文件读写溯源**（HTML 报告里的「跨文件变量溯源」）。

    为什么 Agent 需要它：改一个结构体字段时，真正的问题是「谁在写它、
    谁在读它、有没有同名不同结构体」。`field_access` 里本来就有
    writes/reads 和基名，LSP 侧只在 F12 时用了一小部分。
    """
    name = args.get("name") or ""
    result = L._STATE.get("result")
    if result is None:
        return _text("工程索引还在建立，请稍后重试。")
    ent = (L._field_index(result) or {}).get(name) or {}
    writes = list(ent.get("writes") or [])
    reads = list(ent.get("reads") or [])
    if not writes and not reads:
        return _text("没有找到字段 `%s` 的读写记录。" % name)

    def norm(row):
        row = list(row or []) + ["", "", 0, "?"]
        return row[0], row[1], int(row[2] or 0), (row[3] or "?")

    by_base = {}
    for row in writes:
        rel, fn, ln, base = norm(row)
        by_base.setdefault(base, []).append((rel, fn, ln, "写"))
    for row in reads:
        rel, fn, ln, base = norm(row)
        by_base.setdefault(base, []).append((rel, fn, ln, "读"))

    out = ["# 结构体字段 `%s`" % name, "",
           "写入 %d 处、读取 %d 处，涉及 %d 个基名。"
           % (len(writes), len(reads), len(by_base)), ""]
    if len(by_base) > 1:
        out.append("⚠ 同名字段挂在多个基名上 —— 它们**不是同一个结构体**，"
                   "改名或改语义要分别处理。")
        out.append("")
    for base in sorted(by_base)[:10]:
        items = by_base[base]
        out.append("## `%s.%s`（%d 处）" % (base, name, len(items)))
        out.append("")
        for rel, fn, ln, kind in items[:14]:
            out.append("- %s　`%s`　%s:%d" % (kind, fn, rel, ln))
        if len(items) > 14:
            out.append("- … 另有 %d 处" % (len(items) - 14))
        out.append("")
    return _text("\n".join(out))


def t_stats(args):
    """工程概览：规模、入口数、最复杂的几个 —— 让 Agent 先有全局感。"""
    result = L._STATE.get("result")
    if result is None:
        return _text("工程索引还在建立，请稍后重试。")
    files = getattr(result, "files", None) or []
    edges = getattr(result, "edges", None) or []
    nfn = 0
    top = []
    for mf in files:
        for f in (getattr(mf, "functions", None) or []):
            nfn += 1
            cx = int(getattr(f, "complexity", 0) or 0)
            top.append((cx, getattr(f, "name", ""), getattr(mf, "rel", ""),
                        int(getattr(f, "line", 1) or 1)))
    top.sort(key=lambda t: (-t[0], t[1]))
    out = ["# 工程概览", "",
           "| 项 | 值 |", "| --- | --- |",
           "| 文件 | %d |" % len(files),
           "| 函数 | %d |" % nfn,
           "| 调用边 | %d |" % len(edges),
           "| 根目录 | `%s` |" % (L._STATE.get("root") or ""), ""]
    if top:
        out.append("## 最复杂的函数（前 5）")
        out.append("")
        for cx, nm, rel, ln in top[:5]:
            out.append("- `%s`　%s:%d　复杂度 %d" % (nm, rel, ln, cx))
    return _text("\n".join(out))


def t_search(args):
    pat = (args.get("pattern") or "").lower()
    if not pat:
        return _err("pattern 不能为空")
    try:
        limit = int(args.get("limit") or 30)
    except (TypeError, ValueError):
        limit = 30
    result = L._STATE.get("result")
    if result is None:
        return _text("工程索引还在建立，请稍后重试。")
    hits = []
    for mf in (getattr(result, "files", None) or []):
        rel = getattr(mf, "rel", "") or ""
        for f in (getattr(mf, "functions", None) or []):
            nm = getattr(f, "name", "") or ""
            if pat in nm.lower():
                hits.append((nm, rel, int(getattr(f, "line", 0) or 1)))
                if len(hits) >= limit:
                    break
        if len(hits) >= limit:
            break
    if not hits:
        return _text("没有名字匹配 `%s` 的函数。" % pat)
    out = ["# 名字含 `%s` 的函数（%d）" % (pat, len(hits)), "",
           "| 函数 | 位置 |", "| --- | --- |"]
    for nm, rel, ln in hits:
        out.append("| `%s` | `%s:%d` |" % (nm, rel, ln))
    return _text("\n".join(out))


# --------------------------------------------------------------------------
# 工具清单（schema 里写清"什么时候该用它"，Agent 靠这句话决定调不调）
# --------------------------------------------------------------------------

_STR = {"type": "string"}
_INT = {"type": "integer"}

TOOLS = [
    {"name": "matlabc_outline",
     "description": "列出一个 .m 文件里定义的函数及其行号。"
                    "用于快速了解一个文件的结构，不要用它去猜"
                    "别的文件里有什么。",
     "inputSchema": {"type": "object",
                     "properties": {"path": _STR},
                     "required": ["path"]},
     "handler": t_outline},

    {"name": "matlabc_impact",
     "description": "查询一个函数的**影响面**：谁调用它（含从入口到它的完整"
                    "来路）、它调用谁、以及有多少处调用无法解析。"
                    "改代码之前应该先调它，用来回答「动这里会波及什么」。",
     "inputSchema": {"type": "object",
                     "properties": {"name": _STR},
                     "required": ["name"]},
     "handler": t_impact},

    {"name": "matlabc_heat",
     "description": "按「复杂度 × 调用者数」排出热点函数，"
                    "回答「接手这个工程先看哪几个」。"
                    "可选 dir 只看某个目录（跨模块的分数没有可比性）。",
     "inputSchema": {"type": "object",
                     "properties": {"dir": _STR, "limit": _INT},
                     "required": []},
     "handler": t_heat},

    {"name": "matlabc_definition",
     "description": "给定文件和 0-based 行列位置，返回跳转目标"
                    "（函数定义、变量/字段首次赋值、global 声明）。",
     "inputSchema": {"type": "object",
                     "properties": {"path": _STR, "line": _INT,
                                    "character": _INT},
                     "required": ["path", "line", "character"]},
     "handler": t_definition},

    {"name": "matlabc_references",
     "description": "查询某个位置上的函数被谁调用，"
                    "以及全局变量在哪些文件的哪些行出现"
                    "（分成定义 / 声明 / 使用三类）。",
     "inputSchema": {"type": "object",
                     "properties": {"path": _STR, "line": _INT,
                                    "character": _INT},
                     "required": ["path", "line", "character"]},
     "handler": t_references},

    {"name": "matlabc_diagnostics",
     "description": "工程体检：按类别列出诊断（未初始化、未使用、隐式转换等），"
                    "按严重度排序，可按 path 只看一个文件。"
                    "**首次调用需要跑完整检查（大工程约 1 分钟）**，之后走缓存；"
                    "只想看结构时不要调它。",
     "inputSchema": {"type": "object",
                     "properties": {"path": _STR},
                     "required": []},
     "handler": t_diagnostics},

    {"name": "matlabc_fields",
     "description": "查询一个结构体字段的**跨文件读写位置**，按基名分组。"
                    "改结构体字段之前调它：能看到谁在写、谁在读，"
                    "以及同名字段是不是挂在多个不同结构体上。",
     "inputSchema": {"type": "object",
                     "properties": {"name": _STR},
                     "required": ["name"]},
     "handler": t_fields},

    {"name": "matlabc_stats",
     "description": "工程规模概览：文件数、函数数、调用边数、最复杂的几个函数。"
                    "第一次接触一个工程时先用它建立全局感，再决定深入哪里。",
     "inputSchema": {"type": "object", "properties": {}, "required": []},
     "handler": t_stats},

    {"name": "matlabc_search",
     "description": "按名字子串搜索工程里的函数。"
                    "当你知道大致名字但不确定在哪个文件时用它。",
     "inputSchema": {"type": "object",
                     "properties": {"pattern": _STR, "limit": _INT},
                     "required": ["pattern"]},
     "handler": t_search},
]

_BY_NAME = dict((t["name"], t) for t in TOOLS)


# --------------------------------------------------------------------------
# 协议层
# --------------------------------------------------------------------------

def _handle(msg):
    method = msg.get("method")
    mid = msg.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }}

    if method in ("notifications/initialized", "initialized"):
        return None                      # 通知不需要回应

    if method == "tools/list":
        items = []
        for t in TOOLS:
            items.append({"name": t["name"],
                          "description": t["description"],
                          "inputSchema": t["inputSchema"]})
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": items}}

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name") or ""
        args = params.get("arguments") or {}
        tool = _BY_NAME.get(name)
        if tool is None:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32601, "message": "未知工具：%s" % name}}
        ok, why = _ensure_loaded()
        if not ok:
            return {"jsonrpc": "2.0", "id": mid, "result": _err(why)}
        try:
            return {"jsonrpc": "2.0", "id": mid,
                    "result": tool["handler"](args)}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": mid,
                    "result": _err("工具执行失败：%r" % (exc,))}

    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}

    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": "未知方法：%s" % method}}


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--root", default=os.getcwd(),
                    help="MATLAB 工程根目录（默认当前目录）")
    ns = ap.parse_args(argv)
    root = os.path.abspath(ns.root)
    if not os.path.isdir(root):
        sys.stderr.write("matlabc-mcp: 目录不存在：%s\n" % root)
        return 2
    L._STATE["root"] = root
    L._STATE["result"] = None           # 懒加载

    out = io.open(1, "w", encoding="utf-8", newline="\n")
    for line in io.open(0, "r", encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        resp = _handle(msg)
        if resp is not None:
            out.write(json.dumps(resp, ensure_ascii=False) + "\n")
            out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
