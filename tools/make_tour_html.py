# -*- coding: utf-8 -*-
"""把 archify 的 architecture JSON 渲染成一个**可逐帧播放**的单文件 HTML。

为什么不用 archify 的 render
===========================
`archify validate` 可以通过，但 `render` 在本机必定失败：

    [output/target-hardlinked] Temporary output candidate has multiple
    hard-link names.  evidence: { links: "2" }

原因是它的发布协议：写候选 → 建一个硬链接当正式名（nlink=2）→ 回收暂存名
→ 校验 nlink 必须回到 1。而本机的删除会进回收站（`fsutil hardlink list`
能看到链接被移进 `$RECYCLE.BIN`），**计数永远是 2**，校验永远不过。

这是环境差异，不是 JSON 写错 —— 所以 JSON 保留为唯一事实来源，
本脚本只负责把它渲染成能直接看的页面。换一台不回收删除的机器，
`node archify/bin/archify.mjs render architecture <json> <html>` 能直接出图。

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

#: 分帧脚本：每一帧高亮一组模块，讲一件事。
#: 这里写「人真正会做的动作」，不写实现细节。
STEPS = [
    {
        "title": "① 打开工程",
        "desc": "装好扩展、打开任意 MATLAB 工程。分析在后台进行，"
                "期间大纲已经能用（它只读当前文件）。",
        "nodes": ["vscode", "ext", "lsp", "analyzer"],
        "edges": [["vscode", "ext"], ["ext", "lsp"], ["lsp", "analyzer"]],
    },
    {
        "title": "② 看一个文件里有什么",
        "desc": "Ctrl+Shift+O 列出本文件所有函数，选中即跳转。"
                "不需要等全库分析完成。",
        "nodes": ["lsp", "outline"],
        "edges": [["lsp", "outline"]],
    },
    {
        "title": "③ 跳到定义",
        "desc": "光标停在函数名上按 F12：函数、结构体字段、global 声明都能跳，"
                "跨文件也一样。字段会落到**首次赋值**那一行。",
        "nodes": ["lsp", "codelens"],
        "edges": [["lsp", "codelens"]],
    },
    {
        "title": "④ 关系面板：谁调用它 / 它调用谁",
        "desc": "光标停住，左侧「关系」面板自动刷新：上游按层展开到入口，"
                "下游展开三层；点任意一行就跳到**调用发生的那一行**。"
                "变量显示声明与出现位置，字段显示读写位置。",
        "nodes": ["ext", "sidebar"],
        "edges": [["ext", "sidebar"]],
    },
    {
        "title": "⑤ 生成 HTML 报告",
        "desc": "命令面板 →「生成 HTML 分析报告」，写到 .matlabc/report.html "
                "并自动打开。热点、耦合、数据流、结构体冲突都在这份报告里。",
        "nodes": ["ext", "html"],
        "edges": [["ext", "html"]],
    },
    {
        "title": "⑥ 让 AI 来问（MCP）",
        "desc": "命令面板 →「生成 MCP 配置」写入客户端配置。之后 AI 能直接问"
                "「改这个函数会影响谁」「这个字段谁在写」，甚至按三步安全地改代码。",
        "nodes": ["agent", "mcp", "lsp"],
        "edges": [["agent", "mcp"], ["mcp", "lsp"]],
    },
    {
        "title": "⑦ 链条断在 C 层时",
        "desc": "MATLAB 里解析不到的调用，如果工程内有 C 源、mex 或 DLL，"
                "关系面板会显示它落到哪一行；改 C 也能反查影响哪些 MATLAB 函数。",
        "nodes": ["analyzer", "cimpl"],
        "edges": [["analyzer", "cimpl"]],
    },
    {
        "title": "⑧ 第二次打开为什么很快",
        "desc": "分析结果按工程状态存盘。工程没变就直接读缓存，"
                "编辑器与 AI 共用同一份结果，不各算一遍。",
        "nodes": ["lsp", "cache"],
        "edges": [["lsp", "cache"]],
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
        node_svg.append(
            '<g class="node" data-id="%s">'
            '<rect x="%d" y="%d" width="%d" height="%d" rx="10" '
            'fill="%s22" stroke="%s" stroke-width="1.6"/>'
            '<text x="%d" y="%d" class="lbl">%s</text>'
            '<text x="%d" y="%d" class="sub">%s</text>'
            '</g>' % (
                c["id"], x, y, w, h, col, col,
                x + w / 2.0, y + h / 2.0 - 4.0, esc(c.get("label")),
                x + w / 2.0, y + h / 2.0 + 13.0, esc(c.get("sublabel"))))

    for e in conns:
        a, b = by_id.get(e["from"]), by_id.get(e["to"])
        if not a or not b:
            continue
        ax = a["pos"][0] + a["size"][0] / 2.0
        ay = a["pos"][1] + a["size"][1] / 2.0
        bx = b["pos"][0] + b["size"][0] / 2.0
        by = b["pos"][1] + b["size"][1] / 2.0
        dash = ' stroke-dasharray="6 5"' if e.get("variant") == "dashed" else ""
        edge_svg.append(
            '<line class="edge" data-from="%s" data-to="%s" x1="%.0f" y1="%.0f" '
            'x2="%.0f" y2="%.0f"%s marker-end="url(#ar)"/>'
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
.node.dim{opacity:.16}
.node.on{filter:drop-shadow(0 0 10px rgba(79,140,255,.85))}
.edge{stroke:#3a4050;stroke-width:1.4;transition:stroke .35s, stroke-width .35s}
.edge.dim{stroke:#242833}
.edge.on{stroke:var(--acc);stroke-width:2.4}
#side{width:400px;background:var(--panel);border-left:1px solid #262b35;
 padding:20px 22px;display:flex;flex-direction:column;gap:14px;overflow:auto}
h1{font-size:16px;margin:0}
h1 span{display:block;font-size:11.5px;color:var(--dim);font-weight:400;margin-top:6px}
#step{background:#22262e;border-radius:10px;padding:14px 16px;min-height:150px}
#step h3{margin:0 0 8px;font-size:14px;color:#9fc0ff}
#step p{margin:0;font-size:12.5px;line-height:1.75;color:#c8cdd8}
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
<div id="step"><h3></h3><p></p></div>
<div id="bar">
  <button id="prev">← 上一步</button>
  <button id="next">下一步 →</button>
  <button id="play">⏸ 暂停</button>
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
  document.querySelector('#step p').innerHTML = s.desc;
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
function restart(){ clearInterval(timer); timer = setInterval(tick, 4200); }
document.getElementById('next').onclick = () => { go(i + 1); restart(); };
document.getElementById('prev').onclick = () => { go(i - 1); restart(); };
document.getElementById('play').onclick = (ev) => {
  playing = !playing;
  ev.target.textContent = playing ? '⏸ 暂停' : '▶ 播放';
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
