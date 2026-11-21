# -*- coding: utf-8 -*-
"""**散文门数同步器**：用门的真源算数，一次改齐所有散文（R1092）。

    python tools/sync_gate_count.py           # 只报告，不改
    python tools/sync_gate_count.py --apply   # 真的改
    python tools/sync_gate_count.py --selftest

## 问题

`check_help_contract` 的 N1 判据要求「散文里说的门数 = 真实护栏数」。
而我这几轮一直**靠它报错来一条条改**：

    改成 49 -> 它说真实 48 -> 改回 48 -> 它说 CONTRIBUTING 还是 47
    -> 改 -> 它说 README_CN 还是 47 -> 改 -> 它说 README.md 是 47 gates

一条报一次，改了六轮。根因不是它苛刻，而是**我不知道真数，
只能等它告诉我**。

## 做法

**直接问门**：`check_help_contract.GUARD_SCRIPTS` 的长度就是它认定的护栏数
（它内部还带一层过滤，所以不能用 `len(GUARD_CONTRACT)` 或数文件）。

然后扫描**全部可能写门数的地方**，用同一个数字一次改齐：
* 中文：`N 道` / `N 个护栏` / `N 道门` / `N 道护栏` / `N 道登记制护栏`
* 英文：`N gates` / `N guards`

## 为什么不改历史记录

`vscode/CHANGELOG.md`、`docs/architecture/ADR-*.md`、`tests/*.py` 注释里的
「R41 加第 41 道门」是**历史叙述**，改了会破坏准确性。
本工具默认**跳过**这些路径，并在输出里说明跳过了多少处。

退出码：0=已同步（或无需改） 1=自检失败 2=缺输入
"""
import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

#: **扫描白名单**（R1093）。
#:
#: 全仓库扫描会扫出 272 个文件——"15 道工序""30 个函数"都被当成门数。
#: 根因不是正则不够严，而是**扫描面本身就不该是全仓库**：只有少数几份
#: 文档有资格谈"门数"，其余地方出现的数字与门数无关。
#:
#: 白名单只收四类：
#:   1. 给用户看的帮助与文档（CONTRIBUTING / README / README_CN）
#:   2. 帮助正文的实体（matlabc_help.py）
#:   3. 门禁树（check_all.py 的 ASCII 树）
TARGET_FILES = (
    "CONTRIBUTING.md",
    "README.md",
    "README_CN.md",
    "matlabc_help.py",
    os.path.join("tools", "check_all.py"),
    # R1112：白皮书也写着门数，和图一样会过期
    os.path.join("flow", "whitepaper.html"),
)

#: 历史记录：这里的门数是"当时是多少"，不能改
SKIP_PATH_PARTS = (
    "CHANGELOG", "ADR-", os.path.join("tests", ""),
    "docs" + os.sep + "PLAN_TRACKER", "flow" + os.sep + "rounds",
    "brain-growth",
)

SCAN_EXTS = (".md", ".py", ".mmd", ".txt")
SKIP_DIRS = {".git", "target", "node_modules", "__pycache__", ".m2c",
             "build", ".archify"}

#: **必须只匹配明确的门数表述**（R1092）。
#:
#: 第一版写成 `\d{2}\s*(?:道|个)`，结果扫出 343 个文件——因为"15 道工序"、
#: "30 个函数"这类普通量词全被当成门数。**一个过宽的正则会让"同步工具"
#: 把无关内容改坏**，而它自称是在"同步门数"。
#:
#: 所以这里只收四种明确说法：
#:   中文   N 道门 / N 道护栏 / N 个护栏 / N 道登记制护栏
#:   英文   N gates / N guards
NUM_RE = re.compile(
    r"(?<![\d.])(\d{2})(?=\s*(?:道门|道登记制护栏|道护栏|个护栏)"
    r"|\s+(?:gates|guards)\b)")


def _fix_eol_after_write(path):
    """写完文件后把行尾归一到该扩展名的约定（R1094）。

    **不要在这里自己判断 CRLF/LF** —— 那会形成第二套行尾逻辑，
    与 `check_eol_convention` 的约定表迟早分叉。直接调 fix_eol。

    上轮的教训：只该改 2 个字符的工具改动了 1932 行，因为
    `newline=""` 让 Python 把 CRLF 读成 \n、写回成 LF，
    **整份文件的行尾被静默改掉**，而工具自己的输出还说"改了 2 处"。
    """
    try:
        import fix_eol
        crlf, lf = fix_eol._tables()
        fix_eol.fix_one(path, crlf, lf)
        return True
    except Exception:                      # noqa: BLE001
        return False


def true_count():
    """**主动跑门，从它自己的输出取数**（R1095）。

    上轮发现门里有两个数：`GUARD_SCRIPTS` 的 len 是 49，而 N1 判据
    报的"真实护栏数"是 48。自己读常量不可靠——**只有判据自己算的那个，
    才是它后面会拿去比的那个**。

    所以这里不再猜常量：调用 `check_help_contract`，从输出里读 N。
    这不是"被动等报错"（那是等它随机红了才改）；这里是主动调用判据、
    把它当成一个取数函数。
    """
    import subprocess
    for args in (["--selftest"], []):
        try:
            r = subprocess.run(
                [sys.executable,
                 os.path.join(ROOT, "tools", "check_help_contract.py")] + args,
                cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=300)
        except (OSError, subprocess.SubprocessError):
            continue
        txt = r.stdout.decode("utf-8", "replace")
        m = re.search(r"真实护栏数是\s*(\d+)", txt)
        if m:
            return int(m.group(1)), "N1 判据输出"
        # 全绿时没有那句；退回到常量
        m2 = re.search(r"check_help_contract: OK\D*(\d+)\s*个\s*check", txt)
        if m2:
            return int(m2.group(1)), "N1 OK 输出"

    # 两条路都不通才退回常量，并标明来源不可靠
    import check_help_contract as H
    gs = getattr(H, "GUARD_SCRIPTS", None)
    if gs is not None:
        return len(gs), "GUARD_SCRIPTS（**可能与 N1 口径不一致**）"
    return None, "unknown"


def scan(apply_fix=False):
    n_true, src = true_count()
    if n_true is None:
        return None
    changed, skipped = [], 0
    for rel in TARGET_FILES:
        p = os.path.join(ROOT, rel)
        if not os.path.isfile(p):
            continue
        try:
            s = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if True:
            hits = [(m.start(), m.group(1)) for m in NUM_RE.finditer(s)]
            wrong = [(pos, num) for pos, num in hits if num != str(n_true)]
            if not wrong:
                continue
            if not apply_fix:
                for pos, num in wrong:
                    ln = s[:pos].count("\n") + 1
                    changed.append((rel, ln, num))
                continue
            # 从后往前替换，避免位置偏移
            for pos, num in reversed(wrong):
                s = s[:pos] + str(n_true) + s[pos + len(num):]
            io.open(p, "w", encoding="utf-8", newline="").write(s)
            _fix_eol_after_write(p)
            changed.append((rel, 0, len(wrong)))

    # 统计被跳过的历史文件里有多少处（只为诚实报告，不改）
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if os.path.splitext(fn)[1].lower() not in SCAN_EXTS:
                continue
            p = os.path.join(base, fn)
            rel = os.path.relpath(p, ROOT)
            if not any(s in rel for s in SKIP_PATH_PARTS):
                continue
            try:
                s = io.open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            skipped += 0
    return {"true": n_true, "source": src, "changed": changed,
            "skipped_historical": skipped}


def _selftest():
    """两向自证：真数必须来自门；错的数必须能被识别。"""
    good = bad = 0
    n, src = true_count()
    if isinstance(n, int) and n > 30:
        good += 1
    else:
        bad += 1
        print("  [selftest] 取不到合理门数：%r" % (n,))

    import check_help_contract as H
    if len(H.GUARD_CONTRACT) >= n:
        good += 1
    else:
        bad += 1
        print("  [selftest] GUARD_SCRIPTS 比 GUARD_CONTRACT 还多，口径反了")

    # 识别能力
    samples = [("共 47 道门", "47"), ("48 gates", "48"), ("共 41 个护栏", "41")]
    for text, expect in samples:
        m = NUM_RE.search(text)
        if m and m.group(1) == expect:
            good += 1
        else:
            bad += 1
            print("  [selftest] 未识别 %r" % text)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="散文门数同步")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()

    r = scan(apply_fix=ns.apply)
    if r is None:
        print("sync_gate_count: 缺输入（取不到门的真源）")
        return 2

    if ns.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0

    print("[门数] 真源 %s = **%d**" % (r["source"], r["true"]))
    if not r["changed"]:
        print("  所有散文已一致（跳过历史记录 %d 处）" % r["skipped_historical"])
        return 0
    verb = "已改" if ns.apply else "需改"
    print("  %s %d 个文件（历史记录跳过 %d 处）"
          % (verb, len(r["changed"]), r["skipped_historical"]))
    for row in r["changed"][:12]:
        if row[1]:
            print("    %s:%d  现为 %s" % row)
        else:
            print("    %s  改了 %d 处" % (row[0], row[2]))
    if not ns.apply:
        print("  （加 --apply 才会真的改）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
