# -*- coding: utf-8 -*-
"""Rust VM **逐算子**专项测试：直接喂 MIR 片段，断言数值。

## 与 `test_vm_run.py` 的分工

| 判据 | 问的问题 |
|---|---|
| `test_vm_run.py` | 整个语料的 MIR 跑出来对不对（**端到端**） |
| 本文件 | **单个算子**的语义对不对（**单元**） |

端到端只能告诉你"某处错了"，单元能告诉你是**哪个算子**。

## 期望值是手工算的

形参一律按 `1..n` 填充（与 C 驱动一致）。每个用例的注释里写了算式，
方便复核 —— 不接受"跑出来是多少就写多少"。
"""
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"


def _run(body, args=("x:f64:3",), ret="y:f64:1"):
    d = tempfile.mkdtemp(prefix="vmop_", dir=WORK if os.path.isdir(WORK) else None)
    p = os.path.join(d, "t.mir")
    lines = ["version 3", "func: f"] + ["arg:" + a for a in args] + ["ret:" + ret]
    io = __import__("io")
    io.open(p, "w", encoding="utf-8", newline="\n").write(
        "\n".join(lines + body + ["end"]) + "\n")
    r = subprocess.run([M2C, "run", "--mir", p], stdin=subprocess.DEVNULL,
                       timeout=60, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", "replace").strip()
    assert r.returncode == 0, out
    return out.split(":", 1)[1].strip() if ":" in out else out


P = pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")

CASES = [
    # (名称, MIR 体, 期望, args, ret)
    ("add", ["op:OP-ADD:y:x:x"], "2 4 6", ("x:f64:3",), "y:f64:3"),      # x=1,2,3
    ("sub", ["op:OP-SUB:y:x:x"], "0 0 0", ("x:f64:3",), "y:f64:3"),
    ("mul", ["op:OP-MUL:y:x:x"], "1 4 9", ("x:f64:3",), "y:f64:3"),
    ("div", ["op:OP-DIV:y:x:x"], "1 1 1", ("x:f64:3",), "y:f64:3"),
    ("sum", ["op:OP-SUM:y:x"], "6", ("x:f64:3",), "y:f64:1"),            # 1+2+3
    ("mean", ["op:OP-MEAN:y:x"], "2", ("x:f64:3",), "y:f64:1"),          # 6/3
    ("max", ["op:OP-MAX:y:x"], "3", ("x:f64:3",), "y:f64:1"),
    ("min", ["op:OP-MIN:y:x"], "1", ("x:f64:3",), "y:f64:1"),
    ("sqrt4", ["op:OP-SQRT:y:x"], "1 1.4142135623730951 1.7320508075688772",
     ("x:f64:3",), "y:f64:3"),
    ("floor", ["op:OP-FLOOR:y:x"], "1 2 3", ("x:f64:3",), "y:f64:3"),
    # 下标（1-based，列主序）
    ("index", ["op:OP-INDEX:y:x:2"], "2", ("x:f64:3",), "y:f64:1"),
    ("slice", ["op:OP-SLICE:y:x:2:3"], "2 3", ("x:f64:3",), "y:f64:2"),
    # 逻辑下标选值：x > 2 → 3
    ("mask_gt2", ["op:OP-MASK:y:x:0:2"], "3", ("x:f64:3",), "y:f64:1"),
    # 查找：x > 2 的 1-based 下标 → 3
    ("find_gt2", ["op:OP-FIND:y:x:0:2"], "3", ("x:f64:3",), "y:f64:1"),
    # 谓词
    ("numel", ["op:OP-NUMEL:y:x"], "3", ("x:f64:3",), "y:f64:1"),
    ("length", ["op:OP-LENGTH:y:x"], "3", ("x:f64:3",), "y:f64:1"),
    ("isempty_no", ["op:OP-ISEMPTY:y:x"], "0", ("x:f64:3",), "y:f64:1"),
    ("any", ["op:OP-ANY:y:x"], "1", ("x:f64:3",), "y:f64:1"),
    ("nnz", ["op:OP-NNZ:y:x"], "3", ("x:f64:3",), "y:f64:1"),
    # 展平（列主序）
    ("flatten", ["op:OP-FLATTEN:y:x"], "1 2 3", ("x:f64:3",), "y:f64:3"),
    # 拼接
    ("hcat", ["op:OP-HCAT:y:x:x"], "1 2 3 1 2 3", ("x:f64:3",), "y:f64:6"),
    # 集合差：a=1,2,3 与 b=1,2 → 3（**两个形参都按 1..n 填**，所以 b 要短一截，
    # 否则两集合相同、差集为空 —— 第一版就是这么写错期望值的）
    ("setdiff", ["op:OP-SETDIFF:y:a:b"], "3",
     ("a:f64:3", "b:f64:2"), "y:f64:1"),
    # 相等判定：a 与 a → 1
    ("isequal", ["op:OP-ISEQUAL:y:a:a"], "1", ("a:f64:3",), "y:f64:1"),
    # 常量
    ("const", ["const:y:5"], "5", ("x:f64:1",), "y:f64:1"),
]


@P
@pytest.mark.parametrize("name,body,want,args,ret", CASES,
                         ids=[c[0] for c in CASES])
def test_vm_op(name, body, want, args, ret):
    got = _run(body, args, ret)
    assert " ".join(got.split()) == " ".join(want.split()), \
        "%s：VM=%r 期望=%r" % (name, got, want)


@P
def test_vm_unknown_op_is_reported():
    """未实现的算子必须**报错**，不能返回 0 或空。"""
    d = tempfile.mkdtemp(prefix="vmop_", dir=WORK if os.path.isdir(WORK) else None)
    p = os.path.join(d, "t.mir")
    __import__("io").open(p, "w", encoding="utf-8", newline="\n").write(
        "version 3\nfunc: f\narg:x:f64:3\nret:y:f64:1\n"
        "op:OP-NOT-A-REAL-OP:y:x\nend\n")
    r = subprocess.run([M2C, "run", "--mir", p], stdin=subprocess.DEVNULL,
                       timeout=60, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", "replace")
    assert r.returncode != 0 or "error" in out or "未实现" in out, out[:200]
