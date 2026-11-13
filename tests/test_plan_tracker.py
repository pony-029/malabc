# -*- coding: utf-8 -*-
"""计划追踪表的**防腐蚀**判据：文档里的数字必须等于实测值。

为什么需要它：`docs/PLAN_TRACKER.md` 是"剩余计划"的唯一出处。
散文式计划会烂 —— 因为它没有任何对手方。这里给它两个对手方：
  1) 语料条数（数 `numeric.expected`）
  2) 覆盖率（真的编译 + 跑 + gcov，复用门里的 `measure_coverage`）

现实变了而文档没改 -> 红。于是这份表只能靠改事实或改记录变绿。
"""
import io
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_runtime_static as RS  # noqa: E402

DOC = os.path.join(ROOT, "docs", "PLAN_TRACKER.md")
EXPECTED = os.path.join(ROOT, "translate", "examples", "numeric.expected")


def _doc():
    assert os.path.isfile(DOC), "缺少 docs/PLAN_TRACKER.md"
    return io.open(DOC, encoding="utf-8").read()


def test_doc_exists_and_has_sections():
    d = _doc()
    for key in ("v1.0.0 的三个硬条件", "深度（证明方式）五项",
                "里程碑与剩余轮次", "当前状态"):
        assert key in d, "追踪表缺小节：%s" % key


def test_corpus_count_matches_reality():
    lines = [ln for ln in io.open(EXPECTED, encoding="utf-8").read().splitlines()
             if ln.strip()]
    n = len(lines)
    d = _doc()
    # 文档里必须出现 "<n>/<n>" 形式的自洽写法
    assert ("%d/%d" % (n, n)) in d, \
        "语料实际 %d 条，但 PLAN_TRACKER 里没有写「%d/%d」" % (n, n, n)


@pytest.mark.skipif(RS.measure_coverage() is None,
                    reason="没有 gcc/gcov 或 m2c 未构建")
def test_coverage_numbers_match_reality():
    line_pct, branch_pct = RS.measure_coverage()
    d = _doc()
    want_line = "%.2f%%" % line_pct
    want_branch = "%.2f%%" % branch_pct
    assert want_line in d, ("覆盖率实测行 %s，PLAN_TRACKER 里没有这个数"
                            "（现实变了要同步改表）" % want_line)
    assert want_branch in d, ("覆盖率实测分支 %s，PLAN_TRACKER 里没有这个数"
                              % want_branch)


def test_thresholds_in_doc_match_gate_source():
    d = _doc()
    # RS3 的两个阈值必须与门源码一致（文档不能自己写一套）
    assert ("%.1f" % RS.MIN_LINE_PCT) in d.replace("%", ""), \
        "文档里的行覆盖阈值与门源码 %.1f 不一致" % RS.MIN_LINE_PCT
    assert ("%.1f" % RS.MIN_BRANCH_PCT) in d.replace("%", ""), \
        "文档里的分支阈值与门源码 %.1f 不一致" % RS.MIN_BRANCH_PCT


def test_gate_count_matches_tools_dir():
    """文档里的「N 道门」必须等于 tools/check_*.py 的真实数量。"""
    # check_all.py 是 runner 本身，不算门
    n = len([f for f in os.listdir(os.path.join(ROOT, "tools"))
             if f.startswith("check_") and f.endswith(".py")
             and f != "check_all.py"])
    d = _doc()
    m = re.search(r"(\d+)\s*道门", d)
    assert m, "PLAN_TRACKER 里没有写「N 道门」"
    assert int(m.group(1)) == n, \
        "文档写 %s 道门，实际 tools/check_*.py 有 %d 个" % (m.group(1), n)


def test_no_silent_xfail():
    """全仓 `tests/` 里 **不许有 `pytest.mark.xfail`**（当前为 0，这是棘轮）。

    为什么把"0"当成要守的数：xfail 的默认语义是"失败也不红"，而它的 reason
    字段又极易写成"待定位"这种无信息文本。R811–R813 清掉了最后三个，其中**没有
    一个是它写的那个原因**（两个早已修好、一个是样本造错）。

    所以规则是：新增 xfail 必须同时把这里的 `ALLOWED` 数字改大，并在注释里
    写清"哪一侧、哪一步、什么现象"——**让豁免变成一次有记录的显式决定**，
    而不是随手加个装饰器。

    全仓零 xfail 这件事本身也是证据：所有判据现在都是"真断言"。
    """
    ALLOWED = 0
    base = os.path.join(ROOT, "tests")
    me = os.path.basename(__file__)
    hits = []
    for f in sorted(os.listdir(base)):
        if not f.endswith(".py") or f == me:
            continue                     # 本文件正文里就有这个词，别自匹配
        src = io.open(os.path.join(base, f), encoding="utf-8",
                      errors="replace").read()
        for i, ln in enumerate(src.splitlines(), 1):
            # 只认**装饰器行**：`@pytest.mark.xfail(...)`，
            # 这样注释/文档里提到这个词不会被误判。
            if re.match(r"\s*@pytest\.mark\.xfail\b", ln):
                hits.append("%s:%d" % (f, i))
    assert len(hits) <= ALLOWED, (
        "出现 %d 处 xfail（上限 %d）：%r\n"
        "  要么修掉它，要么把 ALLOWED 改大并在旁边写明理由"
        "（哪一侧、哪一步、什么现象）。" % (len(hits), ALLOWED, hits[:5]))


def test_every_test_file_is_referenced():
    """`tests/` 下每个 `test_*.py` 都必须被**某个门或工作流**引用。

    删除一个测试与**忘记运行**一个测试，在报表上完全一样 —— 都不出现。
    R762 实测：71 个文件里 **15 个从未被任何清单引用**（其中 26 个判据的文件
    已经红了一轮而无人知道）。这条判据把"清单漏项"变成红灯。
    """
    import glob
    import re as _re

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tests = sorted(os.path.basename(p) for p in
                   glob.glob(os.path.join(repo, "tests", "test_*.py")))

    hay = []
    for sub in ("tools", os.path.join(".github", "workflows"), "ci-examples"):
        d = os.path.join(repo, sub)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if os.path.isfile(p) and f.endswith((".py", ".yml", ".yaml", ".sh", ".ps1", ".md")):
                hay.append(io.open(p, encoding="utf-8", errors="replace").read())
    for f in ("README.md", "README_CN.md", "CONTRIBUTING.md"):
        p = os.path.join(repo, f)
        if os.path.isfile(p):
            hay.append(io.open(p, encoding="utf-8", errors="replace").read())
    blob = "\n".join(hay)

    orphans = [t for t in tests if not _re.search(r"\b%s\b" % _re.escape(t), blob)]
    assert not orphans, "这些测试文件未被任何门引用（红了也没人知道）：%s" % orphans
