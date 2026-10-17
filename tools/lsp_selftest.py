# -*- coding: utf-8 -*-
"""lsp_selftest.py —— `matlabc_lsp.py` 的三组判据（诊断 / 定义 / 引用）。

为什么单独成一个工具而不进 `check_all`：它要**起子进程 + 跑分析**，
与其它护栏"纯静态读文件"的性质不同；放进 runner 会把 24 道门从 2 分钟拖到 3 分钟，
而它只在**改 LSP 之后**才需要跑。

用法：

    python tools/lsp_selftest.py            # 三组全跑
    python tools/lsp_selftest.py --diag     # 只跑诊断
    python tools/lsp_selftest.py --help

退出码：0 = 全过；1 = 有失败；2 = 缺输入（找不到 matlabc_lsp.py / 语料）。
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LSP = os.path.join(ROOT, "matlabc_lsp.py")
CORPUS = os.path.join(ROOT, "tests", "sample_m")

_bad = 0
_good = 0


def _chk(cond, msg):
    global _bad, _good
    if cond:
        _good += 1
    else:
        _bad += 1
        print("  [FAIL] " + msg)


def _uri(path):
    return "file:///" + path.replace("\\", "/").lstrip("/")


class Client(object):
    """极简 LSP 客户端：spawn 一个 `matlabc_lsp.py`，收发分帧消息。"""

    def __init__(self):
        self.p = subprocess.Popen(
            [sys.executable, LSP], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

    def send(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.p.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        self.p.stdin.flush()

    def recv(self):
        headers = {}
        while True:
            line = self.p.stdout.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            key, val = line.decode("ascii").split(":", 1)
            headers[key.strip().lower()] = val.strip()
        n = int(headers["content-length"])
        return json.loads(self.p.stdout.read(n).decode("utf-8"))

    def init(self):
        self.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"rootUri": _uri(CORPUS), "capabilities": {}}})
        return self.recv()

    def open(self, path):
        self.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                   "params": {"textDocument": {"uri": _uri(path),
                                               "languageId": "matlab",
                                               "version": 1, "text": "x=1;\n"}}})
        return self.recv()

    def close(self):
        try:
            self.send({"jsonrpc": "2.0", "id": 99, "method": "shutdown"})
            self.recv()
            self.send({"jsonrpc": "2.0", "method": "exit"})
            self.p.wait(timeout=10)
        except Exception:
            pass
        finally:
            try:
                self.p.kill()
            except Exception:
                pass


def _diag(c):
    r = c.init()
    caps = ((r or {}).get("result") or {}).get("capabilities") or {}
    _chk(caps.get("textDocumentSync") == 1, "textDocumentSync 应为 1")
    # `open()` 自己就把 didOpen 触发的 publishDiagnostics 读回来了
    # （首版这里又调了一次 recv()，于是阻塞在没有第三条消息的 read 上）
    d = c.open(os.path.join(CORPUS, "MyCls.m"))
    diags = ((d or {}).get("params") or {}).get("diagnostics") or []
    _chk(len(diags) == 2, "MyCls.m 应 2 条诊断，实际 %d" % len(diags))
    _chk(all(x.get("code") == "m_missing_doc" for x in diags),
         "诊断 code 应全为 m_missing_doc")
    _chk(sorted(x["range"]["start"]["line"] for x in diags) == [6, 13],
         "行号应 0-based [6,13]")
    _chk(all(x.get("severity") == 3 for x in diags), "severity 应为 3")


def _def(c):
    c.init()
    a_m = os.path.join(CORPUS, "a.m")
    c.open(a_m)
    c.send({"jsonrpc": "2.0", "id": 2, "method": "textDocument/definition",
            "params": {"textDocument": {"uri": _uri(a_m)},
                       "position": {"line": 2, "character": 5}}})
    loc = ((c.recv() or {}).get("result") or [None])[0]
    _chk(loc is not None and loc["range"]["start"]["line"] == 5,
         "definition b -> L5")
    c.send({"jsonrpc": "2.0", "id": 3, "method": "textDocument/definition",
            "params": {"textDocument": {"uri": _uri(a_m)},
                       "position": {"line": 12, "character": 5}}})
    loc = ((c.recv() or {}).get("result") or [None])[0]
    _chk(loc is not None and loc.get("uri", "").endswith("/d.m"),
         "definition d -> 跨文件 d.m")
    c.send({"jsonrpc": "2.0", "id": 4, "method": "textDocument/definition",
            "params": {"textDocument": {"uri": _uri(a_m)},
                       "position": {"line": 1, "character": 5}}})
    _chk((c.recv() or {}).get("result") == [], "注释上 definition 应为 []")


def _ref(c):
    c.init()
    a_m = os.path.join(CORPUS, "a.m")
    c.open(a_m)
    c.send({"jsonrpc": "2.0", "id": 2, "method": "textDocument/references",
            "params": {"textDocument": {"uri": _uri(a_m)},
                       "position": {"line": 5, "character": 14},
                       "context": {"includeDeclaration": False}}})
    refs = (c.recv() or {}).get("result") or []
    _chk(len(refs) == 1 and refs[0]["range"]["start"]["line"] == 0,
         "references b -> 调用者 a 在 L0")
    c.send({"jsonrpc": "2.0", "id": 3, "method": "textDocument/references",
            "params": {"textDocument": {"uri": _uri(a_m)},
                       "position": {"line": 5, "character": 14},
                       "context": {"includeDeclaration": True}}})
    _chk(len((c.recv() or {}).get("result") or []) == 2, "含定义应 2 个位置")


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--diag", action="store_true")
    # 注意：不能用 `--def` —— argparse 会把它变成 `args.def`，而 `def` 是 Python 关键字。
    ap.add_argument("--definition", action="store_true")
    ap.add_argument("--ref", action="store_true")
    ap.add_argument("--help", action="store_true")
    args = ap.parse_args(argv)

    if args.help:
        print(__doc__)
        return 0
    if not os.path.isfile(LSP):
        print("lsp_selftest: 缺输入（找不到 %s）" % LSP)
        return 2
    if not os.path.isdir(CORPUS):
        print("lsp_selftest: 缺输入（找不到语料 %s）" % CORPUS)
        return 2

    groups = []
    if args.diag:
        groups = [("diag", _diag)]
    elif args.definition:
        groups = [("definition", _def)]
    elif args.ref:
        groups = [("ref", _ref)]
    else:
        groups = [("diag", _diag), ("def", _def), ("ref", _ref)]

    for name, fn in groups:
        print("[%s]" % name)
        c = Client()
        try:
            fn(c)
        finally:
            c.close()


    print('LSP SELFTEST {"bad": %d, "good": %d}' % (_bad, _good))
    return 0 if _bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
