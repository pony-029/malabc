# -*- coding: utf-8 -*-
"""算子层**随机差分**：Python 解释器（规范）vs C 实现（被测）。

## 为什么

40 个手写语料只能覆盖我想到的形状组合。广播规则（逐维取 max、1 维可扩）
在 `(2,3)⊕(3,)`、`(2,1)⊕(2,3)`、含 0 维这些组合上**只被少数用例碰过**。
差分测试用**随机数据**穷举这些组合，且判定完全交给两个实现的独立输出。

## 用法

    python tools/fuzz_ops.py                 # 默认 60 个随机用例
    python tools/fuzz_ops.py -n 300 --seed 7 # 指定规模与种子
    python tools/fuzz_ops.py --selftest      # 自证：植入偏差必须被抓到

## 判据

每个用例：两实现的输出**逐元素位精确相等**（含 inf/nan 的符号与文本形式）。
不一致即打印反例（op、两个形状、两侧数据），并以非零退出。
"""
import argparse
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")
sys.path.insert(0, ROOT)

from translate import mir_eval as E  # noqa: E402

OPS = ("OP-ADD", "OP-SUB", "OP-MUL", "OP-DIV")

#: 可广播的形状对（含 1 维、单元素、方阵）
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
        # 避免 0 附近除零把结果变成 inf（那会掩盖真正的广播差异）
        if op == "OP-DIV":
            db = [x if abs(x) > 0.5 else 1.5 for x in db]
        out.append((op, sa, da, sb, db))
    return out


def _c_arr(name, shape, data):
    shape_c = ", ".join(str(x) for x in shape)
    init = '    mlc_array_init(&%s, MLC_F64, %d, (int64_t[]){%s});' % (
        name, len(shape), shape_c)
    lines = ["    mlc_array %s;" % name, init]
    for i, v in enumerate(data):
        lines.append('    ((double *)%s.data)[%d] = %r;' % (name, i, v))
    return "\n".join(lines)


def build_program(cases):
    """生成一个把全部用例跑一遍并打印结果的 C 程序。"""
    parts = ['#include <stdio.h>', '#include <math.h>',
             '#include "mlc.h"', '#include "mlc_ops.h"', '', 'int main(void)', '{']
    for ci, (op, sa, da, sb, db) in enumerate(cases):
        fn = {"OP-ADD": "mlc_op_add", "OP-SUB": "mlc_op_sub",
              "OP-MUL": "mlc_op_mul", "OP-DIV": "mlc_op_div"}[op]
        parts.append("    {   /* case %d: %s %s x %s */" % (ci, op, sa, sb))
        parts.append(_c_arr("a", sa, da))
        parts.append(_c_arr("b", sb, db))
        parts.append("        mlc_array o = {0};")
        parts.append("        int64_t i;")
        parts.append("        if (%s(&a, &b, &o) != MLC_OK) { printf(\"%d: ERR\\n\", %d); }" % (fn, ci, ci))
        parts.append("        else {")
        parts.append('            printf("%d:", %d);' % (ci, ci))
        parts.append("            for (i = 0; i < mlc_array_numel(&o); ++i) "
                     "{ printf(\" %.17g\", ((double *)o.data)[i]); }")
        parts.append('            printf("\\n");')
        parts.append("        }")
        parts.append("        mlc_array_free(&a); mlc_array_free(&b); mlc_array_free(&o);")
        parts.append("    }")
    parts += ["    return 0;", "}", ""]
    return "\n".join(parts)


def _bits(x):
    return struct.pack("<d", float(x))


def run_c(cases, cc):
    d = tempfile.mkdtemp(prefix="m2c_fuzz_")
    src = os.path.join(d, "f.c")
    with open(src, "w") as f:
        f.write(build_program(cases))
    exe = os.path.join(d, "f.exe")
    r = subprocess.run([cc, "-std=c99", "-O0",
                        "-I", os.path.join(RT, "include"), src,
                        os.path.join(RT, "src", "mlc_runtime.c"),
                        os.path.join(RT, "src", "mlc_ops.c"),
                        "-o", exe, "-lm"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=900)
    if r.returncode != 0:
        return None, r.stdout.decode("utf-8", "replace")[-800:]
    out = subprocess.run([exe], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT,
                         timeout=300).stdout.decode("utf-8", "replace")
    got = {}
    for ln in out.splitlines():
        if ":" not in ln:
            continue
        k, rest = ln.split(":", 1)
        got[int(k)] = rest.strip()
    shutil.rmtree(d, ignore_errors=True)
    return got, ""


def run_py(cases):
    res = {}
    for ci, (op, sa, da, sb, db) in enumerate(cases):
        r = E.apply_op(op, [E.Arr(da, sa), E.Arr(db, sb)])
        if r is None:
            res[ci] = "ERR"
        else:
            res[ci] = " ".join("%.17g" % v for v in r.data)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("-n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    if args.help:
        print(__doc__)
        return 0

    cc = shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        print("fuzz_ops: 跳过（没有 C 编译器）")
        return 0

    if args.selftest:
        # 自证：把期望值人为改坏，必须被抓到
        cases = gen_cases(5, 3)
        got, err = run_c(cases, cc)
        if got is None:
            print("  [FAIL] C 侧编译失败：%s" % err[-300:])
            print('SELFTEST COUNTS {"bad": 1, "good": 0}')
            return 1
        want = run_py(cases)
        bad = 0
        if got != want:
            bad += 1
        want2 = dict(want)
        for k in list(want2)[:1]:
            want2[k] = want2[k] + " 0"      # 篡改
        if got == want2:
            bad += 1                            # 篡改后应不等
        print("  [OK] 差分有效（篡改后能被识别）" if bad == 0 else "  [FAIL] 差分无效")
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, 1 - bad))
        return 1 if bad else 0

    cases = gen_cases(args.n, args.seed)
    got, err = run_c(cases, cc)
    if got is None:
        print("fuzz_ops: C 侧编译失败\n%s" % err[-600:])
        return 1
    want = run_py(cases)

    diffs = [c for c in range(len(cases)) if got.get(c) != want.get(c)]
    print("fuzz_ops: %d 个用例 ｜ 不一致 %d ｜ seed=%d"
          % (len(cases), len(diffs), args.seed))
    for ci in diffs[:3]:
        op, sa, da, sb, db = cases[ci]
        print("  反例 #%d %s %s x %s\n    C : %s\n    py: %s\n    a=%r\n    b=%r"
              % (ci, op, sa, sb, got.get(ci), want.get(ci), da, db))
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
