# -*- coding: utf-8 -*-
"""构建 14 张英文版架构 SVG（candidate 在 docs/architecture/en/candidates/）。

为什么只提交 SVG、不提交英文 HTML：
    英文 HTML 与中文 HTML 是同一套渲染器的两份产物，各约 700 KB；
    全量提交会把 10 MB 的 HTML 再翻一倍。README 需要的是**矢量图**，
    交互阅读仍走中文 `docs/architecture/index.html`。因此本工具把
    archify 渲染到临时目录，只把裁剪后的 SVG 落到 `en/svg/`。

用法：
    python tools/build_arch_svg_en.py
    python tools/build_arch_svg_en.py --only 00-overall
    python tools/build_arch_svg_en.py --check
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCH = os.path.join(ROOT, "docs", "architecture")
EN = os.path.join(ARCH, "en")
CAND = os.path.join(EN, "candidates")
SVG = os.path.join(EN, "svg")
INDEX = os.path.join(ARCH, "FLOW_INDEX.json")
ARCHIFY = os.environ.get("ARCHIFY_BIN",
                         r"D:/work/rea/archify/archify/bin/archify.mjs")

sys.path.insert(0, HERE)
from export_arch_svg import extract_svg  # noqa: E402


def _types():
    with io.open(INDEX, encoding="utf-8") as fh:
        data = json.load(fh)
    return dict((x["id"], x["type"]) for x in data.get("items") or [])


def _quality(iid):
    return "standard" if iid in ("12-dataflow", "13-sequence") else "showcase"


def build(only=None):
    types = _types()
    if not os.path.isdir(SVG):
        os.makedirs(SVG)
    ids = sorted(types)
    if only:
        ids = [x for x in ids if x == only]
        if not ids:
            print("unknown id: %s" % only)
            return 2
    for iid in ids:
        cand = os.path.join(CAND, iid + ".json")
        if not os.path.isfile(cand):
            print("MISSING %s" % cand)
            continue
        typ, q = types[iid], _quality(iid)
        v = subprocess.run(
            ["node", ARCHIFY, "validate", typ, cand, "--quality", q],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True, timeout=180)
        if v.returncode != 0:
            print("VALIDATE_FAIL %s %s" % (iid, (v.stdout or "")[-300:]))
            continue
        html = os.path.join(tempfile.gettempdir(), iid + ".en.html")
        r = subprocess.run(
            ["node", ARCHIFY, "render", typ, cand, html, "--quality", q],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True, timeout=300)
        if r.returncode != 0:
            print("RENDER_FAIL %s %s" % (iid, (r.stdout or "")[-300:]))
            continue
        svg, css_len = extract_svg(html, keep_fonts=False)
        if not svg:
            print("NO_SVG %s" % iid)
            continue
        out = os.path.join(SVG, iid + ".svg")
        with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write('<?xml version="1.0" encoding="UTF-8"?>\n' + svg + "\n")
        print("%-22s svg=%7d css=%5d" % (iid, os.path.getsize(out), css_len))
    return 0


def check():
    types = _types()
    bad = []
    for iid in sorted(types):
        path = os.path.join(SVG, iid + ".svg")
        if not os.path.isfile(path):
            bad.append("%s 缺 SVG" % iid)
            continue
        try:
            ET.fromstring(io.open(path, "rb").read())
        except ET.ParseError as e:
            bad.append("%s SVG 不是合法 XML：%s" % (iid, e))
    if bad:
        for b in bad:
            print("  - %s" % b)
        return 1
    print("build_arch_svg_en: OK（%d 张英文 SVG 存在且 XML 合法）"
          % len(types))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="构建英文版架构 SVG")
    ap.add_argument("--only", help="只构建一张")
    ap.add_argument("--check", action="store_true", help="只校验产物")
    args = ap.parse_args(argv)
    if args.check:
        return check()
    return build(only=args.only)


if __name__ == "__main__":
    sys.exit(main())
