# -*- coding: utf-8 -*-
"""matlabc_lsp.py —— 最小 LSP 服务（第一版只做三件）。

    initialize             -> capabilities.textDocumentSync = 1（full）
    textDocument/didOpen   -> 先回空诊断，再异步算
    textDocument/didClose  -> 清理

**stdout 只走 `Content-Length` 分帧的 JSON-RPC**；所有日志走 stderr。
这条纪律是硬性的：LSP 客户端会把 stdout 的每个字节都当成协议。

诊断为什么先是空的：`analyzer.api.analyze` 返回的 `PipelineResult` 上**没有**
`heuristics`（实测在 `result.checks_for_sarif` 里，且它不是 heuristics 的别名，
见 R134）。要让它非空，必须先有事实层（facts）。所以这里**不假装**：
`publishDiagnostics` 发空数组，stderr 写明原因。

用法：

    python matlabc_lsp.py            # 作为 LSP 服务（stdin/stdout 协议）

退出码：0 = 正常 EOF / `exit`。
"""
import io
import json
import os
import sys
from urllib.parse import unquote, urlparse

VERSION = "0.1.0"

#: 会话状态：`initialize` 存 root，`didOpen` 用它跑一次分析。
_STATE = {"root": None, "cache": None}


def _uri_to_path(uri):
    """`file:///E:/a/b.m` -> `E:/a/b.m`（Windows 上要吃掉多余的斜杠）。"""
    p = urlparse(uri)
    path = unquote(p.path or "")
    if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
        path = path[1:]
    return path


def _diagnostics_for(uri):
    """从 `analyzer.api.analyze` 的 `model.doc_todos` 派生诊断。

    当前只有一类：`m_missing_doc`（函数缺头部描述）。它**正是** `--json` 的
    `heuristics` 那一类（`render_json` 里现算的就是 `doc_todos` 里的 missing），
    所以「LSP 诊断 == `--json` 的 heuristics」这条判据在**这一类上**成立。

    ⚠ 范围如实：`uninitialized` / `shape_mismatch` / `dead_code` 等**未并入**
    `--json` 的 `heuristics` 通道（`matlabc.py:14279` 的注释明说），所以这里也
    不发 —— 否则 LSP 与 CLI 的口径会分叉。
    """
    root = _STATE.get("root")
    if not root or not os.path.isdir(root):
        return []
    try:
        import analyzer.api as A
        if _STATE["cache"] is None:
            _STATE["cache"] = A.analyze(root)
        result = _STATE["cache"]
    except Exception as exc:                   # 分析失败：发一条提示，别静默
        _log("analyze 失败：%s" % exc)
        return []

    want = os.path.basename(_uri_to_path(uri)).lower()
    todos = (getattr(getattr(result, "model", None), "doc_todos", None) or {}
             ).get("todos") or []
    out = []
    for t in todos:
        if "description" not in (t.get("missing") or []):
            continue
        rel = (t.get("rel") or "").replace("\\", "/")
        if os.path.basename(rel).lower() != want:
            continue
        line0 = max(0, int(t.get("line") or 1) - 1)
        out.append({
            "range": {"start": {"line": line0, "character": 0},
                      "end": {"line": line0, "character": 1}},
            "severity": 3,                      # info：缺文档是提示，不是缺陷
            "code": "m_missing_doc",
            "source": "matlabc",
            "message": "函数缺少头部描述（description）",
        })
    return out


def _read_message(stream):
    """读一帧；EOF 返回 None。"""
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


def _log(msg):
    sys.stderr.write("[matlabc-lsp] %s\n" % msg)
    sys.stderr.flush()


def _word_at(text, line0, char):
    """取 `line0` 行、`char` 所在位置的最长标识符（[A-Za-z0-9_]）。

    返回 `(word, start, end)` 或 None。中文注释里的字不会匹配到函数名，
    所以「在注释上请求定义」自然退化为 `[]`。
    """
    lines = text.splitlines()
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
    return word, start, end


def _definition(uri, pos):
    """光标处标识符 → 它的定义位置。

    查找顺序：**同文件优先**，其次全局唯一命中。找不到返回 None。

    只读 `_STATE["cache"]`（`didOpen` 时算一次），**不再触发分析** ——
    否则每次跳转都要跑一遍全量，IDE 里不可用。
    """
    cache = _STATE.get("cache")
    if cache is None:
        return None
    path = _uri_to_path(uri)
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except (IOError, OSError):
        return None
    got = _word_at(text, int(pos.get("line", 0)), int(pos.get("character", 0)))
    if not got:
        return None
    name = got[0]

    hits = []
    for mf in (getattr(cache, "files", None) or []):
        for f in (getattr(mf, "functions", None) or []):
            if getattr(f, "name", None) == name:
                hits.append((mf.rel, f))
    if not hits:
        return None

    want = os.path.basename(path).lower()
    same = [h for h in hits if os.path.basename(h[0]).lower() == want]
    rel, fn = (same or hits)[0]
    line0 = max(0, int(getattr(fn, "line", 1) or 1) - 1)
    root = _STATE.get("root") or ""
    target = os.path.join(root, rel.replace("/", os.sep)) if root else rel
    return {
        "uri": "file:///" + target.replace("\\", "/").lstrip("/"),
        "range": {"start": {"line": line0, "character": 0},
                  "end": {"line": line0, "character": len(name)}},
    }


def handle(msg, out):
    """处理一帧。返回 False 表示退出循环。"""
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
        _STATE["cache"] = None
        _write_message(out, {
            "jsonrpc": "2.0", "id": mid,
            "result": {
                "capabilities": {"textDocumentSync": 1},
                "serverInfo": {"name": "matlabc-lsp", "version": VERSION},
            },
        })
        _log("initialize -> textDocumentSync=1, root=%r" % (_STATE["root"],))
        return True

    if method == "shutdown":
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": None})
        return True

    if method == "exit":
        _log("exit")
        return False

    if method == "textDocument/didOpen":
        uri = ((msg.get("params") or {}).get("textDocument") or {}).get("uri", "")
        diags = _diagnostics_for(uri)
        _write_message(out, {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": uri, "diagnostics": diags},
        })
        _log("didOpen %s -> %d 条诊断（m_missing_doc）" % (uri, len(diags)))
        return True

    if method == "textDocument/definition":
        params = msg.get("params") or {}
        uri = (params.get("textDocument") or {}).get("uri", "")
        pos = params.get("position") or {}
        loc = _definition(uri, pos)
        _write_message(out, {"jsonrpc": "2.0", "id": mid,
                             "result": [loc] if loc else []})
        _log("definition %s:%s -> %s" % (os.path.basename(_uri_to_path(uri)),
                                         pos.get("line"),
                                         "found" if loc else "none"))
        return True

    if method == "textDocument/didClose":
        return True

    if mid is not None:
        # 未实现的请求：回 null，不假装成功也不崩
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": None})
    return True


def main():
    _log("start v%s" % VERSION)
    inp = sys.stdin.buffer
    out = sys.stdout.buffer
    while True:
        msg = _read_message(inp)
        if msg is None:
            break
        try:
            if not handle(msg, out):
                break
        except Exception as exc:               # 单帧出错不能让整个服务挂掉
            _log("handle error: %s" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
