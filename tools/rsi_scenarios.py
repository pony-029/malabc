# -*- coding: utf-8 -*-
"""全场景探针台（RSI 用）。

和 `lsp_selftest.py` 的分工
==========================

`lsp_selftest` 测的是**函数级契约**（`_field_refs` 返回什么）；
这里测的是**对外协议端到端**：起一个真的 LSP/MCP 进程，只通过
JSON-RPC 说话，看它对外表现。两者互补：

    lsp_selftest  ->  内部实现有没有退化
    rsi_scenarios ->  用户（含 Agent）看到的行为有没有退化

为什么叫 RSI：每一轮跑完，**上一轮的失败会被加成新的场景**，
所以场景集只会变严、不会变松（下界由 `MIN_SCENARIOS` 钉住）。

用法：
    python tools/rsi_scenarios.py            # 跑全部
    python tools/rsi_scenarios.py --only M   # 只跑名字含 M 的
    python tools/rsi_scenarios.py --list

退出码：
    0  = 全过
    1  = 有场景失败
    2  = 缺输入
"""
import argparse
import io
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LSP = os.path.join(ROOT, "matlabc_lsp.py")
MCP = os.path.join(ROOT, "matlabc_mcp.py")
CORPUS = os.path.join(ROOT, "tests", "sample_m")

#: 场景数下界。加场景是允许的，删场景必须同时改这个数（与 check_all 的
#: MIN_GUARDS 同一套纪律：删掉一条也会红）。
MIN_SCENARIOS = 93


def _uri(path):
    return "file:///" + path.replace("\\", "/").lstrip("/")


class Session(object):
    """一个 JSON-RPC 子进程会话。

    ⚠ 两个协议**传输层不同**（第 1 轮实测）：
        LSP  = `Content-Length: N\\r\\n\\r\\n<json>`（带帧头）
        MCP  = 一行一个 JSON（无帧头）
    按同一种发，另一边会**整场解析失败** —— 而且报错全在服务端 stderr 里，
    客户端只看到“没回应”。这就是第 1 轮 19 个 LSP 场景全红的原因。
    """

    def __init__(self, script, argv, cwd=None, framing=None):
        # 默认按**被测脚本**判断传输层：LSP 带帧头，MCP 是行分隔。
        # 让调用点不必每处都写一遍 —— 少写一处的后果是整场全红。
        self.framing = framing or ("lsp" if script.endswith("matlabc_lsp.py")
                                   else "line")
        # **必须走二进制管道**：文本模式下 `stdout.read(n)` 读的是 n 个
        # **字符**，而帧头里写的是**字节数** —— 内容含中文时两者不等，
        # 帧边界错位，JSON 解析全崩。第 3 轮 19 个 LSP 场景全红就是这个。
        self.p = subprocess.Popen([sys.executable, script] + list(argv),
                                  cwd=cwd or ROOT,
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
        # 看门狗：server 不回包时 readline 会永久挂住
        self.wd = threading.Timer(180.0, self.p.kill)
        self.wd.daemon = True
        self.wd.start()
        self.seq = 0
        self.q = queue.Queue()
        self.rt = threading.Thread(target=self._reader)
        self.rt.daemon = True
        self.rt.start()

    def send_raw(self, text):
        self.p.stdin.write((text + "\n").encode("utf-8"))
        self.p.stdin.flush()

    def _send(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        if self.framing == "lsp":
            self.p.stdin.write(b"Content-Length: " + str(len(body)).encode()
                               + b"\r\n\r\n" + body)
        else:
            self.p.stdin.write(body + b"\n")
        self.p.stdin.flush()

    def _read_one(self):
        if self.framing != "lsp":
            ln = self.p.stdout.readline()
            if not ln:
                return None
            ln = ln.strip()
            return json.loads(ln.decode("utf-8")) if ln else None
        # 帧头可能有多个（Content-Type 等），空行是分界
        length = 0
        while True:
            ln = self.p.stdout.readline()
            if not ln:
                return None
            ln = ln.rstrip(b"\r\n")
            if not ln:
                break
            low = ln.lower()
            if low.startswith(b"content-length:"):
                length = int(ln.split(b":", 1)[1].strip())
        if length <= 0:
            return None
        buf = b""
        while len(buf) < length:
            chunk = self.p.stdout.read(length - len(buf))
            if not chunk:
                return None
            buf += chunk
        return json.loads(buf.decode("utf-8"))

    def _reader(self):
        """后台读线程：把消息塞进队列。

        **没有它就没法加超时**（`readline` 是阻塞的）：initialize 之前的
        请求服务端可能根本不回，主线程会永久挂住 —— 第 2 轮实测挂住了，
        只能靠 180s 看门狗收尸，一个场景就吃掉三分钟。
        """
        while True:
            try:
                msg = self._read_one()
            except Exception:
                self.q.put(None)
                return
            if msg is None:
                self.q.put(None)
                return
            self.q.put(msg)

    def notify(self, method, params=None):
        """发通知：**没有 id，也没有回应**。

        LSP 的 didOpen / didChange / didSave 都是通知。当请求发会
        干等到超时 —— 第 4 轮「增量 didChange」就是这么红的。
        """
        self._send({"jsonrpc": "2.0", "method": method,
                    "params": params or {}})

    def rpc(self, method, params=None, timeout=15.0):
        self.seq += 1
        self._send({"jsonrpc": "2.0", "id": self.seq, "method": method,
                    "params": params or {}})
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = self.q.get(timeout=max(0.1, deadline - time.time()))
            except Exception:
                raise IOError("等 id=%d 超时（%.0fs）" % (self.seq, timeout))
            if msg is None:
                raise IOError("server 关闭了 stdout")
            if msg.get("id") == self.seq:
                return msg
            # 通知（diagnostics 等）直接丢掉
        raise IOError("等 id=%d 超时（%.0fs）" % (self.seq, timeout))

    def close(self):
        try:
            self.wd.cancel()
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except Exception:
            try:
                self.p.kill()
            except Exception:
                pass


def _mk(files):
    """建一个临时工程：files = {name: (text, encoding, newline)}"""
    d = tempfile.mkdtemp(prefix="rsi_")
    for name, spec in files.items():
        path = os.path.join(d, name)
        text, enc, nl = spec
        mode = "wb" if isinstance(text, bytes) else "w"
        if mode == "wb":
            with io.open(path, "wb") as fh:
                fh.write(text)
        else:
            with io.open(path, "w", encoding=enc, newline=nl) as fh:
                fh.write(text)
    return d


# ---------------------------------------------------------------------------
# 场景定义：每个函数返回 (ok: bool, detail: str)
# 都通过**公开协议**取数，不 import 产品内部函数。
# ---------------------------------------------------------------------------

GOOD_DOT_M = (u"function y = good(x)\n"
              u"y = x + 1;\n"
              u"end\n")
CALLER_M = (u"function r = caller(a)\n"
            u"r = good(a);\n"
            u"end\n")


def _lsp_fixture():
    """一份包含调用关系的小工程，供 LSP 场景共用。"""
    return _mk({
        "good.m": (GOOD_DOT_M, "utf-8", ""),
        "caller.m": (CALLER_M, "utf-8", ""),
    })


def sc_lsp_initialize(sess, ctx):
    r = sess.rpc("initialize", {"rootUri": _uri(ctx["root"]),
                                "capabilities": {}})
    caps = (r.get("result") or {}).get("capabilities") or {}
    return bool(caps), "capabilities=%d 项" % len(caps)


def sc_lsp_symbols(sess, ctx):
    r = sess.rpc("textDocument/documentSymbol",
                 {"textDocument": {"uri": _uri(os.path.join(ctx["root"],
                                                            "good.m"))}})
    syms = r.get("result") or []
    return any(s.get("name") == "good" for s in syms), "符号=%r" % (
        [s.get("name") for s in syms][:5],)


def sc_lsp_definition(sess, ctx):
    # 第 2 行（0-based 1）第 4 列指向 good 调用
    r = sess.rpc("textDocument/definition",
                 {"textDocument": {"uri": _uri(os.path.join(ctx["root"],
                                                            "caller.m"))},
                  "position": {"line": 1, "character": 5}})
    res = r.get("result")
    ok = bool(res) and ("good.m" in json.dumps(res))
    return ok, "result=%s" % (json.dumps(res)[:90],)


def sc_lsp_references(sess, ctx):
    r = sess.rpc("textDocument/references",
                 {"textDocument": {"uri": _uri(os.path.join(ctx["root"],
                                                            "good.m"))},
                  "position": {"line": 0, "character": 10},
                  "context": {"includeDeclaration": True}})
    res = r.get("result") or []
    return len(res) >= 1, "引用=%d" % len(res)


def sc_lsp_hover(sess, ctx):
    r = sess.rpc("textDocument/hover",
                 {"textDocument": {"uri": _uri(os.path.join(ctx["root"],
                                                            "caller.m"))},
                  "position": {"line": 1, "character": 5}})
    res = r.get("result") or {}
    txt = json.dumps(res, ensure_ascii=False)
    return len(txt) > 20, "hover=%s" % (txt[:80],)


def sc_lsp_codelens(sess, ctx):
    r = sess.rpc("textDocument/codeLens",
                 {"textDocument": {"uri": _uri(os.path.join(ctx["root"],
                                                            "good.m"))}})
    res = r.get("result")
    return res is not None, "lens=%s" % (json.dumps(res)[:70],)


def sc_lsp_unknown_method(sess, ctx):
    r = sess.rpc("textDocument/doesNotExist", {})
    # 只要求：不崩、有回应
    return ("result" in r or "error" in r), "resp keys=%r" % (list(r.keys()),)


def sc_lsp_before_init(ctx):
    """未 initialize 就发请求：**允许不回应**，但不能因此崩掉。

    断言落在「之后 initialize 还能成功」—— 这才是「没崩」的可观测形式。
    要求它必须回应，是把协议细节当成产品缺陷（第 2 轮我差点这么判）。
    """
    s = Session(LSP, ["--root", ctx["root"]])
    try:
        try:
            s.rpc("textDocument/documentSymbol",
                  {"textDocument": {"uri": _uri(os.path.join(ctx["root"],
                                                             "good.m"))}},
                  timeout=3)
        except IOError:
            pass                      # 不回应是允许的
        r = s.rpc("initialize", {"rootUri": _uri(ctx["root"]),
                                 "capabilities": {}})
        caps = (r.get("result") or {}).get("capabilities") or {}
        return bool(caps), "initialize 之后仍可用（%d 项能力）" % len(caps)
    finally:
        s.close()


def sc_lsp_malformed_json(ctx):
    """发一行坏 JSON 后，后续请求仍需可用。"""
    s = Session(LSP, ["--root", ctx["root"]])
    try:
        s.rpc("initialize", {"rootUri": _uri(ctx["root"]),
                             "capabilities": {}})
        s.send_raw("{not json at all")
        r = s.rpc("textDocument/documentSymbol",
                  {"textDocument": {"uri": _uri(os.path.join(ctx["root"],
                                                             "good.m"))}})
        return isinstance(r.get("result"), list), "坏行之后仍响应"
    finally:
        s.close()


def _one_shot_lsp(root, method, params):
    s = Session(LSP, ["--root", root], framing="lsp")
    try:
        s.rpc("initialize", {"rootUri": _uri(root), "capabilities": {}})
        return s.rpc(method, params)
    finally:
        s.close()


def sc_empty_project(ctx):
    d = _mk({})
    try:
        r = _one_shot_lsp(d, "textDocument/documentSymbol",
                          {"textDocument": {"uri": _uri(os.path.join(d, "x.m"))}})
        return r is not None, "空工程仍响应（%r）" % (list(r.keys()),)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_non_utf8(ctx):
    d = _mk({"bad.m": (b"function y = bad(x)\n% \xff\xfe binary\n"
                       b"y = x;\nend\n", "utf-8", "")})
    try:
        r = _one_shot_lsp(d, "textDocument/documentSymbol",
                          {"textDocument": {"uri": _uri(os.path.join(d, "bad.m"))}})
        syms = r.get("result") or []
        return any(s.get("name") == "bad" for s in syms), "符号=%r" % (
            [s.get("name") for s in syms][:4],)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_bom(ctx):
    d = _mk({"bom.m": (u"\ufefffunction y = bomfn(x)\ny = x;\nend\n",
                       "utf-8", "")})
    try:
        r = _one_shot_lsp(d, "textDocument/documentSymbol",
                          {"textDocument": {"uri": _uri(os.path.join(d, "bom.m"))}})
        syms = r.get("result") or []
        return any("bomfn" in (s.get("name") or "") for s in syms), \
            "符号=%r" % ([s.get("name") for s in syms][:4],)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_syntax_error(ctx):
    d = _mk({"half.m": (u"function y = half(x)\nif x > 1\n y = 1;\nend\n",
                        "utf-8", "")})
    try:
        r = _one_shot_lsp(d, "textDocument/documentSymbol",
                          {"textDocument": {"uri": _uri(os.path.join(d, "half.m"))}})
        return isinstance(r.get("result"), list), "语法不完整仍返回列表"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_classdef(ctx):
    d = _mk({"C.m": (u"classdef C\n"
                     u"    methods\n"
                     u"        function y = m(obj, x)\n"
                     u"            y = x;\n"
                     u"        end\n"
                     u"    end\n"
                     u"end\n", "utf-8", "")})
    try:
        r = _one_shot_lsp(d, "textDocument/documentSymbol",
                          {"textDocument": {"uri": _uri(os.path.join(d, "C.m"))}})
        syms = r.get("result") or []
        names = [s.get("name") for s in syms]
        return bool(names), "classdef 符号=%r" % (names[:5],)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_crlf_lines(ctx):
    d = _mk({"crlf.m": (u"function y = crlf(x)\r\ny = x;\r\nend\r\n",
                        "utf-8", "")})
    try:
        r = _one_shot_lsp(d, "textDocument/documentSymbol",
                          {"textDocument": {"uri": _uri(os.path.join(d, "crlf.m"))}})
        syms = r.get("result") or []
        line = (syms[0].get("range") or {}).get("start", {}).get("line") if syms else -1
        return line == 0, "CRLF 首行 line=%r" % (line,)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_unicode_ident(ctx):
    d = _mk({"uni.m": (u"function y = uni(x)\n"
                       u"变量 = x + 1;\n"
                       u"y = 变量;\n"
                       u"end\n", "utf-8", "")})
    try:
        r = _one_shot_lsp(d, "textDocument/documentSymbol",
                          {"textDocument": {"uri": _uri(os.path.join(d, "uni.m"))}})
        return isinstance(r.get("result"), list), "中文标识符不崩"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_long_line(ctx):
    d = _mk({"long.m": (u"function y = longfn(x)\n" + u"y = x" +
                        u" + x" * 4000 + u";\nend\n", "utf-8", "")})
    try:
        t0 = time.time()
        r = _one_shot_lsp(d, "textDocument/documentSymbol",
                          {"textDocument": {"uri": _uri(os.path.join(d, "long.m"))}})
        dt = time.time() - t0
        ok = isinstance(r.get("result"), list) and dt < 15
        return ok, "超长行 %.1fs" % dt
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_nested_functions(ctx):
    d = _mk({"nest.m": (u"function outer()\n"
                        u"    inner(1);\n"
                        u"    function inner(v)\n"
                        u"        disp(v);\n"
                        u"    end\n"
                        u"end\n", "utf-8", "")})
    try:
        r = _one_shot_lsp(d, "textDocument/documentSymbol",
                          {"textDocument": {"uri": _uri(os.path.join(d, "nest.m"))}})
        names = [s.get("name") for s in (r.get("result") or [])]
        return "outer" in names, "嵌套函数符号=%r" % (names[:5],)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_lsp_shutdown(ctx):
    s = Session(LSP, ["--root", ctx["root"]])
    try:
        s.rpc("initialize", {"rootUri": _uri(ctx["root"]), "capabilities": {}})
        r = s.rpc("shutdown", {})
        return "result" in r or "error" in r, "shutdown 有回应"
    finally:
        s.close()


# ---- MCP ---------------------------------------------------------------

def _mcp(root):
    return Session(MCP, ["--root", root])


def _call(sess, name, args):
    """返回 (result, err)。err 为 None 表示成功。

    ⚠ 工具级失败走的是 `result.isError`（MCP 约定），**不是** JSON-RPC error。
    第 1 轮我按 JSON-RPC error 判，于是“整批拒绝”看起来像失败。
    """
    r = sess.rpc("tools/call", {"name": name, "arguments": args})
    res = r.get("result") or {}
    err = r.get("error")
    if err is None and res.get("isError"):
        err = {"code": "isError"}
    return res, err


def _text(res):
    try:
        return (res.get("content") or [{}])[0].get("text", "")
    except Exception:
        return ""


def sc_mcp_initialize(sess, ctx):
    r = sess.rpc("initialize", {"protocolVersion": "2024-11-05",
                                "capabilities": {}})
    info = (r.get("result") or {}).get("serverInfo") or {}
    return bool(info.get("name")), "serverInfo=%r" % (info,)


def sc_mcp_list(sess, ctx):
    r = sess.rpc("tools/list", {})
    tools = (r.get("result") or {}).get("tools") or []
    # 下界跟着实际情况走（R376）：19 → 21（新增 task_plan / task_apply）。
    # 用 `>=` 而不是 `==`：加工具不该让这条红，但**少**工具必须有人知道。
    return len(tools) >= 23, "工具=%d" % len(tools)


def sc_mcp_stats(sess, ctx):
    res, err = _call(sess, "matlabc_stats", {})
    t = _text(res)
    return (not err) and ("文件" in t or "函数" in t), t[:60].replace("\n", " ")


def sc_mcp_outline(sess, ctx):
    res, err = _call(sess, "matlabc_outline", {"path": "good.m"})
    t = _text(res)
    return (not err) and "good" in t, t[:50].replace("\n", " ")


def sc_mcp_heat(sess, ctx):
    res, err = _call(sess, "matlabc_heat", {"limit": 5})
    t = _text(res)
    return (not err) and len(t) > 10, t[:50].replace("\n", " ")


def sc_mcp_search(sess, ctx):
    res, err = _call(sess, "matlabc_search", {"pattern": "goo"})
    t = _text(res)
    return (not err) and "good" in t, t[:50].replace("\n", " ")


def sc_mcp_unknown_tool(sess, ctx):
    r = sess.rpc("tools/call", {"name": "no_such_tool", "arguments": {}})
    return "error" in r, "error=%r" % ((r.get("error") or {}).get("code"),)


def sc_mcp_bad_args(sess, ctx):
    r = sess.rpc("tools/call", {"name": "matlabc_impact", "arguments": {}})
    err = r.get("error")
    txt = _text(r.get("result") or {})
    ok = bool(err) or ("不是本工程" in txt) or ("不能为空" in txt)
    return ok, "err=%r txt=%r" % ((err or {}).get("code"), txt[:40])


def sc_mcp_outside_root(sess, ctx):
    res, err = _call(sess, "matlabc_outline", {"path": "../../etc/passwd"})
    txt = _text(res)
    ok = bool(err) or ("不在工程" in txt) or ("找不到" in txt)
    return ok, "err=%r txt=%r" % ((err or {}).get("code"), txt[:40])


def sc_mcp_help(sess, ctx):
    res, err = _call(sess, "matlabc_help", {})
    t = _text(res)
    return (not err) and ("matlabc_" in t), t[:50].replace("\n", " ")


def sc_mcp_impact_lists(sess, ctx):
    res, err = _call(sess, "matlabc_impact", {"name": "good"})
    t = _text(res)
    return (not err) and ("影响面" in t), t[:60].replace("\n", " ")


# ---- 批量写（事务） ---------------------------------------------------

def _write_mcp_scenarios(ctx):
    """写操作场景单独用一个工程，避免污染只读场景。"""
    d = _mk({"wa.m": (u"function wa()\nv = 1;\nend\n", "utf-8", ""),
            "wb.m": (u"function wb()\nw = 2;\nend\n", "utf-8", "")})
    s = _mcp(d)
    try:
        s.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        res, err = _call(s, "matlabc_propose_edits", {"edits": [
            {"path": "wa.m", "oldText": "v = 1;", "newText": "v = 9;"},
            {"path": "wb.m", "oldText": "w = 2;", "newText": "w = 8;"},
        ]})
        t = _text(res)
        import re
        m = re.search(r"batchId=`([0-9a-f]+)`", t)
        bid = m.group(1) if m else ""
        before = io.open(os.path.join(d, "wa.m"), encoding="utf-8").read()
        yield ("MCP propose_edits 不写盘", bool(bid) and "v = 1;" in before,
               "batch=%r" % (bid,))
        if not bid:
            return
        _call(s, "matlabc_apply_edits", {"batchId": bid})
        after = io.open(os.path.join(d, "wa.m"), encoding="utf-8").read()
        yield ("MCP apply_edits 全写", "v = 9;" in after, after.strip()[:40])
        _call(s, "matlabc_undo_edits", {"batchId": bid})
        undo = io.open(os.path.join(d, "wa.m"), encoding="utf-8").read()
        yield ("MCP undo_edits 全恢复", "v = 1;" in undo, undo.strip()[:40])
        bad, berr = _call(s, "matlabc_propose_edits", {"edits": [
            {"path": "wa.m", "oldText": "v = 1;", "newText": "v = 7;"},
            {"path": "wb.m", "oldText": "zzz", "newText": "q"},
        ]})
        still = io.open(os.path.join(d, "wa.m"), encoding="utf-8").read()
        yield ("MCP 一条不合格整批拒绝", bool(berr) and "v = 1;" in still,
               "err=%r" % ((berr or {}).get("code"),))
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


# ---- 第 3 轮新增：把「上一轮失败/空洞」补成场景 -----------------------

def _clang_fixture():
    """一个带 C 源的工程：用于 cbridge 正/反向与 changed/explain。"""
    return _mk({
        "cm.m": (u"function y = cm(x)\n"
                 u"y = c_entry(x);\n"
                 u"end\n", "utf-8", ""),
        "impl.c": (u"int c_entry(int x)\n"
                   u"{\n"
                   u"    return x;\n"
                   u"}\n", "utf-8", ""),
    })


def sc_mcp_fields(sess, ctx):
    res, err = _call(sess, "matlabc_fields", {"path": "good.m"})
    t = _text(res)
    return (not err) and len(t) > 5, t[:50].replace("\n", " ")


def sc_mcp_diagnostics(sess, ctx):
    res, err = _call(sess, "matlabc_diagnostics", {})
    t = _text(res)
    return (not err) and len(t) > 5, t[:50].replace("\n", " ")


def sc_mcp_diag_cache(sess, ctx):
    """第二次调用必须命中缓存（同一会话内直接返回）。"""
    _call(sess, "matlabc_diagnostics", {})
    t0 = time.time()
    res, err = _call(sess, "matlabc_diagnostics", {})
    dt = time.time() - t0
    return (not err) and dt < 3.0, "第二次 %.2fs" % dt


def sc_mcp_stats_empty(ctx):
    d = _mk({})
    s = _mcp(d)
    try:
        s.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        res, err = _call(s, "matlabc_stats", {})
        t = _text(res)
        return (not err) and ("0" in t), t[:40].replace("\n", " ")
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_lsp_didchange(ctx):
    """改一行并**保存**后，documentSymbol 应反映新内容。

    为什么必须带 didSave：本扩展的约定是「保存即刷新」（增量重算）。
    只发 didChange 就断言，等于要求它逐键重算 —— 那是**另一个产品设计**，
    第 5 轮我差点把这个当成缺陷报出去。

    保存后是**异步重算**，所以要轮询；直接查一次会把「还没算完」判成「算错」。
    """
    d = _mk({"e.m": (u"function y = e(x)\ny = x;\nend\n", "utf-8", "")})
    s = Session(LSP, ["--root", d])
    try:
        s.rpc("initialize", {"rootUri": _uri(d), "capabilities": {}})
        uri = _uri(os.path.join(d, "e.m"))
        s.notify("textDocument/didOpen", {"textDocument": {
            "uri": uri, "languageId": "matlab", "version": 1,
            "text": u"function y = e(x)\ny = x;\nend\n"}})
        s.notify("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": 2},
            "contentChanges": [{"text": u"function y = e2(x)\ny = x;\nend\n"}]})
        # ⚠ **保存 = 写盘 + 通知**。只发 didSave 不写盘，服务端重算的是旧文件，
        # 于是「没更新」—— 第 6 轮我差点把这个报成产品缺陷。
        with io.open(os.path.join(d, "e.m"), "w", encoding="utf-8",
                     newline="") as fh:
            fh.write(u"function y = e2(x)\ny = x;\nend\n")
        s.notify("textDocument/didSave", {"textDocument": {"uri": uri},
                                          "text": u"function y = e2(x)\ny = x;\nend\n"})
        t0 = time.time()
        names = []
        while time.time() - t0 < 12:
            r = s.rpc("textDocument/documentSymbol",
                      {"textDocument": {"uri": uri}}, timeout=10)
            names = [x.get("name") for x in (r.get("result") or [])]
            if any("e2" in (n or "") for n in names):
                return True, "保存后 %.1fs 更新为 %r" % (time.time() - t0, names[:3])
            time.sleep(0.4)
        return False, "保存 12s 后仍是 %r（未重算）" % (names[:3],)
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_lsp_many_files(ctx):
    """50 个文件的工程：符号查询仍要快（<12s）。"""
    files = {}
    for i in range(50):
        files["f%02d.m" % i] = (u"function y = f%02d(x)\ny = x;\nend\n" % i,
                                "utf-8", "")
    d = _mk(files)
    s = Session(LSP, ["--root", d])
    try:
        t0 = time.time()
        s.rpc("initialize", {"rootUri": _uri(d), "capabilities": {}},
              timeout=60)
        r = s.rpc("textDocument/documentSymbol",
                  {"textDocument": {"uri": _uri(os.path.join(d, "f07.m"))}},
                  timeout=60)
        dt = time.time() - t0
        names = [x.get("name") for x in (r.get("result") or [])]
        return (dt < 12) and any("f07" in (n or "") for n in names), \
            "50 文件 %.1fs 符号=%r" % (dt, names[:2])
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def _mcp_with(files, fn):
    d = _mk(files)
    s = _mcp(d)
    try:
        s.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        return fn(s, d)
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_mcp_cbridge_forward(ctx):
    def run(s, d):
        res, err = _call(s, "matlabc_cbridge", {"name": "cm"})
        t = _text(res)
        return (not err) and ("impl.c" in t or "C" in t), t[:60].replace("\n", " ")
    return _mcp_with(_clang_files(), run)


def sc_mcp_cbridge_reverse(ctx):
    def run(s, d):
        res, err = _call(s, "matlabc_cbridge", {"name": "c_entry"})
        t = _text(res)
        return (not err) and ("cm" in t or "MATLAB" in t), t[:60].replace("\n", " ")
    return _mcp_with(_clang_files(), run)


def sc_mcp_definition(s, ctx):
    """`matlabc_definition`：位置 -> 定义。此前**完全没有测试**。

    `audit_coverage.py` 数真实调用点才发现 —— 之前用子串搜"工具名在不在
    测试文件里"，19/19 全绿，那是假数。
    """
    res, err = _call(s, "matlabc_definition",
                     {"path": "caller.m", "line": 1, "character": 5})
    t = _text(res)
    return (not err) and ("good" in t), t[:60].replace("\n", " ")


def sc_mcp_references(s, ctx):
    """`matlabc_references`：谁引用了它。同样此前没有测试。"""
    res, err = _call(s, "matlabc_references",
                     {"path": "good.m", "line": 0, "character": 10})
    t = _text(res)
    return (not err) and len(t) > 5, t[:60].replace("\n", " ")


def sc_mcp_changed(s, ctx):
    res, err = _call(s, "matlabc_changed", {"files": ["good.m"]})
    t = _text(res)
    return (not err) and ("变更影响面" in t), t[:50].replace("\n", " ")


def sc_mcp_explain(s, ctx):
    res, err = _call(s, "matlabc_explain", {"name": "good"})
    t = _text(res)
    return (not err) and len(t) > 20, t[:50].replace("\n", " ")


def _clang_files():
    return {
        "cm.m": (u"function y = cm(x)\n"
                 u"y = c_entry(x);\n"
                 u"end\n", "utf-8", ""),
        "impl.c": (u"int c_entry(int x)\n"
                   u"{\n"
                   u"    return x;\n"
                   u"}\n", "utf-8", ""),
    }



# ---- 第 8 轮：加压场景 ------------------------------------------------

def sc_recursive(ctx):
    """自递归函数：符号与影响面都不能转圈。"""
    d = _mk({"rec.m": (u"function y = rec(x)\n"
                      u"if x > 0\n y = rec(x - 1);\nelse\n y = 0;\nend\n"
                      u"end\n", "utf-8", "")})
    s = Session(LSP, ["--root", d])
    try:
        s.rpc("initialize", {"rootUri": _uri(d), "capabilities": {}})
        r = s.rpc("textDocument/documentSymbol",
                  {"textDocument": {"uri": _uri(os.path.join(d, "rec.m"))}},
                  timeout=15)
        names = [x.get("name") for x in (r.get("result") or [])]
        return any("rec" in (n or "") for n in names), "符号=%r" % (names[:3],)
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_unicode_path(ctx):
    """路径含中文与空格：不能因为编码/空格炸掉。"""
    d = tempfile.mkdtemp(prefix="rsi_")
    sub = os.path.join(d, u"中文 目录")
    os.makedirs(sub)
    p = os.path.join(sub, u"函数.m")
    with io.open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(u"function y = 函数(x)\ny = x;\nend\n")
    s = Session(LSP, ["--root", d])
    try:
        s.rpc("initialize", {"rootUri": _uri(d), "capabilities": {}})
        r = s.rpc("textDocument/documentSymbol",
                  {"textDocument": {"uri": _uri(p)}}, timeout=15)
        return isinstance(r.get("result"), list), "中文路径可查询"
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_corrupt_cache(ctx):
    """缓存文件写坏：必须当没有缓存，不能崩。"""
    d = _mk({"cc.m": (u"function y = cc(x)\ny = x;\nend\n", "utf-8", "")})
    os.makedirs(os.path.join(d, ".matlabc"))
    with io.open(os.path.join(d, ".matlabc", "payload.json"), "w",
                 encoding="utf-8", newline="") as fh:
        fh.write("{ this is not json")
    s = _mcp(d)
    try:
        s.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        res, err = _call(s, "matlabc_diagnostics", {})
        t = _text(res)
        return (not err) and len(t) > 5, "坏缓存下仍可体检"
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_bom_crlf(ctx):
    """BOM + CRLF 同时出现：符号与行号都要对。"""
    d = _mk({"bc.m": (u"\ufefffunction y = bc(x)\r\ny = x;\r\nend\r\n",
                      "utf-8", "")})
    s = Session(LSP, ["--root", d])
    try:
        s.rpc("initialize", {"rootUri": _uri(d), "capabilities": {}})
        r = s.rpc("textDocument/documentSymbol",
                  {"textDocument": {"uri": _uri(os.path.join(d, "bc.m"))}},
                  timeout=15)
        syms = r.get("result") or []
        line = (syms[0].get("range") or {}).get("start", {}).get("line") if syms else -1
        name = (syms[0].get("name") or "") if syms else ""
        return ("bc" in name) and line == 0, "name=%r line=%r" % (name, line)
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_mcp_before_init(ctx):
    """MCP 未 initialize 直接 tools/call：允许不回应，但不能崩。"""
    s = _mcp(ctx["root"])
    try:
        try:
            s.rpc("tools/call", {"name": "matlabc_stats", "arguments": {}},
                  timeout=3)
        except IOError:
            pass
        r = s.rpc("initialize", {"protocolVersion": "2024-11-05",
                                 "capabilities": {}})
        info = (r.get("result") or {}).get("serverInfo") or {}
        return bool(info.get("name")), "initialize 之后仍可用"
    finally:
        s.close()


def sc_big_project(ctx):
    """120 文件工程：stats 必须在 45s 内出结果。"""
    files = {}
    for i in range(120):
        files["b%03d.m" % i] = (u"function y = b%03d(x)\ny = x + 1;\nend\n" % i,
                                "utf-8", "")
    d = _mk(files)
    s = _mcp(d)
    try:
        t0 = time.time()
        s.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        res, err = _call(s, "matlabc_stats", {})
        dt = time.time() - t0
        t = _text(res)
        return (not err) and ("120" in t) and dt < 45, "120 文件 %.1fs" % dt
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_many_functions(ctx):
    """单文件 400 个函数：outline 不能超时。"""
    body = []
    for i in range(400):
        body.append(u"function y = mf%03d(x)\ny = x;\nend\n" % i)
    d = _mk({"many.m": (u"\n".join(body), "utf-8", "")})
    s = _mcp(d)
    try:
        t0 = time.time()
        s.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        res, err = _call(s, "matlabc_outline", {"path": "many.m"})
        dt = time.time() - t0
        t = _text(res)
        return (not err) and ("mf000" in t) and dt < 30, "400 函数 %.1fs" % dt
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_empty_file(ctx):
    """空文件 / 只有注释：不能崩。"""
    d = _mk({"empty.m": (u"", "utf-8", ""),
             "cmt.m": (u"% only a comment\n% another\n", "utf-8", "")})
    s = _mcp(d)
    try:
        s.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        r1, e1 = _call(s, "matlabc_outline", {"path": "empty.m"})
        r2, e2 = _call(s, "matlabc_outline", {"path": "cmt.m"})
        return (e1 is None) and (e2 is None), "空文件与纯注释都可查"
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)



# ---- 第 9 轮：对抗性 ------------------------------------------------

def sc_readonly_workspace(ctx):
    """工作区只读（缓存写不进去）：必须仍可用，不能崩。"""
    d = _mk({"ro.m": (u"function y = ro(x)\ny = x;\nend\n", "utf-8", "")})
    # 造一个「不可写」的 .matlabc：用一个**文件**占住这个位置，
    # 于是 makedirs 必然失败 —— 比改权限更可移植。
    with io.open(os.path.join(d, ".matlabc"), "w",
                 encoding="utf-8", newline="") as fh:
        fh.write("not a dir")
    s = _mcp(d)
    try:
        s.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        res, err = _call(s, "matlabc_diagnostics", {})
        t = _text(res)
        return (not err) and len(t) > 5, "缓存写失败仍可体检"
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_deep_chain(ctx):
    """100 层调用链：impact 不能超时/爆栈。"""
    files = {}
    for i in range(100):
        nxt = ("d%03d(%s);" % (i + 1, "x")) if i < 99 else ""
        files["d%03d.m" % i] = (
            u"function y = d%03d(x)\n%sy = x;\nend\n" % (i, nxt),
            "utf-8", "")
    d = _mk(files)
    s = _mcp(d)
    try:
        t0 = time.time()
        s.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        res, err = _call(s, "matlabc_impact", {"name": "d099"})
        dt = time.time() - t0
        t = _text(res)
        return (not err) and dt < 40, "100 层 %.1fs" % dt
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_mcp_sequential(ctx):
    """连续 10 次调用：结果必须仍然正确（不能串包）。"""
    s = _mcp(ctx["root"])
    try:
        s.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        ok = 0
        for _ in range(10):
            res, err = _call(s, "matlabc_impact", {"name": "good"})
            if not err and "影响面" in _text(res):
                ok += 1
        return ok == 10, "10/10 正确（%d）" % ok
    finally:
        s.close()


def sc_name_mismatch(ctx):
    """文件名与函数名不一致：不应崩溃，且能查到。"""
    d = _mk({"wrongname.m": (u"function y = actualname(x)\ny = x;\nend\n",
                             "utf-8", "")})
    s = _mcp(d)
    try:
        s.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        res, err = _call(s, "matlabc_outline", {"path": "wrongname.m"})
        t = _text(res)
        return (not err) and ("actualname" in t), t[:40].replace("\n", " ")
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_nul_bytes(ctx):
    """文件里含 NUL 字节：不能崩，最差当二进制跳过。"""
    d = _mk({"nul.m": (b"function y = nul(x)\n\x00\x00\ny = x;\nend\n",
                       "utf-8", "")})
    s = Session(LSP, ["--root", d])
    try:
        s.rpc("initialize", {"rootUri": _uri(d), "capabilities": {}})
        r = s.rpc("textDocument/documentSymbol",
                  {"textDocument": {"uri": _uri(os.path.join(d, "nul.m"))}},
                  timeout=15)
        return isinstance(r.get("result"), list), "含 NUL 仍返回列表"
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


def sc_huge_file(ctx):
    """5000 个函数的大文件：outline 必须在 60s 内返回（否则前端会假死）。"""
    body = [u"function y = h%04d(x)\ny = x;\nend\n" % i for i in range(5000)]
    d = _mk({"huge.m": (u"\n".join(body), "utf-8", "")})
    s = _mcp(d)
    try:
        t0 = time.time()
        s.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        res, err = _call(s, "matlabc_outline", {"path": "huge.m"})
        dt = time.time() - t0
        t = _text(res)
        return (not err) and ("h0000" in t) and dt < 60, "5000 函数 %.1fs" % dt
    finally:
        s.close()
        shutil.rmtree(d, ignore_errors=True)


# ---- R370：任务化（matlabc_task.py）-----------------------------------

def _task_demo():
    """一个小工程：定义 + 注释 + 字符串，用来验「该改的改、不该改的不动」。"""
    return _mk({
        "t1.m": (u"function y = helper(x)\n"
                 u"% helper 在注释里，不该被改\n"
                 u"y = x;\n"
                 u"end\n", "utf-8", ""),
        "t2.m": (u"function r = run(v)\n"
                 u"r = helper(v) + helper(v);\n"
                 u"end\n", "utf-8", ""),
        "t3.m": (u"function s = lit()\n"
                 u"s = 'helper';\n"
                 u"end\n", "utf-8", ""),
    })


def _run_task(root, args):
    """跑一次任务，返回 (rc, stdout)。**走 CLI**，不 import 内部函数。"""
    cmd = [sys.executable, os.path.join(ROOT, "matlabc_task.py"), "rename",
           "--dir", root] + list(args)
    log = os.path.join(tempfile.gettempdir(), "task_out_%d.txt" % os.getpid())
    with io.open(log, "wb") as fh:
        try:
            rc = subprocess.call(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                                 stdout=fh, stderr=subprocess.STDOUT,
                                 timeout=180)
        except subprocess.TimeoutExpired:
            rc = -9
    text = io.open(log, "r", encoding="utf-8", errors="replace").read()
    try:
        os.remove(log)
    except OSError:
        pass
    return rc, text


def sc_task_dry_run(ctx):
    """dry-run 必须**不写盘**，且把验收条件先列出来。"""
    d = _task_demo()
    try:
        before = io.open(os.path.join(d, "t1.m"), encoding="utf-8").read()
        rc, out = _run_task(d, ["--old", "helper", "--new", "assist"])
        after = io.open(os.path.join(d, "t1.m"), encoding="utf-8").read()
        ok = (rc == 0 and "验收" not in out and before == after
              and u"criteria" in out and u"dry-run" in out)
        return ok, "rc=%s 未写盘=%s" % (rc, before == after)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_task_apply(ctx):
    """apply 后：4 条验收全过、注释与字符串没被误改。"""
    d = _task_demo()
    try:
        rc, out = _run_task(d, ["--old", "helper", "--new", "assist",
                                "--apply"])
        t1 = io.open(os.path.join(d, "t1.m"), encoding="utf-8").read()
        t3 = io.open(os.path.join(d, "t3.m"), encoding="utf-8").read()
        ok = (rc == 0 and u"验收通过（4/4）" in out
              and "assist" in t1 and u"% helper 在注释里" in t1
              and u"'helper'" in t3)
        return ok, "rc=%s 4/4=%s" % (rc, u"4/4" in out)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_task_rollback(ctx):
    """写盘失败时必须**自己退回去**，不能留下改了一半的工程。

    第一版这条场景写错了：我先改好名、再手工塞回**另一个**旧名字，然后期望
    验收失败 —— 而那个残留名字本来就不属于本次改名，验收判通过是对的。
    （判据写错比功能写错更隐蔽，这一条是变异抽样式的自查抓出来的。）

    真正会触发回滚的是**写不进去**：把目标文件设成只读，`_apply_rename`
    抛异常 → 备份恢复 → rc=1 且 `rollback` 出现在输出里。
    """
    d = _task_demo()
    try:
        _run_task(d, ["--old", "helper", "--new", "assist", "--apply"])
        t1 = os.path.join(d, "t1.m")
        t2 = os.path.join(d, "t2.m")
        snap = io.open(t1, encoding="utf-8").read()
        os.chmod(t2, 0o444)          # 只读：写 t2 必然失败
        try:
            rc, out = _run_task(d, ["--old", "assist", "--new", "helper2",
                                    "--apply"])
        finally:
            os.chmod(t2, 0o666)      # 恢复权限，否则清理不掉
        now = io.open(t1, encoding="utf-8").read()
        ok = (rc == 1 and u"rollback" in out and now == snap)
        return ok, "rc=%s 回滚=%s 文件复原=%s" % (
            rc, u"rollback" in out, now == snap)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def _field_demo():
    """字段工程：一处 `.val` 两次、一个同名变量、一个字符串里的 `.val`。"""
    return _mk({
        "g1.m": (u"function y = g1()\n"
                 u"s.val = 1;\n"
                 u"val = 2;\n"
                 u"y = s.val;\n"
                 u"end\n", "utf-8", ""),
        "g2.m": (u"function q = g2()\n"
                 u"q = 's.val';\n"
                 u"end\n", "utf-8", ""),
    })


def _run_task_cmd(root, sub, args):
    cmd = [sys.executable, os.path.join(ROOT, "matlabc_task.py"), sub,
           "--dir", root] + list(args)
    log = os.path.join(tempfile.gettempdir(), "taskf_out_%d.txt" % os.getpid())
    with io.open(log, "wb") as fh:
        try:
            rc = subprocess.call(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                                 stdout=fh, stderr=subprocess.STDOUT,
                                 timeout=180)
        except subprocess.TimeoutExpired:
            rc = -9
    text = io.open(log, "r", encoding="utf-8", errors="replace").read()
    try:
        os.remove(log)
    except OSError:
        pass
    return rc, text


def sc_task_field_dry_run(ctx):
    """rename-field 的 dry-run：不写盘，且明说是 `.field` 而不是独立标识符。"""
    d = _field_demo()
    try:
        before = io.open(os.path.join(d, "g1.m"), encoding="utf-8").read()
        rc, out = _run_task_cmd(d, "rename-field",
                                ["--old", "val", "--new", "value"])
        after = io.open(os.path.join(d, "g1.m"), encoding="utf-8").read()
        ok = (rc == 0 and before == after and u"`.val`" in out
              and u"dry-run" in out)
        return ok, "rc=%s 未写盘=%s" % (rc, before == after)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_task_field_apply(ctx):
    """rename-field 的 apply：字段改名、同名变量不动、字符串不动。"""
    d = _field_demo()
    try:
        rc, out = _run_task_cmd(d, "rename-field",
                                ["--old", "val", "--new", "value", "--apply"])
        g1 = io.open(os.path.join(d, "g1.m"), encoding="utf-8").read()
        g2 = io.open(os.path.join(d, "g2.m"), encoding="utf-8").read()
        ok = (rc == 0 and u"验收通过（4/4）" in out
              and u"s.value" in g1 and u"\nval = 2;" in g1
              and u"'s.val'" in g2)
        return ok, "rc=%s 4/4=%s" % (rc, u"4/4" in out)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def _extract_demo():
    return _mk({
        "mx.m": (u"function y = mx(x)\n"
                 u"  a = x + 1;\n"
                 u"  b = a * 2;\n"
                 u"  y = b;\n"
                 u"end\n", "utf-8", ""),
    })


def sc_task_extract_dry_run(ctx):
    d = _extract_demo()
    try:
        before = io.open(os.path.join(d, "mx.m"), encoding="utf-8").read()
        rc, out = _run_task_cmd(d, "extract",
                                ["--file", "mx.m", "--lines", "3-4",
                                 "--name", "part", "--in", "a", "--out", "y"])
        after = io.open(os.path.join(d, "mx.m"), encoding="utf-8").read()
        ok = (rc == 0 and before == after and u"part(a)" in out)
        return ok, "rc=%s 未写盘=%s" % (rc, before == after)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_task_extract_apply(ctx):
    d = _extract_demo()
    try:
        rc, out = _run_task_cmd(d, "extract",
                                ["--file", "mx.m", "--lines", "3-4",
                                 "--name", "part", "--in", "a", "--out", "y",
                                 "--apply"])
        now = io.open(os.path.join(d, "mx.m"), encoding="utf-8").read()
        ok = (rc == 0 and u"验收通过（3/3）" in out
              and u"y = part(a);" in now and u"function y = part(a)" in now)
        return ok, "rc=%s 3/3=%s" % (rc, u"3/3" in out)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def sc_task_extract_auto(ctx):
    """`--auto`：接口由工具推断，dry-run 里能看见它推了什么。"""
    d = _extract_demo()
    try:
        rc, out = _run_task_cmd(d, "extract",
                                ["--file", "mx.m", "--lines", "3-4",
                                 "--name", "part", "--auto", "--apply"])
        now = io.open(os.path.join(d, "mx.m"), encoding="utf-8").read()
        ok = (rc == 0 and u"in=a" in out and u"out=y" in out
              and u"y = part(a);" in now)
        return ok, "rc=%s 推断=%s" % (rc, u"in=a" in out)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def _taskproj():
    return {
        "a.m": (u"function y = helper(x)\n"
                u"  y = x + 1;\n"
                u"end\n", "utf-8", ""),
        "b.m": (u"function r = run(v)\n"
                u"  r = helper(v);\n"
                u"end\n", "utf-8", ""),
    }


def sc_mcp_task_plan(sess, ctx):
    """task_plan **只读**，且把验收条件写在前面。

    这条场景自带一个小工程：共享语料里没有 `helper`，拿它去测只会得到
    "没有命中"—— 看似通过，实际什么都没验（第 1 轮踩过同类坑）。
    """
    def run(s, root):
        before = io.open(os.path.join(root, "a.m"), encoding="utf-8").read()
        res, err = _call(s, "matlabc_task_plan",
                         {"task": "rename", "dir": ".", "old": "helper",
                          "new": "assist"})
        t = _text(res)
        after = io.open(os.path.join(root, "a.m"), encoding="utf-8").read()
        ok = ((not err) and before == after
              and u"criteria" in t and u"dry-run" in t)
        return ok, "未写盘=%s 有判据=%s" % (before == after, u"criteria" in t)
    return _mcp_with(_taskproj(), run)


def sc_mcp_task_apply(sess, ctx):
    """task_apply 写入并逐条验收；改成一个已存在的名字时必须拦住并回滚。"""
    def run(s, root):
        res, err = _call(s, "matlabc_task_apply",
                         {"task": "rename", "dir": ".", "old": "helper",
                          "new": "assist"})
        t = _text(res)
        a = io.open(os.path.join(root, "a.m"), encoding="utf-8").read()
        ok_pass = ((not err) and u"验收通过（4/4）" in t and u"assist" in a)
        if not ok_pass:
            return False, "apply 未通过：%r" % (t[-60:],)
        snap = a
        res2, err2 = _call(s, "matlabc_task_apply",
                           {"task": "rename", "dir": ".", "old": "assist",
                            "new": "run"})
        t2 = _text(res2)
        a2 = io.open(os.path.join(root, "a.m"), encoding="utf-8").read()
        ok_rb = bool(err2) and (u"rollback" in t2) and (a2 == snap)
        return ok_rb, "验收通过=%s 冲突回滚=%s" % (ok_pass, ok_rb)
    return _mcp_with(_taskproj(), run)



def sc_task_extract_to(ctx):
    """`--to`：提到新文件，原文件只留调用。"""
    d = _extract_demo()
    try:
        rc, out = _run_task_cmd(d, "extract",
                                ["--file", "mx.m", "--lines", "3-4",
                                 "--name", "part", "--in", "a", "--out", "y",
                                 "--to", "part.m", "--apply"])
        p = os.path.join(d, "part.m")
        now = io.open(os.path.join(d, "mx.m"), encoding="utf-8").read()
        ok = (rc == 0 and os.path.isfile(p)
              and u"function y = part(a)" in io.open(p, encoding="utf-8").read()
              and u"y = part(a);" in now)
        return ok, "rc=%s 新文件=%s" % (rc, os.path.isfile(p))
    finally:
        shutil.rmtree(d, ignore_errors=True)



def sc_task_move(ctx):
    """move：把函数搬到同名新文件，调用点不动。"""
    d = _mk({
        "m3.m": (u"function y = main3(x)\n"
                 u"  y = helper3(x);\n"
                 u"end\n"
                 u"\n"
                 u"function z = helper3(v)\n"
                 u"  z = v * 2;\n"
                 u"end\n", "utf-8", ""),
    })
    try:
        rc, out = _run_task_cmd(d, "move", ["--file", "m3.m",
                                            "--name", "helper3",
                                            "--to", "helper3.m", "--apply"])
        p = os.path.join(d, "helper3.m")
        a = io.open(os.path.join(d, "m3.m"), encoding="utf-8").read()
        # 定义搬走、**调用点留着** —— 这才是"搬函数"该有的样子。
        gone = u"function z = helper3" not in a
        ok = (rc == 0 and os.path.isfile(p) and gone
              and u"y = helper3(x);" in a
              and io.open(p, encoding="utf-8").read().startswith(
                  u"function z = helper3"))
        return ok, "rc=%s 定义已搬走=%s" % (rc, gone)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def _batchproj():
    return {
        "a.m": (u"function y = helper(x)\n"
                u"  y = x + 1;\n"
                u"end\n", "utf-8", ""),
        "b.m": (u"function r = run(v)\n"
                u"  r = helper(v);\n"
                u"end\n", "utf-8", ""),
    }


def sc_mcp_task_batch(sess, ctx):
    """两步串起来做：rename helper->assist->solve，两步都生效。"""
    def run(s, root):
        steps = [{"task": "rename", "old": "helper", "new": "assist"},
                 {"task": "rename", "old": "assist", "new": "solve"}]
        res, err = _call(s, "matlabc_task_apply", {"dir": ".", "steps": steps})
        t = _text(res)
        a = io.open(os.path.join(root, "a.m"), encoding="utf-8").read()
        ok = (not err) and u"2 步全部通过" in t and u"solve" in a
        return ok, "rc_err=%r 两步生效=%s" % (err, u"solve" in a)
    return _mcp_with(_batchproj(), run)


def sc_mcp_task_batch_rollback(sess, ctx):
    """第二步撞上已存在的名字 -> 整批回滚，第一步也要退回去。"""
    def run(s, root):
        steps = [{"task": "rename", "old": "helper", "new": "assist"},
                 {"task": "rename", "old": "assist", "new": "run"}]
        before = io.open(os.path.join(root, "a.m"), encoding="utf-8").read()
        res, err = _call(s, "matlabc_task_apply", {"dir": ".", "steps": steps})
        t = _text(res)
        after = io.open(os.path.join(root, "a.m"), encoding="utf-8").read()
        ok = bool(err) and (u"已回滚全部" in t) and (after == before)
        return ok, "回滚=%s 文件复原=%s" % (u"已回滚全部" in t, after == before)
    return _mcp_with(_batchproj(), run)


def sc_mcp_task_batch_plan(sess, ctx):
    """计划在副本上推演：链式第二步也能算出可行，且工程未被改。"""
    def run(s, root):
        steps = [{"task": "rename", "old": "helper", "new": "assist"},
                 {"task": "rename", "old": "assist", "new": "solve"}]
        before = io.open(os.path.join(root, "a.m"), encoding="utf-8").read()
        res, err = _call(s, "matlabc_task_plan", {"dir": ".", "steps": steps})
        t = _text(res)
        after = io.open(os.path.join(root, "a.m"), encoding="utf-8").read()
        ok = ((not err) and u"全部可执行" in t and before == after)
        return ok, "可执行=%s 未改动=%s" % (u"全部可执行" in t, before == after)
    return _mcp_with(_batchproj(), run)



def _write_steps(d, steps):
    p = os.path.join(d, "plan.json")
    io.open(p, "w", encoding="utf-8", newline="").write(
        json.dumps({"steps": steps}, ensure_ascii=False))
    return p


def sc_task_batch_cli(ctx):
    """CLI 的 batch 子命令：步骤文件 -> 两步都生效。"""
    d = _mk({
        "q1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n", "utf-8", ""),
        "q2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n", "utf-8", ""),
    })
    try:
        p = _write_steps(d, [{"task": "rename", "old": "aa", "new": "cc"},
                             {"task": "rename", "old": "cc", "new": "dd"}])
        rc, out = _run_task_cmd(d, "batch", ["--steps", p, "--apply"])
        now = io.open(os.path.join(d, "q1.m"), encoding="utf-8").read()
        ok = (rc == 0 and u"2 步全部通过" in out and u"dd" in now)
        return ok, "rc=%s 两步生效=%s" % (rc, u"dd" in now)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_task_batch_cli_rollback(ctx):
    """CLI 的 batch：第二步失败 -> 整批回滚。"""
    d = _mk({
        "q1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n", "utf-8", ""),
        "q2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n", "utf-8", ""),
    })
    try:
        before = io.open(os.path.join(d, "q1.m"), encoding="utf-8").read()
        p = _write_steps(d, [{"task": "rename", "old": "aa", "new": "cc"},
                             {"task": "rename", "old": "cc", "new": "bb"}])
        rc, out = _run_task_cmd(d, "batch", ["--steps", p, "--apply"])
        after = io.open(os.path.join(d, "q1.m"), encoding="utf-8").read()
        ok = (rc == 1 and u"已回滚全部" in out and after == before)
        return ok, "rc=%s 回滚=%s 复原=%s" % (
            rc, u"已回滚全部" in out, after == before)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def sc_task_batch_ref(ctx):
    """CLI batch：第二步用 ${prev.new} 引用上一步改出来的名字。"""
    d = _mk({
        "s1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n", "utf-8", ""),
        "s2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n", "utf-8", ""),
    })
    try:
        p = _write_steps(d, [{"task": "rename", "old": "aa", "new": "cc"},
                             {"task": "rename", "old": "${prev.new}",
                              "new": "dd"}])
        rc, out = _run_task_cmd(d, "batch", ["--steps", p, "--apply"])
        now = io.open(os.path.join(d, "s1.m"), encoding="utf-8").read()
        ok = (rc == 0 and u"2 步全部通过" in out and u"dd" in now)
        return ok, "rc=%s 引用生效=%s" % (rc, u"dd" in now)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def _run_undo(root):
    cmd = [sys.executable, os.path.join(ROOT, "matlabc_task.py"), "undo",
           "--dir", root, "--apply"]
    log = os.path.join(tempfile.gettempdir(), "undo_out_%d.txt" % os.getpid())
    with io.open(log, "wb") as fh:
        rc = subprocess.call(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                             stdout=fh, stderr=subprocess.STDOUT, timeout=120)
    text = io.open(log, "r", encoding="utf-8", errors="replace").read()
    try:
        os.remove(log)
    except OSError:
        pass
    return rc, text


def sc_task_undo(ctx):
    """改成之后能原样撤回。"""
    d = _mk({
        "u1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n", "utf-8", ""),
        "u2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n", "utf-8", ""),
    })
    try:
        before = io.open(os.path.join(d, "u1.m"), encoding="utf-8").read()
        rc, out = _run_task_cmd(d, "rename", ["--old", "aa", "--new", "cc",
                                             "--apply"])
        changed = io.open(os.path.join(d, "u1.m"), encoding="utf-8").read()
        rc2, out2 = _run_undo(d)
        after = io.open(os.path.join(d, "u1.m"), encoding="utf-8").read()
        ok = (rc == 0 and u"cc" in changed and rc2 == 0 and after == before)
        return ok, "改=%s 撤回=%s" % (u"cc" in changed, after == before)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def sc_task_undo_conflict(ctx):
    """任务之后改过文件 -> 拒绝撤销，且文件不被改回。"""
    d = _mk({
        "u1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n", "utf-8", ""),
        "u2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n", "utf-8", ""),
    })
    try:
        _run_task_cmd(d, "rename", ["--old", "aa", "--new", "cc", "--apply"])
        p = os.path.join(d, "u1.m")
        io.open(p, "a", encoding="utf-8").write(u"% 手工改的一行\n")
        snap = io.open(p, encoding="utf-8").read()
        rc, out = _run_undo(d)
        now = io.open(p, encoding="utf-8").read()
        ok = (rc == 1 and u"被改过" in out and now == snap)
        return ok, "rc=%s 拒绝=%s 未覆盖=%s" % (rc, u"被改过" in out, now == snap)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def sc_mcp_task_undo(ctx):
    """MCP：改完之后能撤回去。"""
    def run(s, root):
        steps = {"dir": ".", "task": "rename", "old": "helper",
                 "new": "assist"}
        r1, e1 = _call(s, "matlabc_task_apply", steps)
        changed = io.open(os.path.join(root, "a.m"), encoding="utf-8").read()
        r2, e2 = _call(s, "matlabc_task_undo", {"dir": ".", "apply": True})
        t2 = _text(r2)
        back = io.open(os.path.join(root, "a.m"), encoding="utf-8").read()
        ok = ((not e1) and u"assist" in changed
              and (not e2) and u"verdict: undone" in t2
              and u"helper" in back)
        return ok, "改=%s 撤=%s" % (u"assist" in changed, u"helper" in back)
    return _mcp_with({
        "a.m": (u"function y = helper(x)\n  y = x + 1;\nend\n",
                "utf-8", ""),
        "b.m": (u"function r = run(v)\n  r = helper(v);\nend\n",
                "utf-8", ""),
    }, run)



def sc_task_undo_list(ctx):
    """CLI：两步任务 -> --list 列两条 -> 按 id 倒序撤干净。"""
    d = _mk({"v1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n",
                      "utf-8", "")})
    try:
        orig = io.open(os.path.join(d, "v1.m"), encoding="utf-8").read()
        _run_task_cmd(d, "rename", ["--old", "aa", "--new", "bb", "--apply"])
        _run_task_cmd(d, "rename", ["--old", "bb", "--new", "cc", "--apply"])
        rc, out = _run_task_cmd(d, "undo", ["--list"])
        ids = [ln.split()[0] for ln in out.splitlines()
               if ln.strip() and ln.split()[0][:8].isdigit()]
        rc1, _ = _run_task_cmd(d, "undo", ["--id", ids[0], "--apply"]) \
            if ids else (1, "")
        rc2, _ = _run_task_cmd(d, "undo", ["--id", ids[1], "--apply"]) \
            if len(ids) > 1 else (1, "")
        back = io.open(os.path.join(d, "v1.m"), encoding="utf-8").read()
        ok = (rc == 0 and len(ids) == 2 and rc1 == 0 and rc2 == 0
              and back == orig)
        return ok, "记录=%d 撤净=%s" % (len(ids), back == orig)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def sc_task_undo_batch(ctx):
    """CLI：两步 batch -> undo --batch 一次撤干净。"""
    d = _mk({
        "w1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n", "utf-8", ""),
        "w2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n", "utf-8", ""),
    })
    try:
        o1 = io.open(os.path.join(d, "w1.m"), encoding="utf-8").read()
        o2 = io.open(os.path.join(d, "w2.m"), encoding="utf-8").read()
        p = _write_steps(d, [{"task": "rename", "old": "aa", "new": "cc"},
                             {"task": "rename", "old": "bb", "new": "dd"}])
        rc0, _ = _run_task_cmd(d, "batch", ["--steps", p, "--apply"])
        rc, out = _run_task_cmd(d, "undo", ["--batch", "--apply"])
        b1 = io.open(os.path.join(d, "w1.m"), encoding="utf-8").read()
        b2 = io.open(os.path.join(d, "w2.m"), encoding="utf-8").read()
        ok = (rc0 == 0 and rc == 0 and b1 == o1 and b2 == o2
              and u"2 个任务" in out)
        return ok, "撤净=%s/%s" % (b1 == o1, b2 == o2)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def sc_task_undo_verify(ctx):
    """CLI：撤销之后必须打印结构验收通过。"""
    d = _mk({
        "x1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n", "utf-8", ""),
        "x2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n", "utf-8", ""),
    })
    try:
        _run_task_cmd(d, "rename", ["--old", "aa", "--new", "cc", "--apply"])
        rc, out = _run_task_cmd(d, "undo", ["--apply"])
        ok = (rc == 0 and u"撤销验收通过（3/3）" in out
              and u"结构回到任务前" in out)
        return ok, "rc=%s 验收=%s" % (rc, u"撤销验收通过" in out)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def _batch_proj():
    return {
        "w1.m": (u"function y = aa(x)\n  y = x + 1;\nend\n", "utf-8", ""),
        "w2.m": (u"function r = bb(v)\n  r = aa(v);\nend\n", "utf-8", ""),
    }


def sc_mcp_task_undo_list(ctx):
    """MCP：list=true 只列历史，不动文件。"""
    def run(s, root):
        _call(s, "matlabc_task_apply",
              {"dir": ".", "task": "rename", "old": "aa", "new": "cc"})
        before = io.open(os.path.join(root, "w1.m"), encoding="utf-8").read()
        res, err = _call(s, "matlabc_task_undo", {"dir": ".", "list": True})
        t = _text(res)
        after = io.open(os.path.join(root, "w1.m"), encoding="utf-8").read()
        rows = [x for x in t.splitlines() if x.strip()]
        ok = (not err) and len(rows) >= 1 and u"rename" in t and before == after
        return ok, "行数=%d 未改动=%s" % (len(rows), before == after)
    return _mcp_with(_batch_proj(), run)


def sc_mcp_task_undo_batch(ctx):
    """MCP：batch=true 一次撤掉整批。"""
    def run(s, root):
        o1 = io.open(os.path.join(root, "w1.m"), encoding="utf-8").read()
        o2 = io.open(os.path.join(root, "w2.m"), encoding="utf-8").read()
        _call(s, "matlabc_task_apply",
              {"dir": ".", "steps": [
                  {"task": "rename", "old": "aa", "new": "cc"},
                  {"task": "rename", "old": "bb", "new": "dd"}]})
        res, err = _call(s, "matlabc_task_undo",
                         {"dir": ".", "batch": True, "apply": True})
        t = _text(res)
        b1 = io.open(os.path.join(root, "w1.m"), encoding="utf-8").read()
        b2 = io.open(os.path.join(root, "w2.m"), encoding="utf-8").read()
        ok = (not err) and u"undone" in t and b1 == o1 and b2 == o2
        return ok, "撤净=%s/%s" % (b1 == o1, b2 == o2)
    return _mcp_with(_batch_proj(), run)



def sc_task_prune(ctx):
    """CLI prune：计划不删、执行后剩 keep 条。"""
    d = _mk({"a.m": (u"function y = aa(x)\n  y = x + 1;\nend\n",
                     "utf-8", "")})
    try:
        hd = os.path.join(d, ".matlabc", "tasks")
        if not os.path.isdir(hd):
            os.makedirs(hd)
        for i in range(12):
            rid = "20261020-0000%02d-000" % i
            io.open(os.path.join(hd, rid + ".json"), "w",
                    encoding="utf-8", newline="").write(json.dumps({
                        "id": rid, "kind": "rename", "when": "x",
                        "undone": (i < 6), "files": [], "created": [],
                        "params": {}, "batch": "", "scan": {}}))
        rc1, out1 = _run_task_cmd(d, "prune", ["--keep", "8"])
        n1 = len(os.listdir(hd))
        rc2, out2 = _run_task_cmd(d, "prune", ["--keep", "8", "--apply"])
        n2 = len(os.listdir(hd))
        ok = (rc1 == 0 and n1 == 12 and rc2 == 0 and n2 == 8
              and u"已撤销 4" in out1)
        return ok, "计划=%d 执行后=%d" % (n1, n2)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def sc_task_record_packed(ctx):
    """记录里存的是压缩原文（before_z），撤销仍然逐字节还原。"""
    d = _mk({"a.m": (u"function y = aa(x)\n  y = x + 1;\nend\n",
                     "utf-8", "")})
    try:
        orig = io.open(os.path.join(d, "a.m"), encoding="utf-8").read()
        _run_task_cmd(d, "rename", ["--old", "aa", "--new", "cc", "--apply"])
        hd = os.path.join(d, ".matlabc", "tasks")
        name = sorted(os.listdir(hd))[-1]
        rec = json.loads(io.open(os.path.join(hd, name),
                                 encoding="utf-8").read())
        f = (rec.get("files") or [{}])[0]
        packed = ("before_z" in f) and ("before" not in f)
        rc, _ = _run_task_cmd(d, "undo", ["--apply"])
        back = io.open(os.path.join(d, "a.m"), encoding="utf-8").read()
        ok = packed and rc == 0 and back == orig
        return ok, "压缩=%s 还原=%s" % (packed, back == orig)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def sc_task_undo_diff(ctx):
    """CLI：undo --diff 列出将发生的改动，且不写盘。"""
    d = _mk({"a.m": (u"function y = aa(x)\n  y = x + 1;\nend\n",
                     "utf-8", "")})
    try:
        _run_task_cmd(d, "rename", ["--old", "aa", "--new", "cc", "--apply"])
        before = io.open(os.path.join(d, "a.m"), encoding="utf-8").read()
        rc, out = _run_task_cmd(d, "undo", ["--diff"])
        after = io.open(os.path.join(d, "a.m"), encoding="utf-8").read()
        ok = (rc == 0 and u"-function y = cc(x)" in out
              and u"+function y = aa(x)" in out and before == after)
        return ok, "rc=%s 未写盘=%s" % (rc, before == after)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def sc_task_undo_previews(ctx):
    """CLI：undo --diff --json 带 previews（撤销后的内容）。"""
    d = _mk({"a.m": (u"function y = aa(x)\n  y = x + 1;\nend\n",
                     "utf-8", "")})
    try:
        _run_task_cmd(d, "rename", ["--old", "aa", "--new", "cc", "--apply"])
        rc, out = _run_task_cmd(d, "undo", ["--diff", "--json"])
        j = None
        try:
            j = json.loads(out[out.index("{"):])
        except Exception:
            j = None
        info = (j or {}).get("info") or {}
        pvs = info.get("previews") or []
        ok = (rc == 0 and len(pvs) == 1
              and u"aa" in pvs[0].get("before", ""))
        return ok, "previews=%d" % len(pvs)
    finally:
        shutil.rmtree(d, ignore_errors=True)



def sc_task_stats(ctx):
    """CLI：stats 输出表头与至少一行。"""
    d = _mk({"a.m": (u"function y = aa(x)\n  y = x + 1;\nend\n",
                     "utf-8", "")})
    try:
        _run_task_cmd(d, "rename", ["--old", "aa", "--new", "cc", "--apply"])
        rc, out = _run_task_cmd(d, "stats", [])
        ok = (rc == 0 and u"类型" in out and u"rename" in out
              and u"中位ms" in out)
        return ok, "rc=%s" % rc
    finally:
        shutil.rmtree(d, ignore_errors=True)



def sc_mcp_task_stats(ctx):
    """MCP：stats 给出表头与回滚原因排行。"""
    def run(s, root):
        _call(s, "matlabc_task_apply",
              {"dir": ".", "task": "rename", "old": "aa", "new": "cc"})
        # 制造一次回滚：改名成已存在的 run
        _call(s, "matlabc_task_apply",
              {"dir": ".", "task": "rename", "old": "cc", "new": "run"})
        res, err = _call(s, "matlabc_task_stats", {"dir": "."})
        t = _text(res)
        ok = ((not err) and u"中位ms" in t and u"回滚原因" in t
              and u"调用边数变了" in t)
        return ok, "含原因=%s" % (u"回滚原因" in t)
    return _mcp_with({
        "a.m": (u"function y = aa(x)\n  y = x + 1;\nend\n", "utf-8", ""),
        "b.m": (u"function r = run(v)\n  r = aa(v);\nend\n", "utf-8", ""),
    }, run)



def sc_task_baseline(ctx):
    """CLI：baseline --save 之后 stats 仍正常输出。"""
    d = _mk({"a.m": (u"function y = aa(x)\n  y = x + 1;\nend\n",
                     "utf-8", "")})
    try:
        _run_task_cmd(d, "rename", ["--old", "aa", "--new", "cc", "--apply"])
        rc1, out1 = _run_task_cmd(d, "baseline", ["--save"])
        rc2, out2 = _run_task_cmd(d, "stats", [])
        ok = (rc1 == 0 and u"基线已保存" in out1
              and rc2 == 0 and u"中位ms" in out2)
        return ok, "保存=%s stats=%s" % (u"基线已保存" in out1, u"中位ms" in out2)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--only", default="")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    if args.help:
        sys.stdout.write(__doc__)
        return 0
    for p in (LSP, MCP, CORPUS):
        if not os.path.exists(p):
            print("rsi_scenarios: 缺输入（%s）" % p)
            return 2

    root = _lsp_fixture()
    rows = []
    try:
        # ---- LSP 会话内场景 ----
        lsp_sc = [("LSP initialize", sc_lsp_initialize),
                  ("LSP documentSymbol", sc_lsp_symbols),
                  ("LSP definition", sc_lsp_definition),
                  ("LSP references", sc_lsp_references),
                  ("LSP hover", sc_lsp_hover),
                  ("LSP codeLens", sc_lsp_codelens),
                  ("LSP 未知方法", sc_lsp_unknown_method)]
        sess = Session(LSP, ["--root", root], framing="lsp")
        try:
            for name, fn in lsp_sc:
                try:
                    ok, detail = fn(sess, {"root": root})
                except Exception as exc:
                    ok, detail = False, "异常 %r" % (exc,)
                rows.append((name, ok, detail))
            # shutdown 必须最后
            try:
                ok, detail = sc_lsp_shutdown({"root": root})
            except Exception as exc:
                ok, detail = False, "异常 %r" % (exc,)
            rows.append(("LSP shutdown", ok, detail))
        finally:
            sess.close()

        # ---- 需要独立进程 / 独立工程 ----
        solo = [("LSP 未 initialize 即请求", sc_lsp_before_init),
                ("LSP 坏 JSON 行", sc_lsp_malformed_json),
                ("空工程", sc_empty_project),
                ("非 UTF-8 文件", sc_non_utf8),
                ("BOM 文件", sc_bom),
                ("语法不完整", sc_syntax_error),
                ("classdef", sc_classdef),
                ("CRLF 行号", sc_crlf_lines),
                ("中文标识符", sc_unicode_ident),
                ("超长行", sc_long_line),
                ("嵌套函数", sc_nested_functions),
                ("增量 didChange", sc_lsp_didchange),
                ("50 文件工程", sc_lsp_many_files),
                ("自递归函数", sc_recursive),
                ("中文路径", sc_unicode_path),
                ("BOM+CRLF", sc_bom_crlf),
                ("MCP 未 initialize", sc_mcp_before_init),
                ("缓存文件损坏", sc_corrupt_cache),
                ("120 文件工程", sc_big_project),
                ("单文件 400 函数", sc_many_functions),
                ("空文件与纯注释", sc_empty_file),
                ("工作区只读", sc_readonly_workspace),
                ("100 层调用链", sc_deep_chain),
                ("连续 10 次调用", sc_mcp_sequential),
                ("文件名≠函数名", sc_name_mismatch),
                ("含 NUL 字节", sc_nul_bytes),
                ("5000 函数大文件", sc_huge_file),
                ("任务 rename dry-run", sc_task_dry_run),
                ("任务 rename apply", sc_task_apply),
                ("任务 rename 回滚", sc_task_rollback),
                ("任务 rename-field 计划", sc_task_field_dry_run),
                ("任务 rename-field 应用", sc_task_field_apply),
                ("任务 extract 计划", sc_task_extract_dry_run),
                ("任务 extract 应用", sc_task_extract_apply),
                ("任务 extract 自动推断", sc_task_extract_auto),
                ("任务 extract 跨文件", sc_task_extract_to),
                ("任务 move 跨文件", sc_task_move),
                ("任务 batch（CLI）", sc_task_batch_cli),
                ("任务 batch 回滚（CLI）", sc_task_batch_cli_rollback),
                ("任务 batch 步骤引用", sc_task_batch_ref),
                ("任务 undo", sc_task_undo),
                ("任务 undo 冲突拒绝", sc_task_undo_conflict),
                ("MCP task_undo", sc_mcp_task_undo),
                ("任务 undo 列表", sc_task_undo_list),
                ("任务 undo 整批", sc_task_undo_batch),
                ("任务 undo 验收", sc_task_undo_verify),
                ("MCP task_undo list", sc_mcp_task_undo_list),
                ("MCP task_undo batch", sc_mcp_task_undo_batch),
                ("任务记录裁剪", sc_task_prune),
                ("任务记录统计", sc_task_stats),
                ("MCP task_stats", sc_mcp_task_stats),
                ("任务耗时基线", sc_task_baseline),
                ("任务记录压缩存储", sc_task_record_packed),
                ("任务 undo diff", sc_task_undo_diff),
                ("任务 undo previews", sc_task_undo_previews)]
        for name, fn in solo:
            try:
                ok, detail = fn({"root": root})
            except Exception as exc:
                ok, detail = False, "异常 %r" % (exc,)
            rows.append((name, ok, detail))

        # ---- MCP ----
        mcp_sc = [("MCP initialize", sc_mcp_initialize),
                  ("MCP tools/list", sc_mcp_list),
                  ("MCP stats", sc_mcp_stats),
                  ("MCP outline", sc_mcp_outline),
                  ("MCP heat", sc_mcp_heat),
                  ("MCP search", sc_mcp_search),
                  ("MCP help", sc_mcp_help),
                  ("MCP impact", sc_mcp_impact_lists),
                  ("MCP 未知工具", sc_mcp_unknown_tool),
                  ("MCP 参数缺失", sc_mcp_bad_args),
                  ("MCP 越界路径", sc_mcp_outside_root),
                  ("MCP fields", sc_mcp_fields),
                  ("MCP diagnostics", sc_mcp_diagnostics),
                  ("MCP 诊断缓存命中", sc_mcp_diag_cache),
                  ("MCP changed", sc_mcp_changed),
                  ("MCP explain", sc_mcp_explain),
                  ("MCP definition", sc_mcp_definition),
                  ("MCP references", sc_mcp_references),
                  ("MCP task_plan", sc_mcp_task_plan),
                  ("MCP task_apply", sc_mcp_task_apply),
                  ("MCP task 批量执行", sc_mcp_task_batch),
                  ("MCP task 批量回滚", sc_mcp_task_batch_rollback),
                  ("MCP task 批量计划", sc_mcp_task_batch_plan)]
        ms = _mcp(root)
        try:
            for name, fn in mcp_sc:
                try:
                    ok, detail = fn(ms, {"root": root})
                except Exception as exc:
                    ok, detail = False, "异常 %r" % (exc,)
                rows.append((name, ok, detail))
        finally:
            ms.close()

        # ---- 写操作（独立工程） ----
        for name, fn in (("MCP cbridge 正向", sc_mcp_cbridge_forward),
                         ("MCP cbridge 反向", sc_mcp_cbridge_reverse),
                         ("MCP 空工程 stats", sc_mcp_stats_empty)):
            try:
                ok, detail = fn({"root": root})
            except Exception as exc:
                ok, detail = False, "异常 %r" % (exc,)
            rows.append((name, ok, detail))

        for name, ok, detail in _write_mcp_scenarios({"root": root}):
            rows.append((name, ok, detail))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    if args.list:
        for n, _, _ in rows:
            print("  " + n)
        print("共 %d 个场景" % len(rows))
        return 0

    picked = [r for r in rows if not args.only or args.only in r[0]]
    bad = [r for r in picked if not r[1]]
    for name, ok, detail in picked:
        print("  [%s] %-24s %s" % ("PASS" if ok else "FAIL", name, detail[:90]))
    print("rsi_scenarios: %d 个场景，失败 %d%s"
          % (len(picked), len(bad),
             "" if not bad else "：" + "、".join(r[0] for r in bad)))

    # 场景集只许变严：删场景必须同时改下界
    if len(rows) < MIN_SCENARIOS:
        print("rsi_scenarios: FAIL 场景数 %d < 下界 %d（删场景必须改 MIN_SCENARIOS）"
              % (len(rows), MIN_SCENARIOS))
        return 1
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
