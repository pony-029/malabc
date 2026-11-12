# -*- coding: utf-8 -*-
"""VM 的**函数链接**：同一份 MIR 内的 `call:` / `call2:` 必须真的执行。

## 为什么单独一个文件

`test_project_e2e.py` 从 `.m` 出发、经过 `project_map`，验的是**整条链路**；
这里用手写 MIR 只验 **VM 这一层**：不依赖编译器、不依赖生成器，0.3 秒出结论。

两者分工明确：
  * 链路级判据会掩盖 VM 的局部缺陷（因为 C 路跑对了也只说明 C 路对）；
  * 层内判据会掩盖集成缺陷（MIR 是手写的，绕过了 `mir.py`）。
  两条都要有 —— 这正是 R805/R809 两轮各自踩过的教训。

## 判据

* **VC1** `call:` 必须链接同 MIR 的函数，并把返回值写回左值。
* **VC2** `call2:` 必须把**多个**返回值按顺序写到多个左值。
* **VC3** 调不存在的函数要**报错**（而不是静默给出 0），且错误里带函数名。
"""
import io
import os
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
WORK = os.environ.get("M2C_TMP")


def _run_mir(text, name):
    d = WORK if WORK and os.path.isdir(WORK) else None
    import tempfile
    p = os.path.join(tempfile.mkdtemp(prefix="vc_", dir=d), name)
    io.open(p, "w", encoding="utf-8", newline="\n").write(text)
    r = subprocess.run([M2C, "run", "--mir", p], stdin=subprocess.DEVNULL,
                       timeout=120, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", "replace")


CALL_SRC = "\n".join([
    "version 3",
    "func:main",
    "arg:x:f64:3",
    "ret:y:f64:3",
    "call:y:twice:x",
    "end",
    "func:twice",
    "arg:a:f64:3",
    "ret:b:f64:3",
    "op:OP-MUL:b:a:a",
    "end",
    "",
])

CALL2_SRC = "\n".join([
    "version 3",
    "func:main",
    "arg:x:f64:3",
    "ret:y:f64:3",
    "var:z:f64:3",
    "call2:y,z:pair:x",
    "end",
    "func:pair",
    "arg:x:f64:3",
    "ret:y:f64:3",
    "ret:z:f64:3",
    "op:OP-MUL:y:x:x",
    "op:OP-ADD:z:x:x",
    "end",
    "",
])

MISSING_SRC = "\n".join([
    "version 3",
    "func:main",
    "arg:x:f64:3",
    "ret:y:f64:3",
    "call:y:nowhere:x",
    "end",
    "",
])


pytestmark = pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")


def test_vc1_call_links_and_returns():
    rc, out = _run_mir(CALL_SRC, "c1.mir")
    assert rc == 0, out[-300:]
    assert "不做链接" not in out, "VM 仍拒绝链接：\n%s" % out[-300:]
    # 输入默认 1..3 -> twice(x)=x*x -> 1 4 9
    assert "y: 1 4 9" in out, out[-300:]


def test_vc2_call2_binds_multiple_rets():
    rc, out = _run_mir(CALL2_SRC, "c2.mir")
    assert rc == 0, out[-300:]
    assert "z: 2 4 6" in out, "第二个返回值没写回左值 z：\n%s" % out[-300:]
    assert out.count("y: 1 4 9") >= 1, out[-300:]


BAD_REDUCE = "\n".join([
    "version 3",
    "func:main",
    "arg:x:f64:5",
    "ret:y:f64:1",
    "op:OP-MIN:y:x:x",     # 归约只吃 1 个输入，这里给了 2 个
    "end",
    "",
])


def test_vc4_reduce_arity_is_rejected_at_parse():
    """VC4：归约算子给了多余实参，必须在**解析期**就报错。

    不让它走到 C：生成物会写出 `mlc_op_min(&x, &x, y)`，gcc 报
    `too many arguments`；而 VM 会忽略多余实参算出结果 —— 两边"看起来不一致"，
    实际是样本不合法。R813 就有三个假分岔是这么来的，白挂了一个多月的 xfail。
    """
    rc, out = _run_mir(BAD_REDUCE, "bad_reduce.mir")
    assert rc != 0, "非法的归约实参竟然通过了：\n%s" % out[-300:]
    assert "归约" in out, "报错没说明是归约算子的元数问题：\n%s" % out[-300:]
    assert "OP-MIN" in out, "报错没指明是哪个算子：\n%s" % out[-300:]


def test_vc3_missing_callee_is_reported():
    """VC3：调不存在的函数必须**报错**，不能静默给 0。

    静默给 0 是最坏的形态：下游会拿 0 继续算，产出一串"看起来正常"的错值。
    """
    rc, out = _run_mir(MISSING_SRC, "c3.mir")
    assert rc != 0, "调不存在的函数竟然成功：\n%s" % out[-300:]
    assert "nowhere" in out, "报错里没有函数名（用户不知道该补什么）：\n%s" % out[-300:]
