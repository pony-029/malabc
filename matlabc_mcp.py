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
import time

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

    # **先复用 LSP 已经写好的磁盘缓存**（R337）。编辑器里分析过一次之后，
    # 同一份结果就在 `.matlabc_lsp_cache.json` 里；MCP 再跑一遍 12 秒的
    # 结构层纯属重复劳动。缓存自带 stamp 校验，过期会自动落回重算。
    # 只取 `result`，不取 payload —— 诊断有它自己的 stamp 缓存（R336），
    # 拿结构层的空 payload 当"没有诊断"是错的。
    try:
        hit = L._load_cache(root)
    except Exception:
        hit = None
    if hit is not None:
        L._STATE["result"] = hit[0]
        L._STATE["field_index"] = None
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


def _short_desc(text):
    """取描述的第一句。小模型看清单时，一句就够，整段反而占 token。"""
    t = (text or "").strip()
    for sep in (u"。", u"；", u"\n"):
        i = t.find(sep)
        if 0 < i < 60:
            return t[:i + 1]
    return t[:60]


def t_help(args):
    """列出当前可用的工具 —— 让模型自己发现能力，而不是靠提示词猜。

    为什么这是一个**工具**而不是一段文档：小模型不会去翻 README，
    但它会调一个叫 help 的工具。给它一条低成本的自述路径，
    比在系统提示里塞一长串能力说明更省 token，也更不容易过时。
    """
    full = (args.get("detail") or "") == "full"
    vis = _visible_tools()
    out = [u"# matlabc 工具清单（当前 %d 个）" % len(vis), u""]

    for t in vis:
        if t["name"] == "matlabc_help":
            continue
        out.append(u"- **%s** — %s" % (t["name"], _short_desc(t["description"])))
        if full:
            props = (t["inputSchema"] or {}).get("properties") or {}
            req = set((t["inputSchema"] or {}).get("required") or [])
            if props:
                bits = []
                for k in sorted(props):
                    bits.append(u"%s%s" % (k, u"*" if k in req else u""))
                out.append(u"  - 参数：%s（* 为必填）" % u"、".join(bits))
            else:
                out.append(u"  - 参数：无")

    out.append(u"")
    out.append(u"## 这样问最有效")
    out.append(u"")
    out.append(u"- 用 `matlabc_stats` 看看这个工程有多少函数")
    out.append(u"- 用 `matlabc_impact`，name 传 `sqrtm`")
    out.append(u"- 用 `matlabc_outline`，path 传 `@sdpvar/sqrtm.m`")
    # **只推荐当前真的有的工具**（R332）。core 档里没有写工具，
    # 若还提示「用 propose_edit」，模型会去找一个不存在的名字 ——
    # 自述文件和实际清单不一致，比没有自述更糟。
    names = set(t["name"] for t in vis)
    if "matlabc_propose_edit" in names:
        out.append(u"")
        out.append(u"要改代码时：先 `matlabc_propose_edit` 看 diff，"
                   u"确认后 `matlabc_apply_edit`，出问题 `matlabc_undo_edit`。")
    else:
        out.append(u"")
        out.append(u"当前是精简档（`--tools core`），只含只读工具；"
                   u"需要改代码、体检、批量影响面时，请用 `--tools all` 启动。")
    out.append(u"")
    out.append(u"加 `detail=full` 可以看到每个工具的参数表。")
    return _text(u"\n".join(out))


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

    # **先看磁盘缓存**（R336）：诊断结果原来只在内存，进程一重启就要
    # 重跑一遍完整检查（YALMIP 约 70 秒）。而它其实是可复现的产物，
    # 只要工程没改就能复用 —— 判据用 LSP 那套 `_stamp`（全部文件 mtime 汇总），
    # 与缓存同一套过期规则，不另立标准。
    stamp = None
    try:
        stamp = L._stamp(root)
    except Exception:
        stamp = None
    cache = os.path.join(root, ".matlabc", "payload.json")
    if stamp is not None and os.path.isfile(cache):
        try:
            doc = json.loads(io.open(cache, "r", encoding="utf-8").read())
            if (abs(float(doc.get("stamp") or 0) - float(stamp)) < 1e-6
                    and doc.get("payload")):
                L._STATE["payload"] = doc["payload"]
                return True, 0.0
        except Exception:
            pass                       # 缓存坏了就当没有，不阻塞

    try:
        payload = L._run_json(root)
    except Exception:
        return False, time.time() - t0
    L._STATE["payload"] = payload

    # 写盘失败不算错：这次慢，下次再试。
    try:
        d = os.path.dirname(cache)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        io.open(cache, "w", encoding="utf-8", newline="").write(
            json.dumps({"stamp": stamp, "payload": payload},
                       ensure_ascii=False))
    except Exception:
        pass
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


def _fn_meta(name):
    """找到函数对象本身（复杂度、行数）。`_impact` 的返回里没有这些。"""
    result = L._STATE.get("result")
    for mf in (getattr(result, "files", None) or []):
        for f in (getattr(mf, "functions", None) or []):
            if getattr(f, "name", "") == name:
                end = getattr(f, "body_end", None)
                return {"rel": getattr(mf, "rel", "") or "",
                        "line": int(getattr(f, "line", 1) or 1),
                        "complexity": int(getattr(f, "complexity", 0) or 0),
                        "span": (int(end) - int(getattr(f, "line", 1) or 1) + 1)
                        if end else 0}
    return {}


def t_explain(args):
    """一次说清「这个函数是什么、改它有多大风险、从哪看起」。

    为什么不复用 `matlabc_impact`：impact 给的是**数据**（谁调它、它调谁），
    而模型接下来要自己做归纳。这里把归纳做掉 —— 角色、风险等级、先看哪里。
    风险规则写死在下面，可以被判据验证，不是随口说的"高风险"。
    """
    name = args.get("name") or ""
    info = L._impact(name)
    if info is None:
        return _text("`%s` 不是本工程里的函数（或还没有分析到它）。" % name)
    if info.get("pending"):
        return _text("工程索引还在建立，请稍后重试。")

    meta = _fn_meta(name)
    callers = int(info.get("total") or 0)
    chains = info.get("chains") or []
    downs = info.get("down") or []
    unresolved = int(info.get("unresolved") or 0)
    cx = meta.get("complexity", 0)

    out = ["# `%s` 速览" % name, "",
           "`%s:%d`　复杂度 %d%s"
           % (meta.get("rel", ""), meta.get("line", 0), cx,
              ("　约 %d 行" % meta["span"]) if meta.get("span") else ""), ""]

    # ---- 角色：入口 / 中间层 / 叶子，三者可组合 ----
    role = []
    if callers == 0:
        role.append("**入口**（没有任何调用者）")
    else:
        role.append("中间层（%d 个直接调用者、%d 条来路）"
                    % (callers, len(chains)))
    if not downs:
        role.append("**叶子**（不调用工程内的其他函数）")
    else:
        role.append("调用下游 %d 个" % int(info.get("down_total") or 0))
    out.append("## 角色")
    out.append("")
    out.append(" · ".join(role))
    out.append("")

    # ---- 风险：规则显式，可被验证 ----
    # **复杂度单独也能触发风险**：一个没人调用的入口，若本身很复杂，
    # 改动时同样容易出错 —— 这条是看了 switch_case（cx=8、无调用者）
    # 被判成「低」之后补上的。
    if callers >= 5 and cx >= 5:
        level, why = "高", "调用者 ≥5 且复杂度 ≥5 —— 改它要回归的入口多"
    elif cx >= 8:
        level, why = "中", "复杂度 %d —— 读和改都容易出错，与调用者多少无关" % cx
    elif unresolved >= 3:
        level, why = "中", "有 %d 处调用解析不到，影响面有一部分不可见" % unresolved
    elif callers >= 5:
        level, why = "中", "调用者 ≥5 —— 波及面广，但函数本身不复杂"
    else:
        level, why = "低", "调用者与复杂度都不高"
    out.append("## 风险")
    out.append("")
    out.append("**%s** —— %s" % (level, why))
    out.append("")

    # ---- 从哪看起：给一条具体路径，而不是一句"自己看" ----
    out.append("## 从哪看起")
    out.append("")
    if chains and callers:
        shortest = min(chains, key=len)
        out.append("- 来路最短的一条：" + " → ".join(
            "`%s`(%s:%d)" % (n["name"], n["rel"], n["line"])
            for n in shortest))
    elif callers == 0:
        out.append("- 它是入口，改它影响的是一条完整的执行路径，"
                   "没有上游需要回归")
    if downs:
        out.append("- 下游前三个：" + "、".join(
            "`%s`" % d["name"] for d in downs[:3]))
    if unresolved:
        out.append("- ⚠ 有 **%d 处调用解析不到**（外部函数或动态调用），"
                   "这部分影响面无法自动推断，需要人工确认" % unresolved)
        names = info.get("unresolved_names") or []
        if names:
            out.append("  未能解析：" + "、".join(
                "`%s`" % n for n in names[:10]))
    out.append("")
    out.append("要改它读写的数据结构时，再用 `matlabc_fields` 查对应字段的"
               "跨文件读写位置。")
    return _text("\n".join(out))


# --------------------------------------------------------------------------
# 写操作的三道护栏（R328）
#
# 只读工具错了，最坏是一次误导；写工具错了，最坏是丢掉别人一上午的工作。
# 所以「改文件」不是一个工具，而是**三步**：
#
#     propose  只算 diff，**不落盘**            —— 可以被审查
#     apply    显式带上 editId 才真正写          —— 不可能一步改坏
#     undo     从备份恢复                       —— 改错了能收拾
#
# 另外两条硬约束：
#   - 目标必须在工程根之内（防路径穿越）
#   - `oldText` 必须在文件里**恰好出现一次**（0 次是找错文件，多次是改错地方）
# --------------------------------------------------------------------------

def _edit_dir(kind):
    root = L._STATE.get("root") or "."
    d = os.path.join(root, ".matlabc", kind)
    try:
        os.makedirs(d)
    except OSError:
        pass
    return d


def _in_root(path):
    root = os.path.abspath(L._STATE.get("root") or "")
    p = os.path.abspath(path or "")
    if not root:
        return False
    return p == root or p.startswith(root + os.sep)


def t_propose_edit(args):
    """算一次改动：返回 diff 与影响面，**不写盘**。"""
    import difflib
    import hashlib
    path = _resolve(args.get("path"))
    old = args.get("oldText") or ""
    new = args.get("newText") or ""
    if not path or not os.path.isfile(path):
        return _err("找不到文件：%s" % (args.get("path") or "",))
    if not _in_root(path):
        return _err("只允许修改工程目录内的文件：%s" % path)
    if old == "":
        return _err("oldText 不能为空 —— 这里不做整文件覆写")
    try:
        src = io.open(path, "r", encoding="utf-8",
                      errors="replace").read()
    except (IOError, OSError) as exc:
        return _err("读取失败：%r" % (exc,))

    cnt = src.count(old)
    if cnt == 0:
        return _err("文件里找不到 oldText —— 可能是文件已变，或上下文抄错。"
                    "这里不会凭空写入。")
    if cnt > 1:
        return _err("oldText 在文件里出现 %d 次，请给更长的上下文"
                    "（只改一处，不能猜）。" % cnt)

    out = src.replace(old, new, 1)
    rel = _rel(path)
    diff = list(difflib.unified_diff(
        src.splitlines(), out.splitlines(),
        fromfile=rel + "（当前）", tofile=rel + "（改后）", lineterm="", n=2))
    eid = hashlib.sha1((rel + "\x00" + old + "\x00" + new)
                       .encode("utf-8")).hexdigest()[:12]
    rec = {"id": eid, "path": path, "rel": rel,
           "old": old, "new": new, "at": time.time()}
    with io.open(os.path.join(_edit_dir("pending"), eid + ".json"), "w",
                 encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, indent=2))

    rows = ["# 待确认的改动 `%s`" % eid, "",
            "```diff"] + diff[:80] + ["```", ""]
    if len(diff) > 80:
        rows.append("（diff 过长，仅显示前 80 行）")
        rows.append("")
    # 影响面：改这个文件会波及谁 —— 让 apply 之前就能判断值不值得。
    try:
        ch = L._STATE.get("result")
        if ch is not None:
            _t = []
            for mf in (getattr(ch, "files", None) or []):
                if (getattr(mf, "rel", "") or "") == rel:
                    _t = [getattr(f, "name", "") for f in
                          (getattr(mf, "functions", None) or [])]
                    break
            if _t:
                _info = L._impact(_t[0])
                if _info and not _info.get("pending"):
                    rows.append("## 影响面")
                    rows.append("")
                    rows.append("这个文件里的 `%s` 有 %d 个直接调用者。"
                                % (_t[0], int(_info.get("total") or 0)))
                    rows.append("")
    except Exception:
        pass

    rows.append("**这一步没有写盘。** 确认无误后调用 "
                "`matlabc_apply_edit`（editId=`%s`）才会真正落盘；"
                "落盘前会自动备份，之后可用 `matlabc_undo_edit` 恢复。" % eid)
    return _text("\n".join(rows))


def t_apply_edit(args):
    """真正写入。写前再校验一次，并保留备份。"""
    eid = (args.get("editId") or "").strip()
    if not eid:
        return _err("editId 不能为空")
    rec_path = os.path.join(_edit_dir("pending"), eid + ".json")
    if not os.path.isfile(rec_path):
        return _err("找不到 editId=`%s` 的待确认改动（可能已应用或进程重启）"
                    % eid)
    rec = json.loads(io.open(rec_path, "r", encoding="utf-8").read())
    path = rec.get("path") or ""
    if not _in_root(path):
        return _err("目标文件不在工程目录内")
    if not os.path.isfile(path):
        return _err("目标文件已不存在：%s" % path)
    src = io.open(path, "r", encoding="utf-8", errors="replace").read()
    # **再校验一次**：propose 与 apply 之间文件可能被编辑器改过。
    if src.count(rec.get("old") or "") != 1:
        return _err("文件在确认期间发生了变化，oldText 不再唯一匹配。"
                    "请重新 propose。")

    import shutil
    # **备份按 editId 建目录，并写 meta.json 记下目标路径**（R329）。
    # 第一版把文件名编码成 `t.m.<时间>.bak`，undo 时靠 split('.') 反推目标
    # —— 名字里本来就有点，于是反推成 `t`，恢复写到了另一个文件上，
    # 原文件纹丝不动，还回了句「已恢复」。这种错必须靠记录，不能靠猜。
    bak_dir = os.path.join(_edit_dir("backup"), eid)
    try:
        os.makedirs(bak_dir)
    except OSError:
        pass
    bak = os.path.join(bak_dir, "orig.bak")
    try:
        shutil.copy2(path, bak)
        with io.open(os.path.join(bak_dir, "meta.json"), "w",
                     encoding="utf-8", newline="") as fh:
            fh.write(json.dumps({"target": path,
                                 "rel": rec.get("rel") or "",
                                 "at": time.time()},
                                ensure_ascii=False, indent=2))
        out = src.replace(rec.get("old") or "", rec.get("new") or "", 1)
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(out)
    except (IOError, OSError) as exc:
        return _err("写入失败：%r" % (exc,))
    try:
        os.remove(rec_path)
    except OSError:
        pass
    return _text("已写入 `%s`。\n\n备份 id：`%s`\n\n"
                 "要撤销请调用 `matlabc_undo_edit`，backup=`%s`。"
                 % (rec.get("rel") or path, eid, eid))


def t_undo_edit(args):
    """从备份恢复。目标路径从 `meta.json` 读，**不靠文件名反推**。"""
    import shutil
    eid = (args.get("backup") or "").strip()
    if not eid:
        return _err("backup 不能为空（apply 的返回里有这个值）")
    bak_dir = os.path.join(_edit_dir("backup"), os.path.basename(eid))
    meta_p = os.path.join(bak_dir, "meta.json")
    bak = os.path.join(bak_dir, "orig.bak")
    if not os.path.isfile(meta_p) or not os.path.isfile(bak):
        return _err("找不到备份 `%s`（apply 的返回里给的备份 id）" % eid)
    try:
        meta = json.loads(io.open(meta_p, "r", encoding="utf-8").read())
    except Exception as exc:
        return _err("备份元数据损坏：%r" % (exc,))
    target = meta.get("target") or ""
    if not target or not _in_root(target):
        return _err("备份记录的目标文件不在工程目录内")
    try:
        shutil.copy2(bak, target)
    except (IOError, OSError) as exc:
        return _err("恢复失败：%r" % (exc,))
    return _text("已从备份 `%s` 恢复 `%s`。" % (eid, meta.get("rel") or target))


# --------------------------------------------------------------------------
# 批量写操作（R334）：一次改多个文件，**要么全成、要么全不成**。
#
# 为什么需要：真实的重构从来不是改一个文件 —— 改一个函数签名要同时动
# 调用方、文档、测试。一个个 apply 的问题不是慢，而是**改到一半停下**：
# 前 3 个已落盘、第 4 个校验失败，此时仓库处于一个谁也没设计过的状态。
#
# 所以这里的关键不是「批量」，是「事务」：
#   1. 先校验**全部**（任一 oldText 不唯一 → 整体拒绝，一个字节都不写）
#   2. 再备份**全部**
#   3. 最后逐个写入；任何一个写失败，把已写的按备份回滚
# --------------------------------------------------------------------------

_BATCH_LIMIT = 20


def _batch_dir(kind):
    return _edit_dir(kind)


def t_propose_edits(args):
    """一次算多个文件的改动，**不落盘**，返回 batchId 与逐文件 diff。"""
    import difflib
    import hashlib
    edits = args.get("edits") or []
    if not isinstance(edits, list) or not edits:
        return _err("edits 不能为空：给一个数组，每项含 path / oldText / newText")
    if len(edits) > _BATCH_LIMIT:
        return _err("一次最多 %d 个文件" % _BATCH_LIMIT)

    items, problems, rows = [], [], []
    for i, e in enumerate(edits):
        path = _resolve((e or {}).get("path"))
        old = (e or {}).get("oldText") or ""
        new = (e or {}).get("newText") or ""
        label = (e or {}).get("path") or ("#%d" % (i + 1))
        if not path or not os.path.isfile(path):
            problems.append(u"%s：找不到文件" % label)
            continue
        if not _in_root(path):
            problems.append(u"%s：不在工程目录内" % label)
            continue
        if old == "":
            problems.append(u"%s：oldText 不能为空" % label)
            continue
        try:
            src = io.open(path, "r", encoding="utf-8",
                          errors="replace").read()
        except (IOError, OSError) as exc:
            problems.append(u"%s：读取失败 %r" % (label, exc))
            continue
        cnt = src.count(old)
        if cnt == 0:
            problems.append(u"%s：找不到 oldText（不会凭空写入）" % label)
            continue
        if cnt > 1:
            problems.append(u"%s：oldText 出现 %d 次，请给更长上下文"
                            % (label, cnt))
            continue
        items.append({"path": path, "old": old, "new": new,
                      "rel": _rel(path), "src": src})

    if problems:
        # **一条不合格就整体拒绝** —— 半批改动比不改更糟。
        return _err(u"这批改动有 %d 处不合法，整批未生成：\n\n%s"
                    % (len(problems), u"\n".join(u"- " + p for p in problems)))

    batch = hashlib.sha1(
        (u"|".join(it["rel"] + it["old"] for it in items))
        .encode("utf-8")).hexdigest()[:12]
    rec = {"batch": batch, "at": time.time(),
           "items": [{"path": it["path"], "rel": it["rel"],
                      "old": it["old"], "new": it["new"]} for it in items]}
    with io.open(os.path.join(_batch_dir("pending"), "batch-" + batch + ".json"),
                 "w", encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, indent=2))

    rows = [u"# 待确认的批量改动 `%s`（%d 个文件）" % (batch, len(items)), u""]
    for it in items:
        out = it["src"].replace(it["old"], it["new"], 1)
        diff = list(difflib.unified_diff(
            it["src"].splitlines(), out.splitlines(),
            fromfile=it["rel"] + u"（当前）", tofile=it["rel"] + u"（改后）",
            lineterm="", n=1))
        rows.append(u"## `%s`" % it["rel"])
        rows.append(u"")
        rows.append(u"```diff")
        rows.extend(diff[:24])
        rows.append(u"```")
        rows.append(u"")
    rows.append(u"**这一步没有写盘。** 确认后调用 `matlabc_apply_edits`"
                u"（batchId=`%s`）；它要么全部写入，要么一个都不写。" % batch)
    return _text(u"\n".join(rows))


def t_apply_edits(args):
    """事务性写入：全部校验 → 全部备份 → 逐个写，失败回滚。"""
    import shutil
    batch = (args.get("batchId") or "").strip()
    if not batch:
        return _err("batchId 不能为空")
    rec_path = os.path.join(_batch_dir("pending"), "batch-" + batch + ".json")
    if not os.path.isfile(rec_path):
        return _err("找不到 batchId=`%s` 的批量改动" % batch)
    rec = json.loads(io.open(rec_path, "r", encoding="utf-8").read())
    items = rec.get("items") or []

    # ---- 第一步：重新校验全部（propose 与 apply 之间文件可能被改过）----
    fresh = []
    for it in items:
        path = it.get("path") or ""
        if not os.path.isfile(path) or not _in_root(path):
            return _err("目标文件不可用：%s —— 整批未写入" % (it.get("rel"),))
        try:
            src = io.open(path, "r", encoding="utf-8",
                          errors="replace").read()
        except (IOError, OSError) as exc:
            return _err("读取 %s 失败：%r —— 整批未写入"
                        % (it.get("rel"), exc))
        if src.count(it.get("old") or "") != 1:
            return _err("`%s` 在确认期间已被改动，oldText 不再唯一匹配 —— "
                        "整批未写入" % (it.get("rel"),))
        fresh.append((it, src))

    # ---- 第二步：全部备份 ----
    bak_dir = os.path.join(_batch_dir("backup"), "batch-" + batch)
    try:
        os.makedirs(bak_dir)
    except OSError:
        pass
    metas = []
    for idx, (it, src) in enumerate(fresh):
        bak = os.path.join(bak_dir, "%d.bak" % idx)
        try:
            shutil.copy2(it["path"], bak)
        except (IOError, OSError) as exc:
            return _err("备份 `%s` 失败：%r —— 整批未写入"
                        % (it.get("rel"), exc))
        metas.append({"target": it["path"], "rel": it.get("rel"),
                      "bak": os.path.basename(bak)})
    with io.open(os.path.join(bak_dir, "meta.json"), "w",
                 encoding="utf-8", newline="") as fh:
        fh.write(json.dumps({"batch": batch, "at": time.time(),
                             "items": metas}, ensure_ascii=False, indent=2))

    # ---- 第三步：逐个写入；失败就回滚已写的 ----
    done = []
    try:
        for (it, src) in fresh:
            out = src.replace(it.get("old") or "", it.get("new") or "", 1)
            with io.open(it["path"], "w", encoding="utf-8", newline="") as fh:
                fh.write(out)
            done.append(it["path"])
    except (IOError, OSError) as exc:
        for m in metas[:len(done)]:
            try:
                shutil.copy2(os.path.join(bak_dir, m["bak"]), m["target"])
            except Exception:
                pass
        return _err("写入第 %d 个文件时失败：%r —— 已回滚之前的 %d 个"
                    % (len(done) + 1, exc, len(done)))

    try:
        os.remove(rec_path)
    except OSError:
        pass
    rows = [u"已写入 %d 个文件：" % len(done), u""]
    for m in metas:
        rows.append(u"- `%s`" % m["rel"])
    rows.append(u"")
    rows.append(u"备份 id：`%s`；要整体撤销请调用 `matlabc_undo_edits`。"
                % batch)
    return _text(u"\n".join(rows))


def t_undo_edits(args):
    """把一批改动整体恢复。"""
    import shutil
    batch = (args.get("batchId") or "").strip()
    if not batch:
        return _err("batchId 不能为空")
    bak_dir = os.path.join(_batch_dir("backup"), "batch-" + batch)
    meta_p = os.path.join(bak_dir, "meta.json")
    if not os.path.isfile(meta_p):
        return _err("找不到批次 `%s` 的备份" % batch)
    meta = json.loads(io.open(meta_p, "r", encoding="utf-8").read())
    rows, failed = [], []
    for it in (meta.get("items") or []):
        target = it.get("target") or ""
        bak = os.path.join(bak_dir, it.get("bak") or "")
        if not _in_root(target) or not os.path.isfile(bak):
            failed.append(it.get("rel") or target)
            continue
        try:
            shutil.copy2(bak, target)
            rows.append(u"- 已恢复 `%s`" % (it.get("rel") or target))
        except (IOError, OSError):
            failed.append(it.get("rel") or target)
    if failed:
        return _err(u"以下文件恢复失败：%s" % u"、".join(failed))
    return _text(u"已整体恢复（%d 个文件）：\n\n%s"
                 % (len(rows), u"\n".join(rows)))


def t_cbridge(args):
    """跨语言桥接：MATLAB 里解析不到的调用，在 C 源里找到了定义。

    为什么 Agent 需要它：`mex`/`calllib` 造成的「未解析」会让影响面分析
    在边界处停住，而 Agent 往往就此给出「没有更多调用者」的结论 ——
    实际上下面还有一整层 C 代码。
    """
    name = args.get("name") or ""
    r = L._c_bridge(name)
    if not r.get("available"):
        if (r.get("reason") or "") == "pending":
            return _text("工程索引还在建立，请稍后重试。")
        return _text("这个工程里没有 C 源文件（.c/.cpp），"
                     "无法做跨语言桥接。")
    items = r.get("items") or []
    unresolved = r.get("unresolved") or []
    if not items and not unresolved:
        return _text(u"`%s` 没有解析不到的调用，也没有 C 桥接。" % name)

    out = [u"# `%s` 的跨语言调用" % name, u""]
    if items:
        out.append(u"## 在 C 源里找到定义（%d 处）" % len(items))
        out.append(u"")
        for it in items[:20]:
            out.append(u"- `%s` ← `%s`　%s:%d　（调用 %d 次）"
                       % (it["matlab"], it["callee"], it["c_rel"],
                          it["c_line"], it["count"]))
            # C 内部的下一跳：链路到这里还没结束，别让它又断一次
            for _d in (it.get("c_down") or [])[:8]:
                out.append(u"    - `%s` 内部调用 `%s`（line %d）"
                           % (it["c_name"], _d["name"], _d["line"]))
        out.append(u"")
    bins = r.get("binaries") or []
    if bins:
        out.append(u"## 二进制提供（%d 处）" % len(bins))
        out.append(u"")
        out.append(u"入口名写在文件名上，不需要解析机器码：")
        out.append(u"")
        for it in bins[:15]:
            out.append(u"- `%s` → `%s`（%s）"
                       % (it["callee"], it["rel"], it["kind"]))
        out.append(u"")

    calls = r.get("calllib") or []
    if calls:
        out.append(u"## calllib 调用（%d 处）" % len(calls))
        out.append(u"")
        out.append(u"已核对库的导出表：")
        out.append(u"")
        for c in calls[:15]:
            mark = (u"✓ 已导出" if c.get("exported") is True
                    else (u"✗ 该库没有这个导出" if c.get("exported") is False
                          else u"? 库未找到"))
            out.append(u"- `%s('%s', '%s')`　%s"
                       % ("calllib", c.get("lib"), c.get("fn"), mark))
        out.append(u"")

    if unresolved:
        out.append(u"## 仍然连不上（%d 个）" % len(unresolved))
        out.append(u"")
        out.append(u"这些名字在工程内的 C 源里也没有定义，"
                   u"大概率来自 mex 二进制或工具箱：")
        out.append(u"")
        out.append(u"、".join(u"`%s`" % n for n in unresolved[:15]))
        out.append(u"")
    out.append(u"（本次扫描 %d 个 C 源文件、%d 个二进制。）"
               % (r.get("scanned") or 0, r.get("bin_scanned") or 0))

    # **证据来源必须写出来**（R344）：读者要能分清哪条来自内置解析、
    # 哪条来自外部工具，否则事后无法复核。
    rea = r.get("rea") or {}
    out.append(u"")
    if rea.get("available"):
        out.append(u"外部二进制工具（rea）：已安装可运行。")
        # **能跑 ≠ 能干活**：rea 的二进制布局分析实测只吃 Linux x64 ELF。
        # 说「可用」而不说「能覆盖什么」，就等于暗示它比实际更强。
        if rea.get("binary_scope_note"):
            out.append(u"注意：%s。所以上面的 PE 导出结论来自内置解析，"
                       u"将来接 rea 时也补不上这一块。"
                       % rea["binary_scope_note"])
    else:
        out.append(u"外部二进制工具（rea）：不可用 —— %s。"
                   u"上面的二进制结论仅来自内置解析（文件名匹配 + PE 导出表）。"
                   % (rea.get("reason") or u"未知原因"))
    return _text(u"\n".join(out))


def t_changed(args):
    """「我改了这几个文件，谁需要先回归」——比结构 diff 更贴近 Agent 的任务。

    为什么不做 `--diff-html` 那种快照对比
    ------------------------------------
    快照对比要求调用方**手上已经有两个 JSON 产物**。人做评审时会有，
    Agent 在「我刚改完，帮我看看影响」这个场景下不会有 —— 它只有
    **改完之后的当前工程**。

    而这个问题不需要历史快照：**文件里的每个函数，它的上游就是受影响面**。
    上游一直存在，只是没人问过。

    代价：每个函数一次 `_impact`（内部要遍历全库建索引）。所以对文件数
    和函数数都设了上限，并在返回里写明实际算了多少个。
    """
    files = args.get("files") or []
    if isinstance(files, str):
        files = [files]
    if not files:
        return _err("files 不能为空：给一个相对或绝对路径的数组")
    if len(files) > 10:
        return _err("一次最多分析 10 个文件（每个文件里的函数都要单独求上游）")

    result = L._STATE.get("result")
    if result is None:
        return _text("工程索引还在建立，请稍后重试。")

    # 文件 -> 它定义的函数（按相对路径匹配，也认 basename）
    wanted = {}
    for f in files:
        p = _resolve(f)
        wanted[_rel(p)] = True
        wanted[os.path.basename(p)] = True

    targets = []            # (rel, 函数名)
    for mf in (getattr(result, "files", None) or []):
        rel = getattr(mf, "rel", "") or ""
        if rel not in wanted and os.path.basename(rel) not in wanted:
            continue
        for fn in (getattr(mf, "functions", None) or []):
            targets.append((rel, getattr(fn, "name", "") or ""))
    if not targets:
        return _text("这些文件里没有解析到函数：%s" % "、".join(files))

    capped = targets[:30]
    entries = {}            # 入口函数 -> 受影响的 (rel:fn)
    affected = []           # (源函数, 入口, 链)
    for rel, nm in capped:
        info = L._impact(nm)
        if not info or info.get("pending"):
            continue
        for ch in (info.get("chains") or []):
            if not ch:
                continue
            entry = ch[0]["name"]
            entries.setdefault(entry, []).append("%s:%s" % (rel, nm))
            affected.append((nm, entry, ch))

    out = ["# 变更影响面（%d 个文件 / %d 个函数）" % (len(files), len(capped)),
           ""]
    if not affected:
        out.append("这些函数**没有上游调用者** —— 改它们不会波及本工程内的"
                   "其他函数（它们本身就是入口）。")
        out.append("")
        out.append("仍建议确认：它们是否被工程之外的脚本调用。")
        return _text("\n".join(out))

    out.append("## 需要回归的入口（按波及函数数排序）")
    out.append("")
    for entry in sorted(entries, key=lambda k: -len(entries[k]))[:10]:
        names = sorted(set(entries[entry]))
        out.append("- `%s` —— 波及 %d 个函数" % (entry, len(names)))
        out.append("  " + "、".join("`%s`" % n for n in names[:6])
                   + ("…" if len(names) > 6 else ""))
    out.append("")
    out.append("## 一条完整来路（示例）")
    out.append("")
    shortest = min(affected, key=lambda a: len(a[2]))
    out.append("- " + " → ".join(
        "`%s`(%s:%d)" % (n["name"], n["rel"], n["line"]) for n in shortest[2]))
    if len(capped) > 30:
        out.append("")
        out.append("⚠ 函数数超过 30，只分析了前 30 个。")
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
    {"name": "matlabc_help",
     "description": "列出当前可用的工具与推荐问法。不确定能做什么、"
                    "或不确定该调哪个工具时，先调它 —— 比让模型凭印象猜便宜。"
                    "传 detail=full 可看每个工具的参数表。",
     "inputSchema": {"type": "object",
                     "properties": {"detail": _STR},
                     "required": []},
     "handler": t_help},

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

    {"name": "matlabc_propose_edits",
     "description": "**批量**：一次算多个文件的改动，不落盘，返回 batchId 与"
                    "逐文件 diff。只要有一个文件的 oldText 不唯一，整批拒绝生成。"
                    "真实重构通常要同时改几个文件时用它，而不是逐个 propose。",
     "inputSchema": {"type": "object",
                     "properties": {"edits": {
                         "type": "array",
                         "items": {"type": "object",
                                   "properties": {"path": _STR,
                                                  "oldText": _STR,
                                                  "newText": _STR},
                                   "required": ["path", "oldText",
                                                "newText"]}}},
                     "required": ["edits"]},
     "handler": t_propose_edits},

    {"name": "matlabc_apply_edits",
     "description": "把一批改动**事务性**写入：全部校验 → 全部备份 → 逐个写，"
                    "任何一个失败就回滚已写的。要么全成，要么一个都不改。",
     "inputSchema": {"type": "object",
                     "properties": {"batchId": _STR},
                     "required": ["batchId"]},
     "handler": t_apply_edits},

    {"name": "matlabc_undo_edits",
     "description": "把一批改动**整体**恢复（batchId 来自 apply_edits 的返回）。",
     "inputSchema": {"type": "object",
                     "properties": {"batchId": _STR},
                     "required": ["batchId"]},
     "handler": t_undo_edits},

    {"name": "matlabc_propose_edit",
     "description": "**不落盘**地算一次改动：返回 diff 与影响面，并给出 editId。"
                    "oldText 必须在文件里恰好出现一次（0 次说明找错了，多次"
                    "说明会改错地方，都会直接报错）。确认无误后再调用 "
                    "matlabc_apply_edit。改代码前应当先 propose 并读一遍 diff。",
     "inputSchema": {"type": "object",
                     "properties": {"path": _STR, "oldText": _STR,
                                    "newText": _STR},
                     "required": ["path", "oldText", "newText"]},
     "handler": t_propose_edit},

    {"name": "matlabc_apply_edit",
     "description": "把 propose 过的改动真正写入磁盘。会再校验一次 oldText "
                    "是否仍唯一匹配（防止期间文件被改），并自动备份。"
                    "落盘后可用 matlabc_undo_edit 恢复。",
     "inputSchema": {"type": "object",
                     "properties": {"editId": _STR},
                     "required": ["editId"]},
     "handler": t_apply_edit},

    {"name": "matlabc_undo_edit",
     "description": "从备份恢复某个文件（backup 值来自 apply 的返回）。"
                    "改动出问题时用它，而不是靠记忆手改回去。",
     "inputSchema": {"type": "object",
                     "properties": {"backup": _STR},
                     "required": ["backup"]},
     "handler": t_undo_edit},

    {"name": "matlabc_cbridge",
     "description": "跨语言桥接：某个 MATLAB 函数里解析不到的调用，"
                    "在工程内的 C 源（.c/.cpp）里是否有同名定义，并给出行号。"
                    "分析 mex / calllib 场景时用它，否则调用链会在边界处断掉。",
     "inputSchema": {"type": "object",
                     "properties": {"name": _STR},
                     "required": ["name"]},
     "handler": t_cbridge},

    {"name": "matlabc_changed",
     "description": "「我刚改了这几个文件，谁需要先回归」—— 给出受影响的入口"
                    "与波及的函数清单，按波及面排序。"
                    "比拿两个快照做结构 diff 更贴近改完代码当下的问题。"
                    "一次最多 10 个文件。",
     "inputSchema": {"type": "object",
                     "properties": {"files": {"type": "array",
                                              "items": _STR}},
                     "required": ["files"]},
     "handler": t_changed},

    {"name": "matlabc_explain",
     "description": "一个函数的**速览**：它是什么角色（入口/中间层/叶子）、"
                    "改动风险等级与理由、以及从哪看起。"
                    "比 impact 更适合「我要改这个函数，先了解一下」这种开场，"
                    "因为它给的是结论而不是原始列表。",
     "inputSchema": {"type": "object",
                     "properties": {"name": _STR},
                     "required": ["name"]},
     "handler": t_explain},

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

#: 精简模式只暴露这几个（R330）。
#:
#: 起因：本地 27B 模型跑在 16GB 显卡上，上下文只能开 4096 —— 而 14 个工具的
#: description 本身就要 2000~3000 token，加上客户端系统提示，**还没发问就先超了**。
#: 所以给一个「核心 6 个」的档位：覆盖「了解工程 / 看结构 / 查影响 / 查字段」。
#: 完整档位（all）留给上下文充足的情况，不要为了省钱删能力，只是分档。
CORE_TOOLS = ("matlabc_help", "matlabc_stats", "matlabc_outline",
              "matlabc_impact", "matlabc_explain", "matlabc_fields",
              "matlabc_search")

#: 由 `--tools` 决定，main() 里设置。
_TOOL_MODE = ["all"]


def _visible_tools():
    if _TOOL_MODE[0] == "core":
        return [t for t in TOOLS if t["name"] in CORE_TOOLS]
    return TOOLS


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
        for t in _visible_tools():
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
    ap.add_argument("--tools", default="all", choices=("all", "core"),
                    help="暴露的工具集：all=全部，core=核心 6 个"
                         "（本地小上下文模型的显存档位，省 token）")
    ap.add_argument("--cross-lang", dest="cross_lang", default="on",
                    choices=("on", "off"),
                    help="跨语言分析（C 源 / mex / DLL 导出表）："
                         "off 时不扫描这些文件，桥接直接回 disabled")
    ns = ap.parse_args(argv)
    _TOOL_MODE[0] = ns.tools
    L._STATE["cross_lang"] = (ns.cross_lang == "on")
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
