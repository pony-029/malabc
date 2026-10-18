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
    path = args.get("path") or ""
    if not os.path.isfile(path):
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
    if chains:
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
    path = args.get("path") or ""
    if not os.path.isfile(path):
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
    path = args.get("path") or ""
    if not os.path.isfile(path):
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
