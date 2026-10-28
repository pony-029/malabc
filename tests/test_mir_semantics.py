# -*- coding: utf-8 -*-
"""`docs/MIR_SEMANTICS.md` 的**完整性判据** —— 规范不能悄悄落后于实现。

为什么需要：语义规范的最大失效方式不是"写错"，而是**新增了算子却没写进去**。
那时文档仍然自洽、仍然好看，只是它描述的是一个更小的系统。

三条判据：
1. `operators.py` 里每个 opcode 都必须在文档里出现（新增算子不写文档 -> 红）；
2. 五个必填小节都在（数据模型 / 通用规则 / 逐条 / 未定义 / 守住方式）；
3. 通用规则 G1–G5 逐条都在（规则不能被悄悄删掉）。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import operators as O  # noqa: E402

DOC = os.path.join(ROOT, "docs", "MIR_SEMANTICS.md")


def _doc():
    assert os.path.isfile(DOC), "缺少 docs/MIR_SEMANTICS.md"
    return io.open(DOC, encoding="utf-8").read()


def test_every_opcode_is_documented():
    d = _doc()
    missing = [o["id"] for o in O.OPERATORS if o["id"] not in d]
    assert not missing, (
        "这些算子没写进语义规范：%s\n"
        "（新增算子必须同步 docs/MIR_SEMANTICS.md：dtype/形状/所有权/错误/顺序）"
        % missing)


def test_required_sections_present():
    d = _doc()
    for sec in ("## 一、数据模型", "## 二、五条通用规则",
                "## 三、算子逐条", "## 四、明确", "## 五、这份文档怎么被守住"):
        assert sec in d, "语义规范缺小节：%s" % sec


def test_general_rules_present():
    d = _doc()
    for g in ("G1", "G2", "G3", "G4", "G5"):
        assert g in d, "通用规则 %s 不见了" % g


def test_doc_declares_undefined_areas():
    """「未定义」小节必须至少列出 init 重复调用与别名 —— 这是 D4 的教训。"""
    d = _doc()
    for key in ("`init` 的重复调用", "别名"):
        assert key in d, "「未定义」小节缺 %s（它是这条教训的来源）" % key
