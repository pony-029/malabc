# -*- coding: utf-8 -*-
"""把**真实的逐步追踪**注入 `flow/index.html`：每一步怎么动、输入输出怎么变。

## 为什么不是手写一段说明

手写的"这一步做了什么"会立刻过时：改了代码，说明还停在上个版本。
这里直接读 `flow/traces/snr.jsonl`（由 `tools/trace_demo.py` 真跑出来的），
**每一行的输入/输出摘要都是当次运行的 sha256 前 12 位**。

工具只补一件 jsonl 里没有的东西：**每步"怎么动"的一句话语义**（`STEP_DESC`）。
其余（顺序、模块、耗时、摘要）全部来自数据。

## 幂等

用 `<!-- STEPS:BEGIN -->` / `<!-- STEPS:END -->` 包裹，重复运行是替换而不是追加。
"""
import argparse
import html
import sys
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "flow", "index.html")
FIG = os.path.join(ROOT, "flow", "figures")
SVG = os.path.join(ROOT, "flow", "diagrams")
TRACE = os.path.join(ROOT, "flow", "traces")   # 目录：每条 .jsonl 是一条真实链路
HIR_JSON = os.path.join(ROOT, "flow", "hir_status.json")   # 由 tools/hir_status.py 产出

BEGIN = "<!-- STEPS:BEGIN -->"
END = "<!-- STEPS:END -->"
SBEGIN = "<!-- STATS:BEGIN -->"
SEND = "<!-- STATS:END -->"

#: 每步"怎么动"——**这是唯一手写的部分**，其余全部来自 trace 数据。
STEP_DESC = {
    "S1": ("读入源码，按行切成语句序列", "磁盘上的 .m 文本 → 内存里的行数组（附行数）"),
    "S2": ("逐语句匹配、降级成三地址", "源码文本 → MIR 行（`op:` / `const:` / `setb:`）"),
    "S3": ("把三地址折回表达式树再降级", "MIR op 序列 → HIR 树 → 同构的 MIR（算子多重集必须相等）"),
    "S4": ("按函数切文件、生成工程骨架", "MIR → `gen.c` + 每函数 .c + 头文件 + CMake（文件数可见）"),
    "S5": ("把生成的 C 编译成可执行", "C 源文件 → 目标可执行（只看返回码，不看输出）"),
    "S6": ("运行 C 产物，取数值", "可执行 → stdout 的 `名: 值` 行 → 数值序列"),
    "S7": ("用解释器跑同一份 MIR", "同一份 MIR → VM 的数值序列（不经 C，独立路径）"),
    "S8": ("对比两条独立路径的数值", "两份数值序列 → 一致 / 分岔（分歧即定位到这一步）"),
    "S9": ("从生成的 C 反推 MIR", "`gen.c` 的 mlc_op_* 调用 → MIR op 行（证明产物可被重新理解）"),
}


def read_trace(path):
    """读一条链。path 可以是**.jsonl 单文件**，也可以是**目录**（取其中全部）。"""
    if not path:
        return {}
    out = {}
    if os.path.isdir(path):
        names = sorted(f for f in os.listdir(path) if f.endswith(".jsonl"))
        for n in names:
            sub = read_trace(os.path.join(path, n))
            # 递归返回的是 {名: rows}，这里只取值（否则会套成两层 dict）
            out[n[:-6]] = next(iter(sub.values())) if sub else []
        return out
    if not os.path.isfile(path):
        return {}
    rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
    return {os.path.splitext(os.path.basename(path))[0]: rows}


def read_hir():
    """读 HIR 链路状态（由 `tools/hir_status.py` **实跑**产出，不手写）。"""
    if not os.path.isfile(HIR_JSON):
        return None
    try:
        return json.load(io.open(HIR_JSON, encoding="utf-8"))
    except Exception:                                   # noqa: BLE001
        return None


def count_figs():
    n_int = len([d for d in os.listdir(FIG)
                 if os.path.isdir(os.path.join(FIG, d))]) if os.path.isdir(FIG) else 0
    n_svg = len([f for f in os.listdir(SVG) if f.endswith(".svg")]) if os.path.isdir(SVG) else 0
    return n_int, n_svg


def render_case(name, rows):
    """一条链渲染成一个可折叠区块（`<details>`，纯 HTML，不需要脚本）。"""
    ok = sum(1 for r in rows if r.get("status") == "ok")
    # 链路完整性：每个 in 都必须能追溯到更早的 out（R736 的判据）
    try:
        from trace_chain import check as _chain_check
        gaps = len(_chain_check(rows))
    except Exception:                                   # noqa: BLE001
        gaps = -1
    chain = "链路完整" if gaps == 0 else ("断链 %d" % gaps if gaps > 0 else "未校验")
    inner = render_rows(rows)
    return ('<details class="case"%s><summary><b>%s</b>'
            '<span class="case-meta">%d 步 · 通过 %d · %s</span></summary>%s</details>'
            % (" open" if ok == len(rows) else "", html.escape(name),
               len(rows), ok, chain, inner))


def render_steps(cases, hir=None):
    hirline = ("接管 %d/%d、恒等 %d" % (hir["mapped"], hir["total"], hir["identical"])
               if hir else "状态未知（先跑 tools/hir_status.py）")
    """cases: {链名: rows}。多形态并列，全部来自真实运行。"""
    if not cases:
        return (BEGIN + "\n<section id=\"steps\"><h2>每一步怎么动 "
                "<span class=\"hint\">尚无追踪数据：先跑 tools/trace_demo.py</span></h2></section>\n" + END)

    blocks = [render_case(n, rows) for n, rows in sorted(cases.items()) if rows]
    tot = sum(len(r) for r in cases.values())
    okall = sum(1 for rows in cases.values() for r in rows if r.get("status") == "ok")
    return """%(b)s
<section id="steps">
  <h2>每一步怎么动 <span class="hint">数据来自 <code>flow/traces/*.jsonl</code>：真实运行记录，不是描述</span></h2>
  <p class="q"><b>%(n)d</b> 条真实链路（不同形态：一维/二维/循环/累加）共 <b>%(tot)d</b> 步，
    <b>%(ok)d</b> 步通过。每条链的每一步都标了
    <b>控制流/数据流</b>、<b>输入→输出摘要</b>（sha256 前 12 位）与<b>它是怎么变的</b>；
    摘要相等即证明“上一步的输出真的进了这一步”。</p>
  <p class="q">**HIR 已在链上**：`mir.py --via-hir` 每次生成后强制往返一次，
    %(hirline)s。第 3 步（S3）就是它；`--hir-emit` 还能让 MIR **由 HIR 产出**。</p>
  %(blocks)s
</section>
%(e)s""" % {"b": BEGIN, "e": END, "n": len([1 for r in cases.values() if r]),
             "tot": tot, "ok": okall, "blocks": "\n  ".join(blocks),
             "hirline": hirline}


def render_rows(rows):
    cards = []
    for r in rows:
        st = r.get("step", "")
        module = r.get("module", "")
        kind = r.get("kind", "")
        label = "控制流" if kind == "control" else "数据流"
        kcls = "ctl" if kind == "control" else "dat"
        how, delta = STEP_DESC.get(st, ("", ""))
        detail = " · ".join("%s=%s" % (k, v) for k, v in (r.get("detail") or {}).items())
        status = r.get("status", "")
        cards.append(
            '<article class="step %(st)s">'
            '<div class="step-h"><span class="sid">%(st)s</span>'
            '<span class="smod">%(module)s</span>'
            '<span class="kind %(kcls)s">%(label)s</span>'
            '<span class="ms">%(ms)s ms</span>'
            '<span class="st %(status)s">%(status)s</span></div>'
            '<div class="step-b"><div class="how">%(how)s</div>'
            '<div class="io"><code>%(inp)s</code> → <code>%(out)s</code>'
            '<span class="delta">%(delta)s</span></div>'
            '<div class="act">%(action)s</div>'
            '%(detail)s</div></article>'
            % {"st": html.escape(st), "module": html.escape(module),
               "kcls": kcls, "label": label, "ms": int(r.get("ms", 0)),
               "status": html.escape(status),
               "how": html.escape(how), "delta": html.escape(delta),
               "inp": html.escape(str(r.get("in", ""))),
               "out": html.escape(str(r.get("out", ""))),
               "action": html.escape(r.get("action", "")),
               "detail": ('<div class="det">%s</div>' % html.escape(detail)) if detail else ""})

    return '<div class="steps">%s</div>' % "\n".join(cards)


def render_stats(n_int, n_svg, rows, hir=None):
    ok = sum(1 for r in rows if r.get("status") == "ok")
    hir_stat = ""
    if hir:
        hir_stat = ('\n    <span class="stat"><b>%d/%d</b>HIR 接管</span>'
                    '\n    <span class="stat"><b>%d/%d</b>HIR 恒等</span>'
                    % (hir["mapped"], hir["total"],
                       hir["identical"], hir["total"]))
        if hir.get("emitted") is not None:
            hir_stat += ('\n    <span class="stat"><b>%d/%d</b>由 HIR 产出（默认）</span>'
                         % (hir["emitted"],
                            hir["emitted"] + hir.get("passthrough", 0)))
        if hir.get("src_parity") is not None:
            hir_stat += ('\n    <span class="stat"><b>%d%%</b>行号对齐</span>'
                         % int(round(hir["src_parity"])))
    return """%(b)s
  <div class="stats">
    <span class="stat"><b>%(ni)d</b>张交互图</span>
    <span class="stat"><b>%(ns)d</b>张静态 SVG</span>
    <span class="stat"><b>%(nst)d</b>步可追踪</span>
    <span class="stat"><b>%(ok)d/%(nst)d</b>追踪通过</span>
    <span class="stat"><b>0</b>脚本 / 外链</span>%(hir)s
  </div>
%(e)s""" % {"b": SBEGIN, "e": SEND, "ni": n_int, "ns": n_svg,
             "nst": len(rows), "ok": ok, "hir": hir_stat}


STATUS_BEGIN = "<!-- STATUS:BEGIN -->"
STATUS_END = "<!-- STATUS:END -->"


def read_status():
    """读 `flow/status.json`（由 `tools/project_status.py` 产出）。"""
    p = os.path.join(ROOT, "flow", "status.json")
    if not os.path.isfile(p):
        return None
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except (ValueError, OSError):
        return None


def render_status(st):
    """把**计划阶段 + 图分布**渲染成静态表。

    数字全部来自 JSON（一次真实计算），页面本身不写死任何结论 ——
    否则它就是又一份会过期的散文。
    """
    if not st:
        return (STATUS_BEGIN + "\n"
                "<section id=\"status\"><h2>项目整体状态</h2>"
                "<p class=\"q\">缺 <code>flow/status.json</code>："
                "先跑 <code>python tools/project_status.py --json</code>。</p></section>\n"
                + STATUS_END)

    rows = []
    for ph in st.get("phases") or []:
        ok = ph.get("status") == "done"
        rows.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td><code>%s</code></td></tr>"
            % ("✅" if ok else "⚠️", ph.get("id", ""),
               html.escape(ph.get("title", "")),
               html.escape(", ".join(ph.get("evidence") or []))))

    # 职责域：**按层看厚薄**，而不是把目录再列一遍
    g = {}
    for m in st.get("modules") or []:
        k = m.get("group") or "未分组"
        d = g.setdefault(k, {"dirs": 0, "files": 0, "paths": []})
        d["dirs"] += 1
        d["files"] += m.get("files", 0)
        d["paths"].append(m.get("path", ""))
    grows = []
    for k in sorted(g, key=lambda x: -g[x]["files"]):
        d = g[k]
        grows.append("<tr><td>%s</td><td>%d</td><td>%d</td><td><code>%s</code></td></tr>"
                     % (html.escape(k), d["dirs"], d["files"],
                        html.escape(" ".join(d["paths"]))))

    f = st.get("figures") or {}
    live = (f.get("current", 0) + f.get("recent", 0))
    return """%(b)s
  <section id="status">
    <h2>项目整体状态 <span class="hint">由 <code>tools/project_status.py</code> 从仓库算出（数字不可手写）</span></h2>
    <table class="stt" style="border-collapse:collapse;width:100%%;font-size:13px;margin:8px 0">
      <tr style="text-align:left;border-bottom:1px solid currentColor">
        <th style="padding:4px 8px">状态</th><th style="padding:4px 8px">阶段</th>
        <th style="padding:4px 8px">内容</th>
        <th style="padding:4px 8px">证据判据（须已在 GX2 里跑）</th></tr>
      %(rows)s
    </table>
    <table class="stt" style="border-collapse:collapse;width:100%%;font-size:13px;margin:10px 0">
      <tr style="text-align:left;border-bottom:1px solid currentColor">
        <th style="padding:4px 8px">职责域</th><th style="padding:4px 8px">目录数</th>
        <th style="padding:4px 8px">文件数</th><th style="padding:4px 8px">包含</th></tr>
      %(grows)s
    </table>
    <p class="q"><b>流程图</b>：共 %(cnt)d 张 ｜ 现行/近期 <b>%(live)d</b> ｜
      已过时 <b>%(stale)d</b> ｜ 历史(登记) <b>%(hist)d</b>。
      历史档是不随代码重渲染的旧 schema 图（重渲染会丢语义），不是欠账。</p>
    <p class="q">门禁与测试覆盖：GX2 引用 <b>%(gx2)d</b> 个测试文件 ｜ HEAD <code>%(head)s</code>。</p>
    %(histline)s
  </section>
%(e)s""" % {
        "b": STATUS_BEGIN, "e": STATUS_END,
        "rows": "\n      ".join(rows),
        "cnt": f.get("count", 0), "live": live,
        "stale": f.get("stale", 0), "hist": f.get("historical", 0),
        "gx2": st.get("gx2_tests", 0), "head": st.get("head", ""),
        "histline": _render_hist(st),
        "grows": "\n      ".join(grows),
    }


def _render_hist(st):
    """"上次记录 / 变化"一行 —— 让**退化**可见，而不只是当前值。"""
    try:
        sys.path.insert(0, ROOT)
        from tools import project_status as PS      # noqa: PLC0415
        old = PS.history()
        if not old:
            return ('<p class="q">尚无历史：跑 '
                    '<code>python tools/project_status.py --record</code> 记一条。</p>')
        d = PS.delta(st)
        # 历史**条数**与**折叠数**都要露出来：折叠标记写着"中间有 N 条被折掉了"，
        # 而它一旦不可见，"上次记录 → 现在"就会被误读成**连续**的两条。
        folded = sum(int(x.get("folded") or 0) for x in old
                     if isinstance(x.get("folded"), int))
        extra = "，其中早前折叠 %d 条" % folded if folded else ""
        return ('<p class="q">上次记录 <code>%s</code> ｜ 变化：<b>%s</b>'
                ' ｜ 历史共 <b>%d</b> 条%s</p>'
                % (html.escape(str(old[-1].get("ts", ""))[:19]),
                   html.escape(d), len(old), extra))
    except Exception:                                # noqa: BLE001
        return ""


def splice(text, begin, end, block):
    i, j = text.find(begin), text.find(end)
    if i >= 0 and j > i:
        return text[:i] + block + text[j + len(end):]
    return None


def main():
    ap = argparse.ArgumentParser(description="把逐步追踪注入 flow/index.html")
    ap.add_argument("--index", default=INDEX)
    ap.add_argument("--trace", default=TRACE)
    a = ap.parse_args()

    cases = read_trace(a.trace)
    rows = [r for rs in cases.values() for r in rs]      # 汇总用（统计条）
    n_int, n_svg = count_figs()
    text = io.open(a.index, encoding="utf-8").read()

    hir = read_hir()
    new = splice(text, STATUS_BEGIN, STATUS_END, render_status(read_status()))
    if new is None:
        new = text
    new = splice(new, BEGIN, END, render_steps(cases, hir))
    if new is None:
        new = text.replace("</main>", render_steps(rows) + "\n\n</main>", 1)
    stats = splice(new, SBEGIN, SEND, render_stats(n_int, n_svg, rows, hir))
    if stats is None:
        # 首次：替换整个 <div class="stats">…</div>
        i = new.find('<div class="stats">')
        if i >= 0:
            j = new.find("</div>", new.find("</span>", i))
            j = new.find("</div>", j + 6) if j >= 0 else -1
            if j > 0:
                new = new[:i] + render_stats(n_int, n_svg, rows).replace(
                    SBEGIN + "\n", "").replace("\n" + SEND, "") + new[j + 6:]
    else:
        new = stats

    io.open(a.index, "w", encoding="utf-8", newline="\n").write(new)
    print("已注入：%d 步追踪 ｜ 交互图 %d ｜ SVG %d" % (len(rows), n_int, n_svg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
