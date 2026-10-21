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
import shlex
import shutil
import subprocess
import sys
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


def _run_binary(case, fn):
    """元素级二元运算：同形或标量广播；越界形态直接报错（不猜）。"""
    fa = _flat(case["inputs"]["a"]["data"])
    fb = _flat(case["inputs"]["b"]["data"])
    n = max(len(fa), len(fb))
    if len(fa) not in (1, n) or len(fb) not in (1, n):
        raise ValueError("binary: 形状不能广播")
    out = [fn(fa[0] if len(fa) == 1 else fa[i],
              fb[0] if len(fb) == 1 else fb[i]) for i in range(n)]
    shape = case["inputs"]["a"]["shape"]
    if len(fa) == 1:
        shape = case["inputs"]["b"]["shape"]
    return _expect(shape, out)


def _run_add(case):
    return _run_binary(case, lambda x, y: x + y)


def _run_sub(case):
    return _run_binary(case, lambda x, y: x - y)


def _run_mul(case):
    return _run_binary(case, lambda x, y: x * y)


def _run_div(case):
    return _run_binary(case, lambda x, y: x / y)


def _run_sum(case):
    x = _flat(case["inputs"]["x"]["data"])
    return _expect([1], [sum(x)])


def _run_mean(case):
    x = _flat(case["inputs"]["x"]["data"])
    if not x:
        raise ValueError("mean: 空输入")
    return _expect([1], [sum(x) / float(len(x))])


def _run_max(case):
    x = _flat(case["inputs"]["x"]["data"])
    if not x:
        raise ValueError("max: 空输入")
    return _expect([1], [max(x)])


def _run_min(case):
    x = _flat(case["inputs"]["x"]["data"])
    if not x:
        raise ValueError("min: 空输入")
    return _expect([1], [min(x)])


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
    "OP-SUB": _run_sub,
    "OP-MUL": _run_mul,
    "OP-DIV": _run_div,
    "OP-SUM": _run_sum,
    "OP-MEAN": _run_mean,
    "OP-MAX": _run_max,
    "OP-MIN": _run_min,
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


def _mingw_candidates():
    """`MLC_MINGW`（默认 `D:\\work\\MinGW-w64`）下的 gcc。

    目录布局在不同发行包里不一致（bin/ 或 mingw64/bin/），所以既查固定
    相对路径，也查一层子目录；找不到就返回空，不影响其它来源。
    """
    root = os.environ.get("MLC_MINGW", r"D:\work\MinGW-w64")
    if not os.path.isdir(root):
        return []
    out = []
    for rel in (("bin", "gcc.exe"), ("mingw64", "bin", "gcc.exe"),
                ("mingw32", "bin", "gcc.exe")):
        p = os.path.join(root, *rel)
        if os.path.isfile(p):
            out.append(p)
    try:
        for name in os.listdir(root):
            p = os.path.join(root, name, "bin", "gcc.exe")
            if os.path.isfile(p):
                out.append(p)
    except OSError:
        pass
    return out


def find_c_compiler():
    """返回可用的 C 编译命令前缀 list；没有返回 None。

    优先级（R12 起按用户环境调整）：
      1. `MLC_CC` / `CC`（显式覆盖，可带参数）；
      2. `MLC_MINGW`（默认 `D:\\work\\MinGW-w64`）下的 gcc；
      3. PATH 里的 gcc / clang / cc / cl；
      4. pip 安装的 `ziglang`（`python -m ziglang cc`）——最后的离线兜底。
    """
    cands = []
    for env in ("MLC_CC", "CC"):
        v = os.environ.get(env)
        if v:
            cands.append(shlex.split(v))
    for p in _mingw_candidates():
        cands.append([p])
    for name in ("gcc", "clang", "cc", "cl"):
        p = shutil.which(name)
        if p:
            cands.append([p])
    try:
        import importlib.util
        if importlib.util.find_spec("ziglang") is not None:
            cands.append([sys.executable, "-m", "ziglang", "cc"])
    except (ImportError, ValueError):
        pass
    for c in cands:
        if c and (os.path.isabs(c[0]) or shutil.which(c[0])):
            return c
    return None


_BINARY_C = {"OP-ADD": "mlc_op_add", "OP-SUB": "mlc_op_sub",
             "OP-MUL": "mlc_op_mul", "OP-DIV": "mlc_op_div"}
_UNARY_C = {"OP-SUM": "mlc_op_sum", "OP-MEAN": "mlc_op_mean",
            "OP-MAX": "mlc_op_max", "OP-MIN": "mlc_op_min"}


def _c_array_lines(name, arr):
    """生成一个 1D f64 数组的声明与 mlc_array 绑定。"""
    flat = _flat(arr.get("data"))
    n = len(flat)
    vals = ", ".join("%.17g" % v for v in flat)
    return [
        "    double {0}d[{1}] = {{{2}}};".format(name, n, vals),
        ("    mlc_array {0}; {0}.data={0}d; {0}.dtype=MLC_F64; "
         "{0}.ndim=1; {0}.shape[0]={1}; {0}.strides[0]=1; "
         "{0}.owns_data=0;").format(name, n),
    ]


def emit_c_program(case):
    """为一个用例生成可独立编译的 C 程序（供有编译器的环境做真比对）。"""
    op = case.get("operator")
    head = ['#include <stdio.h>', '#include "mlc.h"',
            '#include "mlc_ops.h"', 'int main(void) {']
    if op in _BINARY_C:
        a, b = case["inputs"]["a"], case["inputs"]["b"]
        na = len(_flat(a["data"]))
        nb = len(_flat(b["data"]))
        no = max(na, nb)
        lines = head + _c_array_lines("a", a) + _c_array_lines("b", b)
        lines += [
            "    double od[{0}] = {{0}};".format(no),
            "    mlc_array o; mlc_status st;",
            ("    o.data=od; o.dtype=MLC_F64; o.ndim=1; o.shape[0]={0}; "
             "o.strides[0]=1; o.owns_data=0;").format(no),
            "    st = {0}(&a, &b, &o);".format(_BINARY_C[op]),
            '    if (st != MLC_OK) { printf("ERR %d\\n", (int)st);'
            ' return 1; }',
            '    for (int i=0;i<{0};i++) printf("%.17g\\n", od[i]);'
            .format(no),
            "    return 0;", "}"]
        return "\n".join(lines) + "\n"
    if op in _UNARY_C:
        x = case["inputs"]["x"]
        lines = head + _c_array_lines("x", x)
        lines += [
            "    double od[1] = {0};",
            "    mlc_array o; mlc_status st;",
            ("    o.data=od; o.dtype=MLC_F64; o.ndim=1; o.shape[0]=1; "
             "o.strides[0]=1; o.owns_data=0;"),
            "    st = {0}(&x, &o);".format(_UNARY_C[op]),
            "    if (st != MLC_OK) return 1;",
            '    printf("%.17g\\n", od[0]);',
            "    return 0;", "}"]
        return "\n".join(lines) + "\n"
    if op == "OP-INDEX":
        x = case["inputs"]["x"]
        i = int(case["inputs"].get("i", 1))
        lines = head + _c_array_lines("x", x)
        lines += [
            "    double od[1] = {0};",
            "    mlc_array o; mlc_status st;",
            ("    o.data=od; o.dtype=MLC_F64; o.ndim=1; o.shape[0]=1; "
             "o.strides[0]=1; o.owns_data=0;"),
            "    st = mlc_op_index(&x, {0}, &o);".format(i),
            "    if (st != MLC_OK) return 1;",
            '    printf("%.17g\\n", od[0]);',
            "    return 0;", "}"]
        return "\n".join(lines) + "\n"
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
        cmd = list(cc) + ["-I", INCLUDE_DIR, cpath,
                          os.path.join(SRC_DIR, "mlc_runtime.c"),
                          os.path.join(SRC_DIR, "mlc_ops.c"), "-o", exe]
        cp = subprocess.run(cmd, stdin=subprocess.DEVNULL,
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
        "c_backend": {"available": cc is not None,
                      "compiler": (" ".join(cc) if cc else None)},
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
