# -*- coding: utf-8 -*-
"""P3 判据：**契约桩在契约面上可见**。

## 现状（实测）

工程里出现"调不到的函数"时，今天的产物已经能"编译通过 + 其余函数照跑"：

```
broken: unimplemented      ← 调用方失败
ok1: 2 4 6                 ← 其余正常
```

**缺的是"用户怎么知道该补哪些函数"** —— 头文件里什么都不说。
所以本判据守的是**契约面**：被调用、但不在工程内的函数，必须在
`include/<proj>.h` 里以 `m2c_ext_<名字>(...)` 的形式列出来。

## 为什么用手写 MIR

`mir.py` 把"调用未定义函数"记成 `# unmapped`（不是 `call:`），所以
从 `.m` 出发造不出这个场景。`call:<dst>:<名>:<实参>` 在 MIR 语法里是合法的，
直接用 MIR 造样本，测的就是**发射器/工程装配**这一层。
"""
import io
import os
import shutil
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

#: `caller` 调用一个**不在本文件/本工程**的 `missing`（两个实参）
MIR = ("version 3\n"
       "func:caller\narg:x:f64:3\nret:y:f64:3\n"
       "call:y:missing:x:2\nend\n")


@pytest.fixture(scope="module")
def header():
    if not os.path.isfile(M2C):
        pytest.skip("m2c 未构建")
    d = tempfile.mkdtemp(prefix="p3_", dir=WORK if os.path.isdir(WORK) else None)
    try:
        mir = os.path.join(d, "p.mir")
        io.open(mir, "w", encoding="utf-8", newline="\n").write(MIR)
        out = os.path.join(d, "g")
        r = subprocess.run([M2C, "build", "--mir", mir, "--out", out, "--name", "p"],
                           stdin=subprocess.DEVNULL, timeout=120,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-400:]
        h = os.path.join(out, "include", "p.h")
        assert os.path.isfile(h), "没有生成头文件"
        return io.open(h, encoding="utf-8").read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_header_lists_unresolved_external(header):
    """P3a：头文件里必须有 `m2c_ext_missing(...)` 的声明。"""
    assert "m2c_ext_missing" in header, \
        "头文件没列出未解析的外部函数（用户无从知道要补什么）：\n%s" % header[-400:]


def _gen_mir(src_text, extra_args=()):
    import sys
    d = tempfile.mkdtemp(prefix="p3s_", dir=WORK if os.path.isdir(WORK) else None)
    p = os.path.join(d, "f.m")
    io.open(p, "w", encoding="utf-8", newline="\n").write(src_text)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "translate", "mir.py"),
                        p, "-o", os.path.join(d, "f.mir")] + list(extra_args),
                       stdin=subprocess.DEVNULL, timeout=120,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-300:]
    return io.open(os.path.join(d, "f.mir"), encoding="utf-8").read()


SRC = ("function y = uses_ext(x)\n% @m2c shape x 3\n% @m2c shape y 3\n"
       "y = external_magic(x);\nend\n")


def test_external_call_kept_only_when_asked():
    """P3c：默认**不**保留（如实标未映射）；`--external-calls` 才保留成 `call:`。

    默认值是这条判据的重点：把"运行期才失败的调用"当成默认，
    等于把可行动的诊断换成静默。
    """
    off = _gen_mir(SRC)
    assert "call:" not in off, "默认不该把工程外调用转成 call:"
    assert "unmapped:" in off, "默认应如实标为未映射"

    on = _gen_mir(SRC, ("--external-calls",))
    assert "call:y:external_magic:x" in on, "开了开关仍没保留成 call:"


def test_arity_matches_callsite(header):
    """P3b：形参个数按**调用点实参个数**推出（本例 2 个 → a0, a1）。"""
    line = [l for l in header.splitlines() if "m2c_ext_missing" in l]
    assert line, "没有声明行"
    assert "a0" in line[0] and "a1" in line[0], "形参个数与调用点不符：%r" % line[0]
    assert "a2" not in line[0], "形参个数多了：%r" % line[0]
