# -*- coding: utf-8 -*-
"""特性矩阵里引用的每个语料文件必须**真实存在**。

为什么：`FEATURE_MATRIX.md` 的每一行都靠"证据文件"取信于读者。
文件一旦被改名/删除，那句话就变成**无法核对的主张** —— 而文档本身不会报错。
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOC = os.path.join(ROOT, "docs", "FEATURE_MATRIX.md")


def _doc():
    return io.open(DOC, encoding="utf-8").read()


def test_doc_exists():
    assert os.path.isfile(DOC), "FEATURE_MATRIX.md 不见了"


def test_referenced_files_exist():
    text = _doc()
    # 反引号里形如 xxx/yyy.m 或 aa.m 的路径
    refs = set(re.findall(r"`([\w\\\\/\.\-]+\.m)`", text))
    refs |= set(re.findall(r"`(examples/[\w\\\\/\.\-]+/)`", text))
    missing = []
    for r in sorted(refs):
        rel = r.replace("\\", "/").rstrip("/")
        cand = [os.path.join(ROOT, "translate", "examples", rel),
                os.path.join(ROOT, "translate", rel),
                os.path.join(ROOT, "translate", "examples", "numeric", rel),
                os.path.join(ROOT, rel)]
        if r.endswith("/"):
            ok = any(os.path.isdir(c) for c in cand)
        else:
            ok = any(os.path.isfile(c) for c in cand)
        if not ok:
            missing.append(r)
    assert not missing, "特性矩阵引用了不存在的文件：%s" % missing


def test_matrix_has_both_sides():
    """支持与不支持两侧都要有，且支持条目不少于 15 行。"""
    text = _doc()
    sup = text.split("## 一、")[1].split("## 二、")[0]
    rows = [ln for ln in sup.splitlines() if ln.startswith("|") and "---" not in ln]
    assert len(rows) >= 16, "支持表行数过少：%d" % len(rows)
    assert "## 二、不支持" in text
