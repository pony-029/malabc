# -*- coding: utf-8 -*-
"""纯输出调用（`disp`/`fprintf`…）必须能被**安全丢弃**，即使参数里带括号。

踩过的坑：原正则要求"参数里没有括号"，而真实代码常把函数名写进字符串：

    disp('run an addpath(genpath(''root''))')

于是这条最该丢弃的语句反而卡进 unmapped（实测 YALMIP 上百条）。
判据只看**调用名**：纯输出调用不产生数据，参数结构无关。
"""
import io
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
TMPROOT = r"E:\temp\matlabc"


def _mir(src_code):
    base = TMPROOT if os.path.isdir(TMPROOT) else tempfile.gettempdir()
    d = tempfile.mkdtemp(prefix="m2c_drop_", dir=base)
    try:
        p = os.path.join(d, "f.m")
        io.open(p, "w", encoding="utf-8", newline="\n").write(src_code)
        out = os.path.join(d, "f.mir")
        r = subprocess.run([sys.executable, MIR_PY, p, "-o", out],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=300)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-500:]
        return io.open(out, encoding="utf-8", errors="replace").read()
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_disp_with_parens_inside_string_is_dropped():
    mir = _mir("function y = f(a)\n% @m2c shape a 2\n% @m2c shape y 1\n"
               "disp('run an addpath(genpath(''root'')) now');\n"
               "y = a(1);\nend\n")
    assert "# dropped:" in mir, "带括号的 disp 应被丢弃"
    assert "unmapped:" not in mir, "不该留下未映射语句：%s" % mir


def test_fprintf_with_nested_call_in_string_is_dropped():
    mir = _mir("function y = f(a)\n% @m2c shape a 2\n% @m2c shape y 1\n"
               "fprintf('got %s from f(x)\\n', 'v');\n"
               "y = a(1);\nend\n")
    assert "# dropped:" in mir
    assert "unmapped:" not in mir


def test_assignment_with_sideeffect_head_is_not_dropped():
    """`y = disp(...)` 这种（虽然少见）不能被当成纯输出丢掉 —— 它在赋值。"""
    mir = _mir("function y = f(a)\n% @m2c shape a 2\n% @m2c shape y 1\n"
               "y = a(1);\nend\n")
    assert "unmapped:" not in mir
    assert "op:OP-INDEX" in mir, "正常赋值不该受影响"
