# -*- coding: utf-8 -*-
"""`fe_audit.py`（仓根，3121 行）：前端审计的**收集入口**。

3121 行里大部分是检查器（链接/CDN/JS 语法/运行时），它们都需要一个真实站点。
唯一能独立钉住的是 `collect_html(outdir)` —— 而它恰恰是所有检查器的**输入**：
少收一个页面，后面所有检查都会对那个页面"报告健康"。

判据三条：只收 `.html`、返回绝对路径、空目录给空列表（不崩也不编）。
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _tmp():
    tmp = os.environ.get("M2C_TMP")
    return tempfile.mkdtemp(prefix="fe_",
                            dir=tmp if tmp and os.path.isdir(tmp) else None)


def test_collect_html_only_html_and_absolute():
    """只收 `.html`，且返回的都是绝对路径（检查器直接打开它们）。"""
    import fe_audit as FE

    d = _tmp()
    try:
        for name, body in (("a.html", "<html></html>"),
                           ("b.txt", "no"),
                           ("c.htm", "<html></html>")):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(body)
        got = FE.collect_html(d)
        names = sorted(os.path.basename(p) for p in got)
        assert "a.html" in names, "漏收了 a.html：%r" % (names,)
        assert "b.txt" not in names, "把 .txt 也收进来了：%r" % (names,)
        for p in got:
            assert os.path.isabs(p), "返回了相对路径（检查器会按 cwd 找错地方）：%r" % (p,)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_collect_html_empty_dir_is_empty_list():
    """空目录 → 空列表（不要崩，也不要编一个默认页）。"""
    import fe_audit as FE

    d = _tmp()
    try:
        assert FE.collect_html(d) == []
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_collect_html_missing_dir_does_not_crash():
    """目录不存在时也不能崩 —— 它在"还没生成站点"的阶段就会被调用。"""
    import fe_audit as FE

    missing = os.path.join(ROOT, "__no_such_site__")
    assert not os.path.isdir(missing)
    got = FE.collect_html(missing)
    assert got == [], "缺目录时返回了 %r（应给空列表）" % (got,)
