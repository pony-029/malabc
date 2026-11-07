# -*- coding: utf-8 -*-
"""阶段 1 判据：`translate/check.py` 的诊断必须**指向真实的那一行**。

## 防的是什么

诊断功能最容易"看起来有用"：它能打印一堆行号，但那些行号可能来自内层临时语句、
或者 MIR 的 `# src:` 跟踪错位。用户照着去改第 12 行，发现那里没问题 ——
**这个功能就死了，而且不会报错**。

所以判据不是"能输出"，而是：**报出的源码行，必须真的含有那条阻塞语句的实质内容。**
"""
import io
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import check as CK    # noqa: E402

CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")


def test_convertible_file_reports_ok():
    res = CK.diagnose(os.path.join(CORPUS, "snr.m"))
    assert res["status"] == "ok", "正常函数应判为可生成：%r" % (res.get("blockers"),)
    assert res["ops"] > 0
    text = CK.render(res)
    assert "可以生成" in text


def test_blocked_file_points_at_real_lines():
    """有阻塞时：每条带行号的诊断，源码那一行必须与它实质吻合。"""
    src_dir = r"E:\temp\matlabc\jsonlab"
    if not os.path.isdir(src_dir):
        pytest.skip("缺 jsonlab 参考工程")
    files = sorted(f for f in os.listdir(src_dir) if f.endswith(".m"))[:8]
    checked = 0
    for fn in files:
        res = CK.diagnose(os.path.join(src_dir, fn))
        if res["status"] != "blocked":
            continue
        for b in res["blockers"]:
            if b["line"] <= 0:
                continue
            line = res["sources"].get(b["line"], "")
            stem = b["text"].rstrip(";").split("(")[0][:10]
            if not stem:
                continue
            checked += 1
            assert stem in line or line[:10] in b["text"], \
                "%s 第 %d 行的诊断与实际源码不符：\n  报告 %r\n  源码 %r" \
                % (fn, b["line"], b["text"][:60], line[:60])
            if checked >= 10:
                return
    assert checked > 0, "没有可核对的样本（诊断可能没产出行号）"


def test_render_has_actionable_advice():
    """输出里必须有"先修哪里"——这正是 L2 测量的落地。"""
    src_dir = r"E:\temp\matlabc\jsonlab"
    if not os.path.isdir(src_dir):
        pytest.skip("缺 jsonlab 参考工程")
    res = CK.diagnose(os.path.join(src_dir, "loadjson.m"))
    text = CK.render(res)
    assert "先修哪里" in text
    assert "签名级" in text or "语句级" in text
