# -*- coding: utf-8 -*-
"""返回值 struct 展开：`s.a = ...`（`s` 是返回值）→ 多个 `ret:`。

判据三件：
1. 已声明 → 返回值展开为 `ret:s_a`，语句落成 `op:`/`set:`，**0 未映射**；
2. 未声明 → 保持原样并进 `unmapped`（不猜）；
3. 展开后**不能**再被 `reject:struct` 整函数拒绝（否则等于没展开）。
"""
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"

DECLARED = """function s = f(v)
% @m2c fields s.a
% @m2c shape v 3
% @m2c shape s.a 3
s.a = v .* v;
end
"""

UNDECLARED = """function s = f(v)
% @m2c shape v 3
s.a = v .* v;
end
"""


def _mir(text, name):
    d = tempfile.mkdtemp(prefix="m2c_os_", dir=WORK if os.path.isdir(WORK) else None)
    p = os.path.join(d, name + ".m")
    io.open(p, "w", encoding="utf-8", newline="\n").write(text)
    out = os.path.join(d, name + ".mir")
    r = subprocess.run([sys.executable, MIR_PY, p, "-o", out],
                       stdin=subprocess.DEVNULL, timeout=120,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-300:]
    return io.open(out, encoding="utf-8").read()


def test_declared_out_struct_expands_to_rets():
    t = _mir(DECLARED, "decl")
    assert "ret:s_a" in t, "返回值应展开成 s_a"
    assert "unmapped:" not in t, "展开后不应再有未映射"
    assert "reject:struct" not in t, "已声明的 struct 不应再被整函数拒绝"


def test_undeclared_out_struct_is_refused():
    t = _mir(UNDECLARED, "undecl")
    assert "ret:s" in t and "ret:s_a" not in t, "未声明时不得擅自展开"
    assert "unmapped:" in t, "未声明应如实记为未映射"
