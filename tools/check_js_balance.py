#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""`vscode/` 下的 JS 必须括号配平、字符串与正则必须闭合。

    python tools/check_js_balance.py             # 校验
    python tools/check_js_balance.py --selftest  # 判据自证

**为什么需要这道门**：这台机器上**没有任何 JS 引擎**（`where node` 为空，
`Code.exe` 是 Electron 外壳，不能当 `node --check` 用）。所以
`vscode/extension.js` 的语法错误**没有任何东西会报**。

而它的失败方式是最糟的一种：**扩展静默不激活**。

    用户看到：点了 F12 / 悬停 / 大纲 —— 什么反应都没有。
    日志里：  activate() 那一行根本不会出现。

R205 和 R213 两次「点了没反应」都是这么排查的：先看图，再看日志，
最后才发现问题根本不在协议层。

判据族 **JS1–JS4**：

    JS1  `vscode/extension.js` 非空，且扫描零错误
    JS2  `vscode/lspClient.js` 非空，且扫描零错误
    JS3  **扫描器自己的 10 条用例全过**（判据也要被检验：它第一版报过
         300 条假错误，因为不认正则字面量 `/[&<>"]/g`）
    JS4  `vscode/package.json` 可解析、`main` 指向的文件**真的存在**、
         有 `engines.vscode`、声明了 `matlab` language。
         **扩展「静默不激活」最常见的原因其实在清单里，不在 JS 里** ——
         `main` 指向一个被改名的文件时，VSCode 连报错都不给

**这是启发式，不是解析器**：它只认括号配平、字符串闭合、正则闭合。
它抓不到 `const x = ;` 这种。**但它抓得到「编辑时漏了一个 `}` 或引号」**
—— 而那一类恰恰是手改 600 行 JS 时最常见的。

**扫描器自己错过一次**：第一版不认正则字面量，于是
`/[&<>"]/g` 里的引号被当成字符串开头，报了 **300 条假错误**。
`--selftest` 里专门留了这条用例（`JS3` 之外的第 4 例），防止再犯。

退出码：
    0  = 两个 JS 文件都配平、扫描器用例全过、`package.json` 骨架完整
    1  = 有文件配平失败（或字符串/正则未闭合），或清单不合规
    2  = 缺输入（`vscode/` 下找不到这两个 JS 或 `package.json`）
"""
import argparse
import io
import json
import os
import sys

#: 本门在 README 质量门表那一行里声明的判据族。
ROW_SIGNATURE = "JS1–JS4"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VDIR = os.path.join(ROOT, "vscode")

#: `/` 之前出现这些字符（忽略空白）时，`/` 开始的是**正则**而不是除号。
REGEX_PREV = set("(,=:[!&|?{};\n")
PAIRS = {")": "(", "]": "[", "}": "{"}

_RESULT = {"bad": 0, "good": 0, "fails": []}


def _chk(cond, name):
    if cond:
        _RESULT["good"] += 1
    else:
        _RESULT["bad"] += 1
        _RESULT["fails"].append(name)


def scan(src):
    """返回错误描述列表（空列表 = 配平）。

    跳过：行注释、块注释、单/双引号字符串、模板串、**正则字面量**。
    """
    errors = []
    stack = []
    i = 0
    line = 1
    n = len(src)

    def prev_sig(k):
        j = k - 1
        while j >= 0 and src[j] in " \t":
            j -= 1
        return src[j] if j >= 0 else "\n"

    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                if src[i] == "\n":
                    line += 1
                i += 1
            i += 2
            continue
        if c == "/" and prev_sig(i) in REGEX_PREV:
            i += 1
            in_class = False
            closed = False
            while i < n:
                ch = src[i]
                if ch == "\\":
                    i += 2
                    continue
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    i += 1
                    closed = True
                    break
                elif ch == "\n":
                    break
                i += 1
            if not closed:
                errors.append("第 %d 行：正则未闭合" % line)
                line += 1
            continue
        if c in "'\"`":
            q = c
            start = line
            i += 1
            closed = False
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == "\n":
                    line += 1
                    if q != "`":
                        break
                    i += 1
                    continue
                if src[i] == q:
                    i += 1
                    closed = True
                    break
                i += 1
            if not closed and q != "`":
                errors.append("第 %d 行：字符串未闭合" % start)
            continue
        if c in "([{":
            stack.append((c, line))
        elif c in ")]}":
            if not stack:
                errors.append("第 %d 行：多余的 %r" % (line, c))
            elif stack[-1][0] != PAIRS[c]:
                errors.append("第 %d 行：%r 与第 %d 行的 %r 不匹配"
                              % (line, c, stack[-1][1], stack[-1][0]))
                stack.pop()
            else:
                stack.pop()
        i += 1

    for c, ln in stack:
        errors.append("第 %d 行的 %r 从未闭合" % (ln, c))
    return errors


#: 扫描器自己的用例：`(源码, 期望有错, 名字)`。
#: **好输入必须干净、坏输入必须报错**，两个方向都要有 —— 否则「永远返回
#: 空列表」也能通过。
CASES = (
    ("function f() { return 1; }\n", False, "平衡"),
    ("function f() {\n  return 1;\n", True, "少一个 }"),
    ("}\n", True, "多余的 }"),
    ("var s = 'abc;\n", True, "单引号未闭合"),
    ('var s = "abc";\n', False, "双引号闭合"),
    ('var s = "a\\"b";\n', False, "转义引号"),
    # **这一例是第一版报 300 条假错误的元凶**：正则里的引号
    ('var r = /[&<>"]/g;\nvar x = 1;\n', False, "正则里的引号"),
    ("var s = `a${1}b`;\n", False, "模板串"),
    ("// }\n", False, "注释里的 }"),
    ("/* { */\n", False, "块注释里的 {"),
)


def run_cases():
    """跑 `CASES`；返回 (失败数, 通过数)。"""
    bad = 0
    good = 0
    for src, want_err, name in CASES:
        errs = scan(src)
        if bool(errs) == want_err:
            good += 1
        else:
            bad += 1
            print("  [FAIL] selftest/%s —— 期望%s，实际 %r"
                  % (name, "报错" if want_err else "干净", errs[:2]))
    return bad, good


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv or sys.argv[1:])

    if args.help:
        print(__doc__)
        return 0
    if args.selftest:
        bad, good = run_cases()
        # **`SELFTEST COUNTS` 这一行是 `check_all` 的契约**：runner 用
        # `if "SELFTEST COUNTS" not in out: 判为缺自证`。R240 之前这里只
        # 打 `JS SELFTEST {...}`，于是**单跑绿、进 runner 就红** ——
        # 而我又一直只单跑，所以这道门的自证从未真正被 runner 承认过。
        print('JS SELFTEST {"bad": %d, "good": %d}' % (bad, good))
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if bad == 0 else 1

    if not os.path.isdir(VDIR):
        print("check_js_balance: 缺输入（%s）" % VDIR)
        return 2

    p1 = os.path.join(VDIR, "extension.js")
    p2 = os.path.join(VDIR, "lspClient.js")
    for p in (p1, p2):
        if not os.path.isfile(p):
            print("check_js_balance: 缺输入（%s）" % p)
            return 2

    # 判据名必须是**字面量前缀**：H2a/H2b 会核对 `ROW_SIGNATURE` 与源码里
    # 实际出现的 JSn 次数。用 `"%s/%s" % (tag, name)` 拼标签会让 JS1/JS2
    # 变成「幽灵声明」—— 这一版第一稿就是这么被自己的元门抓住的。
    src1 = io.open(p1, "r", encoding="utf-8").read()
    _chk(bool(src1.strip()), "JS1 extension.js 非空")
    errs1 = scan(src1)
    _chk(not errs1, "JS1 extension.js 配平（%r）" % (errs1[:3],))

    src2 = io.open(p2, "r", encoding="utf-8").read()
    _chk(bool(src2.strip()), "JS2 lspClient.js 非空")
    errs2 = scan(src2)
    _chk(not errs2, "JS2 lspClient.js 配平（%r）" % (errs2[:3],))

    cbad, cgood = run_cases()
    _chk(cbad == 0, "JS3 扫描器用例（%d 过 / %d 败）" % (cgood, cbad))

    # ---- JS4：`package.json` 本身（R241）------------------------------
    # 扩展「静默不激活」最常见的原因其实不是 JS 括号，而是**清单**：
    # 解析失败、`main` 指向一个被改名的文件、少了 `engines.vscode`。
    # VSCode 遇到这些要么不加载、要么加载了但没有任何贡献点 ——
    # 症状和 JS 语法错一模一样（点了没反应），区别只在日志里多一行。
    pkg_path = os.path.join(VDIR, "package.json")
    pkg = None
    try:
        pkg = json.loads(io.open(pkg_path, encoding="utf-8").read())
        _chk(isinstance(pkg, dict), "JS4 package.json 是对象")
        if not isinstance(pkg, dict):
            pkg = None
    except Exception as exc:
        _chk(False, "JS4 package.json 可解析（%r）" % (exc,))
    if pkg is not None:
        main_rel = pkg.get("main") or ""
        _chk(bool(main_rel), "JS4 package.json 有 main")
        _chk(bool(main_rel) and
             os.path.isfile(os.path.join(VDIR, main_rel.replace("/", os.sep))),
             "JS4 main 指向的文件存在（%r）" % (main_rel,))
        _chk(bool((pkg.get("engines") or {}).get("vscode")),
             "JS4 package.json 有 engines.vscode")
        langs = ((pkg.get("contributes") or {}).get("languages") or [])
        _chk(any(isinstance(l, dict) and l.get("id") == "matlab"
                 for l in langs),
             "JS4 package.json 声明了 matlab language")

    if _RESULT["bad"]:
        for f in _RESULT["fails"]:
            print("  [FAIL] " + f)
        print("check_js_balance: %d 项失败" % _RESULT["bad"])
        return 1
    print("check_js_balance: OK（%s：2 个 JS 文件配平，扫描器 %d 条用例全过）"
          % (ROW_SIGNATURE, len(CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
