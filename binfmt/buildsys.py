"""构建系统感知：从 Makefile / CMakeLists.txt 提取「链接了哪些库」。

没有这一层时，「这个工程链接了 blas」这条信息**只存在于构建脚本里**，
静态分析器看不到，于是 blas 的函数全部落进「未解析」桶。有了它，
「未解析」可以进一步绑定到确定的库名：

    Makefile:   -lblas              ─┐
    CMake:      target_link_libraries(foo PRIVATE cublas) ─┤
                                                            ▼
                                       libblas.so / blas.dll / cublas
                                                            │
                                                            ▼
                    归因时先查「构建系统声明的库名」→ library:<name>

支持两种语法（只做字面量）：
    GNU Make   -lfoo、-l foo、-L/path
    CMake      target_link_libraries(...)、find_library(...)、LINK_LIBRARIES 等

诚实边界（三条，全部会写进 notes）：
  * 只做**字面量**提取。变量展开（$(LDLIBS)、${VAR}）不解析 —— 记为 note。
  * **不做**构建系统求值、**不执行**任何命令。它是文本抽取器，不是构建器。
  * 提取不到就是提取不到，返回空列表而不是猜。
"""
import io
import os
import re

from .model import DEP_LINK_FLAG, Dependency

# -lfoo / -l foo
RE_MAKE_L = re.compile(r"(?:^|\s)-l\s*([A-Za-z0-9_][A-Za-z0-9_+\-.]*)")
# -L/path（库搜索路径，单独记）
RE_MAKE_LDIR = re.compile(r"(?:^|\s)-L\s*([^\s\"']+)")
# 未展开的变量，提示我们「看到但读不懂」
RE_VAR = re.compile(r"\$[\(\{][A-Za-z0-9_]+[\)\}]")

RE_CMAKE_LINK = re.compile(
    r"target_link_libraries\s*\(\s*([A-Za-z0-9_:.\-]+)\s+"
    r"(?:PRIVATE|PUBLIC|INTERFACE)?\s*([^\)]*)\)", re.I)
RE_CMAKE_FIND = re.compile(r"find_package\s*\(\s*([A-Za-z0-9_\-]+)", re.I)
RE_CMAKE_ADDLIB = re.compile(r"add_library\s*\(\s*([A-Za-z0-9_:.\-]+)", re.I)

MAX_FILES = 64
MAX_BYTES = 1 << 20

MAKEFILE_NAMES = ("Makefile", "makefile", "GNUmakefile")
CMAKE_NAMES = ("CMakeLists.txt",)

# CMake 的 PRIVATE/PUBLIC/INTERFACE 关键字与常见非库 token
_CMAKE_SKIP = {"PRIVATE", "PUBLIC", "INTERFACE", "debug", "optimized",
               "general", "LINK_PRIVATE", "LINK_PUBLIC", "LINK_INTERFACE_LIBRARIES"}


def _looks_like_var(s):
    return "$" in s or "{" in s or "(" in s


def parse_makefile(text, origin):
    """返回 (deps, notes)。"""
    deps = []
    notes = []
    seen = set()
    unresolved_vars = 0
    for m in RE_MAKE_L.finditer(text):
        lib = m.group(1)
        if _looks_like_var(lib):
            unresolved_vars += 1
            continue
        if lib in seen:
            continue
        seen.add(lib)
        deps.append(Dependency(name=lib, kind=DEP_LINK_FLAG, origin=origin,
                               detail="-l%s" % lib))
    for m in RE_MAKE_LDIR.finditer(text):
        p = m.group(1)
        if _looks_like_var(p):
            unresolved_vars += 1
            continue
        key = "-L:" + p
        if key in seen:
            continue
        seen.add(key)
        deps.append(Dependency(name=p, kind=DEP_LINK_FLAG, origin=origin,
                               detail="-L 搜索路径"))
    if unresolved_vars:
        notes.append("buildsys: %s 有 %d 处 -l/-L 含未展开的 make 变量"
                     "（如 $() ），未解析" % (os.path.basename(origin), unresolved_vars))
    if RE_VAR.search(text) and not deps:
        notes.append("buildsys: %s 里出现变量引用但未找到任何字面量 -l，"
                     "可能库名全在变量中" % os.path.basename(origin))
    return deps, notes


def parse_cmake(text, origin):
    deps = []
    notes = []
    seen = set()
    unresolved = 0
    for m in RE_CMAKE_LINK.finditer(text):
        target = m.group(1)
        args = m.group(2).split()
        for a in args:
            a = a.strip()
            if not a or a in _CMAKE_SKIP:
                continue
            if _looks_like_var(a):
                unresolved += 1
                continue
            # 已定义的目标名（add_library 出来的）不是外部库，标记出来但不丢
            if a in seen:
                continue
            seen.add(a)
            deps.append(Dependency(name=a, kind=DEP_LINK_FLAG, origin=origin,
                                   detail="target_link_libraries(%s)" % target))
    for m in RE_CMAKE_FIND.finditer(text):
        pkg = m.group(1)
        key = "find:" + pkg.lower()
        if key in seen:
            continue
        seen.add(key)
        deps.append(Dependency(name=pkg, kind=DEP_LINK_FLAG, origin=origin,
                               detail="find_package"))
    if unresolved:
        notes.append("buildsys: %s 有 %d 处 target_link_libraries 参数含未展开变量，"
                     "未解析" % (os.path.basename(origin), unresolved))
    return deps, notes


def scan(root, recursive=True, exclude=None):
    """扫描目录下的构建脚本，返回 (deps, notes)。

    与项目其它收集器一致：不递归时只扫 root 本层。
    """
    deps = []
    notes = []
    if not os.path.isdir(root):
        return deps, notes
    root_norm = os.path.normcase(os.path.normpath(str(root)))
    files = []
    if recursive:
        for dp, dn, fn in os.walk(root):
            if exclude and any(os.path.normcase(os.path.normpath(dp)) ==
                               os.path.normcase(os.path.normpath(str(e)))
                               for e in exclude):
                continue
            for f in fn:
                if f in MAKEFILE_NAMES or f in CMAKE_NAMES or \
                        f.lower().endswith((".mk", ".cmake")):
                    files.append(os.path.join(dp, f))
    else:
        for f in os.listdir(root):
            p = os.path.join(root, f)
            if os.path.isfile(p) and (f in MAKEFILE_NAMES or f in CMAKE_NAMES):
                files.append(p)
    del root_norm
    if len(files) > MAX_FILES:
        notes.append("buildsys: 构建脚本数 %d 超上限 %d，只扫前 %d 个"
                     % (len(files), MAX_FILES, MAX_FILES))
        files = files[:MAX_FILES]
    for p in files:
        try:
            with io.open(p, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read(MAX_BYTES)
        except OSError as e:
            notes.append("buildsys: 读取 %s 失败：%s" % (p, e))
            continue
        base = os.path.basename(p)
        if base in CMAKE_NAMES or p.endswith(".cmake"):
            d, n = parse_cmake(text, p)
        else:
            d, n = parse_makefile(text, p)
        deps.extend(d)
        notes.extend(n)
    return deps, notes


def lib_flag_to_candidates(lib):
    """把一个 -l 名映射到可能的二进制文件名（供与 --binary 结果对账）。

    这是纯命名约定，不是「找到文件」 —— 不猜路径。
    """
    l = lib.lower()
    out = []
    if l.startswith("lib"):
        out.append(l + ".so")
        out.append(l + ".dll")
        out.append(l + ".dylib")
        out.append(l + ".lib")
    else:
        out.append("lib" + l + ".so")
        out.append(l + ".dll")
        out.append("lib" + l + ".dylib")
        out.append(l + ".lib")
    return out


# ---- R68：库名归一（「同一个库的各种形式」的唯一事实源） ----
RE_SO_FAMILY = re.compile(r"^(?P<base>.+?\.so)(?:\.\d+(?:\.\d+)*)?$")
RE_DYLIB_FAMILY = re.compile(r"^(?P<base>.+?)(?:\.\d+)*\.dylib$")


def library_family(name):
    """把一个动态库名归一成**家族名**：判断两种写法是不是同一个库。

    同一个库在磁盘上有许多「形式」，这正是 R68 要解决的那件事：

        libfoo.so                     -> libfoo.so
        libfoo.so.6                   -> libfoo.so
        libfoo.so.1.2.3               -> libfoo.so
        libfoo.1.dylib                -> libfoo.dylib
        libfoo.1.2.3.dylib            -> libfoo.dylib
        Foo.framework/Foo             -> foo.framework
        Foo.framework/Versions/A/Foo  -> foo.framework
        libfoo.dll                    -> libfoo.dll
        /usr/lib/libz.so.1            -> libz.so
        @rpath/libbar.dylib           -> libbar.dylib
        @loader_path/../lib/lx.dylib  -> lx.dylib

    三条纪律：
      * **只做文件名归一，不猜路径** —— 不尝试在磁盘上找这个库。
      * 认不出的形态**原样返回小写文件名**（不硬套模板，不把 `libfoo` 猜成
        `libfoo.so` —— 猜错会把两个不同的库合并成一个）。
      * 不做「`libfoo-1.2.dll` → `libfoo.dll`」这类更激进的猜测（见 §8 的
        C18-3：那需要一份真实的 Windows 命名样本才敢做）。
    """
    if not name:
        return ""
    low = name.strip().replace("\\", "/").lower()
    # ⚠ 顺序**必须**是「先判 .framework/、再取 basename」。
    #   R68 的探针（`_r68/probe_r68_framework.py`）量出：反过来写时，
    #   `@rpath/Foo.framework/Versions/A/Foo` 的 basename 是 `foo`，
    #   到判断那一刻 `.framework/` 已不在串里 ⇒ 这一支**不可达**（死代码），
    #   而它的文档字符串明写这一支是活的 ⇒ 行为与文档分叉。
    #   前缀再取一次 basename：`/System/…/Frameworks/Bar.framework/Bar`
    #   要的是 `bar.framework`，不是 `frameworks.bar.framework`。
    if ".framework/" in low:
        return low.split(".framework/", 1)[0].rsplit("/", 1)[-1] + ".framework"
    low = low.rsplit("/", 1)[-1]          # @rpath/... 与普通目录一并去掉
    m = RE_SO_FAMILY.match(low)
    if m:
        return m.group("base")
    m = RE_DYLIB_FAMILY.match(low)
    if m:
        return m.group("base") + ".dylib"
    return low
