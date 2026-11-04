# -*- coding: utf-8 -*-
"""可视化播放器（`translate/report.py`）的判据。

播放器坏掉的表现是**打开后白屏**：不报错、不退出、没有日志。
所以这里必须验三件事，而不是"能生成 HTML"：

1. **控件齐全**：播放/暂停、进度条、速度、循环、聚焦、四个阶段；
2. **脚本语法正确**（用 `node --check` 验真实抽出的那段 JS）——
   语法错 = 白屏，而 Python 侧完全无感；
3. **状态不撒谎**：语料里有真数值的函数必须是 `numeric`（这条在 R629 抓到过
   "成功反而标红"的缺陷）。
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
REPORT = os.path.join(ROOT, "translate", "report.py")
CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
def test_report_player_structure_and_script():
    d = tempfile.mkdtemp(prefix="m2c_play_")
    out = os.path.join(d, "r.html")
    try:
        r = subprocess.run([sys.executable, REPORT, CORPUS, "--limit", "3", "-o", out],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=900)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-600:]
        doc = io.open(out, encoding="utf-8").read()

        # 1) 控件
        for ctl in ('id="play"', 'id="seek"', 'id="speed"', 'id="loop"',
                    'id="mode"', 'id="stages"', 'id="first"', 'id="last"'):
            assert ctl in doc, "缺少控件：%s" % ctl
        # 2) 每个函数一张卡，四阶段
        assert doc.count('data-status=') == 3, "卡片数应等于函数数"
        assert doc.count('class="pane"') == 3 * 4, "每张卡应有 4 个阶段面板"
        # 3) 键盘绑定存在（步进/播放/直跳）
        for k in ("ArrowRight", "ArrowLeft", "Space", "Digit"):
            assert k in doc, "缺少键盘绑定：%s" % k

        # 4) 状态不撒谎：语料的 3 个必须是 numeric
        assert 'data-status="numeric"' in doc
        assert 'data-status="error"' not in doc

        # 5) 真脚本的语法（语法错 = 白屏）
        m = re.search(r"<script>(.*?)</script>", doc, re.S)
        assert m, "报告里没有 <script>"
        node = shutil.which("node")
        if node:
            js = os.path.join(d, "p.js")
            io.open(js, "w", encoding="utf-8", newline="\n").write(m.group(1))
            nr = subprocess.run([node, "--check", js], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=120)
            assert nr.returncode == 0, nr.stdout.decode("utf-8", "replace")[:600]
    finally:
        shutil.rmtree(d, ignore_errors=True)
