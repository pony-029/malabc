# -*- coding: utf-8 -*-
"""runnable_report —— 端到端「可执行读数」：转换 → 生成 → 编译 → 跑 → 分类统计。

为什么需要它：**"能编译"和"算得出数"是两条线**。
`gcc -fsyntax-only` 通过、MIR 里 `TODO` 归零，都不代表函数能算出数值 ——
之前的读数靠手敲 PowerShell 过滤，不可复现。这个工具把那条链固化下来。

输出的四类（互斥，逐函数）：
    numeric   打印出数值（**唯一真正可用的类别**）
    error     调用了但返回非 MLC_OK
    skipped_reject   整函数被拒（struct/cell/varargin…）
    skipped_shape    没有形状注解且不可动态推断

用法：
    python tools/runnable_report.py translate/examples/numeric
    python tools/runnable_report.py C:/Temp/yalmip --recursive --top 5
    python tools/runnable_report.py translate/examples/numeric --selftest

退出码：
    0  = 统计完成
    2  = 缺依赖（没有 C 编译器 / 没有 m2c 可执行文件）
"""
import argparse
import collections
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
RT = os.path.join(ROOT, "c_runtime")

_LINE = re.compile(r"^(?P<name>[A-Za-z_]\w*):\s*(?P<rest>.*)$")


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


def _run(cmd, timeout=1200):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(cmd, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=timeout, env=env)


def classify(text):
    """把驱动输出逐行分类。返回 (collections.Counter, 明细列表)。"""
    cnt = collections.Counter()
    rows = []
    for ln in text.splitlines():
        m = _LINE.match(ln.strip())
        if not m:
            continue
        name, rest = m.group("name"), m.group("rest").strip()
        if rest.startswith("skipped"):
            if "reject" in rest:
                kind = "skipped_reject"
            else:
                kind = "skipped_shape"
        elif rest == "error":
            kind = "error"
        elif rest.startswith("unimplemented"):
            # 跑起来了，但函数体是桩（MLC_UNIMPLEMENTED）—— 与 error 不同：
            # error 是算子运行期失败，unimplemented 是从未真正实现
            kind = "unimplemented"
        elif re.match(r"^-?\d", rest):
            kind = "numeric"
        elif rest == "":
            # 算完了但结果为空（例如空数组）：既不是失败也不是数值
            kind = "empty"
        else:
            continue
        cnt[kind] += 1
        rows.append((kind, name, rest))
    return cnt, rows


def build_and_run(src, recursive, keep=False):
    """返回 (ok, 说明, 驱动输出文本)。"""
    if not os.path.exists(M2C):
        return False, "找不到 m2c：先 cargo build --release", ""
    d = tempfile.mkdtemp(prefix="m2c_runrep_")
    mir = os.path.join(d, "p.mir")
    gen = os.path.join(d, "gen")

    cmd = [sys.executable, os.path.join(ROOT, "translate", "mir.py"), src,
           "-o", mir]
    if recursive and os.path.isdir(src):
        cmd.insert(3, "--recursive")
    r = _run(cmd)
    if r.returncode != 0:
        return False, "转换失败：\n" + r.stdout.decode("utf-8", "replace")[-600:], ""

    r = _run([M2C, "build", "--mir", mir, "--out", gen, "--name", "rep"])
    if r.returncode != 0:
        return False, "生成失败：\n" + r.stdout.decode("utf-8", "replace")[-600:], ""

    exe = os.path.join(gen, "rep.exe" if os.name == "nt" else "rep")
    r = _run([_cc(), "-std=c99", "-O1",
              "-I", os.path.join(gen, "include"),
              "-I", os.path.join(RT, "include"),
              os.path.join(gen, "src", "gen.c"),
              os.path.join(gen, "src", "main.c"),
              os.path.join(RT, "src", "mlc_runtime.c"),
              os.path.join(RT, "src", "mlc_ops.c"),
              "-o", exe])
    if r.returncode != 0:
        return False, "编译失败：\n" + r.stdout.decode("utf-8", "replace")[-800:], ""

    r = _run([exe])
    return True, d, r.stdout.decode("utf-8", "replace")


def selftest():
    bad = good = 0

    def chk(cond, name, detail=""):
        nonlocal bad, good
        if cond:
            good += 1
        else:
            bad += 1
            print("  [FAIL] %-40s %s" % (name, detail))
        return bool(cond)

    cnt, _ = classify("a: 1 2 3\nb: error\nc: skipped (reject:struct)\n"
                      "d: skipped (no shape)\nx: assumed shape [4]\n")
    chk(cnt["numeric"] == 1, "numeric 计 1", cnt)
    chk(cnt["error"] == 1, "error 计 1", cnt)
    chk(cnt["skipped_reject"] == 1, "reject 计 1", cnt)
    chk(cnt["skipped_shape"] == 1, "shape 计 1", cnt)
    chk(bool(_cc()), "找到 C 编译器")
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return bad, good


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--allow-empty", action="store_true")
    ap.add_argument("src", nargs="?")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--top", type=int, default=0,
                    help="列出前 N 条跳过原因")
    ap.add_argument("--keep", action="store_true", help="保留临时目录")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        bad, _ = selftest()
        return 0 if bad == 0 else 1
    if args.help or not args.src:
        print(__doc__)
        return 0
    if not _cc():
        print("runnable_report: 缺 C 编译器")
        return 2

    ok, info, text = build_and_run(args.src, args.recursive, args.keep)
    if not ok:
        print("runnable_report: " + info)
        return 1

    cnt, rows = classify(text)
    total = sum(cnt.values())
    print("用例 %s ｜ 可驱动函数 %d" % (args.src, total))
    print("  numeric（真能算） : %d" % cnt["numeric"])
    print("  unimplemented     : %d（桩：跑了但没实现）" % cnt["unimplemented"])
    print("  error             : %d" % cnt["error"])
    print("  empty             : %d（算完但结果为空）" % cnt["empty"])
    print("  skipped_reject    : %d" % cnt["skipped_reject"])
    print("  skipped_shape     : %d" % cnt["skipped_shape"])
    if args.top:
        print("--- 前 %d 个 numeric ---" % args.top)
        for kind, name, rest in rows:
            if kind == "numeric":
                print("  %-28s %s" % (name[:28], rest[:60]))
                args.top -= 1
                if args.top <= 0:
                    break
    if cnt["empty"]:
        print(u"--- empty（算完但结果为空 —— 与「静默算错」同类，必须查）---")
        for kind, name, rest in rows:
            if kind == "empty":
                print("  %s" % name)
        if not args.allow_empty:
            print("runnable_report: %d 个函数算出空结果 —— 这通常是"
                  "「半实现却报告成功」，用 --allow-empty 可显式放行"
                  % cnt["empty"])
            if not args.keep and info and os.path.isdir(info) \
                    and info.startswith(tempfile.gettempdir()):
                shutil.rmtree(info, ignore_errors=True)
            return 1
    if not args.keep and info and os.path.isdir(info) \
            and info.startswith(tempfile.gettempdir()):
        # 只删本次的工作目录（绝不能碰临时根目录）
        shutil.rmtree(info, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
