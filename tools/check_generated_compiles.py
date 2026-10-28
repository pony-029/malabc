# -*- coding: utf-8 -*-
"""check_generated_compiles —— 生成的 C 必须能编译；丢弃调用不许退回 unmapped。

为什么单独成门：这两条判据此前只活在 pytest 里，而**发版脚本跑的是 GATES 元组
（check_* 清单），不跑 pytest** —— 等于从未参与发版把关。

判据（签名 GX1–GX2）：
    GX1  示例工程（numeric / proj / demo_port.m）转出的 C 通过 `-fsyntax-only`
    GX2  丢弃返回值的调用降成 `call:` 而不是 `unmapped:`（且整工程可编译）

用法：
    python tools/check_generated_compiles.py
    python tools/check_generated_compiles.py --selftest

退出码：
    0  = 两条判据全绿
    1  = 有不合规
    2  = 缺依赖（没有 C 编译器 / 没有 pytest）
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ROW_SIGNATURE = "GX1–GX2"

def _cc():
    return shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")


#: 判据前缀 ⇄ 用例文件（每条判据都要真的能把前缀**发出来**，见 H2b）
CHECKS = (
    ("GX1", os.path.join("tests", "test_generated_compiles.py"),
     "GX1 示例工程（numeric / proj / demo_port.m）转出的 C 编译不过"),
    ("GX2", (os.path.join("tests", "test_void_call.py"),
             os.path.join("tests", "test_multi_return.py"),
             os.path.join("tests", "test_nounshaped.py"),
             os.path.join("tests", "test_numeric_expected_guard.py"),
             os.path.join("tests", "test_op_error_paths.py"),
             os.path.join("tests", "test_plan_tracker.py"),
             os.path.join("tests", "test_rt_balance.py"),
             os.path.join("tests", "test_mir_semantics.py"),
             os.path.join("tests", "test_no_duplicate_decls.py"),
             os.path.join("tests", "test_external_project_compiles.py")),
     "GX2 丢弃返回值的调用退回 unmapped，或多返回值算错/编译不过"),
)


def _run_all():
    """一次跑完全部用例文件；返回 (ok, tail, out)。"""
    files = []
    for _, f, _ in CHECKS:
        files.extend(f if isinstance(f, (list, tuple)) else [f])
    cmd = [sys.executable, "-m", "pytest"] + list(files) + [
        "-q", "--tb=no", "-rf", "-p", "no:cacheprovider"]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=900, env=env)
    out = p.stdout.decode("utf-8", "replace")
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    tail = lines[-1] if lines else ""
    return p.returncode == 0, tail, out


def _attribute(out):
    """从 `FAILED tests/x.py::test_y` 行归因到判据前缀。"""
    probs = []
    hit_files = {}
    for ln in out.splitlines():
        if not ln.startswith("FAILED "):
            continue
        path = ln[7:].split("::")[0].strip().replace("/", os.sep)
        hit_files[path] = hit_files.get(path, 0) + 1
    for prefix, f, why in CHECKS:
        files = f if isinstance(f, (list, tuple)) else [f]
        n = sum(hit_files.get(x, 0) for x in files)
        if n:
            probs.append("%s —— %s（%d 个用例失败）" % (why, "见下", n))
    if not probs:
        # 收集期就炸了（不是某个用例失败）：归到第一条判据
        probs.append("%s —— 用例收集/启动失败，见上方输出" % CHECKS[0][2])
    return probs


def selftest():
    bad = good = 0

    def chk(cond, name, detail=""):
        nonlocal bad, good
        if cond:
            good += 1
        else:
            bad += 1
            print("  [FAIL] %-42s %s" % (name, detail))
        return bool(cond)

    _files = []
    for _, f, _ in CHECKS:
        _files.extend(f if isinstance(f, (list, tuple)) else [f])
    chk(len(_files) >= 3, "至少覆盖 3 个用例文件", len(_files))
    chk(all(os.path.isfile(os.path.join(ROOT, f)) for f in _files),
        "用例文件都存在")
    chk(isinstance(ROW_SIGNATURE, str) and "–" in ROW_SIGNATURE, "签名形如 X1–X2")
    chk([c[0] for c in CHECKS] == ["GX1", "GX2"], "GX1/GX2 都有对应用例")
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return bad, good


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", action="store_true")
    args = ap.parse_args(argv)

    if args.help:
        print(__doc__)
        return 0
    if args.selftest:
        bad, _ = selftest()
        return 0 if bad == 0 else 1

    if not _cc():
        print("check_generated_compiles: 缺 C 编译器（GX1 无法执行）")
        return 2
    try:
        import pytest  # noqa: F401
    except ImportError:
        print("check_generated_compiles: 缺 pytest（GX1/GX2 无法执行）")
        return 2

    ok, tail, out = _run_all()
    probs = [] if ok else _attribute(out)
    for p in probs:
        print("  - " + p)
    if probs:
        print(out[-1200:])
        print("check_generated_compiles: %d 项不合规（%s）"
              % (len(probs), ROW_SIGNATURE))
        return 1
    print("check_generated_compiles: OK（%s 全绿：编译判据 + 丢弃调用判据）"
          % ROW_SIGNATURE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
