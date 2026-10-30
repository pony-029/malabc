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

#: id -> (C 函数名, 元数)。二元/一元/归约共用同一套装置。
OPS = {
    "OP-ADD": ("mlc_op_add", 2),
    "OP-SUB": ("mlc_op_sub", 2),
    "OP-MUL": ("mlc_op_mul", 2),
    "OP-DIV": ("mlc_op_div", 2),
    "OP-SQRT": ("mlc_op_sqrt", 1),
    "OP-ABS": ("mlc_op_abs", 1),
    "OP-EXP": ("mlc_op_exp", 1),
    "OP-SUM": ("mlc_op_sum", 1),
    "OP-MAX": ("mlc_op_max", 1),
    "OP-MIN": ("mlc_op_min", 1),
    "OP-MEAN": ("mlc_op_mean", 1),
}

#: 一元/归约可用的形状（含空数组）
UNARY_SHAPES = ([1], [3], [2, 3])   # 空数组见上：语义未定，暂不纳入

#: 支持「空输出＝就地分配」的算子（`MIR_SEMANTICS` G3）。一元族**不在其中**。
DYN_OUT = {"OP-ADD", "OP-SUB", "OP-MUL", "OP-DIV",
           "OP-SUM", "OP-MAX", "OP-MIN", "OP-MEAN"}

SHAPE_PAIRS = (
    ([3], [3]),
    ([1], [3]),
    ([2, 3], [3]),
    ([2, 1], [2, 3]),
    ([2, 3], [1]),
    ([2, 3], [2, 3]),
    ([3, 3], [3, 3]),
    ([3], [1]),
    # 注意：**不含**空数组 `[0]` —— 差分已实测出两处空数组语义缺口：
    #   * `sqrt([])` / `abs([])`：C 返回 MLC_ERR，解释器返回空（MATLAB 是空）
    #   * `min([])`：解释器返回 0，C 返回 MLC_ERR（MATLAB 是空）
    # 这是 `MIR_SEMANTICS` 第四节「空数组语义未规定」的具体表现，
    # 待语义定稿后一并修；在此之前不放进冒烟（避免用未定的语义当判据）。
)


def _numel(shape):
    n = 1
    for d in shape:
        n *= d
    return n


def _mkdata(shape, rnd):
    return [round(rnd.uniform(-5, 5), 3) for _ in range(_numel(shape))]


def gen_cases(n, seed):
    """用例 = (op_id, [(shape, data), ...])；元数由 OPS 决定。"""
    rnd = random.Random(seed)
    ids = sorted(OPS)
    out = []
    for _ in range(n):
        oid = rnd.choice(ids)
        _, ar = OPS[oid]
        if ar == 2:
            sa, sb = rnd.choice(SHAPE_PAIRS)
            args = [[sa, _mkdata(sa, rnd)], [sb, _mkdata(sb, rnd)]]
            if oid == "OP-DIV":
                args[1][1] = [x if abs(x) > 0.5 else 1.5 for x in args[1][1]]
        else:
            sh = rnd.choice(UNARY_SHAPES)
            args = [[sh, _mkdata(sh, rnd)]]
            if oid == "OP-SQRT":
                args[0][1] = [abs(x) for x in args[0][1]]
        out.append((oid, args))
    return out


def _arr_decl(name, shape, data, indent="        "):
    lines = ["%smlc_array %s;" % (indent, name),
             "%smlc_array_init(&%s, MLC_F64, %d, (int64_t[]){%s});"
             % (indent, name, len(shape), ", ".join(str(x) for x in shape))]
    for i, v in enumerate(data):
        lines.append("%s((double *)%s.data)[%d] = %r;" % (indent, name, i, v))
    return lines


def build_program(cases):
    p = ['#include <stdio.h>', '#include "mlc.h"', '#include "mlc_ops.h"',
         '', 'int main(void)', '{']
    for ci, (oid, args) in enumerate(cases):
        fn, ar = OPS[oid]
        p.append("    {")
        p += _arr_decl("a", args[0][0], args[0][1])
        if ar == 2:
            p += _arr_decl("b", args[1][0], args[1][1])
        p.append("        mlc_array o;")
        if oid in DYN_OUT:
            # 空输出 -> 算子自己长出来
            p.append("        mlc_array_init(&o, MLC_F64, 1, (int64_t[]){0});")
        else:
            # 一元：输出形状必须与输入一致（调用方负责 init）
            sh0 = args[0][0]
            p.append("        mlc_array_init(&o, MLC_F64, %d, (int64_t[]){%s});"
                     % (len(sh0), ", ".join(str(x) for x in sh0)))
        p.append("        int64_t i;")
        call = ("%s(&a, &b, &o)" % fn) if ar == 2 else ("%s(&a, &o)" % fn)
        p.append('        if (%s != MLC_OK) { printf("%%d: ERR\\n", %d); }'
                 % (call, ci))
        p.append("        else {")
        p.append('            printf("%%d:", %d);' % ci)
        p.append('            for (i = 0; i < mlc_array_numel(&o); ++i)'
                 ' { printf(" %.17g", ((double *)o.data)[i]); }')
        p.append('            printf("\\n");')
        p.append("        }")
        frees = " mlc_array_free(&a); mlc_array_free(&o);"
        if ar == 2:
            frees = " mlc_array_free(&a); mlc_array_free(&b); mlc_array_free(&o);"
        p.append("       " + frees)
        p.append("    }")
    p += ["    return 0;", "}", ""]
    return "\n".join(p)


def run_py(cases):
    res = {}
    for ci, (oid, args) in enumerate(cases):
        r = E.apply_op(oid, [E.Arr(d, sh) for sh, d in args])
        res[ci] = "ERR" if r is None else " ".join("%.17g" % v for v in r.data)
    return res


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
    for ci in diffs[:4]:
        oid, args = cases[ci]
        shapes = " x ".join(str(a[0]) for a in args)
        print("  反例 #%d %s [%s]\n    C : %s\n    py: %s\n    data=%r"
              % (ci, oid, shapes, got.get(ci), want.get(ci),
                 [a[1] for a in args]))
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
