# -*- coding: utf-8 -*-
"""Q15 **端到端**：配置开关 → 生成器换算子 + 边界转换 → 运行出饱和值。

语义（R614 起）：**外部世界仍是 f64**，只在函数体内用 Q15 定标整数：

    调用方(f64) --> [from_f64] --> 函数体(Q15) --> [to_f64] --> 调用方(f64)

所以 `0.5 + 0.5 = 1.0` 在 Q15 里会饱和：`16384 + 16384 = 32768 > 32767`
→ `32767 / 32768 = 0.999969482421875`。

顺带回归一个真实坑：夹具文件带 **UTF-8 BOM** 时（Windows 记事本 / PowerShell 默认行为），
BOM 会粘在第一行参数名前面，导致该参数**静默退回默认值**。
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")

SRC = u"""function y = qadd(a, b)
% @m2c shape a 2
% @m2c shape b 2
% @m2c shape y 2
y = a + b;
end
"""

#: Q15 下 0.5 + 0.5 = 1.0 会饱和到这个值
SAT_ONE = "0.999969482421875"


def _cc():
    return shutil.which("gcc") or shutil.which("clang")


def _build_and_run(d, cc, fixed_point=True, bom=True):
    src = os.path.join(d, "src")
    os.makedirs(src, exist_ok=True)
    io.open(os.path.join(src, "qadd.m"), "w", encoding="utf-8").write(SRC)

    mir = os.path.join(d, "a.mir")
    subprocess.run([sys.executable, os.path.join(ROOT, "translate", "mir.py"),
                    src, "-o", mir], stdin=subprocess.DEVNULL,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                   timeout=600, check=True)

    gen = os.path.join(d, "gen")
    cmd = [M2C, "build", "--mir", mir, "--out", gen, "--name", "q"]
    if fixed_point:
        cmd += ["--fixed-point", "q15"]
    subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                   stderr=subprocess.STDOUT, timeout=900, check=True)

    exe = os.path.join(d, "q.exe")
    r = subprocess.run([cc, "-std=c99", "-O1",
                        "-I", os.path.join(gen, "include"),
                        "-I", os.path.join(RT, "include"),
                        os.path.join(gen, "src", "gen.c"),
                        os.path.join(gen, "src", "main.c"),
                        os.path.join(RT, "src", "mlc_runtime.c"),
                        os.path.join(RT, "src", "mlc_ops.c"),
                        "-o", exe, "-lm"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=900)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]

    # 夹具：BOM 由参数控制（默认带，模拟 Windows 编辑器）；值是**真实值**（[-1,1)）
    fx = os.path.join(d, "fx.txt")
    body = u"a = 0.5 0.5\nb = 0.5 -1.0\n".encode("utf-8")
    with open(fx, "wb") as f:
        f.write((b"\xef\xbb\xbf" if bom else b"") + body)

    out = subprocess.run([exe, fx], stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         timeout=120).stdout.decode("utf-8", "replace")
    gen_c = io.open(os.path.join(gen, "src", "gen", "qadd_m.c"),
                    encoding="utf-8").read()
    return out, gen_c


def _vals(out):
    return [x for x in out.replace(":", " ").split()
            if x.lstrip("-").replace(".", "").isdigit()]


@pytest.mark.skipif(_cc() is None or not os.path.isfile(M2C), reason="缺编译器或 m2c")
def test_q15_saturates_end_to_end():
    d = tempfile.mkdtemp(prefix="m2c_q15e2e_")
    try:
        out, gen_c = _build_and_run(d, _cc(), fixed_point=True, bom=True)
        # 三处接线都必须在
        assert "mlc_op_q15_from_f64" in gen_c, "入口必须做 f64 -> Q15"
        assert "mlc_op_q15_add" in gen_c, "应当发射 Q15 加法"
        assert "mlc_op_q15_to_f64" in gen_c, "出口必须做 Q15 -> f64"
        v = _vals(out)
        assert v[:2] == [SAT_ONE, "-0.5"], (
            "0.5+0.5 应饱和到 %s；0.5-1.0 应精确为 -0.5；实际：%s" % (SAT_ONE, out))
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.skipif(_cc() is None or not os.path.isfile(M2C), reason="缺编译器或 m2c")
def test_without_flag_uses_float_add():
    """反向：不加 `--fixed-point` 时是普通 f64 加法（1.0，不饱和，也不做边界转换）。"""
    d = tempfile.mkdtemp(prefix="m2c_q15off_")
    try:
        out, gen_c = _build_and_run(d, _cc(), fixed_point=False, bom=True)
        assert "mlc_op_q15" not in gen_c
        v = _vals(out)
        assert v[:2] == ["1", "-0.5"], out
    finally:
        shutil.rmtree(d, ignore_errors=True)
