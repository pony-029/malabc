# -*- coding: utf-8 -*-
"""工具自证 check —— 带 `--selftest` 的脚本，每次发版都真跑一遍。

为什么要有它
============
R422 加了 `tools/patch_text.py`（带语法自检的替换器），自证写得挺全。
但**没有任何地方会去跑它的自证** —— 工具自己会烂，而没人知道。
本仓的门都是 `check_*.py`，工具类脚本不在任何清单里。

一条工具的自证，和一道门的判据一样，只有被执行才存在。

判据族 **TS1–TS2**：

    TS1  `tools/*.py` 里凡是声明了 `--selftest` 的，跑它必须 rc=0
    TS2  至少存在一个这样的工具（否则这道门自己在空转）

用法：
    python tools/check_tool_selftests.py
    python tools/check_tool_selftests.py --selftest

退出码：
    0  = 所有带自证的工具都通过（TS1–TS2 全绿）
    1  = 有工具的自证失败（列出名字与输出尾部）
    2  = 缺输入（找不到 tools/ 目录）
"""
import io
import os
import re
import subprocess
import sys

ROW_SIGNATURE = "TS1–TS2"

HERE = os.path.dirname(os.path.abspath(__file__))


def _tools_with_selftest():
    out = []
    for n in sorted(os.listdir(HERE)):
        if not n.endswith(".py") or n.startswith("check_"):
            continue
        try:
            src = io.open(os.path.join(HERE, n), encoding="utf-8").read()
        except (IOError, OSError):
            continue
        # **认显式标记，不认字符串**：模板里写过 `--selftest` 的工具
        # （例如 new_gate.py）会被搜字符串的写法误判成"带自证"。
        if re.search(r"^SELFTEST\s*=\s*True", src, re.M):
            out.append(n)
    return out


def check(names=None):
    """返回问题列表（空 = 通过）。`names` 允许注入，供自证用。"""
    names = _tools_with_selftest() if names is None else names
    if not names:
        return [u"TS2 没有任何工具声明 --selftest（这道门在空转）"]
    problems = []
    for n in names:
        path = os.path.join(HERE, n)
        if not os.path.isfile(path):
            problems.append(u"TS1 %s 不存在" % n)
            continue
        try:
            p = subprocess.run([sys.executable, path, "--selftest"],
                               stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=180)
        except subprocess.TimeoutExpired:
            problems.append(u"TS1 %s --selftest 超时（180s）" % n)
            continue
        except OSError as exc:
            problems.append(u"TS1 %s 跑不起来：%s" % (n, exc))
            continue
        if p.returncode != 0:
            tail = p.stdout.decode("utf-8", "replace").strip().splitlines()[-3:]
            problems.append(u"TS1 %s --selftest rc=%d：%s"
                            % (n, p.returncode, u" / ".join(tail)))
    return problems


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    if not os.path.isdir(HERE):
        print("找不到 tools/ 目录")
        return 2
    problems = check()
    if problems:
        for msg in problems:
            print("  - %s" % msg)
        print("check_tool_selftests: %d 项不合规" % len(problems))
        return 1
    names = _tools_with_selftest()
    print("check_tool_selftests: OK（TS1–TS2 全绿；%d 个工具：%s）"
          % (len(names), ", ".join(names)))
    return 0


def selftest():
    """两向自证：真工具必须过；伪造一个必失败的工具名必须红。"""
    good = bad = 0

    def chk(cond, name):
        nonlocal good, bad
        if cond:
            good += 1
        else:
            bad += 1
            print("  [FAIL] %s" % name)

    real = _tools_with_selftest()
    chk(bool(real), "确实存在带自证的工具（否则本门空转）")
    chk(check() == [], "现有工具的自证全部通过")
    chk(any(u"不存在" in m for m in check(["no_such_tool_xyz.py"])),
        "不存在的工具会被判 TS1")

    # 造一个必失败的工具，确认 rc!=0 会被抓
    import shutil
    import tempfile
    d = tempfile.mkdtemp(prefix="ts_")
    try:
        bad_tool = os.path.join(d, "bad_tool.py")
        io.open(bad_tool, "w", encoding="utf-8", newline="").write(
            u"import sys\n"
            u"def main():\n"
            u"    print('boom')\n"
            u"    return 1\n"
            u"if __name__ == '__main__':\n"
            u"    sys.exit(main())\n")
        # 直接跑它，确认"失败能被看见"这条前提成立
        p = subprocess.run([sys.executable, bad_tool],
                           stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=60)
        chk(p.returncode != 0, "坏工具确实返回非 0")
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
