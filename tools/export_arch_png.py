# -*- coding: utf-8 -*-
"""把 14 张架构 SVG 导出为 PNG（汇报/幻灯片场景）。

口径：
    - 尺寸取 SVG 的 `viewBox`，`--force-device-scale-factor=1`，不放大；
    - 输出 `docs/architecture/png/<id>.png`；
    - `--check` 只验 PNG 存在、魔数正确、体积 > 1 KB（CI 无 Chrome 也能跑）；
    - `--all` 需要本机 Chrome/Edge。

用法：
    python tools/export_arch_png.py --all
    python tools/export_arch_png.py --check
    python tools/export_arch_png.py --id 00-overall
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
OUT = os.path.join(ARCH, "png")
CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _chrome():
    env = os.environ.get("CHROME_BIN")
    if env and os.path.isfile(env):
        return env
    for c in CHROME_CANDIDATES:
        if os.path.isfile(c):
            return c
    return None


def _items():
    with io.open(INDEX, "r", encoding="utf-8") as fh:
        return json.load(fh).get("items") or []


def _viewbox(svg_path):
    with io.open(svg_path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', text)
    if not m:
        return None
    return int(float(m.group(1))), int(float(m.group(2)))


def _write_one(chrome, iid, svg):
    size = _viewbox(svg)
    if not size:
        print("NO_VIEWBOX %s" % iid)
        return 1
    w, h = size
    out = os.path.join(OUT, iid + ".png")
    url = "file:///" + svg.replace("\\", "/")
    r = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--force-device-scale-factor=1",
         "--screenshot=" + out, "--window-size=%d,%d" % (w, h), url],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=120)
    if r.returncode != 0 or not os.path.isfile(out):
        print("FAIL %s rc=%s" % (iid, r.returncode))
        return 1
    print("%-22s %dx%d  %7d bytes" % (iid, w, h, os.path.getsize(out)))
    return 0


def build(only=None):
    chrome = _chrome()
    if not chrome:
        print("找不到 Chrome/Edge；设置 CHROME_BIN 或只跑 --check")
        return 2
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    items = _items()
    if only:
        items = [x for x in items if x.get("id") == only]
        if not items:
            print("unknown id: %s" % only)
            return 2
    for it in items:
        iid = it["id"]
        svg = os.path.join(ARCH, "svg", iid + ".svg")
        if not os.path.isfile(svg):
            print("MISSING %s" % svg)
            continue
        _write_one(chrome, iid, svg)
    return 0


def check():
    bad = []
    items = _items()
    for it in items:
        iid = it["id"]
        path = os.path.join(OUT, iid + ".png")
        if not os.path.isfile(path):
            bad.append("%s 缺 PNG" % iid)
            continue
        with io.open(path, "rb") as fh:
            head = fh.read(8)
        if head != PNG_MAGIC or os.path.getsize(path) < 1024:
            bad.append("%s 不是有效 PNG 或体积过小" % iid)
    if bad:
        for b in bad:
            print("  - %s" % b)
        return 1
    print("export_arch_png: OK（%d 张 PNG 存在且魔数正确）" % len(items))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="导出架构 PNG")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--id")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.check:
        return check()
    if not args.all and not args.id:
        ap.print_help()
        return 2
    return build(only=args.id)


if __name__ == "__main__":
    sys.exit(main())
