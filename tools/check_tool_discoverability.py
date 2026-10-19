#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""工具必须能被发现：`tools/` 下的每个非护栏脚本都要在 README 里出现。

    python tools/check_tool_discoverability.py            # 校验
    python tools/check_tool_discoverability.py --selftest # 判据自证

**为什么需要这道门**：`tools/` 下的护栏（`check_*.py`）有 `check_all`
和 README 的「质量门表」两处对手方，**不会消失**。但**非护栏工具没有**：

    tools/sweep_cli.py     十轮里长到 118 条判据，R185 之前 README 一次没提
    tools/lsp_selftest.py  仓库内判据**红了六轮**，因为没人知道要跑它

**「工具存在但没人知道」和「工具不存在」在效果上是同一件事。**
本门就是给那条边界配一个对手方：**每个非护栏工具，至少在 README 出现一次。**

判据族 **TD1–TD3**。

#: P5 的对手方：本门在 README 质量门表那一行里声明的判据族。
ROW_SIGNATURE = "TD1–TD4"

退出码：
    0  = 每个非护栏工具都在 README 里出现
    1  = 有工具在 README 里找不到（或 --selftest 失败）
    2  = 缺输入（tools/ 或 README 不在）
"""
import argparse
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = HERE
READMES = (os.path.join(ROOT, "README.md"),
           os.path.join(ROOT, "README_CN.md"))

#: 不算「工具」的：护栏自身（另有门守）、包初始化。
SKIP = ("check_", "__init__")


def tool_scripts():
    """`tools/` 下的非护栏 `.py`（去掉 `check_*` 与 `__init__`）。"""
    out = []
    for name in sorted(os.listdir(TOOLS)):
        if not name.endswith(".py"):
            continue
        if any(name.startswith(s) for s in SKIP):
            continue
        out.append(name)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv or sys.argv[1:])

    if args.help:
        sys.stdout.write(__doc__)
        return 0

    def chk(cond, name, detail=""):
        if not cond:
            print("  [FAIL] %-32s %s" % (name, detail))
        return bool(cond)

    if args.selftest:
        good = bad = 0
        tools = tool_scripts()
        if chk(bool(tools), "自证：能找到非护栏工具",
               "tools/ 下没有非护栏 .py"):
            good += 1
        else:
            bad += 1
        if chk("sweep_cli.py" in tools, "自证：sweep_cli.py 在名单里"):
            good += 1
        else:
            bad += 1
        if chk(u"USER_GUIDE.md" in (
                io.open(os.path.join(os.path.dirname(TOOLS), "vscode",
                                     "README.md"), "r",
                        encoding="utf-8").read()
                if os.path.isfile(os.path.join(os.path.dirname(TOOLS),
                                               "vscode", "README.md")) else u""),
               "自证：扩展页引用用户手册"):
            good += 1
        else:
            bad += 1
        if chk(not any(t.startswith("check_") for t in tools),
               "自证：护栏被排除"):
            good += 1
        else:
            bad += 1
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if bad == 0 else 1

    if not os.path.isdir(TOOLS):
        print("check_tool_discoverability: 缺输入（%s）" % TOOLS)
        return 2
    texts = {}
    for p in READMES:
        if not os.path.isfile(p):
            print("check_tool_discoverability: 缺输入（%s）" % p)
            return 2
        with io.open(p, "r", encoding="utf-8") as fh:
            texts[os.path.basename(p)] = fh.read()

    tools = tool_scripts()
    bad = 0
    # T1：每个非护栏工具必须至少在一份 README 出现
    missing = []
    for name in tools:
        if not any(name in t for t in texts.values()):
            missing.append(name)
    if not chk(not missing, "TD1 工具在 README 里能找到",
               "没被任何 README 提到：%r（工具存在但没人知道）"
               % (missing,)):
        bad += 1
    # T2：两侧一致 —— 不能在英文有、中文没有
    asym = []
    for name in tools:
        en = name in texts["README.md"]
        cn = name in texts["README_CN.md"]
        if en != cn:
            asym.append((name, en, cn))
    if not chk(not asym, "TD2 两侧都提到",
               "只有一侧提到：%r" % (asym,)):
        bad += 1
    # T3：名单非空（解析坏了会变成「全部通过」）
    if not chk(bool(tools), "TD3 名单非空",
               "tools/ 下解析不到任何非护栏工具"):
        bad += 1

    # TD4：**用户手册必须能从扩展页点到**。
    # 起因：USER_GUIDE.md 与 4 张示意图都在包里，但 README 一处都没引用 ——
    # 手册存在、用户找不到，等于没有。工具要"能被发现"，文档同样要。
    guide = os.path.join(os.path.dirname(TOOLS), "releases", "docs",
                         "USER_GUIDE.md")
    page = os.path.join(os.path.dirname(TOOLS), "vscode", "README.md")
    try:
        page_txt = io.open(page, "r", encoding="utf-8").read()
    except (IOError, OSError):
        page_txt = u""
    if not chk(os.path.isfile(guide) and u"USER_GUIDE.md" in page_txt,
               "TD4 用户手册能从扩展页点开",
               "vscode/README.md 没有引用 USER_GUIDE.md"
               "（手册在，但没人知道它在哪）"):
        bad += 1

    if bad == 0:
        print("check_tool_discoverability: OK（%d 个非护栏工具，两侧 README "
              "都提到：%s；用户手册可从扩展页点开）"
              % (len(tools), ", ".join(tools)))
        return 0
    print("check_tool_discoverability: %d 项不一致" % bad)
    return 1


if __name__ == "__main__":
    sys.exit(main())
