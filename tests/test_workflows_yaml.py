# -*- coding: utf-8 -*-
"""CI workflow 必须是**合法 YAML**。

为什么值得一条用例：R463 发现 `port-ci.yml` 里有一行

    - name: Generated project: cmake + ctest

步骤名里多了一个 `: `，整份 workflow 解析失败 —— GitHub 会直接判
"Invalid workflow file"。也就是说**那条 CI 从来没有跑过**，而本地门全绿，
没人会发现。这类"配置静默失效"只能用解析器抓。
"""
import io
import os

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows")


def _files():
    if not os.path.isdir(WF):
        return []
    return sorted(f for f in os.listdir(WF) if f.endswith((".yml", ".yaml")))


@pytest.mark.parametrize("name", _files() or ["<none>"])
def test_workflow_parses(name):
    if name == "<none>":
        pytest.skip("仓库里没有 workflow")
    path = os.path.join(WF, name)
    text = io.open(path, encoding="utf-8").read()
    doc = yaml.safe_load(text)          # 解析失败会直接抛异常 -> 用例失败
    assert isinstance(doc, dict), "%s 顶层不是映射" % name
    # 至少要有 name 与 on（`on` 在 YAML 1.1 里会被解析成 True）
    assert "name" in doc, "%s 缺 name" % name
    assert "on" in doc or True in doc, "%s 缺 on（触发条件）" % name


def test_utf8_env_pinned():
    """workflow 级别固定 UTF-8：否则子进程用 GBK 打印 `⇄` 会崩，
    而门只会看到"非零退出"，把编码崩溃误判成被测失败。"""
    for name in _files():
        text = io.open(os.path.join(WF, name), encoding="utf-8").read()
        if "PYTHONIOENCODING" in text:
            continue
        # 允许没有 Python 步骤的 workflow
        if "python" not in text.lower():
            continue
        assert False, "%s 有 Python 步骤但没固定 PYTHONIOENCODING" % name
