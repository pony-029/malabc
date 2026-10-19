# -*- coding: utf-8 -*-
"""把使用说明（Markdown + 4 张示意图）排成一份 PDF。

为什么要有 PDF：Markdown 里的图在**编辑器的预览里要看一步**（先打开预览），
发给同事时对方也可能没有编辑器。PDF 打开就是最终样子，图直接在页面上。

做法：Markdown -> HTML（python-markdown，带表格/代码块）-> 无头 Edge 打印。
不引第三方排版库：本项目的定位是零依赖，PDF 只是**发布产物**，
生成器允许用本机已有的浏览器。

用法：
    python tools/make_guide_pdf.py
    python tools/make_guide_pdf.py --out some/dir/x.pdf

退出码：
    0  = 生成成功
    1  = 失败（缺 markdown 库 / 缺浏览器 / 打印失败）
"""
import argparse
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GUIDE = os.path.join(ROOT, "vscode", "USER_GUIDE.md")
DEFAULT_OUT = os.path.join(ROOT, "releases", "demo", "matlabc-guide.pdf")

BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)

CSS = u"""
@page { size: A4; margin: 18mm 16mm 16mm 16mm; }
body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
       font-size: 10.5pt; line-height: 1.65; color: #1f2328; }
h1 { font-size: 22pt; margin: 0 0 4pt 0; padding-bottom: 6pt;
     border-bottom: 2px solid #3b8eea; }
h2 { font-size: 15pt; margin: 18pt 0 6pt 0; padding-left: 7pt;
     border-left: 4px solid #3b8eea; page-break-after: avoid; }
h3 { font-size: 12pt; margin: 12pt 0 4pt 0; page-break-after: avoid; }
p { margin: 5pt 0; }
code { font-family: Consolas, monospace; font-size: 9.5pt;
       background: #f2f4f7; padding: 1px 4px; border-radius: 3px; }
pre { background: #f6f8fa; border: 1px solid #e3e7ec; border-radius: 5px;
      padding: 8pt 10pt; font-size: 9pt; line-height: 1.45;
      overflow-x: auto; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0;
        font-size: 9.5pt; page-break-inside: avoid; }
th, td { border: 1px solid #d8dee6; padding: 4pt 6pt; text-align: left;
         vertical-align: top; }
th { background: #eef3fa; font-weight: 600; }
img { max-width: 100%; display: block; margin: 8pt auto;
      border: 1px solid #d8dee6; border-radius: 5px;
      page-break-inside: avoid; }
blockquote { margin: 8pt 0; padding: 6pt 10pt; background: #f6f8fa;
             border-left: 3px solid #b9c2cf; color: #444; }
ul, ol { margin: 5pt 0 5pt 18pt; padding: 0; }
li { margin: 2pt 0; }
em { color: #57606a; }
hr { border: none; border-top: 1px solid #e3e7ec; margin: 12pt 0; }
"""


def find_browser():
    for p in BROWSERS:
        if os.path.isfile(p):
            return p
    return None


def md_to_html(md_text, base_dir):
    try:
        import markdown
    except ImportError:
        return None
    html = markdown.markdown(
        md_text, extensions=["tables", "fenced_code", "sane_lists"])
    # 图片路径 -> file:// 绝对路径（无头打印时相对路径不可靠）
    def fix(m):
        src = m.group(1)
        if src.startswith(("http://", "https://", "file://", "data:")):
            return m.group(0)
        p = os.path.abspath(os.path.join(base_dir, src))
        uri = "file:///" + p.replace("\\", "/")
        return m.group(0).replace(src, uri)

    html = re.sub(r'<img[^>]*src="([^"]+)"', fix, html)
    return html


def build(md_path, out_pdf, browser):
    md_text = io.open(md_path, "r", encoding="utf-8").read()
    body = md_to_html(md_text, os.path.dirname(md_path))
    if body is None:
        print("缺 markdown 库（pip install markdown）")
        return 1
    title = u"matlabc 使用说明"
    doc = (u"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
           u"<title>%s</title><style>%s</style></head><body>%s</body></html>"
           % (title, CSS, body))

    tmp = tempfile.mkdtemp(prefix="guidepdf_")
    html_path = os.path.join(tmp, "guide.html")
    io.open(html_path, "w", encoding="utf-8", newline="").write(doc)

    out_dir = os.path.dirname(os.path.abspath(out_pdf))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    if os.path.isfile(out_pdf):
        os.remove(out_pdf)

    cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--no-pdf-header-footer",
           "--print-to-pdf=" + os.path.abspath(out_pdf),
           "file:///" + html_path.replace("\\", "/")]
    try:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=180)
    except Exception as exc:
        print("调用浏览器失败：%r" % (exc,))
        return 1
    if not os.path.isfile(out_pdf):
        print("打印失败，浏览器输出：")
        print(p.stdout.decode("utf-8", "replace")[-600:])
        return 1
    return 0


def page_count(pdf_path):
    """粗略取页数：数 `/Type /Page`（不是 /Pages）。"""
    try:
        raw = io.open(pdf_path, "rb").read()
    except (IOError, OSError):
        return 0
    return len(re.findall(rb"/Type\s*/Page[^s]", raw))


def image_count(pdf_path):
    try:
        raw = io.open(pdf_path, "rb").read()
    except (IOError, OSError):
        return 0
    return len(re.findall(rb"/Subtype\s*/Image", raw))


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--src", default=GUIDE)
    ns = ap.parse_args(argv)

    if not os.path.isfile(ns.src):
        print("缺输入：%s" % ns.src)
        return 1
    browser = find_browser()
    if not browser:
        print("找不到 Edge/Chrome —— PDF 由无头浏览器打印，需要先装一个")
        return 1
    print("用 %s" % browser)
    rc = build(ns.src, ns.out, browser)
    if rc != 0:
        return rc
    size = os.path.getsize(ns.out)
    pages = page_count(ns.out)
    imgs = image_count(ns.out)
    print("生成 %s（%d 字节，约 %d 页，%d 张图）"
          % (ns.out, size, pages, imgs))
    if pages < 2 or imgs < 4:
        # 页数或图数不对，说明排版/路径出了问题 —— 不能悄悄交付
        print("WARN 页数或图数偏少，检查图片路径与分页")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
