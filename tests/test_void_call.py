# -*- coding: utf-8 -*-
"""丢弃返回值的调用 `foo(a);` 必须降成 `call:`，而不是 unmapped。

为什么单独锁：它目前只在 YALMIP（外部工程）上生效，仓库内**没有语料覆盖**。
一旦哪天被改回去，16 道门都不会红 —— 只有下次跑 YALMIP 才发现，
而那时你会以为“是别的东西坏了”。
"""
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")

CALLEE = """function y = twice(x)
% @m2c shape x 3
% @m2c shape y 3
y = x + x;
end
"""

CALLER = """function y = useit(x)
% @m2c shape x 3
% @m2c shape y 3
% 结果丢弃：只关心副作用（这里没有，但语法必须被接受）
twice(x);
y = twice(x);
end
"""


def test_void_call_lowers_to_call():
    d = tempfile.mkdtemp(prefix="m2c_void_")
    for name, body in (("twice.m", CALLEE), ("useit.m", CALLER)):
        with open(os.path.join(d, name), "w", encoding="utf-8",
                  newline="") as fh:
            fh.write(body)
    mir = os.path.join(d, "p.mir")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "translate", "mir.py"),
                        d, "-o", mir],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=300)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-400:]

    text = open(mir, encoding="utf-8").read()
    # 定位 useit 段
    i = text.find("func:useit")
    assert i >= 0
    seg = text[i:text.find("func:", i + 1) if text.find("func:", i + 1) > 0
               else len(text)]
    assert "call:" in seg, "丢弃返回值的调用没降成 call: —— %s" % seg[:200]
    assert "unmapped:" not in seg, "仍然被判成 unmapped —— %s" % seg[:200]

    # 再确认整工程能编译
    cc = shutil.which("gcc") or shutil.which("clang")
    if not cc:
        pytest.skip("没有 C 编译器")
    gen = os.path.join(d, "gen")
    r = subprocess.run([M2C, "build", "--mir", mir, "--out", gen,
                        "--name", "p"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=300)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-300:]
    r = subprocess.run([cc, "-std=c99", "-fsyntax-only",
                        "-I", os.path.join(gen, "include"),
                        "-I", os.path.join(ROOT, "c_runtime", "include"),
                        os.path.join(gen, "src", "gen.c")],
                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=300)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-800:]
