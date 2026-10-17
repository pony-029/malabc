# -*- coding: utf-8 -*-
"""MATLAB 语法（TextMate）的**一致性判据**。

R214 背景：用户连续两次报「高亮不一致」——

1. R212：`X(:,1)` 被「后面跟 `(` 就算函数调用」的规则染成函数色，而 `F` 没有。
2. R214：`X'`（转置）被无条件当成字符串开头，一个 `X'` 能把后面几十行染成字符串色。

两次都是同一类问题：**规则无法区分两种语法角色，却假设了其中一种。**
本门把这个假设变成可执行判据：

    G1 转置上下文不开启单引号字符串（`X'` / `(A*B)'` / `s.f'` / `3'`）
    G2 字符串上下文仍开启（`a = 'x'` / `{'a'}` / `[a;b]` 后的 `'x'`）
    G3 块注释 `%{` 必须独占一行（`x=1; %{ 说明` 是行注释）
    G4 所有正则能在 Python `re` 下编译（提前抓语法错误，而不是等 VSCode 静默失效）
    G5 不允许 `support.function` 残留（R212 的回归防护）
    G6 真实 `.m` 语料里**没有跨行单引号字符串**（MATLAB 的 `'` 字符串不能跨行，
       一旦 begin 匹配到而同行内没有 end，就是误判 —— 这条抓的是"实际影响范围"）

判据族 **GR1–GR6**（本脚本的 `ROW_SIGNATURE`，两份 README 的门表要逐字含它）。

退出码：
    0  = 全绿
    1  = 有判据失败
    2  = 缺输入（语法文件或语料目录不在）
"""
import argparse
import io
import json
import os
import re
import sys

#: P5 的对手方：本门在 README 质量门表那一行里声明的判据族。
ROW_SIGNATURE = "GR1–GR6"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAMMAR = os.path.join(ROOT, "vscode", "syntaxes", "matlab.tmLanguage.json")
CORPUS = os.path.join(ROOT, "tests", "sample_m")

_RESULT = {"bad": 0, "good": 0, "fails": []}


def _chk(cond, name):
    if cond:
        _RESULT["good"] += 1
    else:
        _RESULT["bad"] += 1
        _RESULT["fails"].append(name)


def load_grammar():
    with io.open(GRAMMAR, "r", encoding="utf-8") as fh:
        return json.load(fh)


def repo_rule(gram, repo_name):
    """取 `repository.<name>.patterns[0]`（本语法里每个 repo 只有一条规则）。"""
    ent = (gram.get("repository") or {}).get(repo_name) or {}
    pats = ent.get("patterns") or []
    return pats[0] if pats else {}


def single_quote_begin(gram):
    for p in (gram.get("repository") or {}).get("strings", {}).get("patterns", []):
        if p.get("name") == "string.quoted.single.matlab":
            return p.get("begin")
    return None


def block_comment_begin(gram):
    for p in (gram.get("repository") or {}).get("comments", {}).get("patterns", []):
        if p.get("name") == "comment.block.percentage.matlab":
            return p.get("begin")
    return None


def _m(pat, text):
    """`re.search` 带多行语义（`^` / `$` 按行）。"""
    return re.search(pat, text, re.M) is not None


def check_grammar(gram):
    sq = single_quote_begin(gram)
    _chk(bool(sq), "GRAMMAR 找不到单引号字符串规则")

    if sq:
        # ---- G1：转置上下文**不许**开启字符串 ----
        for sample, label in (
            ("X'", "X'"),
            ("(A*B)'", "(A*B)'"),
            ("s.f'", "s.f'"),
            ("3'", "3'"),
            ("[a; b]'", "[a; b]'"),
            ("A(:,1)'", "A(:,1)'"),
        ):
            _chk(not _m(sq, sample),
                 "GR1 转置被当成字符串开头：%s" % label)

        # ---- G2：字符串上下文**必须**开启 ----
        for sample, label in (
            ("a = 'x'", "a = 'x'"),
            ("a='x'", "a='x'"),
            ("{'a','b'}", "{'a','b'}"),
            ("if ~isfield(model,'a')", "if ~isfield(model,'a')"),
            ("return 'x'", "return 'x'"),
        ):
            _chk(_m(sq, sample),
                 "GR2 字符串没被识别：%s" % label)

    bb = block_comment_begin(gram)
    _chk(bool(bb), "GRAMMAR 找不到块注释规则")

    if bb:
        # ---- G3：`%{` 必须独占一行 ----
        _chk(_m(bb, "%{"), "GR3 独占一行的 %{ 没被识别")
        _chk(_m(bb, "  %{"), "GR3 带缩进的 %{ 没被识别")
        _chk(not _m(bb, "x=1; %{ 说明"), "GR3 行尾的 %{ 被当成块注释（会吃掉后面代码）")
        _chk(not _m(bb, "%{ 说明"), "GR3 同行带文字的 %{ 被当成块注释")

    # ---- G4：所有正则可编译 ----
    bad_re = []
    for repo_name, ent in (gram.get("repository") or {}).items():
        for p in ent.get("patterns") or []:
            for key in ("begin", "end", "match"):
                pat = p.get(key)
                if not pat:
                    continue
                try:
                    re.compile(pat, re.M)
                except Exception as exc:
                    bad_re.append("%s.%s=%r (%r)" % (repo_name, key, pat, exc))
    _chk(not bad_re, "GR4 正则无法编译：%r" % (bad_re[:2],))

    # ---- G5：不许有函数调用着色残留 ----
    has_fn = "support.function" in json.dumps(gram, ensure_ascii=False)
    _chk(not has_fn, "GR5 support.function 残留（R212 已删除该规则）")


def check_corpus(gram, corpus=None):
    """GR6：真实语料里不许出现「单引号 begin 匹配但同行内无 end」。

    MATLAB 的 `'…'` 字符串**不能跨行**。所以只要出现跨行，就说明
    某个 `'` 被误判成字符串开头（真凶通常是转置）。

    `corpus` 可指向任意目录（用 `--corpus`），默认 `tests/sample_m`。
    在 YALMIP（1665 个 .m）上跑过一次：旧规则 5 处误判（含 `norm.m:128`
    的 `X'`），新规则 0 处。
    """
    corpus = corpus or CORPUS
    sq = single_quote_begin(gram)
    if not sq or not os.path.isdir(corpus):
        _chk(False, "GR6 缺语法规则或语料目录")
        return
    rx = re.compile(sq, re.M)
    offenders = []
    files = 0
    for dirpath, dirnames, names in os.walk(corpus):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for n in sorted(names):
            if not n.endswith(".m"):
                continue
            files += 1
            path = os.path.join(dirpath, n)
            try:
                with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
                    lines = fh.read().splitlines()
            except (IOError, OSError):
                continue
            for i, line in enumerate(lines):
                # **整行注释直接跳过**：`comments` 在 patterns 里排在
                # `strings` 前面，所以注释里的 `'` 根本不会开启字符串。
                # 实测 YALMIP 有两行 `% **********'`，第一版 G6 把它们
                # 报成"跨行字符串"，那是检查器没模拟优先级，不是语法 bug。
                if line.lstrip().startswith("%"):
                    continue
                m = rx.search(line)
                if not m:
                    continue
                # 同行剩余部分里还有没有 `'`（能闭合）
                if "'" not in line[m.end():]:
                    rel = os.path.relpath(path, corpus).replace("\\", "/")
                    offenders.append("%s:%d" % (rel, i + 1))
    _chk(files > 0, "GR6 语料里没有 .m 文件")
    _chk(not offenders,
         "GR6 出现跨行单引号字符串（%d 处，前 3：%r）"
         % (len(offenders), offenders[:3]))


def selftest():
    """自证：把两条关键正则**故意改坏**，判据必须变红。"""
    bad, good = 0, 0

    # ① 单引号去掉 lookbehind → G1 必须红
    gram = load_grammar()
    for p in gram["repository"]["strings"]["patterns"]:
        if p.get("name") == "string.quoted.single.matlab":
            p["begin"] = "'"
    _RESULT["bad"] = 0
    _RESULT["good"] = 0
    _RESULT["fails"] = []
    check_grammar(gram)
    if any("GR1" in f for f in _RESULT["fails"]):
        good += 1
    else:
        bad += 1
        print("  [FAIL] 去掉 lookbehind 后 G1 没变红")

    # ② 块注释加回无条件匹配 → G3 必须红
    gram = load_grammar()
    for p in gram["repository"]["comments"]["patterns"]:
        if p.get("name") == "comment.block.percentage.matlab":
            p["begin"] = "%\\{"
    _RESULT["bad"] = 0
    _RESULT["good"] = 0
    _RESULT["fails"] = []
    check_grammar(gram)
    if any("GR3" in f for f in _RESULT["fails"]):
        good += 1
    else:
        bad += 1
        print("  [FAIL] 恢复无条件 %{ 后 G3 没变红")

    print("GRAMMAR SELFTEST {\"bad\": %d, \"good\": %d}" % (bad, good))
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--corpus", default=None,
                    help="GR6 的语料目录（默认 tests/sample_m）")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv or sys.argv[1:])

    if args.help:
        print(__doc__)
        return 0
    if not os.path.isfile(GRAMMAR):
        print("check_matlab_grammar: 缺输入（%s）" % GRAMMAR)
        return 2
    if args.selftest:
        return 0 if selftest() == 0 else 1

    gram = load_grammar()
    check_grammar(gram)
    check_corpus(gram, args.corpus)

    print('GRAMMAR COUNTS {"bad": %d, "good": %d}'
          % (_RESULT["bad"], _RESULT["good"]))
    if _RESULT["fails"]:
        for f in _RESULT["fails"]:
            print("  [FAIL] " + f)
        return 1
    print("check_matlab_grammar: OK（%s，%d 条）" % (ROW_SIGNATURE, _RESULT["good"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
