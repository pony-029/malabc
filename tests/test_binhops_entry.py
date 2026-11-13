# -*- coding: utf-8 -*-
"""`binhops.py`（仓根）：二进制跳的**装置登记表**（67 行，`HOP_DEVICES` 是唯一事实源）。

这张表的作用不是"记录信息"，而是**禁止猜**：`binhop` 边的 `via_device` 必须登记在册，
未登记就由 `check_unified_graph` 判红。所以判据要守三件事：

* **前缀直方图是派生量**：`census()` 各组之和必须等于登记条数（手写数字会漂）；
* **两个方向**：登记过的 id 判 True、没登记过的判 False；
* **空 id 恒为 False** —— 空串不能被当成"默认通过"，那等于给未标注的边开口子。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_census_is_derived_not_handwritten():
    """直方图各组之和必须等于 `HOP_DEVICES` 条数（派生量不能手写）。"""
    import binhops as B

    c = B.census()
    assert isinstance(c, dict) and c, "census() 没给出内容"
    assert sum(c.values()) == len(B.HOP_DEVICES), \
        "直方图合计 %d != 登记条数 %d（有装置没被计入，或数字是手写的）" % (
            sum(c.values()), len(B.HOP_DEVICES))
    # 直方图的键必须是 id 的前缀（`elf.dynsym` → `elf`）
    for k in c:
        assert any(i.split(".", 1)[0] == k for i in B.HOP_DEVICES), \
            "直方图出现了不是前缀的组：%r" % k


def test_registration_is_two_way():
    """双向：登记过的 id → True；没登记过的 → False 且被列进未登记。"""
    import binhops as B

    real = sorted(B.HOP_DEVICES)[0]              # 例如 elf.dynsym
    assert B.is_registered(real) is True, "登记表里的 %r 竟被判未登记" % real
    assert B.unregistered_devices([real]) == []

    ghost = "__definitely_not_a_device__"
    assert B.is_registered(ghost) is False
    assert B.unregistered_devices([ghost]) == [ghost]


def test_empty_id_is_never_registered():
    """空 id 恒为 False —— 否则"没标注"会被当成"默认合法"。"""
    import binhops as B

    assert B.is_registered("") is False
    assert B.is_registered(None) is False
    assert B.unregistered_devices([""]) == [""]


def test_unregistered_keeps_order_and_dedups():
    """未登记清单保持输入顺序并去重（否则同一设备会被报多次）。"""
    import binhops as B

    got = B.unregistered_devices(["zz", "aa", "zz", "bb"])
    assert got == ["zz", "aa", "bb"], "顺序或去重不对：%r" % (got,)
