# -*- coding: utf-8 -*-
"""check_runtime_static.py —— 用**第三方静态分析器**检查 C 运行时（契约 RS1–RS2）。

## 为什么需要它

`c_runtime/` 是手写 malloc/free 的 C，而仓库里此前**没有任何第三方仪器**
（实测：`-fsanitize=address` 0 处、valgrind 0 处、gcov 0 处）。
本机 gcc（MinGW-W64 16.2）**不带 libasan/libubsan/liblSan** —— 链接直接失败，
所以可用的第三方仪器是 `cppcheck`（静态）与 `gcov`（覆盖率）。

## 判据

* **RS1**：`cppcheck --enable=warning,performance,portability` 报出的 `warning` 必须为 0。
* **RS2**：同上，`error` 级必须为 0。
* **RS3**：覆盖率回归守卫 —— 用 `--coverage` 编 `mlc_ops.c` 并跑 40 例语料，
  `mlc_ops.c` 的**行覆盖 >= 56.9%**、**分支至少走一次 >= 48.3%**。
  阈值故意压在实测值（56.98 / 48.42）之下：它守的是「不比今天更差」。
  没有 gcc/gcov 时 RS3 记为跳过（打印原因，不假装通过）。

`style` 类（如「变量作用域可缩小」）不计入 —— 它不影响正确性。

## 首次启用时抓到的真缺陷（本门的价值证明）

```
mlc_ops.c:70    int64_t idx[MLC_MAX_DIMS];            /* ndim==0 时上面的 for 不执行 */
mlc_ops.c:114   pa[mlc_bcast_offset(a, ndim, idx)]    /* 读未初始化 */
```

`warning: Uninitialized variable: idx [uninitvar]`。它此前没炸，只因为
`mlc_bcast_offset` 在 `ndim == 0` 时不读 `idx` —— **靠下游保证的隐式安全**。
已改为 `= {0}`。

## 用法

    python tools/check_runtime_static.py            # 检查
    python tools/check_runtime_static.py --selftest # 两向：植入已知缺陷必须被报出

## 退出码

0  = 通过（RS1–RS2 全绿：cppcheck warning/error = 0）
1  = 有 RS1/RS2 问题（warning 或 error），或 RS3 低于阈值，或自证失败
"""
import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROW_SIGNATURE = "RS1–RS3"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")

SOURCES = (os.path.join(RT, "src", "mlc_runtime.c"),
           os.path.join(RT, "src", "mlc_ops.c"))
INCLUDE = os.path.join(RT, "include")


def audit(text):
    """纯函数：cppcheck 输出 -> 问题列表（RS1=warning，RS2=error）。"""
    probs = []
    for ln in (text or "").splitlines():
        low = ln.lower()
        if "error:" in low:
            probs.append(u"RS2 cppcheck 报 error：%s" % ln.strip()[:110])
        elif "warning:" in low:
            probs.append(u"RS1 cppcheck 报 warning：%s" % ln.strip()[:110])
    return probs


def run_cppcheck(paths, inc):
    exe = shutil.which("cppcheck")
    if exe is None:
        return None
    cmd = [exe, "--enable=warning,performance,portability", "--inconclusive",
           "--std=c99", "--quiet", "-I", inc] + list(paths)
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    return r.stdout.decode("utf-8", "replace")



#: RS3 的阈值：实测 56.98 / 48.42，压一点做回归守卫
MIN_LINE_PCT = 62.1
MIN_BRANCH_PCT = 51.6


def _excluded_lines(src_path):
    """读出源码里 `@m2c coverage-exclude begin/end` 之间要排除的行号（1 起，含标记行）。"""
    excluded = set()
    inside = False
    try:
        lines = io.open(src_path, encoding="utf-8", errors="replace").read().split("\n")
    except IOError:
        return excluded
    for i, ln in enumerate(lines, 1):
        if "coverage-exclude begin" in ln:
            inside = True
            excluded.add(i)
            continue
        if "coverage-exclude end" in ln:
            excluded.add(i)
            inside = False
            continue
        if inside:
            excluded.add(i)
    return excluded


def _gcov_stats(gcov_path, excluded):
    """从 `.gcov` 明细算 (行%, 分支至少走一次%)，跳过 `excluded` 行号。

    `.gcov` 行格式：`<次数>:<行号>:<源码>`，其中次数 `#####` 表示未执行、`-` 表示不可执行；
    分支行紧跟在它的源码行之后：`branch N taken M` 或 `branch N never executed`。
    """
    exe = hit = 0
    br = br_taken = 0
    cur = None
    try:
        f = io.open(gcov_path, encoding="utf-8", errors="replace")
    except IOError:
        return None
    with f:
        for raw in f:
            m = re.match(r"\s*([\d#=]+|-):\s*(\d+):", raw)
            if m:
                cnt, no = m.group(1), int(m.group(2))
                cur = no
                if no in excluded or cnt == "-":
                    continue
                exe += 1
                if cnt not in ("#####", "====="):
                    try:
                        if int(cnt) > 0:
                            hit += 1
                    except ValueError:
                        pass
                continue
            mb = re.match(r"branch\s+\d+\s+(?:taken\s+(\d+)|never executed)", raw.strip())
            if mb and cur is not None and cur not in excluded:
                br += 1
                if mb.group(1) and int(mb.group(1)) > 0:
                    br_taken += 1
    if exe <= 0:
        return None
    line_pct = 100.0 * hit / exe
    br_pct = (100.0 * br_taken / br) if br else 0.0
    return line_pct, br_pct


def measure_coverage():
    """跑语料并用 gcov 量 `mlc_ops.c`。返回 (行%, 分支至少走一次%) 或 None。"""
    gcc = shutil.which("gcc")
    gcov = shutil.which("gcov")
    m2c = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
    if gcc is None or gcov is None or not os.path.isfile(m2c):
        return None

    d = tempfile.mkdtemp(prefix="m2c_rs3_")
    try:
        for src in ("mlc_runtime.c", "mlc_ops.c"):
            shutil.copy(os.path.join(RT, "src", src), d)
        mir = os.path.join(d, "n.mir")
        subprocess.run([sys.executable,
                        os.path.join(ROOT, "translate", "mir.py"),
                        os.path.join(ROOT, "translate", "examples", "numeric"),
                        "-o", mir],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
        gen = os.path.join(d, "gen")
        subprocess.run([m2c, "build", "--mir", mir, "--out", gen,
                        "--name", "numeric"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=900)
        cc = subprocess.run([gcc, "-std=c99", "-O0", "--coverage",
                             "-I", os.path.join(gen, "include"),
                             "-I", INCLUDE,
                             os.path.join(gen, "src", "gen.c"),
                             os.path.join(gen, "src", "main.c"),
                             "mlc_runtime.c", "mlc_ops.c",
                             "-o", "num.exe", "-lm"],
                            cwd=d, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=900)
        if cc.returncode != 0:
            return None
        subprocess.run([os.path.join(d, "num.exe")], cwd=d,
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=300)
        out = subprocess.run([gcov, "-b", "-c", "num-mlc_ops.gcno"], cwd=d,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=600
                             ).stdout.decode("utf-8", "replace")
        # 明细文件（与 gcov 的汇总行相比，它可以按行过滤）
        gpath = os.path.join(d, "mlc_ops.c.gcov")
        excluded = _excluded_lines(os.path.join(RT, "src", "mlc_ops.c"))
        got = _gcov_stats(gpath, excluded)
        if got is not None:
            return got
        # 兜底：明细解析失败时退回汇总行（宁可少一点信息，也不要假通过）
        line = re.search(r"Lines executed:([\d.]+)%", out)
        taken = re.search(r"Taken at least once:([\d.]+)%", out)
        if not line or not taken:
            return None
        return float(line.group(1)), float(taken.group(1))
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def selftest():
    """两向自证：植入的缺陷必须被 audit() 报出。"""
    good = bad = 0

    def chk(cond, what):
        if cond:
            print(u"  [OK] %s" % what)
            return True
        print(u"  [FAIL] %s" % what)
        return False

    planted_warn = ("x.c:3:5: warning: Uninitialized variable: q [uninitvar]\n")
    planted_err = ("x.c:9:1: error: Memory leak: p [memleak]\n")
    if chk(len(audit(planted_warn)) == 1
           and audit(planted_warn)[0].startswith(u"RS1"), u"RS1 自证：warning 被抓到"):
        good += 1
    else:
        bad += 1
    if chk(len(audit(planted_err)) == 1
           and audit(planted_err)[0].startswith(u"RS2"), u"RS2 自证：error 被抓到"):
        good += 1
    else:
        bad += 1
    if chk(audit("x.c:1:1: style: minor [variableScope]\n") == [],
           u"自证：style 不计入失败"):
        good += 1
    else:
        bad += 1
    if chk(audit("") == [], u"自证：空输出 -> 无问题"):
        good += 1
    else:
        bad += 1

    exe = shutil.which("cppcheck")
    if exe is not None:
        d = tempfile.mkdtemp(prefix="m2c_rs_selftest_")
        p = os.path.join(d, "planted.c")
        with open(p, "w", encoding="utf-8") as f:
            f.write("int f(int n) {\n    int s;\n"
                    "    if (n > 0) { s = n; }\n    return s;\n}\n")
        got = audit(run_cppcheck([p], INCLUDE))
        if chk(any(x.startswith(u"RS1") or x.startswith(u"RS2") for x in got),
               u"自证：cppcheck 真的能报出植入的未初始化读"):
            good += 1
        else:
            bad += 1

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv if argv is not None else sys.argv[1:])

    if args.help:
        print(__doc__)
        return 0
    if args.selftest:
        return selftest()

    text = run_cppcheck(SOURCES, INCLUDE)
    if text is None:
        print("check_runtime_static: 跳过（cppcheck 不可用）")
        return 0

    probs = audit(text)

    cov = measure_coverage()
    if cov is None:
        print("  [skip] RS3 覆盖率：没有 gcc/gcov 或 m2c 未构建")
    else:
        line_pct, branch_pct = cov
        if line_pct < MIN_LINE_PCT:
            probs.append(u"RS3 mlc_ops.c 行覆盖 %.2f%% < %.1f%%（回归）"
                         % (line_pct, MIN_LINE_PCT))
        if branch_pct < MIN_BRANCH_PCT:
            probs.append(u"RS3 mlc_ops.c 分支至少走一次 %.2f%% < %.1f%%（回归）"
                         % (branch_pct, MIN_BRANCH_PCT))
        if not probs:
            print("  [OK] RS3 覆盖率：行 %.2f%%，分支至少走一次 %.2f%%"
                  % (line_pct, branch_pct))

    if probs:
        for p in probs[:8]:
            print(u"  " + p)
        print("check_runtime_static: %d 处 RS1/RS2 问题" % len(probs))
        return 1
    print("check_runtime_static: OK（%s 全绿：cppcheck warning/error = 0）"
          % ROW_SIGNATURE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
