# -*- coding: utf-8 -*-
"""R100：源码级动态库引用提取 —— 四语言共用一份记录、各自一套语法。

用户原话：「更一层的代码中涉及的**动态链接库**也务必解析出来」。

本模块回答「**代码想用谁**」，与 `binfmt/` 回答的「**谁里面有什么**」互补：

    * 本模块    —— 从**源码字面量**提取库引用（不需要库文件存在）；
    * `binfmt/`  —— 解析 ELF / PE / Mach-O 容器（需要文件存在），走
      `--binary` / `--binary-attach` / `--lib-resolve`。

两者缺一不可：只有前者，会把「引用了不存在的库」当成正常；只有后者，会漏掉
「代码里写了、但没把文件递过来」的那一批 —— 而这恰恰是**静态分析能回答、
运行时工具回答不了**的问题。

⚠ 与帮助里那句「不跟踪运行期绑定（`dlopen` / `LoadLibrary` / `dlsym`）」
**不冲突，但边界必须说清**：

    * **字面量**实参（`dlopen("libx.so", …)`）⇒ 静态可见，**提取**；
    * **变量**实参（`dlopen(buf, …)`）⇒ 库名运行期才定，**记下调用点、
      库名写 None**；
    * `dlsym` 拿到函数指针再调用 ⇒ 调用目标运行期才定，**不提取**。

「有调用点但库名未知」与「根本没有这一行」在站点上是**两件事**（R86 的
证据契约：没证据 ≠ 证据为空）。所以本模块不违反那句声明 —— 它不跟踪运行期
绑定，只提取字面量。

四语言**共有**同一条记录形状、同一批 `kind` 语义、同一张站点页；
**各自**一套 API 表与实参写法 —— 「共有都适配、特有各自体现」在这里的落点。
"""

import re

__all__ = [u"extract_dynlib_refs", u"summarize", u"SUPPORTED_LANGS", u"scan"]

SUPPORTED_LANGS = (u"c", u"py", u"js", u"matlab")

# 记录形状（四语言一致，站点页只认这一种）：
#   {"file": 相对路径, "line": 行号(1 基), "api": 归一后的 API 名,
#    "lib":  库名字面量 或 None（运行期才知道）,
#    "kind": load / use / unload / probe / type,
#    "lib_is_arg": 该 API 的**首实参**是否表示库名。False ⇒ 本来就
#                  不带库名（句柄 / FFI 类型），与「运行期才知道」是
#                  两回事，**不可混为一谈**（R98b ⑰）
#    "text": 该行截断原文（供人工核对，**不参与任何判定**）}
#
# kind 语义（跨语言**同一套** —— 这是「共有」的核心）：
#   load   把库加载进来
#   use    调用一个**已加载**的库（MATLAB 的 calllib 是唯一常见形态，
#          它也是四语言里唯一把「加载」与「使用」分成两步的语义）
#   unload 卸载
#   probe  只问「这个库在不在」，不加载（find_library / libisloaded）
#   type   FFI 类型构造（libpointer / libstruct），本身不带库名

_MAX_TEXT = 120


def _rx(pat):
    return re.compile(pat, re.UNICODE)


# ---- 各语言的 API 表（「特有」的落点）--------------------------------------
# 每项：(正则, 归一 API 名, kind, take_arg)。
#   * 正则只负责**定位调用点**；实参解析统一走 `_literal_after`，四语言共用
#     一份实参词法。需要**第二**个实参的（`process.dlopen(module, path)`）
#     让正则自己吃到第二个实参的开头，避免再加一个 arg_index 字段。
#   * take_arg=False 表示**第一个实参不是库名**：`FreeLibrary`/`dlclose` 收的
#     是句柄；`libpointer('doublePtr')` 收的是**类型名**（把类型名当库名记下来
#     就是记错）。这类调用照样入表，只是 `lib` 为 None。
_APIS = {
    u"c": (
        (_rx(r"\bdlopen\s*\("), u"dlopen", u"load", True),
        (_rx(r"\bLoadLibrary(?:A|W|ExA|ExW)?\s*\("), u"LoadLibrary", u"load", True),
        (_rx(r"\bFreeLibrary\s*\("), u"FreeLibrary", u"unload", False),
        (_rx(r"\bdlclose\s*\("), u"dlclose", u"unload", False),
    ),
    u"py": (
        (_rx(r"\b(?:CDLL|WinDLL|OleDLL|PyDLL)\s*\("), u"ctypes.CDLL", u"load", True),
        (_rx(r"\bLoadLibrary\s*\("), u"ctypes.LoadLibrary", u"load", True),
        (_rx(r"\bfind_library\s*\("), u"find_library", u"probe", True),
        (_rx(r"\bload_library\s*\("), u"ctypeslib.load_library", u"load", True),
        (_rx(r"\bdlopen\s*\("), u"ffi.dlopen", u"load", True),
    ),
    u"js": (
        (_rx(r"process\s*\.\s*dlopen\s*\([^,()]*,\s*"),
         u"process.dlopen", u"load", True),
        (_rx(r"\b(?:ffi|node_ffi|nodeFfi)\s*\.\s*Library\s*\("),
         u"ffi.Library", u"load", True),
        (_rx(r"\bkoffi\s*\.\s*load\s*\("), u"koffi.load", u"load", True),
    ),
    u"matlab": (
        (_rx(r"\bloadlibrary\s*\("), u"loadlibrary", u"load", True),
        (_rx(r"\bcalllib\s*\("), u"calllib", u"use", True),
        (_rx(r"\bunloadlibrary\s*\("), u"unloadlibrary", u"unload", True),
        (_rx(r"\blibisloaded\s*\("), u"libisloaded", u"probe", True),
        (_rx(r"\b(?:libpointer|libstruct)\s*\("), u"libpointer", u"type", False),
    ),
}

# ---- 廉价预筛（**不剥注释**，只为省掉绝大多数文件的精细词法）-----------------
_NEEDLE = {
    u"c": _rx(r"dlopen|LoadLibrary|FreeLibrary|dlclose"),
    u"py": _rx(r"CDLL|WinDLL|OleDLL|PyDLL|LoadLibrary|find_library|load_library|dlopen"),
    u"js": _rx(r"dlopen|ffi|koffi|Library"),
    u"matlab": _rx(r"loadlibrary|calllib|libpointer|libstruct|libisloaded"),
}


# ---------------------------------------------------------------------------
# 词法扫描：剥注释 + 记录字符串区间
# ---------------------------------------------------------------------------
def _blank(out, i, j):
    """把 out[i:j] 里的非换行字符换成空格（换行保留 ⇒ 行号可直接沿用）。"""
    for k in range(i, j):
        if out[k] != u"\n":
            out[k] = u" "


def _scan_c_like(text, py=False):
    """C / JS / Python：剥注释，**保留**字符串内容并记下其区间。

    为什么必须记区间：字符串**内容**要留着（实参的库名就在里面），可
    `printf("use dlopen()")` 这种字符串**文本**里出现的 API 名不能算调用。
    调用点过滤见 `_in_spans` —— 真命中的 API 名在 `(` **之前**，不在任何
    字符串区间内，所以这条过滤不会误杀。

    Python 的三引号串被**当注释剥离**，是刻意的取舍：docstring 里常写
    `cdll.LoadLibrary("…")` 作为**示例**，那不是调用。误报的代价（用户去追
    一个不存在的库）高于漏报（把「代码存进字符串」当成无调用）。
    """
    out = list(text)
    spans = []
    n = len(text)
    i = 0
    while i < n:
        c = text[i]
        if c in u"\"'":
            if py and text.startswith(c * 3, i):
                end = text.find(c * 3, i + 3)
                end = n - 3 if end < 0 else end
                _blank(out, i + 3, end)
                i = end + 3
                continue
            q = c
            start = i
            i += 1
            while i < n:
                ch = text[i]
                if ch == u"\\":
                    i += 2
                    continue
                if ch == q:
                    i += 1
                    break
                if ch == u"\n":
                    break
                i += 1
            spans.append((start, i))
            continue
        if c == u"#":
            j = text.find(u"\n", i)
            j = n if j < 0 else j
            _blank(out, i, j)
            i = j
            continue
        if c == u"/" and i + 1 < n and text[i + 1] == u"/":
            j = text.find(u"\n", i)
            j = n if j < 0 else j
            _blank(out, i, j)
            i = j
            continue
        if c == u"/" and i + 1 < n and text[i + 1] == u"*":
            end = text.find(u"*/", i + 2)
            end = n if end < 0 else end + 2
            _blank(out, i, end)
            i = end
            continue
        i += 1
    return (u"".join(out), spans)


def _scan_matlab(text):
    """MATLAB：`%` 行注释、`%{ %}` 块注释、「单引号转置」消歧 + 字符串区间。

    MATLAB 的 `'` 既是字符串定界符又是**转置运算符**。用标准启发式消歧：
    `'` 紧跟在标识符字符 / `)` / `]` / `}` / `.` 之后 ⇒ 判为转置，**不开始
    字符串**。宁可漏报（把真字符串当代码）也不误报 —— 误报会把 `A'` 之后的
    一大段代码吃成一个「字符串」，从而吞掉真正的库引用。
    """
    out = list(text)
    spans = []
    n = len(text)
    i = 0
    while i < n:
        c = text[i]
        if c == u"%":
            if text.startswith(u"%{", i):
                end = text.find(u"%}", i + 2)
                end = n if end < 0 else end + 2
                _blank(out, i, end)
                i = end
                continue
            j = text.find(u"\n", i)
            j = n if j < 0 else j
            _blank(out, i, j)
            i = j
            continue
        if c == u"\"":
            start = i
            i += 1
            while i < n:
                ch = text[i]
                if ch == u"\\":
                    i += 2
                    continue
                if ch == u"\"":
                    i += 1
                    break
                if ch == u"\n":
                    break
                i += 1
            spans.append((start, i))
            continue
        if c == u"'":
            prev = text[i - 1] if i > 0 else u" "
            if prev.isalnum() or prev in u"_)]}.'":
                i += 1                      # 转置运算符，不是字符串
                continue
            start = i
            i += 1
            while i < n:
                ch = text[i]
                if ch == u"'" and i + 1 < n and text[i + 1] == u"'":
                    i += 2                  # MATLAB 的 '' 转义
                    continue
                if ch == u"'":
                    i += 1
                    break
                if ch == u"\n":
                    break
                i += 1
            spans.append((start, i))
            continue
        i += 1
    return (u"".join(out), spans)


def scan(text, lang):
    """按语言剥注释，返回 `(clean, spans)`；`clean` 与 `text` **等长**。

    `spans` 是字符串字面量的 `(start, end)` 区间（**有序**，供二分）。
    """
    if lang in (u"c", u"js"):
        return _scan_c_like(text, py=False)
    if lang == u"py":
        return _scan_c_like(text, py=True)
    if lang == u"matlab":
        return _scan_matlab(text)
    return (text, [])


def _in_spans(spans, i):
    """i 是否落在某个字符串区间内。`spans` 有序 ⇒ 二分。"""
    if not spans:
        return False
    lo, hi = 0, len(spans)
    while lo < hi:
        mid = (lo + hi) // 2
        if spans[mid][0] <= i:
            lo = mid + 1
        else:
            hi = mid
    return lo > 0 and spans[lo - 1][1] > i


# ---------------------------------------------------------------------------
# 实参解析
# ---------------------------------------------------------------------------
def _literal_after(text, i, doubled_quote=False):
    """从 `text[i:]` 跳过空白后，若开头是字符串字面量则返回 (值, 结束下标)。

    不是字面量 ⇒ 返回 `(None, i)` —— 调用方据此把 `lib` 记为 None（运行期
    才知道），**不猜**。
    """
    n = len(text)
    while i < n and text[i] in u" \t\r\n":
        i += 1
    if i >= n or text[i] not in u"\"'":
        return (None, i)
    q = text[i]
    i += 1
    buf = []
    while i < n:
        ch = text[i]
        if ch == u"\\" and i + 1 < n:
            buf.append(text[i + 1])
            i += 2
            continue
        if ch == q:
            if doubled_quote and i + 1 < n and text[i + 1] == q:
                buf.append(q)
                i += 2
                continue
            return (u"".join(buf), i + 1)
        if ch == u"\n":
            return (None, i)
        buf.append(ch)
        i += 1
    return (None, i)


def _line_no(text, i):
    return text.count(u"\n", 0, i) + 1


def _line_text(text, i):
    a = text.rfind(u"\n", 0, i)
    b = text.find(u"\n", i)
    a = 0 if a < 0 else a + 1
    b = len(text) if b < 0 else b
    return text[a:b].strip()[:_MAX_TEXT]


# ---------------------------------------------------------------------------
# 对外：提取
# ---------------------------------------------------------------------------
def extract_dynlib_refs(rel, text, lang):
    """提取 `rel` 这个文件里的动态库引用，返回记录列表（**源码序**）。

    `lang` 不在 `SUPPORTED_LANGS` 里（例如 `asm`）⇒ 返回空表，**不是**报错：
    站点上有「该语言没有这条能力」与「这个文件恰好没有引用」两种情形，站点页
    用「语言是否受支持」把二者分开（见 `csite.py` 的 dynlibs 页）。
    """
    if lang not in SUPPORTED_LANGS:
        return []
    if not _NEEDLE[lang].search(text):
        return []
    clean, spans = scan(text, lang)
    doubled = (lang == u"matlab")
    out = []
    seen = set()
    for (rx, api, kind, take_arg) in _APIS[lang]:
        for m in rx.finditer(clean):
            if _in_spans(spans, m.start()):
                continue            # 命中落在字符串**文本**里，不是调用点
            lib = None
            if take_arg:
                lib, _end = _literal_after(clean, m.end(), doubled_quote=doubled)
            ln = _line_no(text, m.start())
            key = (ln, api, lib)
            if key in seen:
                continue
            seen.add(key)
            out.append({"file": rel, "line": ln, "api": api,
                        "lib": lib, "kind": kind,
                        "lib_is_arg": take_arg,
                        "text": _line_text(text, m.start())})
    out.sort(key=lambda r: (r["line"], r["api"], r["lib"] or u""))
    return out


# ---------------------------------------------------------------------------
# 聚合（站点页的数据源）
# ---------------------------------------------------------------------------
def summarize(refs):
    """把记录列表聚合成站点页要的三张表。返回 dict（全部可 JSON 化）。"""
    by_lib = {}
    by_api = {}
    by_kind = {}
    files = set()
    unknown = []          # lib 为空 **且** 首实参本该带库名 ⇒ 运行期才知道
    no_arg = []           # 该 API **本来就不带库名**（句柄 / FFI 类型）
    for r in refs:
        f = r.get("file")
        if f:
            files.add(f)
        by_api[r.get("api")] = by_api.get(r.get("api"), 0) + 1
        by_kind[r.get("kind")] = by_kind.get(r.get("kind"), 0) + 1
        lib = r.get("lib")
        if not lib:
            (unknown if r.get("lib_is_arg", True) else no_arg).append(r)
            continue
        rec = by_lib.get(lib)
        if rec is None:
            rec = {"lib": lib, "count": 0, "apis": set(),
                   "kinds": set(), "files": set()}
            by_lib[lib] = rec
        rec["count"] += 1
        rec["apis"].add(r.get("api"))
        rec["kinds"].add(r.get("kind"))
        if f:
            rec["files"].add(f)
    libs = sorted(by_lib.values(), key=lambda x: (-x["count"], x["lib"].lower()))
    for x in libs:
        x["n_files"] = len(x["files"])
        x["apis"] = sorted(a for a in x["apis"] if a)
        x["kinds"] = sorted(k for k in x["kinds"] if k)
        x["files"] = sorted(x["files"])
    def _sk(r):
        return (r.get("line") or 0, r.get("api") or u"")
    unknown = sorted(unknown, key=_sk)
    no_arg = sorted(no_arg, key=_sk)
    return {"total": len(refs), "n_files": len(files), "n_libs": len(libs),
            "libs": libs,
            "unknown": unknown, "n_unknown": len(unknown),
            "no_lib_arg": no_arg, "n_no_lib_arg": len(no_arg),
            "by_api": by_api, "by_kind": by_kind}
