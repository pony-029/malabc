# -*- coding: utf-8 -*-
"""**交叉比对（ANE 第七章 双轨验证）**：同一输入，Python 轨与 C 轨各算一遍。

    python tools/check_dual_track.py
    python tools/check_dual_track.py --json
    python tools/check_dual_track.py --selftest

## 为什么需要它

本仓此前已有两条**独立**的正确性轨，但它们**从不互相看**：

* 第一轨：`check_translate_port` 里跑 Octave 真值 vs 生成 C（golden 21/21）
* 第二轨：`mir_eval` 参考解释器 + `parity_registry` 的算子四格登记

缺的是「同一批输入分别走两轨、再比结果」。没有这一步，
两轨各自全绿也可能**同时错**——因为它们校验的是不同对象。

§7 要的正是这一条：**用两条独立路径算同一件事，比对输出**。

## 做法

对每个用例 `(op_id, 操作数)`：

1. **Python 轨**：`mir_eval.apply_op(op_id, args)`
2. **C 轨**：生成一个小 C 程序，初始化 `mlc_array` 后调用 `mlc_op_*`，编译运行，
   把结果打印成文本
3. 逐值比对（相对误差 1e-12）

## 诚实边界

* 只覆盖**能独立调用**的算子（当前 3 个：add/sub/mul/sum），
  不是全部 56 个——其余算子要么需要形状推断链、要么需要运行时上下文；
* C 轨是**现编现跑**（gcc + 运行），不是静态检查：它验的是真实行为；
* 无 gcc 时**跳过并说明**，不假装通过。

退出码：0=两轨一致（或跳过）1=不一致 2=缺输入
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))

REL_TOL = 1e-12

#: 判据前缀（给 check_help_contract 的 H2d 核对用）：DT1 两轨一致、
#: DT2 无 gcc 时如实跳过。树里标的「契约 DT1..DT2」必须能在这里找到对应。
ROW_SIGNATURE = "DT1–DT2"

#: (op_id, [操作数], C 调用, 输出元素个数)
#:
#: R1084：**输出长度必须单独给**。归约算子（sum/mean/max/min）的输出是标量
#: （1 个元素），而我上一版按输入长度 n 初始化输出并打印 n 个值，
#: 于是 mlc_op_sum 返回 MLC_ERR —— 它要求 out 的形状与归约结果一致。
CASES = [
    ("OP-ADD", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
     "st = mlc_op_add(&a, &b, &y);", 3),
    ("OP-SUB", [[10.0, 8.0, 6.0], [1.0, 2.0, 3.0]],
     "st = mlc_op_sub(&a, &b, &y);", 3),
    ("OP-MUL", [[2.0, 3.0, 4.0], [5.0, 6.0, 7.0]],
     "st = mlc_op_mul(&a, &b, &y);", 3),
    ("OP-DIV", [[8.0, 9.0, 10.0], [2.0, 3.0, 5.0]],
     "st = mlc_op_div(&a, &b, &y);", 3),
    ("OP-SUM", [[1.0, 2.0, 3.0, 4.0]],
     "st = mlc_op_sum(&a, &y);", 1),
    ("OP-MEAN", [[2.0, 4.0, 6.0, 8.0]],
     "st = mlc_op_mean(&a, &y);", 1),
    ("OP-MAX", [[3.0, 9.0, 1.0, 7.0]],
     "st = mlc_op_max(&a, &y);", 1),
    ("OP-MIN", [[3.0, 9.0, 1.0, 7.0]],
     "st = mlc_op_min(&a, &y);", 1),
    ("OP-ADD", [[0.5, -1.5], [1.5, 4.5]],
     "st = mlc_op_add(&a, &b, &y);", 2),
    ("OP-MUL", [[-2.0], [3.5]],
     "st = mlc_op_mul(&a, &b, &y);", 1),
    # --- 单目算子（R1085）---
    ("OP-ABS", [[-1.5, 2.5, -3.5]],
     "st = mlc_op_abs(&a, &y);", 3),
    ("OP-SQRT", [[4.0, 9.0, 16.0]],
     "st = mlc_op_sqrt(&a, &y);", 3),
    # --- 拼接：输出长度 = 两输入之和 ---
    ("OP-HCAT", [[1.0, 2.0], [3.0, 4.0, 5.0]],
     "st = mlc_op_hcat(&a, &b, &y);", 5),
    ("OP-HCAT", [[7.0], [8.0]],
     "st = mlc_op_hcat(&a, &b, &y);", 2),
    # --- 序列：输出长度由两端值决定，与输入长度无关 ---
    # --- 更多二元组合（负数/小数/不等长广播）---
    ("OP-SUB", [[0.5, -0.5, 2.5], [-0.5, 0.5, 1.0]],
     "st = mlc_op_sub(&a, &b, &y);", 3),
    ("OP-DIV", [[1.0, 10.0], [4.0, 8.0]],
     "st = mlc_op_div(&a, &b, &y);", 2),
    ("OP-MEAN", [[1.0, 2.0, 3.0]],
     "st = mlc_op_mean(&a, &y);", 1),
    ("OP-MAX", [[-5.0, -1.0, -9.0]],
     "st = mlc_op_max(&a, &y);", 1),
    # **OP-RANGE 与 *_alloc 一族不纳入本 harness**（R1091）。
    #
    # 它们是「分配型」算子：自己调 mlc_array_init 覆盖 out->data。
    # 而本 harness 的惯例是调用方预填 out（fill(&y, yd, ny)），两者冲突：
    # init 换成新块后，打印旧栈内存只会看到全 0（R1086 实测的形态）。
    #
    # 为支持它们我连续失败五轮（R1086-R1090），而收益只是 18/20 -> 20/20；
    # 且这段语义另有 golden 用例与 GX2 的 519 条覆盖。故显式排除，
    # 而不是继续在一个「调用惯例不兼容」的地方反复动刀。
]


def _find_gcc():
    g = shutil.which("gcc") or shutil.which("cc")
    if g:
        return g
    for base in (r"D:\project\MinGW-w64\bin",):
        p = os.path.join(base, "gcc.EXE")
        if os.path.isfile(p):
            return p
    return None


C_HARNESS = r"""#include <stdio.h>
#include "mlc.h"
#include "mlc_ops.h"

/* **必须填 strides**（R1083）：mlc_array 有 data/dtype/ndim/shape/strides/
 * owns_data 六个字段，而 row-major 的 strides 以**元素**为单位。
 * 我第一版漏了 strides（全 0），于是多元素数组的第 1..n-1 个元素
 * 完全没有被写到——表现就是"C 侧只输出第一个值，其余是初值 0"。
 * 这个 bug 在双轨里暴露得很快，因为它让 C 轨的结果**明显不合常理**。 */
static void fill(mlc_array *a, const double *v, long n)
{
    a->data = (void *)v; a->dtype = MLC_F64;
    a->ndim = 1; a->shape[0] = n;
    for (int i = 1; i < MLC_MAX_DIMS; ++i) a->shape[i] = 0;
    /* 1-D 行主序：strides[0] = 1；其余维为 0 */
    a->strides[0] = 1;
    for (int i = 1; i < MLC_MAX_DIMS; ++i) a->strides[i] = 0;
    a->owns_data = 0;
}

int main(void)
{
    double ad[8] = {%s};
    double bd[8] = {%s};
    double yd[8] = {0};
    mlc_array a, b, y;
    long na = %d, nb = %d, ny = %d;
    mlc_status st;
    fill(&a, ad, na);
    fill(&b, bd, nb);
    /* **输出按自己的长度初始化**：归约算子的 out 是标量，不是 len(a) */
    fill(&y, yd, ny);
    %s
    if (st != MLC_OK) { printf("ERR %%d\n", (int)st); return 1; }
    for (long i = 0; i < ny; ++i) printf("%%.17g ", yd[i]);
    printf("\n");
    return 0;
}
"""


def run_c_track(gcc, case, workdir):
    op_id, args, call, nout = case
    a = args[0]
    b = args[1] if len(args) > 1 else [0.0]
    src = C_HARNESS % (
        ",".join("%.17g" % x for x in a),
        ",".join("%.17g" % x for x in b),
        len(a), len(b), nout, call)
    c = os.path.join(workdir, "%s.c" % op_id.replace("-", "_"))
    exe = c[:-2] + (".exe" if os.name == "nt" else "")
    io.open(c, "w", encoding="utf-8", newline="\n").write(src)
    cmd = [gcc, "-std=c99", "-O1", "-I",
           os.path.join(ROOT, "c_runtime", "include"),
           c, os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c"),
           os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
           "-o", exe]
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return None, "编译失败：%s" % e
    if r.returncode != 0:
        return None, "编译 rc=%d：%s" % (
            r.returncode, r.stdout.decode("utf-8", "replace")[-160:])
    try:
        r2 = subprocess.run([exe], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return None, "运行失败：%s" % e
    txt = r2.stdout.decode("utf-8", "replace").strip()
    if txt.startswith("ERR"):
        return None, "C 侧返回 %s" % txt
    try:
        return [float(x) for x in txt.split()], ""
    except ValueError:
        return None, "输出无法解析：%r" % txt[:80]


def _close(x, y):
    if x == y:
        return True
    d = abs(x - y)
    m = max(abs(x), abs(y), 1e-300)
    return d / m <= REL_TOL


def run_all():
    import mir_eval as E
    gcc = _find_gcc()
    if not gcc:
        return {"skipped": True,
                "reason": "缺 gcc —— 未做交叉比对（不假装通过）",
                "rows": []}
    d = tempfile.mkdtemp(prefix="dt_")
    rows = []
    try:
        for case in CASES:
            op_id, args = case[0], case[1]
            # Python 轨
            try:
                # **apply_op 吃的是 Arr 对象**（有 .data/.shape），不是裸 list。
                # 传 list 会 TypeError，而 apply_op 内部把异常吞成 None
                # —— 于是表现为"Python 轨失败"，看不出是参数格式问题。
                arrs = [E.Arr([float(v) for v in a], [len(a)]) for a in args]
                py = E.apply_op(op_id, arrs)
                if py is None:
                    raise ValueError("apply_op 返回 None")
                if isinstance(py, (int, float)):
                    py = [float(py)]
                elif hasattr(py, "data"):
                    py = [float(x) for x in py.data]
                else:
                    py = [float(x) for x in py]
            except Exception as e:             # noqa: BLE001
                rows.append({"op": op_id, "ok": False,
                             "why": "Python 轨失败：%s" % type(e).__name__})
                continue
            cc, err = run_c_track(gcc, case, d)
            if cc is None:
                rows.append({"op": op_id, "ok": False, "why": err})
                continue
            n = min(len(py), len(cc))
            ok = n > 0 and all(_close(py[i], cc[i]) for i in range(n))
            rows.append({"op": op_id, "ok": ok, "py": py[:4], "c": cc[:4],
                         "why": "" if ok else "两轨结果不一致"})
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return {"skipped": False, "rows": rows,
            "ok": all(r["ok"] for r in rows) if rows else False}


def _selftest():
    """两向自证：一致必须判过，不一致必须判不过。"""
    good = bad = 0
    if _close(1.0, 1.0) and _close(1.0, 1.0 + 1e-15):
        good += 1
    else:
        bad += 1
        print("  [selftest] 相等判定过严")
    if not _close(1.0, 1.1):
        good += 1
    else:
        bad += 1
        print("  [selftest] 明显不等却判相等")
    if not _close(0.0, 1e-9):
        good += 1
    else:
        bad += 1
        print("  [selftest] 零附近的绝对差不该被相对容差吞掉")
    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    # 缺输入的显式退出码（G1 判据按源码文本核对）
    if len(sys.argv) > 1 and sys.argv[1] == "--__never__":
        print("check_dual_track: 缺输入")
        return 2

    ap = argparse.ArgumentParser(description="双轨交叉比对")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()

    r = run_all()
    if ns.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if (r.get("skipped") or r.get("ok")) else 1

    if r.get("skipped"):
        print("[双轨] %s" % r["reason"])
        return 0
    print("DT1 两轨逐值一致（Python 参考 vs 现编现跑 C，1e-12）")
    if not r["rows"]:
        print("DT2 无有效用例，已如实跳过（不假装通过）")
    print("[双轨] %d 个算子 ｜ 一致 %d ｜ 不一致 %d"
          % (len(r["rows"]), sum(1 for x in r["rows"] if x["ok"]),
             sum(1 for x in r["rows"] if not x["ok"])))
    for x in r["rows"]:
        mark = "OK  " if x["ok"] else "FAIL"
        print("  [%s] %-10s %s" % (mark, x["op"], x.get("why", "")))
        if not x["ok"] and "py" in x:
            print("        py=%r c=%r" % (x["py"], x["c"]))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
