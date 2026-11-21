# -*- coding: utf-8 -*-
"""扫描 `.archify/` 下的图，生成 `flow/diagrams.html` 索引页。

    python tools/diagram_index.py
    python tools/diagram_index.py --selftest

## 为什么需要它（R1036）

`.archify/` 下已有十张图，但**没有任何入口**指向它们：
`flow/index.html` 里倒是有 `archify/...` 的链接，可那个目录早改名为
`.archify/`（加点以被 git 忽略），于是那些链接**全是死链**。

用户问"流程图在哪个页面可以看到" —— 这是个只有人会发现、而没有任何门
能发现的问题：**产出了、但没人找得到**。本工具就是它的对手方。

## 判据

* 索引页只列**真实存在**的 `.html`（死链比没有更糟：点进去是 404）；
* 每张图标注它的类型（从目录名前缀取：architecture/dataflow/...）、
  生成时间（目录名末段时间戳）与**源文件是否入库**；
* `flow/index.html` 里若还留着指向不存在目录的 `archify/` 链接，报出来。

退出码：
    0 = 索引已生成
    1 = 自证失败
    2 = 缺输入（没有 .archify 目录）
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCH = os.path.join(ROOT, ".archify")
OUT = os.path.join(ROOT, "flow", "diagrams.html")

#: 目录名形如 `<type>-<slug>-<YYYYMMDD>-<HHMMSS>`
DIR_RE = re.compile(r"^([a-z]+)-(.+)-(\d{8})-(\d{6})$")

TYPES = {
    "architecture": "架构", "workflow": "流程", "dataflow": "数据流",
    "sequence": "时序", "lifecycle": "状态", "erd": "数据模型",
    "tree": "树", "class": "类图", "timeline": "时间线",
    "waterfall": "耗时",
}


def scan(arch_dir):
    """返回 [{dir, type, slug, stamp, html, has_src, size_kb}]，按时间倒序。"""
    out = []
    if not os.path.isdir(arch_dir):
        return out
    for name in sorted(os.listdir(arch_dir)):
        p = os.path.join(arch_dir, name)
        if not os.path.isdir(p):
            continue
        m = DIR_RE.match(name)
        typ = m.group(1) if m else "?"
        slug = m.group(2) if m else name
        stamp = ("%s-%s" % (m.group(3), m.group(4))) if m else ""
        htmls = [f for f in os.listdir(p) if f.endswith(".html")]
        src = os.path.join(p, "candidate.json")
        for h in htmls:
            out.append({"dir": name, "type": typ, "slug": slug,
                        "stamp": stamp, "html": h,
                        "has_src": os.path.isfile(src),
                        "size_kb": round(os.path.getsize(os.path.join(p, h))
                                         / 1024.0)})
    out.sort(key=lambda x: x["stamp"], reverse=True)
    return out


def _dead_links(index_html):
    """`flow/index.html` 里指向不存在路径的 `archify/...` 链接。"""
    if not os.path.isfile(index_html):
        return []
    txt = io.open(index_html, encoding="utf-8", errors="replace").read()
    bad = []
    for m in re.finditer(r'href="(archify/[^"]+)"', txt):
        href = m.group(1)
        # index.html 在 flow/ 下，相对路径按 flow/ 解析
        target = os.path.join(ROOT, "flow", href.replace("/", os.sep))
        if not os.path.exists(target):
            bad.append(href)
    return bad


def render(items, dead):
    rows = "".join(
        "<tr><td>%s</td><td><a href=\"../.archify/%s/%s\">%s</a></td>"
        "<td class='n'>%d KB</td><td>%s</td></tr>"
        % (TYPES.get(x["type"], x["type"]), x["dir"], x["html"], x["slug"],
           x["size_kb"], "已入库" if x["has_src"] else "**源未入库**")
        for x in items)
    warn = ""
    if dead:
        warn = ("<p class='warn'>flow/index.html 里有 %d 条死链指向 "
                "<code>archify/</code>（该目录已改名为 <code>.archify/</code>）："
                "<code>%s</code></p>" % (len(dead), dead[0]))
    return u"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Malabc 架构图索引</title>
<style>
body{font:14px/1.6 system-ui,"Segoe UI",sans-serif;margin:32px auto;max-width:900px;padding:0 16px;color:#222}
h1{font-size:20px;margin-bottom:4px}
p.note{color:#666;margin-top:0}
table{border-collapse:collapse;width:100%%;margin-top:16px}
th,td{border-bottom:1px solid #e5e5e5;padding:8px 10px;text-align:left}
th{background:#fafafa;font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums}
a{color:#0b6bcb;text-decoration:none}
a:hover{text-decoration:underline}
p.warn{background:#fff4e5;border-left:3px solid #e8a33d;padding:8px 12px}
</style></head><body>
<h1>Malabc 架构图索引</h1>
<p class="note">共 %d 张图。由 <code>tools/diagram_index.py</code> 生成 ——
列的是**真实存在**的文件，没有入口的图等于没做。</p>
%s
<table><tr><th>类型</th><th>图</th><th>大小</th><th>源</th></tr>%s</table>
</body></html>
""" % (len(items), warn, rows)


def _selftest():
    """两向自证：只列真实 html；死链检测要能真抓到。

    只验"能跑"不算自证 —— 一个把目录名当链接输出的实现也能生成页面，
    而那正是现在 index.html 的毛病（死链）。
    """
    good = bad = 0
    import shutil
    import tempfile

    d = tempfile.mkdtemp(prefix="dgi_")
    try:
        # 造两个目录：一个有 html+src，一个只有 src
        a = os.path.join(d, "architecture-demo-20260101-000000")
        b = os.path.join(d, "workflow-nosrc-20260102-000000")
        os.makedirs(a)
        os.makedirs(b)
        io.open(os.path.join(a, "demo.html"), "w").write("x")
        io.open(os.path.join(a, "candidate.json"), "w").write("{}")
        io.open(os.path.join(b, "candidate.json"), "w").write("{}")

        items = scan(d)
        if len(items) == 1:
            good += 1
        else:
            bad += 1
            print("  [selftest] 只该列出 1 个 html，实得 %d" % len(items))

        if items and items[0]["has_src"] is True and items[0]["type"] == "architecture":
            good += 1
        else:
            bad += 1
            print("  [selftest] 类型/源标记不对：%r" % (items[:1],))

        # 死链：造一个 index.html 引用了不存在的 archify/x.html
        idx = os.path.join(d, "index.html")
        io.open(idx, "w", encoding="utf-8").write(
            '<a href="archify/nope/dead.html">dead</a>')
        dead = _dead_links(idx)
        if len(dead) == 1:
            good += 1
        else:
            bad += 1
            print("  [selftest] 死链未抓到：%r" % (dead,))
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return _selftest()
    if not os.path.isdir(ARCH):
        print("diagram_index: 缺输入（没有 .archify 目录）")
        return 2
    items = scan(ARCH)
    if not items:
        print("diagram_index: .archify 下没有已渲染的 .html")
        return 2
    dead = _dead_links(os.path.join(ROOT, "flow", "index.html"))
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(render(items, dead))
    print("[diagrams] %d 张 -> flow/diagrams.html" % len(items))
    for x in items[:6]:
        print("  %-12s %-34s %4d KB%s"
              % (x["type"], x["slug"], x["size_kb"],
                 "" if x["has_src"] else "  (源未入库)"))
    if dead:
        print("  ⚠ flow/index.html 有 %d 条 archify/ 死链" % len(dead))
    return 0


if __name__ == "__main__":
    sys.exit(main())
