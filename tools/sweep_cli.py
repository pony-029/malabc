# -*- coding: utf-8 -*-
"""全场景扫测：67 个检查点，覆盖 CLI 开关 / 畸形输入 / 联动 / 幂等。

    python tools/sweep_cli.py                 # 全部（约 25 秒）
    python tools/sweep_cli.py --only 1        # 仅第 1 组（开关）
    python tools/sweep_cli.py --only 2        # 仅第 2 组（畸形输入与编码）
    python tools/sweep_cli.py --only 3        # 仅第 3 组（联动与幂等）
    python tools/sweep_cli.py --selftest      # 判据自身自证
    python tools/sweep_cli.py --help

退出码：0 全过 / 1 有失败 / 2 缺输入或参数错。

━━ 三条结构性防护（来自 R155–R158 的 9 次判据错）━━━━━━━━━━━━━━━━━━━
这三条不是风格问题，是**九次误判的直接产物**：

1. `shape_of()` 先断言字段存在，再取值。
   `d.get("file")` 对不存在的键返回 `None`，判据会**静默通过** ——
   实际字段是 `rel`（R156 实测）。

2. `EMPTY_INPUT_RC = 1` 是**常量**，不在每个判据里重新假设。
   我在第一轮与第三轮**各错了一次**同一个约定（以为空目录 rc=0）。

3. `canon()` 固定剔除 `generated_at` 与 `stats.cache_*`。
   前者每次都变；后者是**本次运行的缓存状态**（冷热两次必然不同，
   R158 误判成 bug）。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MATLABC = os.path.join(ROOT, "matlabc.py")
CORPUS = os.path.join(ROOT, "tests", "sample_m")
PY = sys.executable

#: 「目录里没有目标文件」时 CLI 的退出码。
#: 实测：matlab / py / js / asm 都是 1，**只有 `--lang c` 是 0**（已知不一致）。
EMPTY_INPUT_RC = 1
#: 运行态字段：不属于"分析结果"，比较时必须剔除。
VOLATILE_KEYS = ("generated_at",)
VOLATILE_STATS = ("cache_hits", "cache_misses", "cache_total", "cache_hit_rate")

_RESULT = {"bad": 0, "good": 0, "fails": []}


def _chk(cond, name, detail=""):
    if cond:
        _RESULT["good"] += 1
    else:
        _RESULT["bad"] += 1
        _RESULT["fails"].append("%s %s" % (name, detail))
        print("  [FAIL] %-36s %s" % (name, detail))


def shape_of(obj):
    """字段名清单（或类型名）。**取字段前必须先查它。**"""
    if isinstance(obj, dict):
        return sorted(obj.keys())
    return type(obj).__name__


def need(obj, field, name):
    """断言 `field` 存在，否则把真实 keys 打出来 —— 而不是静默取到 None。"""
    ok = isinstance(obj, dict) and field in obj
    _chk(ok, "%s/has-%s" % (name, field), "keys=%r" % (shape_of(obj),))
    return ok


def canon(d):
    """去掉**每次都变**和**只反映运行状态**的字段后，做规范化序列化。"""
    d = dict(d)
    for k in VOLATILE_KEYS:
        d.pop(k, None)
    if isinstance(d.get("stats"), dict):
        d["stats"] = dict((k, v) for k, v in d["stats"].items()
                          if k not in VOLATILE_STATS)
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


def run(args, timeout=300):
    # `stdin=DEVNULL` 是硬要求（check_subprocess_hygiene 的 S1）：
    # 不设它会继承调用方的 stdin 句柄，本仓有过因此挂死的真实案例。
    p = subprocess.run([PY, MATLABC] + list(args), cwd=ROOT,
                       stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=timeout)
    return (p.returncode,
            (p.stdout or b"").decode("utf-8", "replace"),
            (p.stderr or b"").decode("utf-8", "replace"))


def load(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_text(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def write_bytes(path, data):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "wb") as fh:
        fh.write(data)


# --------------------------------------------------------------------------
# 组 1：CLI 开关
# --------------------------------------------------------------------------
def group1(tmp):
    o = lambda n: os.path.join(tmp, n)
    rc, _, se = run([CORPUS, "--json", o("a.json"), "--sarif-no-persist"])
    _chk(rc == 0, "json/default", "rc=%d %s" % (rc, se.strip()[:50]))
    if rc == 0:
        d = load(o("a.json"))
        if need(d, "heuristics", "json"):
            _chk(len(d["heuristics"]) == 5, "json/heuristics-5",
                 "got %d" % len(d["heuristics"]))

    rc, _, _ = run([CORPUS, "--json", o("b.json"), "--json-compact",
                    "--sarif-no-persist"])
    _chk(rc == 0 and os.path.getsize(o("b.json")) < os.path.getsize(o("a.json")),
        "json/compact-smaller")

    rc, _, _ = run([CORPUS, "--json", o("c.json"), "--no-checks",
                    "--sarif-no-persist"])
    if rc == 0:
        _chk(len(load(o("c.json")).get("heuristics") or []) == 5,
             "json/no-checks-keeps-heuristics")

    rc, _, _ = run([CORPUS, "--json", o("d.json"), "--reproducible",
                    "--sarif-no-persist"])
    if rc == 0:
        _chk(load(o("d.json")).get("generated_at") == "",
             "json/reproducible-blank")

    for flag, ext, minb in (("--xml", "xml", 1000), ("--mermaid", "mmd", 100),
                            ("--dot", "dot", 100), ("--sarif", "sarif", 100)):
        rc, _, _ = run([CORPUS, flag, o("x." + ext), "--sarif-no-persist"])
        _chk(rc == 0 and os.path.getsize(o("x." + ext)) > minb,
             "out/%s" % flag.lstrip("-"), "rc=%d" % rc)

    rc, _, _ = run([CORPUS, "--browse", o("site")])
    n = sum(len(fs) for _, _, fs in os.walk(o("site"))) if rc == 0 else 0
    _chk(rc == 0 and n >= 190, "out/browse", "files=%d" % n)

    # 四个语言分支的空目录（唯一的产品不一致就在这里，如实断言当前行为）
    empty = os.path.join(tmp, "empty")
    os.makedirs(empty)
    for lang in ("py", "js", "asm"):
        rc, _, se = run([empty, "--lang", lang, "--json", o(lang + ".json")])
        _chk(rc == EMPTY_INPUT_RC, "lang/%s-empty" % lang,
             "rc=%d（期望 %d）%s" % (rc, EMPTY_INPUT_RC, se.strip()[:40]))
    # R165 之前这里是唯一的例外（rc=0）；修好后四个分支统一为 EMPTY_INPUT_RC。
    rc, _, se = run([empty, "--lang", "c", "--json", o("c.json")])
    _chk(rc == EMPTY_INPUT_RC, "lang/c-empty-matches-others",
         "rc=%d（期望 %d）%s" % (rc, EMPTY_INPUT_RC, se.strip()[:40]))

    rc, so, _ = run([CORPUS, "--help"])
    _chk(rc == 0 and "usage" in so.lower(), "edge/help")


# --------------------------------------------------------------------------
# 组 2：畸形输入 / 编码 / 规模
# --------------------------------------------------------------------------
def group2(tmp):
    odd = os.path.join(tmp, "odd")
    write_text(os.path.join(odd, "empty.m"), u"")
    write_text(os.path.join(odd, "only_comment.m"), u"% 只有注释\n")
    write_text(os.path.join(odd, "broken.m"), u"function y = broken(a\n y = a;\nend\n")
    write_text(os.path.join(odd, u"\u4e2d\u6587\u540d.m"),
               u"function y = f(a)\n% d\ny = a;\nend\n")
    write_text(os.path.join(odd, "with space.m"),
               u"function y = g(a)\n% d\ny = a;\nend\n")
    rc, _, se = run([odd, "--json", os.path.join(tmp, "odd.json"),
                     "--sarif-no-persist"])
    _chk(rc == 0, "odd/dont-crash", "rc=%d %s" % (rc, se.strip()[:50]))
    if rc == 0:
        d = load(os.path.join(tmp, "odd.json"))
        files = d.get("files") or [{}]
        if need(files[0], "rel", "odd/files"):
            rels = [f.get("rel") for f in files]
            _chk(any(u"\u4e2d\u6587" in (r or "") for r in rels),
                 "odd/chinese-filename")
            _chk(any("space" in (r or "") for r in rels), "odd/space-filename")

    # 规模
    big = os.path.join(tmp, "big")
    body = "".join("  y = y + %d;\n" % i for i in range(5000))
    write_text(os.path.join(big, "huge.m"),
               "function y = huge(x)\n% d\n  y = x;\n" + body + "end\n")
    rc, _, se = run([big, "--json", os.path.join(tmp, "big.json"),
                     "--sarif-no-persist"])
    _chk(rc == 0, "scale/5000-lines", "rc=%d %s" % (rc, se.strip()[:50]))

    # 深嵌套
    deep = os.path.join(tmp, "deep")
    p = deep
    for i in range(8):
        p = os.path.join(p, "d%d" % i)
    write_text(os.path.join(p, "leaf.m"), "function y = leaf(x)\n% d\ny = x;\nend\n")
    rc, _, _ = run([deep, "--json", os.path.join(tmp, "deep.json"),
                    "--sarif-no-persist"])
    _chk(rc == 0, "scale/deep-nesting")

    # 编码：BOM / CRLF / LF / 混合 / 中文
    enc = os.path.join(tmp, "enc")
    write_bytes(os.path.join(enc, "bom.m"),
                b"\xef\xbb\xbffunction y = bom(x)\r\n% d\r\ny = x;\r\nend\r\n")
    write_text(os.path.join(enc, "crlf.m"),
               "function y = crlf(x)\r\n% d\r\ny = x;\r\nend\r\n")
    write_text(os.path.join(enc, "lf.m"), "function y = lf(x)\n% d\ny = x;\nend\n")
    write_text(os.path.join(enc, "mix.m"),
               "function y = mix(x)\r\n% d\n\ty = x;\r\nend\n")
    write_text(os.path.join(enc, "u.m"),
               u"function y = u(x)\n% \u4e2d\u6587\ny = x;\nend\n")
    rc, _, se = run([enc, "--json", os.path.join(tmp, "enc.json"),
                     "--sarif-no-persist"])
    _chk(rc == 0, "encoding/all-parse", "rc=%d %s" % (rc, se.strip()[:50]))
    if rc == 0:
        st = load(os.path.join(tmp, "enc.json")).get("stats") or {}
        _chk(st.get("files") == 5, "encoding/five", "got %r" % (st.get("files"),))

    # schema
    rc, _, _ = run([CORPUS, "--json", os.path.join(tmp, "s.json"),
                    "--sarif-no-persist"])
    if rc == 0:
        s = load(os.path.join(tmp, "s.json"))
        must = ["version", "stats", "files", "edges", "heuristics",
                "doc_todos", "uninitialized", "dead_code"]
        missing = [k for k in must if k not in s]
        _chk(not missing, "schema/required", "missing=%r" % (missing,))


# --------------------------------------------------------------------------
# 组 3：联动与幂等
# --------------------------------------------------------------------------
def group3(tmp):
    o = lambda n: os.path.join(tmp, n)
    rc, _, se = run([CORPUS, "--json", o("all.json"), "--json-compact",
                     "--no-checks", "--reproducible", "--sarif-no-persist"])
    _chk(rc == 0, "combo/four-flags", "rc=%d %s" % (rc, se.strip()[:50]))
    if rc == 0:
        d = load(o("all.json"))
        _chk(len(d.get("heuristics") or []) == 5, "combo/heuristics-5")
        _chk(d.get("generated_at") == "", "combo/blank-timestamp")

    rc, _, _ = run([CORPUS, "--browse", o("site"), "--no-checks"])
    n = sum(len(fs) for _, _, fs in os.walk(o("site"))) if rc == 0 else 0
    _chk(rc == 0 and n >= 190, "combo/browse+nc", "files=%d" % n)

    rc, _, _ = run([CORPUS, "--sarif", o("s.sarif"), "--no-checks",
                    "--fail-on-dup", "0.99", "--sarif-no-persist"])
    _chk(rc == 0, "combo/sarif+nc+dup")

    # 增量冷热：只允许 stats.cache_* 不同
    cache = o("i.pkl")
    c = []
    for i in range(2):
        p = o("i%d.json" % i)
        rc, _, _ = run([CORPUS, "--incremental", "--incr-cache", cache,
                        "--json", p, "--json-compact", "--no-checks",
                        "--sarif-no-persist"])
        _chk(rc == 0, "combo/incr-run%d" % i)
        if rc == 0:
            c.append(canon(load(p)))
    if len(c) == 2:
        _chk(c[0] == c[1], "combo/incr-reproducible",
             "冷热两次结果不同（stats.cache_* 已剔除）")

    # 幂等：三次。
    # ⚠ **不能加 `--reproducible`**：加了之后 `generated_at` 恒为空串，
    # 这条判据就再也发现不了「`canon()` 忘记剔除 `generated_at`」——
    # R170 的变异测试正是这样抓到它的（变异后只有 incr 那条红，idem 全绿）。
    # 现在三次运行的 `generated_at` 各不相同，`canon()` 必须真的剔除才能通过。
    runs = []
    gens = []
    for i in range(3):
        p = o("idem%d.json" % i)
        rc, _, _ = run([CORPUS, "--json", p, "--sarif-no-persist"])
        _chk(rc == 0, "idem/run%d" % i)
        if rc == 0:
            raw = load(p)
            gens.append(raw.get("generated_at"))
            runs.append(canon(raw))
        # 三次必须在**不同的秒**里 —— 否则 `generated_at` 相同，
        # 「canon 剔除它」这件事就永远测不到（R173 的变异测试抓到的）。
        if i < 2:
            time.sleep(1.05)
    _chk(len(set(gens)) >= 2, "idem/timestamps-actually-differ",
         "三次 generated_at 全同（%r）⇒ 这条判据测不到 canon 的剔除职责"
         % (gens[:1],))
    _chk(len(set(runs)) == 1, "idem/three-identical",
         "distinct=%d（若为 3，先查 canon 有没有剔除 generated_at）"
         % len(set(runs)))

    # mixed
    mix = os.path.join(tmp, "mix")
    write_text(os.path.join(mix, "a.m"),
               u"function y = a(x)\n% d\ny = x + 1;\nend\n")
    write_text(os.path.join(mix, "b.c"),
               u"int add(int a, int b) { return a + b; }\n")
    rc, _, se = run([mix, "--mixed", "--json", o("mix.json"),
                     "--sarif-no-persist"])
    _chk(rc == 0, "combo/mixed", "rc=%d %s" % (rc, se.strip()[:50]))

    # 往返
    rc, _, _ = run(["--from-json", o("all.json"), "--json", o("rt.json"),
                    "--sarif-no-persist"])
    _chk(rc == 0, "roundtrip/rc0")
    if rc == 0:
        a, b = load(o("all.json")), load(o("rt.json"))
        for k in ("files", "edges", "heuristics", "stats"):
            _chk(a.get(k) == b.get(k), "roundtrip/%s" % k)


def group4(tmp):
    """较少用的入口：`--version` / `--json-level` / 未知开关。"""
    o = lambda n: os.path.join(tmp, n)
    rc, so, _ = run(["--version"])
    _chk(rc == 0 and so.strip() != "", "version/prints")

    for lvl in ("summary", "full"):
        p = o("lvl_%s.json" % lvl)
        rc, _, se = run([CORPUS, "--json", p, "--json-level", lvl,
                         "--sarif-no-persist"])
        _chk(rc == 0, "json-level/%s" % lvl, "rc=%d %s" % (rc, se.strip()[:40]))
        if rc == 0:
            need(load(p), "stats", "json-level/%s" % lvl)

    a, b = o("lvl_summary.json"), o("lvl_full.json")
    if os.path.exists(a) and os.path.exists(b):
        _chk(os.path.getsize(a) <= os.path.getsize(b),
             "json-level/summary<=full",
             "%d vs %d" % (os.path.getsize(a), os.path.getsize(b)))

    # 未知开关必须明确报错（`--quiet` 并不存在；我曾在第五轮假设它存在）
    rc, so, se = run([CORPUS, "--quiet"])
    _chk(rc == 2, "unknown-flag/rejected", "rc=%d %s" % (rc, se.strip()[:50]))

    # 同一个输出文件连写两次，内容大小应一致
    p = o("same.json")
    rc1, _, _ = run([CORPUS, "--json", p, "--sarif-no-persist"])
    s1 = os.path.getsize(p) if os.path.exists(p) else 0
    rc2, _, _ = run([CORPUS, "--json", p, "--sarif-no-persist"])
    s2 = os.path.getsize(p) if os.path.exists(p) else 0
    _chk(rc1 == 0 and rc2 == 0 and s1 == s2, "idem/same-output-file",
         "%d vs %d" % (s1, s2))


def _lsp_client():
    """起一个 LSP，返回带**超时保护**的客户端。

    R172 的教训：R166 那次脚本"卡住"不是因为服务端不回包，而是因为
    它等**第三条**消息（`didOpen` 只发两条）。所以这里的 `recv` 一律
    带超时，超时返回 `None` 而不是永久阻塞。
    """
    import threading

    class C(object):
        def __init__(self):
            self.p = subprocess.Popen(
                [PY, os.path.join(ROOT, "matlabc_lsp.py")], cwd=ROOT,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            # 兜底回收：进程被强制杀掉时 `finally` 不执行（R176 实测
            # 泄漏过 4 个），atexit 至少覆盖正常退出。
            import atexit as _atexit
            _atexit.register(self.close)

        def send(self, obj):
            body = json.dumps(obj).encode("utf-8")
            self.p.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
            self.p.stdin.flush()

        def recv(self, timeout=8.0):
            box = {}

            def work():
                try:
                    h = {}
                    while True:
                        line = self.p.stdout.readline()
                        if not line:
                            return
                        if line in (b"\r\n", b"\n"):
                            break
                        k, v = line.decode("ascii").split(":", 1)
                        h[k.strip().lower()] = v.strip()
                    box["m"] = json.loads(
                        self.p.stdout.read(int(h["content-length"]))
                        .decode("utf-8"))
                except Exception:
                    pass

            t = threading.Thread(target=work)
            t.daemon = True
            t.start()
            t.join(timeout)
            return box.get("m")

        def init(self, root=None):
            self.send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"rootUri": (_uri(root) if root else None),
                                  "capabilities": {}}})
            return self.recv()

        def close(self):
            try:
                self.p.kill()
            except Exception:
                pass

    return C()


def _uri(p):
    return "file:///" + str(p).replace("\\", "/").lstrip("/")


def group5(tmp):
    """LSP 边界：对畸形输入**不许崩**（功能对由 lsp_selftest 的 19 条证明）。"""
    o = lambda n: os.path.join(tmp, n)

    c = _lsp_client()
    r = c.init(None)
    _chk(bool(r and r.get("result")), "lsp/init-without-rootUri",
         "%r" % (r,))
    caps = ((r or {}).get("result") or {}).get("capabilities") or {}
    _chk(caps.get("textDocumentSync") == 1, "lsp/textDocumentSync==1")
    c.close()

    txt = o("notes.txt")
    write_text(txt, u"hello\n")
    c = _lsp_client()
    c.init(CORPUS)
    c.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": _uri(txt),
                                        "languageId": "plaintext",
                                        "version": 1, "text": "hi"}}})
    first = c.recv()
    second = c.recv()
    _chk(first is not None, "lsp/non-m-file-replies")
    if second is not None:
        _chk(len(((second.get("params") or {}).get("diagnostics")) or []) == 0,
             "lsp/non-m-file-zero-diags")
    c.close()

    c = _lsp_client()
    c.init(CORPUS)
    c.send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": _uri(o("nope.m")),
                                        "languageId": "matlab",
                                        "version": 1, "text": "x"}}})
    a = c.recv()
    b = c.recv()
    _chk(a is not None, "lsp/missing-file-replies")
    if b is not None:
        _chk(len(((b.get("params") or {}).get("diagnostics")) or []) == 0,
             "lsp/missing-file-zero-diags")
    c.close()

    # 未实现的方法必须回 -32601（R167 修的；这里是防退化）
    c = _lsp_client()
    c.init(CORPUS)
    c.send({"jsonrpc": "2.0", "id": 9, "method": "workspace/symbol",
            "params": {"query": "x"}})
    r = c.recv()
    _chk(r is not None, "lsp/unknown-method-replies", "静默不响应是协议违规")
    _chk(((r or {}).get("error") or {}).get("code") == -32601,
         "lsp/unknown-method--32601", "实际 %r" % (r,))
    c.send({"jsonrpc": "2.0", "method": "some/notification"})
    c.send({"jsonrpc": "2.0", "id": 10, "method": "shutdown"})
    r = c.recv()
    _chk(bool(r and r.get("id") == 10), "lsp/connection-survives",
         "处理过未知通知后 shutdown 无响应")
    c.close()


def group6(tmp):
    """四格式数字一致 + 极端参数。"""
    o = lambda n: os.path.join(tmp, n)
    import re

    rc, _, _ = run([CORPUS, "--json", o("a.json"), "--sarif-no-persist"])
    _chk(rc == 0, "fmt/json")
    rc, _, _ = run([CORPUS, "--xml", o("a.xml")])
    _chk(rc == 0, "fmt/xml")
    rc, _, _ = run([CORPUS, "--browse", o("site")])
    _chk(rc == 0, "fmt/browse")
    rc, _, _ = run([CORPUS, "--mermaid", o("a.mmd")])
    _chk(rc == 0, "fmt/mermaid")
    rc, _, _ = run([CORPUS, "--sarif", o("a.sarif"), "--sarif-no-persist"])
    _chk(rc == 0, "fmt/sarif")

    d = load(o("a.json"))
    st = d.get("stats") or {}
    j_files = st.get("files")
    j_funcs = st.get("functions")

    xml_text = io.open(o("a.xml"), encoding="utf-8").read()
    # 实测：`<files>` **没有 count 属性**，数字在 `<stats><files>N</files>`。
    m = re.search(r"<stats>.*?<files>(\d+)</files>", xml_text, re.S)
    _chk(m is not None, "fmt/xml-has-stats-files")
    if m:
        _chk(int(m.group(1)) == j_files, "fmt/xml-files==json",
             "xml=%s json=%s" % (m.group(1), j_files))
    m2 = re.search(r"<stats>.*?<functions>(\d+)</functions>", xml_text, re.S)
    if m2:
        _chk(int(m2.group(1)) == j_funcs, "fmt/xml-functions==json",
             "xml=%s json=%s" % (m2.group(1), j_funcs))

    # **跨语料**再验一次：只用一个语料时，两边都是 13，
    # 「XML 硬编码 13」也能通过。换成 1 个文件的语料再对一次。
    uninit = os.path.join(ROOT, "tests", "sample_uninit")
    if os.path.isdir(uninit):
        rc, _, _ = run([uninit, "--xml", o("u.xml")])
        _chk(rc == 0, "fmt/xml-cross-corpus-rc0")
        if rc == 0:
            ux = io.open(o("u.xml"), encoding="utf-8").read()
            um = re.search(r"<stats>.*?<files>(\d+)</files>", ux, re.S)
            _chk(um is not None and int(um.group(1)) == 1,
                 "fmt/xml-cross-corpus-files==1",
                 "sample_uninit 只有 1 个 .m，XML 报了 %s"
                 % (um.group(1) if um else "NONE"))

    mmd = io.open(o("a.mmd"), encoding="utf-8").read()
    nodes = set(re.findall(r"^\s*(\w+)\[", mmd, re.M))
    _chk(len(nodes) == j_funcs, "fmt/mermaid-nodes==functions",
         "mermaid=%d json=%s" % (len(nodes), j_funcs))

    idx = io.open(os.path.join(tmp, "site", "index.html"),
                  encoding="utf-8").read()
    _chk(str(j_files) in idx, "fmt/browse-mentions-files")

    # SARIF 与 heuristics 是**不同类别**：`m_missing_doc` 不进 SARIF。
    # 这是已知缺口（记录，不是失败）——如果哪天补上了，这条会红，那是信号。
    sar = load(o("a.sarif"))
    srun = (sar.get("runs") or [{}])[0]
    rule_ids = set((r.get("ruleId") or "")
                   for r in ((srun.get("tool") or {}).get("driver") or {})
                   .get("rules") or [])
    _chk("m_heuristics" not in rule_ids,
         "fmt/sarif-still-lacks-m_heuristics（已知缺口，补上则此条变红）")

    # 极端参数：都不许崩
    for v in ("0", "1", "-1"):
        rc, _, se = run([CORPUS, "--json", o("mn%s.json" % v.replace("-", "n")),
                         "--max-nodes", v, "--sarif-no-persist"])
        _chk(rc in (0, 2), "arg/max-nodes-%s" % v,
             "rc=%d %s" % (rc, se.strip()[:40]))

    # 重复 `--json`：后一个覆盖前一个，**前一个文件根本不该被写**。
    # 只断言「dup2 存在」是弱判据 —— 两个都写也会通过（R174 实测：确实只写 dup2）。
    rc, _, _ = run([CORPUS, "--json", o("dup1.json"), "--json", o("dup2.json"),
                    "--sarif-no-persist"])
    _chk(rc == 0 and os.path.exists(o("dup2.json")),
         "arg/repeat-json-last-wins")
    _chk(not os.path.exists(o("dup1.json")),
         "arg/repeat-json-first-not-written",
         "dup1 也存在 ⇒ 两个 --json 都生效了，不是『后者覆盖』")

    rc, _, _ = run([CORPUS, "--json", o("both.json"), "--xml", o("both.xml"),
                    "--sarif-no-persist"])
    _chk(rc == 0 and os.path.exists(o("both.json"))
         and os.path.exists(o("both.xml")), "arg/json+xml-both")

    rc, _, _ = run([CORPUS, "--lang", "C", "--json", o("u.json")])
    _chk(rc == 2, "arg/lang-uppercase-rejected", "rc=%d（期望 2）" % rc)

    deep = os.path.join(tmp, "d" * 30, "e" * 30, "out.json")
    rc, _, _ = run([CORPUS, "--json", deep, "--sarif-no-persist"])
    _chk(rc in (0, 1) and (rc != 0 or os.path.exists(deep)),
         "arg/deep-output-path", "rc=%d" % rc)


def group7(tmp):
    """并发：两/三个进程同时跑，产物必须都正常。

    ⚠ **不要用 `subprocess.PIPE`**。R166 那次「并发 180 秒超时」就是它：
    Windows 上两个子进程会继承彼此的 PIPE 写端，父进程不读则 EOF 永不到，
    `wait()` 挂死。实测对照：文件重定向下同样两个进程 **0.41 秒**跑完，
    两个产物都在 ⇒ 那是**测试方法**的问题，不是产品问题。
    """
    o = lambda n: os.path.join(tmp, n)

    def spawn(args):
        return subprocess.Popen([PY, MATLABC] + list(args), cwd=ROOT,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)

    t0 = time.time()
    pa = spawn([CORPUS, "--json", o("c1.json"), "--sarif-no-persist"])
    pb = spawn([CORPUS, "--json", o("c2.json"), "--sarif-no-persist"])
    ra = pa.wait(timeout=120)
    rb = pb.wait(timeout=120)
    el = time.time() - t0
    _chk(ra == 0 and rb == 0, "conc/two-json-rc0", "rc=%d/%d" % (ra, rb))
    _chk(el < 30, "conc/two-json-under-30s", "%.1fs" % el)
    if ra == 0 and rb == 0:
        a, b = load(o("c1.json")), load(o("c2.json"))
        _chk(canon(a) == canon(b), "conc/two-json-identical")

    t0 = time.time()
    pa = spawn([CORPUS, "--browse", o("s1")])
    pb = spawn([CORPUS, "--browse", o("s2")])
    ra = pa.wait(timeout=120)
    rb = pb.wait(timeout=120)
    el = time.time() - t0
    _chk(ra == 0 and rb == 0, "conc/two-browse-rc0", "rc=%d/%d" % (ra, rb))
    _chk(el < 30, "conc/two-browse-under-30s", "%.1fs" % el)
    n1 = sum(len(fs) for _, _, fs in os.walk(o("s1")))
    n2 = sum(len(fs) for _, _, fs in os.walk(o("s2")))
    _chk(n1 == n2 and n1 >= 190, "conc/two-browse-same-count",
         "%d vs %d" % (n1, n2))

    t0 = time.time()
    ps = [spawn([CORPUS, "--json", o("m1.json"), "--sarif-no-persist"]),
          spawn([CORPUS, "--xml", o("m2.xml")]),
          spawn([CORPUS, "--mermaid", o("m3.mmd")])]
    rcs = [p.wait(timeout=120) for p in ps]
    el = time.time() - t0
    _chk(all(r == 0 for r in rcs), "conc/three-mixed-rc0", "rc=%r" % (rcs,))
    _chk(el < 40, "conc/three-mixed-under-40s", "%.1fs" % el)
    _chk(os.path.getsize(o("m2.xml")) > 1000
         and os.path.getsize(o("m3.mmd")) > 100,
         "conc/three-mixed-outputs-nonempty")


GROUPS = [("1 开关", group1), ("2 畸形/编码/规模", group2),
          ("3 联动/幂等", group3), ("4 少见入口", group4),
          ("5 LSP 边界", group5), ("6 格式一致/极端参数", group6),
          ("7 并发", group7)]


def _selftest():
    """判据自身的自证：三条防护各一条。"""
    bad = good = 0

    def c(cond, msg):
        nonlocal bad, good
        if cond:
            good += 1
        else:
            bad += 1
            print("  [selftest] %s" % msg)

    c(shape_of({"rel": 1}) == ["rel"], "shape_of 应回排序后的键")
    # 用 `in` 而**不是** `need()`：`need()` 会把结果计入全局 `_RESULT`，
    # 而自证必须与全量跑隔离（第一版就是在这里污染了 1 个假 FAIL）。
    c("rel" in shape_of({"rel": 1}), "need 对存在的键应通过")
    c("file" not in shape_of({"rel": 1}), "need 对不存在的键应拦住")
    d = {"generated_at": "x", "stats": {"cache_hits": 1, "files": 13},
         "v": 1}
    s = canon(d)
    c("generated_at" not in s, "canon 应剔除 generated_at")
    c("cache_hits" not in s, "canon 应剔除 stats.cache_*")
    c('"files": 13' in s or '"files":13' in s, "canon 应保留 stats.files")
    c(EMPTY_INPUT_RC == 1, "EMPTY_INPUT_RC 应为 1")
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return bad, good


def _meta():
    """变异测试：**故意改错**每个防护，看对应判据是否变红。

    51 条全绿只说明「当前实现是对的」，说明不了「判据有守门能力」——
    一条永远绿的判据也全绿。这个函数验证的是**判据本身**。

    R170 它抓到一条真的弱判据：`idem/three-identical` 原来带
    `--reproducible`，于是 `generated_at` 恒为空串，`canon()` 剔除它的
    职责从未被检验（把它改坏仍绿）。去掉那个开关后，同一个变异会红。

    退出码：0 = 每个变异都被抓住 / 1 = 有变异没被抓住（判据是装饰）。
    """
    import json as _json
    import shutil as _shutil
    import tempfile as _tempfile

    bad, good = 0, 0
    print("[meta] 下面出现的 [FAIL] 是**故意制造的变异**，不是真失败；"
          "以最后一行 META COUNTS 为准。")

    def c(cond, msg):
        nonlocal bad, good
        if cond:
            good += 1
            print("  [ok]   " + msg)
        else:
            bad += 1
            print("  [FAIL] " + msg)

    def run_group(fn):
        _RESULT["bad"] = 0
        _RESULT["good"] = 0
        _RESULT["fails"] = []
        tmp = _tempfile.mkdtemp(prefix="sweep_meta_")
        try:
            fn(tmp)
        finally:
            _shutil.rmtree(tmp, ignore_errors=True)
        return _RESULT["bad"], list(_RESULT["fails"])

    def canon_keep_cache(d):
        dd = dict(d)
        dd.pop("generated_at", None)
        return _json.dumps(dd, sort_keys=True, ensure_ascii=False)

    def canon_keep_gen(d):
        dd = dict(d)
        if isinstance(dd.get("stats"), dict):
            dd["stats"] = dict((k, v) for k, v in dd["stats"].items()
                               if k not in VOLATILE_STATS)
        return _json.dumps(dd, sort_keys=True, ensure_ascii=False)

    # 0. 基线：不改任何东西，必须 0 红
    n0, f0 = run_group(group1)
    c(n0 == 0, "基线 group1 应 0 红，实际 %d %r" % (n0, f0[:2]))

    # 1. EMPTY_INPUT_RC 1 -> 0：lang/* 必须变红
    orig_rc = EMPTY_INPUT_RC
    globals()["EMPTY_INPUT_RC"] = 0
    n1, f1 = run_group(group1)
    globals()["EMPTY_INPUT_RC"] = orig_rc
    c(n1 >= 3, "EMPTY_INPUT_RC=0 后应 >=3 条红，实际 %d" % n1)
    c(any("lang/" in x for x in f1),
      "变红的应是 lang/*，实际 %r" % (f1[:2],))

    # 2. need() 语义：缺键 / 非 dict 都必须 False。
    #    **不调 `need()` 本身** —— 它会 `_chk` 到全局 `_RESULT`，
    #    输出里会出现唬人的 `[FAIL] meta/has-file`（R171 实测）。
    #    这里断的是同一段逻辑，只是不经过那个计数器。
    c(("rel" in shape_of({"rel": 1})) is True, "shape_of 对存在的键应含它")
    c(("file" in shape_of({"rel": 1})) is False, "shape_of 对缺的键应不含它")
    c(shape_of(None) == "NoneType", "shape_of 对非 dict 应回类型名")

    # 2b. `_chk` 本体：它对 False 必须计数，否则整个工具是装饰
    saved = (_RESULT["bad"], _RESULT["good"])
    _RESULT["bad"] = 0
    _RESULT["good"] = 0
    _chk(False, "meta/probe-must-count")
    c(_RESULT["bad"] == 1, "_chk 对 False 必须让 bad +1")
    _RESULT["bad"], _RESULT["good"] = saved

    # 3. canon 保留 stats.cache_*：incr-reproducible 必须变红
    orig_canon = canon
    globals()["canon"] = canon_keep_cache
    n3, f3 = run_group(group3)
    globals()["canon"] = orig_canon
    c(n3 >= 1, "保留 cache_* 后应变红，实际 %d" % n3)
    c(any("incr-reproducible" in x for x in f3),
      "变红的应是 incr-reproducible，实际 %r" % (f3[:2],))

    # 4. canon 保留 generated_at：idem 必须变红
    #    （R170 修强之前这条是绿的 —— 那个变异抓到的正是它）
    globals()["canon"] = canon_keep_gen
    n4, f4 = run_group(group3)
    globals()["canon"] = orig_canon
    c(n4 >= 1, "保留 generated_at 后应变红，实际 %d" % n4)
    c(any("idem" in x for x in f4),
      "变红的应含 idem/*，实际 %r" % (f4[:2],))

    # 5. `_chk` 变成空操作：整组应当**一条也不计数**。
    #    这是最根本的自检 —— 如果连计数都不发生，那 91 条"全绿"毫无意义。
    orig_chk = _chk
    globals()["_chk"] = lambda *a, **k: None
    n5, _f5 = run_group(group4)
    empty_good = _RESULT["good"]
    globals()["_chk"] = orig_chk
    c(n5 == 0 and empty_good == 0,
      "空 _chk 时 group4 应 0 红 0 绿，实际 bad=%d good=%d"
      % (n5, empty_good))
    # 恢复后再跑一次，确认 group4 仍然有货（防止"整组本来就空"）
    n5b, _ = run_group(group4)
    c(n5b == 0 and _RESULT["good"] > 5,
      "恢复 _chk 后 group4 应有 >5 条绿，实际 %d" % _RESULT["good"])

    print('META COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--only", default=None,
                    help="组号，可逗号分隔：1 / 1,3 / 5,6")
    ap.add_argument("--list", action="store_true", help="列出所有组")
    ap.add_argument("--json", dest="json_out", action="store_true",
                    help="机器可读输出（一行 JSON）")
    ap.add_argument("--quiet", action="store_true", help="只输出总结")
    ap.add_argument("--fail-fast", dest="fail_fast", action="store_true",
                    help="第一个失败就停")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--meta", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv or sys.argv[1:])

    if args.help:
        if not _write_help(__doc__):
            return 2
        return 0
    if args.list:
        for key, _fn in GROUPS:
            print("  " + key)
        return 0
    if args.selftest:
        bad, good = _selftest()
        return 0 if bad == 0 and good >= 7 else 1
    if args.meta:
        if not os.path.isdir(CORPUS):
            print("sweep_cli: 缺输入（%s）" % CORPUS)
            return 2
        return _meta()
    if not os.path.isdir(CORPUS):
        print("sweep_cli: 缺输入（%s）" % CORPUS)
        return 2

    # `--only` 支持逗号分隔的多个组号（`1,3`），也接受单个数字前缀。
    want = None
    if args.only:
        want = [x.strip() for x in args.only.split(",") if x.strip()]

    tmp = os.path.join(os.environ.get("TEMP", ROOT), "malabc_sweep")
    shutil.rmtree(tmp, ignore_errors=True)
    # `exist_ok=True`：上一次被中断的运行可能仍占着这个目录
    # （Windows 上 rmtree 失败但目录还在），不加它会 FileExistsError。
    os.makedirs(tmp, exist_ok=True)
    timings = []
    aborted = False
    try:
        for key, fn in GROUPS:
            if want and not any(key.startswith(w) for w in want):
                continue
            if not args.quiet:
                print("[%s]" % key)
            b0, g0 = _RESULT["bad"], _RESULT["good"]
            t0 = time.time()
            fn(tmp)
            el = time.time() - t0
            timings.append((key, el, _RESULT["bad"] - b0,
                            _RESULT["good"] - g0))
            if not args.quiet:
                print("  -> %.2fs, %d ok, %d bad"
                      % (el, _RESULT["good"] - g0, _RESULT["bad"] - b0))
            if args.fail_fast and _RESULT["bad"] > b0:
                aborted = True
                break
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    r = _RESULT
    total = sum(t[1] for t in timings)
    if args.json_out:
        print(json.dumps({
            "bad": r["bad"], "good": r["good"],
            "total_secs": round(total, 2),
            "groups": [{"name": k, "secs": round(e, 2), "ok": g, "bad": b}
                       for k, e, b, g in timings],
            "failures": r["fails"], "aborted": aborted,
        }, ensure_ascii=False))
    else:
        print('SWEEP COUNTS {"bad": %d, "good": %d, "secs": %.1f}'
              % (r["bad"], r["good"], total))
        if r["fails"]:
            # 失败详情走 **stderr**：`> report.txt` 时正文保持干净。
            sys.stderr.write("FAILURES: " + " | ".join(r["fails"]) + "\n")
    return 1 if (r["bad"] or aborted) else 0


def _write_help(text):
    try:
        sys.stdout.write(text)
    except Exception:
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())
