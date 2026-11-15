# -*- coding: utf-8 -*-
"""`binfmt/buildsys.scan`：**目录级**依赖收集（上一层的 `parse_cmake` 只认文本）。

## 为什么单独一个文件

`parse_cmake` / `parse_makefile` 只看**一段文本**；`scan` 决定"看哪些文件"。
它一旦出错，后面所有解析都作用在错误的集合上 —— 而且**不会报错**，
只会安静地少收（或多收）几个文件。

三条性质：

* **递归边界**：`recursive=False` 不碰子目录，`True` 才进去；
* **变量不当库名**：`${EXTRA_LIBS}` 不是依赖，但要留 notes 说出来；
* **目录不存在**：返回空、不抛 —— 它在"还没构建"的阶段就会被调用。
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "binfmt"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def _project():
    tmp = os.environ.get("M2C_TMP")
    d = tempfile.mkdtemp(prefix="scan_",
                         dir=tmp if tmp and os.path.isdir(tmp) else None)
    with open(os.path.join(d, "CMakeLists.txt"), "w", encoding="utf-8") as f:
        f.write("add_executable(app main.c)\n"
                "target_link_libraries(app PRIVATE blas ${EXTRA_LIBS})\n")
    with open(os.path.join(d, "Makefile"), "w", encoding="utf-8") as f:
        f.write("app: main.o\n\tcc -o app main.o -lm -lz\n")
    sub_dir = os.path.join(d, "sub")
    os.makedirs(sub_dir)
    with open(os.path.join(sub_dir, "CMakeLists.txt"), "w", encoding="utf-8") as f:
        f.write("target_link_libraries(sub PRIVATE lapack)\n")
    return d


def test_recursive_sees_subdir_and_non_recursive_does_not():
    """**递归边界双向**：子目录的 `lapack` 只在 recursive=True 时出现。"""
    from binfmt import buildsys as B

    d = _project()
    try:
        deep, _ = B.scan(d, recursive=True)
        shallow, _ = B.scan(d, recursive=False)
        deep_names = {x.name for x in deep}
        shallow_names = {x.name for x in shallow}

        assert "lapack" in deep_names, "递归模式漏了子目录里的依赖：%r" % (deep_names,)
        assert "lapack" not in shallow_names, \
            "非递归模式竟然进了子目录：%r" % (shallow_names,)
        # 本层两个文件都要被看到
        for want in ("blas", "m", "z"):
            assert want in shallow_names, "本层的 %r 没被收集：%r" % (want, shallow_names)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_unexpanded_variable_is_not_a_dependency():
    """`${EXTRA_LIBS}` 不是库名，但必须在 notes 里说出来（不能静默跳过）。"""
    from binfmt import buildsys as B

    d = _project()
    try:
        deps, notes = B.scan(d, recursive=False)
        names = {x.name for x in deps}
        assert not any("$" in n for n in names), "变量被当成库名：%r" % (names,)
        assert notes, "有未展开变量却没有任何 notes（读者以为全解析了）"
        assert any("变量" in str(n) for n in notes), "notes 没说清是变量问题：%r" % (notes,)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_missing_dir_returns_empty():
    """目录不存在 → 空列表、不抛（"还没构建"是正常状态）。"""
    from binfmt import buildsys as B

    missing = os.path.join(ROOT, "__no_such_project__")
    assert not os.path.isdir(missing)
    deps, _notes = B.scan(missing)
    assert deps == [], "缺目录却返回了 %r" % (deps,)
