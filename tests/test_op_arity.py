# -*- coding: utf-8 -*-
"""算子元数（arity）交叉校验：**MIR 里给的实参个数必须等于 C 原型的形参个数 − 1**。

## 为什么需要这条

R813 里出现过 `op:OP-MIN:y:x:x` —— 归约算子被塞了 2 个输入。后果非常隐蔽：

* 生成器照着写出 `mlc_op_min(&x, &x, y)`；
* gcc 报 `too many arguments`，**而错误的报告点在 C 编译器，不在我们的工具里**；
* VM 则忽略多余实参、照常算出结果 —— 于是现场看起来像"两条实现算出了不同的数"，
  白挂了一个多月的 xfail。

## 口径

* 期望元数 = `mlc_ops.h` 里该原型**形参个数 − 1**（dst 占一个）；
* op-id → C 名 的映射来自 `translate/operators.py` 的 `c` 字段（**唯一一处**）；
* 被检对象是**真实生成物**：拿 `mir.py` 把语料全转一遍，逐条 `op:` 比对。

这条判据把"生成器与运行时原型是否一致"变成可执行的事 —— 而不是等 gcc 替我们发现。
"""
import io
import os
import re
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "translate"))

MIR_PY = os.path.join(ROOT, "translate", "mir.py")
HEADER = os.path.join(ROOT, "c_runtime", "include", "mlc_ops.h")
CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")
WORK = os.environ.get("M2C_TMP")


def expected_arity():
    """`{OP-ID: {可接受的实参个数…}}`，由原型参数数 − 1 得到。

    **一个 op-id 可以有多个 C 入口**：`size(x)` 走 `mlc_op_size_all`（1 个实参），
    `size(x,dim)` 走 `mlc_op_size_dim`（2 个实参）。目录里用 `c` 记主入口、
    `c_aliases` 记同族其余入口 —— 所以期望元数是一个**集合**，不是单值。

    ⚠ 第一版只读 `c`，于是把 `op:OP-SIZE:y:x` 判成"元数不符"并挂了个豁免。
    真实情况是**判据的模型太窄**，数据早就写清了别名（R829 的教训）。
    """
    from operators import OPERATORS

    h = io.open(HEADER, encoding="utf-8", errors="replace").read()
    protos = {}
    for m in re.finditer(r"mlc_status\s+(mlc_op_\w+)\s*\(([^;]*?)\)\s*;", h, re.S):
        protos[m.group(1)] = len([p for p in m.group(2).split(",") if p.strip()])
    out = {}
    for op in OPERATORS:
        names = [op.get("c")] + list(op.get("c_aliases") or ())
        arities = set(protos[n] - 1 for n in names if n in protos)
        if arities:
            out[op["id"]] = arities
    return out


#: **已知的"op-id → C 名"不是 1:1 的算子**：MIR 的实参个数由**发射器**决定，
#: 而 `operators.py` 的 `c` 字段记的是同族的另一个函数。它们不参与元数比对。
#:
#: 这是 R829 的真实发现（不是猜的）：`op:OP-SIZE:y:x` 只给 1 个实参，发射器调
#: 的是 `mlc_op_size_all(&x, y)`；而目录里记的是 `mlc_op_size_dim(a, dim, out)`
#: （2 个实参）。**元数据与实现不一致** —— 记在这里，别让豁免变成垃圾桶：
#: 每条必须带理由，且总数受下面的棘轮约束。
OP_ARITY_EXEMPT = {}   # R830：`OP-SIZE` 已由 `c_aliases` 正确覆盖，豁免清零

#: 豁免上限（棘轮）：**0** —— 新增一条必须改大这里，并在上面写清为什么。
MAX_OP_EXEMPT = 0


def bad_ops(mir_text, expect):
    """返回 `[(op-id, 实际, 期望, 原行)]`。未知 op-id 与豁免项不计入。"""
    bad = []
    for ln in mir_text.splitlines():
        if not ln.startswith("op:"):
            continue
        parts = ln.split(":")
        oid = parts[1].strip() if len(parts) > 1 else ""
        args = [p for p in parts[3:] if p.strip()] if len(parts) > 3 else []
        if oid in OP_ARITY_EXEMPT:
            continue
        if oid in expect and len(args) not in expect[oid]:
            bad.append((oid, len(args), sorted(expect[oid]), ln[:60]))
    return bad


def test_arity_table_is_derivable():
    """前提判据：每个算子的 C 名都能在 `mlc_ops.h` 里找到原型。

    找不到原型时"期望元数"是 0，后面所有比对都会变成空转 —— 那种绿毫无意义。
    """
    expect = expected_arity()
    assert len(expect) >= 50, "只推出 %d 个算子的元数（原型或映射缺了）" % len(expect)
    assert all(min(v) >= 1 for v in expect.values()), \
        "有算子的期望元数 < 1：%r" % [k for k, v in expect.items() if min(v) < 1]


def test_corpus_mir_matches_c_prototypes():
    """语料全转一遍，**每一条 `op:` 的实参个数都要对得上原型**。"""
    if not os.path.isfile(MIR_PY):
        pytest.skip("缺 mir.py")
    if not os.path.isdir(CORPUS):
        pytest.skip("缺语料")

    d = tempfile.mkdtemp(prefix="arity_", dir=WORK if WORK and os.path.isdir(WORK) else None)
    try:
        mir = os.path.join(d, "all.mir")
        r = subprocess.run([sys.executable, MIR_PY, CORPUS, "-o", mir, "--recursive"],
                           stdin=subprocess.DEVNULL, timeout=600,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-500:]
        text = io.open(mir, encoding="utf-8", errors="replace").read()
        expect = expected_arity()
        bad = bad_ops(text, expect)
        assert not bad, "生成器产出的 op 元数与 C 原型不符（%d 处）：%r" % (len(bad), bad[:5])
        assert text.count("op:") >= 20, "语料只产出 %d 条 op，判据可能空转" % text.count("op:")
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


#: **登记了但 C 侧没实现的算子**。当前为空 —— 这是棘轮，新增必须写理由。
#:
#: 为什么需要这条：`check_translate_port` 的 TP8 只核对 `C_IMPLEMENTED` 在
#: Python 与 Rust 两份清单之间**同步**，但如果两边都漏了同一个算子，没人会发现。
#: 于是"55 登记 / 55 实现"这种结论只能靠我临时跑一次脚本得出 —— 而一次性测量
#: 会随下一次改动静默过期。
UNIMPLEMENTED: dict = {}


def test_every_registered_op_has_c_implementation():
    """每个登记在目录里的算子，都必须有 C 落点（否则生成时只能 `TODO`）。"""
    from operators import C_IMPLEMENTED, OPERATORS

    registered = [o["id"] for o in OPERATORS]
    impl = set(C_IMPLEMENTED)
    missing = sorted(set(registered) - impl)

    unexpected = [m for m in missing if m not in UNIMPLEMENTED]
    assert not unexpected, (
        "这些算子已登记但 C 没实现（生成时会落到 TODO + MLC_UNIMPLEMENTED）：%r\n"
        "  要么补实现，要么在 UNIMPLEMENTED 里写清为什么可以先没有。" % unexpected)

    # 反向：豁免表里不许留下"其实已实现"的陈旧条目
    stale = sorted(k for k in UNIMPLEMENTED if k in impl)
    assert not stale, "UNIMPLEMENTED 里有已实现的算子（陈旧条目）：%r" % stale

    for k, why in UNIMPLEMENTED.items():
        assert len(why.strip()) >= 12, "%s 的豁免理由太短：%r" % (k, why)


def test_exempt_list_is_curated():
    """豁免表不能变成垃圾桶：条数有上界、每条都有理由。"""
    assert len(OP_ARITY_EXEMPT) <= MAX_OP_EXEMPT, \
        "豁免项 %d 条 > 上限 %d（新增要改大 MAX_OP_EXEMPT 并写理由）" % (
            len(OP_ARITY_EXEMPT), MAX_OP_EXEMPT)
    for k, why in OP_ARITY_EXEMPT.items():
        assert len(why.strip()) >= 12, "%s 的豁免理由太短：%r" % (k, why)


MIR_RS = os.path.join(ROOT, "rust", "m2c", "src", "mir.rs")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")


def rust_table():
    """`mir.rs` 里的 `OP_ARITY` 表：`{op-id: (lo, hi)}`。"""
    if not os.path.isfile(MIR_RS):
        return None
    src = io.open(MIR_RS, encoding="utf-8", errors="replace").read()
    out = {}
    for m in re.finditer(r'\("(OP-[A-Z0-9]+)",\s*(\d+),\s*(\d+)\)', src):
        out[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    return out


def test_rust_table_matches_prototypes():
    """**两向核对**：Rust 解析期的元数表必须与 `mlc_ops.h` 推出的一致。

    这张表是生成进去的（55 条），而生成物最容易的失效方式是**悄悄过期**：
    原型改了、表没改，于是解析期开始拒绝合法 MIR（或放过非法 MIR）。
    """
    rust = rust_table()
    if rust is None:
        pytest.skip("没有 mir.rs")
    derived = expected_arity()
    assert len(rust) >= 50, "Rust 表只有 %d 条（应 ≥50）" % len(rust)

    want = dict((k, (min(v), max(v))) for k, v in derived.items())
    missing = [k for k in want if k not in rust]
    extra = [k for k in rust if k not in want]
    diff = [(k, rust[k], want[k]) for k in want
            if k in rust and rust[k] != want[k]]
    if missing or extra or diff:
        # 失败时**直接给出可粘贴的整块** —— 把"重生成"从"写个脚本"降成"复制粘贴"。
        # 生成的表如果还要靠临时脚本才能修，那它一定会过期（脚本不在仓库里）。
        block = "\n".join('    ("%s", %d, %d),' % (k, want[k][0], want[k][1])
                          for k in sorted(want))
        raise AssertionError(
            "Rust 的 OP_ARITY 与 mlc_ops.h 不一致（缺 %r / 多 %r / 区间不符 %r）。\n"
            "把 mir.rs 里 `pub const OP_ARITY` 的条目整块替换为下面这些：\n\n%s"
            % (missing[:6], extra[:6], diff[:6], block))


def test_parse_rejects_wrong_arity():
    """解析期必须真的拒：多给和**少给**都要拒（少给原来会一路走到 gcc）。"""
    if not os.path.isfile(M2C):
        pytest.skip("m2c 未构建")
    import tempfile

    d = tempfile.mkdtemp(prefix="ar_", dir=WORK if WORK and os.path.isdir(WORK) else None)
    cases = [
        (["func:f", "arg:x:f64:3", "ret:y:f64:1", "op:OP-MIN:y:x:x", "end"], "多给"),
        (["func:f", "arg:x:f64:3", "ret:y:f64:3", "op:OP-ADD:y:x", "end"], "少给"),
    ]
    try:
        for body, what in cases:
            p = os.path.join(d, "t.mir")
            io.open(p, "w", encoding="utf-8", newline="\n").write(
                "version 3\n" + "\n".join(body) + "\n")
            r = subprocess.run([M2C, "run", "--mir", p],
                               stdin=subprocess.DEVNULL, timeout=120,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            out = r.stdout.decode("utf-8", "replace")
            assert r.returncode != 0, "%s实参竟然通过了：%s" % (what, out[-200:])
            assert "个输入" in out, "%s实参的报错没说清个数：%s" % (what, out[-200:])
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_arity_checker_has_teeth():
    """判据自己要有牙齿：坏行必须被抓出来，好行不能被误伤。"""
    expect = {"OP-MIN": {1}, "OP-ADD": {2}, "OP-SIZE": {1, 2}}
    assert bad_ops("op:OP-MIN:y:x:x", expect), "归约多给一个输入竟然没被抓到"
    assert bad_ops("op:OP-ADD:y:x", expect), "二元算子少给一个输入竟然没被抓到"
    assert not bad_ops("op:OP-MIN:y:x", expect), "正常的归约被误判"
    assert not bad_ops("op:OP-ADD:y:x:x", expect), "正常的二元被误判"
    # **同族两个 C 入口**：`size(x)` 与 `size(x,dim)` 都合法
    assert not bad_ops("op:OP-SIZE:y:x", expect), "size_all（1 个实参）被误判"
    assert not bad_ops("op:OP-SIZE:y:x:2", expect), "size_dim（2 个实参）被误判"
    assert bad_ops("op:OP-SIZE:y:x:2:3", expect), "size 给 3 个实参竟然没被抓到"
    assert not bad_ops("op:OP-UNKNOWN-ID:y:a:b:c", expect), "未知算子被误判（应由别的门管）"
