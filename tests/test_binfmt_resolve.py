# -*- coding: utf-8 -*-
"""库名判定与候选展开（`binfmt/resolve.py`）。

两条互不重叠的性质：

* **是不是文件名**：`libfoo.so.1` 是、`blas` 不是。这个判定决定了后续走哪一支；
* **候选展开不能自乘**：对已经是文件名的名字再套一遍 `-l` 拼法，会产出
  `libfoo.so.1.so` 这种查不到的噪音（该函数注释里点名的坑）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "binfmt"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def test_looks_like_library_filename_both_ways():
    """双向：真文件名认得出，`-l` 简名不能被当成文件名。"""
    from binfmt import resolve as R

    for name in ("libfoo.so.1", "libbar.dylib", "KERNEL32.dll"):
        assert R.looks_like_library_filename(name), "没认出文件名：%r" % name
    for name in ("blas", "m", "pthread"):
        assert not R.looks_like_library_filename(name), "把简名当成了文件名：%r" % name


def test_filename_candidates_do_not_self_multiply():
    """已经是文件名的名字，候选里不能出现 `X.dll.dll` 这类自乘。"""
    from binfmt import resolve as R

    got = R.candidate_names("KERNEL32.dll")
    assert got, "KERNEL32.dll 一个候选都没有"
    assert not any(c.count(".dll") > 1 for c in got), \
        "候选自乘了：%r" % (got,)
    # 大小写变体是 Windows 的真实需要（文件名不区分大小写，但记录里可能不同）
    assert any(c.lower() == "kernel32.dll" for c in got), \
        "没有小写变体：%r" % (got,)
