#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""登记制护栏：README.md 与 README_CN.md 必须**结构对等**。

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
    1 = 发现不对等（P1/P2 任一红）
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
        print("  真实仓库：比对 %d 节，发现 %d 项不对等" % (n, len(b)))
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
    if probs:
        print("check_readme_parity: %d 项不对等" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_readme_parity: OK（%s 与 %s 的 %d 个小节的"
          "表行/代码块/mermaid 逐节对等）" % (EN, CN, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
