# -*- coding: utf-8 -*-
"""可移植性（门）：运行时代码不得把 Windows 当成唯一平台。

为什么需要它
============

本项目要在 Windows 与 Linux 上同时部署。而"跨平台"最常见的坏法不是崩溃，
是**在另一个平台上安静地不工作**：

    * `open("C:\\data\\x")` —— Linux 上只是"文件不存在"，功能静默消失
    * `shutil.which("rea")` 找不到就 return，**没有第二套兜底路径**
    * `os.startfile(...)` —— Linux 上 AttributeError

这些**都不会在 Windows 上暴露**，测试全绿。

判据
====

    PF1 运行时文件里不得出现 **Windows 绝对路径**，除非该行的某一段被
       登记在 `WIN_PATHS`（键是「文件 + 该行里的一段原文」，不是行号 ——
       行号会随改动漂移，漂了之后登记就悄悄失效）。
    PF2 运行时文件里不得使用 **Windows 专属 API**（`os.startfile` /
       `winreg` / `msvcrt` / `ctypes.windll`）—— 不设豁免。
    PF3 两向：登记的那段原文若在文件里找不到了 → 陈旧登记，也红。

用法：
    python tools/check_portability.py
    python tools/check_portability.py --selftest

退出码：
    0  = 通过（PF1–PF3 全绿）
    1  = 有平台假设未被登记 / 登记陈旧 / --selftest 失败
    2  = 缺输入
"""
import argparse
import io
import os
import re
import sys

ROW_SIGNATURE = "PF1–PF3"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 只看**运行时会跑**的文件；tools/ 下的脚本本身允许有平台分支。
RUNTIME = ("matlabc.py", "matlabc_lsp.py", "matlabc_mcp.py",
           "matlabc_flow.py", "matlabc_ask.py")

#: 允许出现的 Windows 路径：键 = (文件, 该行里的一段原文)。
#: 挑「这段原文」而不是行号：行号一改就失配，失配后登记会**静默失效**。
WIN_PATHS = {
    ("matlabc_lsp.py", "Program Files"):
        u"Node 兜底路径之一，同一份列表里还列了 /usr/bin/node、"
        u"/usr/local/bin/node —— 两边成对；只写 Windows 一边才会红",
    ("matlabc_lsp.py", "AppData"):
        u"npm 全局安装目录（rea / node 的默认位置），同处也列了 "
        u"~/.npm-global/bin、~/.local/bin、/usr/local/bin —— 两边成对",
}

WIN_APIS = ("os.startfile", "winreg", "msvcrt", "ctypes.windll")

#: `C:\` / `D:\` / `\AppData\` / `\Program Files`。
#: ⚠ 必须有负向断言：`"steps:\n"` 里的 `s:\` 会被当成盘符路径 ——
#: 第一版就是这样，报了 20 多条 YAML 行的假阳性（`\n`/`\t` 是转义，不是路径）。
RE_WINPATH = re.compile(
    r"[A-Za-z]:\\(?![ntr0\\'\"])|\\AppData\\|\\Program Files")


def _noncode_lines(src):
    """返回**注释与文档串**所在的行号集合（0 基）。

    为什么不直接 `line.lstrip().startswith("#")`：docstring 里的实测记录
    （`# 实测 C:\\Temp\\yalmip 70 秒`、`E:\\matlabc` 那种）同样不是代码路径，
    把它们算进来只会逼人删证据。

    用**三引号开关**做轻量扫描而不是 `ast`：本仓承诺 Python 3.6，
    而 `end_lineno` 是 3.8 才有的 —— 用了等于悄悄抬高最低版本。
    """
    skip = set()
    in_doc = False
    for i, line in enumerate(src.splitlines()):
        s = line.strip()
        if s.startswith("#"):
            skip.add(i)
            continue
        marks = s.count('"""') + s.count("'''")
        if in_doc:
            skip.add(i)
            if marks % 2 == 1:
                in_doc = False
            continue
        if marks % 2 == 1:
            skip.add(i)
            in_doc = True
    return skip


def _registered(name, line):
    for (f, marker) in WIN_PATHS:
        if f == name and marker in line:
            return True
    return False


def audit(sources):
    """纯函数：{文件名: 源码} -> 问题列表（PF1/PF2）。

    抽成纯函数是为了 `--selftest` 能喂**构造的坏样本** ——
    否则这些判据只能证明"今天的仓库是绿的"。
    """
    probs = []
    for name, src in sorted(sources.items()):
        for api in WIN_APIS:
            if api in src:
                probs.append("PF2 %s 使用了 Windows 专属 API：%s" % (name, api))
        skip = _noncode_lines(src)
        for i, line in enumerate(src.splitlines()):
            # **注释与文档串不算平台假设**（`# 实测 C:\Temp\yalmip 70 秒`）。
            if i in skip:
                continue
            if not RE_WINPATH.search(line):
                continue
            if _registered(name, line):
                continue
            probs.append("PF1 %s:%d 出现 Windows 绝对路径且未登记：%s"
                         % (name, i + 1, line.strip()[:70]))
    return probs


def stale_registrations(sources):
    """PF3：登记的那段原文在文件里找不到 → 陈旧。"""
    probs = []
    for (name, marker) in sorted(WIN_PATHS):
        src = sources.get(name)
        if src is None:
            probs.append("PF3 %s 不在扫描面里，登记无效" % name)
            continue
        if marker not in src:
            probs.append("PF3 %s 里的登记原文「%s」已不存在 —— 陈旧登记"
                         % (name, marker))
    return probs


def selftest():
    good = bad = 0

    def chk(cond, name, detail=""):
        if not cond:
            print("  [FAIL] %-46s %s" % (name, detail))
        return bool(cond)

    if chk(not audit({u"a.py": u"p = '/usr/bin/node'\n"}),
           u"自证：POSIX 路径放行"):
        good += 1
    else:
        bad += 1

    probs = audit({u"a.py": u"p = 'C:\\data\\x.txt'\n"})
    if chk(bool(probs), u"自证：Windows 路径被抓到", repr(probs[:1])):
        good += 1
    else:
        bad += 1

    if chk(any("PF2" in p for p in audit({u"a.py": u"os.startfile('x')\n"})),
           u"自证：startfile 被抓到"):
        good += 1
    else:
        bad += 1

    stale = stale_registrations({u"matlabc_lsp.py": u"x = 1\n"})
    if chk(bool(stale), u"自证：陈旧登记被抓到", repr(stale[:1])):
        good += 1
    else:
        bad += 1

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    if args.help:
        sys.stdout.write(__doc__)
        return 0
    if args.selftest:
        return selftest()

    sources = {}
    for name in RUNTIME:
        p = os.path.join(ROOT, name)
        if os.path.isfile(p):
            sources[name] = io.open(p, "r", encoding="utf-8",
                                    errors="replace").read()
    if not sources:
        print("check_portability: 缺输入（一个运行时文件都没找到）")
        return 2

    probs = audit(sources) + stale_registrations(sources)
    if probs:
        print("check_portability: FAIL（%d 项）" % len(probs))
        for p in probs[:8]:
            print("  - " + p)
        return 1
    print("check_portability: OK（%d 个运行时文件，%s 全绿；"
          "Windows 路径登记 %d 处）"
          % (len(sources), ROW_SIGNATURE, len(WIN_PATHS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
