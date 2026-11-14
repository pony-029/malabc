# -*- coding: utf-8 -*-
"""`matlabc_flow.py`（仓根，629 行）：补丁的**语句保持不变量**。

这是本仓少见的"拒绝应用"闸门：补丁落盘前必须自证"没吞掉源码语句"。
判据四向：

* 计数函数 `patch_edit_counts` 的返回值是 `(删除, 新增, hunk 数)`；
* 纯新增补丁 → 通过（不删东西就不可能违法）；
* 删了行但报告没声明 `dead_code` → **必须拒**，且理由说清差多少；
* 删 1 行 + 声明 1 条 `dead_code` → 通过。

⚠ 实测发现判定用的是**精确相等**（`removed != allowed`），不是 `<=`：
声明 2 条 `dead_code` 而只删 1 行也会被拒。这可能是"补丁总是删光所有死代码"的
设计假设，也可能是过严 —— 这里按现状钉住，**一旦有人改成 `<=`，这条判据会红**，
那时应该是一个有意识的决定，而不是顺手改。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

ADD_ONLY = """--- a/x.m
+++ b/x.m
@@ -1,2 +1,3 @@
 y = 1;
+z = 2;
 w = 3;
"""

REMOVE_ONE = """--- a/x.m
+++ b/x.m
@@ -1,2 +1,1 @@
-y = 1;
 z = 3;
"""


def test_edit_counts_tuple_order():
    """计数返回 `(删除, 新增, hunk 数)` —— 顺序错了会让后面的闸门全反。"""
    import matlabc_flow as M

    assert M.patch_edit_counts(ADD_ONLY) == (0, 1, 1)
    assert M.patch_edit_counts(REMOVE_ONE) == (1, 0, 1)
    assert M.patch_edit_counts("") == (0, 0, 0)


def test_add_only_patch_is_allowed():
    """纯新增：不可能吞语句 → 必须通过。"""
    import matlabc_flow as M

    ok, detail = M.check_patch_preserves_source(ADD_ONLY, [])
    assert ok is True, "纯新增补丁被拒：%r" % (detail,)
    assert detail["removed"] == 0 and detail["added"] == 1


def test_removal_without_declaration_is_rejected():
    """删行但报告没声明 `dead_code` → 拒绝，且理由里带上差值。"""
    import matlabc_flow as M

    ok, detail = M.check_patch_preserves_source(REMOVE_ONE, [])
    assert ok is False, "删了 1 行却没拒（覆盖式插入会吞语句）"
    assert detail["allowed_removals"] == 0
    assert "删除" in detail.get("reason", ""), \
        "理由没说明是删除行的问题：%r" % (detail.get("reason"),)


def test_removal_matching_one_declaration_is_allowed():
    """删 1 行 + 声明 1 条 `dead_code` → 通过。"""
    import matlabc_flow as M

    ok, detail = M.check_patch_preserves_source(
        REMOVE_ONE, [{"rule": "dead_code"}])
    assert ok is True, "声明了 1 条 dead_code 仍被拒：%r" % (detail,)
    assert detail["allowed_removals"] == 1


def test_judgement_is_exact_match_not_upper_bound():
    """**钉住现状**：判定是精确相等，不是"不超过"。

    声明 2 条却只删 1 行 → 拒绝。若将来改成 `<=`，这条会红 —— 那应当被当作
    一次显式决定来评审，而不是顺手放宽。
    """
    import matlabc_flow as M

    ok, detail = M.check_patch_preserves_source(
        REMOVE_ONE, [{"rule": "dead_code"}, {"rule": "dead_code"}])
    assert ok is False, \
        "判定语义变了（现在允许少删），请确认是有意的：%r" % (detail,)
    assert detail["allowed_removals"] == 2
