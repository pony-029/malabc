# -*- coding: utf-8 -*-
"""`entity_model.py`（仓根）：实体/成员的**类型白名单**与一致性。

这层的校验函数（`entity_problems` / `member_problems` / `conformance_problems`）
都"返回问题清单"而不抛异常 —— 温和的接口最容易变成永远返回 `[]`。

三条判据各自盯一个方向：

* 合法实体 → 空清单（不误报）；
* `kind` 不在白名单 → **必须报**，且报出"允许哪些"（否则调用方不知道该改成什么）；
* 多个实体 → `conformance_problems` 要**带下标**（第几个），否则定位不到是谁。

⚠ 一个实测过的坑：`blank_member` 的签名是 `(name, kind, type, line)` ——
**名字在前、种类在后**。按 `(kind, name)` 传会得到一个 `kind` 非法的成员，
而错误信息只会说"`kind`='x' 不在…"，很容易被误读成白名单有问题。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_valid_entity_and_member_have_no_problems():
    """合法实体 + 合法成员 → 空清单（判据不能自己先偏）。"""
    import entity_model as E

    e = E.blank_entity("class", "Foo")
    assert E.entity_problems(e) == [], \
        "合法实体被判有问题：%r" % (E.entity_problems(e),)
    # 注意参数顺序：name 在前、kind 在后
    m = E.blank_member("x", "field")
    assert E.member_problems(m) == [], \
        "合法成员被判有问题：%r" % (E.member_problems(m),)


def test_bad_kind_is_reported_with_whitelist():
    """非法 `kind` 必须报，并且**把允许值一并说出来**。"""
    import entity_model as E

    bad = E.blank_entity("function", "foo")      # function 不是实体种类
    probs = E.entity_problems(bad)
    assert probs, "非法 kind 竟然没问题"
    blob = " ".join(probs)
    assert "kind" in blob, "报错没指明是 kind 的问题：%r" % (probs,)
    assert "class" in blob, "报错没列出允许值（调用方不知道该改成什么）：%r" % (probs,)


def test_conformance_reports_index():
    """多实体校验必须**带下标**，否则定位不到是谁。"""
    import entity_model as E

    good = E.blank_entity("class", "Ok")
    bad = E.blank_entity("function", "Bad")
    assert E.conformance_problems([good]) == []
    probs = E.conformance_problems([good, bad])
    assert probs, "坏实体混在里面竟然通过"
    assert any("第 1 个" in p for p in probs), \
        "报错没带下标（不知道是第几个实体）：%r" % (probs,)
