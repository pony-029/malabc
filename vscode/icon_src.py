# -*- coding: utf-8 -*-
"""生成 vscode/icon.png（手动运行，不参与打包）。

为什么是这个形状：这个扩展做的是「谁调用谁」和「跳过去」，
三个节点 + 两条连线是这件事最小的可视化；橙色节点是「当前函数」。
先在 1024 上画，再降采样到 256，边缘才干净（PIL 不做抗锯齿）。

二进制资产必须能找到出处 —— 这个脚本就是出处。
放在 vscode/ 而不是 tools/：tools/ 下每个脚本都要进 README 的工具清单，
而这不是日常工具，只是一次性的资产生成器。

用法：python vscode/icon_src.py
"""
import os

from PIL import Image, ImageDraw

SS = 1024          # 超采样边长
OUT = 256          # 最终边长
SS_DIR = r"C:\temp\icon_ss.png"
DST = r"e:\matlabc\malabc\vscode\icon.png"

BG_TOP = (27, 42, 74)        # #1B2A4A 深蓝
BG_BOT = (46, 74, 125)       # #2E4A7D 稍亮
NODE = (235, 244, 255)       # #EBF4FF 近白
EDGE = (150, 180, 220)       # 连线比节点暗一点
ACCENT = (245, 158, 11)      # #F59E0B 橙


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def main():
    # 竖向渐变
    base = Image.new("RGB", (SS, SS), BG_TOP)
    d = ImageDraw.Draw(base)
    for y in range(SS):
        t = y / float(SS - 1)
        c = tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3))
        d.line([(0, y), (SS, y)], fill=c)

    layer = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
    dl = ImageDraw.Draw(layer)

    cx = SS // 2
    bottom = (cx, int(SS * 0.74))
    left = (int(SS * 0.30), int(SS * 0.32))
    right = (int(SS * 0.70), int(SS * 0.32))
    r_node = int(SS * 0.085)
    w_edge = int(SS * 0.035)

    for tip in (left, right):
        dl.line([bottom, tip], fill=EDGE, width=w_edge)
        dl.ellipse([tip[0] - w_edge // 2, tip[1] - w_edge // 2,
                    tip[0] + w_edge // 2, tip[1] + w_edge // 2], fill=EDGE)

    for p, col in ((left, NODE), (right, NODE), (bottom, ACCENT)):
        dl.ellipse([p[0] - r_node, p[1] - r_node,
                    p[0] + r_node, p[1] + r_node], fill=col)

    base = base.convert("RGBA")
    base.alpha_composite(layer)
    base.putalpha(rounded_mask(SS, int(SS * 0.22)))

    base.save(SS_DIR, "PNG")
    img = Image.open(SS_DIR).convert("RGBA").resize((OUT, OUT), Image.LANCZOS)
    img.save(DST, "PNG")
    print("wrote", DST, os.path.getsize(DST), "bytes")
    print("size", img.size)


if __name__ == "__main__":
    main()
