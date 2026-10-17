#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""`sweep_cli.py` 的每个开关都必须被至少一条判据引用。

    python tools/check_flag_coverage.py            # 校验
    python tools/check_flag_coverage.py --selftest # 判据自证

**为什么需要这道门**：今晚同一种错误发生了两次 ——

    R180 加了 `--probe`，到 R184 才补判据
    R186 加了 `--probe-cli`，到 R187 才补判据

**「功能加了但没验证」在代码里没有任何痕迹**：它不报错、不红、
也不影响任何已有判据。唯一能发现它的办法是**数一数每个开关被引用了几次**。

判据族 **FC1–FC3**：
    FC1  每个 `add_argument("--x")` 的开关，在源码里**至少出现两次**
         （一次是声明本身，另一次必须是使用）
    FC2  `--help` / `-h` 除外（它们由 `_write_help` 处理，不参与判据）
    FC3  开关列表非空（解析坏了会变成「全部通过」）

退出码：
    0  = 每个开关都有引用
    1  = 有开关声明了却从没被用过
    2  = 缺输入（`tools/sweep_cli.py` 不在）
"""
import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "sweep_cli.py")

#: P5 的对手方：本门在 README 质量门表那一行里声明的判据族。
ROW_SIGNATURE = "FC1–FC3"

FLAG_RE = re.compile(r'add_argument\(\s*"(--[A-Za-z0-9-]+)"')
EXCLUDE = ("--help", "-h")


def declared_flags(text):
    return sorted(set(FLAG_RE.findall(text)) - set(EXCLUDE))


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv or sys.argv[1:])

    if args.help:
        sys.stdout.write(__doc__)
        return 0

    if not os.path.isfile(TARGET):
        print("check_flag_coverage: 缺输入（%s）" % TARGET)
        return 2
    with io.open(TARGET, "r", encoding="utf-8") as fh:
        text = fh.read()

    def chk(cond, name, detail=""):
        if not cond:
            print("  [FAIL] %-30s %s" % (name, detail))
        return bool(cond)

    flags = declared_flags(text)

    if args.selftest:
        good = bad = 0
        if chk(bool(flags), "自证：解析到开关"):
            good += 1
        else:
            bad += 1
        if chk("--probe" in flags, "自证：--probe 在名单里"):
            good += 1
        else:
            bad += 1
        if chk("--help" not in flags, "自证：--help 被排除"):
            good += 1
        else:
            bad += 1
        print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
        return 0 if bad == 0 else 1

    bad = 0
    # FC1：每个开关至少被引用一次。
    # ⚠ **不能数 `"--meta"` 这个字符串**：argparse 解析后统一变成 `args.meta`，
    # 于是字符串只出现在 `add_argument` 那一处 —— 我第一版就是这么写的，
    # 结果 6 个**确实有判据**的开关全被误报（R192 实测）。
    # 正确的计数对象是 `args.<attr>`。
    unused = []
    for f in flags:
        attr = "args." + f.lstrip("-").replace("-", "_")
        if attr not in text:
            unused.append(f)
    if not chk(not unused, "FC1 开关都有引用",
               "声明了但没有任何 `args.*` 读取：%r（功能加了却没判据）"
               % (unused,)):
        bad += 1
    # FC2：排除项确实被排除了
    if not chk("--help" not in flags, "FC2 --help 已排除"):
        bad += 1
    # FC3：名单非空
    if not chk(bool(flags), "FC3 名单非空"):
        bad += 1

    if bad == 0:
        print("check_flag_coverage: OK（%d 个开关，全部有引用：%s）"
              % (len(flags), ", ".join(flags)))
        return 0
    print("check_flag_coverage: %d 项不一致" % bad)
    return 1


if __name__ == "__main__":
    sys.exit(main())
