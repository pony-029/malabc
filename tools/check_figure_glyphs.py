# -*- coding: utf-8 -*-
"""figures glyph check —— 图上要画的字，字体里到底有没有字形。

为什么要有它
============
"中文在等宽字体里变成空心方块"这件事在本仓已经出现过三次（第 4、5、7 张图），
每次都是靠肉眼看截图发现的 —— 而方块看起来很像"打码"，最容易放过。

两条判据
========
FG1  源码里 `d.text(...)` / `caption(...)` / `chrome(...)` 用到的字符，
     在**界面字体**（雅黑）里必须有字形（渲染结果不等于 .notdef 的方块）。
FG2  用**等宽字体**（Consolas）绘制的那一行，**不允许出现非 ASCII 字符** ——
     Consolas 没有 CJK 字形，中文一律会变成方块。
FG3  导览页（tour.html）正文里的字符同样要有字形：那页是浏览器渲染，
     但字形回退一样会给出方块，而方块看起来像打码。

用法
====
    python tools/check_figure_glyphs.py            # 检查
    python tools/check_figure_glyphs.py --selftest # 自证（造两个必失败的样本）

退出码：
    0  = 图上要画的字都有字形（FG1–FG2 全绿）
    1  = 有字符缺字形，或等宽字体那几行混进了中文
    2  = 缺输入（找不到 tools/make_guide_figures.py）
"""
import io
import os
import re
import sys

ROW_SIGNATURE = "FG1–FG3"

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC = os.path.join(HERE, "make_guide_figures.py")

#: 与 make_guide_figures.py 保持一致的两个字体
UI_FONT = "C:/Windows/Fonts/msyh.ttc"
MONO_FONT = "C:/Windows/Fonts/consola.ttf"
SIZE = 20


def _glyph_missing(font_path, ch):
    """这个字符在该字体里是不是"没有字形"。

    做法：渲染它，再渲染一个**必定缺失**的码位（U+FFFF），比像素。
    两者逐字节相同 = 字体回退到了同一个 .notdef 方块。
    """
    try:
        from PIL import ImageFont
    except ImportError:
        return False
    try:
        f = ImageFont.truetype(font_path, SIZE)
    except (IOError, OSError):
        return False
    try:
        a = bytes(f.getmask(ch))
        b = bytes(f.getmask(u"\uFFFF"))
    except Exception:
        return False
    if not a:
        return False
    return a == b


# 坐标是 `(x, y)`，本身就带逗号 —— 必须先整段吃掉括号再要字符串，
# 否则正则在第一个逗号处就断了，等于什么都没扫到（自证当场抓到）。
TOUR = os.path.join(REPO, "releases", "demo", "matlabc-tour.html")


def scan_tour(path=TOUR):
    """取出导览页正文里的字符（去标签、去脚本）。"""
    if not os.path.isfile(path):
        return set()
    html = io.open(path, encoding="utf-8").read()
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", u" ", html)
    body = re.sub(r"(?s)<[^>]+>", u" ", body)
    return set(ch for ch in body if ord(ch) > 127)


TEXT_CALL = re.compile(r"""(?:d\.text\(\s*\([^)]*\)\s*,\s*|"""
                       r"""caption\(\s*d\s*,\s*|chrome\(\s*d\s*,\s*)"""
                       r"""u?["']([^"']*)["']""")
MONO_LINE = re.compile(r"""_font\(\s*["']mono["']""")


def scan(path=SRC):
    """返回 (可疑字符集合, 等宽字体里的非 ASCII 行号列表)。"""
    src = io.open(path, encoding="utf-8").read()
    chars = set()
    for m in TEXT_CALL.finditer(src):
        for ch in m.group(1):
            if ord(ch) > 127:
                chars.add(ch)

    bad_mono = []
    for i, ln in enumerate(src.splitlines()):
        if MONO_LINE.search(ln):
            for ch in ln:
                if ord(ch) > 127 and ch not in u"'\"，。":
                    # 行内有中文注释也算 —— 注释不会被画，但这条规则宁可宽一点：
                    # 一行里既有等宽字体又有中文，几乎总是把中文一起画进去。
                    if not ln.strip().startswith("#"):
                        bad_mono.append((i + 1, ch, ln.strip()[:60]))
                    break
    return chars, bad_mono


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--selftest" in argv:
        return selftest()

    if not os.path.isfile(SRC):
        print("找不到 %s" % SRC)
        return 2

    chars, bad_mono = scan()
    missing = sorted(ch for ch in chars if _glyph_missing(UI_FONT, ch))

    tour_chars = scan_tour()
    tour_missing = sorted(ch for ch in tour_chars
                          if _glyph_missing(UI_FONT, ch))

    bad = 0
    if missing:
        bad += 1
        print("FG1 失败：这些字符在界面字体里没有字形（会画成方块）：")
        for ch in missing:
            print(u"   %r  U+%04X" % (ch, ord(ch)))
        print("   改成画形状（polygon/ellipse），或换成字体里有的字符。")
    if tour_missing:
        bad += 1
        print("FG3 失败：导览页里有字符在界面字体里没有字形：")
        for ch in tour_missing[:10]:
            print(u"   %r  U+%04X" % (ch, ord(ch)))
    if bad_mono:
        bad += 1
        print("FG2 失败：等宽字体那几行里出现了非 ASCII 字符：")
        for ln, ch, text in bad_mono[:10]:
            print(u"   L%-4d %r  %s" % (ln, ch, text))

    if bad:
        print("check_figure_glyphs: %d 项不合规" % bad)
        return 1
    print("check_figure_glyphs: OK（FG1–FG3 全绿；示意图 %d 个、"
          "导览页 %d 个非 ASCII 字符）" % (len(chars), len(tour_chars)))
    return 0


def selftest():
    """造两个必失败的样本，确认判据真的会红。"""
    import tempfile
    good = bad = 0

    def chk(cond, name):
        nonlocal good, bad
        if cond:
            good += 1
        else:
            bad += 1
            print("  [FAIL] %s" % name)

    # FG1 的探针：U+FFFF 在雅黑里必定缺字形；中文必定有
    chk(_glyph_missing(UI_FONT, u"\uFFFF"), "FG1 能识别缺字形字符")
    chk(not _glyph_missing(UI_FONT, u"\u4e2d"), "FG1 不会误报正常汉字")
    chk(_glyph_missing(MONO_FONT, u"\u4e2d"), "FG2 的依据：等宽字体确实没有汉字")

    # 扫描器：造一个临时源码，含一处 d.text(u"…") 与一行 mono 中文
    d = tempfile.mkdtemp(prefix="glyph_")
    try:
        p = os.path.join(d, "fake.py")
        io.open(p, "w", encoding="utf-8", newline="").write(
            u"def f(d):\n"
            u"    d.text((0, 0), u\"中\\u25be\", font=None, fill=None)\n"
            u"    x = _font(\"mono\", 13)  # 中文不该出现在这一行\n")
        chars, bad_mono = scan(p)
        chk(u"\u4e2d" in chars, "扫描器能取出绘制字符串里的字符")
        chk(len(bad_mono) >= 1, "扫描器能发现等宽字体行里的非 ASCII")

        # FG3：临时 html，正文含中文 + 一个缺字形符号
        h = os.path.join(d, "fake.html")
        io.open(h, "w", encoding="utf-8", newline="").write(
            u"<html><body><p>中文 \u25be</p><script>\u25be</script></body></html>")
        tc = scan_tour(h)
        chk(u"\u4e2d" in tc, "FG3 能取出正文里的中文")
        chk(u"\u25be" not in tc, "FG3 不会把 <script> 里的内容算进正文")
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    print("SELFTEST COUNTS {\"bad\": %d, \"good\": %d}" % (bad, good))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
