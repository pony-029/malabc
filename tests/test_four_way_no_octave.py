# -*- coding: utf-8 -*-
"""P6 判据：**没有 Octave 也要成立的多路对账**（位模式哈希 + 表示差异归一）。

## 为什么这条不能只写"有 Octave 时才对账"

设计文档 P6 的验收口径是「**无 Octave 机器上四路仍成立**」。现实是：
CI 与大多数开发机**都没有 Octave**。如果对账只在有 Octave 时才跑，
那么在绝大多数机器上它等于不存在 —— 而它恰恰是最贵的那条链路。

所以这里固定比较**三路**（都不需要 Octave）：

    A. MIR 直接喂 Rust VM            （`m2c run`）
    B. MIR → C → gcc → 运行          （生成的 C 自己）
    C. MIR → C → `cmir.py` 反推 MIR'  → VM 再跑一遍

## 为什么用**位模式哈希**而不是 "x != y"

浮点比较里 `0.0 == -0.0`、`nan != nan` —— 用 `!=` 会同时放过真差异、误报假差异。
位模式哈希把每个结果按 IEEE-754 字节串算 sha256：相等即**逐字节相同**。

**表示差异归一**（写清楚，不含糊）：
    * `-0.0` → `0.0`（同一个数，符号位不同）
    * 任何 NaN → 一个固定串（payload 不同但都是 NaN）
其余一律按原始字节比。
"""
import hashlib
import io
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
CMIR_PY = os.path.join(ROOT, "translate", "cmir.py")
CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
RT_INC = os.path.join(ROOT, "c_runtime", "include")
RT_SRC = [os.path.join(ROOT, "c_runtime", "src", "mlc_runtime.c"),
          os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c")]
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

#: 三种形态：一维归约 / 二维列均值 / 二维列和
#:
#: **故意只选无分支的样本**：`cmir` 不还原控制流（它自己如实报"控制流(未还原)"），
#: 所以含 `if`/`for` 的函数在"反推"这一路只能比到值、比不到结构。
#: 那是 cmir 的已知边界，不是本判据该踩的地方 —— 边界本身记在下面的 docstring 里。
CASES = ["snr", "colmean", "col2sum"]


def _run(cmd, timeout=300):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _parse_vals(out):
    """`name: v1 v2 v3` → [v1, v2, v3]（取第一行带冒号的）。"""
    for ln in out.splitlines():
        if ":" not in ln:
            continue
        body = ln.split(":", 1)[1]
        vals = []
        for tok in body.split():
            t = tok.lower()
            try:
                if "nan" in t:
                    vals.append(float("nan"))
                elif t in ("inf", "+inf"):
                    vals.append(float("inf"))
                elif t == "-inf":
                    vals.append(float("-inf"))
                else:
                    vals.append(float(tok))
            except ValueError:
                return None
        if vals:
            return vals
    return None


def _bit_hash(vals):
    """位模式哈希：逐元素 IEEE-754 字节 → sha256。

    归一化只做两件事（其余一律按原始字节）：
      * `-0.0` → `0.0`（同一个数，仅符号位不同）
      * 任何 NaN → 固定串（payload 不同，但都是 NaN）
    """
    if vals is None:
        return None
    buf = bytearray()
    for v in vals:
        if math.isnan(v):
            buf.extend(b"NAN")
            continue
        if v == 0.0:
            v = 0.0                       # -0.0 → 0.0
        buf.extend(struct.pack("<d", v))
    return hashlib.sha256(bytes(buf)).hexdigest()[:16]


def _paths(m):
    """跑三条路，返回 {路径名: 值列表}。"""
    d = tempfile.mkdtemp(prefix="p6_", dir=WORK if os.path.isdir(WORK) else None)
    try:
        mir = os.path.join(d, "a.mir")
        assert _run([sys.executable, MIR_PY, m, "-o", mir], 180).returncode == 0

        # A. VM 直接跑 MIR
        ra = _run([M2C, "run", "--mir", mir], 180)
        a = _parse_vals(ra.stdout.decode("utf-8", "replace"))

        # B. MIR → C → gcc → 运行
        g = os.path.join(d, "g")
        rb = _run([M2C, "build", "--mir", mir, "--out", g, "--name", "t"], 180)
        assert rb.returncode == 0, rb.stdout.decode("utf-8", "replace")[-300:]
        cc = shutil.which("gcc") or shutil.which("clang")
        exe = os.path.join(g, "t.exe" if os.name == "nt" else "t")
        rc = _run([cc, "-std=c99", "-O1", "-I", os.path.join(g, "include"),
                   "-I", RT_INC, os.path.join(g, "src", "gen.c"),
                   os.path.join(g, "src", "main.c")] + RT_SRC + ["-o", exe], 600)
        assert rc.returncode == 0, rc.stdout.decode("utf-8", "replace")[-400:]
        b = _parse_vals(_run([exe], 180).stdout.decode("utf-8", "replace"))

        # C. C → 反推 MIR → 比**算子序列**（结构一路）
        #
        # 注意：反推产物不带 `arg:`/`ret:` 声明（cmir 会如实报"跳过 N"），
        # 所以它**跑不了 VM**。这不是缺陷，是它的职责边界：它证明的是
        # "生成的 C 里还是那批算子"，不是"还能算出同一个数"。
        # 值的一致性由 A/B 两路（VM vs C）以位模式哈希保证。
        back = os.path.join(d, "back.mir")
        rc2 = _run([sys.executable, CMIR_PY, os.path.join(g, "src", "gen.c"),
                    "-o", back], 180)
        assert rc2.returncode == 0, rc2.stdout.decode("utf-8", "replace")[-300:]
        ops_a = sorted(l.split(":")[1] for l in
                       io.open(mir, encoding="utf-8").read().splitlines()
                       if l.startswith("op:"))
        ops_c = sorted(l.split(":")[1] for l in
                       io.open(back, encoding="utf-8").read().splitlines()
                       if l.startswith("op:"))
        return {"vm": a, "c": b, "ops_a": ops_a, "ops_c": ops_c}
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
@pytest.mark.parametrize("name", CASES)
def test_three_paths_agree_without_octave(name):
    src = os.path.join(CORPUS, name + ".m")
    if not os.path.isfile(src):
        pytest.skip("样本不存在：%s" % src)
    if not (shutil.which("gcc") or shutil.which("clang")):
        pytest.skip("没有 C 编译器")

    got = _paths(src)
    for k in ("vm", "c"):
        assert got[k] is not None, "%s 路径没有产出数值" % k

    hv, hc = _bit_hash(got["vm"]), _bit_hash(got["c"])
    assert hv == hc, \
        "VM 与 C 位模式不同（%s vs %s）\n vm=%r\n c =%r" % (
            hv, hc, got["vm"], got["c"])

    assert got["ops_a"], "原 MIR 里没有算子"
    assert got["ops_a"] == got["ops_c"], \
        "反推 MIR 的算子序列与原始不同：\n 原始 %r\n 反推 %r" % (
            got["ops_a"][:8], got["ops_c"][:8])


def test_backparsed_cross_file_calls():
    """跨函数工程的**调用点**要能被反推还原（R799）。

    样本用 `translate/examples/proj`（addone / scale2 / combine 互调）。
    生成物里调用点是 `st = m2c_addone(x, y);`，输出在**末位**、实参可能带 `*`，
    所以反推要：剥 `&`/`*`、把末位放到 MIR 的第二位。

    ⚠ **只比结构不比数值**：Rust VM 不做函数链接（`VM 不做链接`），
    所以两路都会在同一处报错 —— 那正是"行为等价"的证据，不是缺陷。
    """
    proj = os.path.join(ROOT, "translate", "examples", "proj")
    if not os.path.isdir(proj) or not os.path.isfile(M2C):
        pytest.skip("缺 proj 样本或 m2c 未构建")

    d = tempfile.mkdtemp(prefix="p6c_", dir=WORK if os.path.isdir(WORK) else None)
    try:
        mir = os.path.join(d, "proj.mir")
        assert _run([sys.executable, MIR_PY, proj, "-o", mir, "--recursive"],
                    180).returncode == 0
        g = os.path.join(d, "g")
        assert _run([M2C, "build", "--mir", mir, "--out", g, "--name", "p"],
                    180).returncode == 0

        # 每个源文件一份 .c：逐份反推后拼成一份
        parts = []
        for base, _dirs, files in os.walk(g):
            for f in sorted(files):
                if not f.endswith(".c") or f in ("main.c", "selftest.c"):
                    continue
                c = os.path.join(base, f)
                if "m2c_" not in io.open(c, encoding="utf-8").read():
                    continue
                out = c + ".mir"
                assert _run([sys.executable, CMIR_PY, c, "-o", out],
                            180).returncode == 0
                txt = io.open(out, encoding="utf-8").read()
                if parts:
                    txt = "\n".join(l for l in txt.splitlines()
                                    if not l.startswith("version"))
                parts.append(txt.rstrip())
        assert parts, "没有找到任何生成 .c"

        back = io.open(mir, encoding="utf-8").read()
        want = sorted(re.findall(r"^call:[\w:]+$", back, re.M))
        got = sorted(re.findall(r"^call:[\w:]+$", "\n".join(parts), re.M))
        assert want, "原 MIR 里没有 call:（样本选错了）"
        assert got == want, "调用点还原不一致：\n 原始 %r\n 反推 %r" % (want, got)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_hash_normalizes_only_representation():
    """归一只能是**表示**差异（-0.0 / NaN），不能顺手抹掉真实差异。"""
    assert _bit_hash([0.0]) == _bit_hash([-0.0]), "-0.0 与 0.0 应视为同一个数"
    assert _bit_hash([float("nan")]) == _bit_hash([float("nan")])
    assert _bit_hash([1.0]) != _bit_hash([1.0 + 1e-12]), "真差异必须能区分"
    assert _bit_hash([1.0]) != _bit_hash([-1.0])


@pytest.mark.parametrize("name", ["colmean", "iseqtest", "colmax_loop", "while_acc"])
def test_backparsed_mir_reproduces_values(name):
    """反推 MIR 必须**可执行且数值复现**（R793 + R794）。

    修的三处：`re.M`（签名匹配）、函数名以 C 签名为准、局部量 `var:` 声明。
    第四处才是数值复现的关键：**形状元数据**。C 的签名表达不了 `arg:A:f64:3,2`，
    于是生成器现在把它写成注释、`cmir` 读回来 —— 没有它，VM 用默认值填形参，
    `colmean` 会从 `1 3 5` 静默变成 `1 2 3`。

    R795 起连**控制流**也还原：`if`/`else`、`for`、标量 `setb:`、`int64_t` 局部量，
    并且两种算子写法（裸调用 / 守卫式）都要认。
    因此三个样本覆盖三条不同路径：纯算子 / if 分支 / for 循环。
    """
    if not os.path.isfile(M2C):
        pytest.skip("m2c 未构建")
    src = os.path.join(CORPUS, name + ".m")
    if not os.path.isfile(src):
        pytest.skip("样本不存在：%s" % src)

    d = tempfile.mkdtemp(prefix="p6x_", dir=WORK if os.path.isdir(WORK) else None)
    try:
        mir = os.path.join(d, "a.mir")
        assert _run([sys.executable, MIR_PY, src, "-o", mir], 180).returncode == 0
        g = os.path.join(d, "g")
        assert _run([M2C, "build", "--mir", mir, "--out", g, "--name", "t"],
                    180).returncode == 0
        back = os.path.join(d, "back.mir")
        assert _run([sys.executable, CMIR_PY, os.path.join(g, "src", "gen.c"),
                     "-o", back], 180).returncode == 0

        txt = io.open(back, encoding="utf-8").read()
        # 形状必须被读回（不同样本的形参名/维度不同，只要求"带维度的 arg 行"存在）
        assert re.search(r"^arg:\w+:f64:[\d,]+$", txt, re.M), \
            "反推 MIR 没恢复形参形状（生成器的 `arg-shape` 注释没被读回？）：\n%s" \
            % txt[:300]

        a_out = _run([M2C, "run", "--mir", mir], 180).stdout.decode("utf-8", "replace")
        b_out = _run([M2C, "run", "--mir", back], 180).stdout.decode("utf-8", "replace")
        va, vb = _parse_vals(a_out), _parse_vals(b_out)
        assert va is not None and vb is not None, \
            "有一路没产出数值：\n 原=%s\n 反推=%s" % (a_out[:120], b_out[:120])
        assert _bit_hash(va) == _bit_hash(vb), \
            "反推数值不还原：原 %r vs 反推 %r" % (va, vb)
    finally:
        shutil.rmtree(d, ignore_errors=True)
