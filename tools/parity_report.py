# -*- coding: utf-8 -*-
"""对拍门：MIR 解释器（Python）⇄ 生成的 C 程序。

## 这个工具回答的问题

"MATLAB 与 C 两边实现一致吗？" —— 在**没有 MATLAB/Octave** 的机器上，
唯一诚实的答法是：造一个**独立于 C 的第二个执行器**，让它和 C 跑同一份 MIR。

    .m ──mir.py──▶ MIR ──解释执行（Python）──▶ 参考输出
                        └──m2c──▶ C ──gcc──▶ 实际输出

两者语义实现完全不同：一个是 Python 循环，一个是 C 代码。它们一致，
只能说明"发射器 + 运行时"这一层没走样；**仍不等于 MATLAB 语义正确**。
所以本门把结论分三级写清楚，绝不把"未验证"混进"通过"。

## 三级结论

| 级别 | 含义 |
|---|---|
| **V**（已对拍） | 解释器与 C 都能算，且逐值一致 |
| **U**（未对拍） | 解释器放弃（含 unmapped 语句 / 无形状入参）—— **不知道** |
| **X**（不一致） | 两边都能算但结果不同 —— **一定是错** |

只有 X 会让门变红。U 会被**如实计数并打印**，不会被当成通过。

退出码：
    0  = 没有 PA3（可能仍有 PA2 未对拍，数字会如实显示）
    1  = 存在 PA3 不一致（两边都能算但结果不同）
    2  = 缺输入（MIR 不存在 / 找不到 C 编译器 / 生成或编译失败）
"""

import argparse
import io
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import fidelity, mir_eval  # noqa: E402


def _m2c():
    """按平台找 m2c；支持 M2C_BIN 覆盖。"""
    env = os.environ.get("M2C_BIN")
    if env and os.path.isfile(env):
        return env
    exe = "m2c.exe" if os.name == "nt" else "m2c"
    path = os.path.join(ROOT, "rust", "m2c", "target", "release", exe)
    return path if os.path.isfile(path) else None


def _run(cmd, cwd=None, timeout=900):
    p = subprocess.run(cmd, cwd=cwd or ROOT, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def _cc():
    """复用 fidelity 的编译器探测（含 MLC_CC / MinGW / gcc / clang / zig）。"""
    return fidelity.find_c_compiler()


def _interp_lines(funcs):
    """解释执行 -> {函数名: 行文本 或 None}。"""
    res = mir_eval.run_all(funcs)
    out = {}
    for f in funcs:
        outs = res.get(f.name)
        if outs is None:
            out[f.name] = None
            continue
        parts = [" ".join("%.10g" % v for v in a.data) for a in outs]
        out[f.name] = "%s: %s" % (f.name, " | ".join(parts))
    return out


def _c_lines(text):
    """C 程序输出 -> {函数名: 行文本}（含 unimplemented / skipped）。"""
    out = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ":" not in ln:
            continue
        name = ln.split(":", 1)[0]
        out[name] = ln
    return out


def check(mir_path, expect_path=None, keep=False):
    """返回 (probs, stats)。probs 只装**真不一致**。"""
    probs = []
    text = io.open(mir_path, encoding="utf-8").read()
    funcs = mir_eval.parse(text)
    ref = _interp_lines(funcs)

    m2c = _m2c()
    if not m2c:
        return ["PARITY 缺 Rust 发射器（先 cargo build --release）"], {}
    d = tempfile.mkdtemp(prefix="m2c_parity_")
    rc, out = _run([m2c, "build", "--mir", mir_path, "--out", d,
                    "--name", "parity"])
    if rc != 0:
        return ["PARITY 生成工程失败：%s" % (out.strip().splitlines()[:2],)], {}

    cc = _cc()
    if not cc:
        return ["PARITY 没有可用 C 编译器"], {}
    rt = os.path.join(ROOT, "c_runtime")
    exe = os.path.join(d, "parity.exe" if os.name == "nt" else "parity")
    cmd = list(cc) + ["-std=c99", "-O1", "-I", os.path.join(d, "include"),
                      "-I", os.path.join(rt, "include"),
                      os.path.join(d, "src", "gen.c"),
                      os.path.join(d, "src", "main.c"),
                      os.path.join(rt, "src", "mlc_runtime.c"),
                      os.path.join(rt, "src", "mlc_ops.c"), "-o", exe]
    rc, out = _run(cmd)
    if rc != 0:
        return ["PARITY 编译失败：%s" % (out.strip().splitlines()[:2],)], {}

    rc, out = _run([exe], timeout=300)
    if rc != 0:
        return ["PARITY 运行失败（rc=%s）" % (rc,)], {}
    got = _c_lines(out)

    v = u = x = 0
    detail = []
    for f in funcs:
        ref_line = ref.get(f.name)
        got_line = got.get(f.name, "")
        if ref_line is None:
            u += 1
            detail.append(("U", f.name, "-", got_line))
            continue
        if got_line == ref_line:
            v += 1
        else:
            x += 1
            detail.append(("X", f.name, ref_line, got_line))

    for tag, name, want, have in detail:
        if tag == "X":
            probs.append("PARITY 不一致 %s：参考[%s] 实际[%s]"
                         % (name, want[:70], have[:70]))

    stats = {"verified": v, "unverified": u, "mismatch": x,
             "total": len(funcs), "dir": d}
    if not keep:
        shutil.rmtree(d, ignore_errors=True)
        stats["dir"] = None
    return probs, stats


def _flat(x):
    """嵌套列表 -> 扁平（老夹具用 [[1,2],[3,4]]，新的用扁平 + shape）。"""
    if isinstance(x, (list, tuple)):
        out = []
        for v in x:
            out.extend(_flat(v))
        return out
    return [x]


def _arr_from(spec):
    """夹具里的 {"shape":[...], "data":[...]} -> mir_eval.Arr。"""
    data = _flat(spec.get("data") or [])
    shape = spec.get("shape")
    if not shape:
        shape = [len(data) or 1]
    return mir_eval.Arr(data, shape)


def _golden_args(case):
    """按算子把夹具输入映射成算子实参；不认识返回 None（= 未对拍）。"""
    op = case.get("operator")
    ins = case.get("inputs") or {}
    keys = list(ins)
    if op in ("OP-ADD", "OP-SUB", "OP-MUL", "OP-DIV", "OP-MATMUL"):
        if len(keys) < 2:
            return None
        return [_arr_from(ins[keys[0]]), _arr_from(ins[keys[1]])]
    if op in ("OP-SUM", "OP-MEAN", "OP-MAX", "OP-MIN",
              "OP-TRANSPOSE", "OP-FLATTEN"):
        return [_arr_from(ins[keys[0]])] if keys else None
    if op == "OP-INDEX":
        i = ins.get("i")
        if i is None:
            return None
        idx = i.get("data")[0] if isinstance(i, dict) else i
        return [_arr_from(ins[keys[0]]), idx]
    if op == "OP-SLICE":
        spec = case.get("slice") or {}
        return [_arr_from(ins[keys[0]]), int(spec.get("from", 1)),
                int(spec.get("to", 1))]
    if op in ("OP-MASK", "OP-FIND"):
        spec = case.get("mask") or {}
        return [_arr_from(ins[keys[0]]), int(spec.get("cmp", 0)),
                float(spec.get("k", 0))]
    return None


def check_goldens(gdir):
    """解释器跑每个夹具的算子语义，与 expected 比对。

    返回 (probs, stats)；probs 只装**真不一致**。
    """
    probs = []
    files = sorted(f for f in os.listdir(gdir) if f.endswith(".json"))
    v = u = x = 0
    skipped = []
    for fn in files:
        try:
            case = json.loads(io.open(os.path.join(gdir, fn),
                                      encoding="utf-8").read())
        except (IOError, OSError, ValueError):
            u += 1
            skipped.append(fn)
            continue
        op = case.get("operator")
        args = _golden_args(case)
        exp = case.get("expected") or {}
        if args is None or not exp:
            u += 1
            skipped.append(fn)
            continue
        try:
            got = mir_eval._apply_op(op, args)
        except Exception:        # noqa: BLE001 - 参考执行器不该因类型意外崩
            got = None
        if got is None:
            u += 1
            skipped.append(fn)
            continue
        want_shape = list(exp.get("shape") or [])
        want_data = [float(t) for t in _flat(exp.get("data") or [])]
        tol = case.get("tol") or {}
        eps = float(tol.get("abs", 1e-12))
        ok = (got.shape == want_shape and len(got.data) == len(want_data)
              and all(abs(a - b) <= eps + 1e-9 * abs(b)
                      for a, b in zip(got.data, want_data)))
        if ok:
            v += 1
        else:
            x += 1
            probs.append("GOLDEN 不一致 %s（%s）：解释器 shape=%r data=%r，"
                         "期望 shape=%r data=%r"
                         % (fn, op, got.shape, got.data[:6], want_shape,
                            want_data[:6]))
    if skipped:
        print("  未对拍夹具（%d）：%s" % (len(skipped), "、".join(skipped[:5])))
    print("PA1 已对拍 %d" % v)
    print("PA2 未对拍 %d" % u)
    if x:
        print("PA3 不一致 %d" % x)
    return probs, {"verified": v, "unverified": u, "mismatch": x,
                   "total": len(files)}


OCTAVE_CANDIDATES = ["octave-cli", "octave", "matlab"]


def _octave_cli():
    """找参考实现（Octave 优先，MATLAB 次之）。找不到返回 None。"""
    for name in OCTAVE_CANDIDATES:
        p = shutil.which(name)
        if p:
            return p
    local = os.environ.get("LOCALAPPDATA") or ""
    probes = [r"C:\Program Files\GNU Octave\Octave-*\mingw64\bin\octave-cli.exe",
              r"C:\Program Files\GNU Octave\Octave-*\bin\octave-cli.exe"]
    if local:
        # winget 默认装到用户目录下，不在 PATH 里
        probes.append(os.path.join(
            local, "Programs", "GNU Octave", "Octave-*", "mingw64", "bin",
            "octave-cli.exe"))
    for probe in probes:
        hits = glob.glob(probe)
        if hits:
            return hits[0]
    return None


def _matlab_literal(shape, values):
    """把"行主序 + 形状"变成 MATLAB 矩阵表达式。

    MATLAB 是列优先，直接写 [1 2 3; 4 5 6] 会把行主序数据放错位置；
    统一用 reshape(v, c, r).' 还原。
    """
    body = " ".join("%.17g" % v for v in values)
    if len(shape) == 1:
        return "[%s]" % body
    if len(shape) == 2:
        r, c = shape
        return "reshape([%s], %d, %d).'" % (body, c, r)
    return None


def _driver(funcs):
    """生成 MATLAB 驱动脚本：构造与 C 完全一致的输入，逐个调用并打印。"""
    out = ["more off;", "format long g;"]
    for f in funcs:
        if not f.args or not f.rets or f.unmapped:
            continue
        call_args = []
        ok = True
        for name, shape in f.args:
            if shape:
                n = 1
                for d in shape:
                    n *= d
                lit = _matlab_literal(shape, [float(i + 1) for i in range(n)])
                if lit is None:
                    ok = False
                    break
                out.append("%s = %s;" % (name, lit))
                call_args.append(name)
            else:
                out.append("%s = 2;" % name)   # 标量与 main.c 一致
                call_args.append(name)
        if not ok:
            continue
        lhs = "[%s]" % ", ".join(n for n, _ in f.rets) if len(f.rets) > 1 \
            else f.rets[0][0]
        out.append("try")
        out.append("  %s = %s(%s);" % (lhs, f.name, ", ".join(call_args)))
        parts = []
        for n, _ in f.rets:
            # 行主序输出：转置后按列取，正好等于 C 的行优先展开
            parts.append("sprintf('%%.17g ', reshape(%s.', 1, []))" % n)
        out.append("  fprintf('%s: %%s\\n', strjoin({%s}, ' | '));"
                   % (f.name, ", ".join(parts)))
        out.append("catch err")
        out.append("  fprintf('%s: ERROR %%s\\n', err.message);" % f.name)
        out.append("end")
    return "\n".join(out) + "\n"


def check_octave(mir_path, src_path):
    """L4：用 Octave/MATLAB 跑原始 .m，与解释器（和 C）三方对照。

    没有参考实现时**如实返回"未跑"**，绝不假装通过。
    """
    cli = _octave_cli()
    if not cli:
        print("PA4 未跑（缺 Octave / MATLAB —— 没有参考实现就没有 L4）")
        return [], {"ran": False}

    text = io.open(mir_path, encoding="utf-8").read()
    funcs = mir_eval.parse(text)
    from translate.mir import split_functions

    # **单文件**与**目录**两种源：真实工程是一堆 .m 互相调用
    if os.path.isdir(src_path):
        files = []
        for dp, dn, fn in os.walk(src_path):
            dn[:] = sorted(x for x in dn if not x.startswith("."))
            for f in sorted(fn):
                if f.lower().endswith(".m"):
                    files.append(os.path.join(dp, f))
    else:
        files = [src_path]

    # 只取"驱动会调用"的函数：无 unmapped 且有入参/返回值
    need = set(f.name for f in funcs
               if f.args and f.rets and not f.unmapped)
    d = tempfile.mkdtemp(prefix="m2c_l4_")

    # 撞名检测：一次 Octave 调用问清 exist()。
    # 为什么必须排除：YALMIP 自带 isnan.m / length.m，一旦进 addpath 就把
    # Octave 自己的库遮蔽掉，连 fileparts/strchr 都会挂 —— 那时测的不是我们的代码。
    collide = set()
    if need:
        probe = ";".join("printf('%%s %%d\\n','%s',exist('%s'))"
                         % (n, n) for n in sorted(need))
        rc0, out0 = _run([cli, "--no-gui", "--quiet", "--eval", probe],
                         cwd=tempfile.gettempdir(), timeout=300)
        if rc0 == 0:
            for ln in out0.splitlines():
                parts = ln.split()
                if len(parts) == 2 and parts[1] not in ("0",):
                    collide.add(parts[0])
    need -= collide

    written = set()
    for path in files:
        try:
            src = io.open(path, encoding="utf-8", errors="replace").read()
        except (IOError, OSError):
            continue
        src_lines = src.splitlines()
        for b in split_functions(src):
            if b["name"] in written or b["name"] not in need:
                continue
            written.add(b["name"])
            start = max(0, b["line0"] - 1)
            stop = max(b["line_nos"]) if b["line_nos"] else start
            body = "\n".join(src_lines[start:stop])
            io.open(os.path.join(d, b["name"] + ".m"), "w",
                    encoding="utf-8", newline="").write(body + "\nend\n")

    drv = os.path.join(d, "driver.m")
    io.open(drv, "w", encoding="utf-8", newline="").write(_driver(funcs))

    cmd = [cli, "--no-gui", "--quiet", "--eval", "run('%s')" % drv.replace("\\", "/")]
    if os.path.basename(cli).lower().startswith("matlab"):
        cmd = [cli, "-batch", "run('%s')" % drv.replace("\\", "/")]
    rc, out = _run(cmd, cwd=d, timeout=600)
    if rc != 0:
        tail = [ln for ln in out.strip().splitlines()
                if ln.strip() and "shadows" not in ln][-4:]
        print("PA4 失败（参考实现退出码 %s）：%s" % (rc, " / ".join(tail)))
        return ["L4 参考实现运行失败：%s" % out.strip().splitlines()[:2]], {"ran": False}

    ref = _c_lines(out)
    interp = _interp_lines(funcs)

    v = u = x = 0
    probs = []
    for f in funcs:
        r = ref.get(f.name)
        i = interp.get(f.name)
        if f.name in collide:
            u += 1
            continue
        if r is None or i is None or "ERROR" in (r or ""):
            u += 1
            continue
        # 参考实现的数字格式与解释器一致时才算同义
        if _same_values(r, i):
            v += 1
        else:
            x += 1
            probs.append("L4 不一致 %s：Octave[%s] 解释器[%s]"
                         % (f.name, r[:70], i[:70]))
    print("PA4 已对拍 %d（Octave ⇄ 解释器）" % v)
    print("PA4 未对拍 %d" % u)
    if x:
        print("PA4 不一致 %d" % x)
    shutil.rmtree(d, ignore_errors=True)
    return probs, {"ran": True, "verified": v, "unverified": u, "mismatch": x}


def _same_values(a, b):
    """按数值比较两行（容忍 %g 与 %.17g 的格式差异）。"""
    try:
        na = [float(t) for t in a.split(":", 1)[1].replace("|", " ").split()]
        nb = [float(t) for t in b.split(":", 1)[1].replace("|", " ").split()]
    except (IndexError, ValueError):
        return False
    if len(na) != len(nb):
        return False
    return all(abs(x - y) <= 1e-9 + 1e-9 * abs(y) for x, y in zip(na, nb))


def main(argv=None):
    ap = argparse.ArgumentParser(description="MIR 解释器 ⇄ C 对拍")
    ap.add_argument("--mir", default=None, help="MIR 文件路径")
    ap.add_argument("--src", default=None,
                    help="原始 .m（--octave 时用来跑参考实现）")
    ap.add_argument("--octave", action="store_true",
                    help="L4：用 Octave/MATLAB 跑真值并三方对照"
                         "（--src 可给单文件或目录）")
    ap.add_argument("--golden", default=None,
                    help="golden 夹具目录（解释器 ⇄ 夹具期望）")
    ap.add_argument("--show-unverified", type=int, default=5,
                    help="打印多少个未对拍的函数名")
    args = ap.parse_args(argv)

    if args.golden:
        probs, stats = check_goldens(args.golden)
        for p in probs:
            print("  - " + p)
        if probs:
            return 1
        return 0

    if args.octave:
        if not args.mir or not args.src:
            print("--octave 需要同时给 --mir 与 --src")
            return 2
        probs, st = check_octave(args.mir, args.src)
        for p in probs:
            print("  - " + p)
        return 1 if probs else 0

    if not args.mir:
        print("需要 --mir 或 --golden")
        return 2

    probs, stats = check(args.mir)
    if not stats:
        for p in probs:
            print("  - " + p)
        return 2                     # 缺输入 / 工具故障

    # 三个前缀各自单独成行：静态判据要能在源码里"看得见"
    print("PA1 已对拍 %d" % stats["verified"])
    print("PA2 未对拍 %d（原因：含 unmapped 语句或无形状入参）"
          % stats["unverified"])
    if stats["mismatch"]:
        print("PA3 不一致 %d" % stats["mismatch"])
    print("对拍合计 %d 个函数" % stats["total"])
    if stats["unverified"]:
        names = [d[1] for d in _detail_unverified(args.mir, args.show_unverified)]
        if names:
            print("  未对拍示例：%s（原因：含 unmapped 语句或无形状入参）"
                  % "、".join(names))
    for p in probs:
        print("  - " + p)
    if probs:
        return 1                     # PA3：两边都能算但结果不同
    return 0                         # 无 PA3


def _detail_unverified(mir_path, limit):
    text = io.open(mir_path, encoding="utf-8").read()
    funcs = mir_eval.parse(text)
    ref = _interp_lines(funcs)
    return [("U", f.name, "", "") for f in funcs if ref.get(f.name) is None][:limit]


if __name__ == "__main__":
    sys.exit(main())
