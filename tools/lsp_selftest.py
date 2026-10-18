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
import re
import subprocess
import sys
import time

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

        # R268：保存走的是增量（`prev` + `changed`）。第 30 道门只保证
        # files/edges 相同，**诊断是另一条产物** —— 这里单独验一次：
        # 增量算出的 facts 必须与全量逐条相同。
        sys.path.insert(0, ROOT)
        import matlabc_lsp as _L
        from analyzer.api import analyze as _an
        _full = _an(work)
        _inc = _an(work, prev=_full.files, changed={"x.m"})
        _chk(_L._facts_from_result(_full) == _L._facts_from_result(_inc),
             "save/incremental-facts-equal（增量诊断 %r != 全量 %r）"
             % (_L._facts_from_result(_inc), _L._facts_from_result(_full)))
        # 而「活对象」判据必须能区分增量可用与不可用 —— 缓存替身不许当 prev。
        _chk(_L._is_live_result(_full) is True, "save/is-live-for-analyzed")
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
        # R232：每个节点还要说清「被哪几行调用」。
        # `edges` 不带行号，行号来自 `call_sites` —— 这是能否
        # 「点一下就跳到调用处」的前提。
        cs = direct[0].get("call_sites") or []
        _chk(bool(cs), "impact/b-direct-has-call-sites（实际 %r）" % (cs,))
        _chk(all(isinstance(s.get("line"), int) and s["line"] > 0
                 and isinstance(s.get("rel"), str) and s["rel"] for s in cs),
             "impact/call-sites-carry-rel-and-1based-line（%r）" % (cs,))
        # **跨文件回归**（R256）：`a` 既被 a.m 里的 b 调用，也被
        # switch_case.m 调用。首版把所有调用行号都挂到节点自己的 rel 上，
        # 于是 `switch_case.m` 的那几行会被点去 `a.m` 的同号行 ——
        # 一个**看起来能用**的错误跳转，点下去不报错、只是去了错地方。
        _chk(any(s["rel"] != direct[0].get("rel") for s in cs),
             "impact/call-sites-keep-their-own-file（%r）" % (cs,))
        # 第 2 层：`switch_case` 调 `a`，`a` 调 `b`。
        # R227：QuickPick 原来只列第 1 层，分层算了却不返回 ——
        # 用户会以为"上游只有 a 一个"。
        others = info.get("others") or []
        _chk(len(others) == 1, "impact/b-others-count==1（实际 %d）" % len(others))
        if others:
            o = others[0]
            _chk(o.get("name") == "switch_case" and o.get("level") == 2,
                 "impact/b-others-level2（%r）" % (o,))
            # R261：入口是**服务端的事实**，不是客户端从「调用点列表为空」猜的。
            # 客户端那条推断会漏：`call_sites` 滤掉行号 0 的条目，而由 `edges`
            # 补进来、没有行号的调用者会被当成“不存在” → **有调用者的函数
            # 被标成入口**。
            _chk(o.get("is_entry") is True,
                 "impact/entry-flag-true-for-real-entry（%r）"
                 % (o.get("is_entry"),))
            _chk(direct[0].get("is_entry") is False,
                 "impact/entry-flag-false-for-called（%r）"
                 % (direct[0].get("is_entry"),))

    info2 = call("switch_case")
    _chk(isinstance(info2, dict) and info2.get("total") == 0,
         "impact/switch_case-total==0（它是入口）")
    _chk((info2 or {}).get("direct") == [], "impact/switch_case-no-direct")

    _chk(call("no_such_function_xyz") is None,
         "impact/missing-returns-null（不是空对象）")

    # ---- R262：把「edges 的每条边都能被 call_sites 覆盖」变成判据 ------
    # R261 修的是「有边但没有行号 ⇒ 被误标入口」。改完去查它到底可不可达：
    # 三个语料共 19 条边，**未覆盖 0 条** —— 也就是那个状态目前**不可达**，
    # 我上一轮写的「按构造可能」其实还高估了它。
    #
    # 与其留一句“防御性修正”，不如把这个不变量**测出来**：
    # 哪天这条红了，就说明 `_impact` 里那条补 `line=0` 的兜底真被用上了，
    # 那时才需要造一个能复现的语料 —— 而不是继续靠推断。
    try:
        sys.path.insert(0, ROOT)
        from analyzer.api import analyze as _analyze
        _res = _analyze(CORPUS, no_checks=True)
        _covered = set()
        for _mf in (_res.files or []):
            for _f in (getattr(_mf, "functions", None) or []):
                _ck = "%s:%s" % (getattr(_mf, "rel", ""),
                                 getattr(_f, "name", ""))
                for _s in (getattr(_f, "call_sites", None) or []):
                    _t = _s[3]
                    _covered.add((_ck, "%s:%s" % (
                        getattr(getattr(_t, "mfile", None), "rel", ""),
                        getattr(_t, "name", ""))))
        _edges = []
        for _e in (getattr(_res, "edges", None) or []):
            if isinstance(_e, dict):
                _c, _d = _e.get("caller"), _e.get("callee")
            else:
                _c, _d = _e[0], _e[1]
            _edges.append((_c, _d))
        # **防空集**：`edges` 为空时「未覆盖」必然为空，判据会永远绿。
        # 这类“空集合让断言失去意义”的坑，本仓已经踩过（R95 的产物核对）。
        _chk(len(_edges) > 0,
             "impact/edge-coverage-has-edges（实际 %d）" % (len(_edges),))
        _unc = [e for e in _edges if e not in _covered]
        _chk(not _unc,
             "impact/all-edges-carry-a-line（未覆盖 %r）" % (_unc[:3],))
    except Exception as _exc:            # 拿不到分析结果 → 缺输入，红
        _chk(False, "impact/edge-coverage-probe-failed（%r）" % (_exc,))

    # ---- 下游（R233）--------------------------------------------------
    # 关系图原来只画上游，而 CodeLens 上写着 `↓N 被调用` —— 那个数字
    # 点开什么都没有。这里钉住「下游也要给，且与 `--tree` 同集合」。
    infoa = call("a")
    down = (infoa or {}).get("down") or []
    dkeys = set("%s:%s" % (d["rel"], d["name"]) for d in down)
    _chk((infoa or {}).get("down_levels") == 2,
         "impact/a-down-levels==2（实际 %r）" % ((infoa or {}).get("down_levels"),))
    # `a` 调 `b`、`c`；`c` 调 `d`（跨文件）
    _chk(dkeys == {"a.m:b", "a.m:c", "d.m:d"},
         "impact/a-down-set（实际 %r）" % (sorted(dkeys),))
    lv1 = set(d["name"] for d in down if d.get("level") == 1)
    lv2 = set(d["name"] for d in down if d.get("level") == 2)
    _chk(lv1 == {"b", "c"}, "impact/a-down-level1（实际 %r）" % (sorted(lv1),))
    _chk(lv2 == {"d"}, "impact/a-down-level2（实际 %r）" % (sorted(lv2),))
    _chk(all("complexity" in d for d in down),
         "impact/down-nodes-carry-complexity")
    # 入口没有调用者，但**有**下游；叶子相反。两侧不能都空。
    _chk(((infoa or {}).get("down_total") or 0) == 3,
         "impact/a-down-total==3（实际 %r）" % ((infoa or {}).get("down_total"),))

    # 与 CLI `--tree` 对账：同一个正向可达集，两份实现不许分叉。
    try:
        p = subprocess.run([sys.executable, os.path.join(ROOT, "matlabc.py"),
                            CORPUS, "--tree", "a", "--tree-depth", "3"],
                           cwd=ROOT, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=120)
        out = (p.stdout or b"").decode("utf-8", "replace")
        seen = set(re.findall(r"[A-Za-z0-9_./\-]+\.m:[A-Za-z0-9_]+", out))
        # CLI 会把目标自身也打出来，去掉它再比
        seen.discard("a.m:a")
        _chk(seen == dkeys,
             "impact/down-matches-cli-tree（cli=%r lsp=%r）"
             % (sorted(seen), sorted(dkeys)))
    except Exception as exc:
        _chk(False, "impact/down-tree-compare-failed（%r）" % (exc,))

    # ---- 与 CLI 的 `--impact` 对账（R223）-----------------------------
    # 同一个算法现在有**两份实现**：`matlabc.py` 的 `_print_impact` 和
    # `matlabc_lsp.py` 的 `_impact`。两份实现迟早会分叉 —— 让它们互相
    # 对账，比"相信它们一致"可靠。
    try:
        # **不要在函数内 import subprocess**：Python 会把整个函数里出现的
        # `subprocess` 都当成局部名，于是同一函数中更靠前的用法直接
        # `UnboundLocalError`（R233 踩到，因为下游对账插在它前面）。
        # 顶层已经 import 过了。
        p = subprocess.run([sys.executable, os.path.join(ROOT, "matlabc.py"),
                            CORPUS, "--impact", "b"],
                           cwd=ROOT, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=120)
        out = (p.stdout or b"").decode("utf-8", "replace")
        import re as _re
        m1 = _re.search(r"直接调用者（1 层）\s+(\d+)", out)
        m2 = _re.search(r"间接调用者（2 层及以上）\s+(\d+)", out)
        _chk(m1 is not None and m2 is not None,
             "impact/cli-output-parseable（%r）" % (out[:80],))
        if m1 and m2 and isinstance(info, dict):
            cli_total = int(m1.group(1)) + int(m2.group(1))
            _chk(cli_total == info.get("total"),
                 "impact/cli-matches-lsp（cli=%d lsp=%r）"
                 % (cli_total, info.get("total")))
    except Exception as exc:
        _chk(False, "impact/cli-compare-failed（%r）" % (exc,))


def _tokens(c):
    """R219：语义 token 的类型分配。

    判据的核心不是「有多少个 token」，而是**同类是否同色**：
    `function y = a(x)` 的 `y` 是输出参数、`x` 是输入参数，
    它们在函数体内的每次出现都必须同为 `parameter` ——
    这正是用户反复抱怨的「同类东西两种颜色」。
    """
    TYPES = ["variable", "function", "property", "parameter"]

    def decode(uri, lines, client=None):
        cc = client or c
        cc.send({"jsonrpc": "2.0", "id": 60,
                 "method": "textDocument/semanticTokens/full",
                 "params": {"textDocument": {"uri": uri}}})
        r = cc.recv() or {}
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

    # ---- 多行签名（R220）------------------------------------------
    # `function [alpha, beta] = ...` 换行写时，解析器曾把函数名解析成空，
    # 于是参数一个都标不出来。这一组钉的是「跨 `...` 续行的签名」。
    sig_root = os.path.join(ROOT, "tests", "sample_sig")
    if os.path.isdir(sig_root):
        c2 = Client()
        try:
            sig_file = os.path.join(sig_root, "multi.m")
            c2.init(sig_root)
            c2.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                     "params": {"textDocument": {
                         "uri": _uri(sig_file), "languageId": "matlab",
                         "version": 1, "text": "x"}}})
            c2.recv()
            c2.recv()
            slines = io.open(sig_file, encoding="utf-8").read().splitlines()
            stoks = decode(_uri(sig_file), slines, client=c2)
            typ = {}
            for (ln, col, txt, t, m) in stoks:
                typ.setdefault(txt, set()).add(t)
            _chk(typ.get("first") == {"parameter"},
                 "tokens/multi-line-input-param（实际 %r）" % (typ.get("first"),))
            _chk(typ.get("third") == {"parameter"},
                 "tokens/multi-line-third-param（实际 %r）" % (typ.get("third"),))
            _chk(typ.get("alpha") == {"parameter"},
                 "tokens/multi-line-output-param（实际 %r）" % (typ.get("alpha"),))
            _chk(typ.get("multi") == {"function"},
                 "tokens/multi-line-function-name（实际 %r）" % (typ.get("multi"),))
            # 函数名在签名的第 2 行，也必须拿到 declaration ——
            # 否则它和单行函数在「定义处」这件事上不一致（R221）。
            multi_decl = any((m & 1) for (ln, col, txt, t, m) in stoks
                             if txt == "multi")
            _chk(multi_decl, "tokens/multi-line-declaration")
        finally:
            c2.close()


def _struct(c):
    """R228：结构体**变量**与**字段**的两种跳转。

    `tests/sample_struct/a.m`：
        3: s.name = 'x';      ← 变量 s 与字段 name 都定义在这里
        5: y = s.name;        ← 光标放这里

    两者都必须跳到第 3 行，但**语义不同**：
      - 光标在 `s` 上 → 「这个变量哪来的」
      - 光标在 `name` 上 → 「这个字段哪定义」
    """
    root = os.path.join(ROOT, "tests", "sample_struct")
    if not os.path.isdir(root):
        _chk(False, "struct/缺语料 tests/sample_struct")
        return
    c.init(root)
    path = os.path.join(root, "a.m")
    c.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": _uri(path),
                                        "languageId": "matlab",
                                        "version": 1, "text": "x"}}})
    c.recv()
    c.recv()

    def defn(line, char):
        c.send({"jsonrpc": "2.0", "id": 70,
                "method": "textDocument/definition",
                "params": {"textDocument": {"uri": _uri(path)},
                           "position": {"line": line, "character": char}}})
        r = c.recv() or {}
        return r.get("result") or []

    # 第 5 行 `y = s.name;`：s 在第 4 列
    r = defn(4, 4)
    _chk(len(r) == 1 and r[0]["range"]["start"]["line"] == 2,
         "struct/variable-s-jumps-to-first-assign（%r）" % (r,))
    # 同一行第 6 列是 `name`
    r2 = defn(4, 6)
    _chk(len(r2) == 1 and r2[0]["range"]["start"]["line"] == 2,
         "struct/field-jumps-to-write（%r）" % (r2,))
    # 3 列是 `.` —— 不是标识符，不该崩也不该乱跳
    r3 = defn(4, 5)
    _chk(r3 == [] or (len(r3) == 1 and r3[0]["range"]["start"]["line"] == 2),
         "struct/dot-position-does-not-crash（%r）" % (r3,))

    # ---- R235：字段上按 F12 找不到定义，但**必须解释** ----------------
    # 这就是用户报的现象：`lb(...)` 看着像调用、CodeLens 上有数字，
    # 可 `lb` 是字段。跳不过去是对的，沉默是错的。
    c.send({"jsonrpc": "2.0", "id": 71, "method": "textDocument/hover",
            "params": {"textDocument": {"uri": _uri(path)},
                       "position": {"line": 4, "character": 6}}})
    rh = c.recv() or {}
    body = (((rh.get("result") or {}).get("contents") or {})
            .get("value") or "")
    _chk("这是字段" in body,
         "struct/explains-field-not-function（%r）" % (body[:100],))
    _chk("首次写入" in body, "struct/points-to-first-write")

    # ---- 缓存必须带 field_access（R233）--------------------------------
    # 这一条不是"锦上添花"：`_field_index` 在缓存重建的 `SimpleNamespace`
    # 上会 `AttributeError`，于是结构体跳转**静默返回 []**。
    # 「冷启动能用、重启后不能用」是最难查的一类 —— 只能靠查产物形状。
    cache = os.path.join(root, ".matlabc_lsp_cache.json")
    deadline = time.time() + 30
    while time.time() < deadline and not os.path.isfile(cache):
        time.sleep(0.2)
    _chk(os.path.isfile(cache), "struct/cache-written")
    if os.path.isfile(cache):
        try:
            d = json.load(io.open(cache, encoding="utf-8"))
        except Exception:
            d = {}
        _chk(d.get("v") == 3, "struct/cache-schema-v3（实际 %r）" % (d.get("v"),))
        fa = d.get("field_access") or {}
        _chk("name" in fa, "struct/cache-has-field-access（keys=%r）" % (list(fa)[:5],))
        # 缓存的函数记录必须带 `external_calls` —— R235 的 hover 解释分支
        # 靠它；漏了就是「冷启动有解释、重启后沉默」。
        fns = ((d.get("files") or [{}])[0].get("functions") or [{}])
        _chk("external_calls" in (fns[0] if fns else {}),
             "struct/cache-has-external-calls（keys=%r）"
             % (sorted((fns[0] if fns else {}).keys()),))

        # ---- R237：键集合必须与唯一清单**逐字**相同 -----------------
        # 前四次漏字段（signature / call_sites / field_access /
        # external_calls）都是因为保存与恢复是两份手写清单。
        # 现在清单只有一份 `_CACHED_FN_FIELDS`，这条判据直接比对产物：
        #   · 清单加了字段但保存/恢复没跟上 → 产物缺键 → 红
        #   · 保存时多写了清单外的键 → 产物多键 → 红
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        try:
            import matlabc_lsp as _L
            want = set(getattr(_L, "_CACHED_FN_FIELDS", ()))
        except Exception:
            want = set()
        _chk(bool(want), "struct/cache-field-list-declared")
        if want:
            got = set((fns[0] if fns else {}).keys())
            _chk(got == want,
                 "struct/cache-keys-match-list（缺 %r / 多 %r）"
                 % (sorted(want - got), sorted(got - want)))

    # ---- R237：**在同一轮里模拟一次「重启」** --------------------------
    # 上面的检查都发生在"刚分析完"的进程里；而所有缓存 bug 的症状都是
    # 「冷启动对、重启后哑」。所以这里换一个**新进程**、命中同一份缓存、
    # 再跳一次 —— 这才是用户第二天打开项目时走的那条路。
    if os.path.isfile(cache):
        c2 = Client()
        try:
            c2.init(root)
            c2.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                     "params": {"textDocument": {"uri": _uri(path),
                                                 "languageId": "matlab",
                                                 "version": 1, "text": "x"}}})
            c2.recv()
            c2.recv()
            c2.send({"jsonrpc": "2.0", "id": 72,
                     "method": "textDocument/definition",
                     "params": {"textDocument": {"uri": _uri(path)},
                                "position": {"line": 4, "character": 4}}})
            r = c2.recv() or {}
            res = r.get("result") or []
            _chk(len(res) == 1 and res[0]["range"]["start"]["line"] == 2,
                 "struct/warm-cache-still-jumps（%r）" % (res,))
            c2.send({"jsonrpc": "2.0", "id": 73, "method": "textDocument/hover",
                     "params": {"textDocument": {"uri": _uri(path)},
                                "position": {"line": 4, "character": 6}}})
            rh = c2.recv() or {}
            body = (((rh.get("result") or {}).get("contents") or {})
                    .get("value") or "")
            _chk("这是字段" in body,
                 "struct/warm-cache-explains-field（%r）" % (body[:80],))
        finally:
            c2.close()



def _doc(c):
    """R231：悬停里的参数表。

    老代码里大量函数在头部注释写了 `% Input:` 表格，解析器早就把它们
    结构化成了 `header["inputs"]`，但悬停从来没显示 —— 算了却不用。

    两条判据缺一不可：
      - 有参数表时**必须**显示（否则等于没做）
      - 没有参数表时**不许**显示空表（否则每个函数都拖一片空白）
    """
    root = os.path.join(ROOT, "tests", "sample_doc")
    if not os.path.isdir(root):
        _chk(False, "doc/缺语料 tests/sample_doc")
        return
    c.init(root)
    path = os.path.join(root, "documented.m")
    c.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": _uri(path),
                                        "languageId": "matlab",
                                        "version": 1, "text": "x"}}})
    c.recv()
    c.recv()

    def hover_at(line, char):
        c.send({"jsonrpc": "2.0", "id": 80, "method": "textDocument/hover",
                "params": {"textDocument": {"uri": _uri(path)},
                           "position": {"line": line, "character": char}}})
        r = c.recv() or {}
        res = r.get("result")
        return ((res or {}).get("contents") or {}).get("value") or ""

    body = hover_at(0, 15)          # documented
    _chk("| 参数 |" in body, "doc/param-table-present")
    _chk("`x`" in body and "double" in body and "底数" in body,
         "doc/param-row-rendered（%r）" % (body[:120],))
    _chk("`n`" in body and "指数" in body, "doc/second-param")
    _chk("**输出**" in body and "`y`" in body, "doc/output-table")

    body2 = hover_at(8, 15)         # no_doc（第 9 行 function z = no_doc）
    if body2:
        _chk("| 参数 |" not in body2,
             "doc/no-empty-table（%r）" % (body2[:120],))

    # ---- R271：悬停到**参数名**上，要被认成参数，不是「查不到的函数」 ----
    # 以前 `x` 会一路落到「本库内没有名为 x 的函数」—— 而它明明就写在
    # 眼前这个函数的签名里。**那不是查不到，是问错了问题。**
    body3 = hover_at(7, 4)          # documented 的 body：`y = x .^ n;` 的 x
    _chk("**参数**" in body3 and "`double`" in body3,
         "doc/param-hover-typed（%r）" % (body3[:80],))
    # 没有头部参数表的函数：照样认得出是参数，但**如实说没有类型说明**。
    body4 = hover_at(12, 4)         # no_doc 的 body：`z = a + b;` 的 a
    _chk("**参数**" in body4 and "没有类型说明" in body4,
         "doc/param-hover-without-type（%r）" % (body4[:80],))

    # ---- R272：兜底不许沉默 -------------------------------------------
    # 既不是函数、不是字段、不是参数、也不在外部调用表里时，以前 `return None`
    # —— 界面一片安静，用户分不清「我拼错了」还是「扩展坏了」。
    body5 = hover_at(7, 0)          # documented 的 body：`y = x .^ n;` 的 y
    _chk("局部变量" in body5,
         "doc/local-variable-hover（%r）" % (body5[:80],))

    # 另一份语料：注释里提到的、从不赋值也不被调用的名字
    c.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": _uri(
                os.path.join(root, "unknown_ref.m")),
                "languageId": "matlab", "version": 1, "text": "x"}}})
    c.recv()
    c.recv()
    c.send({"jsonrpc": "2.0", "id": 86, "method": "textDocument/hover",
            "params": {"textDocument": {"uri": _uri(
                os.path.join(root, "unknown_ref.m"))},
                "position": {"line": 1, "character": 20}}})
    r6 = c.recv() or {}
    body6 = (((r6.get("result") or {}).get("contents") or {})
             .get("value") or "")
    _chk("不是函数" in body6 and "没有被赋值" in body6,
         "doc/unknown-identifier-explained（%r）" % (body6[:80],))

    # 中文不该被当成标识符：否则悬停注释里的词会输出
    # 「`反例语料` 不是函数」—— 一句正确但毫无意义的话。
    sys.path.insert(0, ROOT)
    import matlabc_lsp as _L2
    _chk(_L2._ident_at([u"% 反例语料：下面提到 zzz_ghost"], 0, 6) is None,
         "doc/cjk-is-not-an-identifier")

    # ---- R235：**本库没有定义时不许沉默** -------------------------------
    # 用户报的「显示有调用、却找不到函数」：`some_toolbox_fn(...)` 看着
    # 像调用，但本库和内置表里都没有它。以前 hover 返回 null、F12 返回
    # 空数组，用户以为扩展坏了。
    ext = os.path.join(root, "ext_call.m")
    c.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": _uri(ext),
                                        "languageId": "matlab",
                                        "version": 1, "text": "x"}}})
    c.recv()
    c.recv()
    c.send({"jsonrpc": "2.0", "id": 81, "method": "textDocument/hover",
            "params": {"textDocument": {"uri": _uri(ext)},
                       "position": {"line": 3, "character": 8}}})
    r_ext = c.recv() or {}
    body_ext = (((r_ext.get("result") or {}).get("contents") or {})
                .get("value") or "")
    _chk("本库内没有名为" in body_ext,
         "doc/explains-missing-function（%r）" % (body_ext[:120],))
    _chk("some_toolbox_fn" in body_ext, "doc/names-the-identifier")

    # R244：悬停在**函数自己**身上时，也要说清它有几次调用跳不动。
    c.send({"jsonrpc": "2.0", "id": 82, "method": "textDocument/hover",
            "params": {"textDocument": {"uri": _uri(ext)},
                       "position": {"line": 0, "character": 15}}})
    r_fn = c.recv() or {}
    body_fn = (((r_fn.get("result") or {}).get("contents") or {})
               .get("value") or "")
    _chk("无法定位" in body_fn,
         "doc/function-hover-reports-unresolved（%r）" % (body_fn[:140],))


def _lens(c):
    """R236：CodeLens —— 它一直是主推功能，却**一条判据都没有**。

    这里钉三件事：
      L1 每个函数恰好一条（不能漏、不能重复）
      L2 调用数来自 `edges`，与真实链一致
      L3 **`unresolved` 必须报出来**：`↓0` 不等于"不调用任何东西"，
         函数体里可能有一堆解析不到的 `foo(...)`，而用户会在那些上
         按 F12 得到「未找到」。
    """
    c.init(CORPUS)
    c.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {
                "uri": _uri(os.path.join(CORPUS, "a.m")),
                "languageId": "matlab", "version": 1, "text": "x"}}})
    c.recv()
    c.recv()
    c.send({"jsonrpc": "2.0", "id": 90, "method": "textDocument/codeLens",
            "params": {"textDocument": {"uri": _uri(os.path.join(CORPUS, "a.m"))}}})
    r = c.recv() or {}
    lenses = r.get("result") or []
    # a.m 有三个函数：a / b / c
    _chk(len(lenses) == 3, "lens/one-per-function（实际 %d）" % len(lenses))
    by = {}
    for l in lenses:
        d = l.get("data") or {}
        by[d.get("name")] = d
        # L1b：锚点必须在函数定义行（0-based）
        if d.get("name") in ("a", "b", "c"):
            _chk(l["range"]["start"]["line"] >= 0, "lens/range-nonneg")
    _chk(set(by) == {"a", "b", "c"}, "lens/all-functions（实际 %r）"
         % (sorted(by),))
    # `a` 有两个调用者：`switch_case` 和 `b`（b 回调 a，这是语料里
    # 刻意留的环）。**第一版写 1 是错的** —— 而它错得很有价值：
    # 如果哪天环上少了一条边，这里就会掉到 1。
    _chk((by.get("a") or {}).get("callers") == 2,
         "lens/a-callers==2（switch_case + b 回调，实际 %r）"
         % ((by.get("a") or {}).get("callers"),))
    _chk((by.get("a") or {}).get("callees") == 2,
         "lens/a-callees==2（实际 %r）" % ((by.get("a") or {}).get("callees"),))
    _chk("unresolved" in (by.get("a") or {}), "lens/has-unresolved-field")

    # L3：ext_call 调了本库没有的 `some_toolbox_fn` —— ↓0 但 unresolved 1
    root2 = os.path.join(ROOT, "tests", "sample_doc")
    if os.path.isdir(root2):
        c2 = Client()
        try:
            f2 = os.path.join(root2, "ext_call.m")
            c2.init(root2)
            c2.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                     "params": {"textDocument": {"uri": _uri(f2),
                                                 "languageId": "matlab",
                                                 "version": 1, "text": "x"}}})
            c2.recv()
            c2.recv()
            c2.send({"jsonrpc": "2.0", "id": 91,
                     "method": "textDocument/codeLens",
                     "params": {"textDocument": {"uri": _uri(f2)}}})
            rr = c2.recv() or {}
            ls = rr.get("result") or []
            _chk(len(ls) == 1, "lens/ext-call-one（实际 %d）" % len(ls))
            if ls:
                d = ls[0].get("data") or {}
                _chk(d.get("callees") == 0,
                     "lens/ext-callees==0（实际 %r）" % (d.get("callees"),))
                _chk(d.get("unresolved") == 1,
                     "lens/ext-unresolved==1（实际 %r）" % (d.get("unresolved"),))

            # R243：关系图的目标节点也要带同一个数 —— 否则图上写
            # 「叶子」（不调用任何东西），而它其实调用了一个跳不动的名字。
            c2.send({"jsonrpc": "2.0", "id": 92, "method": "matlabc/impact",
                     "params": {"name": "ext_call"}})
            ri = c2.recv() or {}
            inf = ri.get("result") or {}
            _chk(inf.get("unresolved") == 1,
                 "impact/target-unresolved==1（实际 %r）"
                 % (inf.get("unresolved"),))
            # R255：只给数量等于给了一个没有内容的数字。名字必须带出来，
            # 否则用户看到「另 1 未解析」也不知道该去查谁。
            _chk(inf.get("unresolved_names") == ["some_toolbox_fn"],
                 "impact/unresolved-names（实际 %r）"
                 % (inf.get("unresolved_names"),))
            _chk(inf.get("unresolved_names_total") == 1,
                 "impact/names-total==1（实际 %r）"
                 % (inf.get("unresolved_names_total"),))

            # R257：**截断必须可见**。`many_ext` 有 7 个不同的未解析名字，
            # 列表只给 5 个 —— 而 `unresolved_names_total` 必须说 7。
            # 只报 5 个而不报总数，等于让读者以为一共就 5 个。
            c2.send({"jsonrpc": "2.0", "id": 93, "method": "matlabc/impact",
                     "params": {"name": "many_ext"}})
            rm = c2.recv() or {}
            im = rm.get("result") or {}
            _chk(len(im.get("unresolved_names") or []) == 5,
                 "impact/names-capped-at-5（实际 %r）"
                 % (len(im.get("unresolved_names") or []),))
            _chk(im.get("unresolved_names_total") == 7,
                 "impact/names-total-reports-7（实际 %r）"
                 % (im.get("unresolved_names_total"),))
            _chk(im.get("unresolved") == 7,
                 "impact/many-ext-unresolved==7（实际 %r）"
                 % (im.get("unresolved"),))

            # R258：**服务端不许截断调用点**（展示层才截断，否则
            # 「另 N 处」算不出来）。`step` 被 `top` 在 9 个不同行上调用。
            #
            # 顺带记录一个语义事实：`call_sites` **每个语句只记一次** ——
            # `step(a)+step(a)+step(a)` 是一个语句，只记 1 处；用 `...`
            # 续行的多行也是同一语句，同样只记 1 处。所以图中
            # 「调用自 N」说的是**语句数**，不是**调用次数**。
            # （第一版注释写成「按行去重」，不准确 —— 行与语句不是一回事。）
            c2.send({"jsonrpc": "2.0", "id": 94, "method": "matlabc/impact",
                     "params": {"name": "leaf"}})
            rl = c2.recv() or {}
            il = ((rl.get("result") or {}).get("direct") or [{}])[0]
            _chk(len(il.get("call_sites") or []) == 9,
                 "impact/upstream-call-sites-complete（实际 %r）"
                 % (len(il.get("call_sites") or []),))
            _chk(all(s.get("rel") == "many_calls.m"
                     for s in (il.get("call_sites") or [])),
                 "impact/call-sites-per-statement（语句数，非调用次数）")

            # R260：节点带参数摘要。**两条来源都要验**，因为它们覆盖
            # 不同的代码风格：
            #   ① 函数头写了 `% Input:` 表格 → 用表格（documented.m）
            #   ② 没有注释块的老代码 → 回退到签名（many_calls.m）
            # 只验 ① 的话，绝大多数函数其实是空的，而判据照样绿。
            _chk(il.get("params") == ["a"] and il.get("params_total") == 1,
                 "impact/upstream-params-from-signature（%r/%r）"
                 % (il.get("params"), il.get("params_total")))
            c2.send({"jsonrpc": "2.0", "id": 95, "method": "matlabc/impact",
                     "params": {"name": "documented"}})
            rd = c2.recv() or {}
            idd = rd.get("result") or {}
            _chk(idd.get("params") == ["x", "n"]
                 and idd.get("params_total") == 2,
                 "impact/target-params-from-header（%r/%r）"
                 % (idd.get("params"), idd.get("params_total")))
            # R263：类型只在**有**的地方给。注释表有类型列，签名没有 ——
            # 两条来源各验一次，否则「签名路径返回空类型」这件事没人守。
            _chk(idd.get("param_types") == ["double", "int"],
                 "impact/target-param-types-from-header（%r）"
                 % (idd.get("param_types"),))
            _chk(il.get("param_types") == [""],
                 "impact/signature-params-have-no-type（%r）"
                 % (il.get("param_types"),))
            _chk(inf.get("down") == [],
                 "impact/no-fake-downstream（down 必须为空：它没有可跳的调用）")
        finally:
            c2.close()


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
    ap.add_argument("--struct", action="store_true")
    ap.add_argument("--doc", action="store_true")
    ap.add_argument("--lens", action="store_true")
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
    elif args.struct:
        groups = [("struct", _struct)]
    elif args.doc:
        groups = [("doc", _doc)]
    elif args.lens:
        groups = [("lens", _lens)]
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
