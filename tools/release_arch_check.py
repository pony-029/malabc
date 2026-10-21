# -*- coding: utf-8 -*-
"""发布前的架构总闸：快照 + 逐图版本 + PNG + 评审记录。

为什么单独一个：
    `check_architecture_docs.py` 管“日常一致性”，`check_all.py` 管全仓；
    发布时还需要回答“这个版本的图冻结了吗、评审了吗、PNG 齐了吗”。
    本工具把四件事串成一个退出码，方便放进 release 流程。

用法：
    python tools/release_arch_check.py --check
    python tools/release_arch_check.py --diff 1.16.72
    python tools/release_arch_check.py --diff 1.16.72 --fail-on-change
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_arch_versions  # noqa: E402
import export_arch_png  # noqa: E402
import record_arch_review  # noqa: E402
import snapshot_arch  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="发布前架构总闸")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--diff", metavar="PREV",
                    help="比较上一个版本与 current")
    ap.add_argument("--fail-on-change", action="store_true")
    args = ap.parse_args(argv)
    if args.diff:
        extra = ["--fail-on-change"] if args.fail_on_change else []
        return snapshot_arch.main(["--diff", args.diff, "current"] + extra)
    if not args.check:
        ap.print_help()
        return 2
    for name, rc in (
            ("snapshot", snapshot_arch.main(["--check"])),
            ("versions", build_arch_versions.main(["--check"])),
            ("png", export_arch_png.check()),
            ("review", record_arch_review.main(["--check"]))):
        print("[%s] %s" % ("OK" if rc == 0 else "FAIL", name))
        if rc != 0:
            return rc
    print("release_arch_check: OK（快照/版本/PNG/评审全绿）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
