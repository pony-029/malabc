# -*- coding: utf-8 -*-
"""构建脚本解析（`binfmt/buildsys.py`）：从 Makefile/CMake 里认依赖。

## 为什么单独一个文件

`test_analysis_layer.py` 已经把「CMake 变量不当库名」钉住了，但那只覆盖一个入口。
这一层还有两个容易错的地方，各自独立：

* **Makefile 的 `-l`**：`-lblas` → `blas`，而 `-l$(EXTRA)` 不该变成库名；
* **家族名**：`libfoo.so.1.2.3` 与 `libfoo.so` 是**同一个库**，比较时要用归一后的名字。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "binfmt"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def test_makefile_l_flags_become_names():
    """`-lblas -lm` → 名字 `blas` / `m`；`$(EXTRA)` 不是库名。"""
    from binfmt import buildsys as B

    deps, _notes = B.parse_makefile("app: -lblas -lm $(EXTRA)\n", "Makefile")
    names = [d.name for d in deps]
    assert names == ["blas", "m"], "Makefile 的 -l 解析结果不对：%r" % (names,)
    assert not any("$" in n for n in names), "变量被当成库名：%r" % (names,)


def test_library_family_normalizes_versions():
    """同一个库的不同形式必须归一成同一个家族名。"""
    from binfmt import buildsys as B

    fam = B.library_family("libfoo.so.1.2.3")
    assert fam == B.library_family("libfoo.so"), \
        "版本后缀没有归一：%r vs %r" % (fam, B.library_family("libfoo.so"))
    assert fam.startswith("libfoo"), "家族名丢了库名：%r" % fam
