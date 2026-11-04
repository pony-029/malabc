# -*- coding: utf-8 -*-
"""多工程演示站点（`report.py --site`）的判据。

要点：**页面必须是机制产出的**，不是每次手写一份。
所以这里测的是"给定 N 个工程目录，一条命令得到 index + N 页 + 可点开的链接"，
而不是某一页的具体内容。
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
CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
def test_site_mode_builds_index_and_pages():
    d = tempfile.mkdtemp(prefix="m2c_site_")
    out = os.path.join(d, "site")
    # 第二个"工程"：一个只有 1 个函数的小目录
    small = os.path.join(d, "tiny")
    os.makedirs(small)
    io.open(os.path.join(small, "one.m"), "w", encoding="utf-8", newline="\n").write(
        "function y = one(a)\n% @m2c shape a 2\n% @m2c shape y 1\ny = a(1);\nend\n")
    try:
        r = subprocess.run([sys.executable, REPORT, "--site", CORPUS, small,
                            "-o", out, "--limit", "2"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=900)
        assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-600:]

        idx = io.open(os.path.join(out, "index.html"), encoding="utf-8").read()
        # index 现在有两张表（工程汇总 + 跨工程卡点），所以 <tr> 数不再等于工程数
        assert "proj_numeric.html" in idx and "proj_tiny.html" in idx
        assert idx.count("<tr>") >= 3, "index 至少应有表头 + 两行"
        # 跨工程对比段必须存在，且至少有一条卡点行（cells 是真实工程的常见卡点）
        assert "跨工程卡点对比" in idx, "缺跨工程对比段"
        assert ("why:cell" in idx or "reject:" in idx or "没有卡点" in idx), "对比段没有内容"

        for name in ("numeric", "tiny"):
            p = os.path.join(out, "proj_%s.html" % name)
            assert os.path.isfile(p), "缺页面：%s" % name
            doc = io.open(p, encoding="utf-8").read()
            assert 'id="play"' in doc and 'id="stages"' in doc, "页面缺播放器"
            assert 'href="proj_%s.html"' % name in idx, "index 未链接到 %s" % name
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.skipif(not os.path.isfile(M2C), reason="m2c 未构建")
def test_site_mode_rejects_non_directory():
    """把输出目录误当输入是最容易犯的错 —— 必须提示，而不是算出一个空工程。"""
    d = tempfile.mkdtemp(prefix="m2c_site2_")
    try:
        r = subprocess.run([sys.executable, REPORT, "--site",
                            os.path.join(d, "nope"), "-o", os.path.join(d, "s"),
                            "--limit", "1"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=300)
        out = r.stdout.decode("utf-8", "replace")
        assert r.returncode != 0
        assert "不是目录" in out or "没有任何工程目录" in out
    finally:
        shutil.rmtree(d, ignore_errors=True)
