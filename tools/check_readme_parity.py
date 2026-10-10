#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""登记制护栏：README.md 与 README_CN.md 必须**结构对等**，且两侧的「质量门表」必须与
`tools/check_*.py` 的真实清单一致（P4），而表里**每一行**又必须与那道门自己声明的
「表行签名」逐字对上（P5）。

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
    P5（R62）表的**内容**也必须与那道门脱不了钩。P4 只证「14 行都在」，不证
       「那一行说的是不是那道门」—— 把一行整段换到另一行上，行的**集合**没变，
       P4 一声不响（R61 §8 C12-1）。于是每道护栏在自己的源码里声明
       `ROW_SIGNATURE`（本门自己的判据族，如 `F1–F6`；或本门独有的机制名，
       如 `NO_HELP_SCRIPTS`），并把它打进**自己的成功行**；P5 要求：
           ① 每道真实护栏都必须声明它（缺 ⇒ 红 —— 那一行就没有对手方）；
           ② 签名要**有信息**（≥3 字符且含数字或下划线，否则该登记不生效）；
           ③ 签名的**锚点**必须在该门源码里出现 —— 签名得指向这道门真的在用的
              判据 / 机制，而不是一个凭空写的字符串；
           ④ 两道门不得共用同一个签名（共用时「换行」同样看不出来）；
           ⑤ 两侧 README 的**对应表行**必须逐字含它。
       P4 把对手方从「另一侧文件」换成了「事实（真实清单）」，P5 再换一次 ——
       换成「**那道门自己**」。

为什么按序号对齐，而不是按标题文本：
    两侧标题本来就不该相同（一侧中文一侧英文）。「第 N 节的骨架必须一样」
    是不依赖翻译质量的、可机械核对的判据。标题文本是否译得对，是人的事。

两向自证：坏样本（中文少一节 / 少一行表 / 少一个代码块 / 表行缺本门签名）必须抓得到；
好样本（两侧对等、表行签名字字对上）必须放行；并对真实仓库做一次整体核对。

用法：
    python tools/check_readme_parity.py             # 0=对等 1=不对等 2=缺输入
    python tools/check_readme_parity.py --selftest   # 两向自证

退出码：
    0 = 两侧结构对等
    1 = 发现不对等 / 质量门表与真实护栏清单不符 / 表行缺本门签名（P1/P2/P4/P5 任一红）
    2 = 缺输入（任一 README 不存在 → 红）
"""
import argparse
import io
import os
import re
import shutil
import sys
import tempfile

# R62/P5：「质量门表」里本门那一行的**签名**（本门自己的判据族，
# 或本门独有的机制名）。它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "P1/P2/P4/P5"

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


# ---------------------------------------------------------------------------
# P5（R62 / R61 §8 C12-1）：质量门表的**内容** ⇄ 那道门自己声明的「表行签名」。
#
# P4 只证「14 行都在」，不证「那一行说的是不是那道门」：把一行整段换到另一行上，
# 行的集合没变，P4 一声不响。P5 把对手方换成**那道门自己** —— 每道护栏在源码里
# 声明 ROW_SIGNATURE，并把它打进自己的成功行；两侧 README 的对应表行必须逐字含它。
# ---------------------------------------------------------------------------
ROW_SIGNATURE_DECL = re.compile(
    r"^[ \t]*ROW_SIGNATURE[ \t]*=[ \t]*([\"'])(.+?)\1[ \t]*$", re.M)


def guard_rows(text):
    """返回 {护栏脚本名: 该表行全文}（只取「质量门表」那个连续表块）。

    与 P4 用同一个表块定位器，但留下**整行文本** —— P5 要比的是行内容。
    """
    lines = text.splitlines()
    got = guard_table(lines)
    if got is None:
        return {}
    start, end, _rows = got
    out = {}
    for k in range(start, end):
        m = GUARD_ROW_RE.match(lines[k].lstrip())
        if m:
            out[m.group(1)] = lines[k].strip()
    return out


def gate_row_signature(root, name):
    """静态读 `tools/<name>` 的 ROW_SIGNATURE；返回 (签名 或 None, 该门源码)。

    刻意**不 import** 那道门（`tools/` 不 import 产品模块，也不互相 import ——
    R52/R54/R55 的纪律），也刻意**不 spawn** 它（否则本门会跑起全套护栏）。
    「门真的把签名打进了成功行」由 `tests/` 的行为判据守着（14 个子进程）。

    ⚠ 返回的源码**已经把声明那一行的字面量抹掉**（`ROW_SIGNATURE =`）：否则
    「锚点必须在源码里出现」会被签名自身满足（`F1` 是 `"F1–F6"` 的子串）——
    这条判据就会退化成**恒真**。这个自伤是 `--selftest` 的 `P5 anchor` 坏样本
    当场抓出来的（它本该红，却放行了）。
    """
    p = os.path.join(root, "tools", name)
    if not os.path.exists(p):
        return None, ""
    src = _read(p)
    m = ROW_SIGNATURE_DECL.search(src)
    if m is None:
        return None, src
    return m.group(2), src.replace(m.group(0), "ROW_SIGNATURE =")


def signature_anchors(sig):
    """签名里必须在**该门源码**中出现的锚点。

    形如 `F1–F6` / `P1/P2/P4/P5` 的判据族 ⇒ 取其中的「大写字母 + 数字」片段
    （F1、F6、P2…）；形如 `_UNIMPLEMENTED_KINDS` / `--check-py36` 的机制名
    ⇒ 取整体。没有锚点检查，签名就只是一个字符串，指不到这道门的任何东西。
    """
    ids = re.findall(r"[A-Z][A-Za-z]*\d+'?", sig)
    return ids if ids else [sig]


def judge_signatures(root, en_text, cn_text, on_problem):
    """P5：表行内容 ⇄ 门。返回核对过的门数。"""
    guards = guard_scripts(root)
    if guards is None:
        on_problem("P5 缺输入：找不到 tools/check_*.py")
        return 0
    if not guards:
        # 与 check_ir_attribution 的「空表是真红」同源：一个都没有 ⇒ 缺输入 → 红，
        # 而不是「没有可检查的对象 ⇒ 放行」。
        on_problem("P5 缺输入：tools/ 下一个 check_*.py 都没有")
        return 0
    en_rows = guard_rows(en_text)
    cn_rows = guard_rows(cn_text)
    seen = {}
    n = 0
    for name in guards:
        sig, src = gate_row_signature(root, name)
        if sig is None:
            on_problem("P5 %s 没有声明 ROW_SIGNATURE —— 它的质量门表那一行"
                       "就没有可逐字核对的对手方" % name)
            continue
        if len(sig) < 3 or not re.search(r"[0-9_]", sig):
            on_problem("P5 %s 的 ROW_SIGNATURE=%r 过短或无信息"
                       "（<3 字符，或不含数字/下划线）⇒ 该登记不生效"
                       % (name, sig))
            continue
        missed = [a for a in signature_anchors(sig) if a not in src]
        if missed:
            on_problem("P5 %s 的 ROW_SIGNATURE=%r 的锚点 %r 在该门源码里找不到"
                       " —— 签名必须指向这道门真的在用的判据 / 机制"
                       % (name, sig, missed))
        if sig in seen:
            on_problem("P5 %s 与 %s 共用同一个签名 %r —— 两道门共用一个签名时，"
                       "把一行的描述换到另一行上同样看不出来"
                       % (seen[sig], name, sig))
        else:
            seen[sig] = name
        for label, rows in ((EN, en_rows), (CN, cn_rows)):
            row = rows.get(name)
            if row is None:
                continue        # 表里根本没有这一行 ⇒ P4 已经点名
            if sig not in row:
                on_problem("P5 %s 里 `%s` 那一行找不到本门的签名 %r —— "
                           "表行的内容与那道门脱了钩（表说 A、门做 B）"
                           % (label, name, sig))
        n += 1
    return n


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

    # ---- P5（R62）：表行内容 ⇄ 门自己声明的 ROW_SIGNATURE ----------------
    # 造一个**真的目录**（P5 要静态读 tools/<门>），门里带 ROW_SIGNATURE。
    _p5tmp = tempfile.mkdtemp(prefix="readme_parity_p5_")
    try:
        def _mkf(root_, rel, body):
            p = os.path.join(root_, rel)
            d = os.path.dirname(p)
            if not os.path.isdir(d):
                os.makedirs(d)
            with io.open(p, "w", encoding="utf-8") as fh:
                fh.write(body)
            return p

        def _gate_body(sig, criteria):
            out = '"""样本门。"""\nimport sys\n\n'
            if sig is not None:
                out += 'ROW_SIGNATURE = "%s"\n\n' % sig
            out += "CRITERIA = %r\n" % (list(criteria),)
            return out

        def _tbl2(rows):
            out = ["| Gate | What it stops |", "| --- | --- |"]
            for nm, desc in rows:
                out.append("| `%s` | %s |" % (nm, desc))
            return "\n".join(out) + "\n"

        SIGS = (("check_alpha.py", "F1–F6"), ("check_beta.py", "S1–S5"),
                ("check_gamma.py", "NO_HELP_SCRIPTS"))

        def _def_gates():
            # criteria 里放签名本身 ⇒ 签名的锚点（F1/F6、S1/S5、整串）都在源码里
            return [(nm, sig, (sig,)) for nm, sig in SIGS]

        def _mkp5(tag, en_rows, cn_rows, gates):
            r = os.path.join(_p5tmp, tag)
            for nm, sig, crit in gates:
                _mkf(r, os.path.join("tools", nm), _gate_body(sig, crit))
            _mkf(r, "README.md", _tbl2(en_rows))
            _mkf(r, "README_CN.md", _tbl2(cn_rows))
            return r

        def _p5(root_, want_problem):
            b = []
            judge_signatures(root_,
                             _read(os.path.join(root_, "README.md")),
                             _read(os.path.join(root_, "README_CN.md")),
                             on_problem_collector(b))
            expect("P5 %s" % os.path.basename(root_), bool(b), want_problem)
            return b

        _good = [(n, "what it stops " + s) for n, s in SIGS]
        _p5(_mkp5("ok", _good, _good, _def_gates()), False)
        # ① 门没声明 ROW_SIGNATURE
        _p5(_mkp5("nodecl", _good, _good,
                  [("check_alpha.py", None, ("F1",))] + _def_gates()[1:]), True)
        # ② README 行里缺本门签名（只缺中文侧）
        _cn_lost = [(n, ("什么也不拦" if n == "check_beta.py" else "拦 " + s))
                    for n, s in SIGS]
        _p5(_mkp5("rowlost", _good, _cn_lost, _def_gates()), True)
        # ③ 签名锚点不在门源码里（签名写 F1–F6，源码只认 Q7）
        _p5(_mkp5("anchor", _good, _good,
                  [("check_alpha.py", "F1–F6", ("Q7",))] + _def_gates()[1:]),
            True)
        # ④ 两道门共用同一个签名
        _p5(_mkp5("dup", _good, _good,
                  [("check_alpha.py", "F1–F6", ("F1–F6",)),
                   ("check_beta.py", "S1–S5", ("S1–S5",)),
                   ("check_gamma.py", "S1–S5", ("S1–S5",))]), True)
        # ⑤ 签名过短 / 无信息
        _p5(_mkp5("thin", _good, _good,
                  [("check_alpha.py", "ab", ("ab",))] + _def_gates()[1:]), True)
        # ⑥ 一个 .py 护栏都没有（缺输入 → 红）
        _p5(_mkp5("empty", _good, _good, []), True)
        # ⑦ 「把一行整段换到另一行上」—— P4 看不见，P5 必须看见
        _swap = [("check_alpha.py", "what it stops NO_HELP_SCRIPTS"),
                 ("check_beta.py", "what it stops S1–S5"),
                 ("check_gamma.py", "what it stops F1–F6")]
        _p5(_mkp5("swap", _swap, _swap, _def_gates()), True)
    finally:
        shutil.rmtree(_p5tmp, ignore_errors=True)

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
        n_sig = 0
        if _gsr is None:
            b.append("P4 缺输入：找不到 tools/check_*.py")
        else:
            judge_table(_read(en_p), _gsr, on_problem_collector(b), EN)
            judge_table(_read(cn_p), _gsr, on_problem_collector(b), CN)
            n_sig = judge_signatures(root, _read(en_p), _read(cn_p),
                                     on_problem_collector(b))
        print("  真实仓库：比对 %d 节，%d 道门的表行签名已核对，发现 %d 项不对等"
              "（含 P4/P5）" % (n, n_sig, len(b)))
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
    n_sig = judge_signatures(root, _read(en_p), _read(cn_p),
                             on_problem_collector(probs))
    if probs:
        print("check_readme_parity: %d 项不对等" % len(probs))
        for p in probs:
            print("  - " + p)
        return 1
    print("check_readme_parity: OK（%s 与 %s 的 %d 个小节的"
          "表行/代码块/mermaid 逐节对等；两侧质量门表各 %d 行 == "
          "tools/check_*.py 的真实清单；表行签名 %s，%d 道门的表行内容"
          "与那道门逐字对上）" % (EN, CN, n, len(guards), ROW_SIGNATURE, n_sig))
    return 0


if __name__ == "__main__":
    sys.exit(main())
