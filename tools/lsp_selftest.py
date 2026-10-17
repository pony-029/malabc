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
import atexit
import json
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LSP = os.path.join(ROOT, "matlabc_lsp.py")
CORPUS = os.path.join(ROOT, "tests", "sample_m")
#: F3 的反例语料：`b` 未定义就被读（`--json` 的 uninitialized 有 1 条、
#: heuristics 是 0 条 —— 所以它的诊断只可能来自 facts）。
CORPUS_UNINIT = os.path.join(ROOT, "tests", "sample_uninit")

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
        # **兜底回收**：`close()` 在 `finally` 里，但进程被 `Stop-Process`
        # 杀掉时 `finally` 根本不执行 —— R176 清理出 4 个残留（2 个
        # lsp_selftest + 2 个 matlabc_lsp）。正常退出时 atexit 会替我们
        # 再调一次 `close()`，而 `close()` 里的 kill 对已死进程是空操作。
        atexit.register(self.close)

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

    def init(self, root=None):
        self.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"rootUri": _uri(root or CORPUS),
                              "capabilities": {}}})
        return self.recv()

    def open(self, path):
        """`didOpen` 会收到**两条** `publishDiagnostics`。

        第一条是**空数组**（证明协议循环没被分析阻塞），第二条才是真结果。
        返回第二条；第一条留在 `self.first_diag` 供 `_diag` 断言。
        """
        self.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                   "params": {"textDocument": {"uri": _uri(path),
                                               "languageId": "matlab",
                                               "version": 1, "text": "x=1;\n"}}})
        self.first_diag = self.recv()
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
    # `open()` 读两条：第一条是空（先返回、再异步算），第二条才是真结果。
    d = c.open(os.path.join(CORPUS, "MyCls.m"))
    _chk(((c.first_diag or {}).get("params") or {}).get("diagnostics") == [],
         "didOpen 的第一条诊断必须是空数组（证明没阻塞协议循环）")
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


def _hover(c):
    c.init()
    a_m = os.path.join(CORPUS, "a.m")
    c.open(a_m)
    c.send({"jsonrpc": "2.0", "id": 2, "method": "textDocument/hover",
            "params": {"textDocument": {"uri": _uri(a_m)},
                       "position": {"line": 2, "character": 5}}})
    h = (c.recv() or {}).get("result")
    val = ((h or {}).get("contents") or {}).get("value") or ""
    _chk(h is not None, "b 上应有 hover")
    _chk("function [z] = b(x)" in val,
         "hover 应含真实签名 `function [z] = b(x)`，实际 %r" % (val[:60],))
    _chk("a.m" in val, "hover 应给出来源文件 a.m")
    c.send({"jsonrpc": "2.0", "id": 3, "method": "textDocument/hover",
            "params": {"textDocument": {"uri": _uri(a_m)},
                       "position": {"line": 1, "character": 5}}})
    _chk((c.recv() or {}).get("result") is None, "注释上 hover 应为 null")


def _symbols(c):
    c.init()
    a_m = os.path.join(CORPUS, "a.m")
    c.open(a_m)
    c.send({"jsonrpc": "2.0", "id": 2, "method": "textDocument/documentSymbol",
            "params": {"textDocument": {"uri": _uri(a_m)}}})
    syms = (c.recv() or {}).get("result") or []
    _chk([s.get("name") for s in syms] == ["a", "b", "c"],
         "a.m 应有 a/b/c 三个符号，实际 %r" % ([s.get("name") for s in syms],))
    _chk([s["selectionRange"]["start"]["line"] for s in syms] == [0, 5, 10],
         "行号应为 0/5/10")
    _chk(all(s.get("kind") == 12 for s in syms), "kind 应为 12（Function）")
    _chk(all(s["range"]["start"]["line"] <= s["selectionRange"]["start"]["line"]
             and s["selectionRange"]["end"]["line"] <= s["range"]["end"]["line"]
             for s in syms),
         "selectionRange 必须落在 range 内部（否则 VSCode 整批丢弃）")


def _uninit(c):
    """F3 的验收判据（R153 预备）：

    `tests/sample_uninit/x.m` 里 `b` 未定义就被读 —— `--json` 的
    `uninitialized` 键有 1 条，而 `heuristics` 是 0 条。所以**这条诊断
    只能来自 facts**，它证明 LSP 的能力超出了 heuristics 通道。

    ⚠ 现在（F3 之前）跑会红 —— 这正是它存在的意义：**F3 做完它才会绿**。
    """
    c.init(CORPUS_UNINIT)
    x_m = os.path.join(CORPUS_UNINIT, "x.m")
    d = c.open(x_m)
    diags = ((d or {}).get("params") or {}).get("diagnostics") or []
    _chk(len(diags) == 1, "x.m 应有 1 条 uninitialized 诊断，实际 %d"
         % len(diags))
    if diags:
        _chk(diags[0].get("code") == "c_uninit_read", "code 应为 c_uninit_read")
        _chk(diags[0]["range"]["start"]["line"] == 2,
             "行号应为 2（0-based，源文件第 3 行）")
        _chk(diags[0].get("severity") == 2, "severity 应为 2（warning）")


def _save(c):
    """R154：`didSave` 必须**重算**，不能重放打开那一刻的缓存。

    ⚠ 这条判据要**改文件**，所以它 `copytree` 到临时目录再动手 ——
    **绝不允许**直接改 `tests/sample_uninit`（那会污染仓库）。

    判据是 `1 -> 0`：改掉未初始化读之后，`didSave` 必须让诊断归零。
    只测「打开时有 1 条」是不够的 —— 重放缓存也会得到 1 条。
    """
    import shutil
    import tempfile
    work = tempfile.mkdtemp(prefix="lspsave_")
    try:
        target = os.path.join(work, "x.m")
        with io.open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(u"function y = x(a)\n% 反例语料\ny = a + b;\nend\n")
        c.init(work)
        u = _uri(target)
        c.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                "params": {"textDocument": {"uri": u, "languageId": "matlab",
                                            "version": 1, "text": "x=1;\n"}}})
        c.recv()                       # 第一条：空
        d0 = ((c.recv() or {}).get("params") or {}).get("diagnostics") or []
        _chk(len(d0) == 1, "打开时应有 1 条诊断，实际 %d" % len(d0))

        with io.open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(u"function y = x(a)\n% 反例语料\ny = a + 1;\nend\n")

        c.send({"jsonrpc": "2.0", "method": "textDocument/didSave",
                "params": {"textDocument": {"uri": u}}})
        after = c.recv() or {}
        d1 = ((after.get("params") or {}).get("diagnostics") or [])
        _chk(after.get("method") == "textDocument/publishDiagnostics",
             "didSave 后应推 publishDiagnostics")
        _chk(len(d1) == 0,
             "改掉未初始化读后应为 0 条，实际 %d（说明没重算）" % len(d1))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _field(c):
    """R201：`s.FIELD` 的跳转 —— 光标在读取处，跳到**第一个写入点**。

    ⚠ 这条也要**改/写文件**，所以同样用临时目录。判据是 `6 -> 3`：
    第 6 行 `y = s.name;` 的 `name` 跳到第 3 行 `s.name = 'x';`。

    **官方 IDE 做不到**：它没有跨文件字段解析，只能文本搜 `.name`，
    会把 `S.name`、`x.name`、注释里的 `.name` 全混在一起。
    """
    import shutil
    import tempfile
    work = tempfile.mkdtemp(prefix="lspfield_")
    try:
        target = os.path.join(work, "a.m")
        src = (u"function y = build(a)\n"
               u"% 结构体成员\n"
               u"s.name = 'x';\n"
               u"s.count = a;\n"
               u"y = 0;\n"
               u"y = s.name;\n"
               u"end\n")
        with io.open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(src.replace(u"\n", u"\r\n"))
        c.init(work)
        u = _uri(target)
        c.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                "params": {"textDocument": {"uri": u, "languageId": "matlab",
                                            "version": 1, "text": "x=1;\n"}}})
        c.recv()
        c.recv()
        # 第 6 行 `y = s.name;` 的 `name`（0-based line 5, char 6）
        c.send({"jsonrpc": "2.0", "id": 7, "method": "textDocument/definition",
                "params": {"textDocument": {"uri": u},
                           "position": {"line": 5, "character": 6}}})
        r = c.recv() or {}
        res = r.get("result") or []
        _chk(len(res) == 1, "field/one-target（实际 %d）" % len(res))
        if res:
            ln = res[0]["range"]["start"]["line"]
            # 第 3 行 `s.name = 'x';`（0-based 2）
            _chk(ln == 2, "field/jumps-to-first-write（实际 line=%d）" % ln)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _impact(c):
    """R217：`matlabc/impact` —— CodeLens 点击时走的自定义方法。

    判据用 `tests/sample_m` 的真实调用链：
      `b` ← `a` ← `switch_case`（入口）
    所以 `b` 必须有 1 个直接调用者 `a`，而 `switch_case` 必须 0 个。
    """
    c.init(CORPUS)
    c.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {
                "uri": _uri(os.path.join(CORPUS, "a.m")),
                "languageId": "matlab", "version": 1, "text": "x"}}})
    c.recv()
    c.recv()

    def call(name):
        c.send({"jsonrpc": "2.0", "id": 50, "method": "matlabc/impact",
                "params": {"name": name}})
        r = c.recv() or {}
        return r.get("result")

    info = call("b")
    _chk(isinstance(info, dict), "impact/b-returns-object")
    if isinstance(info, dict):
        _chk(info.get("total") == 2, "impact/b-total==2（b←a←switch_case）")
        direct = info.get("direct") or []
        _chk(len(direct) == 1 and direct[0].get("rel") == "a.m",
             "impact/b-direct-is-a.m")
        _chk(direct[0].get("line") == 1, "impact/b-direct-line==1")

    info2 = call("switch_case")
    _chk(isinstance(info2, dict) and info2.get("total") == 0,
         "impact/switch_case-total==0（它是入口）")
    _chk((info2 or {}).get("direct") == [], "impact/switch_case-no-direct")

    _chk(call("no_such_function_xyz") is None,
         "impact/missing-returns-null（不是空对象）")


def _tokens(c):
    """R219：语义 token 的类型分配。

    判据的核心不是「有多少个 token」，而是**同类是否同色**：
    `function y = a(x)` 的 `y` 是输出参数、`x` 是输入参数，
    它们在函数体内的每次出现都必须同为 `parameter` ——
    这正是用户反复抱怨的「同类东西两种颜色」。
    """
    TYPES = ["variable", "function", "property", "parameter"]

    def decode(uri, lines):
        c.send({"jsonrpc": "2.0", "id": 60,
                "method": "textDocument/semanticTokens/full",
                "params": {"textDocument": {"uri": uri}}})
        r = c.recv() or {}
        data = (r.get("result") or {}).get("data") or []
        out = []
        di = dc = 0
        for i in range(0, len(data) - 4, 5):
            dl, dch, ln, t, m = data[i:i + 5]
            di += dl
            dc = dch if dl else dc + dch
            out.append((di, dc, lines[di][dc:dc + ln] if di < len(lines) else "",
                        TYPES[t] if t < len(TYPES) else "?", m))
        return out

    path = os.path.join(CORPUS, "a.m")
    c.init(CORPUS)
    c.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": _uri(path),
                                        "languageId": "matlab",
                                        "version": 1, "text": "x"}}})
    c.recv()
    c.recv()
    lines = io.open(path, encoding="utf-8").read().splitlines()
    toks = decode(_uri(path), lines)

    _chk(bool(toks), "tokens/not-empty")
    # 第 1 行 `function y = a(x)`：y 输出、x 输入，都该是 parameter
    line1 = [(col, txt, typ) for (ln, col, txt, typ, m) in toks if ln == 0]
    ys = [ty for (c2, t, ty) in line1 if t == "y"]
    xs = [ty for (c2, t, ty) in line1 if t == "x"]
    _chk(ys == ["parameter"], "tokens/output-param-is-parameter（实际 %r）" % (ys,))
    _chk(xs == ["parameter"], "tokens/input-param-is-parameter（实际 %r）" % (xs,))
    # **同类同色**：函数体里每次出现的 x 都必须是 parameter
    allx = set(typ for (ln, col, txt, typ, m) in toks if txt == "x")
    _chk(allx == {"parameter"},
         "tokens/x-is-parameter-everywhere（实际 %r）" % (sorted(allx),))
    # 输出 y 在函数体里也不能变成 variable
    ally = set(typ for (ln, col, txt, typ, m) in toks if txt == "y")
    _chk(ally == {"parameter"},
         "tokens/y-stays-parameter（实际 %r）" % (sorted(ally),))
    # 函数定义处必须有 declaration 修饰位
    decl = [m for (ln, col, txt, typ, m) in toks if typ == "function" and m & 1]
    _chk(len(decl) == 3, "tokens/three-declarations（a.m 有 3 个函数，实际 %d）"
         % len(decl))
    # 空文件不许崩，且应为空数组
    empty = os.path.join(CORPUS, "empty_tokens.m")
    with io.open(empty, "w", encoding="utf-8", newline="") as fh:
        fh.write(u"")
    c.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": _uri(empty),
                                        "languageId": "matlab",
                                        "version": 1, "text": ""}}})
    c.recv()
    c.recv()
    _chk(decode(_uri(empty), []) == [], "tokens/empty-file-no-tokens")
    try:
        os.remove(empty)
    except OSError:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--diag", action="store_true")
    # 注意：不能用 `--def` —— argparse 会把它变成 `args.def`，而 `def` 是 Python 关键字。
    ap.add_argument("--definition", action="store_true")
    ap.add_argument("--ref", action="store_true")
    ap.add_argument("--hover", action="store_true")
    ap.add_argument("--symbol", action="store_true")
    ap.add_argument("--uninit", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--field", action="store_true")
    ap.add_argument("--impact", action="store_true")
    ap.add_argument("--tokens", action="store_true")
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
    elif args.hover:
        groups = [("hover", _hover)]
    elif args.symbol:
        groups = [("symbol", _symbols)]
    elif args.uninit:
        groups = [("uninit", _uninit)]
    elif args.field:
        groups = [("field", _field)]
    elif args.impact:
        groups = [("impact", _impact)]
    elif args.tokens:
        groups = [("tokens", _tokens)]
    elif args.save:
        groups = [("save", _save)]
    else:
        groups = [("diag", _diag), ("def", _def), ("ref", _ref),
                  ("hover", _hover), ("symbol", _symbols)]

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
