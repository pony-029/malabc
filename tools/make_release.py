# -*- coding: utf-8 -*-
"""生成 `releases/README.md` 的版本表。

**为什么需要它**：这张表原先靠手工补行 —— 每次发布要手写版本号、日期、
大小、一句话摘要。手工的东西会漏：`0.6.79` 就曾经只有代码没有表项。

现在从三处事实推导，不靠记忆：
    版本号  <- vscode/package.json
    摘要    <- vscode/CHANGELOG.md 该版本的第一条
    大小/日期 <- releases/vsix/*.vsix 的文件属性（没有包就留 —）

只替换 `## 版本表` 与下一个 `##` 之间的内容，其余文字（说明、约定）保持不动 ——
**脚本不该重写人写的部分**。

用法：
    python tools/make_release.py            # 写回文件
    python tools/make_release.py --dry-run  # 只打印，不改文件
"""
import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PKG = os.path.join(REPO, "vscode", "package.json")
CHANGELOG = os.path.join(REPO, "vscode", "CHANGELOG.md")
TARGET = os.path.join(REPO, "releases", "README.md")
VSIXDIR = os.path.join(REPO, "releases", "vsix")

TITLE = u"## 版本表"
NEXT = u"\n## "


def _first_sentence(s):
    """取第一句。更新日志里的一条常跨多行，直接截 70 字会断在句子中间
    （第一版就是「…第一次较慢，」这种半句话）。"""
    for sep in (u"。", u". "):
        i = s.find(sep)
        if 0 < i <= 70:
            return s[:i + len(sep)].strip()
    return (s[:66] + u"…") if len(s) > 66 else s


def parse_changelog(text):
    """`## 0.6.86` -> 该版本**第一条记录**（含跨行续写）的一句话摘要。"""
    out = {}
    state = {"cur": None, "buf": None}

    def flush():
        cur, buf = state["cur"], state["buf"]
        if cur and buf and not out.get(cur):
            out[cur] = _first_sentence(buf)

    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^##\s+(\d+\.\d+\.\d+)\s*$", s)
        if m:
            flush()                      # 先把上一个版本收尾，否则会丢
            state["cur"] = m.group(1)
            state["buf"] = None
            out.setdefault(state["cur"], u"")
            continue
        cur = state["cur"]
        if cur is None or out.get(cur):
            continue
        if s.startswith(u"- "):
            if state["buf"] is None:
                state["buf"] = s[2:].strip()
            continue
        if s and state["buf"] is not None:
            state["buf"] += s            # 续行：直接拼，中文不需要补空格
    flush()
    return out


def collect_packages():
    """版本 -> (字节数, 日期)。"""
    out = {}
    if not os.path.isdir(VSIXDIR):
        return out
    for fn in os.listdir(VSIXDIR):
        m = re.match(r"^matlabc-(\d+\.\d+\.\d+)\.vsix$", fn)
        if not m:
            continue
        p = os.path.join(VSIXDIR, fn)
        try:
            import time
            st = os.stat(p)
            out[m.group(1)] = (st.st_size,
                               time.strftime("%Y-%m-%d", time.localtime(st.st_mtime)))
        except OSError:
            continue
    return out


def vkey(v):
    return tuple(int(x) for x in v.split("."))


def build_table(versions, summary, pkgs, current):
    rows = [u"| 版本 | 日期 | 大小 | 主要变化 | 文件 |",
            u"| --- | --- | --- | --- | --- |"]
    for v in sorted(versions, key=vkey, reverse=True):
        size, day = pkgs.get(v, (0, u"—"))
        kb = u"%d KB" % round(size / 1024.0) if size else u"—"
        desc = summary.get(v) or u"—"
        # 表格里不能出现裸 `|`
        desc = desc.replace(u"|", u"\\|")
        if len(desc) > 70:
            desc = desc[:69] + u"…"
        vlabel = v + (u"（当前）" if v == current else u"")
        if size:
            link = u"`vsix/matlabc-%s.vsix`" % v
        else:
            link = u"—"
        rows.append(u"| %s | %s | %s | %s | %s |"
                    % (vlabel, day, kb, desc, link))
    return u"\n".join(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印生成的表，不写回文件")
    ap.add_argument("--all", action="store_true",
                    help="连没有离线包的版本也列出来（默认只列能装的）")
    ns = ap.parse_args(argv)

    import json
    pkg = json.load(io.open(PKG, encoding="utf-8"))
    current = pkg.get("version", "")
    summary = parse_changelog(
        io.open(CHANGELOG, encoding="utf-8").read())
    pkgs = collect_packages()

    # **默认只列真的能装的**：这张表的标题是「离线安装包归档」，
    # 一行没有 vsix 的记录对读者毫无用处（第一版把 87 个版本全列了出来，
    # 其中 80 多个指向 `—`）。要看完整历史去 CHANGELOG。
    if ns.all:
        versions = set(summary) | set(pkgs)
    else:
        versions = set(pkgs)
    if current:
        versions.add(current)
    if not versions:
        sys.stderr.write("没有可用的版本信息\n")
        return 2

    table = build_table(versions, summary, pkgs, current)

    if ns.dry_run:
        print(table)
        return 0

    text = io.open(TARGET, encoding="utf-8").read()
    i = text.find(TITLE)
    if i < 0:
        sys.stderr.write("目标文件里找不到 `%s`\n" % TITLE)
        return 2
    j = text.find(NEXT, i + len(TITLE))
    if j < 0:
        j = len(text)
    out = text[:i] + TITLE + u"\n\n" + table + u"\n" + text[j:]
    # **换行必须是 CRLF**（`check_eol_convention` 的 EO1：手写的 .md 一律 CRLF）。
    # 第一版用 \n 写回，直接把整份文件从 CRLF 翻成了 LF，门立刻红 ——
    # 生成器改写别人维护的文件时，格式也得跟着人家的规矩。
    out = out.replace(u"\r\n", u"\n").replace(u"\n", u"\r\n")
    io.open(TARGET, "w", encoding="utf-8", newline="").write(out)
    print(u"已更新 %s（%d 个版本，当前 %s）"
          % (os.path.relpath(TARGET, REPO), len(versions), current))
    return 0


if __name__ == "__main__":
    sys.exit(main())
