# -*- coding: utf-8 -*-
"""发布前的架构总闸：快照 + 逐图版本 + PNG/基线 + 评审记录。

为什么单独一个：
    `check_architecture_docs.py` 管“日常一致性”，`check_all.py` 管全仓；
    发布时还需要回答“这个版本的图冻结了吗、评审了吗、PNG 齐了吗”。
    本工具把五件事串成一个退出码，方便放进 release 流程。

用法：
    python tools/release_arch_check.py --check
    python tools/release_arch_check.py --diff            # 自动找上一版本
    python tools/release_arch_check.py --diff 1.16.72
    python tools/release_arch_check.py --diff --fail-on-change
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_arch_versions  # noqa: E402
import export_arch_png  # noqa: E402
import record_arch_review  # noqa: E402
import snapshot_arch  # noqa: E402


def _versions():
    try:
        with io.open(snapshot_arch.OUT, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (IOError, ValueError):
        return []
    out = []
    for s in data.get("snapshots") or []:
        v = s.get("version")
        if v and v != "current":
            out.append(v)
    return out


def _key(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def _prev_version(cur, versions=None):
    versions = versions if versions is not None else _versions()
    cand = [v for v in versions if _key(v) < _key(cur)]
    return max(cand, key=_key) if cand else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="发布前架构总闸")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--diff", nargs="?", const="auto", metavar="PREV",
                    help="比较上一版本与 current；省略 PREV 则自动找")
    ap.add_argument("--fail-on-change", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        cases = [
            (_prev_version("1.16.72", ["1.16.72"]), None),
            (_prev_version("1.16.72", ["1.16.71", "1.16.72"]), "1.16.71"),
            (_prev_version("1.16.10", ["1.16.9", "1.16.10"]), "1.16.9"),
            (_prev_version("1.16.10", ["1.16.8", "1.16.9"]), "1.16.9"),
        ]
        bad = [c for c in cases if c[0] != c[1]]
        for got, want in bad:
            print("  [FAIL] got %r want %r" % (got, want))
        print("release_arch_check selftest: %s（%d 例）"
              % ("OK" if not bad else "FAIL", len(cases)))
        return 0 if not bad else 1
    if args.diff:
        prev = args.diff
        if prev == "auto":
            cur = snapshot_arch._version()
            prev = _prev_version(cur)
            if not prev:
                print("no previous snapshot before %s; skip" % cur)
                return 0
            print("auto previous: %s -> %s" % (prev, cur))
        extra = ["--fail-on-change"] if args.fail_on_change else []
        return snapshot_arch.main(["--diff", prev, "current"] + extra)
    if not args.check:
        ap.print_help()
        return 2
    for name, rc in (
            ("snapshot", snapshot_arch.main(["--check"])),
            ("versions", build_arch_versions.main(["--check"])),
            ("png", export_arch_png.check()),
            ("baseline", export_arch_png.check_baseline()),
            ("review", record_arch_review.main(["--check"]))):
        print("[%s] %s" % ("OK" if rc == 0 else "FAIL", name))
        if rc != 0:
            return rc
    print("release_arch_check: OK（快照/版本/PNG/基线/评审全绿）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
