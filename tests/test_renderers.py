# -*- coding: utf-8 -*-
"""渲染层判据（`renderers/`）：47 个文件，此前**没有任何专门判据**。

## 为什么这层值得单独测

渲染层的产物是**给人看的东西**（SVG / 站点 / CSS 树）。它坏了不会让转换出错，
只会让"图看起来不对" —— 而那是最难被发现、也最容易被当成"就这样"的一类问题。

四条判据都盯**可观察的产物性质**，不碰实现：

* **RD1** 没有函数时返回空串 —— 不崩、也不产出一个空壳 SVG；
* **RD2** 有函数时是**零 JS** 的 SVG（项目从第一天就承诺"断网可用、无脚本"）；
* **RD3** 同一输入两次渲染**字节相同** —— 渲染器最容易栽在 dict/set 迭代顺序上；
* **RD4** `max_nodes` 截断时仍产出合法 SVG（截断路径不崩）。
"""
import io
import os
import shutil
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "analyzer", "renderers"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def _project(files):
    """建一个临时工程并 `analyze`，返回 PipelineResult。"""
    from analyzer import api as A

    d = tempfile.mkdtemp(prefix="rd_", dir=os.environ.get("M2C_TMP") or None)
    for rel, body in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        io.open(p, "w", encoding="utf-8", newline="\n").write(body)
    return d, A.analyze(d)


TWO = {
    "a.m": "function y = a(x)\ny = x + 1;\nend\n",
    "b.m": "function y = b(x)\ny = a(x) * 2;\nend\n",
}


def test_rd1_empty_project_renders_empty_string():
    """RD1：没有函数 → 空串。空壳 SVG 会被页面当成"有图"，比没有更糟。"""
    from renderers import callgraph as CG

    d, res = _project({})
    try:
        # 空目录可能没有任何 module；无论哪种，都不应该是非空 SVG
        assert not [f for mf in res.files for f in mf.functions]
        assert CG.render_static_callgraph_svg(res.files, {}, {}) == ""
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_rd2_svg_is_zero_js_and_mentions_functions():
    """RD2：产物必须是 SVG，且**不含 `<script>`**（零 JS 是项目承诺）。"""
    from renderers import callgraph as CG

    d, res = _project(TWO)
    try:
        svg = CG.render_static_callgraph_svg(res.files, {}, {})
        assert svg, "两个函数却渲染出空串"
        assert svg.lstrip().startswith("<svg") or "<svg" in svg[:200], \
            "产物不是 SVG：%r" % svg[:120]
        assert "<script" not in svg.lower(), \
            "SVG 里出现了 <script> —— 违反零 JS/断网可用"
        for name in ("a", "b"):
            assert name in svg, "SVG 里没有函数 %r 的标签" % name
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_rd3_render_is_deterministic():
    """RD3：**跨进程**同一输入必须渲染出字节相同的 SVG。

    为什么不能同进程跑两次了事：`set`/`dict` 的迭代顺序由**进程哈希种子**决定，
    同进程两次一定同序 —— 那样测的是"这个进程稳定"，不是"这个函数确定"。
    真实威胁是：换一个 `PYTHONHASHSEED`，两次生成的文档就不同（diff 噪音、
    评审时看不出真改动）。所以这里用两个不同种子起子进程比对 sha256。
    """
    import subprocess

    d, res = _project(TWO)
    code = (
        "import hashlib, io, os, sys\n"
        "sys.path.insert(0, %r)\n"
        "sys.path.insert(0, %r)\n"
        "from analyzer import api as A\n"
        "from renderers import callgraph as CG\n"
        "r = A.analyze(%r)\n"
        "svg = CG.render_static_callgraph_svg(r.files, {}, {})\n"
        "sys.stdout.write(hashlib.sha256(svg.encode('utf-8')).hexdigest())\n"
    ) % (ROOT, os.path.join(ROOT, "renderers"), d)
    try:
        digs = []
        for seed in ("0", "12345"):
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = seed
            r = subprocess.run([sys.executable, "-c", code], env=env,
                               stdin=subprocess.DEVNULL, timeout=180,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            out = r.stdout.decode("utf-8", "replace").strip()
            assert r.returncode == 0, "子进程失败（seed=%s）：%s" % (seed, out[-300:])
            digs.append(out)
        assert digs[0] == digs[1], \
            "不同 PYTHONHASHSEED 渲染结果不同（%s vs %s）—— 遍历了无序容器" % tuple(digs)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_rd4_truncation_still_valid():
    """RD4：`max_nodes` 截断后仍是合法 SVG。"""
    from renderers import callgraph as CG

    d, res = _project(TWO)
    try:
        svg = CG.render_static_callgraph_svg(res.files, {}, {}, max_nodes=1)
        assert svg, "截断到 1 个节点就没有产物了"
        assert "</svg>" in svg, "截断后 SVG 不完整（缺闭合标签）"
    finally:
        shutil.rmtree(d, ignore_errors=True)
