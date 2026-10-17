#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""收口：把 `matlabc.py` 的 sha256 / 字节数 / 探针时的 HEAD 写回 `docs/KERNEL_RUN.md`。

    python tools/update_kernel_prov.py                     # sha/字节 写回
    python tools/update_kernel_prov.py --dry-run           # 只打印，不落盘
    python tools/update_kernel_prov.py --head <探针日志里的 HEAD>

**为什么需要 `--head`**（R245）：R240 实测到一个真实的「混趟」——
这个工具原来只改 sha 和字节数，**不碰 `provenance.git_head`**。
于是重跑一次探针后，表里 sha 属于新构建、git_head 还留在上一趟，
正是 `check_kernel_snapshot` 文档里点名要防的「一张表混了两趟读数」。
而这类混趟**看不出来**：两行都是合法值，只是来自不同的跑。

**为什么它在 `tools/` 而不是 `C:\temp`**：它是**每次探针收口都要跑**的
第一步（R190 之前的十几轮里，它一直躺在 `C:\temp`）。收口流程本身
不该依赖一份不在仓库里的脚本——否则换台机器就做不了收口。

它**不是护栏**（不以 `check_` 开头，不进 `check_all`），所以由
`check_tool_discoverability.py` 的 TD1/TD2 守着「两侧 README 都提到它」。

退出码：
    0  = 已写回，或本来就已经是最新
    1  = `docs/KERNEL_RUN.md` 里找不到 provenance 行（结构变了 → 红）
    2  = 缺输入（`matlabc.py` 或 `docs/KERNEL_RUN.md` 不在）
"""
import argparse
import hashlib
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MC = os.path.join(ROOT, "matlabc.py")
DOC = os.path.join(ROOT, "docs", "KERNEL_RUN.md")

RE_SHA = r"provenance\.matlabc_sha256 \| ([0-9a-f]{64})"
RE_BYTES = r"provenance\.matlabc_bytes \| (\d+)"
RE_HEAD = r"provenance\.git_head \| ([0-9a-f]{40})"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="只打印将要写入的值，不改文件")
    ap.add_argument("--head", metavar="SHA", default=None,
                    help="探针日志里那行 `HEAD=<sha>` 的 40 位值。"
                         "给了就连 `provenance.git_head` 一起更新；"
                         "不给则只改 sha/字节数（**新跑过探针时必须给**，"
                         "否则表里 sha 与 git_head 来自两趟不同的跑）")
    ap.add_argument("--from-log", dest="from_log", metavar="PATH", default=None,
                    help="直接从探针日志里取 `HEAD=<sha>`，省掉手工复制。"
                         "**并且会核对日志里的 `matlabc=<sha>` 是否等于当前"
                         "文件** —— 不等就拒绝写入（说明这份日志是别的构建"
                         "跑出来的，拿它的 HEAD 配当前的 sha 正好凑出混趟）")
    args = ap.parse_args(argv)

    for p in (MC, DOC):
        if not os.path.isfile(p):
            print("update_kernel_prov: 缺输入（%s）" % p)
            return 2

    with io.open(MC, "rb") as fh:
        cur_sha = hashlib.sha256(fh.read()).hexdigest()
    cur_bytes = os.path.getsize(MC)

    with io.open(DOC, "r", encoding="utf-8", newline="") as fh:
        s = fh.read()

    old_sha = re.search(RE_SHA, s)
    old_bytes = re.search(RE_BYTES, s)
    if old_sha is None or old_bytes is None:
        print("update_kernel_prov: docs/KERNEL_RUN.md 里找不到 provenance 行"
              "（结构变了 → 红）")
        return 1

    print("old_sha   %s" % old_sha.group(1)[:16])
    print("old_bytes %s" % old_bytes.group(1))
    print("new_sha   %s" % cur_sha[:16])
    print("new_bytes %d" % cur_bytes)

    s2 = re.sub(r"(provenance\.matlabc_sha256 \| )[0-9a-f]{64}",
                r"\g<1>" + cur_sha, s)
    s2 = re.sub(r"(provenance\.matlabc_bytes \| )\d+",
                r"\g<1>" + str(cur_bytes), s2)

    head = args.head
    if args.from_log:
        if not os.path.isfile(args.from_log):
            print("update_kernel_prov: 缺输入（探针日志 %s）" % args.from_log)
            return 2
        log = io.open(args.from_log, "r", encoding="utf-8",
                      errors="replace").read()
        mh = re.search(r"HEAD=([0-9a-f]{40})", log)
        ms = re.search(r"matlabc=([0-9a-f]{8,64})", log)
        if mh is None:
            print("update_kernel_prov: 日志里找不到 `HEAD=<sha>`（%s）"
                  % args.from_log)
            return 1
        if ms is not None and not cur_sha.startswith(ms.group(1)):
            print("update_kernel_prov: **拒绝写入** —— 日志里的 "
                  "matlabc=%s 与当前文件 %s 不是同一个构建"
                  % (ms.group(1)[:16], cur_sha[:16]))
            print("  ⇒ 用这份日志的 HEAD 去配当前的 sha，正好凑出"
                  "「一张表混两趟读数」")
            return 1
        head = mh.group(1)
        print("from_log  %s" % args.from_log)
        print("          matlabc=%s（与当前文件一致）"
              % ((ms.group(1)[:16] if ms else "?"),))

    if head:
        if not re.match(r"^[0-9a-f]{40}$", head):
            print("update_kernel_prov: HEAD 不是 40 位 sha（%r）" % (head,))
            return 1
        if re.search(RE_HEAD, s2) is None:
            print("update_kernel_prov: docs/KERNEL_RUN.md 里找不到 "
                  "provenance.git_head 行（结构变了 → 红）")
            return 1
        print("new_head  %s" % head[:16])
        s2 = re.sub(r"(provenance\.git_head \| )[0-9a-f]{40}",
                    r"\g<1>" + head, s2)
    else:
        print("head      （未给 --head / --from-log：git_head 保持不动。"
              "刚跑过探针时必须补上，否则 sha 与 HEAD 来自两趟不同的跑）")

    if s2 == s:
        print("no-change")
        return 0
    if args.dry_run:
        print("would update (dry-run)")
        return 0
    with io.open(DOC, "w", encoding="utf-8", newline="") as fh:
        fh.write(s2)
    print("updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
