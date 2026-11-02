# -*- coding: utf-8 -*-
"""Q15 **端到端**：配置开关 → 生成器换算子 → 运行出饱和值。

上一轮只验证到「生成的 C 里调用的是 `mlc_op_q15_add`」——那证明的是**接线**，
不是**数值**。要证明 Q15 真的生效，必须让 `20000 + 20000` 得到 `32767`。

顺带回归一个真实坑：夹具文件带 **UTF-8 BOM** 时（Windows 记事本 / PowerShell 默认行为），
BOM 会粘在第一行参数名前面，导致该参数**静默退回默认值** —— 表现是"数值莫名其妙不对"。
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

    # 夹具：BOM 由参数控制（默认带，模拟 Windows 编辑器）
    fx = os.path.join(d, "fx.txt")
    body = u"a = 20000 20000\nb = 20000 -32768\n".encode("utf-8")
    with open(fx, "wb") as f:
        f.write((b"\xef\xbb\xbf" if bom else b"") + body)

    out = subprocess.run([exe, fx], stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         timeout=120).stdout.decode("utf-8", "replace")
    gen_c = io.open(os.path.join(gen, "src", "gen", "qadd_m.c"),
                    encoding="utf-8").read()
    return out, gen_c


@pytest.mark.skipif(_cc() is None or not os.path.isfile(M2C), reason="缺编译器或 m2c")
def test_q15_saturates_end_to_end():
    d = tempfile.mkdtemp(prefix="m2c_q15e2e_")
    try:
        out, gen_c = _build_and_run(d, _cc(), fixed_point=True, bom=True)
        assert "mlc_op_q15_add" in gen_c, "应当发射 Q15 版本"
        vals = [x for x in out.split() if x.replace("-", "").replace(".", "").isdigit()]
        assert vals[:2] == ["32767", "-12768"], (
            "20000+20000 必须饱和到 32767，20000-32768 应为 -12768；实际：%s" % out)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.skipif(_cc() is None or not os.path.isfile(M2C), reason="缺编译器或 m2c")
def test_without_flag_uses_float_add():
    """反向：不加 `--fixed-point` 时必须是普通 f64 加法（40000，不饱和）。"""
    d = tempfile.mkdtemp(prefix="m2c_q15off_")
    try:
        out, gen_c = _build_and_run(d, _cc(), fixed_point=False, bom=True)
        assert "mlc_op_q15_add" not in gen_c
        vals = [x for x in out.split() if x.replace("-", "").replace(".", "").isdigit()]
        assert vals[:2] == ["40000", "-12768"], out
    finally:
        shutil.rmtree(d, ignore_errors=True)
