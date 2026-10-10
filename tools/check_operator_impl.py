# -*- coding: utf-8 -*-
"""登记制护栏：跨语言算子元表里不得再有「只声明、不产出」的幻影算子。

背景（superpower 30 轮修复 R28 的根因）：
    `matlabc._CROSS_LANG_KIND_META` 曾登记 10 个跨语言 kind，其中 8 个
    （py_undefined_name / py_eval_usage / py_sql_injection / c_buffer_overflow /
     c_double_free / js_dangerous_call / js_unused_var / js_prototype_pollution）
    在全仓**只出现 1 次** —— 就是元表自身。没有任何代码会产出它们。
    「算子目录」因此在向用户宣称 8 项不存在的检测能力；而测试之所以「通过」，
    是因为它们手工伪造 checks_for_sarif 输入，并不证明检测能力存在。

判据（与规模无关的恒等式，不是调出来的阈值）：
    ∀ kind ∈ _CROSS_LANG_KIND_META:
        元表之外必须存在 `"kind": "<kind>"` 的产出点
        ∨ kind ∈ _UNIMPLEMENTED_KINDS（且原因非空）
    等价地：`幻影算子数 == 0`。

C''5（R40）追加的第三条判据 —— **「不做」必须让用户看得见**：
    ∀ kind ∈ _UNIMPLEMENTED_KINDS:
        kind 必须出现在 matlabc.py 的**模块 docstring** 里
    为什么：`_UNIMPLEMENTED_KINDS` 是源码里的字典，用户永远看不到它。
    一个「不做」的算子如果只写在源码里，用户从 `--help` 得到的印象仍是
    「这个工具会查未定义名」—— 那就是用沉默冒充能力。
    而 matlabc.py 的模块 docstring **就是它的 --help 正文**，
    所以这条判据等于「未实现项必须在帮助里说明理由」。

为什么用 `"kind": "<name>"` 而不是「名字出现过」：
    `_on("py_eval_usage")` 这种开关判断里也有名字，若按「出现过」判就会
    把「只加了个开关、没写产出」算成已实现 —— 那正是这道门要拦的东西。
    产出点在本仓库统一写作 `"kind": "<name>"`，用它做判据既精确又稳定。

一图看懂：

    _CROSS_LANG_KIND_META（宣称的能力清单，9 个 kind）
            │
            │  逐个 kind 问两句
            ▼
    ┌────────────────────────────────────────────────────────────┐
    │ ① 元表之外存在 `"kind": "<kind>"` 的产出点吗？               │
    │        有 → ✓ 真实现                                        │
    │        没有 ↓                                               │
    │ ② 它在 _UNIMPLEMENTED_KINDS 里、且写了非空原因吗？            │
    │        是 → ✓ 已显式登记为「未实现」（诚实，不冒充）          │
    │        否 → ✗ 幻影算子 → 红                                 │
    └────────────────────────────────────────────────────────────┘
            │
            ▼  额外不变量
    META ∩ _UNIMPLEMENTED_KINDS == ∅
      （一个 kind 不许既说自己实现了、又登记说没实现 —— 自相矛盾）

  实测现状：9 个 kind 全部有真实产出点；`py_undefined_name` 显式登记未实现。

退出码：0 = 无幻影；1 = 有幻影/无原因；2 = 缺输入（源文件或元表找不到 → 红）。
"""
import io
import os
import re
import sys

# R62/P5：「质量门表」里本门那一行的**签名**（本门自己的判据族，
# 或本门独有的机制名）。它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "_UNIMPLEMENTED_KINDS"

DEFAULT_SRC = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "matlabc.py")

_META_NAME = "_CROSS_LANG_KIND_META"
_UNIMPL_NAME = "_UNIMPLEMENTED_KINDS"
_KIND_SITE = '"kind": "%s"'


def _read(path):
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read().replace("\r\n", "\n")


def _extract_dict(text, name):
    """取出 `name = { ... }` 的整段文本（花括号配对）；找不到返回 None。"""
    m = re.search(r"^%s\s*=\s*\{" % re.escape(name), text, re.M)
    if not m:
        return None
    start = text.index("{", m.start())
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[m.start():i + 1], start, i
    return None


def _keys_of(block, name):
    """从字典块里取出一级键名（缩进 4 空格 + 引号）。"""
    head = block.split("{", 1)[1]
    return re.findall(r'^\s{4}"([A-Za-z_][\w]*)"\s*:', head, re.M)


def _module_docstring(path):
    """取模块 docstring；解析不了返回 None。

    为什么要 ast 而不是正则找第一段三引号：`matlabc.py` 开头有编码声明注释、
    文件里有大量非 docstring 的三引号字符串，正则很容易抓错那一段。
    """
    import ast
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            return ast.get_docstring(ast.parse(fh.read()), clean=False)
    except (SyntaxError, OSError):
        return None


def analyze(src_path):
    """返回 (findings, unimplemented, meta_keys, err)，findings 为问题 kind 字典。

    findings["phantom"]   : 元表登记、元表外无 `"kind": "..."` 产出点的 kind
    findings["conflict"]  : 同时出现在元表与 _UNIMPLEMENTED_KINDS 的 kind ——
                            自相矛盾（既给标签说「我会检测」，又说「我不实现」）。
                            **必须报红**：这正是「先把 kind 塞进元表凑数、
                            再补一句未实现」的敷衍写法，等于幻影算子换个马甲。
    findings["no_reason"] : _UNIMPLEMENTED_KINDS 里原因为空/过短的 kind
    findings["undocumented"] : 未实现项**没有写进模块 docstring**（= --help 正文）
                               —— 源码里有理由、用户看不到，等于没有（C''5/R40）
    err                   : 非 None 表示缺输入（源文件/元表/未实现表）
    """
    empty = {"phantom": [], "conflict": [], "no_reason": [], "undocumented": []}
    if not os.path.isfile(src_path):
        return empty, [], [], "源文件不存在：%s" % src_path
    text = _read(src_path)
    got = _extract_dict(text, _META_NAME)
    if got is None:
        return empty, [], [], "未找到 %s 定义（缺输入 → 红）" % _META_NAME
    block, start, end = got
    outside = text[:start] + text[end + 1:]

    got_u = _extract_dict(text, _UNIMPL_NAME)
    if got_u is None:
        return empty, [], [], "未找到 %s 定义（缺输入 → 红）" % _UNIMPL_NAME
    unimpl_block = got_u[0]
    unimpl = _keys_of(unimpl_block, _UNIMPL_NAME)
    meta_keys = _keys_of(block, _META_NAME)

    findings = {"phantom": [], "conflict": [], "no_reason": [], "undocumented": []}
    for kind in unimpl:
        m = re.search(r'"%s"\s*:\s*(.*?)\)\s*,?\s*(?:"|\})' % re.escape(kind),
                      unimpl_block, re.S)
        body = m.group(1) if m else ""
        # 只认「明确写了足够长的原因」；空字符串/占位符视同没写
        if len(re.findall(r"[\u4e00-\u9fffA-Za-z]", body)) < 8:
            findings["no_reason"].append(kind)

    # C''5（R40）：理由还必须出现在**模块 docstring**（即 --help 正文）里。
    doc = _module_docstring(src_path) or ""
    for kind in unimpl:
        if kind not in doc:
            findings["undocumented"].append(kind)

    for kind in meta_keys:
        if kind in unimpl:
            # 元表与未实现表**交集必须为空**：有标签 = 宣称能检测。
            findings["conflict"].append(kind)
            continue
        if (_KIND_SITE % kind) not in outside:
            findings["phantom"].append(kind)
    return findings, unimpl, meta_keys, None


def report(src_path, quiet=False):
    findings, unimpl, meta_keys, err = analyze(src_path)
    if err:
        print("[FAIL] %s" % err)
        return 2
    if findings["phantom"]:
        print("[FAIL] 幻影算子（元表登记但全仓无产出点）：%s"
              % ", ".join(findings["phantom"]))
    if findings["conflict"]:
        print("[FAIL] 元表 _CROSS_LANG_KIND_META 与 _UNIMPLEMENTED_KINDS 冲突"
              "（同一 kind 既给了检测标签又声明不实现）：%s"
              % ", ".join(findings["conflict"]))
    if findings["no_reason"]:
        print("[FAIL] _UNIMPLEMENTED_KINDS 缺少原因说明：%s"
              % ", ".join(findings["no_reason"]))
    if findings["undocumented"]:
        print("[FAIL] 未实现算子没有写进**帮助正文**（模块 docstring）—— "
              "源码里有理由、用户看不到，等于用沉默冒充能力：%s"
              % ", ".join(findings["undocumented"]))
    if any(findings.values()):
        return 1
    if not quiet:
        print("check_operator_impl: OK（元表 %d 个 kind 全部有产出点；"
              "显式登记未实现 %d 个（登记表 %s）且已写进帮助正文；"
              "两表交集为空）"
              % (len(meta_keys), len(unimpl), ROW_SIGNATURE))
    return 0


# ----------------------------------------------------------------------
# 自证：正反两个合成样本。只抓坏 / 只放好 都不算通过。
# ----------------------------------------------------------------------
_META_TMPL = '''%s = {
%s}

%s = {
%s}
'''

# 合成样本的模块 docstring（= matlabc.py 里「就是 --help 正文」的那个 docstring）。
# 默认把它写成**提到 zz_alpha** 的样子，好让「幻影/冲突/空原因」那几个样本
# 只在被测变量上有差异 —— 夹具引入额外差异是这道门自己踩过的坑（见 _synth 注释）。
_DOC_TMPL = '"""%s"""\n\n'
_DOC_OK = "合成样本。zz_alpha 不实现：需要真正的名字解析，替代方案是 pyflakes。\n"


def _synth(bad_kind=None, good_kind=None, empty_reason=False,
           dup_kind=None, doc=None):
    """合成样本。dup_kind：同时写进元表与未实现表（冲突样本）。

    注意夹具纪律：`zz_alpha` **只**出现在未实现表里。首版夹具把它同时写进
    两张表，于是「好样本」被判成 conflict 而被误伤 —— 那是夹具引入了被测
    变量之外的差异，不是实现的问题。
    同理（R40）：模块 docstring 默认就提 `zz_alpha`，只想测「幻影」的样本
    不该顺带触发「未写进帮助」。
    """
    if doc is None:
        doc = _DOC_OK
    # 冲突样本同时把 dup_kind 登记成未实现，所以帮助里也得提到它 ——
    # 否则该样本会顺带触发一次「未写进帮助」，测到的就不是「冲突」这一件事了。
    if dup_kind and dup_kind not in doc:
        doc = doc + "\n%s 也登记为未实现。\n" % dup_kind
    meta_extra = ('    "%s": {"label": "B", "level": "error", "category": "x"},\n'
                  % bad_kind) if bad_kind else ""
    if good_kind:
        meta_extra += ('    "%s": {"label": "G", "level": "error", '
                       '"category": "x"},\n' % good_kind)
    if dup_kind:
        meta_extra += ('    "%s": {"label": "D", "level": "error", '
                       '"category": "x"},\n' % dup_kind)
    unimpl = '    "zz_alpha": ("需要真实作用域解析，正则近似会大量误报，故不实现。"),\n'
    if dup_kind:
        unimpl += ('    "%s": ("同样登记为不实现，但元表里还留着标签。"),\n'
                   % dup_kind)
    if empty_reason:
        unimpl = '    "zz_alpha": (""),\n'
    body = ''
    if good_kind:
        body = 'out.append({"kind": "%s"})\n' % good_kind
    return (_DOC_TMPL % doc
            + _META_TMPL % (_META_NAME, meta_extra, _UNIMPL_NAME, unimpl)
            + body)


def selftest():
    import tempfile
    bad = good = 0
    tmp = tempfile.mkdtemp(prefix="chk_oper_selftest_")

    def _write(name, text):
        p = os.path.join(tmp, name)
        with io.open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p

    # ① 坏样本：zz_phantom 在元表里但没有产出点、也没登记为未实现 → 必须被抓
    p = _write("bad.py", _synth(bad_kind="zz_phantom"))
    f, _u, _mk, err = analyze(p)
    if err is None and f["phantom"] == ["zz_phantom"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 坏样本未被抓：%r err=%r" % (f, err))

    # ② 好样本：zz_real 有 `"kind": "zz_real"` 产出点 → 必须放行
    p = _write("good.py", _synth(good_kind="zz_real"))
    f, _u, _mk, err = analyze(p)
    if err is None and not any(f.values()):
        good += 1
    else:
        bad += 1
        print("  [selftest] 好样本被误伤：%r err=%r" % (f, err))

    # ③ 坏样本：未实现表里只写空字符串 → 必须抓「没写原因」
    p = _write("empty_reason.py", _synth(empty_reason=True))
    f, _u, _mk, err = analyze(p)
    if err is None and f["no_reason"] == ["zz_alpha"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 空原因未被抓：%r err=%r" % (f, err))

    # ④ 坏样本：同一 kind 既在元表又在未实现表 → 必须抓「冲突」
    #    （这是本护栏**首跑的负向测试**抓出的自身假门：原先 `if kind in unimpl:
    #     continue` 会把这种自相矛盾的写法直接豁免成绿灯。）
    p = _write("dup.py", _synth(dup_kind="zz_dup"))
    f, _u, _mk, err = analyze(p)
    if err is None and f["conflict"] == ["zz_dup"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 元表/未实现表冲突未被抓：%r err=%r" % (f, err))

    # ⑤ 缺输入：源文件不存在 → 必须返回 err（红）
    _f, _u, _mk, err = analyze(os.path.join(tmp, "nope.py"))
    if err:
        good += 1
    else:
        bad += 1
        print("  [selftest] 缺输入未变红")

    # ⑥ 缺输入：源文件里没有元表 → 必须返回 err（红）
    p = _write("nometa.py", "x = 1\n")
    _f, _u, _mk, err = analyze(p)
    if err:
        good += 1
    else:
        bad += 1
        print("  [selftest] 无元表未变红")

    # ⑦ 坏样本（C''5/R40）：未实现项**没写进帮助正文** → 必须抓
    p = _write("undoc.py", _synth(doc="这个帮助里一个字都没提未实现算子。\n"))
    f, _u, _mk, err = analyze(p)
    if err is None and f["undocumented"] == ["zz_alpha"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 未实现项没写进帮助正文未被抓：%r err=%r" % (f, err))

    # ⑧ 好样本（C''5/R40）：帮助里写了 → 不得误伤
    p = _write("docok.py", _synth())
    f, _u, _mk, err = analyze(p)
    if err is None and not f["undocumented"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 写进帮助的好样本被误伤：%r err=%r" % (f, err))

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return bad, good


def main(argv):
    if "--selftest" in argv:
        bad, good = selftest()
        return 0 if (bad == 0 and good >= 8) else 1
    src = DEFAULT_SRC
    if "--src" in argv:
        i = argv.index("--src")
        if i + 1 >= len(argv):
            print("[FAIL] --src 需要一个路径（缺输入 → 红）")
            return 2
        src = argv[i + 1]
    return report(src)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
