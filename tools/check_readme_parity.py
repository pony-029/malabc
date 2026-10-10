#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""登记制护栏：README.md 与 README_CN.md 必须**结构对等**，且两侧的「质量门表」必须与
`tools/check_*.py` 的真实清单一致（P4）。

动因（R32 §8 C'2）：
    本仓对双语 README 的一致性，上一轮是**靠人记得**核的（「我数过 12=12」）。
    靠人记的检查等于没有检查 —— 下一次改动只会核到「我记得的那一项」。
    真实退化方式有两种，且都不报错：
        英文加了「GPU 归因」一节，中文没加     → 中文读者看不到这个能力
        中文表格删了一行，英文还在            → 两侧讲的不是同一件事

判据（只认装置，不认叙述）：
    P1 两侧的 `##` 一级小节**数量相等**；
    P2 按出现顺序**逐节对等**：每一节的
         表行数（以 `|` 开头结尾的行）、
         代码块数（``` 配对数）、
         mermaid 图数
       必须与对侧同序号小节相同。
    P3 总行数**不比对** —— 中文更紧凑是正常的（实测 EN 542 行 / CN 524 行），
       把行数当判据会逼人灌水凑长度。这一条是本护栏**刻意不做**的事，
       写在这里免得下轮有人「顺手加上」。
    P4（R61）每一侧 README 的「质量门表」都必须**恰好**列出 `tools/check_*.py`
       里真实存在的脚本（runner `check_all.py` 除外）：漏列 ⇒ 红；列了不存在的
       ⇒ 红；同一行出现两次 ⇒ 红；表的最后一行之后紧跟非空、非表行的文本 ⇒ 红。
       为什么需要它（R56 留下的**真缺陷**）：R56 往这张表里补两行时锚点落错，
       把 `` `check_readme_parity.py` `` 那一行**整行覆盖**掉了，只留下它的尾段
       悬在表末（不再以 `|` 开头 ⇒ 已不是表行）。而 P2 只看「每节的表行数」——
       两侧**同时**少一行，计数当然还相等 ⇒ 门 rc=0。
       **两侧一起坏掉时，对等门永远看不见。** P4 换一个对手方：不比两侧，
       比「表 ↔ 真实护栏清单」。

为什么按序号对齐，而不是按标题文本：
    两侧标题本来就不该相同（一侧中文一侧英文）。「第 N 节的骨架必须一样」
    是不依赖翻译质量的、可机械核对的判据。标题文本是否译得对，是人的事。

两向自证：坏样本（中文少一节 / 少一行表 / 少一个代码块）必须抓得到；
好样本（两侧对等）必须放行；并对真实仓库做一次整体核对。

用法：
    python tools/check_readme_parity.py             # 0=对等 1=不对等 2=缺输入
    python tools/check_readme_parity.py --selftest   # 两向自证

退出码：
    0 = 两侧结构对等
    1 = 发现不对等 / 质量门表与真实护栏清单不符（P1/P2/P4 任一红）
    2 = 缺输入（任一 README 不存在 → 红）
"""
import argparse
import io
import os
import re
import sys

EN = "README.md"
CN = "README_CN.md"
H2 = re.compile(r"^##\s+(.*)$")


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sections(text):
    """按 `## ` 切片。返回 [(heading, [lines])]，第一段是前言（heading=""）。"""
    blocks = []
    cur_head, cur = "", []
    for ln in text.splitlines():
        m = H2.match(ln)
        if m:
            blocks.append((cur_head, cur))
            cur_head, cur = m.group(1).strip(), []
        else:
            cur.append(ln)
    blocks.append((cur_head, cur))
    return blocks


def metrics(body):
    """返回 (表行数, 代码块数, mermaid 数)。"""
    rows = sum(1 for l in body
               if l.strip().startswith("|") and l.strip().endswith("|"))
    txt = "\n".join(body)
    fences = txt.count("```") // 2
    mer = txt.count("mermaid")
    return rows, fences, mer


# ---------------------------------------------------------------------------
# P4（R61）：README 的「质量门表」↔ `tools/check_*.py` 的真实清单。
#
# 现场（独立装置 `_r61/probe_c_shapes.py` 与 `git show 24a2803 -- README.md`
# 一起量出的）：R56 的补丁锚点落在一行**长表格行**上，于是它把那行整行替换掉，
# 只留尾段悬在表末：
#
#     | `check_boundary_reverse.py` | … |
#      structurally — section count, … |     ← 头段没了，这已不是表行
#
# 两侧 README 都少了同一个表行 ⇒ P2 的逐节计数仍然相等 ⇒ 这道门 rc=0。
# ---------------------------------------------------------------------------
GUARD_ROW_RE = re.compile(r"^\|\s*`(check_[A-Za-z0-9_]+\.py)`\s*\|")


def guard_scripts(root):
    """`tools/check_*.py` 的真实清单（不含 runner 自己）；tools/ 不在 ⇒ None。"""
    d = os.path.join(root, "tools")
    if not os.path.isdir(d):
        return None
    return sorted(f for f in os.listdir(d)
                  if f.startswith("check_") and f.endswith(".py")
                  and f != "check_all.py")


def guard_table(lines):
    """找出「质量门表」那块连续的 `|` 行；返回 (start, end, rows) 或 None。

    `rows` 只收首列是 `` `check_*.py` `` 的行 —— 被覆盖掉头的残行不以 `|`
    开头，于是**不会**被算进来：它会在 P4 里以「漏了一行」与「表后有悬空
    续行」两种方式同时现形。
    """
    best = None
    i, n = 0, len(lines)
    while i < n:
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < n and lines[j].lstrip().startswith("|"):
                j += 1
            rows = []
            for k in range(i, j):
                m = GUARD_ROW_RE.match(lines[k].lstrip())
                if m:
                    rows.append(m.group(1))
            if len(rows) >= 3 and (best is None or len(rows) > len(best[2])):
                best = (i, j, rows)
            i = j
        else:
            i += 1
    return best


def judge_table(text, guards, on_problem, label):
    """P4：把一份 README 的质量门表与真实护栏清单对照；返回表行或 None。"""
    lines = text.splitlines()
    got = guard_table(lines)
    if got is None:
        on_problem("P4 %s 找不到质量门表"
                   "（至少 3 行首列为 `check_*.py` 的连续表块）" % label)
        return None
    _start, end, rows = got
    listed = set(rows)
    dups = sorted(r for r in listed if rows.count(r) > 1)
    if dups:
        on_problem("P4 %s 质量门表有重复行：%r" % (label, dups))
    missing = sorted(set(guards) - listed)
    if missing:
        on_problem("P4 %s 质量门表漏了 %d 道真实护栏：%r —— 表与 "
                   "`tools/check_*.py` 是互为对手方的两份清单"
                   % (label, len(missing), missing))
    extra = sorted(listed - set(guards))
    if extra:
        on_problem("P4 %s 质量门表列了不存在的护栏：%r" % (label, extra))
    nxt = lines[end] if end < len(lines) else ""
    if nxt.strip() != "":
        on_problem("P4 %s 质量门表最后一行之后紧跟非空、非表行的文本：%r"
                   " —— 典型的「插行时覆盖掉上一行」留下的悬空续行"
                   % (label, nxt.strip()[:60]))
    return rows


def compare(en_text, cn_text, on_problem):
    """施加 P1/P2；返回被比对的小节数。"""
    en = sections(en_text)
    cn = sections(cn_text)
    if len(en) != len(cn):
        on_problem("P1 小节数不等：%s 有 %d 节，%s 有 %d 节"
                   % (EN, len(en), CN, len(cn)))
    n = min(len(en), len(cn))
    for i in range(n):
        eh, eb = en[i]
        ch, cb = cn[i]
        em = metrics(eb)
        cm = metrics(cb)
        tag = "第 %d 节（%s / %s）" % (i + 1, eh or "<前言>", ch or "<前言>")
        if em[0] != cm[0]:
            on_problem("P2 %s 表行数不等：EN=%d CN=%d" % (tag, em[0], cm[0]))
        if em[1] != cm[1]:
            on_problem("P2 %s 代码块数不等：EN=%d CN=%d" % (tag, em[1], cm[1]))
        if em[2] != cm[2]:
            on_problem("P2 %s mermaid 图数不等：EN=%d CN=%d" % (tag, em[2], cm[2]))
    return n


def _read(path):
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def on_problem_collector(bucket):
    def _cb(msg):
        bucket.append(msg)
    return _cb


def _selftest():
    """两向自证：坏样本必须红、好样本必须过。

    约定（与 check_help_contract 相同）：expect 的第一个布尔是
    「判据认为有问题」——也就是这道门会变红的那个值，不是「我的断言成立」。
    """
    bad = good = 0
    fails = []

    def expect(tag, detected, want_problem):
        nonlocal bad, good
        ok = (bool(detected) == bool(want_problem))
        print("  [%s] %-52s -> %s%s"
              % ("反例" if want_problem else "正例", tag,
                 "抓到" if detected else "放行",
                 "" if ok else "   *** 不符预期 ***"))
        if not ok:
            fails.append(tag)
        if want_problem:
            bad += 1
        else:
            good += 1

    def problems(en, cn):
        b = []
        compare(en, cn, on_problem_collector(b))
        return b

    base = ("# T\n\n"
            "## A\n| x | y |\n| - | - |\n| 1 | 2 |\n\n"
            "```mermaid\ngraph TD\n```\n\n"
            "## B\n```sh\necho hi\n```\n")
    base_cn = ("# 标题\n\n"
               "## 甲\n| 一 | 二 |\n| - | - |\n| 3 | 4 |\n\n"
               "```mermaid\ngraph TD\n```\n\n"
               "## 乙\n```sh\necho hi\n```\n")

    expect("P1/P2 对等的好样本", bool(problems(base, base_cn)), False)
    expect("P1 中文少一节", bool(problems(base, base_cn.replace("\n## 乙", ""))),
           True)
    expect("P2 中文少一行表",
           bool(problems(base, base_cn.replace("| 3 | 4 |\n", ""))), True)
    expect("P2 中文少一个代码块",
           bool(problems(base, base_cn.replace("```mermaid\ngraph TD\n```\n", ""))),
           True)
    expect("P2 mermaid 数量不等",
           bool(problems(base, base_cn + "\n```mermaid\ngraph LR\n```\n")), True)
    # 行数与内容长度不同**不得**被判为问题（这是刻意不做的判据）
    expect("行数不同但结构对等（放行）",
           bool(problems(base, base_cn + "\n中文补一段更长的说明文字。\n")), False)

    # ---- P4（R61）：质量门表 ↔ 真实护栏清单 ------------------------------
    _tl = ("| Gate | What it stops |\n| --- | --- |\n"
           "| `check_alpha.py` | a |\n| `check_beta.py` | b |\n"
           "| `check_gamma.py` | c |\n")
    _gs = ("check_alpha.py", "check_beta.py", "check_gamma.py")

    def _tbl(en, cn, guards=_gs):
        b = []
        judge_table(en, guards, on_problem_collector(b), "README.md")
        judge_table(cn, guards, on_problem_collector(b), "README_CN.md")
        return b

    expect("P4 表与真实护栏清单一致（放行）", bool(_tbl(_tl, _tl)), False)
    expect("P4 少一行（R56 的现场）",
           bool(_tbl(_tl.replace("| `check_beta.py` | b |\n", ""), _tl)),
           True)
    expect("P4 列了不存在的护栏",
           bool(_tbl(_tl, _tl + "| `check_ghost.py` | g |\n")), True)
    expect("P4 表后有悬空续行",
           bool(_tbl(_tl + " structurally — tail |\n",
                     _tl + " —— 尾巴 |\n")), True)
    expect("P4 重复行",
           bool(_tbl(_tl + "| `check_alpha.py` | a2 |\n", _tl)), True)
    expect("P4 找不到表",
           bool(_tbl("no table here\n", _tl)), True)

    # ---- 真实仓库整体核对 ----
    root = repo_root()
    en_p = os.path.join(root, EN)
    cn_p = os.path.join(root, CN)
    if not (os.path.exists(en_p) and os.path.exists(cn_p)):
        fails.append("真实仓库缺 README")
        bad += 1
    else:
        b = []
        n = compare(_read(en_p), _read(cn_p), on_problem_collector(b))
        _gsr = guard_scripts(root)
        if _gsr is None:
            b.append("P4 缺输入：找不到 tools/check_*.py")
        else:
            judge_table(_read(en_p), _gsr, on_problem_collector(b), EN)
            judge_table(_read(cn_p), _gsr, on_problem_collector(b), CN)
        print("  真实仓库：比对 %d 节，发现 %d 项不对等（含 P4 质量门表核对）"
              % (n, len(b)))
        for p in b[:12]:
            print("      " + p)
        if b:
            fails.append("真实仓库")
            bad += 1
        else:
            good += 1

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    if fails:
        print("SELFTEST FAILED: %s" % fails)
        return 1
    print("SELFTEST PASSED")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()

    root = repo_root()
    en_p = os.path.join(root, EN)
    cn_p = os.path.join(root, CN)
    for p in (en_p, cn_p):
        if not os.path.exists(p):
            print("check_readme_parity: 缺输入 —— 找不到 %s" % p)
            return 2
    probs = []
    n = compare(_read(en_p), _read(cn_p), on_problem_collector(probs))
    if n == 0:
        print("check_readme_parity: 一个可比对的小节都没有（缺输入 → 红）")
        return 2
    guards = guard_scripts(root)
    if guards is None:
        print("check_readme_parity: 缺输入 —— 找不到 tools/check_*.py")
        return 2
    for _label, _p in ((EN, en_p), (CN, cn_p)):
        judge_table(_read(_p), guards, on_problem_collector(probs), _label)
    if probs:
        print("check_readme_parity: %d 项不对等" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_readme_parity: OK（%s 与 %s 的 %d 个小节的"
          "表行/代码块/mermaid 逐节对等；两侧质量门表各 %d 行 == "
          "tools/check_*.py 的真实清单）" % (EN, CN, n, len(guards)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
