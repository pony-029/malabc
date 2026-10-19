# -*- coding: utf-8 -*-
"""新门生成器 —— 把 CONTRIBUTING 里那六处一次性做掉。

为什么要有它
============
R413 记下"新增一道门要同时改的六处"，R414 照着做仍然被 N1 抓了一次
（散文数字在另一个文件里换了种写法）。清单能提醒，但保证不了逐字改到。

这个脚本负责**机械的那部分**：骨架文件 + 那五处登记。判据本身当然还得人写。

用法
====
    python tools/new_gate.py --name check_foo --signature "FT1–FT3" \\
        --desc "一句话说明这道门守什么" --in-release --register
    python tools/new_gate.py ... --dry-run     # 只打印将改哪里，不落盘

参数：
    --name        脚本名，不带 .py，必须以 check_ 开头
    --signature   判据族签名，形如 FT1–FT3
    --desc        一句话说明（会进 README 表与 ASCII 树）
    --in-release  同时加进 release.py 的 GATES
    --register    真的改那五处（不加则只生成文件）
    --dry-run     与 --register 一起用时只打印

退出码：
    0  = 生成（与登记）成功，或 dry-run 完成
    1  = 已存在同名文件，拒绝覆盖
    2  = 参数不合法（名字/签名格式不对）
"""
import argparse
import io
import os
import re
import sys

ROW_SIGNATURE = "NG1–NG2"

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

TEMPLATE = u'''# -*- coding: utf-8 -*-
"""{desc}

判据族 **{sig}**。

用法：
    python tools/{name}.py
    python tools/{name}.py --selftest     # 两向自证：坏样本要红、好样本要过

退出码：
    0  = {desc}（{sig} 全绿）
    1  = 发现不合规
    2  = 缺输入
"""
import sys

ROW_SIGNATURE = "{sig}"


def check():
    """返回问题列表（空 = 通过）。"""
    return []


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--selftest" in argv:
        return selftest()
    problems = check()
    if problems:
        for msg in problems:
            print("  - %s" % msg)
        print("{name}: %d 项不合规" % len(problems))
        return 1
    print("{name}: OK（{sig} 全绿）")
    return 0


def selftest():
    """两向自证：造一个必失败的样本，确认判据会红。"""
    good = bad = 0

    def chk(cond, name):
        nonlocal good, bad
        if cond:
            good += 1
        else:
            bad += 1
            print("  [FAIL] %s" % name)

    chk(True, "占位：先写一条真判据，再把它变成必红的样本")
    print('SELFTEST COUNTS {{"bad": %d, "good": %d}}' % (bad, good))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _write(path, text, apply_it):
    if not apply_it:
        print("   [dry] 将写入 %s" % os.path.relpath(path, REPO))
        return
    io.open(path, "w", encoding="utf-8", newline="").write(text)


def _replace_once(path, old, new, apply_it, what):
    if not os.path.isfile(path):
        print("   [跳过] 找不到 %s" % os.path.relpath(path, REPO))
        return
    t = io.open(path, encoding="utf-8").read()
    if old not in t:
        print("   [跳过] %s：锚点没命中（%s）" % (os.path.relpath(path, REPO), what))
        return
    if not apply_it:
        print("   [dry] 将修改 %s（%s）" % (os.path.relpath(path, REPO), what))
        return
    io.open(path, "w", encoding="utf-8", newline="").write(t.replace(old, new, 1))
    print("   [ok ] %s（%s）" % (os.path.relpath(path, REPO), what))


def register(name, sig, desc, in_release, apply_it):
    # 1) GUARD_CONTRACT
    p = os.path.join(HERE, "check_help_contract.py")
    anchor = u'    "tools/check_release_gates.py": {'
    entry = (u'    "tools/%s.py": {\n'
             u'        0: "%s（%s 全绿）",\n'
             u'        1: "发现不合规",\n'
             u'        2: "缺输入",\n'
             u'    },\n' % (name, desc, sig))
    _replace_once(p, anchor, entry + anchor, apply_it, "GUARD_CONTRACT")

    # 2) ASCII 树
    p = os.path.join(HERE, "check_all.py")
    m = re.search(r'(?m)^(        └─▶|        ├─▶) (\S+)', io.open(p, encoding="utf-8").read())
    anchor_line = u"        ├─▶ check_release_gates.py        发版门清单：写了没进 GATES 的门 / 陈旧豁免（契约 RG1..RG2）\n"
    line = (u"        ├─▶ %-30s %s（契约 %s）\n"
            % (name + ".py", desc, sig.replace(u"\u2013", "..")))
    _replace_once(p, anchor_line, anchor_line + line, apply_it, "ASCII 树")

    # 3) 两份 README
    for doc in ("README.md", "README_CN.md"):
        p = os.path.join(REPO, doc)
        anchor = u"| `check_release_gates.py` |"
        if not os.path.isfile(p):
            continue
        t = io.open(p, encoding="utf-8").read()
        i = t.index(anchor) if anchor in t else -1
        if i < 0:
            print("   [跳过] %s：找不到门表锚点" % doc)
            continue
        j = t.index("\n", i) + 1
        row = u"| `%s.py` | `%s` — %s |\n" % (name, sig, desc)
        if not apply_it:
            print("   [dry] 将修改 %s（门表行）" % doc)
            continue
        io.open(p, "w", encoding="utf-8", newline="").write(t[:j] + row + t[j:])
        print("   [ok ] %s（门表行）" % doc)

    # 4) release.py
    if in_release:
        p = os.path.join(HERE, "release.py")
        _replace_once(p, u'         "check_release_gates")',
                      u'         "check_release_gates",\n         "%s")' % name,
                      apply_it, "GATES")


COUNT_FILES = ("README.md", "README_CN.md", "CONTRIBUTING.md",
               "matlabc_help.py")

#: 散文里出现过的写法。N1 不认写法、只认数字与事实是否一致 ——
#: 这里也一样：把长得像"门数"的数字全换掉。
COUNT_PAT = re.compile(u"(\\d+)( 道静态门| 道登记制护栏| 道门| 道，| gates)")

#: 只改**看起来像门总数**的数字。试跑时它曾想把 "7 gates" / "8 gates" /
#: "19 道门" 一起改成 36 —— 那些讲的是别的东西，改了就是制造错误。
#: 门数目前是三十几，20 是个安全下界；低于它的匹配只报不改。
MIN_PLAUSIBLE = 20


def real_gate_count():
    return len([n for n in os.listdir(HERE)
                if n.startswith("check_") and n.endswith(".py")])


def fix_counts(apply_it):
    """把四份文档里的「N 道门」改成真实数量。"""
    n = real_gate_count()
    for rel in COUNT_FILES:
        p = os.path.join(REPO, rel)
        if not os.path.isfile(p):
            continue
        t = io.open(p, encoding="utf-8").read()
        hits = [m.group(0) for m in COUNT_PAT.finditer(t)
                if int(m.group(1)) != n and int(m.group(1)) >= MIN_PLAUSIBLE]
        skipped = [m.group(0) for m in COUNT_PAT.finditer(t)
                   if int(m.group(1)) != n and int(m.group(1)) < MIN_PLAUSIBLE]
        if skipped and apply_it:
            print("   [跳过] %s：%s（不像门总数，留给人判断）"
                  % (rel, "、".join(skipped[:3])))
        if not hits:
            continue
        if not apply_it:
            print("   [dry] %s：%d 处数字将改为 %d（%s）"
                  % (rel, len(hits), n, "、".join(hits[:3])))
            continue
        t2 = COUNT_PAT.sub(
            lambda m: (u"%d%s" % (n, m.group(2))
                       if int(m.group(1)) >= MIN_PLAUSIBLE
                       else m.group(0)), t)
        io.open(p, "w", encoding="utf-8", newline="").write(t2)
        print("   [ok ] %s：%d 处改成了 %d" % (rel, len(hits), n))


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--signature", required=True)
    ap.add_argument("--desc", required=True)
    ap.add_argument("--in-release", action="store_true")
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fix-counts", action="store_true",
                    help="顺带把散文里的「N 道门」改成真实数量")
    args = ap.parse_args(argv)

    if not re.match(r"^check_[a-z0-9_]+$", args.name):
        print("名字必须是 check_xxx（小写字母/数字/下划线）")
        return 2
    if not re.match(u"^[A-Z]+\\d+\u2013[A-Z]+\\d+$", args.signature):
        print("签名形如 FT1–FT3（用 en dash）")
        return 2

    path = os.path.join(HERE, args.name + ".py")
    if os.path.exists(path):
        print("%s 已存在，拒绝覆盖" % os.path.relpath(path, REPO))
        return 1

    apply_it = args.register and not args.dry_run
    _write(path, TEMPLATE.format(name=args.name, sig=args.signature,
                                 desc=args.desc), apply_it)
    if args.register:
        register(args.name, args.signature, args.desc, args.in_release, apply_it)
    if args.fix_counts:
        fix_counts(apply_it)

    print("")
    print("")
    print("还剩一件事脚本不做：**判据本身** ——")
    print("  骨架里的 check() 现在总是通过，先写一条真判据，再把它变成必红的样本。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
