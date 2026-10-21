# -*- coding: utf-8 -*-
"""对比同一张架构图的 base/head 两个 candidate，产出 delta HTML + receipt。

为什么需要它：
    改一张架构图时，git diff 只能告诉你 JSON 的哪几行变了；它回答不了
    “版式有没有挪、连线有没有断、角色有没有换”。archify 的 `compare`
    正是为这件事准备的 —— 但它要两个 JSON 文件，而日常场景是
    “HEAD 里的版本 vs 工作区里的版本”。本工具补上这一步。

用法：
    python tools/arch_compare.py --id 00-overall
    python tools/arch_compare.py --id 12-dataflow --rev HEAD~1
    python tools/arch_compare.py --base a.json --head b.json --id 00-overall
    python tools/arch_compare.py --id 00-overall --json

默认产物落在系统临时目录（`arch-delta-<id>.html` + `.receipt.json`），
不污染仓库；要留档时用 `--out docs/architecture/delta/...`。
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCH = os.path.join(ROOT, "docs", "architecture")
INDEX = os.path.join(ARCH, "FLOW_INDEX.json")
ARCHIFY = os.environ.get(
    "ARCHIFY_BIN", r"D:/work/rea/archify/archify/bin/archify.mjs")


def _decode(b):
    return (b or b"").decode("utf-8", "replace")


def _run(cmd, timeout=300, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=timeout)
    return r.returncode, _decode(r.stdout)


def _load_index():
    with io.open(INDEX, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _item(iid):
    for it in _load_index().get("items") or []:
        if it.get("id") == iid:
            return it
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="架构图 base/head 对比")
    ap.add_argument("--id", default="00-overall", help="图 id（默认 00-overall）")
    ap.add_argument("--rev", default="HEAD", help="base 取自哪个 git 版本")
    ap.add_argument("--base", help="直接指定 base candidate")
    ap.add_argument("--head", help="直接指定 head candidate（默认工作区）")
    ap.add_argument("--out", help="delta HTML 输出路径")
    ap.add_argument("--receipt", help="receipt JSON 输出路径")
    ap.add_argument("--json", action="store_true", help="打印 receipt")
    args = ap.parse_args(argv)

    it = _item(args.id)
    if not it:
        print("unknown id: %s" % args.id)
        return 2
    typ = it.get("type") or "architecture"
    if not os.path.isfile(ARCHIFY):
        print("archify 不可用：%s" % ARCHIFY)
        return 2

    base = args.base
    if not base:
        rel = "docs/architecture/candidates/%s.json" % args.id
        rc, out = _run(["git", "show", "%s:%s" % (args.rev, rel)],
                       timeout=30, cwd=ROOT)
        if rc != 0:
            print("git show 失败：%s" % out.strip())
            return 2
        base = os.path.join(tempfile.gettempdir(),
                            "arch-base-%s.json" % args.id)
        with io.open(base, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(out)
    head = args.head or os.path.join(
        ARCH, "candidates", args.id + ".json")
    for label, path in (("base", base), ("head", head)):
        if not os.path.isfile(path):
            print("%s 不存在：%s" % (label, path))
            return 2

    out = args.out or os.path.join(
        tempfile.gettempdir(), "arch-delta-%s.html" % args.id)
    rec = args.receipt or os.path.splitext(out)[0] + ".receipt.json"
    rc, text = _run(["node", ARCHIFY, "compare", typ, base, head, out,
                     "--receipt", rec, "--json"])
    if rc != 0:
        print("archify compare 失败（rc=%d）：\n%s" % (rc, text[-800:]))
        return 1
    if not os.path.isfile(out):
        print("archify compare 没有产出 HTML：%s" % out)
        return 1
    print("delta   %s（%d bytes）" % (out, os.path.getsize(out)))
    print("receipt %s（%d bytes）" % (rec, os.path.getsize(rec)
                                      if os.path.isfile(rec) else 0))
    if args.json and os.path.isfile(rec):
        with io.open(rec, "r", encoding="utf-8") as fh:
            print(fh.read())
    return 0


if __name__ == "__main__":
    sys.exit(main())
