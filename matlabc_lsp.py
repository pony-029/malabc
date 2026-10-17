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
import json
import sys

VERSION = "0.1.0"


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


def handle(msg, out):
    """处理一帧。返回 False 表示退出循环。"""
    method = msg.get("method")
    mid = msg.get("id")

    if method == "initialize":
        _write_message(out, {
            "jsonrpc": "2.0", "id": mid,
            "result": {
                "capabilities": {"textDocumentSync": 1},
                "serverInfo": {"name": "matlabc-lsp", "version": VERSION},
            },
        })
        _log("initialize -> textDocumentSync=1")
        return True

    if method == "shutdown":
        _write_message(out, {"jsonrpc": "2.0", "id": mid, "result": None})
        return True

    if method == "exit":
        _log("exit")
        return False

    if method == "textDocument/didOpen":
        uri = ((msg.get("params") or {}).get("textDocument") or {}).get("uri", "")
        # 先回包（不阻塞协议循环）；真正的分析随后异步做
        _write_message(out, {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": uri, "diagnostics": []},
        })
        _log("didOpen %s（诊断暂为空：PipelineResult 上没有 heuristics，待 facts 层）"
             % uri)
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
