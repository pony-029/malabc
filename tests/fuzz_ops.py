# -*- coding: utf-8 -*-
"""算子层**随机差分**：Python 解释器（规范）vs C 实现（被测）。

## 为什么放在 `tests/` 而不是 `tools/`

`tools/` 下的脚本会被 `check_all` **自动识别为门**并要求七处登记（R552/R562/R590 各绊一次）。
这里是一个**手动/冒烟用**的工具：日常由 `tests/test_fuzz_ops_smoke.py` 以固定 seed 跑小样本。

## 一个已踩过的坑（上一版 40 例全 ERR 的原因）

`mlc_array o = {0}` 的 `ndim = 0`，而 `numel` 对 0 维取**空积 = 1** ——
于是 `numel(out)==0` 不成立，走不到「空输出＝按广播结论就地分配」那条路，
落入形状检查后必然 `ERR`。**生成代码用的是 `mlc_array_init(&o, ..., {0})`（numel 真为 0）**，
装置必须照它写。

## 用法

    python tests/fuzz_ops.py -n 60 --seed 1
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")
sys.path.insert(0, ROOT)

from translate import mir_eval as E  # noqa: E402

OPS = ("OP-ADD", "OP-SUB", "OP-MUL", "OP-DIV")

SHAPE_PAIRS = (
    ([3], [3]),
    ([1], [3]),
    ([2, 3], [3]),
    ([2, 1], [2, 3]),
    ([2, 3], [1]),
    ([2, 3], [2, 3]),
    ([3, 3], [3, 3]),
)


def _numel(shape):
    n = 1
    for d in shape:
        n *= d
    return n


def gen_cases(n, seed):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        op = rnd.choice(OPS)
        sa, sb = rnd.choice(SHAPE_PAIRS)
        da = [round(rnd.uniform(-5, 5), 3) for _ in range(_numel(sa))]
        db = [round(rnd.uniform(-5, 5), 3) for _ in range(_numel(sb))]
        if op == "OP-DIV":
            db = [x if abs(x) > 0.5 else 1.5 for x in db]
        out.append((op, sa, da, sb, db))
    return out


def _arr_decl(name, shape, data):
    lines = ["        mlc_array %s;" % name,
             "        mlc_array_init(&%s, MLC_F64, %d, (int64_t[]){%s});"
             % (name, len(shape), ", ".join(str(x) for x in shape))]
    for i, v in enumerate(data):
        lines.append("        ((double *)%s.data)[%d] = %r;" % (name, i, v))
    return lines


def build_program(cases):
    p = ['#include <stdio.h>', '#include "mlc.h"', '#include "mlc_ops.h"',
         '', 'int main(void)', '{']
    for ci, (op, sa, da, sb, db) in enumerate(cases):
        fn = {"OP-ADD": "mlc_op_add", "OP-SUB": "mlc_op_sub",
              "OP-MUL": "mlc_op_mul", "OP-DIV": "mlc_op_div"}[op]
        p.append("    {")
        p += _arr_decl("a", sa, da)
        p += _arr_decl("b", sb, db)
        # 关键：输出必须是 numel == 0 的**已初始化**空数组（不是 {0}）
        p.append("        mlc_array o;")
        p.append("        mlc_array_init(&o, MLC_F64, 1, (int64_t[]){0});")
        p.append("        int64_t i;")
        p.append('        if (%s(&a, &b, &o) != MLC_OK) {'
                 ' printf("%%d: ERR\\n", %d); }' % (fn, ci))
        p.append("        else {")
        p.append('            printf("%%d:", %d);' % ci)
        p.append('            for (i = 0; i < mlc_array_numel(&o); ++i)'
                 ' { printf(" %.17g", ((double *)o.data)[i]); }')
        p.append('            printf("\\n");')
        p.append("        }")
        p.append("        mlc_array_free(&a); mlc_array_free(&b);"
                 " mlc_array_free(&o);")
        p.append("    }")
    p += ["    return 0;", "}", ""]
    return "\n".join(p)


def run_c(cases, cc):
    d = tempfile.mkdtemp(prefix="m2c_fuzz_")
    src = os.path.join(d, "f.c")
    with open(src, "w") as f:
        f.write(build_program(cases))
    exe = os.path.join(d, "f.exe")
    r = subprocess.run([cc, "-std=c99", "-O0", "-I", os.path.join(RT, "include"),
                        src, os.path.join(RT, "src", "mlc_runtime.c"),
                        os.path.join(RT, "src", "mlc_ops.c"), "-o", exe, "-lm"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=900)
    if r.returncode != 0:
        return None, r.stdout.decode("utf-8", "replace")[-800:]
    out = subprocess.run([exe], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         timeout=300).stdout.decode("utf-8", "replace")
    got = {}
    for ln in out.splitlines():
        if ":" in ln:
            k, rest = ln.split(":", 1)
            got[int(k)] = rest.strip()
    shutil.rmtree(d, ignore_errors=True)
    return got, ""


def run_py(cases):
    res = {}
    for ci, (op, sa, da, sb, db) in enumerate(cases):
        r = E.apply_op(op, [E.Arr(da, sa), E.Arr(db, sb)])
        res[ci] = "ERR" if r is None else " ".join("%.17g" % v for v in r.data)
    return res


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    n, seed = 60, 1
    if "-n" in argv:
        n = int(argv[argv.index("-n") + 1])
    if "--seed" in argv:
        seed = int(argv[argv.index("--seed") + 1])

    cc = shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        print("fuzz_ops: 跳过（没有 C 编译器）")
        return 0

    cases = gen_cases(n, seed)
    got, err = run_c(cases, cc)
    if got is None:
        print("fuzz_ops: C 侧编译失败\n%s" % err[-600:])
        return 1
    want = run_py(cases)

    diffs = [c for c in range(len(cases)) if got.get(c) != want.get(c)]
    print("fuzz_ops: %d 个用例 ｜ 不一致 %d ｜ seed=%d"
          % (len(cases), len(diffs), seed))
    for ci in diffs[:3]:
        op, sa, da, sb, db = cases[ci]
        print("  反例 #%d %s %s x %s\n    C : %s\n    py: %s\n    a=%r\n    b=%r"
              % (ci, op, sa, sb, got.get(ci), want.get(ci), da, db))
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
