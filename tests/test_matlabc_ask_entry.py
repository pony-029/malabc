# -*- coding: utf-8 -*-
"""`matlabc_ask.py`（456 行）：问答的**意图判定**与**检索排序**。

这层坏了不会报错，只会"答非所问"：

* `detect_intent` 把"是什么"这类问题判成 retrieve，回答就会给一堆片段而不是解释；
* `retrieve` 排序错，最相关的文档排到后面，用户看到的是**看起来合理但不对**的答案。

所以只钉两件事：意图分档、以及**最相关的那篇必须排第一**。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DOCS = [
    "colmean 计算每列均值",
    "形状不匹配通常来自 dot 与 transpose",
    "完全无关的内容 abc",
]


def test_explain_intent_is_distinguished():
    """「…是什么」→ `explain`；普通提问/空串 → `retrieve`（且不崩）。"""
    import matlabc_ask as A

    assert A.detect_intent("colmean 是什么") == "explain", \
        "『是什么』类问题没被判成 explain（会退化成列一堆片段）"
    for q in ("为什么 colmean 的结果不对", "where is mlc_op_add defined", ""):
        assert A.detect_intent(q) == "retrieve", \
            "%r 的意图判成了 %r" % (q, A.detect_intent(q))


def test_most_relevant_doc_ranks_first():
    """检索排序：与查询词重合最多的那篇必须排第一。"""
    import matlabc_ask as A

    bm = A.build_bm25(DOCS)
    got = A.retrieve("colmean 均值", DOCS, bm)
    assert got, "查询有明确命中却返回空结果"
    # 返回的是命中文档的**索引字符串**（实测形如 ['0']）
    assert str(got[0]) == "0", \
        "最相关的第 0 篇没排第一（实得 %r）—— 用户会看到答非所问的结果" % (got,)


def test_unrelated_query_does_not_promote_unrelated_doc():
    """**反向**：查一个只出现在第 0 篇的词，第 2 篇（无关）不能排到第一。"""
    import matlabc_ask as A

    bm = A.build_bm25(DOCS)
    got = A.retrieve("colmean", DOCS, bm)
    assert got, "确切命中的词竟然搜不到"
    assert str(got[0]) != "2", "无关文档被排到第一：%r" % (got,)
