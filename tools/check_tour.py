# -*- coding: utf-8 -*-
"""导览页自检（门）。

守三类问题，它们都不会报错、只会**静静变差**：

1. **连线穿框**：端点若还在方框内部，线会压住标题 —— 看起来就是
   「箭头指过了头」。要求每个端点都落在自己的边框之外。
2. **分帧引用了不存在的模块**：改了 JSON 里的 id 而没改 STEPS，
   那一步会**什么都不高亮**，页面照样能打开。
3. **格式**：页面里不能残留模板转义 `%%`，换行必须是 LF
   （EO2：生成的 .html 不得含 CRLF）。

用法：
    python tools/check_tour.py
"""
import io
import json
import os
import re
import sys

ROW_SIGNATURE = "TR1–TR3"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "releases", "demo", "matlabc-tour.html")
DATA = os.path.join(ROOT, "releases", "demo", "matlabc-tour.architecture.json")

MIN_FEATURES = 2          # 每一步至少列几条具体功能


def main():
    problems = []
    if not os.path.isfile(HTML) or not os.path.isfile(DATA):
        print("check_tour: 缺少产物或源文件（先跑 tools/make_tour_html.py）")
        return 2

    html = io.open(HTML, "r", encoding="utf-8").read()
    data = json.loads(io.open(DATA, "r", encoding="utf-8").read())
    comps = dict((c["id"], c) for c in (data.get("components") or []))

    # ---- TR1 分帧引用的模块必须存在 ------------------------------------
    m = re.search(r"const STEPS = (\[.*?\]);", html, re.S)
    if not m:
        problems.append("HTML 里找不到 STEPS")
        steps = []
    else:
        try:
            steps = json.loads(m.group(1))
        except ValueError as exc:
            problems.append("STEPS 不是合法 JSON：%r" % (exc,))
            steps = []
    for st in steps:
        for nid in (st.get("nodes") or []):
            if nid not in comps:
                problems.append("分帧「%s」引用了不存在的模块 %s"
                                % (st.get("title"), nid))
        for pair in (st.get("edges") or []):
            for nid in pair:
                if nid not in comps:
                    problems.append("分帧「%s」的连线引用了不存在的模块 %s"
                                    % (st.get("title"), nid))
        if len(st.get("features") or []) < MIN_FEATURES:
            problems.append("分帧「%s」的具体功能少于 %d 条"
                            % (st.get("title"), MIN_FEATURES))

    # ---- TR2 连线端点必须落在框外 --------------------------------------
    pat = re.compile(
        r'data-from="(\w+)" data-to="(\w+)" x1="([\d.]+)" y1="([\d.]+)" '
        r'x2="([\d.]+)" y2="([\d.]+)"')
    edges = 0
    for mm in pat.finditer(html):
        edges += 1
        f, t = mm.group(1), mm.group(2)
        pts = ((f, float(mm.group(3)), float(mm.group(4))),
               (t, float(mm.group(5)), float(mm.group(6))))
        for nid, px, py in pts:
            c = comps.get(nid)
            if not c:
                continue
            x, y = c["pos"]
            w, h = c["size"]
            if x + 1 < px < x + w - 1 and y + 1 < py < y + h - 1:
                problems.append("连线端点落在 %s 的框内（%.0f,%.0f）"
                                % (nid, px, py))

    # ---- TR3 格式（模板残留 / 换行 / 连线数）----------------------------
    if "%%" in html:
        problems.append("页面里残留模板转义 %%%%")
    if "\r\n" in html:
        problems.append("页面含 CRLF（生成物必须是 LF）")
    if edges != len(data.get("connections") or []):
        problems.append("连线数不符：页面 %d / 数据 %d"
                        % (edges, len(data.get("connections") or [])))

    if problems:
        print("check_tour: FAIL（%d 项）" % len(problems))
        for p in problems[:10]:
            print("  - " + p)
        return 1
    print("check_tour: OK（%d 个模块 / %d 条连线 / %d 步）"
          % (len(comps), edges, len(steps)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
