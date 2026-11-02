# -*- coding: utf-8 -*-
"""RS3 的**排除区**机制判据。

`mlc_ops.c` 里有两条执行路径：f64 主路径（语料覆盖）与 Q15 定点路径
（由 `tests/test_q15_ops.py` 守护）。RS3 只应统计前者 —— 否则每加一批定点算子，
指标就掉一截，最后只能一路下调阈值（62.6 → 59.4 → 58.7 → 56.5）。

但"排除"是危险的：它可以被用来**藏起测不到的代码**。所以这里三条判据：
1. 标记必须成对；
2. 排除区必须**全部是定点相关**（抽查区内的函数名）；
3. 排除区外**不许**出现第二个标记 —— 一次只允许一处、且有明确理由。

外加一条纯单元测试：`_gcov_stats` 真的跳过被排除的行。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "c_runtime", "src", "mlc_ops.c")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_runtime_static as RS  # noqa: E402


def _lines():
    return io.open(SRC, encoding="utf-8", errors="replace").read().replace("\r\n", "\n").split("\n")


def test_markers_are_paired_and_unique():
    lines = _lines()
    begins = [i for i, x in enumerate(lines, 1) if "coverage-exclude begin" in x]
    ends = [i for i, x in enumerate(lines, 1) if "coverage-exclude end" in x]
    assert len(begins) == 1 and len(ends) == 1, (begins, ends)
    assert begins[0] < ends[0], "begin 必须在 end 之前"


def test_excluded_region_is_fixed_point_only():
    """排除区里只许有定点相关的东西 —— 这是它成立的唯一理由。"""
    lines = _lines()
    b = next(i for i, x in enumerate(lines, 1) if "coverage-exclude begin" in x)
    e = next(i for i, x in enumerate(lines, 1) if "coverage-exclude end" in x)
    body = "\n".join(lines[b:e - 1])
    assert "q15" in body.lower(), "排除区里必须真的是定点实现"
    # 抽查：区内不许出现普通的 f64 算子（那才是语料该覆盖的东西）
    for bad in ("mlc_op_sum(", "mlc_op_add(", "mlc_op_sqrt("):
        assert bad not in body, "排除区里不该有主路径算子：%s" % bad


def test_excluded_lines_cover_q15_symbols():
    lines = _lines()
    excluded = RS._excluded_lines(SRC)
    assert excluded, "必须解析出排除行"
    for name in ("mlc_op_q15_add", "mlc_op_q15_mul", "mlc_q15_sat"):
        ln = next((i for i, x in enumerate(lines, 1) if name + "(" in x and "mlc_" in x), None)
        assert ln is not None, name
        assert ln in excluded, "%s 所在的第 %d 行未被排除" % (name, ln)


def test_gcov_stats_skips_excluded(tmp_path=None):
    """单元级：同一份 .gcov，排除未执行的那几行后，覆盖率必须上升。"""
    import tempfile
    d = tempfile.mkdtemp(prefix="m2c_rs3u_")
    try:
        g = os.path.join(d, "x.c.gcov")
        io.open(g, "w", encoding="utf-8").write(
            "        -:    1:/* head */\n"
            "        1:    2:int a;\n"
            "        0:    3:int b;\n"      # 未执行（在第 2 段）
            "        1:    4:int c;\n"
            "branch  0 taken 1\n"
            "branch  1 never executed\n")
        allp = RS._gcov_stats(g, set())
        somep = RS._gcov_stats(g, {3})
        assert allp is not None and somep is not None
        # 可执行行是 2/3/4（第 1 行 `-` 不可执行）；执行了 2 行 -> 66.67%
        assert abs(allp[0] - 66.6667) < 0.01, allp
        # 排除未执行的第 3 行后只剩两行且都执行 -> 100%
        assert abs(somep[0] - 100.0) < 0.01, somep
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
