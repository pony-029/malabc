# -*- coding: utf-8 -*-
"""matlabc_lsp.py —— LSP 最小版。

第一版只做三件事：

    initialize            -> capabilities.textDocumentSync = 1（full 同步）
    textDocument/didOpen  -> **先返回**，再异步算（证明不阻塞协议循环）
    textDocument/publishDiagnostics -> 诊断与 `--json` 的 heuristics 同源

**唯一硬判据**（R137 文档 §3）：

    LSP 对某个 .m 文件发出的诊断
      == `matlabc.py <root> --json` 的 heuristics 里属于该文件的条目

它同时锁死三件事：stdout 没被 `print` 污染、行号没做二次偏移、诊断不是另算一遍。

两个约定（不许散落）：

- **行号 0-based 只在本文件转换**（`--json` 是 1-based）；
- **severity 映射只在本文件维护**（`level -> LSP severity`）。

用法：

    python matlabc_lsp.py            # 作为 LSP 服务（stdin/stdout 协议）

退出码：0 = 正常 EOF / `exit`；2 = 缺输入（找不到 matlabc.py）
"""
import io
import json
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
MATLABC = os.path.join(HERE, "matlabc.py")

#: `--json` 的 `level` -> LSP severity（1=Error 2=Warning 3=Information 4=Hint）
SEVERITY = {"error": 1, "warning": 2, "note": 3, "info": 3, "hint": 4}

_STATE = {"root": None, "payload": None, "result": None,
          "lock": threading.Lock()}


def _log(msg):
    sys.stderr.write("[lsp] %s\n" % msg)
    sys.stderr.flush()


# --------------------------------------------------------------------------
# 协议分帧
# --------------------------------------------------------------------------
def _read_message(stream):
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        try:
            key, val = line.decode("ascii").split(":", 1)
        except ValueError:
            continue
        headers[key.strip().lower()] = val.strip()
    try:
        n = int(headers.get("content-length", "0") or 0)
    except ValueError:
        return None
    if n <= 0:
        return None
    body = stream.read(n)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        return None


def _write_message(stream, obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    stream.write(b"Content-Length: %d\r\n\r\n" % len(body))
    stream.write(body)
    stream.flush()


# --------------------------------------------------------------------------
# 分析：**只走 CLI**，不自己算（否则就是第二事实源）
# --------------------------------------------------------------------------
def _heuristics_from_result(result):
    """把 `PipelineResult` 的 `doc_todos` 压成与 `--json` 的 `heuristics`
    **同一形状**的列表。

    `--json` 里那条（`matlabc.py` 的 `render_json`）就是：

        {"file": rel, "line": line, "func": func,
         "kind": "m_missing_doc", "msg": "...", "level": "note"}
        for t in doc_todos["todos"] if "description" in t["missing"]

    这里逐字复刻同一个过滤条件与同一组字段 —— 两个来源必须是**同一批数据**，
    否则「诊断 == heuristics」这条判据就没意义了。
    """
    model = getattr(result, "model", None)
    todos = (getattr(model, "doc_todos", None) or {}).get("todos") or []
    out = []
    for t in todos:
        if "description" not in (t.get("missing") or []):
            continue
        out.append({
            "file": t.get("rel") or "",
            "line": t.get("line") or 0,
            "func": t.get("func") or "",
            "kind": "m_missing_doc",
            "msg": "函数缺少头部描述（description）",
            "level": "note",
        })
    return out


def _run_json(root):
    """**进程内**跑分析，返回与 `--json` 同形的 `{"heuristics": [...]}`。

    为什么不再起子进程：CLI 全流程实测 **5.92s**（1300 个 .m），而
    `analyzer.api.analyze` 进程内只要 **0.73s** —— 差的 5.2 秒是
    `collect_files` 的 `os.walk`、JSON 序列化与进程启动，LSP 一样都用不上。

    仍然传 `no_checks=True`：诊断只需要 `doc_todos`，而 `_collect_checks`
    占 63%（未关时）。
    """
    try:
        from analyzer.api import analyze
    except ImportError as exc:
        _log("无法 import analyzer.api：%s" % exc)
        return None
    try:
        result = analyze(root, no_checks=True)
    except Exception as exc:                  # 分析失败不能让服务挂掉
        _log("analyze 失败：%r" % (exc,))
        return None
    # 留住整个 `PipelineResult`：`definition` 要用 `files[].functions[]`
    # 的 `(name, line)`，而 `heuristics` 只够发诊断。
    _STATE["result"] = result
    return {"heuristics": _heuristics_from_result(result)}


def _ident_at(lines, line0, char):
    """取 `line0` 行 `char` 位置上的最长标识符（`[A-Za-z0-9_]`）。"""
    if line0 < 0 or line0 >= len(lines):
        return None
    s = lines[line0]
    i = min(max(0, char), len(s))
    start, end = i, i
    while start > 0 and (s[start - 1].isalnum() or s[start - 1] == "_"):
        start -= 1
    while end < len(s) and (s[end].isalnum() or s[end] == "_"):
        end += 1
    if start == end:
        return None
    word = s[start:end]
    if not word or not (word[0].isalpha() or word[0] == "_"):
        return None
    return word


def _definition(uri, pos):
    """`textDocument/definition`：光标处标识符 -> 它的定义位置。

    判据（写在 `vscode/README.md` 里）：

        `a.m:3` 的 `b`  -> `a.m:6`（同文件，行号 0-based 5）
        `a.m:13` 的 `d` -> `d.m:1`（跨文件，行号 0-based 0）
        注释上          -> `[]`（不许假装跳转）

    **查找顺序是同文件优先**：同名函数可能定义在多个文件里，
    最近的那个是"按确定性回答"，不是"猜"。
    """
    result = _STATE.get("result")
    root = _STATE.get("root")
    if result is None or not root:
        return []
    path = _uri_to_path(uri)
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except (IOError, OSError):
        return []
    name = _ident_at(lines, int(pos.get("line", 0)),
                     int(pos.get("character", 0)))
    if name is None:
        return []

    hits = []
    for mf in (getattr(result, "files", None) or []):
        for f in (getattr(mf, "functions", None) or []):
            if getattr(f, "name", None) == name:
                hits.append((getattr(mf, "rel", "") or "",
                             getattr(f, "line", 1)))
    if not hits:
        return []

    want = os.path.basename(path).lower()
    same = [h for h in hits if os.path.basename(h[0]).lower() == want]
    rel, line1 = (same or hits)[0]
    line0 = max(0, int(line1 or 1) - 1)       # ← 唯一的 1-based -> 0-based
    target = os.path.join(root, rel.replace("/", os.sep))
    return [{
        "uri": "file:///" + target.replace("\\", "/").lstrip("/"),
        "range": {"start": {"line": line0, "character": 0},
                  "end": {"line": line0, "character": len(name)}},
    }]


def _uri_to_path(uri):
    """`file:///E:/a/b.m` -> `E:/a/b.m`。"""
    p = uri or ""
    if p.startswith("file:///"):
        p = p[8:]
    elif p.startswith("file://"):
        p = p[7:]
    from urllib.parse import unquote
    p = unquote(p)
    if os.name == "nt" and len(p) > 2 and p[0] == "/" and p[2] == ":":
        p = p[1:]
    return p.replace("/", os.sep)


def _diagnostics_for(uri):
    """从缓存的 payload 里取出**该文件**的诊断。

    过滤依据：`heuristics[].file` 与 uri 的相对路径（或 basename）相等。
    `--json` 的 `file` 是相对 root 的 posix 路径。
    """
    payload = _STATE.get("payload")
    root = _STATE.get("root")
    if not payload or not root:
        return []
    path = _uri_to_path(uri)
    try:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:
        rel = os.path.basename(path)
    base = os.path.basename(rel)

    out = []
    for h in payload.get("heuristics") or []:
        hf = (h.get("file") or "").replace("\\", "/")
        if hf != rel and os.path.basename(hf) != base:
            continue
        line1 = int(h.get("line") or 1)
        line0 = max(0, line1 - 1)               # ← 唯一的 1-based -> 0-based
        out.append({
            "range": {"start": {"line": line0, "character": 0},
                      "end": {"line": line0, "character": 1}},
            "severity": SEVERITY.get((h.get("level") or "note").lower(), 3),
            "code": h.get("kind") or "heuristic",
            "source": "matlabc",
            "message": h.get("msg") or "",
        })
    return out


def _references(uri, pos, include_decl):
    """`textDocument/references`：**函数级**引用（不是行级）。

    语义边界如实：`analyze` 的 `edges` 是 `(caller, callee, ambiguous)` 三元组，
    **不带行号**。所以这里给的是「哪个函数调用了它」，落点是那个调用者的
    **定义行**，不是调用发生的那一行。要行级引用，得先让 `edges` 带 `line`。

    `includeDeclaration=True` 时把光标所在函数自己的定义也加进去。
    """
    result = _STATE.get("result")
    root = _STATE.get("root")
    if result is None or not root:
        return []
    path = _uri_to_path(uri)
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except (IOError, OSError):
        return []
    name = _ident_at(lines, int(pos.get("line", 0)),
                     int(pos.get("character", 0)))
    if name is None:
        return []
    try:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:
        rel = os.path.basename(path)
    target = "%s:%s" % (rel, name)

    keys = []
    if include_decl:
        keys.append(target)
    for e in (getattr(result, "edges", None) or []):
        if len(e) >= 2 and e[1] == target:
            keys.append(e[0])

    fn_by_key = {}
    for mf in (getattr(result, "files", None) or []):
        for f in (getattr(mf, "functions", None) or []):
            fn_by_key["%s:%s" % (getattr(mf, "rel", ""),
                                 getattr(f, "name", ""))] = f

    out = []
    for key in keys:
        if ":" not in key:
            continue
        krel, kname = key.rsplit(":", 1)
        fn = fn_by_key.get(key)
        line0 = max(0, int(getattr(fn, "line", 1) or 1) - 1)
        tgt = os.path.join(root, krel.replace("/", os.sep))
        out.append({
            "uri": "file:///" + tgt.replace("\\", "/").lstrip("/"),
            "range": {"start": {"line": line0, "character": 0},
                      "end": {"line": line0, "character": len(kname)}},
        })
    return out


def _hover(uri, pos):
    """`textDocument/hover`：光标处标识符 -> 函数的签名 / 描述 / 复杂度。

    数据全部来自 `MatlabFunction` 的现成字段，**不重新解析**：
    `signature()` / `header["description"]` / `complexity`。
    找不到时返回 `None`（LSP 里 `null` 表示"这里没有可悬停的信息"）。
    """
    result = _STATE.get("result")
    if result is None:
        return None
    path = _uri_to_path(uri)
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except (IOError, OSError):
        return None
    name = _ident_at(lines, int(pos.get("line", 0)),
                     int(pos.get("character", 0)))
    if name is None:
        return None

    hit = None
    for mf in (getattr(result, "files", None) or []):
        for f in (getattr(mf, "functions", None) or []):
            if getattr(f, "name", None) == name:
                hit = (mf, f)
                break
        if hit:
            break
    if hit is None:
        return None
    mf, f = hit

    try:
        sig = f.signature()
    except Exception:
        sig = "function %s" % name
    desc = (getattr(f, "header", None) or {}).get("description") or ""
    parts = ["```matlab", str(sig), "```"]
    if desc:
        parts.append("")
        parts.append(str(desc))
    parts.append("")
    parts.append("复杂度 %s · 定义于 `%s:%d`"
                 % (getattr(f, "complexity", "?"), getattr(mf, "rel", ""),
                    getattr(f, "line", 0)))
    return {"contents": {"kind": "markdown", "value": "\n".join(parts)}}


#: LSP `SymbolKind.Function` = 12
_SYMBOL_FUNCTION = 12
#: LSP `SymbolKind.Class` = 5
_SYMBOL_CLASS = 5


def _document_symbols(uri):
    """`textDocument/documentSymbol`：该文件的函数列表（大纲 / 符号面板）。

    数据来自 `MatlabFunction.name` / `.line` / `.body_end` / `.kind`，
    **不重新解析**。`kind == "classdef"` 的映射成 Class，其余映射成 Function。

    `range` 覆盖函数体（`line..body_end`），`selectionRange` 只覆盖名字那一行——
    LSP 要求后者**必须**落在前者内部，否则 VSCode 会拒绝整批符号。
    """
    result = _STATE.get("result")
    root = _STATE.get("root")
    if result is None or not root:
        return []
    path = _uri_to_path(uri)
    try:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
    except ValueError:
        rel = os.path.basename(path)
    want = os.path.basename(rel).lower()

    out = []
    for mf in (getattr(result, "files", None) or []):
        if os.path.basename(getattr(mf, "rel", "") or "").lower() != want:
            continue
        for f in (getattr(mf, "functions", None) or []):
            name = getattr(f, "name", "") or ""
            if not name:
                continue
            start = max(0, int(getattr(f, "line", 1) or 1) - 1)
            end = getattr(f, "body_end", None)
            end0 = max(start, int(end) - 1) if end else start
            kind = (_SYMBOL_CLASS
                    if (getattr(f, "kind", "") or "") == "classdef"
                    else _SYMBOL_FUNCTION)
            out.append({
                "name": name,
                "kind": kind,
                "range": {"start": {"line": start, "character": 0},
                          "end": {"line": end0, "character": 0}},
                "selectionRange": {"start": {"line": start, "character": 0},
                                   "end": {"line": start,
                                           "character": len(name)}},
            })
    return out


# --------------------------------------------------------------------------
# 协议处理
# --------------------------------------------------------------------------
def handle(msg, out):
    method = msg.get("method")
    mid = msg.get("id")

    if method == "initialize":
        params = msg.get("params") or {}
        root_uri = params.get("rootUri") or ""
        if not root_uri:
            folders = params.get("workspaceFolders") or []
            if folders:
                root_uri = folders[0].get("uri") or ""
        root = _uri_to_path(root_uri) if root_uri else ""
        _STATE["root"] = root if root and os.path.isdir(root) else None
        _write_message(out, {
            "jsonrpc": "2.0", "id": mid,
            "result": {
                "capabilities": {
                    "textDocumentSync": 1,
                    # 手写客户端不会自动转 provider，这里声明只是让协议
                    # 自洽；`vscode/extension.js` 里仍需自己 register。
                    "documentSymbolProvider": True,
                },
                "serverInfo": {"name": "matlabc-lsp", "version": "0.1.0"},
            },
        })
        _log("initialize root=%r" % (_STATE["root"],))
        return True

    if method == "shutdown":
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": None})
        return True

    if method == "exit":
        return False

    if method == "textDocument/didOpen":
        uri = ((msg.get("params") or {}).get("textDocument") or {}).get("uri", "")
        # **先返回空诊断**，证明协议循环没被分析阻塞
        _write_message(out, {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": uri, "diagnostics": []},
        })

        def _later():
            root = _STATE.get("root")
            if not root:
                return
            with _STATE["lock"]:
                if _STATE["payload"] is None:
                    _log("首次分析 %s" % root)
                    _STATE["payload"] = _run_json(root)
            diags = _diagnostics_for(uri)
            _write_message(out, {
                "jsonrpc": "2.0",
                "method": "textDocument/publishDiagnostics",
                "params": {"uri": uri, "diagnostics": diags},
            })
            _log("didOpen %s -> %d 条" % (os.path.basename(uri), len(diags)))

        threading.Thread(target=_later, daemon=True).start()
        return True

    if method == "textDocument/definition":
        params = msg.get("params") or {}
        uri = (params.get("textDocument") or {}).get("uri", "")
        pos = params.get("position") or {}
        locs = _definition(uri, pos)
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": locs})
        _log("definition %s:%s -> %d"
             % (os.path.basename(_uri_to_path(uri)), pos.get("line"),
                len(locs)))
        return True

    if method == "textDocument/references":
        params = msg.get("params") or {}
        uri = (params.get("textDocument") or {}).get("uri", "")
        pos = params.get("position") or {}
        ctx = params.get("context") or {}
        locs = _references(uri, pos, bool(ctx.get("includeDeclaration")))
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": locs})
        _log("references %s:%s -> %d"
             % (os.path.basename(_uri_to_path(uri)), pos.get("line"),
                len(locs)))
        return True

    if method == "textDocument/hover":
        params = msg.get("params") or {}
        uri = (params.get("textDocument") or {}).get("uri", "")
        pos = params.get("position") or {}
        info = _hover(uri, pos)
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": info})
        _log("hover %s:%s -> %s"
             % (os.path.basename(_uri_to_path(uri)), pos.get("line"),
                "hit" if info else "none"))
        return True

    if method == "textDocument/documentSymbol":
        params = msg.get("params") or {}
        uri = (params.get("textDocument") or {}).get("uri", "")
        syms = _document_symbols(uri)
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": syms})
        _log("documentSymbol %s -> %d"
             % (os.path.basename(_uri_to_path(uri)), len(syms)))
        return True

    if method == "textDocument/didClose":
        return True

    if mid is not None:
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": None})
    return True


def main():
    if not os.path.isfile(MATLABC):
        _log("缺输入：找不到 %s" % MATLABC)
        return 2
    _log("start")
    inp = sys.stdin.buffer
    out = sys.stdout.buffer
    while True:
        msg = _read_message(inp)
        if msg is None:
            break
        try:
            if not handle(msg, out):
                break
        except Exception as exc:               # 单帧出错不能让服务挂掉
            _log("handle error: %r" % (exc,))
    return 0


if __name__ == "__main__":
    sys.exit(main())
