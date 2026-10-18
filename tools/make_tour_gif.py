# -*- coding: utf-8 -*-
"""生成覆盖各模块的演示动图（4 个场景，顺序播放）。

不是录屏 —— 按真实交互逐步绘制，便于反复生成、体积小、配色统一。
每个场景回答一个问题，串起来就是「这个工具能干什么」。
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 640, 380
BG = (30, 30, 30)
PANEL = (37, 37, 38)
BAR = (50, 50, 52)
BORDER = (60, 60, 60)
FG = (212, 212, 212)
DIM = (140, 140, 140)
ACCENT = (86, 156, 214)
GREEN = (106, 153, 85)
SEL = (42, 45, 46)
PICK = (9, 71, 113)

MONO = r"C:\Windows\Fonts\consola.ttf"
UI = r"C:\Windows\Fonts\msyh.ttc"


def F(size, path):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


M12, M13 = F(12, MONO), F(13, MONO)
U11, U12, U13 = F(11, UI), F(12, UI), F(13, UI)


def screen(tab, code, panel_title="", panel=None, hint="", sel=None,
           cursor=None):
    """画一帧。code/panel 是 [(文本, 颜色, 缩进)] 或 [(文本, 颜色)]。"""
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    # 标签栏
    d.rectangle([0, 0, W, 26], fill=(24, 24, 24))
    d.rectangle([0, 0, 150, 26], fill=BAR)
    d.text((10, 6), tab, font=U11, fill=FG)
    # 侧栏边界
    LX = 372
    d.rectangle([LX, 0, W, H], fill=PANEL)
    d.line([LX, 26, LX, H], fill=BORDER)

    # 代码
    y = 38
    for i, item in enumerate(code):
        txt, col = item[0], item[1]
        if sel is not None and i == sel:
            d.rectangle([0, y - 2, LX, y + 16], fill=SEL)
        d.text((8, y), str(i + 1), font=M12, fill=(90, 90, 90))
        d.text((30, y), txt, font=M13, fill=col)
        if cursor is not None and i == cursor[0]:
            cx = 30 + cursor[1]
            d.rectangle([cx, y, cx + 1, y + 15], fill=(174, 174, 174))
        y += 20

    # 右侧面板
    if panel_title:
        d.text((LX + 8, 34), panel_title, font=U13, fill=FG)
        d.line([LX, 58, W, 58], fill=BORDER)
    y = 68
    for item in (panel or []):
        txt, col = item[0], item[1]
        hl = len(item) > 2 and item[2]
        if hl:
            d.rectangle([LX + 2, y - 2, W - 4, y + 16], fill=PICK)
        d.text((LX + 8, y), txt, font=U12, fill=col)
        y += 20

    # 底部提示
    if hint:
        d.rectangle([0, H - 30, W, H], fill=(24, 24, 24))
        d.text((10, H - 24), hint, font=U12, fill=(200, 200, 200))
    return im


CP = [
    (u"function [sol, info] = callpop(F, h, options)", FG),
    # 代码区用等宽字体，中文会变方块 —— 示例代码保持全 ASCII。
    (u"  % parse options", GREEN),
    (u"  options = sdpsettings(options);", FG),
    (u"  [sol, info] = callpop_solver(F, h, options);", FG),
    (u"end", FG),
]

# ---------------- 场景 1：大纲 ----------------
S1 = [
    screen(u"callpop.m", CP, u"大纲",
           [(u"callpop", FG), (u"callpop_solver", FG), (u"callpop_plot", FG)],
           u"Ctrl+Shift+O 列出本文件所有函数"),
    screen(u"callpop.m", CP, u"大纲",
           [(u"callpop", FG), (u"callpop_solver", FG, True),
            (u"callpop_plot", FG)],
           u"↑↓ 选择，回车跳到该函数", cursor=(3, 30)),
    screen(u"callpop.m", CP, u"大纲",
           [(u"callpop", FG), (u"callpop_solver", FG, True),
            (u"callpop_plot", FG)],
           u"已跳到 callpop_solver 的定义行", sel=3, cursor=(3, 30)),
]

# ---------------- 场景 2：F12 ----------------
S2 = [
    screen(u"callpop.m", CP, "",
           [], u"光标停在 callpop_solver 上", cursor=(3, 20)),
    screen(u"callpop.m", CP, u"",
           [], u"按 F12 —— 跳到定义", sel=3, cursor=(3, 20)),
    screen(u"callpop_solver.m",
           [(u"function [sol, info] = callpop_solver(F, h, o)", FG),
            (u"  sol = [];", FG), (u"end", FG)], u"",
           [], u"已跳到 callpop_solver.m 的定义", sel=0),
]

# ---------------- 场景 3：关系面板 ----------------
S3 = [
    screen(u"callpop.m", CP, u"关系：callpop_solver",
           [(u"▾ callpop_solver", FG), (u"  line 4", DIM),
            (u"▸ 上游 ↑ 2 个调用者", FG), (u"▸ 下游 ↓ 3", FG)],
           u"光标停在函数名上，右侧自动出现", cursor=(3, 20)),
    screen(u"callpop.m", CP, u"关系：callpop_solver",
           [(u"▾ callpop_solver", FG), (u"  line 4", DIM),
            (u"▾ 上游 ↑ 2 个调用者", FG),
            (u"    callpop", ACCENT), (u"    callpop.m:4", DIM),
            (u"    └ [入口] main_entry", DIM), (u"▸ 下游 ↓ 3", FG)],
           u"展开上游：谁调用了它，一直到入口", cursor=(3, 20)),
    screen(u"callpop.m", CP, u"关系：callpop_solver",
           [(u"▾ callpop_solver", FG), (u"  line 4", DIM),
            (u"▾ 上游 ↑ 2 个调用者", FG),
            (u"    main_entry", (255, 255, 255), True),
            (u"    main_entry.m:12", (200, 200, 200)),
            (u"▸ 下游 ↓ 3", FG)],
           u"点任意一跳 → 跳到调用发生的那一行", sel=0),
]

# ---------------- 场景 4：热点排行 ----------------
S4 = [
    screen(u"callpop.m", CP, u"命令面板",
           [(u"> matlabc", FG), (u"  热点函数排行", ACCENT),
            (u"  生成 HTML 分析报告", FG), (u"  生成 MCP 配置", FG)],
           u"Ctrl+Shift+P 输入 matlabc"),
    screen(u"callpop.m", CP, u"热点排行（复杂度 × 调用者数）",
           [(u"1. callpop_solver", FG), (u"    复杂度 24 · 调用者 3", DIM),
            (u"2. compileQuadratic", FG), (u"    复杂度 18 · 调用者 5", DIM),
            (u"3. checkBounds", FG), (u"    复杂度 12 · 调用者 9", DIM)],
           u"决定接下来先读哪几个函数"),
    screen(u"callpop.m", CP, u"热点排行（复杂度 × 调用者数）",
           [(u"1. callpop_solver", ACCENT), (u"    复杂度 24 · 调用者 3", DIM),
            (u"2. compileQuadratic", FG), (u"    复杂度 18 · 调用者 5", DIM),
            (u"3. checkBounds", FG), (u"    复杂度 12 · 调用者 9", DIM)],
           u"选中即跳转 —— 从这里开始读代码"),
]

SCENES = [
    (S1, 1300),
    (S2, 1100),
    (S3, 1400),
    (S4, 1400),
]


def main(out):
    frames, durs = [], []
    for frameset, hold in SCENES:
        for f in frameset:
            frames.append(f.convert("P", palette=Image.ADAPTIVE, colors=96))
            durs.append(hold)
    # 每个场景最后一帧多停一会儿，留出阅读时间
    d = os.path.dirname(out)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=durs, loop=0, optimize=True)
    print(u"已生成 %s（%.1f KB，%d 帧，约 %.0f 秒）"
          % (out, os.path.getsize(out) / 1024.0, len(frames),
             sum(durs) / 1000.0))


if __name__ == "__main__":
    # 默认输出跟随仓库位置，换机器/换检出目录都不用改脚本。
    _here = os.path.dirname(os.path.abspath(__file__))
    _default = os.path.join(os.path.dirname(_here), "releases", "demo",
                            "matlabc-tour.gif")
    main(sys.argv[1] if len(sys.argv) > 1 else _default)
