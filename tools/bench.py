# -*- coding: utf-8 -*-
"""bench —— 量「生成的 C」相对「参考实现（Octave）」的耗时。

为什么需要它：这是一个**移植**工具。Rosetta 这类翻译层最常被问的是
"慢多少倍"，而我们此前**一次也没测过** —— 只有"能编译、能算对"。
没有这个数字，"移植"到底换来了什么就说不清。

方法（都含进程启动，如实标注）：
    1. 同一份 `.m` 转 MIR -> 生成 C -> 编译 -> 连跑 N 次取最小值
    2. 同一份 `.m` 用 Octave 连跑 N 次取最小值，另测一次空跑作为启动开销基线
    3. 输出「含启动」与「扣除启动」两种比值；单次太快（<50ms）时加大重复次数

用法：
    python tools/bench.py translate/examples/numeric/bench_loop.m --repeat 3
    python tools/bench.py <file.m> --repeat 5 --keep    # --keep 保留临时产物

退出码：
    0  正常输出（本工具不判红）
    2  参数/依赖不可用（缺 Octave、编译失败等）
"""
import io
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")


def _octave():
    for name in ("octave-cli", "octave"):
        p = subprocess.run(["where" if os.name == "nt" else "which", name],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=30)
        if p.returncode == 0:
            return p.stdout.decode("utf-8", "replace").splitlines()[0].strip()
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "Programs", "GNU Octave")
    if os.path.isdir(base):
        for d in os.listdir(base):
            p = os.path.join(base, d, "mingw64", "bin", "octave-cli.exe")
            if os.path.isfile(p):
                return p
    return None


def _run(cmd, cwd=None, timeout=1200):
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=timeout)
    return time.perf_counter() - t0, p.returncode, p.stdout.decode("utf-8", "replace")


def _best(fn, n):
    ts = []
    for _ in range(max(1, n)):
        ts.append(fn())
    return min(ts)


def _inputs_from_source(src):
    """从 `.m` 的 `% @m2c shape <name> <dims>` 注解生成 Octave 构造语句。

    与生成的 main.c 保持同一规则：行主序、`a[i] = i + 1`。
    返回 (构造语句列表, 调用实参列表)；没有注解就返回 ([], [])。
    """
    import re
    specs = []
    for ln in io.open(src, encoding="utf-8", errors="replace").read().splitlines():
        m = re.match(r"\s*%\s*@m2c\s+shape\s+([A-Za-z_]\w*)\s+([\d,\s]+)",
                     ln)
        if m:
            dims = [int(x) for x in m.group(2).replace(" ", "").split(",") if x]
            specs.append((m.group(1), dims))
    # 从 `function [r = ]f(a, b)` 里取出入参名；返回值不能当输入
    import re as _re
    argnames = None
    for ln in io.open(src, encoding="utf-8", errors="replace").read().splitlines():
        m = _re.match(r"\s*function\s+(?:\w+\s*=\s*)?(\w+)\s*\(([^)]*)\)",
                      ln)
        if m:
            argnames = [a.strip() for a in m.group(2).split(",") if a.strip()]
            break
    if argnames is not None:
        specs = [sp for sp in specs if sp[0] in argnames]

    lines, names = [], []
    for name, dims in specs:
        n = 1
        for d in dims:
            n *= d
        if len(dims) == 1:
            # 一维：用列向量（与 C 侧一维数组等价，`x(i)` 语义相同）
            lines.append("%s = reshape(1:%d, [%d, 1]);" % (name, n, n))
        else:
            lines.append("%s = reshape(1:%d, [%s]);"
                         % (name, n, ", ".join(str(d) for d in dims)))
        names.append(name)
    return lines, names


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    src = argv[0]
    repeat = int(argv[argv.index("--repeat") + 1]) if "--repeat" in argv else 3
    keep = "--keep" in argv
    if not os.path.isfile(src):
        print("找不到 %s" % src)
        return 2

    oct_cli = _octave()
    if not oct_cli:
        print("PA5 未跑（缺 Octave，无法给参考实现的耗时）")
        return 2

    d = tempfile.mkdtemp(prefix="m2c_bench_")
    mir = os.path.join(d, "b.mir")
    t, rc, out = _run([sys.executable, os.path.join(ROOT, "translate", "mir.py"),
                       src, "-o", mir])
    if rc != 0:
        print("转换失败：%s" % out.strip()[-200:])
        return 2

    gen = os.path.join(d, "gen")
    t, rc, out = _run([M2C, "build", "--mir", mir, "--out", gen,
                       "--name", "bench"])
    if rc != 0:
        print("生成失败：%s" % out.strip()[-200:])
        return 2

    exe = os.path.join(gen, "bench.exe")
    cc = _c_compiler()
    if not cc:
        print("PA5 未跑（缺 C 编译器）")
        return 2
    t, rc, out = _run([cc, "-std=c99", "-O2",
                       "-I", os.path.join(gen, "include"),
                       "-I", os.path.join(ROOT, "c_runtime", "include"),
                       os.path.join(gen, "src", "gen.c"),
                       os.path.join(gen, "src", "main.c"),
                       os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
                       os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c"),
                       "-o", exe])
    if rc != 0:
        print("编译失败：%s" % out.strip()[-300:])
        return 2

    # 先验证 C 真的算出了结果（不是 unimplemented 桩），否则数字毫无意义
    _, rc_chk, out_chk = _run([exe])
    if "unimplemented" in out_chk or "skipped" in out_chk:
        line = [ln for ln in out_chk.splitlines()
                if "unimplemented" in ln or "skipped" in ln][:1]
        print("PA5 拒绝报告：生成的 C 没有真正计算 —— %s"
              % (line[0].strip()[:80] if line else "unimplemented"))
        print("  （基准必须先算得出，再算得快；否则测到的是启动时间）")
        return 2

    t_c = _best(lambda: _run([exe])[0], repeat)

    # ---- 进程内计时（首选）：不含启动、不含输入构造 ----
    reps = int(argv[argv.index("--reps") + 1]) if "--reps" in argv else 20
    fn, fn_args, fn_rets = _sig_of(mir)
    c_in, c_val = (_inproc_c(gen, fn, fn_args, fn_rets, reps, cc, d, "bench")
                   if fn else (0.0, None))
    o_in, o_val = (_inproc_octave(src, oct_cli, d, reps)
                   if fn else (0.0, None))

    # 空载对照：同目录下的 bench_null.m（同输入、只做一次廉价运算）
    t_null = 0.0
    null_src = os.path.join(os.path.dirname(os.path.abspath(src)),
                            "bench_null.m")
    if os.path.isfile(null_src) and _shapes_of(null_src) == _shapes_of(src):
        t_null = _build_and_time(null_src, d, "null", repeat) or 0.0

    # Octave：同一份 .m，输入构造与 main.c 一致（a[i]=i+1）
    drv = os.path.join(d, "drv.m")
    name = os.path.splitext(os.path.basename(src))[0]
    setup, names = _inputs_from_source(src)
    if not names:
        setup, names = ["x = 1:1000;"], ["x"]        # 兜底：单参数一维
    body = "\n".join(setup) + "\n%s(%s);\n" % (name, ", ".join(names))
    io.open(drv, "w", encoding="utf-8", newline="").write(
        "addpath('%s');\nmore off;\n%s"
        % (os.path.dirname(os.path.abspath(src)).replace("\\", "/"), body))
    t_oct = _best(lambda: _run([oct_cli, "--no-gui", "--quiet", "--eval",
                                "run('%s')" % drv.replace("\\", "/")], cwd=d)[0],
                  repeat)
    # 启动基线：空 eval
    t_base = _best(lambda: _run([oct_cli, "--no-gui", "--quiet", "--eval", "1;"],
                                cwd=d)[0], repeat)

    def ms(x):
        return x * 1000.0

    print("用例 %s ｜ 整进程重复 %d 次；进程内 %d 次调用/样本"
          % (os.path.basename(src), repeat, reps))
    # 先判「算出来的对不对」，再报耗时 —— 顺序不能反
    if c_val is not None and o_val is not None:
        tol = 1e-9 * max(1.0, abs(o_val))
        if abs(c_val - o_val) > tol:
            print("PA5 拒绝报告：结果不一致 —— C %.17g ／ Octave %.17g"
                  % (c_val, o_val))
            print("  （耗时只有在两边算出同一个值时才可比）")
            return 2
        print("  结果一致：sum(y) = %.10g" % c_val)
    elif c_val is not None:
        print("  结果指纹：sum(y) = %.10g（Octave 侧未取到，未做一致性判定）"
              % c_val)

    if c_in > 0 and o_in > 0:
        print("  【进程内】C %.3f ms ／ Octave %.3f ms：%.1fx"
              % (c_in, o_in, o_in / c_in))
    elif c_in > 0:
        print("  【进程内 C】%.3f ms（Octave 侧进程内不可用，退回其净算口径）"
              % c_in)
    else:
        print("  （进程内计时不可用，退回整进程口径）")
    print("  生成的 C（含启动）：%8.1f ms" % ms(t_c))
    print("  Octave（含启动）  ：%8.1f ms" % ms(t_oct))
    print("  Octave 启动基线    ：%8.1f ms" % ms(t_base))
    if t_c > 0:
        print("  含启动比值（Octave/C）：%.1fx" % (t_oct / t_c))
    net_o = max(0.0, t_oct - t_base)
    if net_o > 0 and t_c > 0:
        print("  扣除启动（Octave 净算 %.1f ms）：%.1fx"
              % (ms(net_o), net_o / t_c))
    if c_in > 0 and net_o > 0:
        print("  【C 进程内 %.3f ms ／ Octave 净算 %.1f ms】：%.1fx"
              % (c_in, ms(net_o), net_o / (c_in / 1000.0)))
    if t_null > 0:
        # 只扣 C 侧：Octave 的空载测量噪声比被测还大，拿它做减法会得到负数
        net_c = max(0.0, t_c - t_null)
        print("  C 侧空载（同输入、只做一次加法）：%.1f ms" % ms(t_null))
        if net_c > 0 and net_o > 0:
            print("  只算被测运算（C %.1f ms ／ Octave 净 %.1f ms）：%.1fx"
                  % (ms(net_c), ms(net_o), net_o / net_c))
    if not keep:
        print("  （临时产物在 %s，未清理 —— 需要复现可直接用）" % d)
    return 0


def _sig_of(mir_path):
    """从 MIR 取函数名 / 参数 / 返回值（含形状），用于生成驱动。"""
    import re
    name, args, rets = None, [], []
    for ln in io.open(mir_path, encoding="utf-8", errors="replace").read().splitlines():
        if ln.startswith("func:") and name is None:
            name = ln[5:].strip()
        elif ln.startswith("arg:"):
            m = re.match(r"arg:(\w+):(\w+):?([\d,]*)", ln)
            if m:
                dims = [int(x) for x in m.group(3).split(",") if x]
                args.append((m.group(1), dims))
        elif ln.startswith("ret:"):
            m = re.match(r"ret:(\w+):(\w+):?([\d,]*)", ln)
            if m:
                dims = [int(x) for x in m.group(3).split(",") if x]
                rets.append((m.group(1), dims))
        elif ln.startswith("# srcfile:"):
            break
    return name, args, rets


def _driver_c(name, args, rets, reps, hdr):
    """生成 C 驱动：构造一次 -> 预热 -> 计时 reps 次。"""
    L = ['#include <stdio.h>', '#include <time.h>', '#include "mlc.h"',
         '#include "mlc_ops.h"', '#include "%s.h"' % hdr, '',
         'int main(void)', '{', '    clock_t t0, t1;', '    int k;']
    for a, dims in args:
        dims = dims or [1]
        dim_c = ", ".join(str(d) for d in dims)
        L.append('    mlc_array %s;' % a)
        L.append('    if (mlc_array_init(&%s, MLC_F64, %d, '
                 '(int64_t[]){%s}) != MLC_OK) return 2;' % (a, len(dims), dim_c))
        L.append('    { int64_t i, n = mlc_array_numel(&%s); '
                 'for (i = 0; i < n; ++i) ((double *)%s.data)[i] = (double)(i + 1); }'
                 % (a, a))
    rname, rdims = (rets[0] if rets else ("y", [1]))
    rdims = rdims or [1]
    L.append('    mlc_array %s;' % rname)
    L.append('    if (mlc_array_init(&%s, MLC_F64, %d, (int64_t[]){%s}) != MLC_OK) '
             'return 2;' % (rname, len(rdims),
                            ", ".join(str(d) for d in rdims)))
    call = "m2c_%s(%s)" % (name, ", ".join(["%s" % a for a, _ in args] +
                                           ["&%s" % rname]))
    L.append('    if (%s != MLC_OK) return 3;' % call)      # 预热
    L.append('    t0 = clock();')
    L.append('    for (k = 0; k < %d; ++k) {' % reps)
    L.append('        if (%s != MLC_OK) return 3;' % call)
    L.append('    }')
    L.append('    t1 = clock();')
    L.append('    { int64_t i2, n2 = mlc_array_numel(&%s); double acc = 0.0;'
             % rname)
    L.append('      for (i2 = 0; i2 < n2; ++i2) acc += ((double *)%s.data)[i2];'
             % rname)
    L.append('      printf("VAL %.17g\\n", acc); }')
    L.append('    printf("%.3f\\n", 1000.0 * (double)(t1 - t0) / CLOCKS_PER_SEC);')
    L.append('    return 0;')
    L.append('}')
    return "\n".join(L)


def _inproc_c(build_dir, name, args, rets, reps, cc, workdir, hdr):
    """编译并运行进程内驱动，返回毫秒（每次调用）。失败返回 0。"""
    src = os.path.join(workdir, "drv_%s.c" % name)
    exe = os.path.join(workdir, "drv_%s.exe" % name)
    io.open(src, "w", encoding="utf-8", newline="").write(
        _driver_c(name, args, rets, reps, hdr))
    rc = _run([cc, "-std=c99", "-O2",
               "-I", os.path.join(build_dir, "include"),
               "-I", os.path.join(ROOT, "c_runtime", "include"),
               src,
               os.path.join(build_dir, "src", "gen.c"),
               os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
               os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c"),
               "-o", exe])[1]
    if rc != 0:
        return 0.0
    t, rc, out = _run([exe])
    if rc != 0:
        return 0.0, None
    lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
    val = None
    ms = 0.0
    for ln in lines:
        if ln.startswith("VAL "):
            try:
                val = float(ln[4:])
            except ValueError:
                val = None
    try:
        ms = float(lines[-1]) / max(1, reps)
    except (ValueError, IndexError):
        ms = 0.0
    return ms, val


def _inproc_octave(src, oct_cli, workdir, reps):
    """Octave 侧进程内计时：构造一次、预热、tic/toc 包 N 次。"""
    name = os.path.splitext(os.path.basename(src))[0]
    setup, names = _inputs_from_source(src)
    if not names:
        return 0.0
    call = "%s(%s);" % (name, ", ".join(names))
    body = "\n".join([""] + setup +
                      ["vv = %s" % call,            # 预热，同时拿到结果
                       "fprintf('VAL %.17g\\n', sum(vv(:)));",
                       "tic;",
                       "for kk = 1:%d, vv = %s end" % (reps, call),
                       "t = toc * 1000 / %d;" % reps,
                       "fprintf('%.3f\\n', t);"])
    drv = os.path.join(workdir, "drvi_%s.m" % name)
    io.open(drv, "w", encoding="utf-8", newline="").write(
        "addpath('%s');\nmore off;%s"
        % (os.path.dirname(os.path.abspath(src)).replace("\\", "/"), body))
    t, rc, out = _run([oct_cli, "--no-gui", "--quiet", "--eval",
                       "run('%s')" % drv.replace("\\", "/")], cwd=workdir)
    if rc != 0:
        return 0.0, None
    lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
    val = None
    for ln in lines:
        if ln.startswith("VAL "):
            try:
                val = float(ln[4:])
            except ValueError:
                val = None
    ms = 0.0
    for ln in reversed(lines):
        try:
            ms = float(ln)
            break
        except ValueError:
            continue
    return ms, val


def _shapes_of(src):
    """取 `.m` 里的 `% @m2c shape` 列表（用于判断两个用例的输入是否可比）。"""
    import re
    out = []
    for ln in io.open(src, encoding="utf-8", errors="replace").read().splitlines():
        m = re.match(r"\s*%\s*@m2c\s+shape\s+([A-Za-z_]\w*)\s+([\d,\s]+)", ln)
        if m:
            dims = tuple(int(x) for x in m.group(2).replace(" ", "").split(",") if x)
            out.append((m.group(1), dims))
    return sorted(out)


def _build_and_time(src, workdir, tag, repeat):
    """把某个 .m 生成 C 并计时（用于空载对照）。失败返回 0。"""
    mir = os.path.join(workdir, "%s.mir" % tag)
    gen = os.path.join(workdir, "gen_%s" % tag)
    if _run([sys.executable, os.path.join(ROOT, "translate", "mir.py"),
             src, "-o", mir])[1] != 0:
        return 0.0
    if _run([M2C, "build", "--mir", mir, "--out", gen,
             "--name", tag])[1] != 0:
        return 0.0
    cc = _c_compiler()
    if not cc:
        return 0.0
    exe = os.path.join(gen, "%s.exe" % tag)
    if _run([cc, "-std=c99", "-O2",
             "-I", os.path.join(gen, "include"),
             "-I", os.path.join(ROOT, "c_runtime", "include"),
             os.path.join(gen, "src", "gen.c"),
             os.path.join(gen, "src", "main.c"),
             os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
             os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c"),
             "-o", exe])[1] != 0:
        return 0.0
    return _best(lambda: _run([exe])[0], repeat)


def _octave_time(src, oct_cli, workdir, repeat):
    """某个 .m 在 Octave 里的耗时（用于空载对照）。失败返回 0。"""
    name = os.path.splitext(os.path.basename(src))[0]
    setup, names = _inputs_from_source(src)
    if not names:
        return 0.0
    drv = os.path.join(workdir, "drv_%s.m" % name)
    body = "\n".join(setup) + "\n%s(%s);\n" % (name, ", ".join(names))
    io.open(drv, "w", encoding="utf-8", newline="").write(
        "addpath('%s');\nmore off;\n%s"
        % (os.path.dirname(os.path.abspath(src)).replace("\\", "/"), body))
    return _best(lambda: _run([oct_cli, "--no-gui", "--quiet", "--eval",
                               "run('%s')" % drv.replace("\\", "/")],
                              cwd=workdir)[0], repeat)


def _c_compiler():
    for name in ("gcc", "clang", "cc"):
        p = subprocess.run(["where" if os.name == "nt" else "which", name],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=30)
        if p.returncode == 0:
            return p.stdout.decode("utf-8", "replace").splitlines()[0].strip()
    return None


if __name__ == "__main__":
    sys.exit(main())
