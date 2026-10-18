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
"""
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


def main():
    problems = []
    try:
        doc = json.loads(io.open(PKG, "r", encoding="utf-8").read())
    except Exception as exc:
        print("check_version_scheme: 读不到 package.json：%r" % (exc,))
        return 1
    cur = str(doc.get("version") or "")

    # ---- VS1：每一位都在范围内 ----------------------------------------
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", cur)
    if not m:
        problems.append("版本号不是 主.次.补 三段式：%r" % (cur,))
        nums = []
    else:
        nums = [int(x) for x in m.groups()]
    over = [n for n in nums if not (0 <= n <= MAX_DIGIT)]
    if over:
        nxt = ("%d.%d.0" % (nums[0], nums[1] + 1) if len(nums) == 3
               and nums[1] < MAX_DIGIT else "1.0.0")
        problems.append("VS1 %s 有越界的位 %r —— 该进位了，下一版应为 %s"
                        "（用 tools/bump_version.py --apply）"
                        % (cur, over, nxt))

    # ---- VS2：版本表首行必须就是当前版本 -------------------------------
    try:
        text = io.open(REL, "r", encoding="utf-8").read()
    except Exception:
        text = ""
    first = ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(u"| 0.") or s.startswith(u"| 1."):
            cell = s.split(u"|")[1].strip()
            # 表里当前版本那格带「（当前）」标注，它不是版本号的一部分 ——
            # 第一版直接比原字符串，于是永远不相等（自己把自己弄红）。
            first = re.sub(r"[（(].*?[）)]", "", cell).strip()
            break
    if not first:
        problems.append("VS2 版本表里没有找到任何版本行")
    elif first != cur:
        problems.append("VS2 版本表首行是 %s，而当前版本是 %s"
                        "（升版本后要跑 tools/make_release.py）"
                        % (first, cur))

    if problems:
        print("check_version_scheme: FAIL（%d 项）" % len(problems))
        for p in problems[:6]:
            print("  - " + p)
        return 1
    print("check_version_scheme: OK（%s，%s 全绿）" % (cur, ROW_SIGNATURE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
