# -*- coding: utf-8 -*-
"""分析侧的行为判据（`analyzer/` + `binfmt/`）。

## 为什么补这一层（R819 的读数逼出来的）

职责域表加上「提及它的判据文件」一列后：

```
分析侧   3 个目录 / 75 个文件 / **只有 4 条判据提到它**
```

75 个文件的层，被验证的程度与 14 个文件的 `vscode/` 差不多。这不是"代码一定有问题"，
而是"坏了很可能没人知道" —— 而这正是判据要解决的事。

## 三条判据各自守什么

* **AL1** `analyze()` 的计数**只有四个真实存在的项**（不是拿 0 冒充）；
* **AL2** 目录不存在必须抛 `ValueError`（而不是返回一个空结果）；
* **AL3** 同一导出符号被两个二进制定义 → `conflicts()` 必须报出来。

AL1 直接照抄了该模块自己的注释："这里不猜、不用 0 冒充：缺的就是不在" ——
判据的价值就在于让那句话**变成会响的东西**。
"""
import io
import os
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "analyzer", "binfmt"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def _write(d, rel, body):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline="\n").write(body)


def test_al1_counts_are_only_real_ones():
    """AL1：`counts()` 必须只给真实存在的四项。

    该模块的注释写着「不猜、不用 0 冒充：缺的就是不在」。这条判据把它变成断言：
    多给一项（比如拿 `heuristics` 凑数）就红 —— 因为那一项在这一层根本没有来源。
    """
    from analyzer import api as A

    d = tempfile.mkdtemp(prefix="al1_",
                         dir=os.environ.get("M2C_TMP") or None)
    try:
        _write(d, "a.m", "function y = a(x)\ny = x + 1;\nend\n")
        _write(d, "b.m", "function y = b(x)\ny = a(x) * 2;\nend\n")
        res = A.analyze(d)
        c = A.counts(res)
        assert set(c) == {"files", "functions", "edges", "checks"}, \
            "counts() 的键集合变了（要么多给了不存在的项，要么漏了真项）：%r" % sorted(c)
        assert c["files"] == 2, "文件数应为 2，实得 %r" % c["files"]
        # `checks` 是 `checks_for_sarif` 的长度，**不是** heuristics 的别名
        assert c["checks"] == len(getattr(res, "checks_for_sarif", []) or [])
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_al2_missing_dir_raises():
    """AL2：目录不存在必须抛 `ValueError` —— 空结果会被下游当成"分析成功但没有东西"。"""
    from analyzer import api as A

    missing = os.path.join(ROOT, "tests", "__no_such_dir__")
    assert not os.path.isdir(missing)
    with pytest.raises(ValueError):
        A.analyze(missing)


def test_al4_library_filename_is_not_rewrapped():
    """AL4：**已经是文件名**的引用不能再套一遍 `-l` 拼法。

    该函数自己的注释就写着这个坑：对 `libfoo.so.1` 再拼一次会产出
    `libfoo.so.1.so` 这样的噪音候选，而它"不会找不到"，只会让解析绕远路。
    所以判据盯的是**负向**：噪音不能出现；同时正向要有去版本后的规范名。
    """
    from binfmt import resolve as R

    got = R.candidate_names("libfoo.so.1")
    assert "libfoo.so" in got, "没有补出 SONAME 规范名：%r" % (got,)
    assert "libfoo.so.1.so" not in got, "把文件名又当 -l 简名拼了一遍：%r" % (got,)


def test_al5_short_name_expands_to_platform_forms():
    """AL5：`-l` 简名要展开成三种平台的候选（.so / .dll / .dylib）。"""
    from binfmt import resolve as R

    got = R.candidate_names("m")
    for want in ("libm.so", "m.dll", "libm.dylib"):
        assert want in got, "简名展开缺 %r：%r" % (want, got)


def test_al6_cmake_link_vars_are_not_deps():
    """AL6：`target_link_libraries` 里的变量引用不能被当成库名。

    变量在构建期才展开；把它写成一条依赖，等于给用户一个查不到的库。
    """
    from binfmt import buildsys as B

    deps, _notes = B.parse_cmake(
        "target_link_libraries(app PRIVATE blas ${EXTRA_LIBS})\n", "CMakeLists.txt")
    names = [d.name for d in deps]
    assert "blas" in names, "普通库名没被解析出来：%r" % (names,)
    assert not any("${" in n for n in names), "变量被当成了库名：%r" % (names,)


def test_al3_conflicting_exports_are_reported():
    """AL3：同一导出符号被多个二进制定义，必须报出来。

    这是**纯二进制侧就能发现**的真问题（符号将被链接器静默择一），
    也是这一层存在的理由之一：不看源码也能说话。
    """
    from binfmt import attribute as AT
    from binfmt.model import BinaryReport, Symbol, SYM_EXPORT

    a = BinaryReport(path="liba.so")
    a.symbols = [Symbol("dup_entry", SYM_EXPORT, origin="liba.so")]
    b = BinaryReport(path="libb.so")
    b.symbols = [Symbol("dup_entry", SYM_EXPORT, origin="libb.so")]

    got = AT.conflicts([a, b])
    assert got, "两个二进制导出同名符号，conflicts() 却什么都没报"
    assert any("dup_entry" in str(x) for x in got), \
        "报告里没提到冲突符号名：%r" % (got,)

    # 反向：不冲突时不能报（否则这个检查会被当成噪音关掉）
    c = BinaryReport(path="libc.so")
    c.symbols = [Symbol("other_entry", SYM_EXPORT, origin="libc.so")]
    assert not AT.conflicts([a, c]), "不同符号竟被判成冲突：%r" % (AT.conflicts([a, c]),)
