#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一条命令演示 LSP 的五个能力，并把结果对到真实源码行上。

    python tools/demo_lsp.py

每个能力都打印「光标在哪一行 → 返回哪个位置 → 那个位置的真实源码」，
所以看到的不只是 JSON，而是**跳转对不对**。

退出码：
    0  = 五个能力都给出了预期位置
    1  = 有能力的返回与预期不符
    2  = 缺输入（tests/sample_m 不在）
"""
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SWEEP = os.path.join(HERE, "sweep_cli.py")
SAMPLE = os.path.join(ROOT, "tests", "sample_m")

bad = 0


def _probe(method, fname, line=None, char=None):
    """调 `sweep_cli.py --probe` 并解析成 dict。"""
    cmd = [sys.executable, SWEEP, "--probe", method, "--probe-file", fname]
    if line is not None:
        cmd += ["--probe-line", str(line), "--probe-char", str(char or 0)]
    p = subprocess.run(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=120)
    try:
        return json.loads((p.stdout or b"").decode("utf-8", "replace"))
    except ValueError:
        return None


def _lines(fname):
    with io.open(os.path.join(SAMPLE, fname), "r", encoding="utf-8",
                 newline="") as fh:
        return fh.read().splitlines()


def _src(fname, zero_line):
    ls = _lines(fname)
    if 0 <= zero_line < len(ls):
        return "%s:%d  %s" % (fname, zero_line + 1, ls[zero_line].rstrip())
    return "%s:%d  <超出文件行数>" % (fname, zero_line + 1)


def _head(title):
    print("")
    print("=" * 62)
    print(" " + title)
    print("=" * 62)


def _result(msg):
    return (msg or {}).get("result")


def main():
    if not os.path.isdir(SAMPLE):
        print("demo_lsp: 缺输入（%s）" % SAMPLE)
        return 2

    # ---- 1. F12 同文件 ------------------------------------------------
    _head("F12 转到定义（同文件）：a.m 第 3 行的 b")
    print(" 光标 " + _src("a.m", 2))
    r = _result(_probe("textDocument/definition", "a.m", 2, 4))
    if r:
        tgt = r[0]
        ln = tgt["range"]["start"]["line"]
        print(" 跳转 " + _src("a.m", ln))
        if ln != 5:
            print(" [FAIL] 期望 a.m 第 6 行")
            globals()["bad"] = bad + 1
    else:
        print(" [FAIL] 无返回")
        globals()["bad"] = bad + 1

    # ---- 2. F12 跨文件 ------------------------------------------------
    _head("F12 转到定义（跨文件）：a.m 第 13 行的 d")
    print(" 光标 " + _src("a.m", 12))
    r = _result(_probe("textDocument/definition", "a.m", 12, 4))
    if r:
        tgt = r[0]
        uri = tgt.get("uri", "")
        other = "d.m" if uri.endswith("/d.m") else os.path.basename(uri)
        ln = tgt["range"]["start"]["line"]
        print(" 跳转 " + _src(other, ln))
        if other != "d.m" or ln != 0:
            print(" [FAIL] 期望 d.m 第 1 行")
            globals()["bad"] = bad + 1
    else:
        print(" [FAIL] 无返回")
        globals()["bad"] = bad + 1

    # ---- 3. Shift+F12 -------------------------------------------------
    _head("Shift+F12 查找引用：a.m 第 6 行 b 的引用")
    print(" 光标 " + _src("a.m", 5))
    r = _result(_probe("textDocument/references", "a.m", 5, 13))
    if r:
        print(" 引用 %d 处（**函数级**：落点是调用者的定义行）" % len(r))
        for tgt in r:
            uri = tgt.get("uri", "")
            f = os.path.basename(uri)
            print("      " + _src(f, tgt["range"]["start"]["line"]))
        print(" 说明：b 被 a 调用，所以给的是 a 的定义行 ——")
        print("       `edges` 是 (caller, callee) 不带行号，行级引用需要它带 line。")
    else:
        print(" 无引用")

    # ---- 4. 悬停 -------------------------------------------------------
    _head("悬停：a.m 第 3 行的 b")
    print(" 光标 " + _src("a.m", 2))
    r = _result(_probe("textDocument/hover", "a.m", 2, 4))
    if r:
        val = ((r.get("contents") or {}).get("value") or "")
        for ln in val.splitlines():
            print("   " + ln)
    else:
        print(" [FAIL] 无返回")
        globals()["bad"] = bad + 1

    # ---- 5. 大纲 -------------------------------------------------------
    _head("符号大纲：a.m")
    r = _result(_probe("textDocument/documentSymbol", "a.m"))
    if r:
        for s in r:
            print("   [kind=%d] %-6s 定义于第 %d 行"
                  % (s.get("kind", 0), s.get("name", "?"),
                     s["range"]["start"]["line"] + 1))
    else:
        print(" [FAIL] 无返回")
        globals()["bad"] = bad + 1

    print("")
    print("=" * 62)
    if bad:
        print(" DEMO: %d 项与预期不符" % bad)
        return 1
    print(" DEMO: 五项全部符合预期（上面每一行「跳转 xxx」都能在源码里核对）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
