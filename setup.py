# -*- coding: utf-8 -*-
"""matlabc 的打包入口（P54 / P55 契约）。

四条契约各有**对手方**，都在 `tests/test_matlabc.py` 里；改这里之前先看它们：

  * `test_p54_docs_consistency` ①：本文件的 version 必须**逐字等于** `matlabc.VERSION`；
  * `test_p55_packaging_entrypoints` ②：console_scripts 必须是 `matlabc=matlabc:main`；
  * `test_p55_packaging_entrypoints` ②：必须声明 `py_modules=["matlabc"]`；
  * `test_p55_packaging_entrypoints` ③：`python -m matlabc --version` 必须 rc=0
    且输出含版本号（靠 `matlabc.py` 末尾的 `__main__` 守卫）。

为什么版本号要**再写一份**（而不是从 matlabc.py 现读）：`setup()` 的 version=
必须是一个**字面量** —— P54 的判据是从**源码文本**里用正则取它的，换成函数调用
或变量名就取不到，判据会静默失配。所以这里保留**唯一一份**字面量，并在 `setup()`
之前用 `_assert_version_synced()` **当场核对**：静态判据与运行时自检是同一件事的
两条路，任一条断了都能被发现。

依赖：matlabc 零第三方**运行时**依赖（只用标准库），故 `install_requires` 为空；
`setuptools` 只在打包时用得到。
"""
import io
import os
import re

from setuptools import setup

# ============================================================================
# ⚠ 唯一的一份版本号字面量（P54 的正则取的就是这一行）。
#   改版本时**只改这里**，并确认 matlabc.py 的 VERSION 同步 —— 下面当场拦。
# ============================================================================
version = "1.16.72"


def _assert_version_synced():
    """把本文件的 version 与 matlabc.py 的 VERSION 对账，不一致直接失败。

    为什么值得为一行版本号写一个函数：`version="1.16.40"` 配 `VERSION = "1.16.72"`
    装出来的包，**装得上、跑得动、只是版本报错** —— 这类缺陷只会在用户那儿暴露。
    静态判据（test_p54 ①）在 CI 抓它，这里让**本地** `pip install` 当场抓到。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    src = io.open(os.path.join(here, "matlabc.py"), encoding="utf-8").read()
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.M)
    if m is None:
        raise SystemExit("setup.py: 在 matlabc.py 里找不到模块级 VERSION（正则失配）")
    if m.group(1) != version:
        raise SystemExit(
            "setup.py 的 version=%r 与 matlabc.py 的 VERSION=%r 不一致 —— "
            "两处必须同步（对手方：tests/test_matlabc.py::test_p54_docs_consistency）"
            % (version, m.group(1)))


_assert_version_synced()

_here = os.path.dirname(os.path.abspath(__file__))
try:
    _LONG = io.open(os.path.join(_here, "docs", "matlabc_README.md"),
                    encoding="utf-8").read()
except OSError:
    _LONG = "matlabc —— MATLAB 深度静态分析器 + Doxygen 风格文档前端。"

setup(
    name="matlabc",
    version=version,
    description="MATLAB 深度静态分析器 + Doxygen 风格文档前端（零第三方运行时依赖）",
    long_description=_LONG,
    long_description_content_type="text/markdown",
    license="MIT",
    url="https://github.com/pony-029/malabc",
    author="冯磊 (Feng Lei)",
    py_modules=["matlabc"],
    entry_points={"console_scripts": ["matlabc=matlabc:main"]},
    python_requires=">=3.6.5",
    install_requires=[],
    include_package_data=True,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Documentation",
    ],
)
