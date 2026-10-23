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
    lines, names = [], []
    for name, dims in specs:
        n = 1
        for d in dims:
            n *= d
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

    t_c = _best(lambda: _run([exe])[0], repeat)

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

    print("用例 %s ｜ 重复 %d 次取最小" % (os.path.basename(src), repeat))
    print("  生成的 C（含启动）：%8.1f ms" % ms(t_c))
    print("  Octave（含启动）  ：%8.1f ms" % ms(t_oct))
    print("  Octave 启动基线    ：%8.1f ms" % ms(t_base))
    if t_c > 0:
        print("  含启动比值（Octave/C）：%.1fx" % (t_oct / t_c))
    net_o = max(0.0, t_oct - t_base)
    if net_o > 0 and t_c > 0:
        print("  扣除启动（Octave 净算 %.1f ms）：%.1fx"
              % (ms(net_o), net_o / t_c))
    if not keep:
        print("  （临时产物在 %s，未清理 —— 需要复现可直接用）" % d)
    return 0


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
