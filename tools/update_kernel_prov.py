#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""收口：把当前 `matlabc.py` 的 sha256 / 字节数写回 `docs/KERNEL_RUN.md`。

    python tools/update_kernel_prov.py            # 写回
    python tools/update_kernel_prov.py --dry-run  # 只打印，不落盘

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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="只打印将要写入的值，不改文件")
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
