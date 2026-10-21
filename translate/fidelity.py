# -*- coding: utf-8 -*-
"""双语保真执行器（R432 / P0）—— `verified_by` 的**唯一裁判**。

职责：
  1. 读取 `translate/golden/*.json`（同输入、同期望输出）；
  2. 用 Python 参考实现算出结果（永远可用，离线）；
  3. 若本机有 C 编译器，则把同一个用例编译成 C 程序并比对；
     没有编译器时**明确报 skipped + 原因**，而不是假装通过；
  4. 给出逐用例的 abs/rel 误差与通过/失败清单。

设计纪律（与 `translate/__init__.py` 一致）：
  * 默认姿态是「不可信」：没跑过的用例不算 verified；
  * C 后端缺失是一等状态，必须可见（`c_backend.available=False`）。
"""

import io
import json
import os
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN_DIR = os.path.join(HERE, "golden")
INCLUDE_DIR = os.path.join(os.path.dirname(HERE), "c_runtime", "include")
SRC_DIR = os.path.join(os.path.dirname(HERE), "c_runtime", "src")


def load_case(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _flat(data):
    out = []
    if isinstance(data, (list, tuple)):
        for x in data:
            out.extend(_flat(x))
    else:
        out.append(float(data))
    return out


def _shape(data):
    if not isinstance(data, (list, tuple)):
        return []
    if not data:
        return [0]
    return [len(data)] + _shape(data[0])


def _numel(shape):
    n = 1
    for d in shape:
        n *= int(d)
    return n


def _expect(shape, data):
    return {"dtype": "f64", "shape": list(shape), "data": _flat(data)}


def _run_add(case):
    a = case["inputs"]["a"]["data"]
    b = case["inputs"]["b"]["data"]
    fa, fb = _flat(a), _flat(b)
    n = max(len(fa), len(fb))
    if len(fa) not in (1, n) or len(fb) not in (1, n):
        raise ValueError("add: 形状不能广播")
    out = [(fa[0] if len(fa) == 1 else fa[i]) +
           (fb[0] if len(fb) == 1 else fb[i]) for i in range(n)]
    shape = case["inputs"]["a"]["shape"]
    if len(fa) == 1:
        shape = case["inputs"]["b"]["shape"]
    return _expect(shape, out)


def _run_sum(case):
    x = _flat(case["inputs"]["x"]["data"])
    return _expect([1], [sum(x)])


def _run_index(case):
    x = _flat(case["inputs"]["x"]["data"])
    i = int(case["inputs"].get("i", 1))
    idx0 = i - 1  # IDX-1
    if idx0 < 0 or idx0 >= len(x):
        raise ValueError("index 越界")
    return _expect([1], [x[idx0]])


def _run_transpose(case):
    x = case["inputs"]["x"]["data"]
    rows = len(x)
    cols = len(x[0]) if rows else 0
    out = [[x[r][c] for r in range(rows)] for c in range(cols)]
    return _expect([cols, rows], out)


def _run_matmul(case):
    a = case["inputs"]["A"]["data"]
    b = case["inputs"]["B"]["data"]
    n, k, m = len(a), len(a[0]), len(b[0])
    out = [[sum(a[i][t] * b[t][j] for t in range(k)) for j in range(m)]
           for i in range(n)]
    return _expect([n, m], out)


_RUNNERS = {
    "OP-ADD": _run_add,
    "OP-SUM": _run_sum,
    "OP-INDEX": _run_index,
    "OP-TRANSPOSE": _run_transpose,
    "OP-MATMUL": _run_matmul,
}


def run_python(case):
    op = case.get("operator")
    if op not in _RUNNERS:
        raise ValueError("没有 Python 参考实现：%s" % op)
    return _RUNNERS[op](case)


def compare(case, got):
    """按 abs/rel 容差比较；返回 {ok, max_abs, detail}。"""
    exp = case.get("expected") or {}
    tol = case.get("tol") or {}
    abs_tol = float(tol.get("abs", 1e-12))
    rel_tol = float(tol.get("rel", 1e-9))
    if got.get("dtype") != exp.get("dtype"):
        return {"ok": False, "max_abs": None,
                "detail": "dtype %r != %r" % (got.get("dtype"), exp.get("dtype"))}
    if list(got.get("shape") or []) != list(exp.get("shape") or []):
        return {"ok": False, "max_abs": None,
                "detail": "shape %r != %r" % (got.get("shape"), exp.get("shape"))}
    fe = _flat(exp.get("data"))
    fg = _flat(got.get("data"))
    if len(fe) != len(fg):
        return {"ok": False, "max_abs": None,
                "detail": "numel %d != %d" % (len(fg), len(fe))}
    max_abs = 0.0
    bad = None
    for i, (e, g) in enumerate(zip(fe, fg)):
        d = abs(e - g)
        max_abs = max(max_abs, d)
        lim = abs_tol + rel_tol * abs(e)
        if d > lim and bad is None:
            bad = "index %d: expected %.17g got %.17g (|d|=%.3g > %.3g)" % (
                i, e, g, d, lim)
    return {"ok": bad is None, "max_abs": max_abs, "detail": bad or ""}


def find_c_compiler():
    """返回第一个可用的 C 编译器路径；没有返回 None。"""
    for cand in (os.environ.get("CC"), "gcc", "clang", "cc", "cl"):
        if not cand:
            continue
        p = shutil.which(cand) if not os.path.isabs(cand) else cand
        if p and os.path.isfile(p):
            return p
    return None


def emit_c_program(case):
    """为一个用例生成可独立编译的 C 程序（供有编译器的环境做真比对）。"""
    op = case.get("operator")
    if op == "OP-ADD":
        a, b = case["inputs"]["a"], case["inputs"]["b"]
        fa, fb = _flat(a["data"]), _flat(b["data"])
        lines = ['#include <stdio.h>', '#include "mlc.h"',
                 '#include "mlc_ops.h"', 'int main(void) {',
                 '    double ad[%d] = {%s};' % (len(fa), ", ".join(
                     "%.17g" % v for v in fa)),
                 '    double bd[%d] = {%s};' % (len(fb), ", ".join(
                     "%.17g" % v for v in fb)),
                 '    double od[%d] = {0};' % max(len(fa), len(fb)),
                 '    mlc_array a, b, o; mlc_status st;',
                 '    a.data=ad; a.dtype=MLC_F64; a.ndim=1; a.shape[0]=%d;'
                 ' a.strides[0]=1; a.owns_data=0;' % len(fa),
                 '    b.data=bd; b.dtype=MLC_F64; b.ndim=1; b.shape[0]=%d;'
                 ' b.strides[0]=1; b.owns_data=0;' % len(fb),
                 '    o.data=od; o.dtype=MLC_F64; o.ndim=1; o.shape[0]=%d;'
                 ' o.strides[0]=1; o.owns_data=0;' % max(len(fa), len(fb)),
                 '    st = mlc_op_add(&a, &b, &o);',
                 '    if (st != MLC_OK) { printf("ERR %d\\n", (int)st);'
                 ' return 1; }',
                 '    for (int i=0;i<{n};i++) printf("%.17g\\n", od[i]);'
                 .format(n=max(len(fa), len(fb))),
                 '    return 0;', '}']
        return "\n".join(lines) + "\n"
    if op == "OP-SUM":
        x = _flat(case["inputs"]["x"]["data"])
        return '\n'.join([
            '#include <stdio.h>', '#include "mlc.h"', '#include "mlc_ops.h"',
            'int main(void) {',
            '    double xd[%d] = {%s};' % (len(x), ", ".join(
                "%.17g" % v for v in x)),
            '    double od[1] = {0};',
            '    mlc_array a, o; mlc_status st;',
            '    a.data=xd; a.dtype=MLC_F64; a.ndim=1; a.shape[0]=%d;'
            ' a.strides[0]=1; a.owns_data=0;' % len(x),
            '    o.data=od; o.dtype=MLC_F64; o.ndim=1; o.shape[0]=1;'
            ' o.strides[0]=1; o.owns_data=0;',
            '    st = mlc_op_sum(&a, &o);',
            '    if (st != MLC_OK) return 1;',
            '    printf("%.17g\\n", od[0]);', '    return 0;', '}'])
    if op == "OP-INDEX":
        x = _flat(case["inputs"]["x"]["data"])
        i = int(case["inputs"].get("i", 1))
        return '\n'.join([
            '#include <stdio.h>', '#include "mlc.h"', '#include "mlc_ops.h"',
            'int main(void) {',
            '    double xd[%d] = {%s};' % (len(x), ", ".join(
                "%.17g" % v for v in x)),
            '    double od[1] = {0};',
            '    mlc_array a, o; mlc_status st;',
            '    a.data=xd; a.dtype=MLC_F64; a.ndim=1; a.shape[0]=%d;'
            ' a.strides[0]=1; a.owns_data=0;' % len(x),
            '    o.data=od; o.dtype=MLC_F64; o.ndim=1; o.shape[0]=1;'
            ' o.strides[0]=1; o.owns_data=0;',
            '    st = mlc_op_index(&a, %d, &o);' % i,
            '    if (st != MLC_OK) return 1;',
            '    printf("%.17g\\n", od[0]);', '    return 0;', '}'])
    return None


def run_c(case):
    """编译并运行 C 用例；没有编译器/没有 C 落点时返回 skipped。"""
    cc = find_c_compiler()
    if cc is None:
        return {"status": "skipped",
                "reason": "no C compiler (CC/gcc/clang/cc/cl not found)"}
    src = emit_c_program(case)
    if src is None:
        return {"status": "skipped",
                "reason": "no C emitter for %s" % case.get("operator")}
    tmp = tempfile.mkdtemp(prefix="mlc_fid_")
    try:
        cpath = os.path.join(tmp, "case.c")
        exe = os.path.join(tmp, "case.exe" if os.name == "nt" else "case")
        with io.open(cpath, "w", encoding="utf-8") as fh:
            fh.write(src)
        cp = subprocess.run([cc, "-I", INCLUDE_DIR, cpath,
                             os.path.join(SRC_DIR, "mlc_runtime.c"),
                             os.path.join(SRC_DIR, "mlc_ops.c"), "-o", exe],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=60)
        if cp.returncode != 0:
            return {"status": "compile_error",
                    "reason": (cp.stderr or b"").decode("utf-8", "replace")[:400]}
        rp = subprocess.run([exe], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=30)
        if rp.returncode != 0:
            return {"status": "run_error",
                    "reason": (rp.stdout or b"").decode("utf-8", "replace")[:200]}
        vals = [float(x) for x in
                (rp.stdout or b"").decode("utf-8", "replace").split()]
        exp = _flat((case.get("expected") or {}).get("data"))
        got = {"dtype": "f64", "shape": list(
            (case.get("expected") or {}).get("shape") or []), "data": vals}
        res = compare(case, got)
        res["status"] = "ok" if res["ok"] else "mismatch"
        return res
    except (OSError, subprocess.SubprocessError) as e:
        return {"status": "error", "reason": str(e)[:300]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_all(golden_dir=None, with_c=False):
    """跑全部 golden；返回逐用例结果 + C 后端状态。"""
    gdir = golden_dir or GOLDEN_DIR
    files = []
    if os.path.isdir(gdir):
        files = sorted(f for f in os.listdir(gdir) if f.endswith(".json"))
    results = []
    passed = 0
    for fn in files:
        case = load_case(os.path.join(gdir, fn))
        try:
            got = run_python(case)
            res = compare(case, got)
        except (ValueError, KeyError, TypeError) as e:
            res = {"ok": False, "max_abs": None, "detail": str(e)}
        res["case"] = fn
        res["operator"] = case.get("operator")
        if with_c:
            res["c"] = run_c(case)
        if res.get("ok"):
            passed += 1
        results.append(res)
    cc = find_c_compiler()
    return {
        "total": len(files),
        "passed": passed,
        "failed": [r for r in results if not r.get("ok")],
        "results": results,
        "c_backend": {"available": cc is not None, "compiler": cc},
    }


def self_test():
    """门禁用：全部用例必须通过；返回 (ok, report)。"""
    rep = run_all(with_c=False)
    ok = rep["total"] > 0 and rep["passed"] == rep["total"]
    return ok, rep


if __name__ == "__main__":
    import sys
    ok, rep = self_test()
    print("fidelity: %d/%d passed; C backend: %s"
          % (rep["passed"], rep["total"],
             "available (%s)" % rep["c_backend"]["compiler"]
             if rep["c_backend"]["available"] else "unavailable"))
    for r in rep["failed"]:
        print("  [FAIL] %s %s" % (r.get("case"), r.get("detail")))
    sys.exit(0 if ok else 1)
