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
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
MATLABC = os.path.join(HERE, "matlabc.py")

#: `--json` 的 `level` -> LSP severity（1=Error 2=Warning 3=Information 4=Hint）
SEVERITY = {"error": 1, "warning": 2, "note": 3, "info": 3, "hint": 4}

_STATE = {"root": None, "payload": None, "lock": threading.Lock()}


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
def _run_json(root):
    """跑 `matlabc.py <root> --json <tmp>`，返回 payload 或 None。

    时间预算 120s：LSP 的 first-open 可以慢，**但必须有上界**。
    """
    if not os.path.isfile(MATLABC):
        _log("找不到 matlabc.py：%s" % MATLABC)
        return None
    fd, tmp = tempfile.mkstemp(suffix=".json", prefix="lsp-")
    os.close(fd)
    try:
        proc = subprocess.run(
            [sys.executable, MATLABC, root, "--json", tmp,
             "--sarif-no-persist"],
            cwd=HERE, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=120,
        )
        if proc.returncode != 0:
            _log("matlabc.py rc=%d：%s"
                 % (proc.returncode,
                    (proc.stderr or b"").decode("utf-8", "replace")[:200]))
            return None
        with io.open(tmp, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except subprocess.TimeoutExpired:
        _log("matlabc.py 超时（120s）")
        return None
    except (IOError, OSError, ValueError) as exc:
        _log("分析失败：%s" % exc)
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


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
                "capabilities": {"textDocumentSync": 1},
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
