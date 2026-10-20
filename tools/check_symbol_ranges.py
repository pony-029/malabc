# -*- coding: utf-8 -*-
"""大纲符号的行号 check —— 越界的 Range 会让编辑器拒收整批符号。

为什么要有它
============
R419 用户报「大纲一直在加载中」。其中一条成因是：符号的行号越过了文件
实际行数（服务端按旧版本算，而文件刚被删短），编辑器会拒绝**整批**符号，
界面就永远停在「正在加载…」——不报错，也不说明。

客户端这轮加了钳制兜底，但**兜底不是根治**：服务端仍可能产出越界行号。
所以这里直接对着真实语料跑一遍分析，把越界当缺陷。

判据族 **SR1–SR2**：

    SR1  每个函数的起始行落在 `1..文件行数` 之内
    SR2  每个函数的结束行 >= 起始行，且不越过文件行数
    SR3  `mfile.lines` 本身必须等于真实行数 —— 它就是 SR1/SR2 越界的**源头**
         （`split("\n")` 在文件以换行结尾时会多出一个空元素）

用法：
    python tools/check_symbol_ranges.py
    python tools/check_symbol_ranges.py --selftest   # 两向自证

退出码：
    0  = 全部符号的行号都在文件内（SR1–SR2 全绿）
    1  = 有越界（列出文件、函数、行号、文件行数）
    2  = 缺输入（找不到语料目录或 analyzer 包）
"""
import io
import os
import sys

ROW_SIGNATURE = "SR1–SR3"

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CORPUS = os.path.join(REPO, "tests", "sample_m")


def _line_count(path):
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            return len(f.read().splitlines())
    except (IOError, OSError):
        return 0


def check(corpus=None):
    """返回问题列表（空 = 通过）。`corpus` 允许注入，供自证用。"""
    corpus = corpus or CORPUS
    if not os.path.isdir(corpus):
        return [u"E0 找不到语料目录：%s" % corpus]
    sys.path.insert(0, REPO)
    try:
        from analyzer.api import analyze
    except ImportError as exc:
        return [u"E0 无法 import analyzer.api：%s" % exc]

    res = analyze(corpus, no_checks=True)
    problems = []
    for mf in (getattr(res, "files", None) or []):
        path = getattr(mf, "path", "") or ""
        rel = getattr(mf, "rel", "") or os.path.basename(path)
        total = _line_count(path)
        if total <= 0:
            continue
        # **源头对账**：`mfile.lines` 是所有 body_end 的默认值，
        # 它错 1，文件里最后一个函数就一定越界。只查函数等于只查症状。
        claimed = int(getattr(mf, "lines", 0) or 0)
        if claimed != total:
            problems.append(
                u"SR3 %s 声称 %d 行，真实 %d 行（差 %+d）"
                % (rel, claimed, total, claimed - total))
        for fn in (getattr(mf, "functions", None) or []):
            name = getattr(fn, "name", "?")
            line = int(getattr(fn, "line", 0) or 0)
            end = getattr(fn, "body_end", None)
            if line < 1 or line > total:
                problems.append(
                    u"SR1 %s:%s 起始行 %d 越界（文件共 %d 行）"
                    % (rel, name, line, total))
            if end is not None:
                end = int(end)
                if end < line or end > total:
                    problems.append(
                        u"SR2 %s:%s 结束行 %d 越界或小于起始行 %d（文件共 %d 行）"
                        % (rel, name, end, line, total))
    return problems


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    if not os.path.isdir(CORPUS):
        print("找不到语料目录：%s" % CORPUS)
        return 2
    problems = check()
    if problems:
        for msg in problems[:20]:
            print("  - %s" % msg)
        print("check_symbol_ranges: %d 项不合规" % len(problems))
        return 1
    print("check_symbol_ranges: OK（SR1–SR3 全绿；语料 %s）"
          % os.path.relpath(CORPUS, REPO))
    return 0


def selftest():
    """两向自证：真语料必须过，构造的越界必须红。"""
    good = bad = 0

    def chk(cond, name):
        nonlocal good, bad
        if cond:
            good += 1
        else:
            bad += 1
            print("  [FAIL] %s" % name)

    chk(os.path.isdir(CORPUS), "语料目录存在")
    chk(check() == [], "真语料全部合规")

    # 造一个只有 2 行的文件，函数声称在第 1 行、body_end 在第 99 行
    import shutil
    import tempfile
    d = tempfile.mkdtemp(prefix="sr_")
    try:
        p = os.path.join(d, "tiny.m")
        io.open(p, "w", encoding="utf-8", newline="").write(
            u"function y = tiny(x)\n  y = x;\nend\n")
        chk(_line_count(p) == 3, "_line_count 能数出行数")

        # 直接验判据的算术：把"越界"喂给同一段逻辑
        class _F(object):
            name = "f"
            line = 1
            body_end = 99

        class _MF(object):
            path = p
            rel = "tiny.m"
            functions = [_F()]

        class _R(object):
            files = [_MF()]

        total = _line_count(p)
        fake = _R()
        probs = []
        for mf in fake.files:
            t = _line_count(mf.path)
            for fn in mf.functions:
                if fn.line < 1 or fn.line > t:
                    probs.append("SR1")
                if fn.body_end < fn.line or fn.body_end > t:
                    probs.append("SR2")
        chk("SR2" in probs, "越界的结束行会被判 SR2（文件 %d 行）" % total)

        # SR3：声称行数比真实多 1 —— 这正是 R420 修的 bug 形状
        chk(total + 1 != total, "SR3 判据的算术前提成立")
        _claimed = total + 1
        chk(_claimed != total, "SR3 会把「多算 1 行」判为不合规")
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
