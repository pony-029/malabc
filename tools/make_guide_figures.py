# -*- coding: utf-8 -*-
"""生成使用说明里的 4 张示意图。

它们是**按真实界面绘制的示意画面**，不是屏幕截图 —— 手册里也是这么标注的。
为什么不用截屏：截屏会随主题、字号、系统字体漂移，而说明书需要一套稳定的、
跨版本看起来一样的图；另外截屏里难免带上作者自己的工程名与路径。

产物：`releases/docs/figures/*.png`（手册与图放在同一目录；打包时映射到
`extension/figures/`，手册里的相对路径 `figures/x.png` 因此仍然成立）。

用法：
    python tools/make_guide_figures.py
    python tools/make_guide_figures.py --out some/dir

退出码：
    0  = 4 张都生成
    1  = 缺字体（需要微软雅黑 / Consolas）或写盘失败
"""
import argparse
import io
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(ROOT, "releases", "docs", "figures")

W, H = 900, 520
BG = (30, 30, 30)
PANEL = (37, 37, 38)
SIDE = (37, 37, 38)
BORDER = (60, 60, 60)
TEXT = (212, 212, 212)
DIM = (150, 156, 165)
ACCENT = (59, 142, 234)
GREEN = (106, 153, 85)
ORANGE = (206, 145, 120)
BLUE = (86, 156, 214)
YELLOW = (220, 220, 170)
PURPLE = (197, 134, 192)
WHITE = (240, 240, 240)

FONT_PATHS = {
    "ui": r"C:\Windows\Fonts\msyh.ttc",
    "ui_bold": r"C:\Windows\Fonts\msyhbd.ttc",
    "mono": r"C:\Windows\Fonts\consola.ttf",
}


def _has_cjk(text):
    """这段文字里有没有中日韩字符。

    Consolas 没有 CJK 字形 —— 用它渲染中文会出**方块**（第一版就是这样，
    `% 求解器入口` 变成了四个空心方框）。代码用等宽、中文用雅黑，
    混排时按字符段切换字体。
    """
    for ch in text:
        if u"\u4e00" <= ch <= u"\u9fff":
            return True
    return False


def _font(kind, size):
    p = FONT_PATHS.get(kind) or FONT_PATHS["ui"]
    if not os.path.isfile(p):
        raise IOError("缺字体：%s" % p)
    return ImageFont.truetype(p, size)


def round_rect(d, box, radius, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline,
                        width=width)


def chrome(d, title, h=None):
    """窗口外框 + 标题栏。"""
    d.rectangle([0, 0, W, h or H], fill=BG)
    d.rectangle([0, 0, W, 34], fill=(50, 50, 50))
    f = _font("ui", 14)
    d.text((16, 9), title, font=f, fill=(200, 200, 200))
    # 三个圆点
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([W - 90 + i * 26, 12, W - 80 + i * 26, 22], fill=c)


def code_line(d, x, y, text, f, lineno=None, fnum=None):
    """画一行代码：注释/字符串/关键字上色，函数名用黄色。"""
    if lineno is not None:
        d.text((x, y), str(lineno), font=fnum, fill=(110, 110, 110))
    cx = x + 34
    if not text.strip():
        return
    # 注释
    if "%" in text:
        code, _, cmt = text.partition("%")
        d.text((cx, y), code, font=f, fill=TEXT)
        w = d.textlength(code, font=f)
        cf = _font("ui", 13) if _has_cjk(cmt) else f
        d.text((cx + w, y), "%" + cmt, font=cf, fill=GREEN)
        return
    # 关键字 + 其余（够用即可，不追求完整高亮）
    kw = re.match(r"(\s*)(function|end|if|else|for|while|switch|case|return|"
                  r"global)(\b.*)$", text)
    if kw:
        d.text((cx, y), kw.group(1), font=f, fill=TEXT)
        w1 = d.textlength(kw.group(1), font=f)
        d.text((cx + w1, y), kw.group(2), font=f, fill=BLUE)
        w2 = d.textlength(kw.group(2), font=f)
        rest = kw.group(3)
        # 函数名（= 后面、括号前）
        m = re.search(r"=\s*([A-Za-z_]\w*)", rest)
        if m:
            before = rest[:m.start(1)]
            d.text((cx + w1 + w2, y), before, font=f, fill=TEXT)
            wx = cx + w1 + w2 + d.textlength(before, font=f)
            d.text((wx, y), m.group(1), font=f, fill=YELLOW)
            w3 = d.textlength(m.group(1), font=f)
            d.text((wx + w3, y), rest[m.end(1):], font=f, fill=TEXT)
        else:
            d.text((cx + w1 + w2, y), rest, font=f, fill=TEXT)
        return
    d.text((cx, y), text, font=f, fill=TEXT)


def editor_panel(d, x0, y0, x1, y1, fname, lines, tab_w=170):
    d.rectangle([x0, y0, x1, y1], fill=PANEL)
    # 标签页
    d.rectangle([x0, y0, x0 + tab_w, y0 + 30], fill=BG)
    d.text((x0 + 12, y0 + 7), fname, font=_font("ui", 13), fill=(220, 220, 220))
    d.line([x0, y0 + 30, x1, y0 + 30], fill=BORDER)
    f = _font("mono", 14)
    fnum = _font("mono", 12)
    y = y0 + 44
    for i, ln in enumerate(lines):
        code_line(d, x0 + 6, y, ln, f, lineno=i + 1, fnum=fnum)
        y += 20


def caption(d, text, h=None):
    h = h or H
    f = _font("ui", 13)
    d.rectangle([0, h - 30, W, h], fill=(24, 24, 24))
    d.text((16, h - 24), text, font=f, fill=(160, 166, 176))


# ---------------------------------------------------------------------------
# 图 1：关系面板
# ---------------------------------------------------------------------------

def fig_relations(path):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    chrome(d, "matlabc — 关系面板")
    split = 600
    editor_panel(d, 0, 34, split, H - 30, "solver.m", [
        u"function y = solver(f, h, opts)",
        u"% 求解器入口",
        u"opts = sdpsettings(opts);",
        u"[y, info] = iterate(f, h, opts);",
        u"end",
    ])
    # 侧栏
    d.rectangle([split, 34, W, H - 30], fill=SIDE)
    d.line([split, 34, split, H - 30], fill=BORDER)
    fs = _font("ui", 14)
    fsm = _font("ui", 13)
    d.text((split + 16, 44), u"关系 — iterate", font=_font("ui_bold", 14),
           fill=WHITE)
    y = 76
    # 三角用多边形画：字体里没有 ▾/▸ 字形（第一版渲染成了空心方框）。
    rows = [
        (u"上游（2）", u"open", ACCENT),
        (u"solver.m:4", u"", TEXT),
        (u"run_all.m:11", u"", TEXT),
        (u"下游（3）", u"open", ACCENT),
        (u"step.m:1", u"", TEXT),
        (u"residual.m:1", u"", TEXT),
        (u"c_kernel（跨语言）", u"", ORANGE),
        (u"字段读写（5）", u"closed", DIM),
    ]
    for txt, kind, col in rows:
        if kind:
            cx0, cy0 = split + 16, y + 6
            if kind == u"open":
                d.polygon([(cx0, cy0), (cx0 + 8, cy0), (cx0 + 4, cy0 + 6)],
                          fill=col)
            else:
                d.polygon([(cx0, cy0 - 1), (cx0 + 6, cy0 + 3),
                           (cx0, cy0 + 7)], fill=col)
            d.text((split + 30, y), txt, font=fsm, fill=col)
        else:
            d.text((split + 30, y), txt, font=fsm, fill=col)
        y += 24
    # 底部提示
    d.rectangle([split + 12, H - 76, W - 12, H - 42], fill=(45, 45, 48))
    d.text((split + 20, H - 70), u"跨语言：c_kernel 在 impl.c:12",
           font=_font("ui", 12), fill=ORANGE)
    caption(d, u"示意图 · 光标停在函数名上，右侧面板给出上游 / 下游 / 字段读写")
    im.save(path)


# ---------------------------------------------------------------------------
# 图 2：CodeLens 与跳转
# ---------------------------------------------------------------------------

def fig_codelens(path):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    chrome(d, "matlabc — CodeLens 与转到定义")
    d.rectangle([0, 34, W, H - 30], fill=PANEL)
    d.rectangle([0, 34, 190, 64], fill=BG)
    d.text((12, 41), "caller.m", font=_font("ui", 13), fill=(220, 220, 220))
    d.line([0, 64, W, 64], fill=BORDER)

    f = _font("mono", 14)
    fnum = _font("mono", 12)
    lines = [
        u"function y = caller(v)",
        u"  a = prepare(v);",
        u"  y = solve_it(a);",
        u"end",
    ]
    y = 72
    for i, ln in enumerate(lines):
        if i == 2:
            # CodeLens 行
            d.text((6 + 34, y), u"3 个调用者 · 复杂度 4 · 被 2 个文件引用",
                   font=_font("ui", 12), fill=(150, 190, 240))
            y += 20
        code_line(d, 6, y, ln, f, lineno=i + 1, fnum=fnum)
        y += 21

    # 跳转提示
    box = [470, 150, 860, 250]
    round_rect(d, box, 8, fill=(45, 45, 48), outline=BORDER)
    d.text((490, 164), u"F12  →  solve_it.m", font=_font("ui_bold", 14),
           fill=WHITE)
    d.text((490, 190), u"function y = solve_it(a)", font=_font("mono", 13),
           fill=TEXT)
    d.text((490, 212), u"  y = iterate(a);", font=_font("mono", 13), fill=TEXT)
    d.text((490, 232), u"% 就地预览：Alt+F12 不用离开当前文件",
           font=_font("ui", 12), fill=DIM)
    caption(d, u"示意图 · 函数上方那行「N 个调用者」是本扩展加的（CodeLens）")
    im.save(path)


# ---------------------------------------------------------------------------
# 图 3：热点排行
# ---------------------------------------------------------------------------

def fig_heat(path):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    chrome(d, "matlabc — 热点函数排行")
    d.rectangle([0, 34, W, H - 30], fill=(38, 38, 40))
    d.text((20, 46), u"按「复杂度 × 调用者数」排序", font=_font("ui", 13),
           fill=DIM)

    f = _font("mono", 14)
    rows = [
        (u"solve_it", u"solver.m:12", u"复杂度 18 · 调用者 7", u"96"),
        (u"iterate", u"solver.m:40", u"复杂度 12 · 调用者 5", u"61"),
        (u"residual", u"step.m:3", u"复杂度 9 · 调用者 4", u"37"),
        (u"prepare", u"caller.m:8", u"复杂度 6 · 调用者 3", u"19"),
        (u"report", u"io.m:21", u"复杂度 4 · 调用者 1", u"5"),
    ]
    y = 84
    for name, loc, meta, score in rows:
        d.rectangle([14, y - 6, W - 14, y + 40], fill=(45, 45, 48))
        d.text((28, y), name, font=_font("mono", 15), fill=YELLOW)
        d.text((28, y + 20), loc, font=_font("mono", 12), fill=DIM)
        d.text((330, y + 4), meta, font=_font("ui", 13), fill=TEXT)
        d.text((W - 90, y + 2), score, font=_font("ui_bold", 16), fill=ACCENT)
        y += 56
    caption(d, u"示意图 · 选中即跳转；「（当前目录）」只在本目录内排序")
    im.save(path)


# ---------------------------------------------------------------------------
# 图 4：命令面板
# ---------------------------------------------------------------------------

def fig_commands(path):
    # 19 条命令需要比默认画布更高的区域（多出来的那几行曾落在框外）
    HH = 628
    im = Image.new("RGB", (W, HH), BG)
    d = ImageDraw.Draw(im)
    chrome(d, "matlabc — 命令面板", HH)
    d.rectangle([0, 34, W, HH - 30], fill=(37, 37, 38))

    box = [60, 50, W - 60, 578]
    round_rect(d, box, 6, fill=(45, 45, 48), outline=BORDER)
    d.text((80, 76), u"matlabc", font=_font("mono", 15), fill=WHITE)
    d.line([74, 106, W - 74, 106], fill=BORDER)

    # **必须列全 9 条**：图上写"共 9 条"却只画 7 条，读者会去数。
    cmds = [
        (u"matlabc: 打开使用说明", u"完整手册（离线）"),
        (u"matlabc: 打开使用说明（PDF）", u"图在页面上"),
        (u"matlabc: 选择 Python 解释器", u"启动失败先试它"),
        (u"matlabc: 重新启动服务", u"索引卡住时用"),
        (u"matlabc: 撤销上一次改动", u"改完能反悔"),
        (u"matlabc: 查看最近的提交", u""),
        (u"matlabc: 确认撤销", u"diff 里的按钮"),
        (u"matlabc: 撤销这一次改动", u"记录视图里用"),
        (u"matlabc: 查看这一次改了什么", u""),
        (u"matlabc: 复制记录 id", u""),
        (u"matlabc: 按 id 撤销改动", u"粘贴 id"),
        (u"matlabc: 改动记录按耗时排序", u"看分布"),
        (u"matlabc: 按文件过滤改动记录", u"只看某个文件"),
        (u"matlabc: 清除改动记录过滤", u""),
        (u"matlabc: 查看日志", u""),
        (u"matlabc: 打开使用导览", u"10 步动画"),
        (u"matlabc: 热点函数排行", u"复杂度 × 调用者数"),
        (u"matlabc: 热点函数排行（当前目录）", u""),
        (u"matlabc: 预览调用关系图", u""),
        (u"matlabc: 预览调用关系图（横向）", u""),
        (u"matlabc: 查看名字的关系（函数/变量）", u""),
        (u"matlabc: 生成 HTML 分析报告", u"单文件报告"),
        (u"matlabc: 生成 MCP 配置（给 AI 客户端）", u""),
    ]
    y = 78
    for i, (name, hint) in enumerate(cmds):
        if i == 0:
            d.rectangle([68, y - 7, W - 68, y + 25], fill=(9, 71, 113))
        d.text((84, y), name, font=_font("ui", 13), fill=WHITE)
        if hint:
            d.text((600, y + 1), hint, font=_font("ui", 11), fill=DIM)
        y += 21
    caption(d, u"示意图 · Ctrl+Shift+P 输入 matlabc，共 23 条命令", HH)
    im.save(path)



# ---------------------------------------------------------------------------
# 图 5：撤销确认（diff 预览 + 确认按钮）
# ---------------------------------------------------------------------------

def fig_undo(path):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    chrome(d, "matlabc — 撤销上一次改动")

    # 上半：Modal 对话框
    box = [70, 56, W - 70, 176]
    round_rect(d, box, 8, fill=(45, 45, 48), outline=BORDER)
    d.text((94, 76), u"matlabc: 上面是撤销后会变成的样子。确认撤销？",
           font=_font("ui", 14), fill=WHITE)

    # 两个按钮
    b1 = [W - 300, 112, W - 190, 150]
    round_rect(d, b1, 5, fill=(14, 99, 156))
    d.text((b1[0] + 34, 120), u"撤销", font=_font("ui", 14), fill=WHITE)
    b2 = [W - 170, 112, W - 94, 150]
    round_rect(d, b2, 5, fill=(60, 60, 64))
    d.text((b2[0] + 24, 120), u"取消", font=_font("ui", 14), fill=TEXT)

    # 下半：diff 视图
    pane = [40, 196, W - 40, H - 30]
    round_rect(d, pane, 6, fill=(37, 37, 38), outline=BORDER)
    d.rectangle([40, 196, W - 40, 222], fill=(45, 45, 48))
    d.text((56, 202), u"diff — 撤销后", font=_font("ui", 12), fill=(200, 200, 200))

    f = _font("mono", 13)
    rows = [
        (u"[undo   ] 目标：20261020-003128-368", (150, 156, 165)),
        (u"[plan   ] 将恢复 2 个文件、删除 0 个新建文件（未写盘）",
         (150, 156, 165)),
        (u"--- 当前 a.m", (150, 156, 165)),
        (u"+++ 撤销后 a.m", (150, 156, 165)),
        (u"@@ -1,3 +1,3 @@", (120, 140, 170)),
        (u"-function y = assist(x)", (230, 140, 140)),
        (u"+function y = helper(x)", (140, 210, 150)),
        (u"   y = x + 1;", TEXT),
        (u" end", TEXT),
        (u"--- 当前 b.m", (150, 156, 165)),
        (u"-  r = assist(v);", (230, 140, 140)),
        (u"+  r = helper(v);", (140, 210, 150)),
    ]
    y = 234
    for txt, col in rows:
        # 含中文的行必须换雅黑：Consolas 没有 CJK 字形，画出来是空心方块
        # （第一张图就踩过这个坑，这里再犯一次就太蠢了）。
        ff = _font("ui", 12) if _has_cjk(txt) else f
        d.text((56, y), txt, font=ff, fill=col)
        y += 20

    caption(d, u"示意图 · 撤销前先看 diff：红的是将被改掉的，绿的是将恢复的")
    im.save(path)



# ---------------------------------------------------------------------------
# 图 6：一次改代码的流程
# ---------------------------------------------------------------------------

def fig_flow(path):
    # 布局按**画布宽度算**，不写死坐标：上一版 4 个框 + 结论框直接顶出右边界，
    # 截图上少了一个框（"通过 → 生效"整块不见了）。
    W2, H2 = 900, 380
    im = Image.new("RGB", (W2, H2), BG)
    d = ImageDraw.Draw(im)
    chrome(d, "一次改代码：验收条件在动手之前")

    steps = [
        (u"① 算一遍", u"改哪些位置", ACCENT),
        (u"② 列判据", u"怎么算成功", ACCENT),
        (u"③ 写入", u"逐文件备份", (90, 160, 220)),
        (u"④ 复核", u"重新分析对比", (90, 160, 220)),
        (u"通过 → 生效", u"返回 pass", GREEN),
    ]
    margin = 36
    gap = 24
    bw = (W2 - 2 * margin - gap * (len(steps) - 1)) // len(steps)
    bh = 96
    y = 92
    centers = []
    for i, (t1, t2, col) in enumerate(steps):
        x = margin + i * (bw + gap)
        centers.append(x + bw // 2)
        fill = (35, 60, 45) if col == GREEN else (45, 45, 48)
        round_rect(d, [x, y, x + bw, y + bh], 8, fill=fill, outline=col, width=2)
        f1 = _font("ui_bold", 14 if i < len(steps) - 1 else 13)
        d.text((x + 12, y + 20), t1, font=f1, fill=WHITE)
        d.text((x + 12, y + 52), t2, font=_font("ui", 11), fill=DIM)
        if i < len(steps) - 1:
            ax = x + bw + 4
            d.line([ax, y + bh // 2, ax + gap - 8, y + bh // 2],
                   fill=BORDER, width=2)
            d.polygon([(ax + gap - 9, y + bh // 2 - 5),
                       (ax + gap - 1, y + bh // 2),
                       (ax + gap - 9, y + bh // 2 + 5)], fill=BORDER)

    # 回滚支路：从 ④ 复核 往下
    rx = centers[-2]
    by = y + bh + 26
    d.line([rx, y + bh + 4, rx, by + 40], fill=(150, 90, 90), width=2)
    d.polygon([(rx - 5, by + 40), (rx + 5, by + 40), (rx, by + 48)],
              fill=(150, 90, 90))
    half = 150
    round_rect(d, [rx - half, by + 48, rx + half, by + 108], 8,
               fill=(60, 42, 42), outline=(180, 100, 100), width=2)
    d.text((rx - half + 14, by + 60), u"任一条不过 → 逐字节回滚",
           font=_font("ui_bold", 12), fill=WHITE)
    d.text((rx - half + 14, by + 84), u"返回 rollback，工程回到动手前",
           font=_font("ui", 11), fill=DIM)

    caption(d, u"示意图 · 判据先写出来，再动手；过不了就自己退回去")
    im.save(path)



# ---------------------------------------------------------------------------
# 图 7：侧栏「改动记录」与右键菜单
# ---------------------------------------------------------------------------

def fig_tasks(path):
    # 三角与状态点一律**画出来**，不依赖字形：▾ / ◷ / ✓ 在雅黑里也未必有，
    # 一旦缺失就是一片空心方块（这个坑在这一套图里已经踩过三次）。
    W2, H2 = 900, 420
    im = Image.new("RGB", (W2, H2), BG)
    d = ImageDraw.Draw(im)
    chrome(d, "侧栏 · 改动记录")

    def tri(x, y, down=True, col=(190, 190, 190)):
        if down:
            d.polygon([(x, y), (x + 10, y), (x + 5, y + 7)], fill=col)
        else:
            # 收起 = 向右的三角（第一版画成了向下，等于"已展开"）
            d.polygon([(x + 1, y), (x + 1, y + 9), (x + 8, y + 4)], fill=col)

    side = [36, 56, 470, H2 - 26]
    round_rect(d, side, 8, fill=(37, 37, 38), outline=BORDER)
    d.rectangle([36, 56, 470, 84], fill=(45, 45, 48))
    d.text((52, 63), u"资源管理器", font=_font("ui", 12), fill=(200, 200, 200))

    f = _font("ui", 12)
    fb = _font("ui_bold", 12)
    y = 96
    tri(52, y + 5, True)
    d.text((70, y), u"改动记录（6）", font=fb, fill=WHITE)
    y += 26
    tri(70, y + 5, True)
    d.text((88, y), u"本次会话", font=f, fill=(150, 200, 240))
    y += 24
    rows = [
        (u"rename   2026-10-20 00:12", u"2 文件", True),
        (u"extract  2026-10-20 00:09", u"2 文件", True),
        (u"move     2026-10-20 00:04", u"1 文件", False),
    ]
    for label, desc, pending in rows:
        if pending:
            d.ellipse([96, y + 4, 104, y + 12], outline=(150, 200, 240))
        else:
            d.line([96, y + 8, 99, y + 11], fill=(120, 180, 130), width=2)
            d.line([99, y + 11, 105, y + 4], fill=(120, 180, 130), width=2)
        d.text((114, y), label, font=f, fill=WHITE if pending else DIM)
        d.text((366, y), desc, font=f, fill=DIM)
        y += 22
    y += 6
    tri(70, y + 5, False)
    d.text((88, y), u"更早", font=f, fill=(150, 200, 240))
    y += 30
    d.text((52, y), u"点一行 = 撤销那一次；右键有更多。", font=f, fill=DIM)

    mx, my = 500, 150
    round_rect(d, [mx, my, mx + 300, my + 132], 6, fill=(45, 45, 48),
               outline=BORDER)
    d.text((mx + 16, my + 10), u"撤销这一次改动", font=f, fill=WHITE)
    d.text((mx + 16, my + 40), u"查看这一次改了什么", font=f, fill=WHITE)
    d.rectangle([mx + 8, my + 66, mx + 292, my + 67], fill=BORDER)
    d.text((mx + 16, my + 76), u"复制记录 id", font=f, fill=WHITE)
    d.text((mx + 16, my + 104), u"（前两项只在「未撤销」时出现）",
           font=_font("ui", 11), fill=DIM)
    d.text((mx, my - 26), u"右键某一行的菜单：", font=_font("ui", 12), fill=DIM)

    caption(d, u"示意图 · 改了什么、还能不能撤，一眼看到")
    im.save(path)


FIGS = [
    ("relations.png", fig_relations),
    ("codelens.png", fig_codelens),
    ("heat.png", fig_heat),
    ("commands.png", fig_commands),
    ("undo.png", fig_undo),
    ("flow.png", fig_flow),
    ("tasks.png", fig_tasks),
]


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ns = ap.parse_args(argv)
    out = os.path.abspath(ns.out)
    if not os.path.isdir(out):
        os.makedirs(out)
    for name, fn in FIGS:
        p = os.path.join(out, name)
        try:
            fn(p)
        except IOError as exc:
            print("MISSING %s: %r" % (name, exc))
            return 1
        print("  %-16s %d bytes" % (name, os.path.getsize(p)))
    print("生成 %d 张 -> %s" % (len(FIGS), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
