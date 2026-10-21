# -*- coding: utf-8 -*-
"""对比两个目录下的架构 PNG：缺失/新增/字节变化 + 可选像素差异。

为什么需要它：
    SVG 的视觉可能变了但 canonical SVG 哈希没变（例如外部字体/渲染差异）；
    PNG 是最终位图，适合做发布前的人工评审。本工具零依赖地先比 sha256，
    有 Pillow 时再给像素 bbox / 变化比例；没有 Pillow 也能用。

用法：
    python tools/diff_arch_png.py
    python tools/diff_arch_png.py --base old/png --head docs/architecture/png
    python tools/diff_arch_png.py --base a --head b --json
    python tools/diff_arch_png.py --max-ratio 0.005 --fail-on-change
"""
import argparse
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCH = os.path.join(ROOT, "docs", "architecture")
DEFAULT_BASE = os.path.join(ARCH, "png_baseline")
DEFAULT_HEAD = os.path.join(ARCH, "png")


def _sha(path):
    h = hashlib.sha256()
    with io.open(path, "rb") as fh:
        while True:
            b = fh.read(65536)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _pixel(a, b):
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return {"available": False}
    ia = Image.open(a).convert("RGB")
    ib = Image.open(b).convert("RGB")
    if ia.size != ib.size:
        return {"available": True, "size": [list(ia.size), list(ib.size)]}
    d = ImageChops.difference(ia, ib)
    bbox = d.getbbox()
    hist = d.convert("L").histogram()
    nonzero = sum(hist[1:])
    total = ia.size[0] * ia.size[1]
    return {"available": True, "bbox": list(bbox) if bbox else None,
            "ratio": round(nonzero / float(total), 4) if total else 0.0}


def _files(d):
    out = {}
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".png"):
            out[fn] = os.path.join(d, fn)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="对比架构 PNG")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--head", default=DEFAULT_HEAD)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-on-change", action="store_true")
    ap.add_argument("--max-ratio", type=float, default=0.005,
                    help="同尺寸像素变化比例阈值（默认 0.005）")
    args = ap.parse_args(argv)
    a, b = _files(args.base), _files(args.head)
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    changed = []
    for fn in sorted(set(a) & set(b)):
        if _sha(a[fn]) != _sha(b[fn]):
            info = _pixel(a[fn], b[fn])
            info["file"] = fn
            changed.append(info)
    result = {"base": args.base, "head": args.head,
              "max_ratio": args.max_ratio,
              "added": added, "removed": removed, "changed": changed}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("%s -> %s" % (args.base, args.head))
        for x in added:
            print("  + %s" % x)
        for x in removed:
            print("  - %s" % x)
        for x in changed:
            extra = ""
            if x.get("available"):
                if x.get("size"):
                    extra = " size %s -> %s" % (x["size"][0], x["size"][1])
                else:
                    extra = " bbox=%r ratio=%s (max %s)" % (
                        x.get("bbox"), x.get("ratio"), args.max_ratio)
            print("  ~ %s%s" % (x["file"], extra))
        if not (added or removed or changed):
            print("  0 changes")
    bad = bool(added or removed)
    for x in changed:
        if not x.get("available") or x.get("size") or x.get("ratio") is None:
            bad = True
        elif x["ratio"] > args.max_ratio:
            bad = True
    if args.fail_on_change and bad:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
