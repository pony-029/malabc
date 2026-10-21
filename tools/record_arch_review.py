# -*- coding: utf-8 -*-
"""记录/校验架构评审行（`docs/architecture/REVIEWS.md`）。

为什么需要它：
    快照回答“图什么时候变”，ADR 回答“为什么变”，但“谁看过、结论是什么”
    没有落点。本工具把评审变成一行可追溯记录，并让发布闸能检查它。

用法：
    python tools/record_arch_review.py --write --reviewer alice \
        --result pass --notes "14 张图复核"
    python tools/record_arch_review.py --check
    python tools/record_arch_review.py --json
"""
import argparse
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCH = os.path.join(ROOT, "docs", "architecture")
DOC = os.path.join(ARCH, "REVIEWS.md")
MATLABC = os.path.join(ROOT, "matlabc.py")
HEADER = "| Version | Date | Diagrams | Reviewer | Result | Notes |"
RESULTS = ("pass", "warn", "fail")


def _version():
    text = io.open(MATLABC, "r", encoding="utf-8", errors="replace").read()
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)', text, re.M)
    return m.group(1) if m else "unknown"


def _rows():
    text = io.open(DOC, "r", encoding="utf-8").read()
    lines = text.splitlines()
    out = []
    in_table = False
    for line in lines:
        if line.strip() == HEADER:
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            if out:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and not set(cells[0]) <= set("- "):
            out.append(cells[:6])
    return out


def _write(rows):
    lines = [
        "# 架构评审记录",
        "",
        "> 每次发布一行：版本 / 日期 / 变更图 / 复核人 / 结论 / 备注。",
        "> `python tools/record_arch_review.py --check` 要求当前版本有评审行；",
        "> `python tools/release_arch_check.py --check` 会一起跑快照/版本/PNG/评审。",
        "",
        HEADER,
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    with io.open(DOC, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="记录/校验架构评审")
    ap.add_argument("--version", default=_version())
    ap.add_argument("--date", default=time.strftime("%Y-%m-%d", time.gmtime()))
    ap.add_argument("--diagrams", default="00-13")
    ap.add_argument("--reviewer", default="")
    ap.add_argument("--result", choices=RESULTS, default="pass")
    ap.add_argument("--notes", default="")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = _rows()
    if args.json:
        print(json.dumps([dict(zip(
            ("version", "date", "diagrams", "reviewer", "result", "notes"),
            r)) for r in rows], ensure_ascii=False, indent=2))
        return 0
    if args.write:
        if not args.reviewer:
            print("--write 需要 --reviewer")
            return 2
        row = [args.version, args.date, args.diagrams, args.reviewer,
               args.result, args.notes or "-"]
        for i, old in enumerate(rows):
            if old[0] == args.version:
                rows[i] = row
                break
        else:
            rows.append(row)
        _write(rows)
        print("wrote %s（%d 行）" % (DOC, len(rows)))
        return 0
    # --check
    cur = [r for r in rows if r[0] == args.version]
    if not cur:
        print("REVIEWS.md 缺当前版本 %s 的评审行" % args.version)
        return 1
    row = cur[-1]
    if row[4] not in RESULTS:
        print("评审结论非法：%r" % row[4])
        return 1
    if not row[3]:
        print("评审行缺 reviewer")
        return 1
    print("record_arch_review: OK（%s · %s · %s）"
          % (row[0], row[4], row[3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
