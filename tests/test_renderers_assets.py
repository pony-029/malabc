# -*- coding: utf-8 -*-
"""静态资产的写出（`renderers/assets.py`）：CSS 树落盘要**确定、零外部依赖**。

`test_renderers.py` 覆盖的是调用图 SVG；这里是另一条产物路径（CSS 目录树）。
它坏掉的表现很隐蔽：页面能打开，只是**样式全丢**或**每次生成都不一样**
（后者会让站点产物出现无意义 diff）。
"""
import hashlib
import io
import os
import shutil
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "renderers"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def _tree_hash(d):
    """目录内容哈希（相对路径 + 内容），用来验"两次写出完全一致"。"""
    h = hashlib.sha256()
    for base, _dirs, files in os.walk(d):
        for f in sorted(files):
            p = os.path.join(base, f)
            h.update(os.path.relpath(p, d).replace("\\", "/").encode())
            h.update(io.open(p, "rb").read())
    return h.hexdigest()


def test_page_css_tree_is_written_and_deterministic():
    """写出至少一个 CSS 文件，且**两次写出内容完全一致**。"""
    from renderers import assets as A

    tmp = os.environ.get("M2C_TMP")
    d1 = tempfile.mkdtemp(prefix="css1_", dir=tmp if tmp and os.path.isdir(tmp) else None)
    d2 = tempfile.mkdtemp(prefix="css2_", dir=tmp if tmp and os.path.isdir(tmp) else None)
    try:
        A.write_page_css_tree(d1)
        A.write_page_css_tree(d2)
        files = [f for _b, _d, fs in os.walk(d1) for f in fs]
        assert files, "一个文件都没写出（页面会没有样式）"
        assert _tree_hash(d1) == _tree_hash(d2), \
            "两次写出的 CSS 树不同（产物会出现无意义 diff）"
    finally:
        shutil.rmtree(d1, ignore_errors=True)
        shutil.rmtree(d2, ignore_errors=True)


def test_css_has_no_remote_import():
    """**零外部依赖**：CSS 里不能 `@import url(http…)` 或引用远程字体。

    项目承诺"断网可用" —— 一个远程 `@import` 会在离线环境下静默失效，
    页面看起来正常但样式缺一块。
    """
    from renderers import assets as A

    tmp = os.environ.get("M2C_TMP")
    d = tempfile.mkdtemp(prefix="css3_", dir=tmp if tmp and os.path.isdir(tmp) else None)
    try:
        A.write_page_css_tree(d)
        bad = []
        for base, _dirs, files in os.walk(d):
            for f in files:
                if not f.endswith(".css"):
                    continue
                txt = io.open(os.path.join(base, f), encoding="utf-8",
                              errors="replace").read()
                for token in ("http://", "https://", "//fonts."):
                    if "@import" in txt and token in txt:
                        bad.append(f)
        assert not bad, "CSS 里有远程 @import（断网会静默失效）：%r" % bad
    finally:
        shutil.rmtree(d, ignore_errors=True)
