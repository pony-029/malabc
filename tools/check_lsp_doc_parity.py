#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""LSP 文档 ⇄ 代码 双向一致。

    python tools/check_lsp_doc_parity.py            # 校验
    python tools/check_lsp_doc_parity.py --selftest # 判据自证

**为什么需要这道门**：`check_readme_parity` 只保证 README 的中英两侧
**彼此对等**——两边一起错，它照样绿。R180/R181 实测两份文档同时过时：

    README.md        说「诊断 == heuristics」，而 R161 之后是**超集**
    README.md        没提 `didSave`（R153 就实现了）
    vscode/README.md 说「诊断只有一类 m_missing_doc」，而 R161 之后是四类

**根因**：文档里的「能力表」没有任何东西去核对代码。

本门核对两件事：

1. **代码里实现的 `textDocument/*` 方法** ⊆ **vscode/README.md 能力表里列出的**
2. 能力表里列出的每个方法，**代码里必须真的有**

第 1 条防「实现了但没写」，第 2 条防「写了但没实现」。

判据族 **LSP1–LSP4**。

退出码：
    0  = 双向一致（LSP1–LSP4 全绿）
    1  = 有方向不一致（实现了没写 / 写了没实现），或 --selftest 失败
    2  = 缺输入（matlabc_lsp.py 或 vscode/README.md 不在）
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LSP = os.path.join(ROOT, "matlabc_lsp.py")
VREADME = os.path.join(ROOT, "vscode", "README.md")
EXTJS = os.path.join(ROOT, "vscode", "extension.js")

#: P5 的对手方：本门在 README 质量门表那一行里声明的判据族。
ROW_SIGNATURE = "LSP1–LSP5"

#: 不是「能力」的协议方法：生命周期与同步通知。
NOT_CAPABILITY = {
    "textDocument/didOpen", "textDocument/didClose", "textDocument/didSave",
    "textDocument/didChange", "initialize", "shutdown", "exit",
}


def _chk(cond, name, detail=""):
    if not cond:
        print("  [FAIL] %-34s %s" % (name, detail))
    return bool(cond)


def code_methods(path=LSP):
    """`matlabc_lsp.py` 里 `if method == "textDocument/xxx":` 出现的方法。"""
    with io.open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    found = set(re.findall(r'method\s*==\s*"(textDocument/[A-Za-z]+)"', text))
    return found - NOT_CAPABILITY


def doc_methods(path=VREADME):
    """`vscode/README.md` 能力表里反引号括起来的 `textDocument/*`。"""
    if not os.path.isfile(path):
        return None
    with io.open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return set(re.findall(r"`(textDocument/[A-Za-z]+)`", text)) - NOT_CAPABILITY


def legend_pair(path_py=LSP, path_js=EXTJS):
    """`(py_types, py_mods, js_types, js_mods)`；任一解析失败返回 `None`。

    `matlabc_lsp.py` 的 `_SEMANTIC_TYPES` 与 `extension.js` 的
    `SemanticTokensLegend([...], [...])` 必须**逐项同序**。
    """
    try:
        py = io.open(path_py, "r", encoding="utf-8").read()
        js = io.open(path_js, "r", encoding="utf-8").read()
    except (IOError, OSError):
        return None
    t = re.search(r"_SEMANTIC_TYPES = \[(.+?)\]", py)
    mo = re.search(r"_SEMANTIC_MODS = \[(.+?)\]", py)
    m = re.search(r"SemanticTokensLegend\(\s*\[([^\]]+)\]\s*,\s*\[([^\]]+)\]",
                  js, re.S)
    if not (t and mo and m):
        return None
    py_types = re.findall(r'"(\w+)"', t.group(1))
    py_mods = re.findall(r'"(\w+)"', mo.group(1))
    js_types = [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
    js_mods = [x.strip().strip("'\"") for x in m.group(2).split(",") if x.strip()]
    if not (py_types and py_mods and js_types and js_mods):
        return None
    return py_types, py_mods, js_types, js_mods


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv or sys.argv[1:])

    if args.help:
        sys.stdout.write(__doc__)
        return 0

    if args.selftest:
        good = bad = 0
        if _chk("textDocument/hover" in code_methods(), "自证：代码里能提到 hover"):
            good += 1
        else:
            bad += 1
        if _chk("textDocument/didOpen" not in code_methods(),
                "自证：didOpen 不算能力"):
            good += 1
        else:
            bad += 1
        dm = doc_methods()
        if _chk(dm is not None, "自证：vscode/README.md 存在"):
            good += 1
        else:
            bad += 1
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if bad == 0 else 1

    if not os.path.isfile(LSP):
        print("check_lsp_doc_parity: 缺输入（%s）" % LSP)
        return 2
    code = code_methods()
    doc = doc_methods()
    if doc is None:
        print("check_lsp_doc_parity: 缺输入（%s）" % VREADME)
        return 2

    bad = 0
    # D1：代码实现了但文档没写
    missing_in_doc = code - doc
    if not _chk(not missing_in_doc, "LSP1 代码有、文档无",
                "未写进 vscode/README.md：%r" % (sorted(missing_in_doc),)):
        bad += 1
    # D2：文档写了但代码没有
    missing_in_code = doc - code
    if not _chk(not missing_in_code, "LSP2 文档有、代码无",
                "文档列了但没实现：%r" % (sorted(missing_in_code),)):
        bad += 1
    # D3：空集必红（两边都是空说明解析坏了）
    if not _chk(bool(code) and bool(doc), "LSP3 非空",
                "方法集合为空：code=%d doc=%d" % (len(code), len(doc))):
        bad += 1

    # D5（R275）：更新日志必须存在，且**含当前版本**那一节。
    # 版本号是唯一一个每轮都变的数字，而「忘了写更新日志」是最常见的
    # 文档腐烂方式：它不报错、不崩，只是让页面上的「更新日志」页
    # 永远停在上一个版本 —— 用户看到的最新一条就是旧的。
    _vsdir = os.path.dirname(VREADME)
    try:
        _pkg = json.load(io.open(os.path.join(_vsdir, "package.json"),
                                 encoding="utf-8"))
        _ver = str(_pkg.get("version") or "").strip()
    except (IOError, OSError, ValueError):
        _ver = ""
    _chal = os.path.join(_vsdir, "CHANGELOG.md")
    if not _chk(os.path.isfile(_chal), "LSP5 更新日志存在",
                "缺 %s" % _chal):
        bad += 1
    elif not _chk(("## %s" % _ver) in io.open(_chal, encoding="utf-8").read(),
                  "LSP5a 更新日志含当前版本",
                  "CHANGELOG 里没有 `## %s`（package.json 的 version 是 %r）"
                  % (_ver, _ver)):
        bad += 1

    # D4：语义高亮的 legend 必须在两侧**同序**。
    # 协议里 tokenType 就是一个下标，顺序错一位颜色整体错乱，
    # **而且不会报任何错** —— 这种「静默错位」正是判据该守的地方。
    lg = legend_pair()
    if not _chk(lg is not None, "LSP4 语义 legend 可解析",
                "找不到 _SEMANTIC_TYPES / _SEMANTIC_MODS 或 SemanticTokensLegend"):
        bad += 1
    else:
        py_types, py_mods, js_types, js_mods = lg
        if not _chk(py_types == js_types, "LSP4a tokenTypes 同序",
                    "py=%r js=%r" % (py_types, js_types)):
            bad += 1
        if not _chk(py_mods == js_mods, "LSP4b tokenModifiers 同序",
                    "py=%r js=%r" % (py_mods, js_mods)):
            bad += 1

    if bad == 0:
        print("check_lsp_doc_parity: OK（代码 %d 个能力方法 ⇄ 文档 %d 个，双向一致）"
              % (len(code), len(doc)))
        return 0
    print("check_lsp_doc_parity: %d 项不一致" % bad)
    return 1


if __name__ == "__main__":
    sys.exit(main())
