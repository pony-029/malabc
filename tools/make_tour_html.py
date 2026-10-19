# -*- coding: utf-8 -*-
"""把 archify 的 architecture JSON 渲染成**可逐帧播放**的单文件 HTML。

为什么不用 archify 的 render
===========================
`archify validate` 可以通过，但 `render` 在本机必定失败：

    [output/target-hardlinked] Temporary output candidate has multiple
    hard-link names.  evidence: { links: "2" }

原因是它的发布协议：写候选 → 建一个硬链接当正式名（nlink=2）→ 回收暂存名
→ 校验 nlink 必须回到 1。而本机的删除会进回收站（`fsutil hardlink list`
能看到链接被移进 `$RECYCLE.BIN`），**计数永远是 2**，校验永远不过。

这是环境差异，不是 JSON 写错 —— 所以 JSON 保留为唯一事实来源，
本脚本只负责把它渲染成能直接看的页面。

用法：
    python tools/make_tour_html.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC = os.path.join(REPO, "releases", "demo", "matlabc-tour.architecture.json")
OUT = os.path.join(REPO, "releases", "demo", "matlabc-tour.html")

#: 分帧脚本：每帧高亮一组模块，讲一件事。
#: `features` 写**具体到能照着做**的东西（快捷键、命令名、参数），
#: 否则读者只知道「有关系面板」，不知道要按什么。
STEPS = [
    {
        "title": "① 打开工程",
        "desc": "装好扩展、打开任意 MATLAB 工程。分析在后台进行，"
                "这段时间大纲已经能用 —— 它只读当前文件，不排队。",
        "nodes": ["vscode", "ext", "lsp", "analyzer"],
        "edges": [["vscode", "ext"], ["ext", "lsp"], ["lsp", "analyzer"]],
        "features": [
            "左侧资源管理器下方出现「关系」面板",
            "状态栏显示分析进度，期间不会卡住编辑器",
            "首次打开大工程约 1 分钟，之后走缓存",
        ],
    },
    {
        "title": "② 看一个文件里有什么",
        "desc": "不用等全库分析完成。列的是**本文件**定义的函数，"
                "点一下跳到它所在的行。",
        "nodes": ["lsp", "outline"],
        "edges": [["lsp", "outline"]],
        "features": [
            "Ctrl+Shift+O —— 列出本文件所有函数",
            "↑↓ 选择，回车跳转",
            "名字前面不带任何符号，就是函数名本身",
        ],
    },
    {
        "title": "③ 跳到定义",
        "desc": "函数、结构体字段、global 声明都能跳，跨文件也一样。"
                "字段会落到**首次赋值**那一行。"
                "函数上方那行「N 个调用者」也是这个扩展加的（CodeLens）。",
        "nodes": ["lsp", "codelens"],
        "edges": [["lsp", "codelens"]],
        "features": [
            "F12 —— 跳到定义（函数 / 字段 / global）",
            "Alt+F12 —— 就地预览，不离开当前文件",
            "函数上方显示「N 个调用者」（matlabc 提供的 CodeLens）",
        ],
    },
    {
        "title": "④ 关系面板：谁调用它、它调用谁",
        "desc": "光标停住就自动刷新，不用按任何键。上游按层展开到入口，"
                "下游展开三层；点任意一行跳到**调用发生的那一行**。",
        "nodes": ["ext", "sidebar"],
        "edges": [["ext", "sidebar"]],
        "features": [
            "函数：← 调用者（按层） / → 被调用",
            "变量：声明（首次赋值） + 本文出现位置",
            "字段：写入 / 读取分开列，并标注挂在几个基名上",
            "跨函数同名变量会分组，标注「同名但不同变量」",
        ],
    },
    {
        "title": "⑤ 生成 HTML 报告",
        "desc": "要通读整个工程、或者转发给别人时用它。生成完自动打开。",
        "nodes": ["ext", "html"],
        "edges": [["ext", "html"]],
        "features": [
            "命令面板 → matlabc: 生成 HTML 分析报告",
            "输出到 .matlabc/report.html（不污染源码目录）",
            "含热点排行、跨文件耦合、结构体字段冲突",
        ],
    },
    {
        "title": "⑥ 让 AI 来问（MCP）",
        "desc": "把同一套分析结果以标准协议交给 AI 客户端。"
                "它问一句、你答一句，不用你手动翻代码。",
        "nodes": ["agent", "mcp", "lsp"],
        "edges": [["agent", "mcp"], ["mcp", "lsp"]],
        "features": [
            "命令面板 → matlabc: 生成 MCP 配置（写入 .vscode/mcp.json）",
            "19 个工具：影响面、字段溯源、热点、体检、搜索…",
            "改代码分三步：propose 看 diff → apply 落盘 → undo 撤销",
            "不确定有什么能力时，它会先调用 matlabc_help",
        ],
    },
    {
        "title": "⑦ 让 AI 真的去改（带验收、可回滚）",
        "desc": "普通的「让 AI 改代码」是它改完你自己看。这里改代码走**任务**："
                "先把验收条件列出来，改完重新分析逐条核对，不过就退回去。",
        "nodes": ["agent", "mcp", "lsp"],
        "edges": [["agent", "mcp"], ["mcp", "lsp"]],
        "features": [
            "四种任务：改函数名、改结构体字段、把一段提成函数、把函数搬到独立文件",
            "先「算一遍」（不写盘）看到要改哪些位置与验收条件，再执行",
            "任一条验收不过 → 逐字节回滚；多步任务失败 → 整批回滚",
        ],
    },
    {
        "title": "⑧ 链条断在 C 层时",
        "desc": "mex / calllib 让调用链在 MATLAB 边界断掉。"
                "工程内有 C 源、mex 或 DLL 时，关系面板会指出它落到哪。",
        "nodes": ["analyzer", "cimpl"],
        "edges": [["analyzer", "cimpl"]],
        "features": [
            "C 源：给出定义所在文件与行号，并能展开三层内部调用",
            "mex：入口名就在文件名上（foo.mexw64 → foo）",
            "DLL：核对 calllib('lib','fn') 的 fn 是否真的被导出",
            "设置 matlabc.crossLanguage 可整体关掉（省 IO）",
        ],
    },
    {
        "title": "⑨ 第二次打开为什么很快",
        "desc": "分析结果按工程状态存盘。工程没变就直接读缓存，"
                "编辑器与 AI 共用同一份结果，不各算一遍。",
        "nodes": ["lsp", "cache"],
        "edges": [["lsp", "cache"]],
        "features": [
            "缓存文件在工程根下，工程一改就自动失效重算",
            "不会拿旧结果冒充新结果（有判据守着）",
            "AI 侧复用编辑器算过的结果，不再重跑一遍",
        ],
    },
    {
        "title": "⑩ 出问题时怎么办",
        "desc": "扩展不工作时，先看**状态栏**——它把「用哪个 Python、有没有就绪」"
                "摆在明面上，而不是让你猜。",
        "nodes": ["vscode", "ext", "lsp"],
        "edges": [["vscode", "ext"], ["ext", "lsp"]],
        "features": [
            "右下角 `✓ matlabc` 就绪 / `⚠ matlabc` 没起来（悬停看原因）",
            "点它 → 重新启动服务（只重启分析，不丢未保存的编辑）",
            "还不行 → 点它 → 查看日志；换 Python 也是点它",
        ],
    },
]

TYPE_COLOR = {
    "external": "#8b93a7",
    "frontend": "#4f8cff",
    "backend": "#a06bff",
    "messagebus": "#22b8cf",
    "security": "#e8a33d",
    "cloud": "#3ec98b",
}


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def clip(cx, cy, w, h, tx, ty, gap=3.0):
    """把中心连线上的一点裁到矩形边框（外扩 gap），返回 border 上的点。

    不裁的话线会**穿过方框、压住文字** —— 屏幕上看起来就是「箭头指过了头」。
    """
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    hw, hh = w / 2.0 + gap, h / 2.0 + gap
    scales = []
    if dx:
        scales.append(hw / abs(dx))
    if dy:
        scales.append(hh / abs(dy))
    k = min(scales) if scales else 1.0
    return cx + dx * k, cy + dy * k


def build_html(data):
    comps = data.get("components") or []
    conns = data.get("connections") or []
    cards = data.get("cards") or []
    meta = data.get("meta") or {}

    by_id = dict((c["id"], c) for c in comps)
    max_x = max([c["pos"][0] + c["size"][0] for c in comps] + [1000])
    max_y = max([c["pos"][1] + c["size"][1] for c in comps] + [560])

    node_svg, edge_svg = [], []
    for c in comps:
        x, y = c["pos"]
        w, h = c["size"]
        col = TYPE_COLOR.get(c.get("type"), "#8b93a7")
        # `tag` 之前只在数据里、从不显示 —— 而它恰恰写着「谁提供的 / 给谁用」。
        # 画成右上角的小标签，不用占正文空间。
        tag_svg = ""
        tag = c.get("tag") or ""
        if tag:
            tw = len(tag) * 9.0 + 10.0
            tx = x + w - tw - 6.0
            tag_svg = ('<rect x="%.1f" y="%d" width="%.1f" height="14" rx="7" '
                       'fill="%s33" stroke="%s66"/>'
                       '<text x="%.1f" y="%d" class="tag">%s</text>'
                       % (tx, y + 5, tw, col, col, tx + tw / 2.0, y + 15.5,
                          esc(tag)))
        node_svg.append(
            '<g class="node" data-id="%s">'
            '<rect x="%d" y="%d" width="%d" height="%d" rx="10" '
            'fill="%s22" stroke="%s" stroke-width="1.6"/>'
            '%s'
            '<text x="%d" y="%d" class="lbl">%s</text>'
            '<text x="%d" y="%d" class="sub">%s</text>'
            '</g>' % (
                c["id"], x, y, w, h, col, col, tag_svg,
                x + w / 2.0,
                (y + h / 2.0 + 4.0) if tag else (y + h / 2.0 - 4.0),
                esc(c.get("label")),
                x + w / 2.0,
                (y + h / 2.0 + 20.0) if tag else (y + h / 2.0 + 13.0),
                esc(c.get("sublabel"))))

    for e in conns:
        a, b = by_id.get(e["from"]), by_id.get(e["to"])
        if not a or not b:
            continue
        acx = a["pos"][0] + a["size"][0] / 2.0
        acy = a["pos"][1] + a["size"][1] / 2.0
        bcx = b["pos"][0] + b["size"][0] / 2.0
        bcy = b["pos"][1] + b["size"][1] / 2.0
        # 两端都裁到边框：线不再穿过方框
        ax, ay = clip(acx, acy, a["size"][0], a["size"][1], bcx, bcy)
        bx, by = clip(bcx, bcy, b["size"][0], b["size"][1], acx, acy)
        dash = ' stroke-dasharray="6 5"' if e.get("variant") == "dashed" else ""
        edge_svg.append(
            '<line class="edge" data-from="%s" data-to="%s" x1="%.1f" y1="%.1f" '
            'x2="%.1f" y2="%.1f"%s marker-end="url(#ar)"/>'
            % (e["from"], e["to"], ax, ay, bx, by, dash))

    cards_html = []
    for c in cards:
        items = "".join("<li>%s</li>" % esc(i) for i in (c.get("items") or []))
        cards_html.append(
            '<div class="card"><h4><span class="dot" style="background:%s"></span>%s'
            '</h4><ul>%s</ul></div>'
            % ({"cyan": "#22b8cf", "emerald": "#3ec98b",
                "rose": "#f2637e", "amber": "#e8a33d"}.get(c.get("dot"), "#8b93a7"),
               esc(c.get("title")), items))

    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>%(title)s</title>
<style>
:root{--bg:#14161a;--panel:#1b1e24;--fg:#e6e9ef;--dim:#8b93a7;--acc:#4f8cff;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;display:flex;
 height:100vh;overflow:hidden}
#map{flex:1;display:flex;align-items:center;justify-content:center;padding:12px}
svg{width:100%%;height:100%%}
.node{cursor:pointer;transition:opacity .35s, filter .35s}
.node .lbl{font-size:13px;font-weight:600;fill:var(--fg);text-anchor:middle}
.node .sub{font-size:10.5px;fill:var(--dim);text-anchor:middle}
.node .tag{font-size:9px;fill:#c8cdd8;text-anchor:middle}
.node.dim{opacity:.16}
.node.on{filter:drop-shadow(0 0 10px rgba(79,140,255,.85))}
.edge{stroke:#3a4050;stroke-width:1.4;transition:stroke .35s, stroke-width .35s}
.edge.dim{stroke:#242833}
.edge.on{stroke:var(--acc);stroke-width:2.4}
#side{width:430px;background:var(--panel);border-left:1px solid #262b35;
 padding:20px 22px;display:flex;flex-direction:column;gap:13px;overflow:auto}
h1{font-size:16px;margin:0}
h1 span{display:block;font-size:11.5px;color:var(--dim);font-weight:400;margin-top:6px}
#step{background:#22262e;border-radius:10px;padding:14px 16px;min-height:120px}
#step h3{margin:0 0 8px;font-size:14px;color:#9fc0ff}
#step p{margin:0;font-size:12.5px;line-height:1.75;color:#c8cdd8}
#feat{margin:10px 0 0;padding-left:16px;color:#a9b6cc;font-size:12px;
 line-height:1.85;border-top:1px dashed #333a47;padding-top:9px}
#feat li::marker{color:var(--acc)}
#bar{display:flex;gap:8px;align-items:center}
button{background:#2a2f3a;color:var(--fg);border:1px solid #353b47;
 border-radius:8px;padding:7px 12px;font-size:12.5px;cursor:pointer}
button:hover{background:#333a47}
#dots{display:flex;gap:6px;margin-left:auto}
#dots i{width:7px;height:7px;border-radius:50%%;background:#3a4050;display:block}
#dots i.on{background:var(--acc)}
.card{background:#22262e;border-radius:10px;padding:12px 14px}
.card h4{margin:0 0 8px;font-size:12.5px;display:flex;align-items:center;gap:7px}
.card .dot{width:7px;height:7px;border-radius:50%%}
.card ul{margin:0;padding-left:16px;color:#b9bfcb;font-size:12px;line-height:1.8}
</style></head><body>
<div id="map">
<svg viewBox="0 0 %(w)d %(h)d" xmlns="http://www.w3.org/2000/svg">
<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6"
 markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#5a6274"/>
</marker></defs>
%(edges)s
%(nodes)s
</svg>
</div>
<div id="side">
<h1>%(title)s<span>%(subtitle)s</span></h1>
<div id="step"><h3></h3><p></p><ul id="feat"></ul></div>
<div id="bar">
  <button id="prev">← 上一步</button>
  <button id="next">下一步 →</button>
  <button id="play">暂停</button>
  <div id="dots">%(dots)s</div>
</div>
%(cards)s
</div>
<script>
const STEPS = %(steps)s;
let i = 0, timer = null, playing = true;
const nodes = [...document.querySelectorAll('.node')];
const edges = [...document.querySelectorAll('.edge')];
const dots = [...document.querySelectorAll('#dots i')];
function render(){
  const s = STEPS[i];
  document.querySelector('#step h3').textContent = s.title;
  document.querySelector('#step p').textContent = s.desc;
  const ul = document.querySelector('#feat');
  ul.innerHTML = (s.features || []).map(f => '<li>' + f + '</li>').join('');
  ul.style.display = (s.features || []).length ? '' : 'none';
  nodes.forEach(n => {
    const on = s.nodes.includes(n.dataset.id);
    n.classList.toggle('on', on);
    n.classList.toggle('dim', !on);
  });
  edges.forEach(e => {
    const on = (s.edges || []).some(p => p[0] === e.dataset.from && p[1] === e.dataset.to);
    e.classList.toggle('on', on);
    e.classList.toggle('dim', !on);
  });
  dots.forEach((d, k) => d.classList.toggle('on', k === i));
}
function go(n){ i = (n + STEPS.length) %% STEPS.length; render(); }
function tick(){ if (playing) go(i + 1); }
function restart(){ clearInterval(timer); timer = setInterval(tick, 6000); }
document.getElementById('next').onclick = () => { go(i + 1); restart(); };
document.getElementById('prev').onclick = () => { go(i - 1); restart(); };
document.getElementById('play').onclick = (ev) => {
  playing = !playing;
  ev.target.textContent = playing ? '暂停' : '播放';
};
document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowRight') { go(i + 1); restart(); }
  if (e.key === 'ArrowLeft') { go(i - 1); restart(); }
  if (e.key === ' ') { e.preventDefault();
    document.getElementById('play').click(); }
});
// 点模块直接跳到讲它的那一帧
nodes.forEach(n => n.onclick = () => {
  const k = STEPS.findIndex(s => s.nodes.includes(n.dataset.id));
  if (k >= 0) { go(k); restart(); }
});
render(); restart();
</script></body></html>
""" % {
        "title": esc(meta.get("title")),
        "subtitle": esc(meta.get("subtitle")),
        "w": int(max_x + 60),
        "h": int(max_y + 40),
        "edges": "\n".join(edge_svg),
        "nodes": "\n".join(node_svg),
        "dots": "".join("<i></i>" for _ in STEPS),
        "cards": "\n".join(cards_html),
        "steps": json.dumps(STEPS, ensure_ascii=False),
    }


def main():
    data = json.loads(io.open(SRC, "r", encoding="utf-8").read())
    html = build_html(data)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(html)
    print("已生成 %s（%.1f KB，%d 步）"
          % (os.path.relpath(OUT, REPO), len(html.encode("utf-8")) / 1024.0,
             len(STEPS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
