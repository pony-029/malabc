# -*- coding: utf-8 -*-
"""导览页自检（门）。

守三类问题，它们都不会报错、只会**静静变差**：

1. **连线穿框**：端点若还在方框内部，线会压住标题 —— 看起来就是
   「箭头指过了头」。要求每个端点都落在自己的边框之外。
2. **分帧引用了不存在的模块**：改了 JSON 里的 id 而没改 STEPS，
   那一步会**什么都不高亮**，页面照样能打开。
3. **格式**：页面里不能残留模板转义 `%%`，换行必须是 LF
   （EO2：生成的 .html 不得含 CRLF）。

判据族 **TR1–TR3**。

用法：
    python tools/check_tour.py
    python tools/check_tour.py --selftest     # 两向自证：坏样本要红、好样本要过

退出码：
    0  = 导览页与它的数据一致（TR1–TR3 全绿）
    1  = 有问题（或 --selftest 失败）
    2  = 缺输入（还没跑 tools/make_tour_html.py）
"""
import argparse
import io
import json
import os
import re
import sys

ROW_SIGNATURE = "TR1–TR3"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HTML = os.path.join(ROOT, "releases", "demo", "matlabc-tour.html")
DATA = os.path.join(ROOT, "releases", "demo", "matlabc-tour.architecture.json")

MIN_FEATURES = 2          # 每一步至少列几条具体功能


def audit(html, data):
    """纯函数：给页面文本 + 数据，返回问题列表。

    抽成纯函数是为了 `--selftest`：只有能拿**构造的坏样本**喂进来，
    才能证明这些判据真的会红 —— 否则它们可能只是在描述自己。
    """
    problems = []
    comps = dict((c["id"], c) for c in (data.get("components") or []))

    # ---- TR1 分帧引用的模块必须存在 ------------------------------------
    m = re.search(r"const STEPS = (\[.*?\]);", html, re.S)
    steps = []
    if not m:
        problems.append("TR1 HTML 里找不到 STEPS")
    else:
        try:
            steps = json.loads(m.group(1))
        except ValueError as exc:
            problems.append("TR1 STEPS 不是合法 JSON：%r" % (exc,))
    for st in steps:
        for nid in (st.get("nodes") or []):
            if nid not in comps:
                problems.append("TR1 分帧「%s」引用了不存在的模块 %s"
                                % (st.get("title"), nid))
        for pair in (st.get("edges") or []):
            for nid in pair:
                if nid not in comps:
                    problems.append("TR1 分帧「%s」的连线引用了不存在的模块 %s"
                                    % (st.get("title"), nid))
        if len(st.get("features") or []) < MIN_FEATURES:
            problems.append("TR1 分帧「%s」的具体功能少于 %d 条"
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
                problems.append("TR2 连线端点落在 %s 的框内（%.0f,%.0f）"
                                % (nid, px, py))

    # ---- TR3 格式 -------------------------------------------------------
    if "%%" in html:
        problems.append("TR3 页面里残留模板转义 %%%%")
    if "\r\n" in html:
        problems.append("TR3 页面含 CRLF（生成物必须是 LF）")
    if edges != len(data.get("connections") or []):
        problems.append("TR3 连线数不符：页面 %d / 数据 %d"
                        % (edges, len(data.get("connections") or [])))
    return problems, len(comps), edges, len(steps)


#: 自证用的最小样本：一个模块、一条自环边、一帧。
_GOOD_DATA = {
    "components": [{"id": "a", "label": "A", "sublabel": "",
                    "pos": [0, 0], "size": [100, 50]}],
    "connections": [{"from": "a", "to": "a"}],
}
#: 端点取**边框值**（0 与 100）而不是框外负数：页面的正则不收负号
#: （`[\d.]+`），样本自己写错会让「好样本」先红 —— 第一版就踩了这个。
_GOOD_HTML = (
    '<g class="node" data-id="a"></g>'
    '<line class="edge" data-from="a" data-to="a" '
    'x1="0" y1="25" x2="100" y2="25"/>'
    'const STEPS = [{"title": "t", "nodes": ["a"], "edges": [["a", "a"]], '
    '"features": ["x", "y"]}];'
)


def selftest():
    good = bad = 0

    def chk(cond, name, detail=""):
        if not cond:
            print("  [FAIL] %-40s %s" % (name, detail))
        return bool(cond)

    # 1) 好样本必须过
    probs, n, e, s = audit(_GOOD_HTML, _GOOD_DATA)
    if chk(not probs, "自证：好样本无问题", repr(probs[:2])):
        good += 1
    else:
        bad += 1

    # 2) TR1：引用不存在的模块必须红
    probs, _, _, _ = audit(_GOOD_HTML.replace('["a"]', '["zzz"]'), _GOOD_DATA)
    if chk(any("TR1" in p for p in probs), "自证：不存在的模块被抓到",
           repr(probs[:2])):
        good += 1
    else:
        bad += 1

    # 3) TR2：端点落回框内必须红
    inside = _GOOD_HTML.replace('x1="0"', 'x1="50"')
    probs, _, _, _ = audit(inside, _GOOD_DATA)
    if chk(any("TR2" in p for p in probs), "自证：穿框端点被抓到",
           repr(probs[:2])):
        good += 1
    else:
        bad += 1

    # 4) TR3：CRLF 必须红
    probs, _, _, _ = audit(_GOOD_HTML + "\r\n", _GOOD_DATA)
    if chk(any("TR3" in p for p in probs), "自证：CRLF 被抓到", repr(probs[:2])):
        good += 1
    else:
        bad += 1

    # 5) TR3：连线数不符必须红
    probs, _, _, _ = audit(_GOOD_HTML, {"components": _GOOD_DATA["components"],
                                        "connections": []})
    if chk(any("TR3" in p for p in probs), "自证：连线数不符被抓到",
           repr(probs[:2])):
        good += 1
    else:
        bad += 1

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv if argv is not None else sys.argv[1:])
    if args.help:
        sys.stdout.write(__doc__)
        return 0
    if args.selftest:
        return selftest()

    if not os.path.isfile(HTML) or not os.path.isfile(DATA):
        print("check_tour: 缺少产物或源文件（先跑 tools/make_tour_html.py）")
        return 2
    html = io.open(HTML, "r", encoding="utf-8").read()
    data = json.loads(io.open(DATA, "r", encoding="utf-8").read())
    problems, ncomp, edges, steps = audit(html, data)

    if problems:
        print("check_tour: FAIL（%d 项）" % len(problems))
        for p in problems[:10]:
            print("  - " + p)
        return 1
    print("check_tour: OK（%d 个模块 / %d 条连线 / %d 步，%s 全绿）"
          % (ncomp, edges, steps, ROW_SIGNATURE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
