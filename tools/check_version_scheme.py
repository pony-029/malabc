# -*- coding: utf-8 -*-
"""版本号规则（门）。

规则：**每一位只走 0–9，满 10 进一位**。

    patch 0..9   -> 0.7.3 -> 0.7.4
    patch 满 10  -> 0.7.9 -> 0.8.0
    minor 满 10  -> 0.9.9 -> 1.0.0

为什么值得一道门：版本号是**纯人工维护**的数字，写 `0.6.105` 和写 `0.7.0`
在任何别的门里都看不出区别 —— 但前者会让"哪一版更新得多"失去可读性，
而它恰恰是发版时唯一能快速判断的东西。0.6.104 就是这么积累出来的。

判据：
    VS1  当前版本每一位都在 0–9 之内（越界 = 该进位了）
    VS2  releases/README.md 的版本表首行 == 当前版本
         （否则说明升了版本却没重新生成表）

用法：
    python tools/check_version_scheme.py
    python tools/check_version_scheme.py --selftest

退出码：
    0  = 版本号合规，且版本表首行就是它（VS1–VS2 全绿）
    1  = 版本位越界（该进位了），或升了版本却没重新生成版本表
    2  = 读不到 vscode/package.json
"""
import argparse
import io
import json
import os
import re
import sys

ROW_SIGNATURE = "VS1–VS2"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PKG = os.path.join(ROOT, "vscode", "package.json")
REL = os.path.join(ROOT, "releases", "README.md")

MAX_DIGIT = 9


def clean_cell(cell):
    """版本表里当前版本那格带「（当前）」标注，它不是版本号的一部分。

    第一版直接拿原字符串比，于是永远不相等 —— 门把自己弄红了一次。
    """
    return re.sub(r"[（(].*?[）)]", "", cell or "").strip()


def audit(version, first_row):
    """纯函数：给版本号与版本表首行，返回问题列表。

    抽成纯函数，是为了 `--selftest` 能把**构造的坏值**喂进来：
    否则这些判据只能证明「今天的仓库是绿的」，证明不了它们会红。
    """
    problems = []
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", (version or "").strip())
    if not m:
        problems.append("VS1 版本号不是 主.次.补 三段式：%r" % (version,))
        nums = []
    else:
        nums = [int(x) for x in m.groups()]
    over = [n for n in nums if not (0 <= n <= MAX_DIGIT)]
    if over:
        nxt = ("%d.%d.0" % (nums[0], nums[1] + 1)
               if len(nums) == 3 and nums[1] < MAX_DIGIT else "1.0.0")
        problems.append("VS1 %s 有越界的位 %r —— 该进位了，下一版应为 %s"
                        "（用 tools/bump_version.py --apply）"
                        % (version, over, nxt))

    first = clean_cell(first_row)
    if not first:
        problems.append("VS2 版本表里没有找到任何版本行")
    elif first != (version or "").strip():
        problems.append("VS2 版本表首行是 %s，而当前版本是 %s"
                        "（升版本后要跑 tools/make_release.py）"
                        % (first, version))
    return problems


def read_first_row(path):
    try:
        text = io.open(path, "r", encoding="utf-8").read()
    except Exception:
        return ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(u"| 0.") or s.startswith(u"| 1."):
            return s.split(u"|")[1].strip()
    return ""


def selftest():
    good = bad = 0

    def chk(cond, name, detail=""):
        if not cond:
            print("  [FAIL] %-42s %s" % (name, detail))
        return bool(cond)

    cases = [
        # (版本, 表首行, 期望红?, 说明)
        ("0.7.1", "0.7.1", False, "好样本"),
        ("0.7.0", "0.7.0（当前）", False, "表里带「（当前）」标注也算相等"),
        ("0.6.104", "0.6.104（当前）", True, "补丁位越界"),
        ("0.9.9", "0.9.9", False, "边界：小版本满 9 仍合规"),
        ("0.7.0", "0.6.104", True, "升了版本却没重新生成表"),
        ("0.7", "0.7", True, "不是三段式"),
    ]
    for version, first, want_red, why in cases:
        probs = audit(version, first)
        got = bool(probs)
        if chk(got == want_red, "自证：%s（%s/%s）" % (why, version, first),
               repr(probs[:1])):
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

    try:
        doc = json.loads(io.open(PKG, "r", encoding="utf-8").read())
    except Exception as exc:
        print("check_version_scheme: 读不到 package.json：%r" % (exc,))
        return 2
    cur = str(doc.get("version") or "")
    problems = audit(cur, read_first_row(REL))

    if problems:
        print("check_version_scheme: FAIL（%d 项）" % len(problems))
        for p in problems[:6]:
            print("  - " + p)
        return 1
    print("check_version_scheme: OK（%s，%s 全绿）" % (cur, ROW_SIGNATURE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
