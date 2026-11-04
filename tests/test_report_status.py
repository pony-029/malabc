# -*- coding: utf-8 -*-
"""报告的状态分类必须**一义**：`error` 只表示"编译/运行失败"。

踩过的坑：把**没有顶层 function 的脚本**（`Contents.m` 这类）算成 `error`，
于是真实工程里满屏红 —— 而"红"本来该是"需要人看"的信号，被噪声填满就失效了。
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
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
REPORT = os.path.join(ROOT, "translate", "report.py")
TMPROOT = r"E:\temp\matlabc"


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
def test_script_without_function_is_skipped_not_error():
    base = TMPROOT if os.path.isdir(TMPROOT) else tempfile.gettempdir()
    d = tempfile.mkdtemp(prefix="m2c_status_", dir=base)
    try:
        src = os.path.join(d, "proj")
        os.makedirs(src)
        # 1) 正常函数
        io.open(os.path.join(src, "ok.m"), "w", encoding="utf-8", newline="\n").write(
            "function y = ok(a)\n% @m2c shape a 2\n% @m2c shape y 1\ny = a(1);\nend\n")
        # 2) 纯文档（没有顶层 function）
        io.open(os.path.join(src, "Contents.m"), "w", encoding="utf-8", newline="\n").write(
            "% Contents\n% 说明而已\n")
        out = os.path.join(d, "r.html")
        r = subprocess.run([sys.executable, REPORT, src, "-o", out, "--limit", "5"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=600)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-600:]

        doc = io.open(out, encoding="utf-8").read()
        assert 'data-status="numeric"' in doc, "正常函数应算 numeric"
        assert 'data-status="skipped"' in doc, "无顶层 function 的文件应归 skipped"
        assert 'data-status="error"' not in doc, "不该出现 error（没有真失败）"
    finally:
        shutil.rmtree(d, ignore_errors=True)
