# -*- coding: utf-8 -*-
"""`pyast_frontend.py`（仓根，933 行）：Python 源码 → IR 的**解析契约**。

这层是"多语言前端"里唯一自带解析器的模块，产出直接喂给图谱与报表。
所以判据盯**结构**而不是实现：字段名一改，下游全是静默空表。

四条性质：

* 顶层键固定 `{rel, path, functions, imports, classes, globals}`；
* 函数项带 `name/line/params`（行号从 1 起，**不能是 0**）；
* import 记成 `(模块, 名字, 行)` 三元组 —— 两段式 `from sys import argv` 也要能拆；
* `function_problems` 会对坏字段报错，但**不为"没有要求"的字段报警**（`body_start=0` 合法）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SRC = "def foo(a, b=1):\n    return a + b\n"
SRC2 = "import os\nfrom sys import argv\n\nclass K:\n    def m(self):\n        pass\n"


def test_parse_ast_shape():
    """顶层键集合固定；函数项的行号从 1 起、形参名完整。"""
    import pyast_frontend as P

    r = P.parse_ast(SRC, "a.py", "", {})
    assert set(r) == {"rel", "path", "functions", "imports", "classes",
                      "globals"}, "顶层键变了（下游会静默空表）：%r" % sorted(r)
    assert r["rel"] == "a.py"
    fns = r["functions"]
    assert len(fns) == 1, "一个函数却解析出 %d 个" % len(fns)
    fn = fns[0]
    assert fn["name"] == "foo"
    assert fn["line"] == 1, "行号应为 1，实得 %r" % (fn["line"],)
    assert fn["params"] == ["a", "b"], "形参名不对：%r" % (fn["params"],)


def test_imports_are_triples_and_classes_have_line():
    """import 是 `(模块, 名字, 行)`；class 带名字与行号。"""
    import pyast_frontend as P

    r = P.parse_ast(SRC2, "b.py", "", {})
    assert r["imports"] == [("os", "os", 1), ("sys", "argv", 2)], \
        "import 三元组不对（两段式没拆开？）：%r" % (r["imports"],)
    assert [(c["name"], c["line"]) for c in r["classes"]] == [("K", 4)], \
        "class 解析不对：%r" % (r["classes"],)


def test_function_problems_reports_bad_fields():
    """坏字段必须报，且**指出是哪个字段**。"""
    import pyast_frontend as P

    fn = P.parse_ast(SRC, "a.py", "", {})["functions"][0]
    assert P.function_problems(fn) == [], "合法函数被判有问题"

    for key, bad, word in (("line", 0, "line"),
                           ("params", "notalist", "params"),
                           ("name", "", "name")):
        f2 = dict(fn)
        f2[key] = bad
        probs = P.function_problems(f2)
        assert probs, "%s=%r 竟然没报" % (key, bad)
        assert any(word in p for p in probs), \
            "报错没指明字段 %r：%r" % (word, probs)


def test_unspecified_field_is_not_flagged():
    """**反向**：`body_start=0` 不是问题（该字段没有"必须 >=1"的约束）。

    过度校验会让这条判据被当成噪音关掉 —— 于是连真问题也没人看。
    """
    import pyast_frontend as P

    fn = P.parse_ast(SRC, "a.py", "", {})["functions"][0]
    f2 = dict(fn)
    f2["body_start"] = 0
    assert P.function_problems(f2) == [], \
        "body_start=0 被误报：%r" % (P.function_problems(f2),)
