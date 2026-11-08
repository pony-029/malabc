# -*- coding: utf-8 -*-
"""**真值完备性**专项：`numeric.expected` 必须覆盖且仅覆盖语料。

## 三个问题，三种漏法

| 检查 | 漏了会怎样 |
|---|---|
| 每个 `.m` 都有真值 | 没真值的函数**永远不会被验**，但测试照样绿 |
| 没有孤儿真值 | 函数删了、真值留着 → 数字对不上人却不知道 |
| 每条真值非空 | 空串会让 `==` 比较永远成立（空 vs 空） |

外加一条**覆盖度**：哪些算子从未被任何真值覆盖 —— 那是"测试没碰到"的算子。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import operators as O      # noqa: E402

CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")
EXP = os.path.join(ROOT, "translate", "examples", "numeric.expected")


def _expected():
    d = {}
    for ln in io.open(EXP, encoding="utf-8", errors="replace"):
        ln = ln.strip()
        if ln and ":" in ln:
            k, v = ln.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def _stems():
    return {f[:-2] for f in os.listdir(CORPUS) if f.endswith(".m")}


def test_every_corpus_function_has_truth():
    """**每个语料函数都必须有真值** —— 否则它从未被验证过。"""
    have, need = set(_expected()), _stems()
    missing = sorted(need - have)
    assert not missing, "缺真值 %d 个：%r" % (len(missing), missing[:8])


def test_no_orphan_truth():
    """真值里不能有语料中已不存在的函数（删函数时忘了删真值）。"""
    have, need = set(_expected()), _stems()
    orphan = sorted(have - need)
    assert not orphan, "孤儿真值 %d 个：%r" % (len(orphan), orphan[:8])


def test_truth_not_empty():
    bad = [k for k, v in _expected().items() if not v.strip()]
    assert not bad, "空真值 %d 个：%r" % (len(bad), bad[:8])


def test_operator_coverage_is_reported():
    """统计"从未被语料用到的算子" —— 它们是**没被测过**的代码。

    这里不断言为零（那会把判据变成"必须写满所有算子"的负担），
    只断言**覆盖率不低于下界**，并把缺口打印出来，让下一轮有得选。
    """
    # **只统计"能按函数名检测"的算子**：`a + b` 这种样本没有函数名，
    # 用名字找它必然找不到 —— 把它们算进分母只会让指标失去意义（第一版就是这样
    # 把 OP-ADD/OP-MUL 报成"未覆盖"的）。
    named, cosmetic = {}, []
    for op in O.OPERATORS:
        sample = str(op.get("matlab") or "")
        head = sample.split("(")[0].strip()
        if "(" in sample and head.isidentifier():
            named[op["id"]] = head
        else:
            cosmetic.append(op["id"])

    used = set()
    for f in os.listdir(CORPUS):
        if not f.endswith(".m"):
            continue
        src = io.open(os.path.join(CORPUS, f), encoding="utf-8",
                      errors="replace").read()
        for oid, head in named.items():
            if head in src:
                used.add(oid)

    covered = used & set(named)
    pct = 100.0 * len(covered) / max(1, len(named))
    uncovered = sorted(set(named) - covered)
    print("算子覆盖（按函数名可检测的 %d 个）：%d → %.1f%%"
          % (len(named), len(covered), pct))
    print("  未覆盖：%s" % ", ".join(uncovered[:12]))
    print("  无法按名检测（运算符类，%d 个）：%s"
          % (len(cosmetic), ", ".join(cosmetic[:8])))
    assert pct >= 25.0, "算子覆盖率过低（%.1f%%），真值集已经和算子表脱节" % pct
