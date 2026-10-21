# -*- coding: utf-8 -*-
"""从 archify HTML 导出**自足、瘦身**的独立 SVG，并维护哈希清单。

为什么需要它：
    archify 的 HTML 把 286 KB 的页面 CSS（其中绝大部分是 6 个 @font-face 的
    base64）内联在 `<style>` 里。直接把这坨 CSS 塞进 SVG，单张 300 KB+，
    README 加载慢；而只抠 `<svg>` 又会丢样式。本工具只保留：
        - `:root`（CSS 变量）
        - `svg` / `body` / `text`（基础字体与颜色）
        - SVG 里**实际用到**的 class 规则
        - 可选 `--keep-fonts`（默认丢弃，靠系统等宽字体兜底）
    实测单张从 ~300 KB 降到 ~20 KB，Chrome 渲染仍非白。

为什么维护 MANIFEST：
    candidate 改了、HTML 重渲染了、SVG 忘了重导 —— 这三种“看起来都对”的
    陈旧，靠 git diff 看不出来。`svg/MANIFEST.json` 记录三者的 sha256，
    `check_architecture_docs.py` 的 AD5 现算现比。

用法：
    python tools/export_arch_svg.py --all
    python tools/export_arch_svg.py --id 00-overall
    python tools/export_arch_svg.py --check
    python tools/export_arch_svg.py --all --keep-fonts
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCH = os.path.join(ROOT, "docs", "architecture")
INDEX = os.path.join(ARCH, "FLOW_INDEX.json")
MANIFEST = os.path.join(ARCH, "svg", "MANIFEST.json")


def _read(path):
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _write(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _sha256(path):
    h = hashlib.sha256()
    with io.open(path, "rb") as fh:
        while True:
            b = fh.read(65536)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _strip_comments(css):
    return re.sub(r"/\*[\s\S]*?\*/", "", css)


def _top_blocks(css):
    """把 CSS 拆成 [(selector, body)]；嵌套 at-rule 作为整体返回。"""
    out = []
    i = 0
    n = len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        depth = 1
        k = j + 1
        while k < n and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        sel = css[i:j].strip()
        if sel:
            out.append((sel, css[j + 1:k - 1]))
        i = k
    return out


def _filter_css(css, classes, keep_fonts=False):
    css = _strip_comments(css)
    keep = []
    has_svg = False
    for sel, body in _top_blocks(css):
        if sel.startswith("@"):
            if keep_fonts and sel.startswith("@font-face"):
                keep.append("%s{%s}" % (sel, body))
            continue
        parts = [x.strip() for x in sel.split(",")]
        hit = False
        for s in parts:
            if s in (":root", "svg", "text", "body", "html"):
                hit = True
            else:
                for c in classes:
                    if "." + c in s:
                        hit = True
                        break
            if hit:
                break
        if hit:
            if any(x.strip() == "svg" for x in parts):
                has_svg = True
            keep.append("%s{%s}" % (sel, body))
    if not has_svg:
        keep.append("svg{font-family:'JetBrains Mono',ui-monospace,"
                    "Consolas,monospace;background:#fff;}")
    return "\n".join(keep)


def extract_svg(html_path, keep_fonts=False):
    s = _read(html_path)
    blocks = re.findall(r"<svg[\s\S]*?</svg>", s)
    if not blocks:
        return None, 0
    svg = max(blocks, key=len)
    classes = set()
    for m in re.findall(r'class="([^"]+)"', svg):
        classes.update(m.split())
    css = "\n".join(re.findall(r"<style[^>]*>([\s\S]*?)</style>", s))
    filt = _filter_css(css, classes, keep_fonts)
    if "]]>" in filt:
        filt = filt.replace("]]>", "]]]]><![CDATA[>")
    if "xmlns=" not in svg.split(">", 1)[0]:
        svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    if filt:
        m = re.match(r"(<svg[^>]*>)", svg)
        if m:
            svg = (svg[:m.end()] + '<style type="text/css"><![CDATA[\n'
                   + filt + "\n]]></style>" + svg[m.end():])
    return svg, len(filt)


def _load_index():
    with io.open(INDEX, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _item_paths(it):
    iid = it["id"]
    return (os.path.join(ARCH, it["candidate"]),
            os.path.join(ARCH, it["html"]),
            os.path.join(ARCH, "svg", iid + ".svg"))


def export_all(keep_fonts=False, only=None):
    data = _load_index()
    items = data.get("items") or []
    if only:
        items = [x for x in items if x.get("id") == only]
        if not items:
            print("unknown id: %s" % only)
            return 2
    manifest = {"version": 1, "generated": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": "tools/export_arch_svg.py", "items": {}}
    for it in items:
        iid = it["id"]
        cand, html, svg = _item_paths(it)
        if not os.path.isfile(html):
            print("MISSING html: %s" % html)
            return 2
        out, css_len = extract_svg(html, keep_fonts)
        if not out:
            print("NO SVG: %s" % html)
            return 2
        _write(svg, '<?xml version="1.0" encoding="UTF-8"?>\n' + out + "\n")
        manifest["items"][iid] = {
            "candidate_sha256": _sha256(cand),
            "html_sha256": _sha256(html),
            "svg_sha256": _sha256(svg),
            "svg_bytes": os.path.getsize(svg),
        }
        print("%-22s svg=%7d  css=%6d" % (iid, os.path.getsize(svg), css_len))
    if only:
        # 单张模式：与现有清单合并，不丢其他条目
        if os.path.isfile(MANIFEST):
            with io.open(MANIFEST, "r", encoding="utf-8") as fh:
                old = json.load(fh)
            old.setdefault("items", {}).update(manifest["items"])
            manifest = old
            manifest["generated"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write(MANIFEST, json.dumps(manifest, ensure_ascii=False,
                                indent=2, sort_keys=True) + "\n")
    total = sum(v.get("svg_bytes", 0) for v in manifest["items"].values())
    print("MANIFEST %s（%d 条，SVG 合计 %d 字节）"
          % (MANIFEST, len(manifest["items"]), total))
    return 0


def check_manifest():
    if not os.path.isfile(MANIFEST):
        print("缺 %s" % MANIFEST)
        return 2
    with io.open(MANIFEST, "r", encoding="utf-8") as fh:
        man = json.load(fh)
    items = (man.get("items") or {})
    bad = []
    for iid, rec in sorted(items.items()):
        cand = os.path.join(ARCH, "candidates", iid + ".json")
        html = os.path.join(ARCH, "html", iid + ".html")
        svg = os.path.join(ARCH, "svg", iid + ".svg")
        for label, path, key in (("candidate", cand, "candidate_sha256"),
                                 ("html", html, "html_sha256"),
                                 ("svg", svg, "svg_sha256")):
            if not os.path.isfile(path):
                bad.append("%s 缺 %s" % (iid, label))
            elif _sha256(path) != rec.get(key):
                bad.append("%s 的 %s 已变，SVG 清单陈旧" % (iid, label))
    if bad:
        for b in bad:
            print("  - %s" % b)
        return 1
    print("export_arch_svg: OK（%d 条清单与 candidate/html/svg 一致）"
          % len(items))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="导出瘦身 SVG + 哈希清单")
    ap.add_argument("--all", action="store_true", help="导出索引里的全部图")
    ap.add_argument("--id", help="只导出一张")
    ap.add_argument("--keep-fonts", action="store_true",
                    help="保留 @font-face（体积大，但字体完全一致）")
    ap.add_argument("--check", action="store_true", help="只校验清单")
    args = ap.parse_args(argv)
    if args.check:
        return check_manifest()
    if not args.all and not args.id:
        ap.print_help()
        return 2
    return export_all(keep_fonts=args.keep_fonts, only=args.id)


if __name__ == "__main__":
    sys.exit(main())
