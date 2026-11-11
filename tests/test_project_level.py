# -*- coding: utf-8 -*-
"""**工程级**判据（P0）：三个互相调用的 `.m` → C 工程 → 编译 → 运行 → 数值正确。

## 为什么这条此前不存在

现有 41 道门几乎全是**函数级或语法级**：单函数转得对、单函数算得对。
而"把一堆函数装成工程"是另一件事 —— 跨文件调用、头文件原型、链接顺序。

设计文档 §八 写明：

    给定 3 函数互相调用 → m2c 生成工程 → gcc → 运行 → 输出等于手算值
    这条判据今天会红，而这正是它的价值。

**实测（2026-11-11）它已经绿了**：`translate/examples/proj` 的
`combine → addone / scale2` 链跑出 `4 8 12`，与手算 `(x+x)*2` 一致。
（R720 当时红的那个例子是 `twice → scale`，多一个实参，属另一形态。）

判据分三层，任一层失败都指名道姓：
    P0a `mir.py <目录>` 成功，且三个函数都进了同一份 MIR
    P0b `m2c build` + `gcc` 成功（工程骨架、头文件、每函数 .c 都对）
    P0c 运行数值 == 手算值（这才是"工程能跑"）
"""
import io
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
SRC = os.path.join(ROOT, "translate", "examples", "proj")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
RT_INC = os.path.join(ROOT, "c_runtime", "include")
RT_SRC = [os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
          os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c")]
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

#: 手算值：combine(x) = scale2(addone(x)) = (x + x) * 2，x = 1,2,3
EXPECT = {"addone": "2 4 6", "scale2": "2 4 6", "combine": "4 8 12"}


def _run(cmd, timeout=300):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


@pytest.fixture(scope="module")
def outputs():
    if not os.path.isfile(M2C):
        pytest.skip("m2c 未构建")
    cc = shutil.which("gcc") or shutil.which("clang")
    if not cc:
        pytest.skip("没有 C 编译器")

    d = WORK if os.path.isdir(WORK) else None
    import tempfile
    d = tempfile.mkdtemp(prefix="p0_", dir=d)
    try:
        mir = os.path.join(d, "p.mir")
        r = _run([sys.executable, MIR_PY, SRC, "-o", mir], 120)
        assert r.returncode == 0, "P0a MIR 生成失败：%s" % \
            r.stdout.decode("utf-8", "replace")[-300:]
        text = io.open(mir, encoding="utf-8").read()
        for fn in EXPECT:
            assert "func:%s" % fn in text, "P0a 缺函数 %s（目录模式没合进同一份 MIR）" % fn

        g = os.path.join(d, "g")
        r = _run([M2C, "build", "--mir", mir, "--out", g, "--name", "p"], 180)
        assert r.returncode == 0, "P0b m2c build 失败：%s" % \
            r.stdout.decode("utf-8", "replace")[-300:]

        exe = os.path.join(g, "p.exe" if os.name == "nt" else "p")
        r = _run([cc, "-std=c99", "-O1", "-I", os.path.join(g, "include"),
                  "-I", RT_INC, os.path.join(g, "src", "gen.c"),
                  os.path.join(g, "src", "main.c")] + RT_SRC + ["-o", exe], 600)
        assert r.returncode == 0, "P0b gcc 失败：%s" % \
            r.stdout.decode("utf-8", "replace")[-400:]

        out = _run([exe], 120).stdout.decode("utf-8", "replace")
        return out
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.parametrize("name,want", sorted(EXPECT.items()))
def test_project_runs_correctly(outputs, name, want):
    """P0c：三个函数的输出都必须等于手算值。"""
    got = None
    for ln in outputs.splitlines():
        if ln.startswith(name + ":"):
            got = " ".join(ln.split(":", 1)[1].split())
            break
    assert got is not None, "P0c 没有 %s 的输出：\n%s" % (name, outputs[-500:])
    assert got == want, "P0c %s：得 %r 期望 %r" % (name, got, want)


def test_no_unimplemented(outputs):
    """工程里只要有一个 `unimplemented`，就等于"装得起来但跑不动"。"""
    bad = [ln.strip() for ln in outputs.splitlines() if "unimplemented" in ln]
    assert not bad, "P0c 有函数未实现：%r" % bad[:4]


#: 第二形态：跨文件调用的实参是**字面量**（`scale(x, 2)`）。
LITERAL_SRC = {
    # `k` 必须是**标量形参**（`% @m2c i64 k`）—— 字面量实参只有配标量形参才合法；
    # 配数组形参需要先落 1 元临时量，那是另一种形态，见文档「P0 实测」。
    "scale.m": "function y = scale(x, k)\n% @m2c shape x 3\n% @m2c shape y 3\n"
               "% @m2c i64 k\ny = x .* k;\nend\n",
    "twice.m": "function y = twice(x)\n% @m2c shape x 3\n% @m2c shape y 3\n"
               "y = scale(x, 2);\nend\n",
}


def test_literal_arg_cross_file_call():
    """`twice → scale(x, 2)` 必须能生成并算对（= 2 4 6）。"""
    if not os.path.isfile(M2C):
        pytest.skip("m2c 未构建")
    cc = shutil.which("gcc") or shutil.which("clang")
    if not cc:
        pytest.skip("没有 C 编译器")

    import tempfile
    d = tempfile.mkdtemp(prefix="p0d_", dir=WORK if os.path.isdir(WORK) else None)
    try:
        src = os.path.join(d, "src")
        os.makedirs(src)
        for n, body in LITERAL_SRC.items():
            io.open(os.path.join(src, n), "w", encoding="utf-8",
                    newline="\n").write(body)
        mir = os.path.join(d, "p.mir")
        r = _run([sys.executable, MIR_PY, src, "-o", mir], 120)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-300:]

        g = os.path.join(d, "g")
        r = _run([M2C, "build", "--mir", mir, "--out", g, "--name", "p"], 180)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-300:]

        exe = os.path.join(g, "p.exe" if os.name == "nt" else "p")
        r = _run([cc, "-std=c99", "-O1", "-I", os.path.join(g, "include"),
                  "-I", RT_INC, os.path.join(g, "src", "gen.c"),
                  os.path.join(g, "src", "main.c")] + RT_SRC + ["-o", exe], 600)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-400:]

        out = _run([exe], 120).stdout.decode("utf-8", "replace")
        assert "unimplemented" not in out, "仍有 unimplemented：\n%s" % out[-300:]
        got = None
        for ln in out.splitlines():
            if ln.startswith("twice:"):
                got = " ".join(ln.split(":", 1)[1].split())
        assert got == "2 4 6", "twice 得 %r 期望 '2 4 6'" % got
    finally:
        shutil.rmtree(d, ignore_errors=True)
