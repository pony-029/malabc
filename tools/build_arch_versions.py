# -*- coding: utf-8 -*-
"""给每张架构图记录 `since` / `changed_in`，并生成 `VERSIONS.md`。

口径：
    - `since`      = 该 candidate 第一次出现在 git 历史里的提交；
    - `changed_in` = 最近一次改该 candidate 的提交；
    - 版本号        = `matlabc.py` 的 `VERSION`（与 SNAPSHOTS 对齐）。

为什么不用手写：
    14 张图的“首次/最近”是派生量；手写一次就会停在那一刻。
    `--check` 红了就重跑 `--write`；CI 会跑 `--check`。

用法：
    python tools/build_arch_versions.py --write
    python tools/build_arch_versions.py --check
    python tools/build_arch_versions.py --json
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCH = os.path.join(ROOT, "docs", "architecture")
INDEX = os.path.join(ARCH, "FLOW_INDEX.json")
OUT = os.path.join(ARCH, "VERSIONS.md")
MATLABC = os.path.join(ROOT, "matlabc.py")


def _version():
    text = io.open(MATLABC, "r", encoding="utf-8", errors="replace").read()
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)', text, re.M)
    return m.group(1) if m else "unknown"


def _history(rel):
    try:
        r = subprocess.run(
            ["git", "log", "--follow", "--format=%h %ad", "--date=short",
             "--reverse", "--", rel],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "-", "-"
    lines = (r.stdout or b"").decode("utf-8", "replace").splitlines()
    lines = [x.strip() for x in lines if x.strip()]
    if not lines:
        return "-", "-"
    return lines[0], lines[-1]


def _load():
    with io.open(INDEX, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _expected(data):
    ver = _version()
    out = []
    for it in data.get("items") or []:
        cand = it.get("candidate") or ""
        since, changed = _history("docs/architecture/" + cand)
        out.append({
            "id": it.get("id"),
            "title": it.get("title"),
            "since": since,
            "changed_in": changed,
            "version": ver,
        })
    return out


def _markdown(rows):
    lines = [
        "# 架构图版本记录（自动生成）",
        "",
        "> 由 `python tools/build_arch_versions.py` 从 `git log` 现算；不要手改。",
        "> 版本号来自 `matlabc.py` 的 `VERSION`，与 `SNAPSHOTS.json` 对齐。",
        "",
        "| # | 图 | 首次 | 最近 | 当前版本 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append("| %s | %s | `%s` | `%s` | %s |"
                     % (r["id"], r["title"], r["since"], r["changed_in"],
                        r["version"]))
    lines += [
        "",
        "## 怎么读",
        "",
        "- `since` 是图第一次出现的提交，`changed_in` 是最近一次改图的提交；",
        "  两者相同表示这张图从加入后没再改过。",
        "- 发布时 `SNAPSHOTS.json` 冻结该版本的三个哈希；`VERSIONS.md` 记录",
        "  “哪张图在哪个提交进入/变更”，两者互补。",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="架构图版本记录")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    data = _load()
    rows = _expected(data)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if args.write:
        for it in data.get("items") or []:
            row = [r for r in rows if r["id"] == it.get("id")][0]
            it["since"] = row["since"]
            it["changed_in"] = row["changed_in"]
        with io.open(INDEX, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        with io.open(OUT, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write(_markdown(rows))
        print("wrote %s 与 %s（%d 张图）" % (INDEX, OUT, len(rows)))
        return 0
    # --check：字段 + Markdown 两向
    bad = []
    for it in data.get("items") or []:
        row = [r for r in rows if r["id"] == it.get("id")][0]
        for key in ("since", "changed_in"):
            if it.get(key) != row[key]:
                bad.append("%s 的 %s：%r != %r"
                           % (it.get("id"), key, it.get(key), row[key]))
    cur = ""
    if os.path.isfile(OUT):
        with io.open(OUT, "r", encoding="utf-8") as fh:
            cur = fh.read()
    if cur != _markdown(rows):
        bad.append("VERSIONS.md 与 git log 不一致")
    if bad:
        for b in bad[:12]:
            print("  - %s" % b)
        print("重跑：python tools/build_arch_versions.py --write")
        return 1
    print("build_arch_versions: OK（%d 张图的 since/changed_in 与 git log 一致）"
          % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
