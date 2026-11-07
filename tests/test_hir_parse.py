# -*- coding: utf-8 -*-
"""验收 D2/D3：HIR 解析 + 降级。

## 委派产物的真实缺陷（本轮抓到两个）

模型给的代码**看起来完整**，但有两处会在使用时出错：

1. `"mem.setidx2": "OP-SETDIFF"` —— 映射写错。`OP-SETDIFF` **确实存在**，
   所以"id 是否存在"这条判据抓不到它，必须**与已验收的 D1 表比对**；
2. 表达式解析器不认数字字面量（`0` / `2`），遇到就报 "unexpected char"。

⇒ 这两条正好说明：委派产物的判据不能只验"格式合法"，要验**与既有真值一致**。
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import hir as H           # noqa: E402
from translate import hir_ops as HO      # noqa: E402


def test_mapping_matches_accepted_table():
    """降级用的映射必须与 D1 已验收的表一致（能抓到"id 存在但映射写错"）。"""
    from translate import hir as _h
    assert _h._HO.HIR_TO_MIR == HO.HIR_TO_MIR
    # 逐条点名最容易写错的两项
    assert HO.mir_of("mem.setidx2") == "OP-SETIDX2"
    assert HO.mir_of("set.setdiff") == "OP-SETDIFF"


def test_parse_basic_shape():
    prog = H.parse_hir(
        "hir 1\n"
        "func: snr\n"
        "  param sig vec[4]\n"
        "  ret y scalar\n"
        "  v1 = ew.mul(sig, sig)\n")
    kinds = [p["kind"] for p in prog]
    assert kinds == ["func", "param", "ret", "let"]
    assert prog[1]["name"] == "sig" and prog[1]["type"] == "vec[4]"
    assert prog[3]["dst"] == "v1"
    assert prog[3]["expr"]["op"] == "ew.mul"
    assert [a.get("var") for a in prog[3]["expr"]["args"]] == ["sig", "sig"]


def test_parse_number_literal():
    """数字字面量必须能解析（委派版本此处报错）。"""
    prog = H.parse_hir("hir 1\nfunc: f\n  y = ew.add(x, 1)\n")
    args = prog[1]["expr"]["args"]
    assert args[1] == {"num": "1"}


def test_lower_simple():
    out = H.hir_to_mir("hir 1\nfunc: f\n  v = ew.mul(a, b)\n")
    assert out == "op:OP-MUL:v:a:b"


def test_lower_nested_postorder():
    """嵌套：后序降级，临时量 __h1/__h2 顺序固定。"""
    out = H.hir_to_mir("hir 1\nfunc: f\n  y = ew.div(red.mean(ew.mul(a, a)), b)\n")
    assert out.split("\n") == [
        "op:OP-MUL:__h1:a:a",
        "op:OP-MEAN:__h2:__h1",
        "op:OP-DIV:y:__h2:b",
    ]


def test_unknown_op_raises():
    """未登记的 HIR 算子必须报错，不得猜。"""
    with pytest.raises(ValueError):
        H.hir_to_mir("hir 1\nfunc: f\n  y = zz.unknown(a)\n")


def test_bad_header_raises():
    with pytest.raises(ValueError):
        H.parse_hir("func: f\n")
