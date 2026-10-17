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
    for i in range(3):
        p = o("idem%d.json" % i)
        rc, _, _ = run([CORPUS, "--json", p, "--sarif-no-persist"])
        _chk(rc == 0, "idem/run%d" % i)
        if rc == 0:
            runs.append(canon(load(p)))
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


GROUPS = [("1 开关", group1), ("2 畸形/编码/规模", group2),
          ("3 联动/幂等", group3), ("4 少见入口", group4)]


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


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--only", default=None)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv or sys.argv[1:])

    if args.help:
        if not _write_help(__doc__):
            return 2
        return 0
    if args.selftest:
        bad, good = _selftest()
        return 0 if bad == 0 and good >= 7 else 1
    if not os.path.isdir(CORPUS):
        print("sweep_cli: 缺输入（%s）" % CORPUS)
        return 2

    tmp = os.path.join(os.environ.get("TEMP", ROOT), "malabc_sweep")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    try:
        for key, fn in GROUPS:
            if args.only and not key.startswith(args.only):
                continue
            print("[%s]" % key)
            fn(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    r = _RESULT
    print('SWEEP COUNTS {"bad": %d, "good": %d}' % (r["bad"], r["good"]))
    if r["fails"]:
        print("FAILURES: " + " | ".join(r["fails"]))
        return 1
    return 0


def _write_help(text):
    try:
        sys.stdout.write(text)
    except Exception:
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())
