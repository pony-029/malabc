#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""matlabc MCP server（纯标准库实现，零第三方依赖）。

让任意支持 Model Context Protocol (MCP) 的 AI Agent（CodeBuddy / Cursor /
Claude 等）把 matlabc 当作「代码理解 + 静态检查 + 确定性补丁」工具即插即用。

协议：MCP over stdio，使用 LSP 风格的分包帧（Content-Length + body），
与官方 MCP SDK 兼容。传输层用 subprocess 复用 matlabc 现有 CLI，保证
行为一致与进程隔离（Agent 调用不会污染 matlabc 自身进程状态）。

启动方式（交给 Agent 的 MCP client 自动拉起）：
    python matlabc_mcp.py
"""
from __future__ import absolute_import, division, print_function

import atexit
import json
import os
import re
import subprocess
import sys

__version__ = "1.0.0"

# 所有拉起的子进程（matlabc CLI），用于退出/超时兜底，防止孤儿进程跑飞
_CHILDREN = []


def _kill_tree(proc):
    """杀掉子进程及其整棵进程树（Windows 用 taskkill /T，POSIX 用 killpg）。"""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    else:
        try:
            os.killpg(os.getpgid(proc.pid), 9)
        except Exception:
            proc.kill()


def _cleanup_children():
    for proc in _CHILDREN:
        if proc.poll() is None:
            _kill_tree(proc)


atexit.register(_cleanup_children)

# ---------------------------------------------------------------------------
# 版本探测：从 matlabc.py 精确提取 VERSION 字符串，避免把行内注释带进来
# ---------------------------------------------------------------------------
_VERSION_RE = re.compile(r'VERSION\s*=\s*["\']([^"\']+)["\']')


def _detect_matlabc_version():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "matlabc.py"), "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VERSION"):
                    match = _VERSION_RE.search(line)
                    if match:
                        return match.group(1)
    except Exception:
        pass
    return "unknown"


MATLABC_VERSION = _detect_matlabc_version()

# ---------------------------------------------------------------------------
# 工具清单（inputSchema 自描述，供 Agent 发现与调用）
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "matlabc_analyze",
        "description": (
            "对 MATLAB/C/Python/JavaScript 工程做静态分析与结构梳理，"
            "生成调用关系、风险热点、技术债等报告。返回报告摘要与落盘路径。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "待分析目录或文件"},
                "checks": {"type": "string", "description": "检查项，逗号分隔或 all，默认 all"},
                "output": {"type": "string", "description": "报告输出路径，默认 mcp_analysis.md"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "matlabc_check",
        "description": (
            "针对具体静态检查项（uninitialized/type_mismatch/dead_code/"
            "shape_mismatch/tainted_sink）做门禁式扫描，返回 JSON 结果或告警计数。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "待检查目录或文件"},
                "check": {"type": "string", "description": "检查项名称，默认 all"},
                "max_warnings": {"type": "integer", "description": "超过则门禁失败，默认 0"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "matlabc_ask",
        "description": (
            "用自然语言问答式理解代码：谁调用 X / X 调用谁 / 风险热点 / 解释 X。"
            "内部用 BM25 检索 + 意图识别组装上下文后交大模型。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "自然语言问题"},
                "dir": {"type": "string", "description": "代码根目录，默认 ."},
            },
            "required": ["question"],
        },
    },
    {
        "name": "matlabc_version",
        "description": "返回 matlabc 引擎版本与支持的默认能力清单，供 Agent 做能力协商。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "matlabc_gen_patch",
        "description": (
            "运行 AI 修复闭环（review->fix->apply->verify->report），"
            "生成确定性修复补丁；auto_apply=true 时应用并自证验证。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "待修复目录或文件"},
                "auto_apply": {"type": "boolean", "description": "是否应用补丁并自证，默认 false"},
            },
            "required": ["target"],
        },
    },
]


# ---------------------------------------------------------------------------
# 传输层：LSP 风格分包帧
# ---------------------------------------------------------------------------
def _read_message():
    """从 stdin 读取一条 MCP 消息（Content-Length framing）。返回 dict 或 None。"""
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        if b":" in line:
            key, _, val = line.partition(b":")
            headers[key.strip().lower()] = val.strip()
    try:
        length = int(headers.get(b"content-length", b"0"))
    except ValueError:
        length = 0
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        return None


def _write_message(obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(b"Content-Length: %d\r\n\r\n" % len(body))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


# ---------------------------------------------------------------------------
# 命令分发：subprocess 复用 matlabc CLI
# ---------------------------------------------------------------------------
def _run(argv, timeout=600):
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
    }
    if os.name != "nt":
        kwargs["start_new_session"] = True  # POSIX：便于 killpg 整树清理
    proc = subprocess.Popen([sys.executable] + argv, **kwargs)
    _CHILDREN.append(proc)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        out, _ = proc.communicate()
    return out.decode("utf-8", "replace")


def _tail(text, limit):
    if len(text) <= limit:
        return text
    return "...(truncated)...\n" + text[-limit:]


def _cmd_analyze(args):
    target = args.get("target")
    if not target:
        return "error: 'target' is required"
    checks = args.get("checks") or "all"
    out = args.get("output") or "mcp_analysis.md"
    out = os.path.basename(out)  # 安全护栏：输出锁定在当前目录，防止路径穿越
    cli = ["matlabc.py", target, "--checks", checks, "-o", out, "--reproducible"]
    return "report written to %s\n\n%s" % (out, _tail(_run(cli), 4000))


def _cmd_check(args):
    target = args.get("target")
    if not target:
        return "error: 'target' is required"
    check = args.get("check") or "all"
    try:
        maxw = int(args.get("max_warnings", 0))
    except (TypeError, ValueError):
        maxw = 0
    cli = ["matlabc.py", target, "--checks", check,
           "--max-warnings", str(maxw), "--json"]
    return _tail(_run(cli), 6000)


def _cmd_ask(args):
    question = args.get("question")
    if not question:
        return "error: 'question' is required"
    d = args.get("dir") or "."
    cli = ["matlabc_ask.py", question, "--dir", d]
    return _tail(_run(cli), 6000)


def _cmd_gen_patch(args):
    target = args.get("target")
    if not target:
        return "error: 'target' is required"
    auto = bool(args.get("auto_apply", False))
    cli = ["matlabc_flow.py", target]
    if auto:
        cli.append("--auto-apply")
    else:
        cli += ["--gen-apply-patch", "mcp_fix.patch"]
    return _tail(_run(cli), 6000)


def _cmd_version(args):
    return json.dumps({
        "matlabc_version": MATLABC_VERSION,
        "mcp_server_version": __version__,
        "tools": [t["name"] for t in TOOLS],
    }, ensure_ascii=False)


DISPATCH = {
    "matlabc_version": _cmd_version,
    "matlabc_analyze": _cmd_analyze,
    "matlabc_check": _cmd_check,
    "matlabc_ask": _cmd_ask,
    "matlabc_gen_patch": _cmd_gen_patch,
}


def _handle_call(msg, msg_id):
    params = msg.get("params", {}) or {}
    name = params.get("name")
    arguments = params.get("arguments", {}) or {}
    try:
        handler = DISPATCH.get(name)
        if handler is None:
            raise ValueError("unknown tool: %s" % name)
        text = handler(arguments)
        is_error = False
    except Exception as exc:  # noqa: BLE001 - 把任何异常转成工具错误返回给 Agent
        text = "error: %s" % exc
        is_error = True
    _write_message({
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {"content": [{"type": "text", "text": text}], "isError": is_error},
    })


def main():
    while True:
        msg = _read_message()
        if msg is None:
            break
        if not isinstance(msg, dict):
            continue
        method = msg.get("method")
        msg_id = msg.get("id")
        if method == "initialize":
            _write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "matlabc", "version": MATLABC_VERSION},
                },
            })
        elif method == "notifications/initialized":
            continue
        elif method == "ping":
            _write_message({"jsonrpc": "2.0", "id": msg_id, "result": {}})
        elif method == "tools/list":
            _write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS},
            })
        elif method == "tools/call":
            _handle_call(msg, msg_id)
        else:
            if msg_id is not None:
                _write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": "method not found: %s" % method},
                })


if __name__ == "__main__":
    main()
