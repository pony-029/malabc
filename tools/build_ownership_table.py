# -*- coding: utf-8 -*-
"""用 `git log -1` 现算架构文档里的「模块归属」表，避免提交号腐烂。

为什么需要它：
    `docs/architecture/README.md` 的「最近提交」是派生量。手写一次就会
    停在那一刻，之后主文件改了、表还是旧的，而没有任何东西在看它。
    本工具把这张表变成可复现产物：`--check` 红了就重跑 `--write`。

用法：
    python tools/build_ownership_table.py --check
    python tools/build_ownership_table.py --write
    python tools/build_ownership_table.py --json
"""
import argparse
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOC = os.path.join(ROOT, "docs", "architecture", "README.md")
ANCHOR = "## 2.5 模块归属"
HEADER = "| 模块 | 主文件 | 最近提交 |"


def _read():
    with io.open(DOC, "r", encoding="utf-8") as fh:
        return fh.read()


def _git_head(files):
    try:
        r = subprocess.run(
            ["git", "log", "-1", "--format=%h %ad", "--date=short",
             "--"] + files,
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "-"
    out = (r.stdout or b"").decode("utf-8", "replace").strip()
    return out or "-"


def _files(cell):
    out = []
    for part in cell.split("·"):
        p = part.strip().strip("`").strip()
        if p:
            out.append(p)
    return out


def _rows(text):
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(ANCHOR):
            start = i
            break
    if start is None:
        return None, lines
    i = start
    while i < len(lines) and not lines[i].startswith(HEADER):
        i += 1
    if i >= len(lines):
        return None, lines
    header_at = i
    i += 2  # header + separator
    rows = []
    body_at = i
    while i < len(lines) and lines[i].startswith("|"):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if len(cells) >= 3:
            rows.append((cells[0], cells[1], cells[2]))
        i += 1
    return {"header_at": header_at, "body_at": body_at,
            "end_at": i, "rows": rows}, lines


def _refresh(rows):
    fresh = []
    for module, files_cell, old in rows:
        files = _files(files_cell)
        stamp = _git_head(files) if files else "-"
        fresh.append((module, files_cell, stamp))
    return fresh


def render():
    text = _read()
    parsed, lines = _rows(text)
    if parsed is None:
        return None, None, None
    fresh = _refresh(parsed["rows"])
    table = [HEADER, "| --- | --- | --- |"]
    for module, files_cell, stamp in fresh:
        href = stamp.split()[0] if stamp != "-" else "-"
        date = stamp.split()[1] if " " in stamp else ""
        table.append("| %s | %s | `%s` %s |"
                     % (module, files_cell, href, date))
    return fresh, parsed, table


def main(argv=None):
    ap = argparse.ArgumentParser(description="刷新模块归属表")
    ap.add_argument("--check", action="store_true", help="只校验是否过期")
    ap.add_argument("--write", action="store_true", help="写回文档")
    ap.add_argument("--json", action="store_true", help="打印现算结果")
    args = ap.parse_args(argv)
    fresh, parsed, table = render()
    if fresh is None:
        print("找不到「%s」表：%s" % (ANCHOR, DOC))
        return 2
    if args.json:
        print(json.dumps([{"module": m, "files": f, "head": h}
                          for m, f, h in fresh],
                         ensure_ascii=False, indent=2))
        return 0
    if args.write:
        text = _read()
        lines = text.splitlines()
        new = (lines[:parsed["header_at"]] + table
               + lines[parsed["end_at"]:])
        with io.open(DOC, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write("\n".join(new) + "\n")
        print("wrote %s（%d 行）" % (DOC, len(fresh)))
        return 0
    # --check：逐行比
    text = _read()
    lines = text.splitlines()
    current = lines[parsed["header_at"]:parsed["end_at"]]
    if current != table:
        stale = []
        for (m, f, h), line in zip(fresh, table):
            if line not in current:
                stale.append("%s -> %s" % (m, h))
        print("归属表已过期（%d 行不一致）：" % len(stale))
        for s in stale[:12]:
            print("  - %s" % s)
        print("重跑：python tools/build_ownership_table.py --write")
        return 1
    print("build_ownership_table: OK（%d 个模块的最近提交与 git log 一致）"
          % len(fresh))
    return 0


if __name__ == "__main__":
    sys.exit(main())
