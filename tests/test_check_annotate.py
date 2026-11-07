# -*- coding: utf-8 -*-
"""`check --annotate`：把"形参 struct"的阻塞变成**可粘贴的注解**。

## 防的是什么

建议注解很容易"看起来有用"：它能打印 `% @m2c fields s.a`，但那条注解可能
① 指向的不是形参（局部 struct 不需要注解，加了反而改变语义）；
② 指向元胞字段（`s.f{...}`），那不是"一组标量"。

所以判据不是"能输出"，而是：**加上它之后，形参真的被展开、struct 拒绝真的消失**。
"""
import io
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import check as CK    # noqa: E402

MIR_PY = os.path.join(ROOT, "translate", "mir.py")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

SRC = """function y = f(s, v)
% @m2c shape v 3
% @m2c shape y 3
k = s.alpha;
y = v .* k;
end
"""


def _mir(path, out):
    r = subprocess.run([sys.executable, MIR_PY, path, "-o", out],
                       stdin=subprocess.DEVNULL, timeout=120,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-300:]
    return io.open(out, encoding="utf-8").read()


def test_annotate_suggests_param_struct_field():
    d = tempfile.mkdtemp(prefix="m2c_ann_", dir=WORK if os.path.isdir(WORK) else None)
    p = os.path.join(d, "f.m")
    io.open(p, "w", encoding="utf-8", newline="\n").write(SRC)

    res = CK.diagnose(p)
    assert res["status"] == "blocked"
    anns = res["annotations"]
    assert anns, "应给出 struct 注解建议"
    lines = anns[0][1]
    assert any("s.alpha" in ln for ln in lines), "应指向 s.alpha：%r" % (lines,)


def test_annotated_copy_actually_expands_args():
    """加上建议的注解后：形参被展开，`reject:struct` 消失 —— 这才是"注解有用"。"""
    d = tempfile.mkdtemp(prefix="m2c_ann2_", dir=WORK if os.path.isdir(WORK) else None)
    p = os.path.join(d, "f.m")
    io.open(p, "w", encoding="utf-8", newline="\n").write(SRC)
    out = os.path.join(d, "f_ann.m")

    rc = CK.main.__globals__["sys"].argv  # 避免真调 CLI，直接复用逻辑
    res = CK.diagnose(p)
    anns = res["annotations"]
    assert anns

    # 手工按 CLI 的规则插入注解（与 --annotate 写副本的逻辑一致）
    lines = io.open(p, encoding="utf-8").read().split("\n")
    ins = []
    for _fn, ls, _n in anns:
        ins.extend(ls)
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("function"):
            lines[i + 1:i + 1] = ins
            break
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines))

    before = _mir(p, os.path.join(d, "a.mir"))
    after = _mir(out, os.path.join(d, "b.mir"))
    assert "reject:struct" in before
    assert "reject:struct" not in after, "加了注解后不应再被整函数拒绝"
    assert "arg:s_alpha" in after, "形参应展开成 s_alpha"
    assert after.count("unmapped:") <= before.count("unmapped:")
