#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""matlabc MCP server（纯标准库实现，零第三方依赖）。

一句话：让任何支持 Model Context Protocol 的 AI Agent（CodeBuddy / Codex /
Cursor / Claude 等）把 matlabc 当成「代码理解 + 静态检查 + 确定性补丁」工具，
即插即用，不用教它怎么敲命令行。

装上之后，Agent 拿到五个工具：

    matlabc_analyze     扫一个工程，产出结构化报告（函数 / 调用图 / 告警）
    matlabc_check       只跑静态检查，返回告警清单（可指定 checks）
    matlabc_ask         拿报告当事实底座做问答（谁调用 X / 哪里风险最高）
    matlabc_gen_patch   产出**确定性**修复补丁（未初始化 / 死代码 / 形状不匹配）
    matlabc_version     报版本，用于 Agent 自检握手是否成功

它是怎么接进 Agent 的：

    ┌──────────────┐   MCP over stdio（LSP 风格分包帧）   ┌──────────────────┐
    │  AI Agent    │  Content-Length: 123\\r\\n\\r\\n{json}   │ matlabc_mcp.py   │
    │ (MCP client) │◀────────────────────────────────────▶│  (本文件)        │
    └──────────────┘                                      └────────┬─────────┘
                                                                   │ 每次调用起一个
                                                                   │ 独立子进程
                                                                   ▼
                                                          ┌──────────────────┐
                                                          │ matlabc.py CLI   │
                                                          └──────────────────┘

设计取舍（为什么这么写）：
  * **传输层复用 CLI，不 import**：Agent 的调用因此与命令行行为逐字节一致，
    且进程隔离 —— Agent 中途崩溃、超时、被 kill，都不会污染 matlabc 自身状态。
  * **stdin 必须切断**：本进程的 stdin 上跑的是 JSON-RPC 协议流。拉起的子进程
    若继承 stdin，会**偷走协议字节**导致静默协议损坏。这不是洁癖，是正确性。
  * **子进程全部登记收尸**：`_CHILDREN` + `atexit` 兜底；退出或超时按进程树
    杀掉（Windows 用 taskkill /T，POSIX 用 killpg），不留孤儿。

怎么启动：交给 Agent 的 MCP client 自动拉起，通常你不需要手敲。若要手测：

    python matlabc_mcp.py

  它是长驻的 stdio 服务：**正确行为是一直等输入**（不是卡死）。按 Ctrl-C 退出；
  或从 stdin 送 EOF，它收到即退出 —— 所以 `python matlabc_mcp.py --help`
  既没有 usage 也不打印任何东西（这不是坏了，是它的设计）。

诚实边界：
  * 只实现 JSON-RPC 的 initialize / tools/list / tools/call 与若干通知；
    不是 MCP 全量实现（没有 resources / prompts / sampling）。
  * 依赖子进程跑 CLI，所以「单次调用 = 一次进程启动」。大工程请用
    matlabc_analyze 一次拿全量报告，而不是反复调用。

退出码：
    0  = 从 stdin 收到 EOF，正常收工退出（宿主关闭连接时的标准路径）
    1  = 未捕获异常（由解释器给出；本文件不捕获顶层异常）

  （工具调用本身的失败**不**体现在退出码上 —— 它按 JSON-RPC 协议以
    isError 的响应回给宿主，进程继续存活。这是 MCP 的约定。）
"""
from __future__ import absolute_import, division, print_function

import atexit
import io
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
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                stdin=subprocess.DEVNULL,      # R62-R31e：不许继承 MCP 宿主的 stdin
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            pass                               # 收尸路径不许再抛异常
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

# 脚本解析：MCP 宿主（Cursor / Claude / CodeBuddy…）以它自己的 CWD 拉起本
# 服务器，所以裸相对名 "matlabc.py" 只有在「巧好以仓库根为 CWD」时才找得到。
# 实测：把 cwd 设成任意目录后 `_run(["matlabc.py", ...])` 直接 rc=2。
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _script(name):
    """把 CLI 脚本解析为绝对路径（找不到时退回原名，行为不变）。"""
    p = os.path.join(_SCRIPT_DIR, name)
    return p if os.path.exists(p) else name

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
                "output": {"type": "string", "description": "非应用模式下补丁文件名（锁定 CWD），默认 mcp_fix.patch"},
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
        # R62-R31e（真缺陷）：本进程是 stdio JSON-RPC server，stdin 上跑的是
        # MCP 协议。旧实现不设 stdin ⇒ 子进程 matlabc.py 直接继承这条管道：
        # ① 子进程若读一次 stdin，就会**偷走**本该给 server 的协议字节
        #    （静默的协议损坏，比崩溃更难查）；
        # ② 该管道永不 EOF，任何读到它的子进程都会永久阻塞。
        # 实测同源证据：`matlabc_mcp.py --help` 在 stdin 继承时 >30s 不返回，
        # 切断后 0.5s 返回（探针 probe_r26b_pipe，含重跑对照）。
        "stdin": subprocess.DEVNULL,
    }
    if os.name != "nt":
        kwargs["start_new_session"] = True  # POSIX：便于 killpg 整树清理
    proc = subprocess.Popen([sys.executable] + argv, **kwargs)
    _CHILDREN.append(proc)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        # 收尸 drain 也必须带超时：Windows 上子进程若留下继承管道的孙进程，
        # 无超时的 communicate() 会永久阻塞，把这里变成新的挂死点。
        try:
            out, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            out = b""
    # D-P0-3：**同时**回传退出码。旧实现只回传 stdout，于是 CLI 的 argparse
    # 报错（rc=2）被当作成功结果返回给 Agent（isError=false）——「没有门」被
    # 伪装成「有门」。缺输入 / 失败必须能红。
    return (proc.returncode or 0), out.decode("utf-8", "replace")


def _is_cli_usage_error(text):
    """argparse 的失败签名（子进程 stderr 已并入 stdout）。"""
    t = text or ""
    return ("usage:" in t) and ("error:" in t)


def _run_ok(argv, what, timeout=600):
    """跑子进程；非零退出码 → RuntimeError（由 _handle_call 转成 isError=true）。"""
    rc, text = _run(argv, timeout=timeout)
    if rc != 0:
        raise RuntimeError("%s 失败（rc=%d）：%s" % (what, rc, _tail(text, 800)))
    return text


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
    cli = [_script("matlabc.py"), target, "--checks", checks,
           "-o", out, "--reproducible"]
    text = _run_ok(cli, "matlabc_analyze")
    return "report written to %s\n\n%s" % (out, _tail(text, 4000))


def _cmd_check(args):
    target = args.get("target")
    if not target:
        return "error: 'target' is required"
    check = args.get("check") or "all"
    try:
        maxw = int(args.get("max_warnings", 0))
    except (TypeError, ValueError):
        maxw = 0
    cli = [_script("matlabc.py"), target, "--checks", check,
           "--max-warnings", str(maxw), "--json"]
    rc, text = _run(cli)
    if rc != 0 and _is_cli_usage_error(text):
        # 参数被 CLI 拒绝 → 真错误（不是门禁失败），必须响亮
        raise RuntimeError("matlabc_check 参数被 CLI 拒绝（rc=%d）：%s"
                           % (rc, _tail(text, 600)))
    # 非零退出码在这里是**门禁结果**（告警超阈值），显式上报给 Agent 而非吞掉
    return "exit_code=%d\n%s" % (rc, _tail(text, 6000))


def _cmd_ask(args):
    question = args.get("question")
    if not question:
        return "error: 'question' is required"
    d = args.get("dir") or "."
    cli = [_script("matlabc_ask.py"), question, "--dir", d]
    return _tail(_run_ok(cli, "matlabc_ask"), 6000)


def _cmd_gen_patch(args):
    target = args.get("target")
    if not target:
        return "error: 'target' is required"
    auto = bool(args.get("auto_apply", False))
    if auto:
        return _tail(_run_ok([_script("matlabc_flow.py"), target,
                              "--auto-apply"], "matlabc_gen_patch"), 6000)
    # D-P0-3：旧实现在**非应用**分支给 matlabc_flow.py 传 `--gen-apply-patch`，
    # 而该脚本根本没有这个开关（只有 directory 位置参数 + --auto-apply 等），
    # argparse 报 rc=2 并打印 usage，而 _run 丢弃退出码 ⇒ 被当成成功回给 Agent。
    # 正确做法：非应用模式直接调确定性补丁引擎，并把**补丁内容**回传给 Agent。
    out = os.path.basename(args.get("output") or "mcp_fix.patch")  # 防路径穿越
    text = _run_ok([_script("matlabc.py"), target, "--gen-apply-patch",
                    out, "--ai-mode", "off"], "matlabc_gen_patch")
    patch_path = out + ".git.patch"
    if os.path.exists(patch_path):
        body = io.open(patch_path, "r", encoding="utf-8", errors="replace").read()
        return ("patch written to %s (%d bytes)\n\n%s"
                % (patch_path, len(body.encode("utf-8")), _tail(body, 6000)))
    return "no deterministic fix applicable\n\n" + _tail(text, 2000)


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
