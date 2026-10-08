# -*- coding: utf-8 -*-
"""页面样式与脚本资产（从 matlabc.py 迁出，便于独立优化页面样式与交互）。

本文件集中承载所有内嵌的 CSS / JS 字符串常量；render_* 装配函数后续迁入各子模块后，
统一从本文件导入这些资产。需要分析数据层的装配逻辑不在此文件。
"""

import os
import shutil
import sys

CG_PULSE_CSS = """
@keyframes cgPulseAnim{0%{stroke:#d73a49;stroke-width:3.5;}60%{stroke:#d73a49;stroke-width:3;}100%{stroke:#57606a;stroke-width:1;}}
.cg-node-g.cg-pulse circle{animation:cgPulseAnim 1.6s ease-out;}
"""
P271_A11Y_CSS = """
.skip-link{position:absolute;left:-9999px;top:0;z-index:10001;padding:8px 16px;
  background:#0969da;color:#fff;border-radius:0 0 6px 0;text-decoration:none;font-size:14px;}
.skip-link:focus{left:0;top:0;outline:2px solid #fff;outline-offset:-4px;}
"""

# HTML 报告内嵌「热点函数调用图」所需的精简样式（与浏览站点的 .cg-local 规则保持一致，
# 使 --html 与 --browse 两处输出在视觉与交互上统一）。仅含 SVG 调用图相关类。
HTML_CG_CSS = """
.cg-local{max-height:560px;overflow:auto;background:#fff;border:1px solid #d0d7de;border-radius:8px;padding:6px;margin:4px 0 12px;}
.cg-toolbar{display:flex;align-items:center;gap:6px;padding:2px 0 6px;font-size:12px;color:#57606a;user-select:none;}
.cg-toolbar button{min-width:24px;height:22px;padding:0 6px;border:1px solid #d0d7de;border-radius:5px;background:#f6f8fa;cursor:pointer;font-size:13px;line-height:1;}
.cg-toolbar button:hover{background:#eaeef2;}
.cg-toolbar .cg-zoom-pct{min-width:42px;text-align:center;font-variant-numeric:tabular-nums;}
.cg-toolbar .cg-tip{margin-left:auto;color:#8b949e;}
.cg-local-svg{display:block;}
.cg-edge{fill:none;stroke:#c8d1da;stroke-width:1.2;}
.cg-node{stroke:#fff;stroke-width:1;}
.cg-node-g{cursor:pointer;}
.cg-node-g.hl circle{stroke:#0d1117;stroke-width:2.5;}
.cg-node-g.hl text{fill:#0969da;font-weight:600;}
.cg-node-g.dim{opacity:.16;}
.cg-edge.hl{stroke:#d73a49;stroke-width:2;}
.cg-edge.dim{opacity:.12;}
.cg-legend2{font-size:12px;display:flex;gap:12px;flex-wrap:wrap;align-items:center;color:#555;margin:2px 0 8px;}
.cg-legend2 span{display:inline-flex;align-items:center;gap:5px;}
.cg-legend2 i{width:11px;height:11px;border-radius:50%;display:inline-block;box-shadow:inset 0 0 0 1px rgba(0,0,0,.12);}
.func-card{background:#fff;border:1px solid #d0d7de;border-left:5px solid #0072c6;border-radius:6px;padding:10px 14px;margin:12px 0;}
.func-card h4{margin:0 0 6px;font-size:15px;}
.cg-title{margin:6px 0 2px;font-weight:600;color:#1f2328;font-size:13px;}
.kind{font-size:11px;padding:1px 6px;border-radius:10px;color:#fff;}
.kind.main{background:#1a7f37}.kind.local{background:#9a6700}.kind.method{background:#8250df}
.kind.constructor{background:#cf222e}.kind.script{background:#57606a}
.badge{display:inline-block;font-size:11px;padding:1px 8px;border-radius:10px;background:#eef2f6;margin-left:8px;color:#444;}
.muted{color:#57606a;font-size:12px;}
.cg-search{width:100%;box-sizing:border-box;padding:6px 10px;margin:6px 0 4px;border:1px solid #d0d7de;border-radius:6px;font-size:13px;font-family:Consolas,Menlo,monospace;}
.cg-search:focus{outline:none;border-color:#0969da;box-shadow:0 0 0 2px rgba(9,105,218,.15);}
""" + CG_PULSE_CSS + """
.cg-src-btn{cursor:pointer;}
.cg-src-btn:hover circle{fill:#0969da;}
@keyframes cgSrcPulseAnim{0%{background:#fff8c5;}65%{background:#fff8c5;}100%{background:transparent;}}
tr.cg-src-pulse{animation:cgSrcPulseAnim 1.6s ease-out;}
/* P15 循环调用可视化：红色虚线徽标 + 红色虚线闭环边 */
.cg-cycle-badge{cursor:pointer;}
.cg-cycle-badge circle{fill:none;stroke:#cf222e;stroke-width:1.5;stroke-dasharray:3 2;}
.cg-cycle-badge text{fill:#cf222e;font-size:9px;font-weight:700;}
.cg-cycle-badge:hover circle{fill:#ffebe9;}
.cg-edge-cycle{stroke:#cf222e;stroke-dasharray:4 3;}
/* P17 可分享链接按钮 */
.cg-share-btn{margin:6px 0 4px;padding:5px 10px;border:1px solid #d0d7de;border-radius:6px;background:#f6f8fa;color:#0969da;font-size:12px;cursor:pointer;}
.cg-share-btn:hover{background:#eaeef2;}
/* P18：调用图节点简要说明 caption + MATLAB 内置库函数说明列表 */
.cg-desc{font-size:10px;fill:#57606a;}
.cg-desc-full{font-weight:600;fill:#1f2328;}
.cg-ord{font-size:9px;fill:#bf5700;font-weight:700;paint-order:stroke;stroke:#fff;stroke-width:2px;}
.call-order-list{margin:4px 0 6px;padding-left:22px;}
.call-order-list li{padding:1px 0;font-size:13px;}
.call-ord{display:inline-block;min-width:18px;margin-right:4px;text-align:center;background:#fff3bf;color:#9a6700;border-radius:9px;font-size:11px;font-weight:700;padding:0 4px;}
.impact-block{margin:8px 0 10px;border:1px solid #d0d7de;border-radius:8px;background:#fafbfc;padding:6px 12px;}
.impact-block summary{cursor:pointer;font-weight:600;color:#0969da;font-size:13px;}
.impact-body{padding:6px 0 2px;}
.impact-col{margin:6px 0 2px;font-size:13px;}
.impact-col b{color:#1f2328;}
.metrics-tbl{border-collapse:collapse;width:100%;font-size:13px;margin-top:6px;}
.metrics-tbl th,.metrics-tbl td{border:1px solid #d0d7de;padding:5px 8px;text-align:left;}
.metrics-tbl th{background:#f0f3f6;}
.tag-key{display:inline-block;padding:0 6px;border-radius:8px;background:#ffebe9;color:#cf222e;font-size:11px;font-weight:700;}
.tag-god{display:inline-block;padding:0 6px;border-radius:8px;background:#fff8c5;color:#9a6700;font-size:11px;font-weight:700;}
.tag-iso{display:inline-block;padding:0 6px;border-radius:8px;background:#eaeef2;color:#57606a;font-size:11px;font-weight:700;}
.cg-hover-card{position:fixed;z-index:9999;background:#fff;border:1px solid #d0d7de;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.16);padding:10px 12px;max-width:320px;font-size:12px;color:#1f2328;pointer-events:auto;}
.cg-hover-title{font-weight:700;font-size:13px;margin-bottom:6px;display:flex;align-items:center;gap:8px;}
.cg-hover-title code{font-size:13px;}
.cg-hover-kind{font-size:11px;color:#57606a;background:#f0f3f6;border-radius:8px;padding:0 6px;font-weight:600;}
.cg-hover-row{margin:3px 0;line-height:1.5;}
.cg-hover-k{color:#57606a;margin-right:8px;}
.cg-hover-desc{margin-top:6px;padding-top:6px;border-top:1px dashed #d0d7de;color:#424a53;}
.cg-hover-actions{margin-top:8px;display:flex;gap:6px;}
.cg-hover-btn{padding:3px 10px;border:1px solid #d0d7de;border-radius:6px;background:#f6f8fa;color:#0969da;font-size:12px;cursor:pointer;}
.cg-hover-btn:hover{background:#eaeef2;}
.cg-node-g:focus,.cg-src-btn:focus,.cg-cycle-badge:focus,.cg-badge:focus{outline:2px solid #0969da;outline-offset:2px;}
.builtin-section{margin:18px 0;}
.builtin-section h2{font-size:18px;margin:8px 0;}
.builtin-tbl{border-collapse:collapse;width:100%;max-width:920px;font-size:13px;margin-top:6px;}
.builtin-tbl th,.builtin-tbl td{border:1px solid #d0d7de;padding:5px 9px;text-align:left;}
.builtin-tbl th{background:#f0f3f6;}
.builtin-tbl td.num{text-align:right;font-variant-numeric:tabular-nums;}
.nav-link{color:#0969da;text-decoration:none;margin-left:14px;font-size:13px;}
/* P20：调用路径查找（最短可达路径 BFS）面板 */
.cg-path-panel{margin:10px 0 14px;border:1px solid #d0d7de;border-radius:8px;background:#f6f8fa;padding:10px 12px;}
.cg-path-title{font-weight:600;color:#1f2328;font-size:13px;margin-bottom:6px;}
.cg-path-inputs{display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
.cg-path-in{padding:5px 9px;border:1px solid #d0d7de;border-radius:6px;font-size:13px;font-family:Consolas,Menlo,monospace;min-width:160px;}
.cg-path-in:focus{outline:none;border-color:#0969da;box-shadow:0 0 0 2px rgba(9,105,218,.15);}
.cg-path-arrow{color:#57606a;font-weight:700;}
.cg-path-btn{padding:5px 12px;border:1px solid #d0d7de;border-radius:6px;background:#fff;color:#0969da;font-size:12px;cursor:pointer;}
.cg-path-btn:hover{background:#eaeef2;}
.cg-path-clear{color:#57606a;}
.cg-path-result{margin-top:8px;font-size:13px;}
.cg-path-msg{color:#9a6700;padding:4px 0;}
.cg-path-list{margin:4px 0 0;padding-left:22px;}
.cg-path-list li{padding:2px 0;}
.cg-path-node{cursor:default;}
.cg-path-node:hover{background:#ddf4ff;}
"""

BROWSE_CSS = """
:root { --accent:#0072c6; --bg:#f6f8fa; --border:#d0d7de; --surface:#fff;
  --surface-2:#f6f8fa; --text:#1f2328; --muted:#57606a; --code-bg:#f6f8fa;
  --shadow:0 1px 3px rgba(0,0,0,.08);
  /* P-rev R47：语义语法色令牌——源码高亮、预览代码片、函数签名三处复用同一套 */
  --syntax-comment:#6a737d; --syntax-string:#b35a1f; --syntax-keyword:#d73a49;
  --syntax-builtin:#005cc5; --syntax-number:#0086b3; --syntax-op:#959da5;
  --syntax-field:#8250df; --syntax-field-write:#9a3412; --syntax-struct:#1f6feb; }
:root[data-theme="dark"] { --accent:#1f6feb; --bg:#0d1117; --border:#30363d;
  --surface:#161b22; --surface-2:#0d1117; --text:#c9d1d9; --muted:#8b949e;
  --code-bg:#0d1117; --shadow:0 1px 3px rgba(0,0,0,.4);
  --syntax-comment:#8b949e; --syntax-string:#a5d6ff; --syntax-keyword:#ff7b72;
  --syntax-builtin:#79c0ff; --syntax-number:#79c0ff; --syntax-op:#c9d1d9;
  --syntax-field:#d2a8ff; --syntax-field-write:#ffa198; --syntax-struct:#79c0ff; }
* { box-sizing: border-box; }
/* FE-1：现代焦点可达性——键盘导航显式高亮（鼠标点按不触发，避免视觉干扰） */
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 2px; }
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible,
  textarea:focus-visible, [tabindex]:focus-visible, .nav-link:focus-visible { outline-offset: 3px; }
/* 锚点跳转目标在 sticky 头部下留出余量，避免被遮挡（现代 sticky 布局标配） */
:target, [id] { scroll-margin-top: 72px; }
/* 平滑滚动，但尊重 reduce-motion 偏好，避免前庭功能障碍用户不适 */
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
/* FE-5：现代 UI 细节——声明配色方案让原生控件/滚动条随主题（暗色下自动暗滚动条），
   原生控件强调色跟随主题、选区高亮、稳定滚动条槽避免布局抖动 */
:root { color-scheme: light dark; }
input, select, textarea, button { accent-color: var(--accent); }
::selection { background: var(--accent); color: #fff; }
html { scrollbar-color: var(--accent) transparent; scrollbar-width: thin; scrollbar-gutter: stable; }
/* FE-8：现代 CSS——容器查询让面板在窄容器自适应、:has() 高危行高亮、可打印报告 */
.cg-wrap, .gs-wrap, .ug-wrap { container-type: inline-size; }
@container (max-width: 680px) {
  pre, table.browse { font-size: 12px; }
}
tbody tr:has(.sev-high) { background: rgba(207, 34, 46, 0.08); }
@media print {
  nav, .toolbar, .cg-hover-card, #cg-preview { display: none !important; }
  body { background: #fff; color: #111; }
  a[href] { color: #111; text-decoration: underline; }
}
/* FE-13：skip-link 焦点样式（键盘用户跳转主内容可见；配合 S9 门禁——CSS 已外链，
   故 S9 同时扫描外链样式表以避免误报） */
.skip-link{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.skip-link:focus{position:static;width:auto;height:auto;margin:8px;padding:8px 14px;overflow:visible;clip:auto;white-space:normal;background:var(--accent);color:#fff;border-radius:6px;z-index:9999}
/* FE-16：响应式——窄屏下目录树收口、调用图/表格横向滚动，避免溢出与误触 */
@media (max-width: 720px) {
  .cg-wrap, .gs-wrap, .dh-wrap { padding: 8px; }
  .cg-wrap { overflow-x: auto; }
  table.browse, table.fh-table, table.bd-table { display: block; overflow-x: auto; max-width: 100%; }
  .gs-tabs, .dup-toolbar { flex-wrap: wrap; }
  pre.code { font-size: 12px; }
  .gs-couple-svg { max-width: 100%; height: auto; }
}
body { font-family:"Microsoft YaHei","Segoe UI",sans-serif; margin:0; background:var(--bg); color:#1f2328; }
header { background:#0d1117; color:#fff; padding:12px 24px; position:sticky; top:0; z-index:10; display:flex; gap:16px; row-gap:8px; flex-wrap:wrap; align-items:center; }
header a { color:#9ecbff; text-decoration:none; margin-right:12px; font-size:14px; }
header a:hover { text-decoration:underline; }
header .brand { margin:0 auto 0 0; line-height:1.2; font-weight:bold; font-size:16px; color:#fff; border-bottom:none; padding:0; }
#search { padding:6px 12px; border-radius:6px; border:1px solid #30363d; background:#21262d; color:#fff; width:260px; }
main { max-width:1200px; margin:0 auto; padding:20px 24px 80px; }
h1 { font-size:22px; border-bottom:2px solid var(--accent); padding-bottom:8px; }
h2 { font-size:18px; margin-top:32px; border-left:5px solid var(--accent); padding-left:10px; }
table { border-collapse:collapse; width:100%; background:#fff; }
th,td { border:1px solid var(--border); padding:6px 10px; font-size:13px; text-align:left; vertical-align:top; }
th { background:#eef2f6; position:sticky; top:49px; }
tr:hover td { background:#f2f8ff; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
code { font-family:Consolas,"Courier New",monospace; font-size:12px; background:#f0f3f6; padding:1px 5px; border-radius:3px; }
pre { background:#fff; padding:12px; border:1px solid var(--border); border-radius:6px; overflow:auto; }
.tree { font-family:Consolas,monospace; background:#fff; border:1px solid var(--border); border-radius:6px; padding:12px 16px; font-size:13px; line-height:1.6; }
.tree-leaf { margin-left:1.4em; }
.kind { font-size:11px; padding:1px 6px; border-radius:10px; color:#fff; }
.kind.main{background:#1a7f37}.kind.local{background:#9a6700}.kind.method{background:#8250df}
.kind.constructor{background:#cf222e}.kind.script{background:#57606a}
.stat { display:inline-block; background:#fff; border:1px solid var(--border); border-radius:8px; padding:10px 18px; margin:0 10px 10px 0; }
.stat b { display:block; font-size:22px; color:var(--accent); }
/* P-rev S1：任务向导（首页从「功能菜单」升级为「任务主线」） */
.wizard { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:14px; margin:18px 0 8px; }
.wizard .task { display:block; background:#fff; border:1px solid var(--border); border-left:4px solid var(--accent);
  border-radius:10px; padding:16px 18px; text-decoration:none; color:#1f2328; transition:transform .12s ease, box-shadow .12s ease; }
.wizard .task:hover { transform:translateY(-2px); box-shadow:0 6px 18px rgba(0,114,198,.14); text-decoration:none; }
.wizard .task .ico { font-size:22px; }
.wizard .task h3 { margin:8px 0 4px; font-size:16px; color:var(--accent); }
.wizard .task p { margin:0; font-size:13px; color:#57606a; line-height:1.5; }
.wizard .task .go { display:inline-block; margin-top:10px; font-size:12px; color:var(--accent); font-weight:600; }
.wizard .task.is-review { border-left-color:#cf222e; } .wizard .task.is-review h3 { color:#cf222e; }
.wizard .task.is-risk { border-left-color:#9a6700; } .wizard .task.is-risk h3 { color:#9a6700; }
.wizard .task.is-dep { border-left-color:#8250df; } .wizard .task.is-dep h3 { color:#8250df; }
.hint-row { font-size:13px; color:#57606a; margin:6px 0 0; }
/* P-rev S2：跨页联动高亮 */
.ctx-focus { background:#fff3bf !important; outline:2px solid #f0a500; border-radius:3px;
  box-shadow:0 0 0 4px rgba(240,165,0,.18); transition:background .2s; }
/* P-rev R19：影响闭包可视化——被波及的下游节点 */
.ctx-impact rect, .ctx-impact ellipse { fill:#ffe3e3 !important; stroke:#cf222e !important; stroke-width:3 !important; }
.ctx-impact text { font-weight:700; }
.ctx-impact-tip { position:fixed; left:50%; bottom:24px; transform:translateX(-50%);
  background:#cf222e; color:#fff; padding:8px 16px; border-radius:20px; font-size:13px;
  box-shadow:0 4px 14px rgba(207,34,46,.4); z-index:95; }
/* P-rev S3：源码就地编辑 */
.code-edit { display:block; border-radius:3px; padding:0 2px; outline:1px dashed transparent; }
.code-edit:hover { outline-color:#c9d3dc; }
.code-edit[contenteditable="true"]:focus { outline:2px solid var(--accent); background:#f6fbfe; }
.edit-badge { margin-left:12px; font-size:12px; color:#1a7f37; font-weight:600;
  background:#eaf6ee; border:1px solid #a7e0b8; border-radius:20px; padding:3px 10px; }
/* P-rev R9：主题切换按钮 */
.theme-btn { margin-left:auto; background:transparent; border:1px solid rgba(255,255,255,.4);
  color:#fff; cursor:pointer; border-radius:6px; padding:5px 12px; font-size:13px; }
:root[data-theme="dark"] .theme-btn { border-color:rgba(255,255,255,.25); }
/* P-rev R11：草稿改动行高亮（显示改动时） */
.edit-dirty { background:#fff1c1 !important; box-shadow:inset 3px 0 0 #f0a500; }
/* P-rev R10：键盘可达性——聚焦环 + 跳转链接高对比 */
:focus-visible { outline:3px solid #f0a500; outline-offset:2px; border-radius:3px; }
a:focus-visible, button:focus-visible, [tabindex]:focus-visible { outline:3px solid #f0a500; outline-offset:2px; }
.skip-link:focus { left:8px; top:8px; z-index:1000; }
.kbd-x { cursor:pointer; }
/* P-rev S4：个人工作台浮窗 */
.wb-dock { position:fixed; right:14px; bottom:14px; z-index:90; }
.wb-toggle { width:46px; height:46px; border-radius:50%; border:none; cursor:pointer;
  background:var(--accent); color:#fff; font-size:20px; box-shadow:0 4px 14px rgba(0,114,198,.4); }
.wb-panel { display:none; position:absolute; right:0; bottom:56px; width:280px; max-height:60vh;
  overflow:auto; background:#fff; border:1px solid var(--border); border-radius:12px;
  box-shadow:0 10px 30px rgba(0,0,0,.18); padding:12px 14px; font-size:13px; }
.wb-panel.open { display:block; }
.wb-sec { margin-bottom:12px; }
.wb-sec h4 { margin:0 0 6px; font-size:13px; color:#1f2328; }
.wb-list { list-style:none; margin:0; padding:0; }
.wb-list li { display:flex; align-items:center; gap:6px; padding:3px 0; border-bottom:1px dashed #eee; }
.wb-list li a { flex:1; color:var(--accent); text-decoration:none; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.wb-list li button { border:none; background:none; cursor:pointer; color:#cf222e; }
.wb-time { color:#8b949e; font-size:11px; }
.wb-empty { color:#8b949e; margin:0; font-size:12px; }
/* P-rev R15：工作台头部 + 协作按钮 */
.wb-head { display:flex; align-items:center; gap:6px; margin-bottom:8px; padding-bottom:6px; border-bottom:1px solid #eee; }
.wb-title { font-weight:700; font-size:13px; flex:1; color:#1f2328; }
.wb-mini { border:1px solid var(--border); background:#fff; border-radius:6px; font-size:11px; padding:2px 8px; cursor:pointer; color:var(--accent); }
/* P-rev R54：探索历史条目跳转按钮 */
.wb-hist-jump { border:none; background:none; cursor:pointer; color:var(--accent);
  font-size:12px; text-align:left; padding:2px 0; }
.wb-hist-jump:hover { text-decoration:underline; }
/* P-rev R24：导入冲突解决面板 */
.wb-cf-ovl { position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:120;
  display:flex; align-items:center; justify-content:center; padding:16px; }
.wb-cf-box { background:#fff; border-radius:12px; max-width:520px; width:100%;
  max-height:80vh; overflow:auto; padding:16px 18px; box-shadow:0 12px 40px rgba(0,0,0,.3); }
.wb-cf-box h3 { margin:0 0 6px; font-size:16px; color:#1f2328; }
.wb-cf-sum { margin:0 0 10px; font-size:12px; color:#57606a; }
.wb-cf-row { border:1px solid var(--border); border-radius:8px; padding:8px 10px; margin:8px 0; }
.wb-cf-key { font-size:12px; font-weight:600; color:#1f2328; word-break:break-all; }
.wb-cf-vals { display:flex; gap:10px; flex-wrap:wrap; margin:4px 0 6px; }
.wb-cf-v { font-size:11px; color:#57606a; background:var(--surface-2); border-radius:4px; padding:2px 6px; }
.wb-cf-btns { display:flex; gap:6px; }
.wb-cf-foot { display:flex; gap:8px; justify-content:flex-end; margin-top:12px; }
.wb-cf-ok { background:var(--accent); color:#fff; border-color:var(--accent); }
/* P-rev S6：智能引导优先顺序 */
.guide-ol { list-style:none; counter-reset:g; margin:8px 0; padding:0; }
.guide-li { counter-increment:g; background:#fff; border:1px solid var(--border);
  border-left:4px solid var(--accent); border-radius:8px; padding:10px 14px; margin:8px 0;
  display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
.guide-li::before { content:counter(g); font-weight:700; color:#fff; background:var(--accent);
  width:22px; height:22px; border-radius:50%; display:inline-flex; align-items:center;
  justify-content:center; font-size:12px; }
.guide-go { color:var(--accent); text-decoration:none; font-weight:600; flex:1; min-width:200px; }
.guide-sev { font-size:11px; padding:2px 8px; border-radius:10px; color:#fff; }
.guide-error { background:#cf222e; } .guide-warning { background:#9a6700; } .guide-suggestion { background:#57606a; }
.guide-imp { font-size:11px; padding:2px 8px; border-radius:10px; background:#eef2ff; color:#3b5bdb; font-weight:600; }
.guide-why { border:1px solid var(--accent); background:#fff; color:var(--accent);
  border-radius:6px; padding:0; font-size:12px; }
.guide-why > summary { list-style:none; cursor:pointer; padding:3px 10px; display:inline-block; }
.guide-why > summary::-webkit-details-marker { display:none; }
.guide-ref { flex-basis:100%; display:none; margin-top:4px; padding:8px 10px; background:#f6f8fa;
  border-radius:6px; font-size:12px; color:#444; }
.guide-why[open] .guide-ref { display:block; }
.hint-row code { background:#eef2f6; padding:1px 6px; border-radius:4px; }
/* 源码视图 */
.src { background:#fff; border:1px solid var(--border); border-radius:6px; overflow-x:auto; font-size:13px; }
.src table { border-collapse:collapse; width:100%; background:transparent; }
.src td { border:none; padding:1px 0; font-family:Consolas,"Courier New",monospace; font-size:13px; white-space:pre; line-height:1.65; }
.src td.ln { color:#9198a1; text-align:right; padding:1px 12px 1px 8px; width:56px; user-select:none; background:#f6f8fa; border-right:1px solid var(--border); }
.src td.code { padding:1px 14px; }
/* P-rev R41：源码阅读节奏——空行/续行给视觉呼吸，函数定义行之间留白分块 */
.src tr.code-row.blank-line td { height:0.55em; background:transparent; border-bottom:none; }
.src tr.code-row.blank-line td.code { background:transparent; }
.src tr.fdef td { background:#e7f3ff; border-top:1px solid #bfdbfe; }
.src tr.fdef td.ln { background:#d9ecff; font-weight:bold; }
.src tr.fdef:first-child td { border-top:none; }  /* P34：函数定义行之间以淡分隔线「分块」 */
/* P-rev R45/R49：函数定义行上方加分隔横条。R49 起改用 var(--accent) 随主题，
   并在暗色主题下调高透明度（深底上低透明度渐变几乎不可见）。 */
.src tr.fdef td { position:relative; }
.src tr.fdef td::before { content:""; position:absolute; top:0; left:0; right:0; height:3px;
  background:linear-gradient(90deg,var(--accent),transparent); opacity:.35; }
.src tr.fdef:first-child td::before { display:none; }
:root[data-theme="dark"] .src tr.fdef td::before { opacity:.6; }
.src tr.gs-match td { background:#fff8c5; }  /* P41：全文搜索命中行高亮 */
/* P35：注释块折叠——折叠纯注释行，让核心逻辑更紧凑 */
.src.fold-comments tr.comment-line { display:none; }
.src.fold-comments tr.comment-line.collapsed-anchor { display:table-row; }
.src tr:target td { background:#fff3bf; }
.src tr:target td.ln { background:#ffe69c; }
/* P271 R6-3：源码行「现代化标记」——废弃/不推荐 API 就地标出，悬停看替代方案 */
.src .src-mods { margin-left:8px; }
.src .src-mod { display:inline-block; margin-left:6px; padding:0 6px;
  border-radius:9px; font-size:11px; line-height:1.7; white-space:nowrap;
  cursor:help; border:1px solid #d4a72c; color:#9a6700; background:#fff8c5; }
.src .src-mod-high { border:1px solid #d1242f; color:#b42318; background:#ffebe9; }
:root[data-theme="dark"] .src .src-mod { color:#f0c674; background:#3b2f10; border-color:#6b5210; }
:root[data-theme="dark"] .src .src-mod-high { color:#ff7b72; background:#3d1416; border-color:#8b1a1c; }

/* P271 R6-2：代码审查工作台（合规得分卡 / 发现清单 / 文件分布） */
.cmp-score { display:flex; align-items:center; gap:18px; padding:14px 18px;
  border-radius:10px; border:1px solid #d8dee4; background:#f6f8fa; margin:12px 0; }
.cmp-score-num { font-size:38px; font-weight:700; line-height:1; }
.cmp-score.ok .cmp-score-num { color:#1a7f37; }
.cmp-score.warn .cmp-score-num { color:#9a6700; }
.cmp-score.bad .cmp-score-num { color:#b42318; }
.cmp-grade { font-size:15px; font-weight:600; }
.cmp-cards { display:flex; gap:10px; flex-wrap:wrap; margin:10px 0 18px; }
.cmp-card { flex:1 1 140px; padding:10px 14px; border-radius:8px;
  border:1px solid #d8dee4; background:#fff; }
.cmp-card-n { font-size:22px; font-weight:700; }
.cmp-card-l { font-size:12px; color:#57606a; }
.cmp-card.error .cmp-card-n { color:#b42318; }
.cmp-card.warning .cmp-card-n { color:#9a6700; }
.cmp-card.suggestion .cmp-card-n { color:#0969da; }
.cmp-h { font-size:14px; margin:16px 0 6px; padding-left:8px; border-left:3px solid #d8dee4; }
.cmp-h.error { border-left-color:#b42318; color:#b42318; }
.cmp-h.warning { border-left-color:#9a6700; color:#9a6700; }
.cmp-h.suggestion { border-left-color:#0969da; color:#0969da; }
.cmp-tbl { width:100%; border-collapse:collapse; font-size:12.5px; }
.cmp-tbl th, .cmp-tbl td { border:1px solid #d8dee4; padding:5px 8px;
  text-align:left; vertical-align:top; }
.cmp-tbl th { background:#f6f8fa; font-weight:600; }
.cmp-tbl tr:nth-child(even) td { background:#fbfcfd; }
.cmp-how { color:#57606a; }
.cmp-empty { padding:14px; color:#1a7f37; background:#f0fff4;
  border:1px solid #b7ebc6; border-radius:8px; }
/* P271 R6-4：需人工复核提示（明确「自动检查没报 ≠ 没问题」） */
.cmp-note { font-size:12.5px; color:#57606a; background:#f6f8fa;
  border-left:3px solid #0969da; padding:8px 12px; margin:8px 0 12px;
  border-radius:0 6px 6px 0; line-height:1.7; }
:root[data-theme="dark"] .cmp-note { background:#161b22; color:#c9d1d9; }
:root[data-theme="dark"] .cmp-score, :root[data-theme="dark"] .cmp-tbl th,
:root[data-theme="dark"] .cmp-tbl tr:nth-child(even) td { background:#161b22; }
:root[data-theme="dark"] .cmp-card { background:#0d1117; }
:root[data-theme="dark"] .cmp-tbl th, :root[data-theme="dark"] .cmp-tbl td { border-color:#30363d; }
:root[data-theme="dark"] .cmp-how { color:#8b949e; }

/* P271 R5-4：源码行内联诊断徽章（把分析结论放回代码所在位置） */
.src .src-diag { display:inline-block; margin-left:10px; padding:1px 7px;
  border-radius:10px; font-size:11px; line-height:1.6; white-space:nowrap;
  color:#57606a; background:#f6f8fa; border:1px solid #d8dee4; text-decoration:none; }
.src .src-diag:hover { background:#eaeef2; }
.src .src-diag-warn { color:#9a6700; background:#fff8c5; border-color:#d4a72c; }
.src .src-diag-warn:hover { background:#fff1a8; }
.src .src-diag .sd-w { color:#b42318; }
:root[data-theme="dark"] .src .src-diag { color:#c9d1d9; background:#21262d; border-color:#30363d; }
:root[data-theme="dark"] .src .src-diag:hover { background:#30363d; }
:root[data-theme="dark"] .src .src-diag-warn { color:#f0c674; background:#3b2f10; border-color:#6b5210; }
:root[data-theme="dark"] .src .src-diag .sd-w { color:#ff7b72; }
/* P271 R3：源码行深链高亮（#Lx / #Lx-y 由 LINE_DEEPLINK_JS 添加） */
.src tr.ln-hl td.ln { background:#ffd33d; color:#1f2328; }
.src tr.ln-hl td.code { background:#fff8c5; }
.src td.ln { cursor:pointer; }
a.call { color:#0969da; font-weight:500; }
a.call:hover { background:#ddf4ff; text-decoration:none; border-radius:3px; }
/* 语法高亮配色 */
.tk-comment { color:var(--syntax-comment); font-style:italic; }
.src table tr.comment-line > td { background:var(--surface-2); }
.src table tr.comment-line > td.code { border-left:3px solid var(--border); }
.src table .ident { cursor:pointer; border-radius:3px; padding:0 1px; }
.src table .ident:hover { background:#e8f0ff; }
.src table .ident.fld { color:var(--syntax-field); }  /* 结构体字段：紫色区别于普通变量 */
.src table .ident.fld[data-rw="w"], .src table .var.fld[data-rw="w"] { color:var(--syntax-field-write); text-decoration:underline; }  /* P35：字段「写入」用橙红下划线强调 */
.src table .ident.struct-base { color:var(--syntax-struct); text-decoration:underline dotted; }  /* P34：结构体基名，点击联动高亮其字段 */
.src table .ident.fld-def, .src table .var.fld-def { font-weight:600; }  /* P36：字段定义位（首次写入），点击字段名即跳转至此 */
.src table .ident.fld:hover, .src table .var.fld:hover { text-decoration:underline; }  /* P36：字段可点击跳转的可视提示 */
.src table .ident.hl-ident, .src table .var.hl-ident { background:#fff3bf !important; border-radius:3px; box-shadow:0 0 0 1px #f0c000; }
.src table .hl-def { outline:2px solid #0969da; outline-offset:1px; animation:cg-def-pulse 1.2s ease 2; }
@keyframes cg-def-pulse { 0%{background:#dbeafe;} 100%{background:transparent;} }
.xf-toggle { display:inline-block; margin:4px 0 2px; padding:4px 8px; background:var(--surface-2); border:1px solid var(--border); border-radius:6px; font-size:13px; cursor:pointer; }
.xf-toggle input { margin-right:4px; vertical-align:middle; }
.tk-string  { color:var(--syntax-string); }
.tk-keyword { color:var(--syntax-keyword); font-weight:600; }
.tk-builtin { color:var(--syntax-builtin); }
.tk-number  { color:var(--syntax-number); }
.tk-op      { color:var(--syntax-op); }
/* 源码行 hover 高亮 */
.src tr:hover td { background:#f6f8fa; }
.src tr:hover td.ln { background:#eaeef2; color:#444; }
.src tr.fdef:hover td { background:#fff8e6; }
/* 语法颜色图例 */
.legend { font-size:12px; margin:6px 0 10px; display:flex; gap:14px; flex-wrap:wrap; align-items:center; color:#555; }
.legend .chip { display:inline-flex; align-items:center; gap:5px; }
.legend .sw { width:12px; height:12px; border-radius:3px; display:inline-block; box-shadow:inset 0 0 0 1px rgba(0,0,0,.08); }
/* 调用点歧义标记 */
.amb { color:#b08800; font-weight:700; cursor:help; margin-left:2px; }
/* 热点分析三栏 */
.hotspot { display:flex; gap:18px; flex-wrap:wrap; margin-top:8px; }
.hs-col { flex:1 1 280px; min-width:260px; background:#fafbfc; border:1px solid #eaecef; border-radius:8px; padding:10px 14px; }
.hs-col h3 { margin:4px 0 8px; font-size:14px; }
.hs-col ol, .hs-col ul { margin:0; padding-left:20px; }
.hs-col li { margin:3px 0; font-size:13px; }
/* 交互式全局调用图 */
.cg-ctrl { display:flex; gap:16px; align-items:center; flex-wrap:wrap; margin:8px 0; font-size:13px; }
.cg-ctrl button { font-size:13px; padding:3px 10px; border:1px solid #d0d7de; background:#f6f8fa; border-radius:6px; cursor:pointer; }
.cg-ctrl button:hover { background:#eaeef2; }
.cg-zoombar { display:inline-flex; align-items:center; gap:4px; }
.cg-zoombar button { width:28px; height:26px; font-size:15px; line-height:1; padding:0; }
.cg-zoom-pct { font-variant-numeric:tabular-nums; min-width:42px; text-align:center; color:#57606a; font-size:12px; }
#cg-svg:focus { outline:2px solid var(--accent); outline-offset:-2px; }
.cg-wrap { position:relative; border:1px solid #eaecef; border-radius:8px; background:#fff; overflow:hidden; }
#cg-svg { width:100%; height:660px; display:block; background:#fcfcfd; cursor:grab; }
#cg-svg:active { cursor:grabbing; }
.cg-tip { position:fixed; display:none; pointer-events:none; background:rgba(33,38,45,.95); color:#fff; padding:6px 9px; border-radius:6px; font-size:12px; line-height:1.5; z-index:50; max-width:300px; box-shadow:0 4px 14px rgba(0,0,0,.25); }
.cg-legend { font-size:12px; margin:6px 0; display:flex; align-items:center; gap:8px; color:#555; }
.cg-legend .bar { width:160px; height:12px; border-radius:3px; background:linear-gradient(90deg,rgb(60,180,70),rgb(180,160,30),rgb(240,30,30)); }
.func-card { background:#fff; border:1px solid var(--border); border-left:5px solid var(--accent); border-radius:6px; padding:10px 14px; margin:10px 0; }
.func-card h4 { margin:0 0 6px; font-size:15px; }
.muted { color:#57606a; font-size:12px; }
.badge { display:inline-block; font-size:11px; padding:1px 8px; border-radius:10px; background:#eef2f6; margin-left:8px; }
/* doxygen 风格调用关系图 */
.callgraph { background:#f6f8fa; border:1px solid var(--border); border-radius:6px; padding:8px 12px; margin:8px 0; }
.callgraph summary { cursor:pointer; font-weight:600; color:var(--accent); }
.cg-title { margin:6px 0 2px; font-weight:600; color:#1f2328; font-size:13px; }
.calltree, .calltree ul { list-style:none; margin:2px 0 4px 16px; padding:0; }
.calltree > li { padding:1px 0 1px 16px; font-size:13px; }
.calltree li { position:relative; }
.calltree li::before { content:"└─"; position:absolute; left:0; color:#9198a1; }
/* 局部调用关系 SVG 图（离线、零依赖） */
.cg-note { margin:4px 0 6px; }
.cg-local { max-height:520px; overflow:auto; background:#fff; border:1px solid var(--border); border-radius:8px; padding:6px; margin:4px 0 10px; }
.cg-toolbar { display:flex; align-items:center; gap:6px; padding:2px 0 6px; font-size:12px; color:#57606a; user-select:none; }
.cg-toolbar button { min-width:24px; height:22px; padding:0 6px; border:1px solid #d0d7de; border-radius:5px; background:#f6f8fa; cursor:pointer; font-size:13px; line-height:1; }
.cg-toolbar button:hover { background:#eaeef2; }
.cg-toolbar .cg-zoom-pct { min-width:42px; text-align:center; font-variant-numeric:tabular-nums; }
.cg-toolbar .cg-tip { margin-left:auto; color:#8b949e; }
.cg-local-svg { display:block; }
.cg-edge { fill:none; stroke:#c8d1da; stroke-width:1.2; }
.cg-node { stroke:#fff; stroke-width:1; }
.cg-local-svg a:hover .cg-node { stroke:#0d1117; stroke-width:2; }
.cg-local-svg a:hover text { fill:#0969da; text-decoration:underline; }
.cg-node-g { cursor:pointer; }
.cg-node-g.hl circle { stroke:#0d1117; stroke-width:2.5; }
.cg-node-g.hl text { fill:#0969da; font-weight:600; }
.cg-node-g.dim { opacity:.16; }
.cg-edge.hl { stroke:#d73a49; stroke-width:2; }
.cg-edge.dim { opacity:.12; }
.cg-node-g.cg-pulse circle { stroke:#d73a49; stroke-width:3; }
/* 调用图搜索框（P14）与脉冲定位动画 */
.cg-search-wrap { margin:4px 0 8px; }
.cg-search { width:100%; box-sizing:border-box; padding:6px 10px; margin:2px 0 4px;
  border:1px solid var(--border); border-radius:6px; font-size:13px; font-family:var(--mono); }
.cg-search:focus { outline:none; border-color:#0969da; box-shadow:0 0 0 2px rgba(9,105,218,.15); }
.cg-search-hint { font-size:11px; display:block; }
""" + CG_PULSE_CSS + """
/* 调用图 → 源码联动（P16-A）：节点上的源码跳转按钮 + 源码行脉冲定位 */
.cg-src-btn { cursor: pointer; }
.cg-src-btn:hover circle { fill:#0969da; }
@keyframes cgSrcPulseAnim { 0%{background:#fff8c5;} 65%{background:#fff8c5;} 100%{background:transparent;} }
tr.cg-src-pulse { animation: cgSrcPulseAnim 1.6s ease-out; }
/* P15 循环调用可视化：红色虚线徽标 + 红色虚线闭环边 */
.cg-cycle-badge { cursor: pointer; }
.cg-cycle-badge circle { fill:none; stroke:#cf222e; stroke-width:1.5; stroke-dasharray:3 2; }
.cg-cycle-badge text { fill:#cf222e; font-size:9px; font-weight:700; }
.cg-cycle-badge:hover circle { fill:#ffebe9; }
.cg-edge-cycle { stroke:#cf222e; stroke-dasharray:4 3; }
/* P17 可分享链接按钮 */
.cg-share-btn { margin:6px 0 4px; padding:5px 10px; border:1px solid var(--border); border-radius:6px; background:#f6f8fa; color:#0969da; font-size:12px; cursor:pointer; }
.cg-share-btn:hover { background:#eaeef2; }
/* P18：调用图节点简要说明 caption + MATLAB 内置库函数说明列表 */
.cg-desc { font-size:10px; fill:#57606a; }
.cg-desc-full { font-weight:600; fill:#1f2328; }
/* P21：边线上的调用顺序序号（按源码调用顺序） */
.cg-ord { font-size:9px; fill:#bf5700; font-weight:700; paint-order:stroke; stroke:#fff; stroke-width:2px; }
/* P21：源码页「调用（按源码调用顺序）」编号列表 */
.call-order-list { margin:4px 0 6px; padding-left:22px; }
.call-order-list li { padding:1px 0; font-size:13px; }
.call-ord { display:inline-block; min-width:18px; margin-right:4px; text-align:center;
  background:#fff3bf; color:#9a6700; border-radius:9px; font-size:11px; font-weight:700; padding:0 4px; }
/* P22：影响面 / 依赖面（传递闭包）区块 */
.impact-block { margin:8px 0 10px; border:1px solid var(--border); border-radius:8px; background:#fafbfc; padding:6px 12px; }
.impact-block summary { cursor:pointer; font-weight:600; color:var(--accent); font-size:13px; }
.impact-body { padding:6px 0 2px; }
.impact-col { margin:6px 0 2px; font-size:13px; }
.impact-col b { color:#1f2328; }
/* P23：关键函数风险度量表格与标签 */
.metrics-tbl { border-collapse:collapse; width:100%; font-size:13px; margin-top:6px; }
.metrics-tbl th, .metrics-tbl td { border:1px solid var(--border); padding:5px 8px; text-align:left; }
.metrics-tbl th { background:#f0f3f6; }
.metrics-tbl td.num, .metrics-tbl td { text-align:left; }
.tag-key { display:inline-block; padding:0 6px; border-radius:8px; background:#ffebe9; color:#cf222e; font-size:11px; font-weight:700; }
.tag-god { display:inline-block; padding:0 6px; border-radius:8px; background:#fff8c5; color:#9a6700; font-size:11px; font-weight:700; }
.tag-iso { display:inline-block; padding:0 6px; border-radius:8px; background:#eaeef2; color:#57606a; font-size:11px; font-weight:700; }
/* P29：节点悬浮详情卡片 + 键盘焦点 */
.cg-hover-card { position:fixed; z-index:9999; background:#fff; border:1px solid var(--border);
  border-radius:10px; box-shadow:0 8px 24px rgba(0,0,0,.16); padding:10px 12px; max-width:320px;
  font-size:12px; color:#1f2328; pointer-events:auto; }
.cg-hover-title { font-weight:700; font-size:13px; margin-bottom:6px; display:flex; align-items:center; gap:8px; }
.cg-hover-title code { font-size:13px; }
.cg-hover-kind { font-size:11px; color:#57606a; background:#f0f3f6; border-radius:8px; padding:0 6px; font-weight:600; }
.cg-hover-row { margin:3px 0; line-height:1.5; }
.cg-hover-k { color:#57606a; margin-right:8px; }
.cg-hover-desc { margin-top:6px; padding-top:6px; border-top:1px dashed var(--border); color:#424a53; }
.cg-hover-actions { margin-top:8px; display:flex; gap:6px; }
.cg-hover-btn { padding:3px 10px; border:1px solid var(--border); border-radius:6px; background:#f6f8fa;
  color:#0969da; font-size:12px; cursor:pointer; }
.cg-hover-btn:hover { background:#eaeef2; }
.cg-node-g:focus, .cg-src-btn:focus, .cg-cycle-badge:focus, .cg-badge:focus { outline:2px solid #0969da; outline-offset:2px; }
/* P36：函数预览弹窗 */
.cg-preview-mask { position:fixed; inset:0; z-index:10000; background:rgba(0,0,0,.35);
  display:flex; align-items:center; justify-content:center; }
.cg-preview-panel { background:#fff; border-radius:12px; box-shadow:0 16px 48px rgba(0,0,0,.24);
  max-width:520px; width:92%; max-height:82vh; overflow:auto; padding:18px 20px; }
.cg-preview-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.cg-preview-title { font-size:17px; font-weight:700; display:flex; align-items:center; gap:8px; }
.cg-preview-title code { font-size:16px; }
.cg-preview-close { border:none; background:none; font-size:24px; line-height:1; cursor:pointer; color:#57606a; padding:0 4px; }
.cg-preview-close:hover { color:#1f2328; }
.cg-preview-sig { margin:10px 0 4px; padding:8px 10px; background:var(--surface-2); border:1px solid var(--border);
  border-radius:8px; font-family:Consolas,Menlo,monospace; font-size:12.5px; color:var(--text); white-space:pre-wrap; }
.cg-preview-rows { margin:8px 0 4px; }
.cg-preview-desc { margin-top:8px; padding-top:8px; border-top:1px dashed var(--border); color:var(--muted); font-size:12.5px; line-height:1.6; }
.cg-preview-snip { margin:10px 0 4px; padding:10px 12px; background:var(--code-bg,#f6f8fa);
  color:var(--text,#1f2328); border:1px solid var(--border,#d0d7de); border-radius:8px;
  font-family:Consolas,Menlo,monospace; font-size:12px; line-height:1.55; white-space:pre; overflow-x:auto; }
.cg-preview-snip .cg-snip-ln { color:var(--muted,#6e7681); user-select:none; }
.cg-preview-snip .cg-snip-line { white-space:pre; cursor:pointer; }
.cg-preview-snip .cg-snip-line:hover { background:rgba(56,139,253,0.16); }
/* P-rev R39/R47：预览代码主题适配。R47 起语义色统一走 --syntax-* 令牌，
   与源码高亮/函数签名共用同一套，浅/深主题各定义一次，不再逐处写暗色覆盖。 */
.cg-preview-snip .cg-snip-comment { color:var(--syntax-comment); font-style:italic; }
.cg-preview-snip .cg-snip-string { color:var(--syntax-string); }
.cg-preview-snip .cg-snip-keyword { color:var(--syntax-keyword); font-weight:600; }
.cg-preview-snip .cg-snip-builtin { color:var(--syntax-builtin); }
.cg-preview-snip .cg-snip-number { color:var(--syntax-number); }
.cg-preview-snip .cg-snip-op { color:var(--syntax-op); }
/* P52：预览面板「同名函数候选」区块 */
.cg-preview-dups { margin-top:8px; padding-top:8px; border-top:1px dashed var(--border); }
.cg-preview-dups-title { font-size:12px; color:#57606a; margin-bottom:4px; font-weight:600; }
.cg-preview-dup { font-size:12px; color:#424a53; padding:2px 0 2px 4px; line-height:1.6; border-left:2px solid transparent; cursor:pointer; border-radius:3px; }
.cg-preview-dup code { font-size:11.5px; }
.cg-preview-dup-mark { display:inline-block; width:16px; color:#1a7f37; font-weight:700; }
.cg-preview-dup.is-self { background:#f6f8fa; border-left-color:#1a7f37; }
.cg-preview-dup:not(.is-self) { color:#6e7781; }
.cg-preview-dup:not(.is-self):hover { background:#e8f0ff; color:#1f2328; border-left-color:#0969da; }
.builtin-section { margin:18px 0; }
.builtin-section h2 { font-size:18px; margin:8px 0; }
.builtin-tbl { border-collapse:collapse; width:100%; max-width:920px; font-size:13px; margin-top:6px; }
.builtin-tbl th, .builtin-tbl td { border:1px solid var(--border); padding:5px 9px; text-align:left; }
.builtin-tbl th { background:#f0f3f6; }
.builtin-tbl td.num { text-align:right; font-variant-numeric:tabular-nums; }
.nav-link { color:#0969da; text-decoration:none; margin-left:14px; font-size:14px; }
/* P81：类层次（Class Hierarchy）继承图容器 */
.class-hierarchy-wrap { margin:10px 0 18px; padding:8px; border:1px solid var(--border); border-radius:8px; background:#fff; overflow-x:auto; }
.class-hierarchy-wrap svg { display:block; max-width:100%; height:auto; }
/* A2：多返回值解构标注（源码行内「返回值流向」药丸） */
.destructure { display:inline-block; margin-left:8px; font-size:11px; color:#8250df; background:#f6f8fa; border:1px solid #d0d7de; border-radius:10px; padding:1px 8px; cursor:help; }
.builtin-list { margin:10px 0 14px; border:1px solid var(--border); border-radius:8px; background:#fff; padding:6px 12px; }
.builtin-list summary { cursor:pointer; font-weight:600; }
.builtin-list-body { padding:6px 0 2px; }
.builtin-item { font-size:13px; line-height:1.7; }
.builtin-item code { background:#eef1f4; padding:1px 5px; border-radius:4px; }
/* 按需下钻：容器与展开 / 折叠徽标 */
.cg-host { min-height:40px; }
.cg-badge { cursor:pointer; }
.cg-badge circle { fill:#fff; stroke:#57606a; stroke-width:1; }
.cg-badge text { font-size:11px; fill:#57606a; font-weight:bold; }
.cg-badge:hover circle { fill:#e8f0ff; stroke:#0969da; }
.cg-legend2 { font-size:12px; display:flex; gap:12px; flex-wrap:wrap; align-items:center; color:#555; margin:2px 0 8px; }
.cg-legend2 span { display:inline-flex; align-items:center; gap:5px; }
.cg-legend2 i { width:11px; height:11px; border-radius:50%; display:inline-block; box-shadow:inset 0 0 0 1px rgba(0,0,0,.12); }
.entry-graph { background:#fff; border:1px solid var(--border); border-radius:6px; padding:8px 12px; margin:8px 0; }
/* 函数头部注释（结构化信息展示） */
.func-header { margin:6px 0 10px; padding:8px 12px; background:#f8fafc; border-left:3px solid #0969da; border-radius:4px; font-size:13px; }
.fh-label { color:#0969da; white-space:nowrap; }
.fh-desc { margin:3px 0; line-height:1.5; }
.fh-notice { margin:3px 0; line-height:1.5; color:#bf5700; }
.fh-ref { margin:3px 0; line-height:1.6; font-size:12px; }
.fh-io { margin:4px 0; }
.fh-table { width:100%; border-collapse:collapse; margin:2px 0; font-size:12.5px; }
.fh-table th { text-align:left; color:#57606a; font-weight:600; padding:2px 8px 2px 0; border-bottom:1px solid #d0d7de; }
.fh-table td { padding:2px 8px 2px 0; vertical-align:top; }
.fh-calling, .fh-calledby { margin:4px 0; line-height:1.5; }
.fh-hint { font-size:11px; margin-left:6px; }
/* P-rev R43：文件头信息卡在暗色主题下的对比度。原 th 用 #57606a（浅灰）在深色底上
   偏暗，label/desc 用硬编码色在深色下也可能偏暗，这里统一用 var 随主题提亮。 */
:root[data-theme="dark"] .fh-table th { color:#8b949e; border-bottom-color:#30363d; }
:root[data-theme="dark"] .fh-label { color:#79c0ff; }
:root[data-theme="dark"] .fh-notice { color:#d29922; }
:root[data-theme="dark"] .fh-desc, :root[data-theme="dark"] .fh-ref { color:#c9d1d9; }
:root[data-theme="dark"] .fh-table td { color:#c9d1d9; }
.fh-updates ul { margin:2px 0 0 16px; padding:0; list-style-type:square; }
.fh-updates li { font-size:12px; line-height:1.5; color:#57606a; }
/* 文件夹级调用统计 */
.folder-stats { margin:16px 0; }
.folder-stats table { width:100%; border-collapse:collapse; font-size:13px; }
.folder-stats th { background:#f6f8fa; text-align:left; padding:6px 10px; border-bottom:2px solid #d0d7de; }
.folder-stats td { padding:5px 10px; border-bottom:1px solid #eaeef2; vertical-align:top; }
.folder-stats tr:hover td { background:#f6f8fa; }
.fs-entry-list { font-size:12px; max-width:300px; }
/* P60：目录依赖区块 */
.folder-deps { margin:16px 0; }
.folder-deps .fd-table { width:100%; border-collapse:collapse; font-size:13px; margin-bottom:14px; }
.folder-deps .fd-table th { background:#f6f8fa; text-align:left; padding:6px 10px; border-bottom:2px solid #d0d7de; }
.folder-deps .fd-table td { padding:5px 10px; border-bottom:1px solid #eaeef2; vertical-align:top; }
.folder-deps .fd-table tr:hover td { background:#f6f8fa; }
.folder-deps .fd-calls { font-size:12px; max-width:520px; }
.folder-deps .fd-calls a { text-decoration:none; color:var(--accent); }
.folder-deps .fd-calls a:hover { text-decoration:underline; }
.fd-dirs { display:flex; flex-wrap:wrap; gap:10px; }
.fd-dir { border:1px solid var(--border); border-radius:8px; padding:8px 12px; background:#fff; min-width:180px; }
.fd-dir-name { font-weight:700; font-size:13px; margin-bottom:4px; color:#24292f; text-decoration:none; }
.fd-dir-name:hover { text-decoration:underline; color:var(--accent); }
.fd-dir-row { font-size:12px; color:#57606a; line-height:1.7; }
.fd-dir-row code { background:#f6f8fa; border-radius:4px; padding:1px 4px; }
.fd-cycle-warn { background:#fff8c5; border:1px solid #d4a72c; color:#7d5b00; border-radius:6px; padding:6px 10px; font-size:13px; margin-bottom:12px; }
.fd-cycle-mark { color:#d4a72c; font-weight:700; }
.fd-dir.is-cycle { border-color:#d4a72c; background:#fffdf0; }
/* P65：目录索引页 */
.crumb { margin-left:12px; font-size:13px; color:#57606a; }
.crumb a { text-decoration:none; color:var(--accent); }
.crumb a:hover { text-decoration:underline; }
.dir-overview { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }
.dir-overview .stat { padding:4px 12px; border-radius:14px; background:#f6f8fa; border:1px solid #d0d7de; font-size:13px; color:#57606a; }
.dir-overview .stat b { color:#24292f; }
.dir-overview .tag-mid { background:#fff8e6; border-color:#d4a72c; color:#7d5b00; font-weight:600; }
.dir-overview .tag-high { background:#ffebe9; border-color:#e5484d; color:#8b1c1c; font-weight:700; }
.dir-overview .tag-cycle { background:#fff8c5; border-color:#d4a72c; color:#7d5b00; font-weight:600; }
.dir-deps { margin:12px 0; padding:10px 12px; background:#f6f8fa; border:1px solid var(--border); border-radius:8px; }
.dir-dep { font-size:13px; line-height:1.8; }
.dir-dep a { text-decoration:none; color:var(--accent); }
.dir-dep a:hover { text-decoration:underline; }
.dir-file { margin:10px 0; padding:8px 12px; border:1px solid var(--border); border-radius:8px; background:#fff; }
.dir-file-name { font-weight:600; font-size:13px; color:#24292f; text-decoration:none; }
.dir-file-name:hover { text-decoration:underline; }
.dir-file-fns { margin-top:6px; }
.fn-pill { display:inline-block; margin:2px 4px 2px 0; padding:2px 8px; border-radius:12px; background:#f6f8fa; border:1px solid #d0d7de; font-size:12px; text-decoration:none; color:#57606a; }
.fn-pill:hover { background:#eaeef2; color:var(--accent); }
/* 端到端调用链路 */
.e2e-chain { margin:8px 0 14px; border:1px solid var(--border); border-radius:8px; padding:10px 14px; background:#fff; }
.e2e-chain summary { cursor:pointer; font-weight:600; font-size:14px; color:var(--accent); outline:none; }
.e2e-entry { margin-right:8px; }
.e2e-step { padding:3px 0 3px 18px; line-height:1.6; font-size:13px; position:relative; }
.e2e-arrow { position:absolute; left:0; color:#0969da; font-weight:bold; }
.e2e-desc { margin-left:18px; font-size:12px; color:#57606a; padding:1px 0 4px 0; border-bottom:1px dotted #d0d7de; }
.e2e-cycle { color:#bf5700; }
.e2e-io { font-size:11px; margin-left:4px; }
/* 参数流向药丸（点击高亮源码读写位置） */
.param-flow { margin:8px 0 4px; font-size:13px; }
.param-pill { display:inline-block; margin:2px 4px 2px 0; padding:1px 4px; border-radius:10px;
  border:1px solid #d0d7de; background:#f6f8fa; cursor:pointer; font-family:var(--mono); font-size:12px; }
/* P73：函数卡片内文件夹调用 + 参数说明 */
.fn-folder-calls { margin:4px 0; font-size:13px; color:#57606a; }
.fn-folder-calls a { text-decoration:none; color:var(--accent); }
.fn-folder-calls a:hover { text-decoration:underline; }
.fn-param-docs { margin:4px 0; font-size:13px; color:#57606a; }
.param-doc { display:inline-block; margin:1px 6px 1px 0; font-size:12px; }
.param-doc .null { color:#8b949e; font-style:italic; }
.fn-external { margin:4px 0; font-size:13px; color:#8b6d00; }
.fn-external code { background:#fff8e6; border-radius:4px; padding:1px 4px; }
.fn-external code.ext-leak, .fn-external a.ext-leak { background:#ffebe9; color:#8b1c1c; border:1px solid #e5484d; }
.fn-external a.ext-leak { text-decoration:underline; cursor:pointer; }
.param-pill:hover { background:#eaeef2; border-color:#8b949e; }
.param-pill .pill-k { margin-left:5px; font-size:11px; padding:0 4px; border-radius:8px; color:#fff; }
.k-both .pill-k { background:#8250df; }
.k-read .pill-k { background:#0969da; }
.k-write .pill-k { background:#bf5700; }
.k-decl .pill-k { background:#57606a; }
.k-unused .pill-k { background:#9aa0a6; }
.param-pill.k-both { border-color:#8250df; }
.param-pill.k-read { border-color:#0969da; }
.param-pill.k-write { border-color:#bf5700; }
.param-pill.k-decl { border-color:#57606a; }
/* 源码中的参数出现：默认无背景，悬停淡显 */
.var { border-radius:2px; cursor:pointer; padding:0 1px; }
.var:hover { background:#f0f3f6; }
.var.var-d { box-shadow:inset 0 -2px 0 #cfd8e3; }
.var.hl.var-d { background:#e7e7e7; }
.var.hl.var-r { background:#dbeafe; box-shadow:inset 0 -2px 0 #0969da; }
.var.hl.var-w { background:#ffedd5; box-shadow:inset 0 -2px 0 #bf5700; }
.vf-hint { margin:4px 0; }
.vf-info { display:none; position:sticky; top:0; z-index:20; margin:6px 0; padding:6px 10px;
  background:#0d1117; color:#fff; border-radius:6px; font-size:13px; }
/* 全局搜索（函数跳转 + 全文检索） */
.gs-mode { display:inline-flex; border:1px solid #d0d7de; border-radius:6px; overflow:hidden; }
.gs-mode button { border:0; background:#f6f8fa; padding:5px 12px; font-size:13px; cursor:pointer; color:#57606a; }
.gs-mode button.active { background:#0969da; color:#fff; }
.gs-regex { display:inline-flex; align-items:center; gap:4px; font-size:13px; color:#57606a; cursor:pointer; }
#search { flex:1; min-width:240px; margin:0 10px; padding:6px 10px; border:1px solid #d0d7de; border-radius:6px; font-size:14px; }
#search:focus { outline:2px solid #0969da33; border-color:#0969da; }
.gs-results { position:absolute; top:52px; left:16px; right:16px; max-height:60vh; overflow:auto;
  background:#fff; border:1px solid #d0d7de; border-radius:8px; box-shadow:0 8px 28px rgba(0,0,0,.16);
  display:none; z-index:60; padding:6px 0; }
.gs-head { padding:4px 14px; font-size:12px; color:#57606a; border-bottom:1px solid #eaecef; }
.gs-empty { padding:12px 14px; color:#8b949e; font-size:13px; }
.gs-list { list-style:none; margin:0; padding:4px 0; }
.gs-list li { padding:5px 14px; font-size:13px; border-bottom:1px solid #f3f4f6; }
.gs-list li:last-child { border-bottom:0; }
.gs-list li a { color:#0969da; text-decoration:none; }
.gs-list li a:hover { text-decoration:underline; }
.gs-list .muted { margin-left:8px; color:#57606a; font-size:12px; }
.gs-list .kind { margin-left:6px; }
.gs-snip { font-family:var(--mono); font-size:12px; color:#333; margin-top:2px; white-space:pre-wrap; word-break:break-all; }
.gs-snip mark, .gs-hl { background:#fff3a0; border-radius:2px; padding:0 1px; }
/* P20：调用路径查找（最短可达路径 BFS）面板 */
.cg-path-panel { margin:10px 0 14px; border:1px solid var(--border); border-radius:8px; background:#fff; padding:10px 12px; }
.cg-path-title { font-weight:600; color:#1f2328; font-size:13px; margin-bottom:6px; }
.cg-path-inputs { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.cg-path-in { padding:5px 9px; border:1px solid var(--border); border-radius:6px; font-size:13px; font-family:Consolas,Menlo,monospace; min-width:160px; }
.cg-path-in:focus { outline:none; border-color:#0969da; box-shadow:0 0 0 2px rgba(9,105,218,.15); }
.cg-path-arrow { color:#57606a; font-weight:700; }
.cg-path-btn { padding:5px 12px; border:1px solid var(--border); border-radius:6px; background:#f6f8fa; color:#0969da; font-size:12px; cursor:pointer; }
.cg-path-btn:hover { background:#eaeef2; }
.cg-path-clear { color:#57606a; }
.cg-path-result { margin-top:8px; font-size:13px; }
.cg-path-msg { color:#9a6700; padding:4px 0; }
.cg-path-list { margin:4px 0 0; padding-left:22px; }
.cg-path-list li { padding:2px 0; }
.cg-path-node { cursor:default; }
.cg-path-node:hover { background:#ddf4ff; }
/* C3：暗色主题（data-theme="dark"）——GitHub Dark 语义覆盖关键硬编码颜色 */
:root[data-theme="dark"] { --accent:#1f6feb; --bg:#0d1117; --border:#30363d; }
:root[data-theme="dark"] body { background:#0d1117; color:#c9d1d9; }
:root[data-theme="dark"] header { background:#161b22; }
:root[data-theme="dark"] table, :root[data-theme="dark"] pre, :root[data-theme="dark"] .tree,
:root[data-theme="dark"] .src, :root[data-theme="dark"] .func-card, :root[data-theme="dark"] .stat,
:root[data-theme="dark"] .cg-wrap, :root[data-theme="dark"] .cg-local, :root[data-theme="dark"] .hs-col,
:root[data-theme="dark"] .impact-block, :root[data-theme="dark"] .cg-hover-card { background:#161b22; }
:root[data-theme="dark"] th { background:#21262d; }
:root[data-theme="dark"] tr:hover td { background:#1c2128; }
:root[data-theme="dark"] code { background:#1b1f24; }
:root[data-theme="dark"] .muted { color:#8b949e; }
:root[data-theme="dark"] a { color:#58a6ff; }
:root[data-theme="dark"] .src td.ln { background:#161b22; color:#8b949e; border-right-color:#30363d; }
:root[data-theme="dark"] .src tr.fdef td { background:#1c2a3a; }
:root[data-theme="dark"] .src tr.fdef td.ln { background:#13233a; }
:root[data-theme="dark"] .src tr:hover td { background:#1c2128; }
/* P-rev R59：删除冗余的暗色 .tk-* 覆盖——R47 起语法色统一走 --syntax-* 令牌，
   浅/深主题各在 :root 定义一次，此处逐类硬编码会与令牌脱节（且正是 R59 契约
   要消除的「语法色不走令牌」反例）。 */
:root[data-theme="dark"] .src table tr.comment-line > td { background:#161b22; }
/* P-rev R37：文件头注释折叠为单行占位——避免在源码体里重复展示已在信息卡中
   完整呈现的元数据，保留行号准确，用户可点开查看原始文本 */
.src-hdr-fold > td { background:transparent !important; }
.src-hdr-fold > td.code { color:var(--muted); font-style:italic; }
.src-hdr-details summary { cursor:pointer; padding:2px 6px;
 background:rgba(0,114,198,.06); border-radius:4px; display:inline-block; }
/* P-rev R55：块注释折叠占位（复用文件头折叠视觉，但配色区分块注释） */
.src-blk-details summary { cursor:pointer; padding:2px 6px;
 background:rgba(130,80,223,.08); color:#8250df; border-radius:4px; display:inline-block; }
:root[data-theme="dark"] .src-blk-details summary { background:rgba(210,168,255,.12); color:#d2a8ff; }
:root[data-theme="dark"] .src-hdr-details summary { background:rgba(255,255,255,.06); }
.src-hdr-hint { margin-left:8px; font-size:11px; color:var(--muted); }
/* P-rev R50：块注释 %{ %} 边界行用独立强调，视觉上「成块」 */
.src tr.block-comment-edge > td.code { border-left:4px solid var(--accent); }
.src tr.block-comment-edge > td { font-weight:500; }
/* P-rev R38：参考文献 [N]] 徽章——一眼能看见每条独立条目 */
.ref-badge { display:inline-block; min-width:24px; padding:1px 6px; margin-right:6px;
 background:rgba(0,114,198,.1); color:var(--accent); border-radius:10px;
 font-weight:600; font-size:11px; }
/* P-rev R40：预览导航位置/进度显示 */
.cg-hover-pos { margin-right:8px; font-size:11px; color:var(--muted); }
.cg-hover-btn[disabled] { opacity:.45; cursor:not-allowed; }
:root[data-theme="dark"] .hs-col { border-color:#30363d; }
:root[data-theme="dark"] .cg-ctrl button, :root[data-theme="dark"] .cg-path-btn,
:root[data-theme="dark"] .cg-share-btn, :root[data-theme="dark"] .cg-hover-btn,
:root[data-theme="dark"] .xf-toggle { background:#21262d; border-color:#30363d; color:#c9d1d9; }
:root[data-theme="dark"] .badge { background:#21262d; }
:root[data-theme="dark"] .cg-hover-desc { color:#8b949e; border-top-color:#30363d; }
:root[data-theme="dark"] .cg-hover-k, :root[data-theme="dark"] .cg-hover-kind { color:#8b949e; background:#21262d; }
:root[data-theme="dark"] .cg-title, :root[data-theme="dark"] .impact-col b { color:#c9d1d9; }
:root[data-theme="dark"] .callgraph, :root[data-theme="dark"] .cg-hover-card { background:#161b22; }
.theme-toggle { padding:4px 10px; border:1px solid #30363d; border-radius:6px;
  background:transparent; color:#9ecbff; font-size:13px; cursor:pointer; }
.theme-toggle:hover { background:#21262d; }
/* C3：文件概览卡片 */
.file-overview { background:#fff; border:1px solid var(--border); border-left:5px solid var(--accent);
  border-radius:8px; padding:12px 16px; margin:0 0 14px; }
.file-overview h2 { margin:0 0 6px; font-size:16px; border:none; padding:0; }
.file-overview .fo-desc { color:#424a53; font-size:13px; margin:4px 0; }
.file-overview .fo-meta { font-size:12px; color:#57606a; display:flex; gap:16px; flex-wrap:wrap; margin-top:6px; }
:root[data-theme="dark"] .file-overview { background:#161b22; }
:root[data-theme="dark"] .file-overview .fo-desc { color:#c9d1d9; }
/* C3：文件描述（目录页文件列表） */
.dir-file-desc { color:#57606a; font-size:12px; margin:2px 0 0; }
:root[data-theme="dark"] .dir-file-desc { color:#8b949e; }
/* C3：可折叠目录树 */
.tree details { margin-left:1.2em; }
.tree summary { cursor:pointer; color:var(--accent); font-weight:600; }
.tree details > summary { list-style:none; }
.tree details > summary::-webkit-details-marker { display:none; }
.tree details[open] > summary { color:#1f2328; }
:root[data-theme="dark"] .tree details[open] > summary { color:#c9d1d9; }
/* C3：导航分组分隔符 */
.nav-sep { color:#57606a; margin:0 8px 0 14px; font-size:13px; }
:root[data-theme="dark"] .nav-sep { color:#484f58; }
/* P225-I：分组导航 + 移动端折叠（治本解决首页 30 链接平铺溢出） */
.nav-toggle{display:none;border:1px solid #30363d;background:#21262d;color:#fff;border-radius:6px;padding:6px 12px;font-size:13px;cursor:pointer;margin-left:auto;}
.topnav{display:flex;flex-wrap:wrap;gap:2px 0;align-items:center;flex:1 1 auto;}
.nav-group{display:inline-flex;align-items:center;flex-wrap:wrap;margin-right:8px;padding-right:8px;border-right:1px solid #21262d;}
.nav-group:last-of-type{border-right:none;}
.nav-group-label{color:#8b949e;font-size:11px;margin:0 6px 0 2px;letter-spacing:.5px;user-select:none;}
.nav-group .nav-link{margin:0 10px 0 0;font-size:13px;}
.nav-group .nav-link.active{color:#fff;background:rgba(31,111,235,.35);padding:2px 8px;border-radius:6px;text-decoration:none;}
.nav-group .nav-link.active:hover{text-decoration:none;}
@media (max-width:880px){
  header{padding:8px 10px;}
  .nav-toggle{display:inline-block;}
  .topnav{display:none;width:100%;margin-top:6px;}
  .topnav.open{display:flex;flex-direction:column;align-items:stretch;}
  .nav-group{flex-direction:column;align-items:stretch;margin:0 0 6px;padding:0 0 6px;border-right:none;border-bottom:1px solid #21262d;}
  .nav-group:last-of-type{border-bottom:none;margin-bottom:0;}
  .nav-group-label{text-align:left;margin:4px 0;}
  .nav-group .nav-link{margin:1px 0;padding:8px 4px;}
  .nav-group .nav-link.active{padding:8px 10px;}
}
/* C3：函数索引分组（按目录） */
.fn-group { margin:8px 0; }
.fn-group summary { cursor:pointer; font-size:14px; padding:4px 0; }
/* ================= P103：面包屑 ================= */
.crumbs { font-size:12.5px; color:#57606a; padding:6px 14px; background:#f6f8fa;
  border-bottom:1px solid #d0d7de; word-break:break-all; }
:root[data-theme="dark"] .crumbs { color:#8b949e; background:#161b22; border-color:#30363d; }
.crumbs a { color:var(--accent); text-decoration:none; }
.crumbs a:hover { text-decoration:underline; }
.crumbs .crumb-cur { font-weight:600; color:#1f2328; }
:root[data-theme="dark"] .crumbs .crumb-cur { color:#c9d1d9; }
/* ================= P105：源码页左侧函数大纲 ================= */
.src-wrap { display:flex; gap:0; align-items:flex-start; }
.src-outline { flex:0 0 190px; max-width:190px; position:sticky; top:0;
  max-height:calc(100vh - 30px); overflow:auto; padding:8px 10px; font-size:12px;
  border-right:1px solid #d8dee4; background:#fbfcfd; }
:root[data-theme="dark"] .src-outline { background:#0d1117; border-color:#30363d; }
.src-outline h4 { margin:2px 0 6px; font-size:11px; text-transform:uppercase;
  color:#57606a; letter-spacing:.05em; }
:root[data-theme="dark"] .src-outline h4 { color:#8b949e; }
.src-outline a { display:block; color:var(--accent); text-decoration:none;
  padding:2px 6px; border-radius:4px; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; }
.src-outline a:hover { background:#eaeef2; }
:root[data-theme="dark"] .src-outline a:hover { background:#21262d; }
.src-outline a.so-cur { background:var(--accent); color:#fff; font-weight:600; }
.src-code { flex:1 1 auto; min-width:0; }
/* ================= P104：函数详情页 ================= */
#fd-root { padding:4px 0 40px; }
.fd-sig { font:600 15px/1.5 ui-monospace,Consolas,monospace; padding:14px 16px;
  background:#f6f8fa; border:1px solid #d8dee4; border-left:4px solid var(--accent);
  border-radius:8px; word-break:break-all; }
:root[data-theme="dark"] .fd-sig { background:#161b22; border-color:#30363d; }
.fd-badges { padding:10px 0; display:flex; flex-wrap:wrap; gap:6px; }
.fd-badges .bd { font-size:12px; padding:3px 10px; border-radius:999px;
  background:#eaeef2; color:#1f2328; text-decoration:none; }
:root[data-theme="dark"] .fd-badges .bd { background:#21262d; color:#c9d1d9; }
.fd-badges .bd-kind { background:var(--accent); color:#fff; }
.fd-badges .bd-warn { background:#fff4e5; color:#9a6700; border:1px solid #d4a72c; }
.fd-badges .bd-todo { background:#e6f4ff; color:#0969da; border:1px solid #54aeff; }
.fd-actions { padding:6px 0 12px; display:flex; gap:8px; }
.fd-actions .btn { font-size:13px; padding:6px 14px; border-radius:6px;
  border:1px solid #d0d7de; color:#1f2328; background:#fff; text-decoration:none; }
:root[data-theme="dark"] .fd-actions .btn { color:#c9d1d9; background:#21262d; border-color:#30363d; }
.fd-actions .btn:hover { border-color:var(--accent); color:var(--accent); }
.fd-actions .btn.on { background:var(--accent); color:#fff; border-color:var(--accent); }
.fd-builtins { margin:14px 0; padding:12px 16px; border:1px solid var(--border); border-radius:8px; background:var(--surface-2); }
.fd-builtins h3 { margin:0 0 8px; font-size:14px; }
.fd-builtins ul { margin:0; padding-left:18px; }
.fd-builtins li { font-size:13px; line-height:1.7; }
.fd-builtins .bd-name { font-weight:600; color:var(--syntax-builtin); }
.bd-table { width:100%; border-collapse:collapse; margin:6px 0 2px; font-size:13px; }
.bd-table th, .bd-table td { border:1px solid var(--border); padding:6px 10px; text-align:left; vertical-align:top; }
.bd-table th { background:var(--surface-3); font-weight:600; }
.bd-table td.bd-name { white-space:nowrap; }
tr.bd-missing td { background:rgba(255,170,0,0.08); }
.bd-search { width:100%; box-sizing:border-box; padding:10px 14px; margin:10px 0 16px; font-size:14px; border:1px solid var(--border); border-radius:8px; background:var(--surface); color:var(--fg); }
.bd-func { margin:18px 0; padding:14px 16px; border:1px solid var(--border); border-radius:10px; background:var(--surface-2); }
.bd-func h3 { margin:0 0 10px; font-size:15px; }
.bd-fname { color:var(--syntax-func); }
.bd-banner { margin:8px 0 12px; font-size:14px; }
.bd-banner .warn { color:#c0392b; font-weight:600; }
.bd-toolbar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
.bd-toolbar .bd-search { flex:1 1 320px; margin:0; }
.bd-sig { font-family:var(--mono, monospace); font-size:12px; color:var(--muted); white-space:nowrap; }
.bd-table td.bd-sig { color:var(--muted); }
.fd-flow { margin:10px 0; border:1px solid #d0d7de; border-radius:6px; padding:8px 12px; background:#fafbfc; }
.fd-flow h3 { margin:4px 0 6px; font-size:13px; color:#57606a; }
.fd-flow ul { margin:0; padding-left:18px; }
.fd-flow li { font-size:13px; color:#475569; margin:2px 0; }
.fd-flow-empty { color:#8b949e; font-size:13px; margin:4px 0; }
.fd-flow-svg { max-width:600px; }
.fd-flow-edge { stroke-width:1.4; }
.fd-flow-edge.in { stroke:#d1242f; stroke-dasharray:4 3; }
.fd-flow-edge.out { stroke:#0969da; stroke-dasharray:2 2; }
.fd-flow-node { stroke-width:1; }
.fd-flow-node.in { fill:#ffebe9; stroke:#d1242f; }
.fd-flow-node.out { fill:#ddf4ff; stroke:#0969da; }
:root[data-theme="dark"] .fd-flow-node.in { fill:#21262d; stroke:#f85149; }
:root[data-theme="dark"] .fd-flow-node.out { fill:#0d1117; stroke:#58a6ff; }
.fd-flow-node.cur { fill:var(--accent); stroke:var(--accent); }
.fd-flow-t { font:600 11px ui-monospace,Consolas,monospace; fill:#1f2328; }
.fd-flow-t.cur-t { fill:#fff; }
:root[data-theme="dark"] .fd-flow-t { fill:#c9d1d9; }
.fd-flow-legend { font-size:12px; color:#57606a; margin:6px 0 0; }
.fd-suggest { margin:8px 0 0; border:1px solid #f1c0c0; border-radius:6px; padding:6px 10px; background:#fff5f5; }
.fd-suggest h4 { margin:2px 0 4px; font-size:13px; color:#a4133c; }
.fd-suggest ul { margin:0; padding-left:18px; }
.fd-suggest li { font-size:13px; color:#7a2e2e; margin:3px 0; }
.fd-sug-conf { font-size:11px; color:#9a6700; background:#fff4e5; border-radius:8px; padding:0 6px; margin-left:4px; }
.fd-title { margin:10px 0 4px; font-size:22px; }
.fd-cg { margin:10px 0; }
.fd-cg h3, .fd-col h3 { font-size:13px; color:#57606a; margin:10px 0 6px; }
:root[data-theme="dark"] .fd-cg h3, :root[data-theme="dark"] .fd-col h3 { color:#8b949e; }
.fd-svg { width:100%; max-width:760px; border:1px solid #d8dee4; border-radius:8px;
  background:#fcfdfe; }
:root[data-theme="dark"] .fd-svg { background:#0d1117; border-color:#30363d; }
.fd-node { fill:#eaeef2; stroke:#8b949e; }
:root[data-theme="dark"] .fd-node { fill:#21262d; stroke:#484f58; }
.fd-cur { fill:var(--accent); stroke:var(--accent); }
.fd-node-t { font:600 11px ui-monospace,Consolas,monospace; fill:#1f2328; }
:root[data-theme="dark"] .fd-node-t { fill:#c9d1d9; }
.fd-cur-t { fill:#fff; }
.fd-edge { stroke:#8b949e; stroke-width:1.2; stroke-dasharray:4 3; }
.fd-cols { display:flex; gap:24px; flex-wrap:wrap; }
.fd-col { flex:1 1 300px; min-width:260px; }
.fd-col ul { list-style:none; margin:0; padding:0; }
.fd-col li { padding:3px 0; font-size:13px; }
.fd-fn { color:var(--accent); text-decoration:none; font-weight:600; }
.fd-fn:hover { text-decoration:underline; }
.fd-loc { color:#8b949e; font-size:11.5px; }
.fd-loading { color:#57606a; padding:30px; text-align:center; }
.fd-empty { padding:30px; text-align:center; color:#57606a; }
/* ================= P111：度量雷达 ================= */
.radar { display:inline-block; vertical-align:middle; }
.card-metric { display:flex; align-items:center; gap:10px; }
.card-metric-txt { font-size:12px; color:#57606a; }
:root[data-theme="dark"] .card-metric-txt { color:#8b949e; }
/* ================= P107：全局搜索浮层 ================= */
#gsearch-ovl { display:none; position:fixed; inset:0; z-index:999;
  background:rgba(13,17,23,.55); }
#gsearch-ovl.open { display:flex; align-items:flex-start; justify-content:center; }
#gsearch-panel { margin-top:9vh; width:min(640px,92vw); background:#fff; color:#1f2328;
  border-radius:12px; box-shadow:0 12px 40px rgba(0,0,0,.25); overflow:hidden; }
:root[data-theme="dark"] #gsearch-panel { background:#161b22; color:#c9d1d9; }
#gsearch-input { width:100%; box-sizing:border-box; border:none; outline:none;
  padding:14px 16px; font-size:15px; background:transparent; color:inherit; }
#gsearch-results { max-height:46vh; overflow:auto; border-top:1px solid #d8dee4; }
:root[data-theme="dark"] #gsearch-results { border-color:#30363d; }
#gsearch-results a { display:flex; justify-content:space-between; gap:10px; padding:8px 16px;
  text-decoration:none; color:inherit; }
#gsearch-results a:hover, #gsearch-results a.hl { background:#eaeef2; }
:root[data-theme="dark"] #gsearch-results a:hover,
:root[data-theme="dark"] #gsearch-results a.hl { background:#21262d; }
.gs-n { font-weight:600; color:var(--accent); font-family:ui-monospace,Consolas,monospace; }
.gs-loc { font-size:11.5px; color:#8b949e; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; }
.gs-badges { display:inline-flex; gap:4px; flex-wrap:wrap; align-items:center; }
.gs-b { font-size:10px; line-height:1; padding:2px 5px; border-radius:6px; font-weight:600; white-space:nowrap; }
.gs-b-t { background:#ffe3e3; color:#b42318; }
.gs-b-hd { background:#fff4e0; color:#9a6700; }
.gs-b-hi { background:#e7f0ff; color:#0b5cad; }
.gs-b-dup { background:#efe7ff; color:#6940b8; }
/* P270：命令面板「目标类型」徽标（函数/文件/目录/全局变量） */
.gs-b-kind { background:#eef1f5; color:#57606a; border:1px solid #d8dee4; }
:root[data-theme="dark"] .gs-b-t { background:#3d1d1d; color:#ff9b94; }
:root[data-theme="dark"] .gs-b-hd { background:#3a2e15; color:#f0c674; }
:root[data-theme="dark"] .gs-b-hi { background:#16263d; color:#79b8ff; }
:root[data-theme="dark"] .gs-b-dup { background:#2a1d3d; color:#c8a4ff; }
:root[data-theme="dark"] .gs-b-kind { background:#21262d; color:#c9d1d9; border-color:#30363d; }
#gsearch-hint { font-size:11px; color:#8b949e; padding:8px 16px; border-top:1px solid #d8dee4; }
:root[data-theme="dark"] #gsearch-hint { border-color:#30363d; }
#gsearch-hint b { color:#57606a; font-weight:600; }
:root[data-theme="dark"] #gsearch-hint b { color:#c9d1d9; }
/* P271 R4：最近访问分组标题 */
#gsearch-results .gs-recent-tip { font-size:11px; color:#8b949e; padding:6px 16px 2px; letter-spacing:.3px; }
:root[data-theme="dark"] #gsearch-results .gs-recent-tip { color:#8b949e; }
/* P271 R5-3：预览面板 —— 不跳转即可查看选中项详情（MCP resources「按需读取」的思路） */
#gsearch-body { display:flex; align-items:stretch; min-height:0; }
#gsearch-results { flex:1 1 auto; min-width:0; }
#gsearch-preview { flex:0 0 40%; max-width:280px; overflow:auto;
  border-left:1px solid #d8dee4; padding:0; background:#f6f8fa; }
#gsearch-preview:empty { display:none; }
:root[data-theme="dark"] #gsearch-preview { background:#161b22; border-color:#30363d; }
.gp-title { font-size:13px; font-weight:600; padding:10px 12px 4px; word-break:break-all; }
.gp-row { display:flex; gap:8px; font-size:12px; padding:2px 12px; }
.gp-k { color:#8b949e; flex:0 0 62px; }
.gp-v { color:#24292f; word-break:break-all; }
:root[data-theme="dark"] .gp-v { color:#c9d1d9; }
.gp-code { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:11px; padding:6px 12px; margin:4px 8px; background:#fff;
  border:1px solid #d8dee4; border-radius:6px; white-space:pre-wrap; word-break:break-all; }
:root[data-theme="dark"] .gp-code { background:#0d1117; border-color:#30363d; }
.gp-foot { font-size:11px; color:#8b949e; padding:8px 12px 10px; border-top:1px solid #d8dee4;
  margin-top:6px; }
:root[data-theme="dark"] .gp-foot { border-color:#30363d; }
/* 窄屏：预览改为堆叠在结果下方，避免两栏都挤得没法看 */
@media (max-width:720px){
  #gsearch-body { flex-direction:column; }
  #gsearch-preview { flex:none; max-width:none; border-left:none;
    border-top:1px solid #d8dee4; max-height:32vh; }
}
/* P271 R5-2：结果分组标题（同类结果聚在一起，比一长串混排更易扫读） */
#gsearch-results .gs-group { font-size:11px; font-weight:600; color:#8b949e;
  padding:8px 16px 3px; letter-spacing:.5px; text-transform:none; }
#gsearch-results .gs-group:not(:first-child) { margin-top:4px; border-top:1px solid #eaeef2; }
:root[data-theme="dark"] #gsearch-results .gs-group { color:#8b949e; }
:root[data-theme="dark"] #gsearch-results .gs-group:not(:first-child) { border-color:#21262d; }
/* P271 R5-1：作用域提示条——限定范围后必须让用户看见，否则会以为「搜不到」 */
#gsearch-results .gs-scope-tip { font-size:11px; color:#57606a; padding:7px 16px 3px;
  background:#f6f8fa; border-bottom:1px solid #d8dee4; }
#gsearch-results .gs-scope-tip b { color:#0969da; font-weight:600; }
:root[data-theme="dark"] #gsearch-results .gs-scope-tip { background:#161b22; color:#c9d1d9; border-color:#30363d; }
:root[data-theme="dark"] #gsearch-results .gs-scope-tip b { color:#58a6ff; }
/* P270 R4：键盘帮助浮层 */
#kbd-help { position:fixed; inset:0; background:rgba(27,31,36,.5); display:none;
  align-items:center; justify-content:center; z-index:10000; }
.kbd-card { background:var(--card,#fff); color:var(--fg,#1f2328); border-radius:12px;
  box-shadow:0 12px 40px rgba(0,0,0,.3); min-width:320px; max-width:90vw; overflow:hidden; }
.kbd-head { display:flex; justify-content:space-between; align-items:center; padding:12px 16px;
  font-weight:700; border-bottom:1px solid #d8dee4; }
.kbd-x { cursor:pointer; padding:2px 6px; border-radius:6px; }
.kbd-x:hover { background:#eaeef2; }
.kbd-tbl { width:100%; border-collapse:collapse; font-size:13px; }
.kbd-tbl td { padding:7px 16px; border-bottom:1px solid #f0f2f4; }
.kbd-k { font-family:ui-monospace,Consolas,monospace; font-weight:700; color:var(--accent,#0969da); white-space:nowrap; width:1%; }
.kbd-foot { padding:10px 16px; font-size:11px; color:#8b949e; }
:root[data-theme="dark"] .kbd-card { background:#161b22; color:#c9d1d9; }
:root[data-theme="dark"] .kbd-head { border-color:#30363d; }
:root[data-theme="dark"] .kbd-x:hover { background:#21262d; }
:root[data-theme="dark"] .kbd-tbl td { border-color:#21262d; }
/* P270 R4：可访问性——跳转主内容链接（仅键盘聚焦时可见） */
.skip-link { position:absolute; left:-999px; top:4px; z-index:10001; padding:6px 12px;
  background:var(--accent,#0969da); color:#fff; border-radius:6px; }
.skip-link:focus { left:8px; }
/* ================= P108：响应式 ================= */
/* ================= P271 R2：Toast 反馈 =================
   用于所有「复制到剪贴板」等操作——没有反馈时，用户分不清是成功了还是静默失败。 */
.cg-toast { position:fixed; left:50%; bottom:28px; transform:translate(-50%, 12px);
  z-index:10002; max-width:min(92vw, 460px); padding:9px 16px; border-radius:8px;
  background:#1f2328; color:#fff; font-size:13px; line-height:1.5;
  box-shadow:0 6px 20px rgba(0,0,0,.22); opacity:0; pointer-events:none;
  transition:opacity .18s ease, transform .18s ease; }
.cg-toast.show { opacity:1; transform:translate(-50%, 0); }
.cg-toast.cg-toast-ok { background:#1a7f37; }
.cg-toast.cg-toast-err { background:#b42318; }
:root[data-theme="dark"] .cg-toast { background:#f0f6fc; color:#0d1117; }
:root[data-theme="dark"] .cg-toast.cg-toast-ok { background:#238636; color:#fff; }
:root[data-theme="dark"] .cg-toast.cg-toast-err { background:#b62324; color:#fff; }

/* P271 R2：尊重系统「减少动效」偏好。
   前庭功能敏感/易晕动的用户开启该偏好后，脉冲高亮、平滑滚动、Toast 过渡
   都会引起不适。这里统一降级为无动画（功能完全保留，只是不动）。 */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration:.001ms !important;
    animation-iteration-count:1 !important;
    transition-duration:.001ms !important;
    scroll-behavior:auto !important;
  }
}

/* P271 R2：尊重系统「高对比度」偏好，提升弱视用户的可读性。 */
@media (prefers-contrast: more) {
  :root { --border:#0d1117; --muted:#24292f; }
  body { color:#0d1117; }
  a { text-decoration:underline; }
  table th, table td { border-color:#0d1117; }
  .cg-toast { outline:2px solid #fff; }
}

@media (max-width:900px){
  .src-wrap { flex-direction:column; }
  .src-outline { position:static; max-width:none; width:100%; max-height:180px;
    border-right:none; border-bottom:1px solid #d8dee4; }
  .fd-cols { flex-direction:column; }
  /* P271 R1：宽表（如 12 列的度量表）在窄屏会被挤成不可读的竖条，
     改为「块级 + 横向滚动」，配合已补齐的 viewport 才真正可用。 */
  .page-main table, main table, .metrics-tbl, .folder-stats table,
  .fd-table, .fh-table, .src table {
    display:block; overflow-x:auto; -webkit-overflow-scrolling:touch;
  }
}
@media (max-width:640px){
  .site-head .head-in { flex-wrap:wrap; gap:4px; }
  .crumbs { font-size:11px; padding:4px 8px; }
  /* P271 R1：头部导航链接较多，窄屏需换行且给足点击间距（≥32px 触摸目标） */
  header > a, header .nav-link, .nav-link {
    display:inline-block; margin:2px 6px 2px 0; padding:6px 2px;
  }
  .src td.ln { width:40px; padding-right:6px; font-size:11px; }
  #gsearch-results a { padding:8px 12px; }
  #gsearch-panel { margin-top:4vh; }
  /* P-rev S5：移动优先交互——卡片堆叠、触摸目标加大、命令面板全宽 */
  .wizard { grid-template-columns:1fr; }
  .wizard .task { padding:14px 16px; }
  .ug-btn, .ug-check { min-height:36px; padding:8px 12px; font-size:14px; }
  #gsearch-ovl { align-items:flex-end; }
  #gsearch-panel { width:100%; max-width:100%; margin:0; border-radius:14px 14px 0 0; max-height:80vh; }
  .wb-dock { right:10px; bottom:10px; }
  .wb-toggle { width:54px; height:54px; font-size:24px; }
  .wb-panel { width:88vw; max-width:340px; }
  /* 触屏无 hover：代码行加分隔线代替悬停底色 */
  .code-row { border-bottom:1px solid #f0f3f6; }
  .code-edit[contenteditable="true"] { min-height:1.4em; }
  .edit-badge { display:block; margin:6px 0 0; }
  header { padding:8px 10px; }
}
/* ================= P112：打印样式 ================= */
@media print {
  nav, header, .tree, .src-outline, .fd-actions, #gsearch-ovl, .crumbs a { display:none !important; }
  .page-main { padding:0 !important; }
  body { background:#fff !important; color:#000 !important; }
  .src-code pre, .src-code pre code { background:#fff !important; color:#000 !important; }
  .fd-svg { max-width:100%; page-break-inside:avoid; }
}
/* ===== c_report / p203 专用规则（FE-21 合并进 browse.css，统一外部化） ===== */
.stats-cards{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0;}
.stat-card{flex:1;min-width:120px;border:1px solid #d0d7de;border-radius:8px;
  padding:10px 14px;background:#f6f8fa;}
.stat-card .num{font-size:22px;font-weight:600;}
#c-table{border-collapse:collapse;font-size:12px;width:100%;}
#c-table th,#c-table td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;}
#c-table th{background:#f6f8fa;}
.mono{font-family:Consolas,Monaco,monospace;font-size:11px;}
code.inc{background:#f6f8fa;border:1px solid #d0d7de;border-radius:4px;
  padding:0 4px;margin:1px;}
.cx{font-weight:600;}
:root[data-theme="dark"] #c-table th{background:#161b22;}
:root[data-theme="dark"] code.inc{background:#161b22;border-color:#30363d;}
.folder-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:14px 0;}
.taint-path{font-family:Consolas,monospace;background:#fff;border:1px solid var(--border);border-radius:6px;padding:8px 12px;}
.e2e-chain{font-family:Consolas,monospace;background:#fff;border:1px solid var(--border);border-radius:6px;padding:10px 14px;white-space:pre-wrap;}
#p203-toolbar{margin:14px 0;}
.ug-btn{display:inline-block;margin:0 8px 8px 0;padding:8px 14px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--accent);cursor:pointer;text-decoration:none;}
.ug-btn:hover{text-decoration:none;box-shadow:0 4px 12px rgba(0,114,198,.15);}
/* ===== P225-K：补齐「样式孤儿」（HTML 引用但 CSS 零定义）=====
 * 缘起：全站审计发现 24 个 class 被页面使用却无任何 CSS 定义——其中
 * .site-header/.topbar/.container/.content/.data-table 是结构骨架类，缺失时
 * 多个独立页面（合规/总览/标定/维度/算子影响/变量流/目录矩阵/函数库）布局退化。
 * 统一在此补齐，作为 BROWSE_CSS 唯一事实来源的一部分。 */
/* — 独立页头部/骨架 — */
.site-header{display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between;
  padding:12px 18px;margin:-18px -18px 18px;border-bottom:1px solid var(--border);background:var(--surface);}
.site-header .brand-sub{display:block;font-size:12px;color:var(--muted);font-weight:400;margin-top:2px;}
.topbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:8px 12px;margin-bottom:14px;
  border:1px solid var(--border);border-radius:8px;background:var(--surface-alt,#f6f8fa);font-size:13px;}
.topbar a{color:var(--accent);text-decoration:none;}
.topbar a:hover{text-decoration:underline;}
.container{max-width:1180px;margin:0 auto;padding:18px;}
.content{max-width:1180px;margin:0 auto;}
.data-table{border-collapse:collapse;width:100%;font-size:12.5px;margin:12px 0;background:var(--surface);}
.data-table th,.data-table td{border:1px solid var(--border);padding:6px 9px;text-align:left;vertical-align:top;}
.data-table thead th{background:var(--surface-alt,#f6f8fa);position:sticky;top:0;z-index:1;}
.data-table tbody tr:nth-child(even){background:rgba(0,0,0,.02);}
.data-table-wrap{overflow-x:auto;}
/* — 合规审查得分卡（compliance.html） — */
.cmp-card{border:1px solid var(--border);border-left:4px solid var(--muted);border-radius:8px;
  padding:10px 14px;margin:8px 0;background:var(--surface);}
.cmp-ok{border-left-color:#1a7f37;background:rgba(26,127,55,.06);}
.cmp-error{border-left-color:#cf222e;background:rgba(207,34,46,.06);}
.cmp-warning{border-left-color:#9a6700;background:rgba(154,103,0,.07);}
.cmp-suggestion{border-left-color:#0969da;background:rgba(9,105,218,.06);}
.cmp-score-meta{font-size:12px;color:var(--muted);margin-top:4px;}
/* — 总览/算子/变量流/目录矩阵 局部组件 — */
.ov-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:14px 0;}
.ov-card{border:1px solid var(--border);border-radius:8px;padding:12px 14px;background:var(--surface);}
.ov-row{display:flex;justify-content:space-between;gap:10px;padding:4px 0;font-size:13px;border-bottom:1px dashed var(--border);}
.op-fired{color:#1a7f37;font-weight:600;}
.op-zero{color:var(--muted);}
.vf-c-dim{color:var(--muted);opacity:.75;}
.dm-col{border-right:1px solid var(--border);padding:0 8px;}
.bd-calib{font-weight:600;color:var(--accent);}
.bd-c-calib{color:var(--accent);}
.bd-na{color:var(--muted);font-style:italic;}
.bd-note{font-size:12px;color:var(--muted);margin:6px 0;}
.bd-rev-results{border:1px solid var(--border);border-radius:6px;padding:8px 12px;margin:8px 0;background:var(--surface);}
.bd-toast{position:fixed;right:16px;bottom:16px;z-index:9999;background:#24292f;color:#fff;
  border-radius:8px;padding:10px 14px;font-size:13px;box-shadow:0 6px 20px rgba(0,0,0,.3);}
.bi-sig{font-family:Consolas,Monaco,monospace;font-size:12px;color:var(--accent);}
.fn-friendly-desc{font-size:12.5px;color:var(--muted);margin:4px 0 8px;}
.sc-note{font-size:12px;color:var(--muted);border-left:3px solid var(--border);padding-left:8px;margin:8px 0;}
:root[data-theme="dark"] .topbar{background:#161b22;}
:root[data-theme="dark"] .data-table thead th{background:#161b22;}
:root[data-theme="dark"] .data-table tbody tr:nth-child(even){background:rgba(255,255,255,.03);}
"""

def write_browse_css_tree(outdir):
    """FE-21：将统一 stylesheet 写入站点根目录，并复制到每个含 .html 的子目录，
    使任意深度的页面用相对 href="browse.css" 均可解析（避免逐页内联 <style>）。
    样式源优先取 page_css/browse.css（与 page_css 体系一致、单一事实来源），
    缺失时回退到 BROWSE_CSS 常量，保证向后兼容。"""
    outdir = str(outdir)
    if not os.path.isdir(outdir):
        return
    _here = os.path.dirname(os.path.abspath(__file__))
    # P225-J：BROWSE_CSS 常量为唯一事实来源；page_css/browse.css 为「镜像产物」。
    # 若镜像与常量漂移（曾导致线上顶栏溢出：镜像缺 flex-wrap/导航折叠 CSS），
    # 以常量为准并告警，同时把镜像回写为新内容，杜绝「落盘滞后于代码」再次发生。
    for _cand in (os.path.join(_here, "page_css", "browse.css"),
                  os.path.join(os.path.dirname(_here), "assets", "page_css", "browse.css")):
        if os.path.isfile(_cand):
            with open(_cand, "r", encoding="utf-8") as _bf:
                _mirror = _bf.read()
            if _mirror != BROWSE_CSS:
                sys.stderr.write(
                    "[write_browse_css_tree] WARN: 镜像样式表与 BROWSE_CSS 漂移，"
                    "已以常量为准并回写镜像: %s\n" % _cand)
                try:
                    with open(_cand, "w", encoding="utf-8", newline="\n") as _wf:
                        _wf.write(BROWSE_CSS)
                except (IOError, OSError) as _e:
                    sys.stderr.write("[write_browse_css_tree] WARN: 镜像回写失败: %s\n" % _e)
            break
    _css_text = BROWSE_CSS
    root_css = os.path.join(outdir, "browse.css")
    with open(root_css, "w", encoding="utf-8") as _f:
        _f.write(_css_text)
    for _dirpath, _dirnames, _filenames in os.walk(outdir):
        if _dirpath == outdir:
            continue
        if any(_fn.endswith(".html") for _fn in _filenames):
            _dst = os.path.join(_dirpath, "browse.css")
            if not os.path.exists(_dst):
                shutil.copyfile(root_css, _dst)


PAGE_CSS_FILES = ("todo.css", "taint.css", "watch.css", "search.css",
                  "diff.css", "dims.css", "src_dim.css", "float_nav.css", "sfn.css",
                  "dm.css",
                  "structure.css", "focus.css", "varflow.css", "schedule.css")

# 由 write_browse_css_tree 单独管理的样式表：不从 PAGE_CSS_FILES 复制，
# 但也不应被「孤儿样式表」检查误报（它不是未链接，而是走另一条复制路径）。
BROWSE_MANAGED_CSS = ("browse.css",)


def write_page_css_tree(outdir):
    """FE-21：将各页专用样式表复制到站点根目录及每个含 .html 的子目录，
    消除逐页内联 <style>（S22）。每页仅链接自身 CSS，互不干扰（避免 .stat-card 等类名冲突）。"""
    outdir = str(outdir)
    if not os.path.isdir(outdir):
        return
    # page_css 目录相对本模块有两种可能布局（assets 为模块文件 renderers/assets.py，
    # 或包 renderers/assets/__init__.py），逐一尝试定位，避免路径假设错误导致静默空操作。
    _here = os.path.dirname(os.path.abspath(__file__))
    _src_dir = None
    for _cand in (os.path.join(_here, "page_css"),
                  os.path.join(_here, "assets", "page_css"),
                  os.path.join(os.path.dirname(_here), "assets", "page_css")):
        if os.path.isdir(_cand):
            _src_dir = _cand
            break
    if _src_dir is None:
        sys.stderr.write("[write_page_css_tree] WARN: 未找到 page_css 目录（候选: %s）\n"
                         % ", ".join([os.path.join(_here, "page_css"),
                                      os.path.join(_here, "assets", "page_css")]))
        return
    # 构建期守卫：PAGE_CSS_FILES 引用了不存在的样式表会导致悬空 <link>，尽早暴露
    for _name in PAGE_CSS_FILES:
        if not os.path.exists(os.path.join(_src_dir, _name)):
            sys.stderr.write(
                "[write_page_css_tree] WARN: PAGE_CSS_FILES 引用了不存在的样式表: %s\n" % _name)
    # 孤儿文件：page_css/ 下未被 PAGE_CSS_FILES 收录的 .css 不会被复制，提示清理。
    # 排除 BROWSE_MANAGED_CSS（由 write_browse_css_tree 独立复制），避免误报。
    for _fn in os.listdir(_src_dir):
        if (_fn.endswith(".css") and _fn not in PAGE_CSS_FILES
                and _fn not in BROWSE_MANAGED_CSS):
            sys.stderr.write(
                "[write_page_css_tree] WARN: page_css/ 存在未被链接的孤儿样式表: %s\n" % _fn)
    for _name in PAGE_CSS_FILES:
        _src = os.path.join(_src_dir, _name)
        if os.path.exists(_src):
            shutil.copyfile(_src, os.path.join(outdir, _name))
    for _dirpath, _dirnames, _filenames in os.walk(outdir):
        if _dirpath == outdir:
            continue
        if any(_fn.endswith(".html") for _fn in _filenames):
            for _name in PAGE_CSS_FILES:
                _src = os.path.join(_src_dir, _name)
                _dst = os.path.join(_dirpath, _name)
                if os.path.exists(_src) and not os.path.exists(_dst):
                    shutil.copyfile(_src, _dst)


CORE_JS = r"""
/* ================= P270：全站共享内核（主题） =================
 * 单一数据源：--browse 站点、report.html、global_state.html 复用同一份逻辑与
 * 同一个 localStorage key('gs-theme')，消除此前 3 份实现、key 互不统一的缺陷。
 * 优先级：URL ?theme=dark|light > localStorage > 系统 prefers-color-scheme。
 */
(function () {
  'use strict';
  var KEY = 'gs-theme';
  function apply(t) {
    try {
      if (t === 'dark') { document.documentElement.setAttribute('data-theme', 'dark'); }
      else { document.documentElement.removeAttribute('data-theme'); }
      if (t === 'dark' || t === 'light') { localStorage.setItem(KEY, t); }
    } catch (e) {}
  }
  window.applyTheme = apply;
  window.maToggleTheme = function () {
    var dark = document.documentElement.getAttribute('data-theme') === 'dark';
    apply(dark ? 'light' : 'dark');
  };
  /* P271 R2：全站共享 Toast。
   * 缘起：源码行「点击行号复制链接」此前**复制成功却没有任何反馈**——
   * 用户无法判断到底成了没有（静默失败与静默成功看起来一模一样）。
   * 所有「复制到剪贴板」类操作都应调用 window.__toast() 给出可见反馈。 */
  window.__toast = function (msg, kind) {
    try {
      var box = document.getElementById('cg-toast');
      if (!box) {
        box = document.createElement('div');
        box.id = 'cg-toast';
        box.setAttribute('role', 'status');
        box.setAttribute('aria-live', 'polite');
        document.body.appendChild(box);
      }
      box.textContent = msg || '';
      box.className = 'cg-toast show' + (kind ? (' cg-toast-' + kind) : '');
      if (window.__toastT) { clearTimeout(window.__toastT); }
      window.__toastT = setTimeout(function () { box.className = 'cg-toast'; }, 2200);
    } catch (e) {}
  };
  try {
    var m = /[?&]theme=(dark|light)/.exec(location.search || '');
    if (m) { apply(m[1]); return; }
    var s = localStorage.getItem(KEY);
    if (s === 'dark') { apply('dark'); return; }
    if (s === null && window.matchMedia &&
        window.matchMedia('(prefers-color-scheme: dark)').matches) {
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  } catch (e) {}
  // P271：可见主题按钮由共享内核统一注入（此前仅 browse 首页的 BROWSE_JS 注入，
  // 导致 report/global_state 等页主题切换体验不一致）。页面已自带按钮则不再重复。
  function injectToggle() {
    var hdr = document.querySelector('header');
    // R1：模板若已自带 #gs-theme 按钮（旧主题系统），不再重复注入，避免双按钮
    if (!hdr || document.getElementById('theme-toggle') || document.getElementById('gs-theme')) { return; }
    var btn = document.createElement('button');
    btn.id = 'theme-toggle';
    btn.className = 'theme-toggle';
    btn.setAttribute('aria-label', '切换暗色/亮色主题');
    var dark = document.documentElement.getAttribute('data-theme') === 'dark';
    btn.textContent = dark ? '☀ 浅色' : '🌙 暗色';
    btn.addEventListener('click', function () {
      window.maToggleTheme();
      var d = document.documentElement.getAttribute('data-theme') === 'dark';
      btn.textContent = d ? '☀ 浅色' : '🌙 暗色';
    });
    hdr.appendChild(btn);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectToggle);
  } else { injectToggle(); }
})();
"""

# P270 R3：可分享深链层——把视图状态（tab/筛选/排序/搜索）双向同步到 URL hash，
#           使任意视图可复制链接分享；同时保留 localStorage 偏好（个人默认）。
# 约定 hash 形如：#view=d&f=cross&sort=roi&q=foo&page=1  （仅含非空字段）
DEEPLINK_JS = r"""
(function(){
  'use strict';
  var KMAP = { tab:'tab', f:'f', sort:'sort', q:'q', page:'page' };
  function readHash(){
    var o = {};
    try {
      var raw = decodeURIComponent(String(location.hash || '').replace(/^#/, ''));
      raw.split('&').forEach(function(pair){
        if(!pair) return;
        var kv = pair.split('=');
        if(kv.length === 2) o[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1]);
      });
    } catch(e){}
    return o;
  }
  function writeHash(state){
    var parts = [];
    Object.keys(state).forEach(function(k){
      var v = state[k];
      if(v === '' || v == null || (k === 'f' && v === 'all') ||
         (k === 'page' && String(v) === '0')) return;
      parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
    });
    var cand = parts.length ? '#' + parts.join('&') : '';
    if(location.hash === cand) return;
    try { history.replaceState(null, '', cand || location.pathname + location.search); }
    catch(e){ try { location.hash = cand; } catch(_){} }
  }
  window.__DL_READ__ = readHash;
  window.__DL_WRITE__ = writeHash;
  window.__DL_HOOK__ = null;   // 页面注册：state() -> 对象；由页面在状态变更后调用 __dl_sync()
  window.__dl_sync = function(){
    if(typeof window.__DL_HOOK__ === 'function'){ writeHash(window.__DL_HOOK__()); }
  };
  window.__dl_load = function(){
    var h = readHash();
    var st = { tab:h.tab || '', f:h.f || 'all', sort:h.sort || '', q:h.q || '', page:h.page || '0' };
    return st;
  };
})();
"""

KBD_JS = r"""
(function(){
  'use strict';
  if (window.__KBD_LOADED__) return; window.__KBD_LOADED__ = true;
  var HELP = [
    ['?', '打开/关闭本帮助'],
    ['/', '命令面板：跳函数/文件/目录/全局变量'],
    ['Ctrl/Cmd + K', '命令面板（同上）'],
    ['t', '切换 暗色/浅色 主题'],
    ['g', '跳到「概览」区块（页面含 #gs-overview 时）'],
    ['d', '跳到「重复代码」看板（页面含 dup 工具条时）'],
    ['h', '返回站点首页（index.html，若存在）'],
    ['Alt+← / Alt+→', '调用链预览：上一步 / 下一步（穿梭探索历史）'],
    ['Esc', '关闭任意浮层 / 调用链预览 / 帮助'],
  ];
  function build(){
    if (document.getElementById('kbd-help')) return;
    var ov = document.createElement('div');
    ov.id = 'kbd-help'; ov.setAttribute('role','dialog'); ov.setAttribute('aria-modal','true');
    ov.setAttribute('aria-label','键盘快捷键帮助');
    var rows = HELP.map(function(p){return '<tr><td class="kbd-k">'+p[0]+'</td><td>'+p[1]+'</td></tr>';}).join('');
    ov.innerHTML = '<div class="kbd-card"><div class="kbd-head">键盘快捷键<span class="kbd-x" role="button" aria-label="关闭" tabindex="0">✕</span></div>'
      + '<table class="kbd-tbl">'+rows+'</table>'
      + '<div class="kbd-foot">再次按 ? 或 Esc 关闭</div></div>';
    ov.style.display = 'none';
    ov.addEventListener('click', function(e){ if(e.target===ov || (e.target.classList&&e.target.classList.contains('kbd-x'))) hide(); });
    document.body.appendChild(ov);
    ov.querySelector('.kbd-x').addEventListener('keydown', function(e){ if(e.key==='Enter'||e.key===' '){ hide(); } });
  }
  var lastFocus = null;
  function show(){ build(); var ov=document.getElementById('kbd-help'); if(!ov) return;
    ov.style.display='flex'; lastFocus=document.activeElement; var x=ov.querySelector('.kbd-x'); if(x)x.focus(); }
  function hide(){ var ov=document.getElementById('kbd-help'); if(!ov) return; ov.style.display='none';
    if(lastFocus&&lastFocus.focus) try{lastFocus.focus();}catch(e){} }
  function toggle(){ var ov=document.getElementById('kbd-help'); if(ov&&ov.style.display==='flex') hide(); else show(); }
  window.__kbd_toggle = toggle;
  document.addEventListener('keydown', function(e){
    var tag = (e.target && e.target.tagName) || '';
    var typing = tag==='INPUT' || tag==='TEXTAREA' || (e.target && e.target.isContentEditable);
    // 帮助浮层打开时，仅 Esc/? 生效
    var ov = document.getElementById('kbd-help');
    if(ov && ov.style.display==='flex'){
      if(e.key==='Escape' || (e.key==='?' && !typing)){ e.preventDefault(); hide(); }
      return;
    }
    if(e.key==='?' && !typing && !e.ctrlKey && !e.metaKey){ e.preventDefault(); show(); return; }
    if(typing) return;
    // P-rev R71：Alt+←/→ 在调用图预览页穿梭探索历史（上一/下一步）。
    // 需在 altKey 拦截前处理；无预览能力（普通源码页）时保持默认行为。
    if(e.altKey && !e.ctrlKey && !e.metaKey &&
       (e.key==='ArrowLeft' || e.key==='ArrowRight')){
      if(window.cgPreviewPrev || window.cgPreviewNext){
        e.preventDefault();
        if(e.key==='ArrowLeft' && window.cgPreviewPrev){ window.cgPreviewPrev(); }
        if(e.key==='ArrowRight' && window.cgPreviewNext){ window.cgPreviewNext(); }
      }
      return;
    }
    if(e.ctrlKey || e.metaKey || e.altKey) return;
    if(e.key==='Escape'){           // 关闭其它浮层（命令面板 / 预览面板等）
      // P-rev R71：Esc 同时关闭调用链预览面板，与「上一/下一」形成完整键盘闭环
      if(window.cgHidePreview) window.cgHidePreview();
      var o = document.getElementById('gsearch-ovl');
      if(o && o.style.display!=='none'){ if(window.__gs_hide) window.__gs_hide(); else o.style.display='none'; }
      return;
    }
    if(e.key==='t'){ if(window.maToggleTheme) maToggleTheme(); return; }
    if(e.key==='/'){ e.preventDefault(); if(window.__gs_open) window.__gs_open(); else if(window.__gs_toggle) window.__gs_toggle(); return; }
    if(e.key==='g'){ var g=document.getElementById('gs-overview'); if(g){ g.scrollIntoView(); g.setAttribute('tabindex','-1'); g.focus(); } return; }
    if(e.key==='d'){ var d=document.getElementById('dup-toolbar'); if(d){ d.scrollIntoView(); var c=d.querySelector('.chip'); if(c&&c.focus) c.focus(); } return; }
    if(e.key==='h'){ if(window.__CG_SITE_REL__!==undefined){ var rel=window.__CG_SITE_REL__||''; var idx=document.createElement('a'); idx.href=rel+'index.html'; if(idx.href) location.href=idx.href; } return; }
  });
})();
"""  # noqa: E501

# P-rev S2：跨页上下文联动总线（共享内核）。任何带 data-sym 的元素被点击时，
# 将符号名写入 localStorage(pony.focusSymbol) 并广播 storage 事件；所有已打开页面
# 监听到后，若自身存在同名 data-sym 元素则高亮并平滑滚动到该位置。
CONTEXT_LINK_JS = r"""
(function () {
  var KEY = "pony.focusSymbol";
  function norm(s){ return (s||"").trim().toLowerCase(); }
  function mark(el){
    if(!el) return;
    document.querySelectorAll(".ctx-focus").forEach(function(n){ n.classList.remove("ctx-focus"); });
    el.classList.add("ctx-focus");
    el.scrollIntoView({behavior:"smooth", block:"center"});
    if (el.getBoundingClientRect().top < 60) window.scrollBy(0, -60);
  }
  function focusSym(sym){
    if(!sym) return;
    var key = norm(sym);
    // P-rev R13：类方法形式 rel::Cls.method → 也尝试只按方法名 method 匹配（去掉类名前缀）
    var alt = key.indexOf(".") >= 0 ? norm(sym.split(".").slice(-1)[0]) : null;
    var hit = null;
    document.querySelectorAll("[data-sym]").forEach(function(el){
      var ek = norm(el.getAttribute("data-sym"));
      if (ek === key || (alt && ek === alt)) {
        el.classList.add("ctx-cand"); hit = hit || el;
      }
    });
    // 兼容既有标记：带 .sym/.fn/.callnode 且文本即符号名的元素
    if(!hit){
      document.querySelectorAll(".sym,.fn,.callnode,.fn-name").forEach(function(el){
        if (norm(el.textContent) === key) { hit = hit || el; }
      });
    }
    mark(hit);
    // P-rev R75：聚焦失败（本页无该符号）就此打住——不把幽灵符号记进
    // _symHistory（否则「对比」按钮会显示一个永远点不出来的名字），
    // 也不触发影响高亮（目标都不存在，波及高亮无从谈起）。
    if(!hit) return;
    // P-rev R30：记录最近聚焦过的两个符号，供「共同依赖」对比使用
    if(_symHistory[0]!==key){
      _symHistory.unshift(key);
      _symHistory = _symHistory.slice(0, 2);
      updateCommonBtn();
    }
    // P-rev R19：影响闭包可视化——把「改了它会波及哪些函数」直接高亮在调用图上，
    // 让「波及 N 处」从文字变成肉眼可见的高亮子树。
    highlightImpact(key);
  }
  var _symCache=null;
  function highlightImpact(key){
    if(_symCache!==null){ applyImpact(_symCache, key); return; }
    if(typeof fetch!=="function"){ _symCache=[]; return; }  // 老环境降级
    var url=(window.__CG_SITE_REL__||"")+"symbols.json";
    fetch(url).then(function(r){ return r.json(); })
      .then(function(j){ _symCache=j.symbols||[]; applyImpact(_symCache, key); })
      .catch(function(){ _symCache=[]; });
  }
  // P-rev R23：双向影响——mode 决定高亮「波及下游（impacts）」还是「依赖上游（deps）」
  // P-rev R30：新增 "common" —— 最近聚焦的两个符号的**共同依赖**，用于判断
  // 「改动 A 与 B 会不会互相牵连 / 二者是否耦合在同一批底层函数上」。
  var _impactMode = "impacts";
  var _symHistory = [];
  function setImpactMode(m){
    _impactMode = (m==="deps" || m==="common" || m==="common-impact") ? m : "impacts";
  }
  function _findSym(syms, key){
    for(var i=0;i<syms.length;i++){ if(norm(syms[i].id)===key) return syms[i]; }
    return null;
  }
  // P-rev R30/R33：凑够两个符号才启用「对比」按钮（共同依赖 / 共同影响）
  function updateCommonBtn(){
    var cb=document.getElementById("ctx-common-btn");
    if(!cb) return;
    if(_symHistory.length>=2){
      cb.style.display="";
      cb.textContent="🔀 对比："+(_symHistory[0].split("::").pop())
                     +" / "+(_symHistory[1].split("::").pop());
    } else {
      cb.style.display="none";
    }
  }
  // P-rev R33：计算两个符号闭包的交集；listOf 决定用 deps 还是 impacts
  function _intersect(tgt, other, listOf){
    var mine=(listOf(tgt)||[]), set={};
    (listOf(other)||[]).forEach(function(x){ set[norm(x)]=1; });
    return mine.filter(function(x){ return set[norm(x)]; });
  }
  function applyImpact(syms, key){
    document.querySelectorAll(".ctx-impact").forEach(function(n){ n.classList.remove("ctx-impact"); });
    var tgt=_findSym(syms, key);
    if(!tgt) return;
    var list, label;
    if(_impactMode==="common" || _impactMode==="common-impact"){
      var other = _symHistory.length>1 ? _findSym(syms, _symHistory[1]) : null;
      if(!other){ return; }
      // R33：共同影响 = 二者「被共同下游依赖」的交集，用于识别「哪些模块改动会同时牵连 A、B」
      var useImpacts = (_impactMode==="common-impact");
      list = _intersect(tgt, other, function(s){ return useImpacts ? s.impacts : s.deps; });
      label = useImpacts
        ? "🔀 " + tgt.name + " 与 " + other.name + " 共同影响 %d 个函数（高亮）"
        : "🔀 " + tgt.name + " 与 " + other.name + " 共同依赖 %d 个函数（高亮）";
    } else {
      list = (_impactMode==="deps" ? (tgt.deps||[]) : (tgt.impacts||[]));
      label = (_impactMode==="deps")
        ? "🔗 "+tgt.name+" 依赖 %d 个函数（高亮）"
        : "⚡ 改 "+tgt.name+" 将波及 %d 个函数（高亮）";
    }
    if(!list || !list.length) return;
    var set={};
    list.forEach(function(id){ set[norm(id)]=1; });
    var n=0;
    document.querySelectorAll(".cg-node-g[data-sym]").forEach(function(g){
      if(set[norm(g.getAttribute("data-sym"))]){
        g.classList.add("ctx-impact"); n++;
      }
    });
    if(n>0){
      var tip=document.createElement("div");
      tip.className="ctx-impact-tip";
      tip.setAttribute("role","status");
      tip.textContent = label.replace("%d", n);
      document.body.appendChild(tip);
      setTimeout(function(){ if(tip.parentNode) tip.parentNode.removeChild(tip); }, 4000);
    }
  }
  function symFromEl(el){
    if (el.hasAttribute("data-sym")) return el.getAttribute("data-sym");
    return el.textContent;
  }
  document.addEventListener("click", function(e){
    var t = e.target.closest("[data-sym],.sym,.fn,.callnode,.fn-name");
    if(!t) return;
    var sym = symFromEl(t);
    try { localStorage.setItem(KEY, sym); } catch(_){}
    focusSym(sym);
  });
  window.addEventListener("storage", function(e){
    if (e.key === KEY && e.newValue) focusSym(e.newValue);
  });
  // 入口参数 ?focus= 支持从其它页面带参跳转后自动定位
  // P-rev R70：改为「轮询直到目标出现」——固定 120ms 在慢设备 / 调用图节点
  // 异步插入前可能静默错过；现最多重试 25 次（约 3s），找到即聚焦并停止，
  // 超时兜底聚焦一次（结果为空也只清高亮，不再反复滚动）。
  // P-rev R75：兜底不再是"无声操作"——彻底未命中走 __toast/console 报告；
  try {
    var p = new URLSearchParams(location.search).get("focus");
    if (p) {
      var _ftries = 0, _fdone = false, _fhit = false;
      function _tryFocus(){
        if(_fdone) return;
        var key = norm(p);
        var alt = key.indexOf(".") >= 0 ? norm(p.split(".").slice(-1)[0]) : null;
        var found = false;
        document.querySelectorAll("[data-sym]").forEach(function(el){
          var ek = norm(el.getAttribute("data-sym"));
          if (ek === key || (alt && ek === alt)) found = true;
        });
        if(!found){
          document.querySelectorAll(".sym,.fn,.callnode,.fn-name").forEach(function(el){
            if (norm(el.textContent) === key) found = true;
          });
        }
        if(found){ _fhit = true; _fdone = true; focusSym(p); }
      }
      var _ftimer = setInterval(function(){
        _ftries++;
        if(_ftries > 25){ clearInterval(_ftimer);
          if(!_fdone){ _fdone = true;
            // P-rev R75：彻底未命中要给可见反馈——否则「页面到了、目标没高亮」
            // 会静默发生（R70 之前固定 120ms 也是同一类静默坑）。优先走 __toast，
            // 老页面无 toast 时退回 console.warn，保证任何环境都有迹可循。
            if(!_fhit){
              if(typeof window.__toast === "function"){
                window.__toast("?focus= 未找到符号「"+p+"」（可能已改名或移走）", "err");
              } else {
                try{ console.warn("[pony-focus] 本页未找到目标符号:", p); }catch(_e){}
              }
            }
            focusSym(p);
          }
          return; }
        _tryFocus();
        if(_fdone) clearInterval(_ftimer);
      }, 120);
    }
  } catch(_){}
  // P-rev R23：影响方向切换按钮（波及下游 / 依赖上游），仅在存在调用图时显示
  document.addEventListener("DOMContentLoaded", function(){
    setTimeout(function(){
      if(!document.querySelector(".cg-node-g[data-sym]")) return;
      var head=document.querySelector("header");
      if(!head || document.getElementById("ctx-dir-btn")) return;
      var b=document.createElement("button");
      b.id="ctx-dir-btn"; b.className="ug-btn"; b.textContent="⚡ 波及下游";
      b.setAttribute("aria-label","切换影响方向：波及下游 / 依赖上游 / 共同依赖");
      b.onclick=function(){
        // R33：循环顺序 波及 → 依赖 → 共同依赖 → 共同影响 → 波及
        var next = (_impactMode==="impacts") ? "deps"
                 : (_impactMode==="deps") ? "common"
                 : (_impactMode==="common") ? "common-impact" : "impacts";
        setImpactMode(next);
        b.textContent = (next==="deps") ? "🔗 依赖上游"
                      : (next==="common") ? "🔀 共同依赖"
                      : (next==="common-impact") ? "🔀 共同影响" : "⚡ 波及下游";
        var cur=null;
        try{ cur=localStorage.getItem(KEY); }catch(_){}
        if(cur){ _symCache=null; focusSym(cur); }
      };
      head.appendChild(b);
      // P-rev R30/R33：对比需要「两个」符号才有意义；默认对比共同依赖，
      // 长按/再次点击可切到共同影响（对称视角：改动会同时牵连二者的下游）。
      var cb=document.createElement("button");
      cb.id="ctx-common-btn"; cb.className="ug-btn"; cb.style.display="none";
      cb.textContent="🔀 对比最近两个符号";
      cb.setAttribute("aria-label","高亮最近聚焦的两个符号的共同依赖");
      var _commonUsesImpacts = false;
      cb.onclick=function(){
        if(_symHistory.length<2){ return; }
        _commonUsesImpacts = !_commonUsesImpacts;
        setImpactMode(_commonUsesImpacts ? "common-impact" : "common");
        b.textContent = _commonUsesImpacts ? "🔀 共同影响" : "🔀 共同依赖";
        _symCache=null; focusSym(_symHistory[0]);
      };
      head.appendChild(cb);
      updateCommonBtn();
    }, 200);
  });
})();
"""

# P-rev R9（已收敛）：暗色主题切换。R1 起统一到 P270 共享内核的 gs-theme 键与
# window.maToggleTheme（见 THEME_JS 内注释），本文件仅为旧 WB.themeToggle 入口的兼容别名。
THEME_JS = r"""
/* P-rev R9 原为独立设计令牌/暗色切换（写旧 localStorage 键）。现收敛到 P270 统一内核
 * CORE_JS 的 gs-theme 键与 window.maToggleTheme，消除旧键 / gs-theme 双 key
 * 分歧与浏览站/报告/全局态主题状态不互通的半截革命问题。本文件仅作为旧
 * window.WB.themeToggle 入口的兼容别名，不再写旧键。 */
(function(){
  var KEY="gs-theme";
  function apply(t){ document.documentElement.setAttribute("data-theme", t); }
  function init(){
    var saved; try{ saved=localStorage.getItem(KEY); }catch(_){}
    if(!saved){ saved = (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark":"light"; }
    if(saved==="dark"){ apply("dark"); }
  }
  function toggle(){
    // 优先复用共享内核，保证与 --browse 站点、report、global_state 行为完全一致
    if(typeof window.maToggleTheme === "function"){ window.maToggleTheme(); }
    else {
      var cur=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark";
      apply(cur); try{ localStorage.setItem(KEY,cur); }catch(_){}
    }
    var btn=document.getElementById("theme-toggle")||document.getElementById("gs-theme");
    if(btn){ var dark=document.documentElement.getAttribute("data-theme")==="dark";
      btn.textContent=dark?"☀ 浅色":"🌙 暗色"; }
  }
  window.WB = window.WB || {};
  window.WB.themeToggle = toggle;
  document.addEventListener("DOMContentLoaded", init);
  init();
})();
"""

GLOBAL_SEARCH_JS = r"""
/* ================= P107/P108：全站函数搜索浮层 + 键盘导航 + scrollspy =================
 * 由 src/_search.js 注入所有源码页/函数详情页；数据复用 window.__CG__.meta。
 * Ctrl+K / Cmd+K / '/' 打开；↑↓ 选择；Enter 跳转函数详情；Esc 关闭；'t' 切换主题。
 * P270：主题已统一收敛到 CORE_JS（本文件前置拼接），此处不再重复实现。
 */
(function () {
  'use strict';
  if (window.__GS_LOADED__) { return; }
  window.__GS_LOADED__ = true;
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var meta = (window.__CG__ && window.__CG__.meta) || [];
  var sel = -1, list = [];
  function ovl() {
    var el = document.getElementById('gsearch-ovl');
    if (!el) {
      el = document.createElement('div');
      el.id = 'gsearch-ovl';
      el.innerHTML =
        '<div id="gsearch-panel" role="dialog" aria-label="函数搜索">' +
        '<input id="gsearch-input" type="text" placeholder="搜索函数 / 文件 / 目录 / 全局变量 / 源码全文…（↑↓ 选择，Enter 跳转，Esc 关闭）" ' +
        'autocomplete="off" spellcheck="false"/>' +
        // P271 R5-3：结果区 + 预览区并排（窄屏自动堆叠）
        '<div id="gsearch-body">' +
        '<div id="gsearch-results" role="listbox" aria-label="搜索结果"></div>' +
        '<div id="gsearch-preview" aria-live="polite"></div>' +
        '</div>' +
        '<div id="gsearch-hint">Ctrl+K 或 / 打开 · ↑↓ 选择 · Enter 跳转 · '
        + '<b>Shift+Enter</b> 在全局状态中查看 · Esc 关闭 · t 切换主题<br>'
        + '限定范围：<b>fn:</b> 函数 · <b>file:</b> 文件 · <b>dir:</b> 目录 · '
        + '<b>var:</b> 全局变量 · <b>@</b> 全文 · <b>&gt;</b> 命令</div></div>';
      document.body.appendChild(el);
    }
    return el;
  }
  function render() {
    var box = document.getElementById('gsearch-results');
    if (!box) { return; }
    if (list.length === 0) {
      box.innerHTML = '<div style="padding:10px 16px;color:#8b949e;">无匹配函数</div>';
      sel = -1;
      return;
    }
    var html = [];
    // P271 R5-1：作用域生效时必须明确告知，否则用户会以为「搜不到东西」
    if (curScope) {
      html.push('<div class="gs-scope-tip">仅搜索 <b>' + esc(SCOPE_LABEL[curScope] || curScope)
        + '</b> ・ 加 <b>fn:</b>/<b>file:</b>/<b>dir:</b>/<b>var:</b>/<b>@</b> 可切换范围'
        + ' ・ 清空输入框返回全部</div>');
    }
    // P271 R4：最近访问模式下加一行说明，避免与搜索结果混淆
    if (recentMode) {
      html.push('<div class="gs-recent-tip">最近访问（输入以搜索）</div>');
    }
    // P271 R5-2：按类别插入分组标题。list 已完成分组排序，故此处顺序与 list 一致，
    // 键盘 ↑↓ 的选中高亮不会跳位。
    var lastKind = null;
    for (var i = 0; i < list.length; i++) {
      var it = list[i];
      var href = hrefFor(it);
      if (!href) { continue; }            // 目标不可用则跳过（绝不产出死链）
      if (it.k !== lastKind) {
        lastKind = it.k;
        html.push('<div class="gs-group">' + esc(KIND_LABEL[it.k] || it.k) + '</div>');
      }
      // 类别已由分组标题表达，项内不再重复同一信息（减少噪音）
      var badges = [];
      if (it.k === 'fn') {
        var m = meta[it.g] || {};
        var cx = m.cx || 0;
        var fl = m.fl || {};
        if (fl.t) { badges.push('<span class="gs-b gs-b-t">污点</span>'); }
        if (fl.hd || cx >= 15) { badges.push('<span class="gs-b gs-b-hd">复杂度' + cx + '</span>'); }
        if (fl.hi) { badges.push('<span class="gs-b gs-b-hi">高扇入</span>'); }
        if (m.dups && m.dups.length > 1) { badges.push('<span class="gs-b gs-b-dup">同名' + m.dups.length + '</span>'); }
      }
      var bd = '<span class="gs-badges">' + badges.join('') + '</span>';
      /* P271 R5-2：一行上下文说明（灵感来自技能目录的「一行价值说明」）。
       * 不只是路径 —— 让用户**不点开**就能判断这是不是要找的东西：
       *   函数：文件:行号；文件/目录：所属路径；全局变量：定义处；命令：作用说明。 */
      var loc;
      if (it.k === 'fn') {
        loc = esc(it.r) + ':' + it.l;
      } else if (it.k === 'cmd') {
        loc = esc(it.hint || '');
      } else if (it.k === 'var') {
        loc = esc(it.r) ? ('定义于 ' + esc(it.r)) : '';
      } else if (it.k === 'dir') {
        loc = esc(it.r) ? ('目录 ' + esc(it.r)) : '';
      } else {
        loc = esc(it.r);
      }
      if (it.k === 'text') {
        // 全文命中：展示行号 + 高亮片段，点击跳转到对应源码行
        var snip = esc(it.t);
        var ql = String(it.q || '').toLowerCase();
        var si = snip.toLowerCase().indexOf(ql);
        if (si >= 0) {
          snip = snip.slice(0, si) + '<mark class="gs-hl">' +
            snip.slice(si, si + ql.length) + '</mark>' + snip.slice(si + ql.length);
        }
        html.push('<a href="' + esc(href) + '" data-i="' + i + '">' +
          '<span class="gs-loc">' + esc(it.r) + ' : L' + it.l + '</span>' +
          '<span class="gs-snip">' + snip + '</span></a>');
        continue;
      }
      // data-cgn 仅对函数项有意义（悬停时在调用图脉冲该节点）；命令项不加，
      // 避免悬停命令时去做一次必然落空的节点查找。
      var cgn = (it.k === 'fn') ? (' data-cgn="' + esc(it.n) + '"') : '';
      html.push('<a href="' + esc(href) + '" data-i="' + i + '"' + cgn + '>' +
        '<span class="gs-n">' + esc(it.n) + '</span>' + bd +
        '<span class="gs-loc">' + loc + '</span></a>');
    }
    if (!html.length) {
      box.innerHTML = '<div style="padding:10px 16px;color:#8b949e;">无匹配结果</div>';
      sel = -1;
      return;
    }
    box.innerHTML = html.join('');
    sel = Math.min(Math.max(sel, 0), list.length - 1);
    var anchors = box.querySelectorAll('a');
    for (var j = 0; j < anchors.length; j++) {
      anchors[j].classList.toggle('hl', j === sel);
      // R4：无障碍——每条结果作为 listbox option，显式标记选中态
      anchors[j].setAttribute('role', 'option');
      anchors[j].setAttribute('aria-selected', j === sel ? 'true' : 'false');
    }
    // P271 R5-3：render() 在所有选中变化（↑↓ / 输入 / 打开）后都会执行，
    // 故在这里统一刷新预览，不必在每个改 sel 的地方各写一遍。
    updatePreview();
  }
  function open() {
    var w = ovl();
    w.classList.add('open');
    var input = document.getElementById('gsearch-input');
    input.value = '';
    // P271 R4：打开即展示「最近访问」，减少重复输入
    list = getRecent().slice(0, 12);
    recentMode = list.length > 0;
    sel = -1;
    render();
    setTimeout(function () { input.focus(); }, 0);
  }
  function close() {
    var w = document.getElementById('gsearch-ovl');
    if (w) { w.classList.remove('open'); }
  }
  /* P271 R5-3：预览面板 —— 设计灵感来自 MCP 的 resources「按需读取」：
   * 不必跳转离开当前页，就能看到选中项的关键信息，判断「是不是我要找的」。
   * 数据全部取自页面已注入的 __CG__ / __GS_INDEX__，不发起任何请求。 */
  function row(label, val) {
    if (val === undefined || val === null || val === '') { return ''; }
    return '<div class="gp-row"><span class="gp-k">' + esc(label) + '</span>'
      + '<span class="gp-v">' + val + '</span></div>';
  }
  function buildPreview(it) {
    if (!it) { return ''; }
    var h = '';
    if (it.k === 'fn') {
      var m = meta[it.g] || {};
      var CG = window.__CG__ || {};
      var up = CG.up || [], down = CG.down || {};
      var callers = (up[it.g] || []).length;
      var callees = ((down && down[it.g]) || []).length;
      h += '<div class="gp-title">' + esc(it.n) + '</div>';
      h += row('位置', esc(it.r || '') + ':' + (it.l || ''));
      h += row('圈复杂度', (m.cx === undefined ? '—' : String(m.cx)));
      h += row('扇入 / 扇出', callers + ' / ' + callees);
      var tags = [];
      var fl = m.fl || {};
      if (fl.t) { tags.push('<span class="gs-b gs-b-t">污点</span>'); }
      if (fl.hd || (m.cx || 0) >= 15) { tags.push('<span class="gs-b gs-b-hd">高复杂度</span>'); }
      if (fl.hi) { tags.push('<span class="gs-b gs-b-hi">高扇入</span>'); }
      if (m.dups && m.dups.length > 1) {
        tags.push('<span class="gs-b gs-b-dup">同名 ' + m.dups.length + '</span>');
      }
      h += row('标记', tags.join('') || '—');
      h += '<div class="gp-foot">Enter 打开函数详情 · Shift+Enter 在全局状态查看</div>';
    } else if (it.k === 'cmd') {
      h += '<div class="gp-title">' + esc(it.n) + '</div>';
      h += row('类型', '命令');
      h += row('说明', esc(it.hint || '—'));
      h += '<div class="gp-foot">Enter 执行该命令</div>';
    } else if (it.k === 'var') {
      h += '<div class="gp-title">' + esc(it.n) + '</div>';
      h += row('定义于', esc(it.r || '—'));
      h += '<div class="gp-foot">Enter 跳转到定义处</div>';
    } else if (it.k === 'file' || it.k === 'dir') {
      h += '<div class="gp-title">' + esc(it.n) + '</div>';
      h += row('路径', esc(it.r || '—'));
      h += row('类型', it.k === 'dir' ? '目录' : '文件');
      h += '<div class="gp-foot">Enter 打开</div>';
    } else if (it.k === 'text') {
      h += '<div class="gp-title">' + esc(it.r || '') + ' : L' + it.l + '</div>';
      var line = esc(it.t || '');
      var ql = String(it.q || '').toLowerCase();
      var si = line.toLowerCase().indexOf(ql);
      if (si >= 0 && ql) {
        line = line.slice(0, si) + '<mark class="gs-hl">'
          + line.slice(si, si + ql.length) + '</mark>' + line.slice(si + ql.length);
      }
      h += '<div class="gp-code">' + line + '</div>';
      h += '<div class="gp-foot">Enter 跳到该行</div>';
    }
    return h;
  }
  function updatePreview() {
    var pv = document.getElementById('gsearch-preview');
    if (!pv) { return; }
    var it = (sel >= 0 && list[sel]) ? list[sel] : null;
    pv.innerHTML = it ? buildPreview(it) : '';
  }
  window.__GS_OPEN__ = open;   // P271：供页面顶部「搜索」链接调用，统一入口
  // P271 R4：导出内部函数以便离线回归测试（Node + DOM stub）直接验证打分/深链逻辑
  window.__GS_MATCH_SCORE__ = matchScore;
  window.__GS_FILTERED_HREF__ = gsFilteredHref;
  window.__GS_RECENT__ = { get: getRecent, push: pushRecent };
  // P271 R3：导出检索与命令注册，供回归测试验证「命令模式」与「无幽灵命令」
  window.__GS_SEARCH__ = search;
  window.__GS_COMMANDS__ = availableCommands;
  // P271 R5-3：导出预览构建，供回归测试验证「按需看详情」
  window.__GS_PREVIEW__ = buildPreview;
  // P271：悬停搜索结果 → 在全局调用图上脉冲高亮对应节点（沿用原 BROWSE_JS 的交互，
  // 现统一到命令面板；仅当页面提供 window.cgPulse 时生效，其它页面静默）。
  document.addEventListener('mouseover', function (ev) {
    var t = ev.target;
    while (t && t !== document.body) {
      if (t.getAttribute && t.getAttribute('data-cgn')) {
        if (window.cgPulse) { window.cgPulse(t.getAttribute('data-cgn')); }
        return;
      }
      t = t.parentNode;
    }
  });
  // P271 R3/R4：点击结果（非回车）也走统一的 activate —— 命令在此执行，
  // 其余计入「最近访问」后跳转；必须 preventDefault，否则命令项会跳到 '#'
  document.addEventListener('click', function (ev) {
    var t = ev.target;
    while (t && t !== document.body) {
      var di = t.getAttribute ? t.getAttribute('data-i') : null;
      if (di !== null && di !== '' && di !== undefined) {
        var idx = parseInt(di, 10);
        if (!isNaN(idx) && list[idx]) {
          ev.preventDefault();
          activate(list[idx]);
        }
        return;
      }
      t = t.parentNode;
    }
  });
  document.addEventListener('keydown', function (ev) {
    var tag = (ev.target && ev.target.tagName || '').toLowerCase();
    var isTyping = tag === 'input' || tag === 'textarea' || ev.target && ev.target.isContentEditable;
    var isOpen = document.getElementById('gsearch-ovl') &&
      document.getElementById('gsearch-ovl').classList.contains('open');
    if (isOpen) {
      if (ev.key === 'Escape') { close(); ev.preventDefault(); return; }
      if (ev.key === 'ArrowDown') { sel = Math.min(sel + 1, list.length - 1); render(); ev.preventDefault(); return; }
      if (ev.key === 'ArrowUp') { sel = Math.max(sel - 1, 0); render(); ev.preventDefault(); return; }
      if (ev.key === 'Enter') {
        if (sel >= 0 && list[sel]) {
          var it = list[sel];
          // P271 R4：Shift+Enter → 深链到「全局状态」页并预置筛选（可分享的过滤视图）。
          // 命令项无对应目标页，故 Shift+Enter 对命令无意义，直接执行。
          if (ev.shiftKey && it.k !== 'cmd') {
            var gsHref = gsFilteredHref(it);
            if (gsHref) { remember(it); window.location.href = gsHref; }
          } else {
            activate(it);   // P271 R3：命令执行 / 记录最近访问 / 修复过的 hrefFor 跳转
          }
        }
        ev.preventDefault(); return;
      }
    }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') { open(); ev.preventDefault(); return; }
    if (!isTyping && ev.key === '/') { open(); ev.preventDefault(); return; }
    if (!isTyping && ev.key === 't') {
      // P270：统一走共享内核（此前此处写 'ma-theme'、而恢复时读 'gs-theme'，
      // 导致按 t 切换的主题在刷新后丢失——key 不对称缺陷）。
      if (typeof window.maToggleTheme === 'function') { window.maToggleTheme(); }
      else if (typeof window.applyTheme === 'function') {
        window.applyTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
      } else {
        var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        try { localStorage.setItem('gs-theme', next); } catch (e) {}
      }
      return;
    }
  });
  var panel = null;
  document.addEventListener('click', function (ev) {
    var w = document.getElementById('gsearch-ovl');
    if (w && w.classList.contains('open') && ev.target === w) { close(); }
  });
  // P271：顶部「🔍 搜索」链接统一打开命令面板（替代原内联 onclick，避免审计误报且更稳健）
  document.addEventListener('click', function (ev) {
    var t = ev.target;
    while (t && t !== document.body) {
      if (t.id === 'nav-search') { ev.preventDefault(); open(); return; }
      t = t.parentNode;
    }
  });
  /* P270：命令面板——跨「函数 / 文件 / 目录 / 全局变量」四类目标检索（Ctrl+K）。
   * 所有索引项的 href 均为 browse 站点根相对，此处按本页 SITE_REL 拼接；
   * 修复了此前在 src/ 页硬编码 `func_detail.html?g=` 造成的死链。*/
  var SITE_REL = window.__CG_SITE_REL__ || "";
  var IDX = window.__GS_INDEX__ || { file: [], dir: [], var: [] };
  function fdBase() {
    // 页面可覆盖（如 global_state 指向 browse/func_detail.html，或不可用置空）
    if (typeof window.__GS_FD_BASE__ !== 'undefined') { return window.__GS_FD_BASE__; }
    return SITE_REL + "func_detail.html";
  }
  function hrefFor(it) {
    // 命令项不产生真实链接（用 '#' 占位），实际动作由 Enter/点击时执行 run()。
    if (it.k === 'cmd') { return '#'; }
    if (it.k === 'fn') {
      // P271 R4：自包含页面（如 --html 报告）没有 func_detail.html，可由页面注册
      // 自定义解析器把函数映射到**页内锚点**；返回 null 表示本页不可达，该项跳过，
      // 绝不产出死链。
      if (typeof window.__GS_FN_HREF__ === 'function') {
        var custom = window.__GS_FN_HREF__(it);
        return (typeof custom === 'string' && custom) ? custom : null;
      }
      var b = fdBase();
      return b ? (b + "?g=" + it.g) : null;
    }
    // R3：it.h 缺失（索引异常）时返回 null，由 render 的 `if (!href) continue` 守卫
    // 跳过，绝不产出 `SITE_REL + undefined` 之类的死链。
    if (!it.h) { return null; }
    return SITE_REL + it.h;
  }
  /* P271 R4：跨站深链 —— 跳到「全局状态」页并预置搜索（hash 由 DEEPLINK_JS 消费），
   * 例：global_state.html#tab=d&q=fooA → 打开即定位到该函数相关的重复代码，链接可分享。
   *
   * 注意 tab 取值必须是该页**真实存在**的页签（g=global / p=persistent / d=重复代码 /
   * t=演化趋势 / dg=关系图）。此前按命令面板的分类写了 fn/var/file 这类不存在的页签，
   * __gs_show() 会静默失效——链接生成了却「没反应」。而 q 搜索框只作用于「重复代码」
   * 表格，因此统一落到 tab=d。 */
  function gsFilteredHref(it) {
    var base = (typeof window.__GS_GLOBAL_STATE_HREF__ !== 'undefined')
      ? window.__GS_GLOBAL_STATE_HREF__
      : (SITE_REL + 'global_state.html');
    if (!base) { return null; }
    var name = it.n || it.t || '';
    return base + '#tab=d&q=' + encodeURIComponent(name);
  }
  var KIND_LABEL = { fn: '函数', file: '文件', dir: '目录', var: '全局变量',
                     text: '全文', cmd: '命令' };
  /* P271 R3：命令注册表 —— 让面板从「只能跳转」升级为「能执行命令」。
   * 每条命令 { id, title, hint, when(), run() }：
   *   · when() 决定该命令在**当前页面**是否可用（例如报告页没有站点首页可跳，
   *     对应命令就不显示——避免出现点了没反应的“幽灵命令”）；
   *   · run() 执行动作，并通过 window.__toast() 给出可见反馈。
   * 输入以 '>' 开头时只显示命令（可被发现的“命令模式”）。 */
  function go(href) { window.location.href = href; }
  function toast(m, k) { if (window.__toast) { window.__toast(m, k); } }
  function copyText(t, okMsg) {
    function fallback() {
      try {
        var ta = document.createElement('textarea');
        ta.value = t; document.body.appendChild(ta); ta.select();
        var okc = document.execCommand('copy');
        document.body.removeChild(ta);
        toast(okc ? okMsg : '复制失败，请手动复制', okc ? 'ok' : 'err');
      } catch (e) { toast('复制失败，请手动复制', 'err'); }
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(t).then(
        function () { toast(okMsg, 'ok'); }, fallback);
    } else { fallback(); }
  }
  function hrefOf(name) {
    // 仅当目标文件确实可能存在于本站点时才提供跳转命令
    if (typeof window.__GS_PAGES__ === 'object' && window.__GS_PAGES__) {
      if (window.__GS_PAGES__[name] === false) { return null; }
    }
    return SITE_REL + name;
  }
  var COMMANDS = [
    { id: 'theme', title: '切换暗色/亮色主题', hint: '快捷键 t',
      when: function () { return typeof window.maToggleTheme === 'function'; },
      run: function () {
        window.maToggleTheme();
        var dark = document.documentElement.getAttribute('data-theme') === 'dark';
        toast('已切换为' + (dark ? '暗色' : '亮色') + '主题', 'ok');
      } },
    { id: 'copy-link', title: '复制本页链接', hint: '分享当前视图',
      when: function () { return true; },
      run: function () { copyText(location.href, '已复制本页链接'); } },
    { id: 'home', title: '回到站点首页', hint: '快捷键 h',
      when: function () { return !!hrefOf('index.html'); },
      run: function () { go(hrefOf('index.html')); } },
    { id: 'unified', title: '打开统一代码结构图', hint: '四类节点 + 三种连线',
      when: function () { return !!hrefOf('unified.html'); },
      run: function () { go(hrefOf('unified.html')); } },
    { id: 'metrics', title: '打开风险度量', hint: '按风险分排序的全部函数',
      when: function () { return !!hrefOf('metrics.html'); },
      run: function () { go(hrefOf('metrics.html')); } },
    { id: 'dup', title: '打开重复代码分析', hint: '相似函数/片段聚合',
      when: function () { return !!hrefOf('dup.html'); },
      run: function () { go(hrefOf('dup.html')); } },
    { id: 'func-detail', title: '打开函数详情索引', hint: '全部函数卡片',
      when: function () { return !!hrefOf('func_detail.html'); },
      run: function () { go(hrefOf('func_detail.html')); } },
    { id: 'global-state', title: '打开全局状态页', hint: 'global/persistent/重复代码',
      when: function () {
        var b = (typeof window.__GS_GLOBAL_STATE_HREF__ !== 'undefined')
          ? window.__GS_GLOBAL_STATE_HREF__ : hrefOf('global_state.html');
        return !!b;
      },
      run: function () {
        var b = (typeof window.__GS_GLOBAL_STATE_HREF__ !== 'undefined')
          ? window.__GS_GLOBAL_STATE_HREF__ : hrefOf('global_state.html');
        go(b);
      } }
  ];
  function availableCommands() {
    var out = [];
    for (var i = 0; i < COMMANDS.length; i++) {
      var c = COMMANDS[i];
      try { if (c.when()) { out.push(c); } } catch (e) {}
    }
    return out;
  }
  /* P271 R4：模糊打分（越小越好；-1 = 不匹配）。
   * 依次尝试：完全相等 → 前缀 → 词首（_ . / - 之后或 camelCase 边界）→ 子串 → 子序列。
   * 子序列匹配让 `fda` 也能命中 `fooDetailA`；连续命中越多、位置越靠前，得分越好。 */
  function matchScore(name, q) {
    if (!q) { return 0; }
    var n = String(name).toLowerCase();
    if (n === q) { return 0; }
    var i = n.indexOf(q);
    if (i === 0) { return 1; }
    if (i > 0) {
      var prev = n.charAt(i - 1);
      var boundary = (prev === '_' || prev === '.' || prev === '/' || prev === '-' ||
                      prev === ' ' || prev === ':');
      // camelCase 边界：前一小写、当前大写
      if (!boundary && i > 0) {
        boundary = (prev === prev.toLowerCase() && prev !== prev.toUpperCase()) &&
                   (n.charAt(i) !== n.charAt(i).toLowerCase());
      }
      return boundary ? (2 + Math.min(i, 20) * 0.01) : (10 + Math.min(i, 40) * 0.01);
    }
    // 子序列匹配
    var qi = 0, gaps = 0, consec = 0, best = 0, last = -2;
    for (var k = 0; k < n.length && qi < q.length; k++) {
      if (n.charAt(k) === q.charAt(qi)) {
        if (last === k - 1) { consec++; if (consec > best) { best = consec; } }
        else { gaps += Math.max(0, k - last - 1); consec = 1; if (best === 0) { best = 1; } }
        last = k; qi++;
      }
    }
    if (qi < q.length) { return -1; }
    return 100 + gaps * 0.5 - best * 2;
  }
  /* P271 R4：最近访问（localStorage 持久化，空查询时直接展示，越用越顺手）。 */
  var RECENT_KEY = 'gs-recent', RECENT_MAX = 12;
  function getRecent() {
    try {
      var raw = window.localStorage && localStorage.getItem(RECENT_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      return Object.prototype.toString.call(arr) === '[object Array]' ? arr : [];
    } catch (e) { return []; }
  }
  function pushRecent(it) {
    try {
      if (!it || !window.localStorage) { return; }
      var key = it.k + '|' + (it.g == null ? '' : it.g) + '|' + (it.n || it.t || '');
      var arr = getRecent().filter(function (x) {
        return (x.k + '|' + (x.g == null ? '' : x.g) + '|' + (x.n || x.t || '')) !== key;
      });
      arr.unshift({ k: it.k, g: it.g, n: it.n, r: it.r, h: it.h, l: it.l, t: it.t, q: it.q });
      localStorage.setItem(RECENT_KEY, JSON.stringify(arr.slice(0, RECENT_MAX)));
    } catch (e) {}
  }
  /* P271 R5-1：分类作用域（scoping）。
   * 设计灵感来自 MATLAB Agentic Toolkit 的一条建议：「只安装与当前工作相关的技能组，
   * 加载越少，agent 越可靠」。搜索同理——限定范围后结果更聚焦、命中率更高。
   * 语法：`fn:` 函数 / `file:` 文件 / `dir:` 目录 / `var:` 全局变量 /
   *       `@` 或 `text:` 全文 / `>` 命令（R3 已有）。
   * 只输入前缀（如 `fn:`）即列出该类别，便于快速浏览。 */
  var SCOPE_ALIAS = {
    'fn': 'fn', 'f': 'fn', 'func': 'fn', '函数': 'fn',
    'file': 'file', 'fl': 'file', '文件': 'file',
    'dir': 'dir', 'd': 'dir', 'folder': 'dir', '目录': 'dir',
    'var': 'var', 'v': 'var', 'globals': 'var', '全局变量': 'var',
    'text': 'text', 't': 'text', '@': 'text', '全文': 'text'
  };
  var SCOPE_LABEL = { fn: '函数', file: '文件', dir: '目录', var: '全局变量',
                      text: '全文', cmd: '命令' };
  var curScope = null;        // 当前生效的作用域（供面板提示）
  /* P271 R5-2：结果分组顺序。灵感来自 MATLAB Agentic Toolkit 的技能目录
     「分组 + 一行价值说明」——分组让同类结果聚在一起，比一长串混排更易扫读。 */
  var GROUP_RANK = { cmd: 0, fn: 1, file: 2, dir: 3, var: 4, text: 5 };
  var GROUP_ORDER = ['cmd', 'fn', 'file', 'dir', 'var', 'text'];
  function parseScope(q) {
    if (!q) { return { scope: null, q: q }; }
    // `@关键字`：全文检索的常用约定，无需冒号
    if (q.charAt(0) === '@') { return { scope: 'text', q: q.slice(1) }; }
    var m = /^([A-Za-z@一-龥]+)\s*[:：]\s*(.*)$/.exec(q);
    if (m) {
      var key = m[1].toLowerCase();
      if (SCOPE_ALIAS[key]) { return { scope: SCOPE_ALIAS[key], q: m[2] }; }
      // 未识别的前缀：按原文搜索（不吞掉用户输入）
    }
    return { scope: null, q: q };
  }
  // P271：全文检索（浏览站特有）。复用 browse 首页注入的 window.__SEARCH_DATA__.files，
  // 跨源码行做子串匹配，结果并入同一面板（不再另起一套 #search 框）。
  function searchText(q, cap) {
    var sd = window.__SEARCH_DATA__;
    if (!sd || !sd.fulltext) { return []; }
    var res = [];
    var ql = q.toLowerCase();
    for (var fi = 0; fi < sd.files.length && res.length < cap; fi++) {
      var fl = sd.files[fi];
      for (var li = 0; li < fl.lines.length && res.length < cap; li++) {
        if (fl.lines[li].toLowerCase().indexOf(ql) >= 0) {
          res.push({ k: 'text', r: fl.r, h: fl.h, l: li + 1, t: fl.lines[li], q: q, s: 2 });
        }
      }
    }
    return res;
  }
  function search(q) {
    var out = [];
    var i;
    // P271 R3：以 '>' 开头进入「只显示命令」模式（便于被发现）
    if (q.charAt(0) === '>') {
      var cq = q.slice(1).trim();
      var cmds = availableCommands();
      for (i = 0; i < cmds.length; i++) {
        var sc = cq ? matchScore(cmds[i].title, cq) : 0;
        if (sc >= 0) {
          out.push({ k: 'cmd', n: cmds[i].title, hint: cmds[i].hint,
                     run: cmds[i].run, s: sc });
        }
      }
      out.sort(function (a, b) { return a.s - b.s; });
      return out.slice(0, 30);
    }
    // P271 R5-1：解析作用域，限定后只检索对应类别（空关键词则列出该类别全部）
    var sp = parseScope(q);
    var scope = sp.scope, sq = sp.q.toLowerCase();
    curScope = scope;       // 供面板提示「当前仅搜索某一类」
    var wantFn = !scope || scope === 'fn';
    var wantText = !scope || scope === 'text';
    var wantCmd = !scope;                       // 命令不参与类别限定（用 > 进入）

    if (wantFn) {
      for (i = 0; i < meta.length; i++) {
        var m = meta[i];
        if (!m || !m.n) { continue; }
        if (m.k === 'folder') { continue; }     // 目录已由 IDX.dir 覆盖
        // 限定时允许空关键词（列出该类别全部）
        var s = sq ? matchScore(m.n, sq) : 0;
        if (s >= 0) { out.push({ k: 'fn', g: i, n: m.n, r: m.r, l: m.l, s: s }); }
      }
    }
    ['file', 'dir', 'var'].forEach(function (kind) {
      if (scope && scope !== kind) { return; }  // P271 R5-1：作用域过滤
      (IDX[kind] || []).forEach(function (it) {
        var s2 = sq ? matchScore(it.n, sq) : 0;
        if (s2 >= 0) { out.push({ k: kind, n: it.n, r: it.r, h: it.h, s: s2 }); }
      });
    });
    // 全文：排序权重略低于名称匹配（s=2），保证名称优先、全文补充
    if (wantText && sq) {
      var tx = searchText(sq, 30);
      for (var ti = 0; ti < tx.length; ti++) { out.push(tx[ti]); }
    }
    // P271 R3：普通搜索也带出匹配的命令（排在前面，让「能执行命令」这件事被发现）
    if (wantCmd && sq) {
      var cmds2 = availableCommands();
      for (var ci = 0; ci < cmds2.length; ci++) {
        var sc2 = matchScore(cmds2[ci].title, sq);
        if (sc2 >= 0) {
          out.push({ k: 'cmd', n: cmds2[ci].title, hint: cmds2[ci].hint,
                     run: cmds2[ci].run, s: sc2 });
        }
      }
    }
    out.sort(function (a, b) {
      // P271 R5-2：先按类别分组（命令 → 函数 → 文件 → 目录 → 全局变量 → 全文），
      // 组内再按相关度。分组顺序与渲染顺序一致，键盘 ↑↓ 选中才不会跳位。
      var ac = GROUP_RANK[a.k], bc = GROUP_RANK[b.k];
      if (ac === undefined) { ac = 9; }
      if (bc === undefined) { bc = 9; }
      if (ac !== bc) { return ac - bc; }
      if (a.s !== b.s) { return a.s - b.s; }
      return String(a.n || a.t).length - String(b.n || b.t).length;
    });
    return out.slice(0, 60);
  }
  document.addEventListener('input', function (ev) {
    if (!ev.target || ev.target.id !== 'gsearch-input') { return; }
    var q = ev.target.value.trim().toLowerCase();
    list = [];
    sel = -1;
    // P271 R4：空查询展示「最近访问」，越用越顺手（无需每次重新输入）
    if (!q) { list = getRecent().slice(0, 12); recentMode = true; render(); return; }
    recentMode = false;
    list = search(q);
    render();
  });
  // 导航前记录最近访问（点击/回车均会走到 hrefFor → 统一在此记录）
  var recentMode = false;
  function remember(it) { if (it && it.k !== 'text' && it.k !== 'cmd') { pushRecent(it); } }
  /* P271 R3：统一「执行某一项」的入口——命令走 run()，其余走链接跳转。
   * 回车与点击共用，避免两条路径行为不一致（此前点击只是跟随 href）。 */
  function activate(it) {
    if (!it) { return; }
    if (it.k === 'cmd') {
      try { it.run(); } catch (e) {}
      return;
    }
    remember(it);
    if (it.k === 'text') {
      window.location.href = it.h + '?q=' + encodeURIComponent(it.q) + '#L' + it.l;
      return;
    }
    var hf = hrefFor(it);
    if (hf) { window.location.href = hf; }
  }
  /* scrollspy：源码页左侧大纲高亮当前函数（P105） */
  function spy() {
    var links = document.querySelectorAll('.src-outline a[data-line]');
    if (!links.length) { return; }
    var lines = [];
    for (var i = 0; i < links.length; i++) {
      lines.push({ el: links[i], line: parseInt(links[i].getAttribute('data-line'), 10) });
    }
    lines.sort(function (a, b) { return a.line - b.line; });
    var pos = (window.pageYOffset || document.documentElement.scrollTop) + 120;
    var cur = null;
    for (var j = 0; j < lines.length; j++) {
      var tr = document.getElementById('L' + lines[j].line);
      if (tr && tr.offsetTop <= pos) { cur = lines[j]; }
    }
    for (var k = 0; k < links.length; k++) { links[k].classList.remove('so-cur'); }
    if (cur) { cur.el.classList.add('so-cur'); }
  }
  if (document.querySelector('.src-outline')) {
    document.addEventListener('scroll', function () { spy(); }, { passive: true });
    window.addEventListener('resize', spy);
    setTimeout(spy, 120);
  }
})();
"""

LOCALCG_INIT_JS = """
// P17：调用图视图状态持久化到 URL #（可分享 / 书签 / 浏览器前进后退）。
// 多个 .cg-host 共存时，按 curRoot 各自独立记录。序列化格式（整体 encodeURIComponent
// 后写入 location.hash 的 cg= 字段）：
//   <root>~<dir>~<exp逗号列表>~<focus>~<cyc> ; <root2>~...
// 其中 exp 为「已展开节点 gid 列表」，focus 为搜索聚焦词，cyc 为当前高亮的循环 gid。
window.__CG_HOSTS__ = window.__CG_HOSTS__ || [];
var __CG_RESTORE__ = false;          // 还原过程中为 true，抑制回写避免死循环 / 抖动
window.__CG_PATH_QUERY__ = null;     // P20：当前生效的「调用路径查询」（{from,to}），写入 URL # 分享
window.__CG_PATH_APPLIED__ = null;   // P20：最近一次已应用的路径查询键（from~to），避免 hashchange 重复高亮/回弹
var __CG_SYNC_TIMER__ = null;        // 防抖计时器（避免逐字符搜索产生大量 history 条目）
function _cgStateOfHost(host){
  if(host.__cgSnapshot) return host.__cgSnapshot();
  return {root: host.__cgRoot, dir: host.__cgDir || 'callee', exp: [], focus: '', cyc: null};
}
function _cgSerializeAll(){
  var parts = [];
  for(var h = 0; h < window.__CG_HOSTS__.length; h++){
    var st = _cgStateOfHost(window.__CG_HOSTS__[h]);
    if(st.root == null) continue;
    parts.push([st.root, st.dir, st.exp.join(','), st.focus, (st.cyc == null ? '' : st.cyc)]);
  }
  // P27：与 _cgMapToStr 统一按 root gid 升序，保证「序列化 → 解析 → 再序列化」往返一致，
  // 使 _cgApplyHash 的比较能正确早退，避免每次 hashchange 都重建所有 host（潜在抖动 / 回弹）。
  // P31：同一 root 下存在 callee / caller 两图（data-dir 不同），需以 dir 作为次级排序键，
  // 使两图各自独立、顺序稳定（否则 callee/caller 展开状态会被覆盖 / 回退）。
  parts.sort(function(a, b){ return (a[0] - b[0]) || (a[1] < b[1] ? -1 : (a[1] > b[1] ? 1 : 0)); });
  return parts.map(function(x){ return x.join('~'); }).join(';');
}
function _cgMapToStr(map){
  var parts = [];
  for(var k in map){
    var st = map[k];
    parts.push([st.root, st.dir, st.exp.join(','), st.focus, (st.cyc == null ? '' : st.cyc)]);
  }
  parts.sort(function(a, b){ return (a[0] - b[0]) || (a[1] < b[1] ? -1 : (a[1] > b[1] ? 1 : 0)); });
  return parts.map(function(x){ return x.join('~'); }).join(';');
}
function _cgParseHash(){
  var raw = '';
  try { raw = decodeURIComponent(String(location.hash || '').replace(/^#/, '')); } catch(e){ raw = ''; }
  if(raw.indexOf('cg=') !== 0) return null;
  var body = raw.slice(3);
  if(!body) return null;
  var map = {};
  body.split(';').forEach(function(seg){
    var f = seg.split('~');
    if(f.length < 5) return;
    var root = parseInt(f[0], 10);
    if(isNaN(root)) return;
    var exp = [];
    f[2].split(',').forEach(function(x){ if(x !== ''){ var g = parseInt(x, 10); if(!isNaN(g)) exp.push(g); } });
    var cyc = (f[4] === '') ? null : parseInt(f[4], 10);
    if(f[4] !== '' && isNaN(cyc)) cyc = null;
    map[root + '~' + f[1]] = {root: root, dir: f[1], exp: exp, focus: f[3], cyc: cyc};
  });
  return map;
}
function _cgSyncHash(){
  if(__CG_RESTORE__) return;                         // 还原中跳过
  if(__CG_SYNC_TIMER__ != null) clearTimeout(__CG_SYNC_TIMER__);
  __CG_SYNC_TIMER__ = setTimeout(function(){
    __CG_SYNC_TIMER__ = null;
    var cand = '#cg=' + encodeURIComponent(_cgSerializeAll());
    if(window.__CG_PATH_QUERY__){
      var pq = window.__CG_PATH_QUERY__;
      cand += '&cgp=' + encodeURIComponent(pq.from + '~' + pq.to);
    }
    if(location.hash === cand) return;               // 已一致则不改动（避免抖动）
    try { location.hash = cand; } catch(e){}
  }, 350);
}
function _cgApplyHash(){
  if(__CG_RESTORE__) return;
  var map = _cgParseHash();
  if(!map) return;
  // P20：优先还原 URL # 中的调用路径查询（cgp=）。即便其余视图状态与当前一致也照常
  // 高亮路径，使「从 A 到 B 的最短调用路径」可通过链接分享、刷新 / 前进后退后自动还原。
  // 用 __CG_PATH_APPLIED__ 记录最近一次已应用的路径键，避免每次 hashchange 重复高亮、
  // 导致用户手动折叠路径节点被「回弹」。
  var pm = _cgParsePath();
  if(pm && window.cgFindPath){
    var _pk = pm.from + '~' + pm.to;
    if(window.__CG_PATH_APPLIED__ !== _pk){
      window.__CG_PATH_APPLIED__ = _pk;
      try { window.cgFindPath(pm.from, pm.to, true); } catch(e){}
    }
  } else if(!pm){
    window.__CG_PATH_APPLIED__ = null;
  }
  // 与当前状态一致则不重复还原（避免 hashchange 自触发造成的额外渲染抖动）
  if(encodeURIComponent(_cgMapToStr(map)) === encodeURIComponent(_cgSerializeAll())) return;
  __CG_RESTORE__ = true;
  for(var h = 0; h < window.__CG_HOSTS__.length; h++){
    var host = window.__CG_HOSTS__[h];
    var st = map[host.__cgRoot + '~' + (host.__cgDir || 'callee')];
    if(st && host.__cgRestore) host.__cgRestore(st);
  }
  __CG_RESTORE__ = false;
}
// 复制「可分享链接」：把当前全部调用图视图状态编码进 URL #，复制到剪贴板并返回完整 URL。
window.cgCopyShareLink = function(){
  var s = _cgSerializeAll();
  var url = location.origin + location.pathname + (s ? ('#cg=' + encodeURIComponent(s)) : '');
  try {
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(url).catch(function(){});
    } else {
      var ta = document.createElement('textarea'); ta.value = url; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch(e2){}
      document.body.removeChild(ta);
    }
  } catch(e){}
  return url;
};

window.initLocalCG = function(){
  // 初始化页面内所有「按需下钻」调用图容器（.cg-host）。真实 SVG 由前端依据
  // window.__CG__ 全局邻接表渲染，默认仅展开「根 + 直接子」一层（浅层），点击
  // 节点上的 +/- 徽标即可增量展开 / 折叠其被调（callee）或被调用（caller）子树，
  // 彻底消除旧服务端渲染的 MAX_CALLGRAPH_DEPTH 截断与节点爆炸问题。
  var hosts = document.querySelectorAll('.cg-host');
  for(var h = 0; h < hosts.length; h++){ initOneCG(hosts[h]); }
  // 调用图搜索框（P14）：实时聚焦「本函数卡片」内的调用 / 被调用图
  // （自动展开祖先路径 + 脉冲定位），清空则恢复默认浅层视图。
  var searchBoxes = document.querySelectorAll('.cg-search');
  for(var s = 0; s < searchBoxes.length; s++){
    (function(box){
      box.addEventListener('input', function(){
        var det = box.closest('details.callgraph');
        var hs = det ? det.querySelectorAll('.cg-host') : document.querySelectorAll('.cg-host');
        for(var h = 0; h < hs.length; h++){ if(hs[h]._cgFocus) hs[h]._cgFocus(box.value); }
        if(det && box.value.trim()) det.open = true;
      });
      box.addEventListener('keydown', function(e){
        if(e.key === 'Escape'){
          box.value = '';
          var det = box.closest('details.callgraph');
          var hs = det ? det.querySelectorAll('.cg-host') : document.querySelectorAll('.cg-host');
          for(var h = 0; h < hs.length; h++){ if(hs[h]._cgFocus) hs[h]._cgFocus(''); }
        }
      });
    })(searchBoxes[s]);
  }
  // P17：监听 hashchange 实现浏览器前进 / 后退还原；首次加载时还原 URL # 中的视图状态。
  if(!window.__CG_HASH_INIT__){
    window.__CG_HASH_INIT__ = true;
    window.addEventListener('hashchange', function(){ _cgApplyHash(); });
  }
  _cgApplyHash();
};
function initOneCG(host){
  var CG = window.__CG__;
  if(!CG || !CG.meta) return;
  var meta = CG.meta, down = CG.down, up = CG.up;
  var SITE_REL = window.__CG_SITE_REL__ || "";
  var curRoot = parseInt(host.getAttribute('data-root'), 10);
  var dir = host.getAttribute('data-dir') || 'callee';
  if(isNaN(curRoot) || !meta[curRoot]) return;
  // P17：登记本宿主到全局注册表，供 URL # 状态序列化 / 还原（多图共存时各自独立）。
  host.__cgRoot = curRoot;
  window.__CG_HOSTS__ = window.__CG_HOSTS__ || [];
  window.__CG_HOSTS__.push(host);
  var MAX_NODES = 1200;    // P32：提升防爆炸上限，支持更深层的完整调用链展开
  var R = 5.5, CHAR_W = 7.2, LABEL_PAD = 6, X_GAP = 150, Y_GAP = 32, MARGIN = 20;
  var CG_MIN_ROW_GAP = 22;          // P18：节点最小纵向间距（防重叠）
  var CG_MIN_ROW_GAP_CAPTION = 34;  // P24：带说明注释(cg-desc)的节点需更大间距，避免注释与下一节点标签重叠
  var KIND_COLOR = {main:"#1a7f37",local:"#9a6700",method:"#8250df",constructor:"#cf222e",script:"#57606a"};
  var expanded = {}; expanded[curRoot] = true;   // 根默认展开一层
  // P83：视图变换状态——缩放/平移作用于 svg 的 CSS transform，不改动布局坐标；
  // 滚轮以鼠标位置为中心缩放，拖拽平移画布，双击节点把该节点设为新的根（聚焦子树）。
  var cgZoom = 1, cgPanX = 0, cgPanY = 0, cgDrag = null, cgClickTimer = null, lastW = 0, lastH = 0;
  var active = null;
  var prevY = null;   // P45：节点位置记忆——记录上一次布局的 y 坐标，减少展开/折叠时的跳动
  // P17：视图状态（供 URL # 持久化）。focus 为搜索聚焦词，cyc 为当前高亮的循环 gid。
  var focusVal = '';
  var cycVal = null;
  function curState(){
    var exp = [];
    for(var k in expanded){ if(expanded[k]) exp.push(parseInt(k, 10)); }
    return {root: curRoot, dir: dir, exp: exp, focus: focusVal, cyc: cycVal};
  }
  host.__cgSnapshot = curState;
  host.__cgDir = dir;
  // P20：路径高亮辅助——展开路径节点的祖先链路（使其在当前子树下可见），并高亮给定 gid 集合
  host.__cgExpandAncestors = function(gids){
    gids.forEach(function(g){
      var stack=[g], seen={};
      while(stack.length){
        var cur = stack.pop();
        if(seen[cur]) continue; seen[cur]=1;
        expanded[cur] = true;
        var rev = (dir==='callee'? up: down)[cur] || [];
        for(var i=0;i<rev.length;i++){ if(!seen[rev[i]]) stack.push(rev[i]); }
      }
    });
    render();
  };
  host.__cgHighlightGids = function(gids){
    var set = {}; for(var i=0;i<gids.length;i++){ set[gids[i]] = 1; }
    highlightSet(set, gids.length ? gids[0] : null);
  };
  // P21：追本溯源——「溯源（展开全部）」一键展开本宿主根函数的完整传递子树：
  // callee 方向 = 全下游（被调链条到叶子）；caller 方向 = 全上游（调用方链条溯源到入口/根）。
  // 「收缩」复位为默认浅层（根 + 直接子一层）。均复用 expanded / render / _cgSyncHash。
  host.__cgExpandAll = function(){
    var stack = [curRoot], seen = {};
    while(stack.length){
      var cur = stack.pop();
      if(seen[cur]) continue; seen[cur] = 1;
      expanded[cur] = true;
      var adj = adjOf(cur);
      for(var i = 0; i < adj.length; i++){ if(!seen[adj[i]]) stack.push(adj[i]); }
    }
    render();
    _cgSyncHash();
  };
  host.__cgCollapseAll = function(){
    expanded = {}; expanded[curRoot] = true;
    render();
    _cgSyncHash();
  };
  var svgNS = "http://www.w3.org/2000/svg";

  // P15：循环调用（回边）检测。基于 down 邻接表做 Tarjan 强连通分量（SCC）：
  // 分量大小 > 1、或含自环（g ∈ down[g]）的节点视为「处于循环中」。生成 sccOf
  // （gid→分量序号；自环单独记 -1）与 sccList（分量序号→节点数组），供节点徽标与
  // 点击高亮使用。闭环在 down / up 邻接上对称，故仅用 down 即可完整识别。
  var sccOf = {}, sccList = {};
  (function(){
    var idx = {}, low = {}, onStack = {}, stack = [];
    var index = 0, sccId = 0;
    function sc(v){
      idx[v] = index; low[v] = index; index++;
      stack.push(v); onStack[v] = 1;
      var adj = down[v] || [];
      for(var i = 0; i < adj.length; i++){
        var w = adj[i];
        if(idx[w] == null){ sc(w); low[v] = Math.min(low[v], low[w]); }
        else if(onStack[w]){ low[v] = Math.min(low[v], idx[w]); }
      }
      if(low[v] === idx[v]){
        var comp = [];
        do { var w2 = stack.pop(); onStack[w2] = 0; comp.push(w2); } while(w2 !== v);
        var id = sccId++;
        sccList[id] = comp;
        if(comp.length > 1){ for(var c = 0; c < comp.length; c++){ sccOf[comp[c]] = id; } }
      }
    }
    for(var i = 0; i < meta.length; i++){ if(idx[i] == null) sc(i); }
    // 自环（a 调用自身）：单独标记 sccOf = -1
    for(var g2 = 0; g2 < meta.length; g2++){
      if((down[g2] || []).indexOf(g2) >= 0 && sccOf[g2] == null){ sccOf[g2] = -1; }
    }
  })();
  function inCycle(g){ return sccOf[g] != null; }

  function adjOf(g){ return (dir === 'callee' ? down : up)[g] || []; }
  var nameCnt = {};
  for(var i = 0; i < meta.length; i++){ var nn = meta[i].n; nameCnt[nn] = (nameCnt[nn] || 0) + 1; }
  function labelOf(g){
    var m = meta[g]; var lab = m.n;
    if(lab.length > 24) lab = lab.slice(0, 23) + '…';
    if((nameCnt[lab] || 0) > 1 && m.r){
      var base = m.r.split('/').pop();
      if(base.length > 18) base = base.slice(0, 17) + '…';
      lab = lab + ' (' + base + ')';
    }
    return lab;
  }
  function hrefOf(g){
    var m = meta[g];
    if(!m || !m.p) return null;
    return SITE_REL + m.p + '#L' + m.l;
  }
  function computeVisible(){
    var seen = {}, nodes = [], edges = [], depthOf = {}, hasHidden = {}, truncated = false;
    var stack = [curRoot]; seen[curRoot] = true; depthOf[curRoot] = 0; nodes.push(curRoot);
    var guard = 0;
    while(stack.length){
      if(guard++ > 100000) break;
      var g = stack.pop();
      var links = adjOf(g);
      if(!expanded[g] && links.length) hasHidden[g] = true;
      if(expanded[g]){
        for(var i = 0; i < links.length; i++){
          var c = links[i];
          edges.push([g, c]);
          if(!seen[c]){
            if(nodes.length >= MAX_NODES){ truncated = true; continue; }
            seen[c] = true; depthOf[c] = depthOf[g] + 1; nodes.push(c); stack.push(c);
          }
        }
      }
    }
    return {nodes:nodes, edges:edges, depthOf:depthOf, hasHidden:hasHidden, truncated:truncated};
  }
  function layout(vis){
    var children = {};
    vis.nodes.forEach(function(g){ children[g] = []; });
    vis.edges.forEach(function(e){ if(children[e[0]]) children[e[0]].push(e[1]); });
    var maxLabelW = {}, maxD = 0;
    vis.nodes.forEach(function(g){
      var d = vis.depthOf[g]; if(d > maxD) maxD = d;
      var w = labelOf(g).length * CHAR_W + LABEL_PAD;
      if(!(d in maxLabelW) || w > maxLabelW[d]) maxLabelW[d] = w;
    });
    var xCol = {}; xCol[0] = MARGIN;
    for(var d = 1; d <= maxD + 1; d++){ xCol[d] = xCol[d - 1] + R * 2 + (maxLabelW[d - 1] || 40) + X_GAP; }
    var y = {}; var nextY = {v: 0}; var seenY = {};
    function assign(g){
      if(seenY[g]) return; seenY[g] = true;
      if(children[g].length === 0){ y[g] = nextY.v; nextY.v += Y_GAP; }
      else {
        var ok = true;
        children[g].forEach(function(ch){ assign(ch); if(y[ch] == null) ok = false; });
        if(ok){
          // P27：父节点 y 取所有子节点 y 的「范围中点」(min+max)/2，而非首尾均值。
          // 当某被调函数被多个父函数共享时，子节点 y 不再单调，首尾均值会把父节点
          // 拉到错误位置、加剧塌缩；取范围中点更稳健，让父节点居中覆盖其子树范围。
          var _mn = y[children[g][0]], _mx = y[children[g][0]];
          children[g].forEach(function(ch){ if(y[ch] < _mn) _mn = y[ch]; if(y[ch] > _mx) _mx = y[ch]; });
          y[g] = (_mn + _mx) / 2;
        } else { y[g] = nextY.v; nextY.v += Y_GAP; }
      }
    }
    assign(curRoot);
    // P18：去碰撞——当某被调函数被多个调用方共享时，assign 会将其父节点的 y 取子节点均值，
    // 可能塌缩到与子节点同一 y，导致多个节点 / 标签互相覆盖（即「调用图显示时覆盖别的函数的调用」）。
    // 此处将可见节点按 y 排序后强制最小纵向间距 CG_MIN_ROW_GAP，彻底消除重叠。
    var _order = vis.nodes.slice().sort(function(a, b){ return y[a] - y[b]; });
    for(var _k = 1; _k < _order.length; _k++){
      var _p = _order[_k - 1], _c = _order[_k];
      // P24：带说明注释(cg-desc)的上方节点需要更大间距，避免其注释与下方节点标签重叠。
      var _need = ((meta[_p] && meta[_p].d) ? CG_MIN_ROW_GAP_CAPTION : CG_MIN_ROW_GAP);
      if(y[_c] - y[_p] < _need) y[_c] = y[_p] + _need;
    }
    // P45：节点位置记忆——优先沿用上一次的 y（仅对已存在节点），再重新去碰撞，
    // 使展开/折叠/溯源后已有节点尽量保持原位、不跳动（新节点保持本次布局位置）。
    if(prevY){
      vis.nodes.forEach(function(g){ if(prevY[g] != null) y[g] = prevY[g]; });
      var _order2 = vis.nodes.slice().sort(function(a, b){ return y[a] - y[b]; });
      for(var _k2 = 1; _k2 < _order2.length; _k2++){
        var _p2 = _order2[_k2 - 1], _c2 = _order2[_k2];
        var _need2 = ((meta[_p2] && meta[_p2].d) ? CG_MIN_ROW_GAP_CAPTION : CG_MIN_ROW_GAP);
        if(y[_c2] - y[_p2] < _need2) y[_c2] = y[_p2] + _need2;
      }
    }
    var _h = 0;
    vis.nodes.forEach(function(g){ if(y[g] > _h) _h = y[g]; });
    return {xCol:xCol, y:y, maxD:maxD, maxLabelW:maxLabelW, height:_h + 12};
  }
  function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function render(){
    var vis = computeVisible();
    var lo = layout(vis);
    prevY = lo.y;   // P45：记录本次布局的 y 坐标，供下一次渲染沿用（位置记忆）
    var W = lo.xCol[lo.maxD] + R * 2 + (lo.maxLabelW[lo.maxD] || 40) + MARGIN + 46;
    var H = MARGIN * 2 + Math.max(lo.height, Y_GAP);
    var parts = [];
    parts.push('<svg class="cg-local-svg" xmlns="' + svgNS + '" width="' + Math.ceil(W) +
               '" height="' + Math.ceil(H) + '" viewBox="0 0 ' + Math.ceil(W) + ' ' + Math.ceil(H) +
               '" font-family="Consolas,Segoe UI,Microsoft YaHei,sans-serif">');
    vis.edges.forEach(function(e){
      var p = e[0], c = e[1];
      var x1 = lo.xCol[vis.depthOf[p]], y1 = MARGIN + lo.y[p];
      var x2 = lo.xCol[vis.depthOf[c]], y2 = MARGIN + lo.y[c];
      var mx = (x1 + x2) / 2;
      var sameCycle = inCycle(p) && inCycle(c) && sccOf[p] === sccOf[c] && sccOf[p] !== -1;
      parts.push('<path class="cg-edge' + (sameCycle ? ' cg-edge-cycle' : '') + '" data-p="' + p + '" data-c="' + c +
                 '" d="M ' + x1.toFixed(1) + ',' + y1.toFixed(1) +
                 ' C ' + mx.toFixed(1) + ',' + y1.toFixed(1) +
                 ' ' + mx.toFixed(1) + ',' + y2.toFixed(1) +
                 ' ' + x2.toFixed(1) + ',' + y2.toFixed(1) + '"/>');
      // P21：调用顺序注释——callee 方向在连线上标注「第几次调用」（按源码调用顺序，
      // down[p] 即为按顺序的被调列表）。caller 方向无「调用时序」语义，故不标注。
      if(dir === 'callee'){
        var _lst = down[p] || [];
        var _oi = _lst.indexOf(c);
        if(_oi >= 0){
          var my = (y1 + y2) / 2;
          parts.push('<text class="cg-ord" x="' + mx.toFixed(1) + '" y="' + (my - 3).toFixed(1) +
                     '" text-anchor="middle">' + (_oi + 1) + '</text>');
        }
      }
    });
    vis.nodes.forEach(function(g){
      var m = meta[g];
      if(!m) return;   // P30：防御性兜底，避免损坏数据（meta 缺失）导致整页 JS 崩溃
      var x = lo.xCol[vis.depthOf[g]], y = MARGIN + lo.y[g];
      var color = KIND_COLOR[m.k] || "#0969da";
      var isRoot = (g === curRoot);
      var stroke = isRoot ? ' stroke="#0d1117" stroke-width="1.5"' : '';
      var lx = x + R + LABEL_PAD;
      var label = labelOf(g);
      var lw = label.length * CHAR_W;
      var inner = '';
      inner += '<circle class="cg-node" cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) +
                '" r="' + R + '" fill="' + color + '"' + stroke + '/>';
      inner += '<rect x="' + (lx - 1.5).toFixed(1) + '" y="' + (y - 8.5).toFixed(1) +
                '" width="' + (lw + 3).toFixed(1) + '" height="17" rx="2" fill="#ffffff" opacity="0.85"/>';
      inner += '<text x="' + lx.toFixed(1) + '" y="' + (y + 4).toFixed(1) +
                '" font-size="12" fill="' + (isRoot ? '#0d1117' : '#1f2328') + '"' +
                (isRoot ? ' font-weight="600"' : '') + '>' + esc(label) + '</text>';
      // P18：节点 tooltip 同时展示「所属文件 + 函数简要说明」，悬停即可看懂该函数
      var _tt = "";
      if(m.r) _tt += m.r;
      if(m.d) _tt += (m.r ? " — " : "") + m.d;
      if(_tt) inner += '<title>' + esc(_tt) + '</title>';
      // P21：注释——函数简要说明 caption。所有带说明（header 注释 description）的节点
      // 均在节点下方显示注释（根/当前高亮节点显示全文强调，其余截断，避免拥挤）。
      if(m.d){
        var _dFull = (isRoot || g === active);
        var _d = (!_dFull && m.d.length > 18) ? m.d.slice(0, 18) + "…" : m.d;
        inner += '<text class="cg-desc' + (_dFull ? ' cg-desc-full' : '') + '" x="' + x.toFixed(1) +
                  '" y="' + (y + R + 13).toFixed(1) + '" text-anchor="middle">' + esc(_d) + '</text>';
      }
      // P-rev R7：节点携带 data-sym=rel::name，供跨页精确联动（点击函数名全站高亮）
      var _sym = (m.p ? m.p : "") + "::" + m.n;
      parts.push('<g class="cg-node-g" data-gid="' + g + '" data-sym="' + esc(_sym) + '" tabindex="0" role="button" aria-label="函数 ' + esc(m.n) + '">' + inner + '</g>');
      // P16-A：源码跳转按钮（↗），点击平滑滚动并脉冲对应源码行（同文件）或跳转到该函数源码页（跨文件）
      // P28：源码跳转按钮（↗）仅在 --browse 站点（存在独立源码页，SITE_REL 非空）渲染；
      // 单文件 HTML 报告无源码页，渲染它会导致点击跳转到不存在的 src/*.html（404）。
      if(m.l != null && m.p && SITE_REL !== ''){
        var sx = lx + lw + 20;
        parts.push('<g class="cg-src-btn" data-gid="' + g + '" data-p="' + esc(m.p) + '" data-l="' + m.l + '" tabindex="0" role="button" aria-label="跳转到 ' + esc(m.n) + ' 源码">' +
                   '<circle cx="' + sx.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="6" fill="#0d1117" opacity="0.85"/>' +
                   '<text x="' + sx.toFixed(1) + '" y="' + (y + 3.5).toFixed(1) + '" font-size="9" fill="#fff" text-anchor="middle">↗</text>' +
                   '<title>跳转到源码行 ' + m.l + '</title></g>');
      }
      // P15：循环调用徽标（红色虚线 ↺）。处于循环中（含自递归）的节点渲染此徽标，
      // 点击展开并高亮整个循环（SCC）的全部节点与边（见 cycleHighlight）。
      if(inCycle(g)){
        var hasSrc = (m.l != null && m.p && SITE_REL !== '');
        var cycX = lx + lw + (hasSrc ? 38 : 20);
        var cycTip = (sccOf[g] === -1)
          ? '循环调用（自递归：' + esc(m.n) + ' 调用自身）'
          : '循环调用（环内 ' + (sccList[sccOf[g]] ? sccList[sccOf[g]].length : '?') + ' 个函数形成闭环），点击高亮整个循环';
        parts.push('<g class="cg-cycle-badge" data-gid="' + g + '" tabindex="0" role="button" aria-label="高亮循环调用">' +
                   '<circle cx="' + cycX.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="6" />' +
                   '<text x="' + cycX.toFixed(1) + '" y="' + (y + 3.5).toFixed(1) +
                   '" text-anchor="middle">\u21ba</text>' +
                   '<title>' + cycTip + '</title></g>');
      }
      var links = adjOf(g);
      if(links.length){
        var bx = lx + lw + 6, by = y;
        var sign = expanded[g] ? '−' : '+';
        parts.push('<g class="cg-badge" data-gid="' + g + '" tabindex="0" role="button" aria-label="' + (expanded[g] ? '折叠' : '展开') + ' ' + esc(m.n) + '">' +
                   '<circle cx="' + bx.toFixed(1) + '" cy="' + by.toFixed(1) + '" r="7" />' +
                   '<text x="' + bx.toFixed(1) + '" y="' + (by + 4).toFixed(1) +
                   '" text-anchor="middle">' + sign + '</text></g>');
      }
    });
    // P30：达到 MAX_NODES 上限时给出「已截断」提示，引导用搜索/下钻聚焦，而非静默丢节点。
    if(vis.truncated){
      parts.push('<text x="' + MARGIN + '" y="' + Math.ceil(H - 6) +
                 '" font-size="11" fill="#9a6700">⚠ 节点过多，仅展示前 ' + MAX_NODES +
                 ' 个；可用搜索或逐级下钻聚焦。</text>');
    }
    parts.push('</svg>');
    // P83：视图工具栏（缩放/复位/适合窗口），独立于 SVG 之外，随每次渲染重建。
    parts.push('<div class="cg-toolbar">' +
               '<button type="button" data-cg-action="zoom-out" title="缩小">−</button>' +
               '<button type="button" data-cg-action="zoom-in" title="放大">+</button>' +
               '<span class="cg-zoom-pct">' + Math.round(cgZoom * 100) + '%</span>' +
               '<button type="button" data-cg-action="fit" title="适合窗口">⛶</button>' +
               '<button type="button" data-cg-action="reset" title="复位视图">⟲</button>' +
               '<span class="cg-tip">滚轮缩放 · 拖拽平移 · 双击节点设为新焦点</span></div>');
    lastW = W;
    lastH = H;
    host.innerHTML = parts.join('');
    cgApplyView();
  }
  // P83：把缩放/平移状态应用到 svg（CSS transform，transform-origin 0 0）。
  function cgApplyView(){
    var svg = host.querySelector('svg.cg-local-svg');
    if(!svg) return;
    svg.style.transformOrigin = '0 0';
    svg.style.transform = 'translate(' + cgPanX + 'px,' + cgPanY + 'px) scale(' + cgZoom + ')';
    var pct = host.querySelector('.cg-zoom-pct');
    if(pct) pct.textContent = Math.round(cgZoom * 100) + '%';
  }
  // P83：以屏幕坐标 (cx,cy) 为中心缩放（保持该点在内容坐标系中的位置不动）。
  function cgZoomAt(factor, cx, cy){
    var rect = host.getBoundingClientRect();
    var px = (cx - rect.left - cgPanX) / cgZoom;
    var py = (cy - rect.top - cgPanY) / cgZoom;
    var nz = Math.max(0.15, Math.min(4, cgZoom * factor));
    cgPanX = cx - rect.left - px * nz;
    cgPanY = cy - rect.top - py * nz;
    cgZoom = nz;
    cgApplyView();
  }
  // P83：适合窗口——让整张调用图适配宿主可视区域（不放大，只可能缩小）。
  function cgFit(){
    var cw = host.clientWidth || 600, ch = host.clientHeight || 300;
    var w = lastW || cw, h = lastH || ch;
    cgZoom = Math.max(0.15, Math.min(1, cw / w, ch / h));
    cgPanX = (cw - w * cgZoom) / 2;
    cgPanY = (ch - h * cgZoom) / 2;
    cgApplyView();
  }
  // P83：复位视图（100% 缩放、无平移）。
  function cgResetView(){
    cgZoom = 1; cgPanX = 0; cgPanY = 0;
    cgApplyView();
  }
  function clearAll(){
    var ne = host.querySelectorAll('.cg-node-g');
    for(var i = 0; i < ne.length; i++){ ne[i].classList.remove('hl','dim'); }
    var ee = host.querySelectorAll('.cg-edge');
    for(var j = 0; j < ee.length; j++){ ee[j].classList.remove('hl','dim'); }
    active = null;
  }
  // P15：以给定节点集合高亮调用图（循环高亮用）：命中节点 hl、其余 dim，边同理；
  // 可选 pulseGid 触发 cg-pulse 脉冲定位。
  function highlightSet(nodeSet, pulseGid){
    var ne = host.querySelectorAll('.cg-node-g');
    for(var i = 0; i < ne.length; i++){
      var nid = +ne[i].getAttribute('data-gid');
      var on = !!nodeSet[nid];
      ne[i].classList.toggle('hl', on);
      ne[i].classList.toggle('dim', !on);
    }
    var ee = host.querySelectorAll('.cg-edge');
    for(var e = 0; e < ee.length; e++){
      var ep = +ee[e].getAttribute('data-p'), ec = +ee[e].getAttribute('data-c');
      var onE = !!nodeSet[ep] && !!nodeSet[ec];
      ee[e].classList.toggle('hl', onE);
      ee[e].classList.toggle('dim', !onE);
    }
    if(pulseGid != null){
      var first = host.querySelector('.cg-node-g[data-gid="' + pulseGid + '"]');
      if(first){
        first.classList.remove('cg-pulse'); void first.getBoundingClientRect();
        first.classList.add('cg-pulse');
        try { first.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch(e2){}
      }
    }
    active = (pulseGid != null) ? pulseGid : null;
  }
  // P15：点击循环徽标 → 展开并高亮整个循环（SCC）节点与边。
  function cycleHighlight(gid){
    var id = sccOf[gid];
    if(id == null) return;
    var set = {};
    if(id === -1){ set[gid] = 1; }
    else {
      var comp = sccList[id] || [];
      for(var i = 0; i < comp.length; i++){ set[comp[i]] = 1; }
    }
    for(var k in set){ expanded[+k] = true; }
    render();
    highlightSet(set, gid);
    cycVal = gid; focusVal = ''; _cgSyncHash();
  }
  host.addEventListener('click', function(ev){
    // P28：阻止事件冒泡到 document 级点击清理（VARFLOW_JS 的 clearHl/clearIdentHl/cgClearAll），
    // 避免「点击环徽标高亮环路 / 点击路径/影响面高亮」后立刻被 document 处理器清掉。
    if(ev.stopPropagation) ev.stopPropagation();
    // P83：拖拽平移结束后抑制其随后的 click，避免误触节点动作 / 徽标。
    if(cgDrag && cgDrag.moved){ ev.preventDefault(); cgDrag = null; return; }
    // P83：工具栏按钮（缩放 / 适合窗口 / 复位）。
    var tb = (ev.target && ev.target.closest) ? ev.target.closest('[data-cg-action]') : null;
    if(tb){
      var act = tb.getAttribute('data-cg-action');
      if(act === 'zoom-in'){ cgZoomAt(1.25, host.clientWidth / 2, host.clientHeight / 2); }
      else if(act === 'zoom-out'){ cgZoomAt(0.8, host.clientWidth / 2, host.clientHeight / 2); }
      else if(act === 'fit'){ cgFit(); }
      else if(act === 'reset'){ cgResetView(); }
      return;
    }
    // P16-A：源码跳转按钮（↗）优先处理，避免触发链路高亮 / 徽标折叠
    var srcBtn = (ev.target && ev.target.closest) ? ev.target.closest('.cg-src-btn') : null;
    if(srcBtn){
      var sg = +srcBtn.getAttribute('data-gid');
      gotoSource(meta[sg]);
      return;
    }
    var cyc = (ev.target && ev.target.closest) ? ev.target.closest('.cg-cycle-badge') : null;
    if(cyc){
      cycleHighlight(+cyc.getAttribute('data-gid'));
      return;
    }
    var badge = (ev.target && ev.target.closest) ? ev.target.closest('.cg-badge') : null;
    if(badge){
      var bg = +badge.getAttribute('data-gid');
      expanded[bg] = !expanded[bg];
      render();
      _cgSyncHash();
      return;
    }
    var gnode = (ev.target && ev.target.closest) ? ev.target.closest('.cg-node-g') : null;
    if(!gnode){ if(active){ clearAll(); _cgSyncHash(); } return; }
    var g = +gnode.getAttribute('data-gid');
    if(ev.shiftKey){
      // Shift 点击：始终在新标签打开该函数的源码页（兼容两种输出）。
      var h = hrefOf(g);
      if(h) window.open(h, '_blank');
      return;
    }
    // 普通点击节点：
    //  --browse 站点（SITE_REL 非空）：弹出「函数预览」面板（签名 / 说明 / 影响面 / 跳转按钮），
    //    先看清函数接口再决定是否进入源码；↗ 按钮仍可直达源码，Shift 点击仍新标签打开。
    //  单文件 HTML 报告（SITE_REL 为空）：改为「下钻 / 折叠」该节点子树（与 +/- 徽标一致），
    //    非破坏性，避免「点击子函数后整个图只剩本函数」的观感。
    if(SITE_REL !== ''){
      // P83：单击防抖——240ms 内若再次点击（构成双击）则取消预览面板，避免
      // 「双击聚焦」时预览面板闪现；双击动作由 dblclick 处理器接管。
      if(cgClickTimer) clearTimeout(cgClickTimer);
      cgClickTimer = setTimeout(function(){ cgClickTimer = null; cgShowPreview(g); }, 240);
    } else {
      if(adjOf(g).length){
        expanded[g] = !expanded[g];
        render();
        _cgSyncHash();
      } else {
        // 叶子节点无子级可展开：仅脉冲定位反馈，不变暗整图。
        var _n = host.querySelector('.cg-node-g[data-gid="' + g + '"]');
        if(_n){ _n.classList.remove('cg-pulse'); void _n.getBoundingClientRect(); _n.classList.add('cg-pulse'); }
      }
    }
  });

  // P29：键盘无障碍——Enter / Space 触发与鼠标点击等价的操作（SVG <g> 无法原生 click，
  // 故聚焦后派发合成 click 事件冒泡到上面的 click 监听，复用同一套动作逻辑）。
  host.addEventListener('keydown', function(ev){
    if(ev.key !== 'Enter' && ev.key !== ' ' && ev.key !== 'Spacebar'){ return; }
    var t = ev.target;
    if(!t || !t.closest) return;
    var el = t.closest('.cg-node-g,.cg-src-btn,.cg-cycle-badge,.cg-badge');
    if(!el) return;
    ev.preventDefault();
    try {
      var cev;
      if(typeof MouseEvent === 'function'){ cev = new MouseEvent('click', {bubbles:true, cancelable:true}); }
      else { cev = document.createEvent('MouseEvents'); cev.initEvent('click', true, true); }
      el.dispatchEvent(cev);
    } catch(e){}
  });

  // P29：节点悬浮详情卡片——悬停展示函数名/类型/文件:行/圈复杂度/扇入扇出/影响面依赖面/说明，
  // 并提供「跳转源码 / 影响面」快捷按钮（数据来自 meta + 全局 down/up 邻接）。
  // P83：拖拽平移画布——空白区按住左键拖动；交互元素（按钮/徽标）不启动拖拽。
  host.addEventListener('mousedown', function(ev){
    if(ev.button !== 0) return;
    var hit = (ev.target && ev.target.closest)
      ? ev.target.closest('button,.cg-badge,.cg-src-btn,.cg-cycle-badge') : null;
    if(hit) return;
    cgDrag = {x: ev.clientX, y: ev.clientY, px: cgPanX, py: cgPanY, moved: false};
  });
  host.addEventListener('mousemove', function(ev){
    if(cgDrag){
      var dx = ev.clientX - cgDrag.x, dy = ev.clientY - cgDrag.y;
      if(Math.abs(dx) > 2 || Math.abs(dy) > 2){
        cgDrag.moved = true;
        cgPanX = cgDrag.px + dx;
        cgPanY = cgDrag.py + dy;
        cgApplyView();
      }
      return;
    }
    var gn = (ev.target && ev.target.closest) ? ev.target.closest('.cg-node-g') : null;
    if(gn){ cgShowHover(+gn.getAttribute('data-gid'), ev.clientX, ev.clientY); }
    else { cgHideHover(); }
  });
  host.addEventListener('mouseup', function(){ cgDrag = null; });
  host.addEventListener('mouseleave', function(){ cgDrag = null; cgHideHover(); });
  // P83：滚轮以鼠标位置为中心缩放。默认（未缩放且内容超高）放行原生滚动条；
  // Ctrl+滚轮或已放大时执行缩放，避免「大图无法滚动」。
  host.addEventListener('wheel', function(ev){
    var contentTall = lastH > host.clientHeight - 8;
    if(!ev.ctrlKey && contentTall && cgZoom <= 1.001) return;
    ev.preventDefault();
    ev.stopPropagation();
    cgZoomAt(ev.deltaY < 0 ? 1.15 : 1 / 1.15, ev.clientX, ev.clientY);
  }, {passive: false});
  // P83：双击节点 → 把该节点设为新的根（聚焦其子树），重置展开状态与视图。
  host.addEventListener('dblclick', function(ev){
    ev.stopPropagation();
    var gn = (ev.target && ev.target.closest) ? ev.target.closest('.cg-node-g') : null;
    if(!gn) return;
    if(cgClickTimer){ clearTimeout(cgClickTimer); cgClickTimer = null; }
    if(window.cgHidePreview) window.cgHidePreview();
    var g = +gn.getAttribute('data-gid');
    if(!meta[g] || g === curRoot) return;
    curRoot = g;
    expanded = {}; expanded[curRoot] = true;
    focusVal = ''; cycVal = null; active = null;
    cgResetView();
    render();
    _cgSyncHash();
    host.__cgRoot = curRoot;
  });

  // P16-A：跳转 / 脉冲对应源码行。同文件则原地平滑滚动 + 脉冲高亮；跨文件则导航跳转。
  function gotoSource(m){
    if(!m) return;
    var href = SITE_REL + m.p + '#L' + m.l;
    var curBase = (location.pathname.split('/').pop() || '').toLowerCase();
    var tgtBase = (m.p.split('/').pop() || '').toLowerCase();
    if(curBase === tgtBase){
      var lineEl = document.getElementById('L' + m.l);
      if(lineEl){
        lineEl.scrollIntoView({ block: 'center', behavior: 'smooth' });
        lineEl.classList.remove('cg-src-pulse'); void lineEl.getBoundingClientRect();
        lineEl.classList.add('cg-src-pulse');
      }
    } else {
      location.href = href;
    }
  }

  // 调用图搜索 / 聚焦（P14）：输入函数名（子串匹配，忽略大小写），自动展开其全部
  // 祖先调用路径使其可见，并以脉冲动画定位高亮。复用现有 expanded / render /
  // highlightChain 闭包状态与 cg-pulse 视觉，dim 其余节点形成聚焦效果。
  host._cgFocus = function(q){
    q = (q || '').toString().trim().toLowerCase();
    if(!q){ clearAll(); return; }
    var matches = [];
    for(var g = 0; g < meta.length; g++){
      if(meta[g] && meta[g].n && meta[g].n.toLowerCase().indexOf(q) >= 0) matches.push(g);
    }
    if(!matches.length){ clearAll(); return; }
    // 沿反向邻接（callee→up，caller→down）展开所有祖先，保证匹配节点可达。
    matches.forEach(function(g){
      var stack = [g], seen = {};
      while(stack.length){
        var cur = stack.pop();
        if(seen[cur]) continue; seen[cur] = 1;
        expanded[cur] = true;
        var rev = (dir === 'callee' ? up : down)[cur] || [];
        for(var i = 0; i < rev.length; i++){ if(!seen[rev[i]]) stack.push(rev[i]); }
      }
    });
    render();
    var ne = host.querySelectorAll('.cg-node-g');
    for(var i = 0; i < ne.length; i++){
      var nid = +ne[i].getAttribute('data-gid');
      var on = matches.indexOf(nid) >= 0;
      ne[i].classList.toggle('hl', on);
      ne[i].classList.toggle('dim', !on);
    }
    active = matches[0];
    var first = host.querySelector('.cg-node-g[data-gid="' + matches[0] + '"]');
    if(first){
      first.classList.remove('cg-pulse');
      void first.getBoundingClientRect();
      first.classList.add('cg-pulse');
      try { first.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch(e){}
    }
    focusVal = q; cycVal = null; _cgSyncHash();
  };
  // 调用图名称联动高亮（P16-B）：输入精确函数名，自动展开其全部祖先路径并脉冲定位。
  // 与 _cgFocus（子串搜索）的区别是精确匹配，供源码页点击「函数名」时反向联动调用图。
  host._cgFocusName = function(name){
    name = (name || '').toString().trim();
    if(!name){ clearAll(); return; }
    var matches = [];
    for(var g = 0; g < meta.length; g++){ if(meta[g] && meta[g].n === name) matches.push(g); }
    if(!matches.length){ clearAll(); return; }
    matches.forEach(function(g){
      var stack = [g], seen = {};
      while(stack.length){
        var cur = stack.pop();
        if(seen[cur]) continue; seen[cur] = 1;
        expanded[cur] = true;
        var rev = (dir === 'callee' ? up : down)[cur] || [];
        for(var i = 0; i < rev.length; i++){ if(!seen[rev[i]]) stack.push(rev[i]); }
      }
    });
    render();
    var ne = host.querySelectorAll('.cg-node-g');
    for(var i = 0; i < ne.length; i++){
      var nid = +ne[i].getAttribute('data-gid');
      var on = matches.indexOf(nid) >= 0;
      ne[i].classList.toggle('hl', on);
      ne[i].classList.toggle('dim', !on);
    }
    active = matches[0];
    var first = host.querySelector('.cg-node-g[data-gid="' + matches[0] + '"]');
    if(first){
      first.classList.remove('cg-pulse');
      void first.getBoundingClientRect();
      first.classList.add('cg-pulse');
      try { first.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch(e){}
    }
    focusVal = name; cycVal = null; _cgSyncHash();
  };
  // P17：从 URL # 状态还原本宿主视图（由 _cgApplyHash 调用）。
  host.__cgRestore = function(st){
    if(st.dir === 'callee' || st.dir === 'caller') dir = st.dir;
    // P83：分享链接可能携带与当前不同的根（双击聚焦产生），据此切换根并保持视图。
    if(st.root != null && meta[st.root] && st.root !== curRoot){
      curRoot = st.root;
      host.__cgRoot = curRoot;
    }
    expanded = {}; expanded[curRoot] = true;
    if(st.exp){ for(var i = 0; i < st.exp.length; i++){ var eg = st.exp[i]; if(meta[eg]) expanded[eg] = true; } }
    focusVal = st.focus || '';
    cycVal = (st.cyc == null) ? null : st.cyc;
    render();
    if(focusVal){ host._cgFocus(focusVal); }
    else if(cycVal != null && sccOf[cycVal] != null){ cycleHighlight(cycVal); }
    else { clearAll(); }
  };
  render();
}

// 全局调用图搜索（P14）：遍历页面内所有 .cg-host 并调用其聚焦方法。供 HTML 报告
// 顶部单一搜索框使用（一次搜索聚焦全部热点函数的调用 / 被调用图）。
window.cgFocus = function(q){
  var hosts = document.querySelectorAll('.cg-host');
  for(var h = 0; h < hosts.length; h++){
    if(hosts[h]._cgFocus) hosts[h]._cgFocus(q);
  }
};
// 调用图名称联动高亮（P16-B）：供源码页点击「函数名」时调用，遍历页面内所有
// .cg-host 并对名为 name 的函数节点执行精确匹配聚焦（展开祖先路径 + 脉冲定位）。
window.cgHighlightName = function(name){
  var hosts = document.querySelectorAll('.cg-host');
  for(var h = 0; h < hosts.length; h++){
    if(hosts[h]._cgFocusName) hosts[h]._cgFocusName(name);
  }
};
// 清空全部调用图聚焦（供点击空白处时复位调用图高亮，与源码高亮保持一致）。
window.cgClearAll = function(){
  var hosts = document.querySelectorAll('.cg-host');
  for(var h = 0; h < hosts.length; h++){
    if(hosts[h]._cgFocus) hosts[h]._cgFocus('');
  }
};
// P21：追本溯源——「溯源（展开全部）」/「收缩」全局入口，作用于页面内所有调用图。
// 展开全部：callee 图展开完整下游（被调链条到叶子），caller 图展开完整上游（调用方链条
// 溯源到入口 / 根）。收缩：复位为默认浅层（根 + 直接子一层）。
window.cgExpandAll = function(){
  var hosts = document.querySelectorAll('.cg-host');
  for(var h = 0; h < hosts.length; h++){ if(hosts[h].__cgExpandAll) hosts[h].__cgExpandAll(); }
};
window.cgCollapseAll = function(){
  var hosts = document.querySelectorAll('.cg-host');
  for(var h = 0; h < hosts.length; h++){ if(hosts[h].__cgCollapseAll) hosts[h].__cgCollapseAll(); }
};
// P28：作用域版「溯源/收缩」——仅在触发按钮所属的函数卡片（details.callgraph）内展开/收缩，
// 避免在含多个函数卡片的源码页上误操作整页所有调用图。HTML 报告顶部的全局控件不在卡片内，
// 则回退为全局（作用于全部 .cg-host）。
window.cgExpandAllScoped = function(btn){
  var det = btn ? (btn.closest ? btn.closest('details.callgraph') : null) : null;
  var hosts = det ? det.querySelectorAll('.cg-host') : document.querySelectorAll('.cg-host');
  for(var h = 0; h < hosts.length; h++){ if(hosts[h].__cgExpandAll) hosts[h].__cgExpandAll(); }
};
window.cgCollapseAllScoped = function(btn){
  var det = btn ? (btn.closest ? btn.closest('details.callgraph') : null) : null;
  var hosts = det ? det.querySelectorAll('.cg-host') : document.querySelectorAll('.cg-host');
  for(var h = 0; h < hosts.length; h++){ if(hosts[h].__cgCollapseAll) hosts[h].__cgCollapseAll(); }
};

// ---------------------------------------------------------------------------
// P20：调用图最短可达路径（BFS）。在全局邻接表 window.__CG__.down（调用方向）上求
// 「从 A 到 B」的最短调用路径，返回 gid 序列并：① 在当前页所有 .cg-host 中展开并
// 高亮该路径；② 渲染成可点击的节点列表（每项跳转到对应函数源码）；③ 把查询写入
// URL # 的 cgp= 字段以便分享 / 刷新 / 前进后退自动还原（与 P17 状态分享并存）。
// ---------------------------------------------------------------------------
function cgNameGids(name){
  var meta = (window.__CG__ && window.__CG__.meta) || [];
  name = (name || '').toString().trim();
  if(name === '') return [];
  var asGid = parseInt(name, 10);
  if(!isNaN(asGid) && meta[asGid]) return [asGid];   // 允许直接传 gid
  var exact = [], subs = [];
  for(var g = 0; g < meta.length; g++){
    if(!meta[g] || !meta[g].n) continue;
    if(meta[g].n === name) exact.push(g);
    else if(meta[g].n.toLowerCase().indexOf(name.toLowerCase()) >= 0) subs.push(g);
  }
  return exact.length ? exact : subs;                 // 优先精确匹配，其次子串匹配
}
function cgBFS(a, b){
  if(a === b) return [a];
  var down = (window.__CG__ && window.__CG__.down) || {};
  var prev = {}, visited = {}, q = [a]; visited[a] = 1;
  while(q.length){
    var cur = q.shift();
    var adj = down[cur] || [];
    for(var i = 0; i < adj.length; i++){
      var w = adj[i];
      if(visited[w]) continue;
      visited[w] = 1; prev[w] = cur;
      if(w === b){
        var path = [b], x = cur;
        while(x !== a){ path.push(x); x = prev[x]; }
        path.push(a); path.reverse();
        return path;
      }
      q.push(w);
    }
  }
  return null;
}
// 全局版源码跳转（与 initOneCG 内的 gotoSource 同语义，供路径列表节点点击使用）。
function cgGotoSource(m){
  if(!m) return;
  var sr = window.__CG_SITE_REL__ || "";
  var href = sr + m.p + '#L' + m.l;
  var curBase = (location.pathname.split('/').pop() || '').toLowerCase();
  var tgtBase = (m.p.split('/').pop() || '').toLowerCase();
  if(curBase === tgtBase){
    var el = document.getElementById('L' + m.l);
    if(el){ el.scrollIntoView({block:'center', behavior:'smooth'}); el.classList.remove('cg-src-pulse'); void el.getBoundingClientRect(); el.classList.add('cg-src-pulse'); }
  } else {
    location.href = href;
  }
}
function cgPathResult(msg){
  var box = document.getElementById('cg-path-result');
  if(box) box.innerHTML = '<div class="cg-path-msg">' + msg + '</div>';
}
function cgPathResultHTML(gids){
  var box = document.getElementById('cg-path-result');
  if(!box) return;
  if(!gids || !gids.length){ box.innerHTML = ''; return; }
  var meta = (window.__CG__ && window.__CG__.meta) || [];
  var html = '<ol class="cg-path-list">';
  for(var i = 0; i < gids.length; i++){
    var m = meta[gids[i]];
    if(!m) continue;
    var fileShort = (m.p || '').replace(/^.*\\//, '').replace(/\\.html$/, '');
    html += '<li class="cg-path-node" data-gid="' + gids[i] + '">'
          + '<code>' + (m.n || ('gid' + gids[i])) + '</code> '
          + '<span class="muted">' + fileShort + ' 第 ' + (m.l || '?') + ' 行</span></li>';
  }
  html += '</ol>';
  box.innerHTML = html;
  // browse 站点（有独立源码页）时，路径节点可点击跳转到对应函数源码
  if((window.__CG_SITE_REL__ || '') !== ''){
    var items = box.querySelectorAll('.cg-path-node');
    for(var k = 0; k < items.length; k++){
      (function(li){
        li.style.cursor = 'pointer';
        li.addEventListener('click', function(){
          var g = +li.getAttribute('data-gid');
          cgGotoSource(meta[g]);
        });
      })(items[k]);
    }
  }
}
// 在页面内所有 .cg-host 中展开并高亮给定路径 gid 集合。
window.cgHighlightPathGids = function(gids){
  if(!gids || !gids.length) return;
  var hosts = document.querySelectorAll('.cg-host');
  for(var h = 0; h < hosts.length; h++){ if(hosts[h].__cgExpandAncestors) hosts[h].__cgExpandAncestors(gids); }
  for(var h2 = 0; h2 < hosts.length; h2++){ if(hosts[h2].__cgHighlightGids) hosts[h2].__cgHighlightGids(gids); }
};
// 主入口：从 fromName 到 toName 求最短调用路径并可视化 / 分享。
window.cgFindPath = function(fromName, toName, silent){
  var G = window.__CG__;
  if(!G || !G.meta) return null;
  var fromGids = cgNameGids(fromName), toGids = cgNameGids(toName);
  if(!fromGids.length || !toGids.length){
    cgPathResult('未匹配到函数：' + (fromGids.length ? '' : '起点「' + fromName + '」') + (toGids.length ? '' : '终点「' + toName + '」') + '。请检查拼写，或输入更精确的函数名。');
    return null;
  }
  var best = null;
  for(var i = 0; i < fromGids.length; i++){
    for(var j = 0; j < toGids.length; j++){
      var p = cgBFS(fromGids[i], toGids[j]);
      if(p && (!best || p.length < best.length)) best = p;
    }
  }
  if(!best){
    cgPathResult('在调用关系上无法从「' + fromName + '」到达「' + toName + '」：二者可能无调用路径，或方向相反（可互换起点 / 终点重试）。');
    return null;
  }
  window.cgHighlightPathGids(best);
  cgPathResultHTML(best);
  if(!silent){
    window.__CG_PATH_QUERY__ = {from: fromName, to: toName};
    window.__CG_PATH_APPLIED__ = String(fromName) + '~' + String(toName);
    _cgSyncHash();
  }
  return best;
};
// 清除路径查询：清空结果、复位高亮并回写 URL（去掉 cgp=）。
window.cgClearPath = function(){
  var box = document.getElementById('cg-path-result');
  if(box) box.innerHTML = '';
  window.__CG_PATH_QUERY__ = null;
  window.__CG_PATH_APPLIED__ = null;
  if(window.cgClearAll) window.cgClearAll();
  _cgSyncHash();
};
// 解析 URL # 中的 cgp= 字段 → {from, to}；无则返回 null。
function _cgParsePath(){
  var raw = '';
  try { raw = decodeURIComponent(String(location.hash || '').replace(/^#/, '')); } catch(e){ raw = ''; }
  var i = raw.indexOf('cgp=');
  if(i < 0) return null;
  var body = raw.slice(i + 4).split('&')[0];
  var f = body.split('~');
  if(f.length < 2) return null;
  return {from: f[0], to: f[1]};
}

// ---------------------------------------------------------------------------
// P22：改动影响面 / 依赖面分析（传递闭包）。在全局邻接表上沿 up（谁调用了我，影响面）
// 或 down（我调用了谁，依赖面）做 BFS 传递闭包，返回 gid 集合并：① 高亮整片受影响 /
// 被依赖的函数；② 渲染分组结果列表（含函数名 + 文件:行号，可点击跳转）；③ 供源码页
// 每个函数卡片的静态「影响面 / 依赖面」区块与页面顶部的交互面板共用。
// ---------------------------------------------------------------------------
// P45：闭包查询缓存——影响面/依赖面在预览/悬浮/面板中被频繁重复计算，
// 这里按 dir:gid 记忆结果，千级函数项目下预览依旧秒开。
var __CG_CLOSURE_CACHE__ = {};
function cgClosure(startGid, dir){
  var key = dir + ':' + startGid;
  if(__CG_CLOSURE_CACHE__[key]) return __CG_CLOSURE_CACHE__[key];
  var G = window.__CG__;
  var adj = (dir === 'up') ? ((G && G.up) || {}) : ((G && G.down) || {});
  var seen = {}, q = [startGid]; seen[startGid] = 1;
  var out = [];
  while(q.length){
    var cur = q.shift();
    var nbrs = adj[cur] || [];
    for(var i = 0; i < nbrs.length; i++){
      var w = nbrs[i];
      if(seen[w]) continue;
      seen[w] = 1; out.push(w); q.push(w);
    }
  }
  __CG_CLOSURE_CACHE__[key] = out;
  return out;
}
function cgImpactResult(msg){
  var box = document.getElementById('cg-impact-result');
  if(box) box.innerHTML = '<div class="cg-path-msg">' + msg + '</div>';
}
function cgImpactResultHTML(gids, label){
  var box = document.getElementById('cg-impact-result');
  if(!box) return;
  if(!gids || !gids.length){ box.innerHTML = ''; return; }
  var meta = (window.__CG__ && window.__CG__.meta) || [];
  var html = '<div class="cg-path-msg">' + label + '：共 ' + (gids.length - 1) + ' 个函数（含自身 ' + gids.length + ' 项）</div>';
  html += '<ol class="cg-path-list">';
  for(var i = 0; i < gids.length; i++){
    var m = meta[gids[i]];
    if(!m) continue;
    var fileShort = (m.p || '').replace(/^.*\\//, '').replace(/\\.html$/, '');
    html += '<li class="cg-path-node" data-gid="' + gids[i] + '"><code>' + (m.n || ('gid' + gids[i])) + '</code> <span class="muted">' + fileShort + ' 第 ' + (m.l || '?') + ' 行</span></li>';
  }
  html += '</ol>';
  box.innerHTML = html;
  if((window.__CG_SITE_REL__ || '') !== ''){
    var items = box.querySelectorAll('.cg-path-node');
    for(var k = 0; k < items.length; k++){
      (function(li){
        li.style.cursor = 'pointer';
        li.addEventListener('click', function(){
          var g = +li.getAttribute('data-gid');
          cgGotoSource(meta[g]);
        });
      })(items[k]);
    }
  }
}
function cgClosureShow(name, dir, label){
  var gids = cgNameGids(name);
  if(!gids.length){ cgImpactResult('未匹配到函数「' + name + '」。请检查拼写，或输入更精确的函数名。'); return null; }
  var start = gids[0];
  var rest = cgClosure(start, dir);
  var all = [start].concat(rest);
  window.cgHighlightPathGids(all);
  cgImpactResultHTML(all, label);
  return all;
}
window.cgImpactSet = function(name){
  return cgClosureShow(name, 'up', '影响面（谁（传递）调用了它）');
};
window.cgDependencySet = function(name){
  return cgClosureShow(name, 'down', '依赖面（它（传递）依赖谁）');
};
window.cgClearImpact = function(){
  var box = document.getElementById('cg-impact-result');
  if(box) box.innerHTML = '';
  if(window.cgClearAll) window.cgClearAll();
};

// ---------------------------------------------------------------------------
// P29：节点悬浮详情卡片。悬停调用图节点时展示函数名 / 类型 / 文件:行 / 圈复杂度 /
// 扇入扇出 / 影响面依赖面 / 说明，并提供「跳转源码 / 影响面」快捷按钮。
// ---------------------------------------------------------------------------
function cgHoverCard(){
  var c = document.getElementById('cg-hover-card');
  if(!c){
    c = document.createElement('div');
    c.id = 'cg-hover-card';
    c.className = 'cg-hover-card';
    c.style.display = 'none';
    document.body.appendChild(c);
  }
  return c;
}
function cgHideHover(){
  var c = document.getElementById('cg-hover-card');
  if(c) c.style.display = 'none';
}
function cgShowHover(gid, cx, cy){
  var c = cgHoverCard();
  var meta = (window.__CG__ && window.__CG__.meta) || [];
  var m = meta[gid];
  if(!c || !m){ return; }
  var down = (window.__CG__ && window.__CG__.down) || {};
  var up = (window.__CG__ && window.__CG__.up) || {};
  var fanOut = (down[gid] || []).length;
  var fanIn = (up[gid] || []).length;
  var impact = cgClosure(gid, 'up').length;
  var dependency = cgClosure(gid, 'down').length;
  var kindLabel = {main:'主函数', local:'局部函数', method:'方法', constructor:'构造函数', script:'脚本'}[m.k] || m.k || '其他';
  var html = '<div class="cg-hover-title"><code>' + (m.n || ('gid' + gid)) + '</code>'
           + '<span class="cg-hover-kind">' + kindLabel + '</span></div>';
  html += '<div class="cg-hover-row"><span class="cg-hover-k">文件</span>' + (m.r || '—') + ' 第 ' + (m.l || '?') + ' 行</div>';
  if(m.cx != null){ html += '<div class="cg-hover-row"><span class="cg-hover-k">圈复杂度</span>' + m.cx + '</div>'; }
  html += '<div class="cg-hover-row"><span class="cg-hover-k">扇入</span>' + fanIn + '<span class="cg-hover-k"> 扇出</span>' + fanOut + '</div>';
  html += '<div class="cg-hover-row"><span class="cg-hover-k">影响面</span>' + impact + '<span class="cg-hover-k"> 依赖面</span>' + dependency + '</div>';
  if(m.d){ html += '<div class="cg-hover-desc">' + (m.d) + '</div>'; }
  html += '<div class="cg-hover-actions">'
        + '<button type="button" class="cg-hover-btn" data-cg-act="jump" data-cg-gid="' + gid + '">跳转源码</button>'
        + '<button type="button" class="cg-hover-btn" data-cg-act="impact" data-cg-gid="' + gid + '">影响面</button>'
        + '</div>';
  c.innerHTML = html;
  c.style.display = 'block';
  // 定位：跟随鼠标，防越界
  var w = c.offsetWidth || 300, h = c.offsetHeight || 140;
  var left = cx + 14, top = cy + 14;
  if(left + w > window.innerWidth - 8) left = cx - w - 14;
  if(top + h > window.innerHeight - 8) top = cy - h - 14;
  if(left < 8) left = 8;
  if(top < 8) top = 8;
  c.style.left = left + 'px';
  c.style.top = top + 'px';
}
window.cgHoverJump = function(gid){
  var meta = (window.__CG__ && window.__CG__.meta) || [];
  var m = meta[gid];
  if(m){
    // P-rev R46：跳转源码也进入预览历史，配合「上一/下一」在「看调用图 → 看源码」
    // 之间续接探索路径（而非跳走后历史断掉）。
    var H = window.__CG_PREVIEW_HISTORY__;
    var I = window.__CG_PREVIEW_IDX__;
    if(I < 0 || H[I] !== gid){
      H = H.slice(0, I + 1); H.push(gid);
      window.__CG_PREVIEW_HISTORY__ = H; window.__CG_PREVIEW_IDX__ = H.length - 1;
      if(window.cgSavePreviewHistory){ window.cgSavePreviewHistory(); }
    }
    cgGotoSource(m);
  }
};
window.cgHoverImpact = function(gid){
  var meta = (window.__CG__ && window.__CG__.meta) || [];
  var m = meta[gid];
  if(m && m.n && window.cgImpactSet) window.cgImpactSet(m.n);
};
// FE-7：事件委托替代内联 onclick（CSP 友好、可审计；S20 门禁执法）。
if(!window.__cgDelegated){
  window.__cgDelegated = true;
  document.addEventListener('click', function(e){
    var b = e.target && e.target.closest ? e.target.closest('[data-cg-act]') : null;
    if(!b) return;
    var act = b.getAttribute('data-cg-act');
    var gidAttr = b.getAttribute('data-cg-gid');
    var gid = gidAttr == null ? null : (+gidAttr);
    if(act === 'close' && window.cgHidePreview) window.cgHidePreview();
    else if(act === 'prev' && window.cgPreviewPrev) window.cgPreviewPrev();
    else if(act === 'next' && window.cgPreviewNext) window.cgPreviewNext();
    else if(act === 'jump' && window.cgHoverJump) window.cgHoverJump(gid);
    else if(act === 'body' && window.cgPreviewBody) window.cgPreviewBody(gid);
    else if(act === 'impact' && window.cgHoverImpact) window.cgHoverImpact(gid);
  });
}
// P37：跳转到函数体首行（body_start），配合「函数体」按钮快速进入实现
window.cgPreviewBody = function(gid){
  var meta = (window.__CG__ && window.__CG__.meta) || [];
  var m = meta[gid];
  if(m && m.p){ cgGotoSource({p: m.p, l: m.body || m.l}); }
};

// ---------------------------------------------------------------------------
// P36：函数预览——点击调用图节点弹出预览面板，展示函数签名 / 类型 / 文件:行 /
// 圈复杂度 / 扇入扇出 / 影响面依赖面 / 说明，并提供「跳转源码 / 影响面 / 关闭」按钮。
// 避免点击后立即跳走，先看清函数接口再决定是否进入源码。
// ---------------------------------------------------------------------------
function cgPreviewModal(){
  var m = document.getElementById('cg-preview');
  if(!m){
    m = document.createElement('div');
    m.id = 'cg-preview';
    m.className = 'cg-preview-mask';
    m.style.display = 'none';
    m.innerHTML = '<div class="cg-preview-panel" id="cg-preview-panel"></div>';
    m.addEventListener('click', function(ev){
      if(ev.target === m){ cgHidePreview(); }
    });
    document.body.appendChild(m);
  }
  return m;
}
function cgHidePreview(){
  var m = document.getElementById('cg-preview');
  if(m){ m.style.display = 'none'; }
}
// P46：预览历史导航——记录点击预览的函数序列，支持「上一/下一」在调用链中来回穿梭。
// P-rev R42：历史持久化到 localStorage，刷新/跨页后仍可回溯（gid 是全局稳定的）。
window.__CG_PREVIEW_HISTORY__ = [];
window.__CG_PREVIEW_IDX__ = -1;
(function(){
  try{
    var _s = JSON.parse(localStorage.getItem("pony.preview.history") || "null");
    if(_s && Array.isArray(_s.h)){
      window.__CG_PREVIEW_HISTORY__ = _s.h;
      window.__CG_PREVIEW_IDX__ = (_s.i >= 0 && _s.i < _s.h.length) ? _s.i : (_s.h.length - 1);
    }
  }catch(_){}
})();
function cgSavePreviewHistory(){
  try{
    localStorage.setItem("pony.preview.history", JSON.stringify({
      h: window.__CG_PREVIEW_HISTORY__, i: window.__CG_PREVIEW_IDX__
    }));
  }catch(_){}
}
// P-rev R48：清空/恢复探索历史，暴露给工作台面板使用（跨文件越积越长时一键清空）。
window.cgClearPreviewHistory = function(){
  window.__CG_PREVIEW_HISTORY__ = [];
  window.__CG_PREVIEW_IDX__ = -1;
  try{ localStorage.removeItem("pony.preview.history"); }catch(_){}
};
window.cgHistorySize = function(){ return window.__CG_PREVIEW_HISTORY__.length; };
// P-rev R54/R60：把历史条目转成可展示/可跳转的列表（gid -> 可读标签 + 源路径）。
window.cgHistoryList = function(){
  var meta = (window.__CG__ && window.__CG__.meta) || [];
  return window.__CG_PREVIEW_HISTORY__.map(function(gid){
    var m = meta[gid];
    var label = m ? (m.n || m.p || gid) : gid;
    // R60：记录源文件路径与行号，供跨页跳转（不在当前页时也能定位）
    return { id: gid, label: String(label), src: m ? (m.p || null) : null,
             line: m ? (m.l || 0) : 0 };
  });
};
// P-rev R54/R60：跳到历史第 idx 条。当前页有调用图则原地渲染预览；
// 否则（R60）按记录的源路径跨页跳转到源码页并带 ?focus= 定位。
window.cgJumpHistory = function(idx){
  var H = window.__CG_PREVIEW_HISTORY__;
  if(idx >= 0 && idx < H.length){
    window.__CG_PREVIEW_IDX__ = idx;
    if(window.cgSavePreviewHistory){ window.cgSavePreviewHistory(); }
    if(typeof cgRenderPreview === "function" && (window.__CG__ && window.__CG__.meta)){
      cgRenderPreview(H[idx]);
    } else {
      var list = window.cgHistoryList();
      var it = list[idx];
      if(it && it.src){
        // P-rev R64：跳转带 ?focus=<gid>，让目标源码页自动触发该符号的跨页联动高亮
        // （ctxlink 会消费 ?focus= 并调用 focusSym），而不只是定位到行号锚点。
        var url = (window.__CG_SITE_REL__ || "") + "src/" + it.src + ".html"
                + "?focus=" + encodeURIComponent(it.id)
                + "#L" + (it.line || 1);
        location.href = url;
      }
    }
  }
};
function cgShowPreview(gid){
  var H = window.__CG_PREVIEW_HISTORY__;
  var I = window.__CG_PREVIEW_IDX__;
  if(I < 0 || H[I] !== gid){
    H = H.slice(0, I + 1);
    H.push(gid);
    window.__CG_PREVIEW_HISTORY__ = H;
    window.__CG_PREVIEW_IDX__ = H.length - 1;
    cgSavePreviewHistory();
  }
  cgRenderPreview(gid);
}
window.cgPreviewPrev = function(){
  var I = window.__CG_PREVIEW_IDX__;
  if(I > 0){ window.__CG_PREVIEW_IDX__ = I - 1; cgSavePreviewHistory(); cgRenderPreview(window.__CG_PREVIEW_HISTORY__[I - 1]); }
};
window.cgPreviewNext = function(){
  var H = window.__CG_PREVIEW_HISTORY__;
  var I = window.__CG_PREVIEW_IDX__;
  if(I >= 0 && I < H.length - 1){ window.__CG_PREVIEW_IDX__ = I + 1; cgSavePreviewHistory(); cgRenderPreview(H[I + 1]); }
};
function cgRenderPreview(gid){
  var m = cgPreviewModal();
  // P-rev R40：确保任何预览入口（包括节点 hover、外部跳转）都进入导航历史，
  // 否则「上一/下一」按钮无内容可翻，是最常见的「按钮毫无反应」原因。
  var _H = window.__CG_PREVIEW_HISTORY__;
  var _I = window.__CG_PREVIEW_IDX__;
  if(_I < 0 || _H[_I] !== gid){
    _H = _H.slice(0, _I + 1);
    _H.push(gid);
    window.__CG_PREVIEW_HISTORY__ = _H;
    window.__CG_PREVIEW_IDX__ = _H.length - 1;
    if(window.cgSavePreviewHistory){ window.cgSavePreviewHistory(); }
  }
  var meta = (window.__CG__ && window.__CG__.meta) || [];
  var md = meta[gid];
  if(!md){ cgHidePreview(); return; }
  var down = (window.__CG__ && window.__CG__.down) || {};
  var up = (window.__CG__ && window.__CG__.up) || {};
  var fanOut = (down[gid] || []).length;
  var fanIn = (up[gid] || []).length;
  var impact = cgClosure(gid, 'up').length;
  var dependency = cgClosure(gid, 'down').length;
  var kindLabel = {main:'主函数', local:'局部函数', method:'方法', constructor:'构造函数', script:'脚本'}[md.k] || md.k || '其他';
  var html = '<div class="cg-preview-head"><div class="cg-preview-title"><code>' + (md.n || ('gid'+gid)) + '</code>'
           + '<span class="cg-hover-kind">' + kindLabel + '</span></div>'
           + '<button type="button" class="cg-preview-close" data-cg-act="close">×</button></div>';
  if(md.sig){ html += '<div class="cg-preview-sig">' + (md.sig) + '</div>'; }
  html += '<div class="cg-preview-rows">'
        + '<div class="cg-hover-row"><span class="cg-hover-k">文件</span>' + (md.r || '—') + ' 第 ' + (md.l || '?') + ' 行</div>';
  if(md.cx != null){ html += '<div class="cg-hover-row"><span class="cg-hover-k">圈复杂度</span>' + md.cx + '</div>'; }
  html += '<div class="cg-hover-row"><span class="cg-hover-k">扇入</span>' + fanIn + '<span class="cg-hover-k"> 扇出</span>' + fanOut + '</div>';
  html += '<div class="cg-hover-row"><span class="cg-hover-k">影响面</span>' + impact + '<span class="cg-hover-k"> 依赖面</span>' + dependency + '</div>';
  html += '</div>';
  if(md.d){ html += '<div class="cg-preview-desc">' + (md.d) + '</div>'; }
  // P52/P80：同名函数候选（就近解析可视化 + 一键切换解析目标）
  // 列出所有同名候选，标记当前就近解析到的那个；点击任意候选跳转到其源码定义行，
  // 把「看得到」升级为「改得动」——用户可直接切到期望的那个同名实现。
  if(md.dups && md.dups.length > 1){
    var dk = {main:'主函数', local:'局部函数', method:'方法', constructor:'构造函数', script:'脚本'};
    html += '<div class="cg-preview-dups">'
          + '<div class="cg-preview-dups-title">同名函数候选（点击切换解析目标）</div>';
    for(var di = 0; di < md.dups.length; di++){
      var du = md.dups[di];
      html += '<div class="cg-preview-dup' + (du.self ? ' is-self' : '') + '"'
            + ' data-dup-p="' + (du.p || '') + '" data-dup-l="' + (du.l || 1) + '"'
            + ' title="' + (du.self ? '当前就近解析到此处' : '点击切换到此处（跳转源码定义行）') + '">'
            + '<span class="cg-preview-dup-mark">' + (du.self ? '✓' : '↗') + '</span>'
            + '<code>' + (du.r || '') + '</code> 第 ' + (du.l || '?') + ' 行'
            + '<span class="cg-hover-kind">' + (dk[du.k] || du.k || '') + '</span>'
            + '</div>';
    }
    html += '</div>';
  }
  // P37：预览内嵌函数源码片段（定义行起 N 行），让用户不离开调用图即可判断函数实现
  if(md.snip){ html += '<pre class="cg-preview-snip">' + (md.snip) + '</pre>'; }
  // P-rev R40：上一/下一按钮根据历史位置动态禁用，并显示当前进度
  var _I2 = window.__CG_PREVIEW_IDX__, _H2 = window.__CG_PREVIEW_HISTORY__;
  var _hasPrev = _I2 > 0;
  var _hasNext = _I2 >= 0 && _I2 < _H2.length - 1;
  var _posInfo = (_H2 && _H2.length > 0)
      ? ' [' + (_I2 + 1) + '/' + _H2.length + ']'
      : '（尚无历史，点节点进入预览后即可穿梭）';
  html += '<div class="cg-hover-actions">'
        + '<span class="cg-hover-pos">' + _posInfo + '</span>'
        + '<button type="button" class="cg-hover-btn" id="cg-btn-prev"'
        +       (_hasPrev ? '' : ' disabled title="已在历史最早位置"')
        +       ' data-cg-act="prev">上一</button>'
        + '<button type="button" class="cg-hover-btn" id="cg-btn-next"'
        +       (_hasNext ? '' : ' disabled title="已在历史最末位置"')
        +       ' data-cg-act="next">下一</button>'
        + '<button type="button" class="cg-hover-btn" data-cg-act="jump" data-cg-gid="' + gid + '">跳转源码</button>'
        + '<button type="button" class="cg-hover-btn" data-cg-act="body" data-cg-gid="' + gid + '">函数体</button>'
        + '<button type="button" class="cg-hover-btn" data-cg-act="impact" data-cg-gid="' + gid + '">影响面</button>'
        + '<button type="button" class="cg-hover-btn" data-cg-act="close">关闭</button>'
        + '</div>';
  var panel = document.getElementById('cg-preview-panel');
  if(panel){ panel.innerHTML = html; }
  // P41：预览片段「行点击 → 源码定位」——点击某行跳转到源码页对应行并脉冲（双向定位）
  if(panel){
    var lines = panel.querySelectorAll('.cg-snip-line');
    for(var li = 0; li < lines.length; li++){
      (function(lnEl){
        lnEl.addEventListener('click', function(){
          var ln = +lnEl.getAttribute('data-ln');
          if(ln && md.p){ cgGotoSource({p: md.p, l: ln}); }
        });
      })(lines[li]);
    }
    // P80：同名候选点击切换——点击候选跳转到其源码定义行（切换就近解析目标）
    var dupEls = panel.querySelectorAll('.cg-preview-dup');
    for(var di = 0; di < dupEls.length; di++){
      (function(el){
        el.addEventListener('click', function(){
          var p = el.getAttribute('data-dup-p');
          var l = +el.getAttribute('data-dup-l');
          if(p){ cgGotoSource({p: p, l: l}); }
        });
      })(dupEls[di]);
    }
  }
  m.style.display = 'flex';
}
"""

# 以下资产常量由 R2 修复从备份恢复（原整块被误删）：
VIEWSTATE_JS = "\n(function(){\n  'use strict';\n  // 注意：本脚本通常先于声明 __VIEWSTATE_SPEC__ 的 <script> 被解析执行，\n  // 因此 SPEC 必须在 init() 里**延迟读取**，不能在 IIFE 顶部就取值（否则恒为空）。\n  var SPEC = [];\n  function parseHash(){\n    var out = {};\n    var h = (location.hash || '').replace(/^#/, '');\n    if (!h) { return out; }\n    var parts = h.split('&');\n    for (var i = 0; i < parts.length; i++) {\n      var kv = parts[i].split('=');\n      if (kv.length === 2) { out[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1]); }\n    }\n    return out;\n  }\n  function writeHash(){\n    var kv = [];\n    for (var i = 0; i < SPEC.length; i++) {\n      var s = SPEC[i];\n      var el = document.getElementById(s.id);\n      if (!el) { continue; }\n      var v = s.type === 'check' ? (el.checked ? '1' : '0') : String(el.value);\n      if (v !== String(s.def)) { kv.push(s.key + '=' + encodeURIComponent(v)); }\n    }\n    var h = kv.length ? ('#' + kv.join('&')) : '';\n    try {\n      if (history && history.replaceState) {\n        history.replaceState(null, '', location.pathname + location.search + h);\n      } else { location.hash = h; }\n    } catch (e) {}\n  }\n  function applyHash(){\n    var st = parseHash();\n    for (var i = 0; i < SPEC.length; i++) {\n      var s = SPEC[i];\n      var el = document.getElementById(s.id);\n      if (!el) { continue; }\n      var v = (s.key in st) ? st[s.key] : String(s.def);\n      if (s.type === 'check') { el.checked = (v === '1' || v === 'true'); }\n      else { el.value = v; }\n      if (typeof s.apply === 'function') { try { s.apply(); } catch (e) {} }\n    }\n  }\n  function bind(){\n    for (var i = 0; i < SPEC.length; i++) {\n      (function(s){\n        var el = document.getElementById(s.id);\n        if (!el) { return; }\n        var ev = s.type === 'check' ? 'change' : (s.evt || 'change');\n        el.addEventListener(ev, function(){\n          if (typeof s.apply === 'function') { try { s.apply(); } catch (e) {} }\n          writeHash();\n        });\n      })(SPEC[i]);\n    }\n  }\n  function init(){\n    SPEC = window.__VIEWSTATE_SPEC__ || [];\n    if (!SPEC.length) { return; }\n    applyHash();\n    bind();\n    writeHash();     // 清掉与默认值相同的冗余参数，保持 URL 干净\n    window.addEventListener('hashchange', applyHash);\n  }\n  if (document.readyState === 'loading') {\n    document.addEventListener('DOMContentLoaded', init);\n  } else { init(); }\n})();\n"
LINE_DEEPLINK_JS = '\n(function(){\n  function hl(){\n    var rows = document.querySelectorAll(\'tr.code-row[id^="L"]\');\n    for (var i = 0; i < rows.length; i++) { rows[i].classList.remove(\'ln-hl\'); }\n    var h = (location.hash || \'\').replace(/^#/, \'\');\n    var m = /^L(\\d+)(?:-(\\d+))?$/.exec(h);\n    if (!m) { return; }\n    var a = parseInt(m[1], 10), b = m[2] ? parseInt(m[2], 10) : a;\n    if (b < a) { var t = a; a = b; b = t; }\n    var first = null;\n    for (var n = a; n <= b; n++) {\n      var el = document.getElementById(\'L\' + n);\n      if (el) { el.classList.add(\'ln-hl\'); if (!first) { first = el; } }\n    }\n    if (first && first.getBoundingClientRect) {\n      // P271 R2：尊重「减少动效」偏好（CSS 的 scroll-behavior 覆盖不了 JS 的\n      // behavior 选项，必须在 JS 里也判断一次）。\n      var reduce = false;\n      try {\n        reduce = !!(window.matchMedia &&\n          window.matchMedia(\'(prefers-reduced-motion: reduce)\').matches);\n      } catch (e) {}\n      // 顶部留白，避免被固定 header 遮挡\n      var y = first.getBoundingClientRect().top + window.scrollY - 70;\n      try {\n        window.scrollTo({ top: y, behavior: reduce ? \'auto\' : \'smooth\' });\n      } catch (e) {\n        try { window.scrollTo(0, y); } catch (_) {}\n      }\n    }\n  }\n  function notify(ok, msg){\n    if (window.__toast) { window.__toast(msg, ok ? \'ok\' : \'err\'); }\n  }\n  function copyLine(i){\n    var base = location.href.split(\'#\')[0];\n    var link = base + \'#L\' + i;\n    function fallback(){\n      try {\n        var ta = document.createElement(\'textarea\');\n        ta.value = link; document.body.appendChild(ta); ta.select();\n        var okc = document.execCommand(\'copy\');\n        document.body.removeChild(ta);\n        notify(okc, okc ? (\'已复制第 \' + i + \' 行链接\') : \'复制失败，请手动复制\');\n      } catch (e) {\n        notify(false, \'复制失败，请手动复制\');\n      }\n    }\n    if (navigator.clipboard && navigator.clipboard.writeText) {\n      navigator.clipboard.writeText(link).then(\n        function(){ notify(true, \'已复制第 \' + i + \' 行链接\'); },\n        fallback);\n    } else { fallback(); }\n  }\n  document.addEventListener(\'click\', function (ev) {\n    var t = ev.target;\n    while (t && t !== document.body) {\n      if (t.classList && t.classList.contains(\'ln\') && t.getAttribute(\'data-ln\')) {\n        ev.preventDefault();\n        copyLine(t.getAttribute(\'data-ln\'));\n        return;\n      }\n      t = t.parentNode;\n    }\n  });\n  window.__copyLineLink = copyLine;\n  if (document.readyState === \'loading\') {\n    document.addEventListener(\'DOMContentLoaded\', hl);\n  } else { hl(); }\n  window.addEventListener(\'hashchange\', hl);\n})();\n'
WORKBENCH_JS = '\n(function () {\n  var K_ANNO="pony.anno", K_FAV="pony.fav", K_REC="pony.recent";\n  function get(k){ try{return JSON.parse(localStorage.getItem(k)||"{}");}catch(_){return {};} }\n  function set(k,v){ try{localStorage.setItem(k,JSON.stringify(v));}catch(_){} }\n  function key(){ return location.pathname + (location.hash||""); }\n  function safe(s){ return (s||"").replace(/[<>&]/g,function(c){return {"<":"&lt;",">":"&gt;","&":"&amp;"}[c];}); }\n  function recView(){\n    var r=get(K_REC); r[key()]=new Date().toLocaleString();\n    // 仅保留最近 12 个\n    var keys=Object.keys(r); if(keys.length>12){ delete r[keys[0]]; }\n    set(K_REC,r);\n  }\n  function renderPanel(){\n    var p=document.getElementById("wb-panel"); if(!p) return;\n    var anno=get(K_ANNO), fav=get(K_FAV), rec=get(K_REC);\n    var h=\'<div class="wb-sec"><h4>📌 标注</h4>\';\n    var ak=Object.keys(anno);\n    h+= ak.length? \'<ul class="wb-list">\'+\n       ak.map(function(k){return \'<li><a href="\'+safe(k)+\'">\'+safe(k.split("/").pop())+\'</a>\'+\n       \'<button data-del="anno" data-k="\'+safe(k)+\'">✕</button></li>\';}).join("")+\'</ul>\'\n       : \'<p class="wb-empty">在源码行号上右键/长按可标注</p>\';\n    h+=\'</div><div class="wb-sec"><h4>⭐ 收藏</h4>\';\n    var fk=Object.keys(fav);\n    h+= fk.length? \'<ul class="wb-list">\'+\n       fk.map(function(k){return \'<li><a href="\'+safe(k)+\'">\'+safe(k.split("/").pop())+\'</a>\'+\n       \'<button data-del="fav" data-k="\'+safe(k)+\'">✕</button></li>\';}).join("")+\'</ul>\'\n       : \'<p class="wb-empty">点击页面「收藏」按钮加入</p>\';\n    h+=\'</div><div class="wb-sec"><h4>🕘 最近视图</h4>\';\n    var rk=Object.keys(rec).slice(-8).reverse();\n    h+= rk.length? \'<ul class="wb-list">\'+\n       rk.map(function(k){return \'<li><a href="\'+safe(k)+\'">\'+safe(k.split("/").pop())+\'</a>\'+\n       \'<span class="wb-time">\'+safe(rec[k])+\'</span></li>\';}).join("")+\'</ul>\'\n       : \'<p class="wb-empty">暂无</p>\';\n    h+=\'</div>\';\n    // P-rev R48/R54：探索历史区——历史条目可点击跳回，让「回溯」从数字变成可交互路径\n    var histSize = (typeof window.cgHistorySize==="function") ? window.cgHistorySize() : 0;\n    h+=\'<div class="wb-sec"><h4>\U0001f9ed 探索历史</h4>\';\n    if(histSize>0){\n      var histItems = (typeof window.cgHistoryList==="function")\n          ? window.cgHistoryList() : [];\n      h+=\'<p class="wb-empty">调用链探索 \'+histSize+\' 步 · \'\n        +\'<button class="wb-mini" id="wb-clear-hist">清空</button></p>\';\n      if(histItems.length){\n        h+=\'<ul class="wb-list">\';\n        histItems.forEach(function(it, idx){\n          h+=\'<li><button class="wb-hist-jump" data-idx="\'+idx+\'">\'\n            +safe(it.label||it.id)+\'</button>\'\n            +(idx===histSize-1?\' <span class="wb-time">当前</span>\':\'\')+\'</li>\';\n        });\n        h+=\'</ul>\';\n      }\n    } else {\n      h+=\'<p class="wb-empty">尚未开始调用链探索</p>\';\n    }\n    h+=\'</div>\';\n    p.innerHTML=h;\n    p.querySelectorAll("button[data-del]").forEach(function(b){\n      b.onclick=function(){\n        var store=b.getAttribute("data-del")==="anno"?K_ANNO:K_FAV;\n        var d=get(store); delete d[b.getAttribute("data-k")]; set(store,d); renderPanel();\n      };\n    });\n    var ch=document.getElementById("wb-clear-hist");\n    if(ch){ ch.onclick=function(){\n      if(window.cgClearPreviewHistory){ window.cgClearPreviewHistory(); }\n      renderPanel();\n    }; }\n    // P-rev R54：点击历史条目跳回对应预览（若在当前页有调用图）\n    p.querySelectorAll(".wb-hist-jump").forEach(function(btn){\n      btn.onclick=function(){\n        var idx=parseInt(btn.getAttribute("data-idx"),10);\n        if(typeof window.cgJumpHistory==="function"){ window.cgJumpHistory(idx); }\n        renderPanel();\n      };\n    });\n  }\n  function addBtn(label, onclick){\n    var b=document.createElement("button"); b.className="ug-btn wb-act"; b.textContent=label;\n    b.onclick=onclick; return b;\n  }\n  function ensurePanel(){\n    if(document.getElementById("wb-panel")) return;\n    var w=document.createElement("div"); w.id="wb-dock"; w.className="wb-dock";\n    w.innerHTML=\'<button class="wb-toggle" title="我的工作台">\U0001f9f0</button>\'+\n                \'<div class="wb-panel" id="wb-panel"></div>\';\n    // P-rev R15：面板头部加「导出/导入」协作按钮\n    var head=document.createElement("div"); head.className="wb-head";\n    head.innerHTML=\'<span class="wb-title">我的工作台</span>\';\n    var exp=document.createElement("button"); exp.className="wb-mini"; exp.textContent="导出";\n    exp.onclick=exportAll;\n    var imp=document.createElement("button"); imp.className="wb-mini"; imp.textContent="导入";\n    imp.onclick=function(){\n      var ipt=document.createElement("input"); ipt.type="file"; ipt.accept=".json,application/json";\n      ipt.onchange=function(){ if(ipt.files[0]) importAll(ipt.files[0]); }; ipt.click();\n    };\n    head.appendChild(exp); head.appendChild(imp);\n    w.querySelector(".wb-panel").appendChild(head);\n    document.body.appendChild(w);\n    var toggle=w.querySelector(".wb-toggle");\n    var panel=w.querySelector(".wb-panel");\n    toggle.onclick=function(){ panel.classList.toggle("open"); if(panel.classList.contains("open")) renderPanel(); };\n    // 浮窗内事件委托\n    panel.addEventListener("click",function(e){\n      if(e.target.matches(\'a\')) panel.classList.remove("open");\n    });\n  }\n  // P-rev R15：协作层——标注/收藏导出为 JSON（团队共享），导入时合并。\n  function exportAll(){\n    var data={ v:1, anno:get(K_ANNO), fav:get(K_FAV), recent:get(K_REC) };\n    var blob=new Blob([JSON.stringify(data,null,2)], {type:"application/json"});\n    var a=document.createElement("a");\n    a.href=URL.createObjectURL(blob); a.download="workbench.json"; a.click();\n    setTimeout(function(){ URL.revokeObjectURL(a.href); }, 1000);\n  }\n  // P-rev R24：冲突可视化解决——逐条展示「本地 vs 导入」取值，由用户决定保留哪一方，\n  // 而不是一刀切保留本地。选择后即时写回对应 store 并重绘面板。\n  function openConflictModal(conflicts, summary){\n    var ovl=document.createElement("div");\n    ovl.className="wb-cf-ovl"; ovl.setAttribute("role","dialog");\n    ovl.innerHTML=\'<div class="wb-cf-box"><h3>⚠ 导入冲突解决</h3>\'\n      +\'<p class="wb-cf-sum">\'+ (summary||"") +\' · 共 \'+conflicts.length+\' 处冲突</p>\'\n      +\'<div class="wb-cf-list"></div>\'\n      +\'<div class="wb-cf-foot"><button class="wb-mini" data-all="local">全部保留本地</button>\'\n      +\'<button class="wb-mini" data-all="inc">全部采用导入</button>\'\n      +\'<button class="wb-mini wb-cf-ok">完成</button></div></div>\';\n    var list=ovl.querySelector(".wb-cf-list");\n    conflicts.forEach(function(c, idx){\n      var row=document.createElement("div");\n      row.className="wb-cf-row";\n      row.innerHTML=\'<div class="wb-cf-key">\'+safe(c.k)+\'</div>\'\n        +\'<div class="wb-cf-vals"><span class="wb-cf-v">本地：\'+safe(String(c.local))+\'</span>\'\n        +\'<span class="wb-cf-v">导入：\'+safe(String(c.inc))+\'</span></div>\';\n      var btns=document.createElement("div");\n      btns.className="wb-cf-btns";\n      var b1=document.createElement("button"); b1.className="wb-mini"; b1.textContent="保留本地";\n      var b2=document.createElement("button"); b2.className="wb-mini"; b2.textContent="采用导入";\n      // P-rev R31：三向合并——多人标注常常是**互补**而非矛盾（如不同人标注了不同关注点），\n      // 一刀切二选一会丢信息。这里提供「都保留」，把双方取值合并成数组一并存下。\n      var b3=document.createElement("button"); b3.className="wb-mini"; b3.textContent="都保留";\n      function apply(val){\n        var st = (c.store==="fav") ? K_FAV : K_ANNO;\n        var s=get(st); s[c.k]=val; set(st,s);\n        b1.disabled = (val===c.local); b2.disabled = (val===c.inc);\n        b3.disabled = Array.isArray(val);\n        renderPanel();\n      }\n      b1.onclick=function(){ apply(c.local); };\n      b2.onclick=function(){ apply(c.inc); };\n      b3.onclick=function(){\n        // 去重后合并为数组，避免同一取值重复存储\n        var merged=[];\n        [c.local, c.inc].forEach(function(v){\n          if(v!==undefined && v!==null && merged.indexOf(v)<0) merged.push(v);\n        });\n        apply(merged);\n      };\n      btns.appendChild(b1); btns.appendChild(b2); btns.appendChild(b3);\n      row.appendChild(btns);\n      list.appendChild(row);\n    });\n    function batchAll(mode){\n      conflicts.forEach(function(c){\n        var st=(c.store==="fav")?K_FAV:K_ANNO; var s=get(st);\n        if(mode==="local"){ s[c.k]=c.local; }\n        else if(mode==="inc"){ s[c.k]=c.inc; }\n        else {   // P-rev R31：批量「都保留」\n          var merged=[];\n          [c.local, c.inc].forEach(function(v){\n            if(v!==undefined && v!==null && merged.indexOf(v)<0) merged.push(v);\n          });\n          s[c.k]=merged;\n        }\n        set(st,s);\n      });\n      renderPanel(); close();\n    }\n    ovl.querySelector(\'[data-all="local"]\').onclick=function(){ batchAll("local"); };\n    ovl.querySelector(\'[data-all="inc"]\').onclick=function(){ batchAll("inc"); };\n    var allMerge=document.createElement("button");\n    allMerge.className="wb-mini"; allMerge.textContent="全部都保留";\n    allMerge.onclick=function(){ batchAll("merge"); };\n    ovl.querySelector(".wb-cf-foot").insertBefore(\n      allMerge, ovl.querySelector(".wb-cf-ok"));\n    function close(){ if(ovl.parentNode) ovl.parentNode.removeChild(ovl); }\n    ovl.querySelector(".wb-cf-ok").onclick=close;\n    document.body.appendChild(ovl);\n  }\n  function importAll(file){\n    var r=new FileReader();\n    r.onload=function(){\n      try{\n        var d=JSON.parse(r.result||"{}");\n        var a=get(K_ANNO), f=get(K_FAV), rc=get(K_REC);\n        // P-rev R20：协作冲突合并——按路径规范化后去重，并识别「同一键不同值」的冲突。\n        // 多人各自标注后汇总时，若对同一处给出不同意见，需要显式提示而不是静默覆盖。\n        var added={anno:0,fav:0}, dup=0, conflict=[];\n        function npath(k){ return String(k).replace(/\\\\/g,"/").replace(/\\/{2,}/g,"/"); }\n        function merge(store, incoming, label){\n          Object.keys(incoming||{}).forEach(function(raw){\n            var k=npath(raw), v=incoming[raw];\n            if(store[k]!==undefined){\n              dup++;\n              // P-rev R24：记录冲突的**双方取值**，供 UI 逐条选择保留哪一方\n              if(store[k]!==v){ conflict.push({store:label, k:k, local:store[k], inc:v}); }\n            } else { store[k]=v; added[label]++; }\n          });\n        }\n        merge(a, d.anno, "anno");\n        merge(f, d.fav, "fav");\n        Object.keys(d.recent||{}).forEach(function(raw){\n          var k=npath(raw);\n          if(rc[k]===undefined){ rc[k]=d.recent[raw]; }\n        });\n        set(K_ANNO,a); set(K_FAV,f); set(K_REC,rc);\n        renderPanel();\n        var summary="导入完成：新增标注 "+added.anno+" 项、收藏 "+added.fav+" 项"\n                    + (dup>0 ? ("；已存在（去重）"+dup+" 项") : "");\n        // P-rev R24：冲突不再只用 alert 罗列，而是给出可逐条选择的解决面板\n        if(conflict.length>0){ openConflictModal(conflict, summary); }\n        else { alert(summary); }\n      }catch(_){ alert("导入失败：不是有效的 workbench.json"); }\n    };\n    r.readAsText(file);\n  }\n  // 暴露全局，供源码页「标注本行 / 收藏本页」按钮调用\n  window.WB = {\n    annotate:function(target){ var a=get(K_ANNO); a[target||key()]="1"; set(K_ANNO,a); },\n    favor:function(target){ var f=get(K_FAV); f[target||key()]="1"; set(K_FAV,f); },\n    render:renderPanel, ensure:ensurePanel, recent:recView,\n    exportAll:exportAll, importAll:importAll\n  };\n  document.addEventListener("DOMContentLoaded", function(){\n    ensurePanel(); recView();\n  });\n})();\n'
SYMBOLS_JS = '\n(function(){\n  var _cache = null;\n  function norm(s){ return (s||"").trim().toLowerCase(); }\n  function relOf(pathname){\n    return (pathname.split("/").pop()||"").replace(/\\.html$/,"");\n  }\n  function annotate(syms){\n    // 优先只处理本文件相关符号，避免同名函数跨文件误标\n    var here = relOf(location.pathname);\n    var local = [], all = [];\n    for(var i=0;i<syms.length;i++){\n      var s=syms[i]; if(!s||!s.id) continue;\n      var r=(s.rel||"").replace(/\\\\/g,"/").replace(/\\.m$/,"").split("/").pop();\n      if(r===here) local.push(s); else all.push(s);\n    }\n    var pool = local.concat(all);\n    document.querySelectorAll("code,a,span,td,li").forEach(function(el){\n      if(el.hasAttribute("data-sym")) return;          // 已有精确标识，不覆盖\n      if(el.children.length>0) return;                  // 只处理纯文本节点\n      var t=norm(el.textContent);\n      if(!t || t.length>60) return;\n      for(var i=0;i<pool.length;i++){\n        if(norm(pool[i].name)===t){\n          el.setAttribute("data-sym", pool[i].id);\n          el.setAttribute("title", (el.getAttribute("title")||"") +\n            " · 扇入 "+pool[i].fan_in+" · 波及 "+pool[i].impact+" 处");\n          break;\n        }\n      }\n    });\n  }\n  // 老环境（含审计用的 jsdom）没有 fetch，必须能力探测后降级，否则抛 ReferenceError\n  function canFetch(){ return typeof fetch === "function"; }\n  function load(){\n    if(_cache){ annotate(_cache); return; }\n    if(!canFetch()){ _cache=[]; return; }\n    var url=(window.__CG_SITE_REL__||"")+"symbols.json";\n    fetch(url).then(function(r){ return r.json(); })\n      .then(function(j){ _cache=j.symbols||[]; annotate(_cache); })\n      .catch(function(){ _cache=[]; });\n  }\n  window.WB = window.WB || {};\n  window.WB.reloadSymbols = function(){ _cache=null; load(); };\n  document.addEventListener("DOMContentLoaded", load);\n})();\n'
EDITLOOP_JS = '\n(function () {\n  var SKEY = "pony.edit." + location.pathname;\n  function norm(s){ return (s||"").replace(/\\s+$/,""); }\n  // P-rev R32：data-orig 存的是 HTML 转义后的原始文本；取回时需反转义，\n  // 才能与 textContent（纯文本）正确比较，否则含 <>& 的行永远判为「已改动」。\n  function decode(s){\n    var d=document.createElement("textarea"); d.innerHTML=(s||""); return d.value;\n  }\n  function origText(td){ return decode(td.getAttribute("data-orig")); }\n  function load(){ try { return JSON.parse(localStorage.getItem(SKEY)||"{}"); } catch(_){ return {}; } }\n  function save(d){ try { localStorage.setItem(SKEY, JSON.stringify(d)); } catch(_){} }\n  function badge(){\n    var b = document.getElementById("edit-badge");\n    if(!b){ b=document.createElement("span"); b.id="edit-badge";\n      b.className="edit-badge"; document.querySelector("header").appendChild(b); }\n    return b;\n  }\n  function diag(line){\n    var msgs=[];\n    var t=norm(line);\n    if(t.match(/\\bif\\b|\\bfor\\b|\\bwhile\\b|\\bswitch\\b|\\btry\\b|\\bfunction\\b/)\n       && !/end\\b\\s*$|^\\s*%/) {} // 仅作提示，不强制\n    var opens=(line.match(/\\bif\\b|\\bfor\\b|\\bwhile\\b|\\bswitch\\b|\\btry\\b|\\bfunction\\b|\\bclassdef\\b/g)||[]).length;\n    var ends=(line.match(/\\bend\\b/g)||[]).length;\n    if(opens>ends && /\\b(if|for|while|switch|try|function|classdef)\\b/.test(t) && !/\\bend\\b/.test(t))\n      msgs.push("⚠ 该行以控制结构开头但未见 end（建议核对闭合）");\n    if(/\\bTODO\\b|\\bFIXME\\b/i.test(t)) msgs.push("📌 含 TODO/FIXME 标记");\n    if(t.trim()==="") msgs.push("");\n    return msgs.filter(Boolean);\n  }\n  function refresh(){\n    var d=load(); var n=Object.keys(d).length;\n    var b=badge();\n    if(n>0){ b.textContent="✎ 草稿 "+n+" 行 · 已自动保存"; b.style.display=""; }\n    else { b.style.display="none"; }\n  }\n  // P-rev R12：对「当前（可能已编辑）文件」做客户端增量重算——end 闭合计数、\n  // 相对原始的行数差、以及基于控制结构的圈复杂度估算，给出「改完即时反馈」。\n  function recheck(){\n    var d=load();\n    var lines=[];\n    document.querySelectorAll(".code-edit[data-ln]").forEach(function(td){\n      var ln=td.getAttribute("data-ln");\n      var v = d[ln]!==undefined ? d[ln] : origText(td);\n      lines.push(v||"");\n    });\n    var endOpen=0, unclosed=0, cc=1;\n    for(var i=0;i<lines.length;i++){\n      var s=lines[i];\n      if(/^\\s*%/.test(s)) continue;           // 注释行跳过\n      var opens=(s.match(/\\b(if|for|while|switch|try|function|classdef|methods|properties|events|enumeration)\\b/g)||[]).length;\n      var ends=(s.match(/\\bend\\b/g)||[]).length;\n      endOpen += opens - ends;\n      // 圈复杂度：每个决策点 +1\n      cc += (s.match(/\\b(if|for|while|switch|catch|elseif|case)\\b/g)||[]).length;\n    }\n    if(endOpen>0) unclosed=endOpen;\n    var origCount=document.querySelectorAll(".code-edit[data-ln]").length;\n    var diff=lines.length-origCount;\n    var msg="⟳ 重算：复杂度≈"+cc;\n    if(diff!==0) msg+=" · 行数"+(diff>0?"+":"")+diff;\n    if(unclosed>0) msg+=" · ⚠ 未闭合 end×"+unclosed;\n    var b=badge();\n    b.textContent=msg; b.style.display="";\n    b.style.background = unclosed>0 ? "#fdeaea" : "#eaf6ee";\n    b.style.color = unclosed>0 ? "#cf222e" : "#1a7f37";\n    b.style.borderColor = unclosed>0 ? "#f5b5b5" : "#a7e0b8";\n    // P-rev R18：真·语义回算——额外读取统一符号层 symbols.json，补上「真实」扇入\n    // 与传递影响面，让重算结果既有客户端即时量度、又有服务端权威语义数据。\n    augmentWithSymbols(msg, unclosed>0);\n  }\n  var _symCache=null;\n  function augmentWithSymbols(baseMsg, bad){\n    if(_symCache){ renderSymbolInfo(baseMsg, _symCache, bad); return; }\n    if(typeof fetch!=="function"){ _symCache=[]; return; }  // 老环境降级\n    var rel = (location.pathname.split("/").pop()||"").replace(/\\.html$/,"");\n    var url = (window.__CG_SITE_REL__||"") + "symbols.json";\n    fetch(url).then(function(r){ return r.json(); })\n      .then(function(j){ _symCache=j.symbols||[]; renderSymbolInfo(baseMsg,_symCache,bad); })\n      .catch(function(){ /* 符号层不可用则只显示客户端量度 */ });\n  }\n  function renderSymbolInfo(baseMsg, syms, bad){\n    // 取本文件里「传递影响面」最大的函数作为该文件的代表风险\n    var rel = (location.pathname.split("/").pop()||"").replace(/\\.html$/,"");\n    var best=null;\n    for(var i=0;i<syms.length;i++){\n      var s=syms[i];\n      if(!s || typeof s.rel!=="string") continue;\n      if(s.rel.replace(/\\\\/g,"/").split("/").pop().replace(/\\.m$/,"")!==rel) continue;\n      if(!best || (s.impact||0)>(best.impact||0)) best=s;\n    }\n    var b=badge();\n    if(best){\n      b.textContent = baseMsg + " · 权威："+best.name+" 扇入"+best.fan_in+" 波及"+best.impact+"处";\n    } else {\n      b.textContent = baseMsg;\n    }\n    b.style.display="";\n    b.style.background = bad ? "#fdeaea" : "#eaf6ee";\n    b.style.color = bad ? "#cf222e" : "#1a7f37";\n    b.style.borderColor = bad ? "#f5b5b5" : "#a7e0b8";\n  }\n  function applyEdits(){\n    var d=load();\n    document.querySelectorAll(".code-edit[data-ln]").forEach(function(td){\n      var ln=td.getAttribute("data-ln"); var v=d[ln];\n      if(v!==undefined && td.getAttribute("contenteditable")==="true"){\n        if(document.activeElement!==td) td.textContent=v;\n      }\n    });\n  }\n  document.addEventListener("DOMContentLoaded", function(){\n    if(!document.querySelector(".code-edit[data-ln]")) return;\n    var d=load();\n    document.querySelectorAll(".code-edit[data-ln]").forEach(function(td){\n      td.setAttribute("contenteditable","true");\n      td.setAttribute("spellcheck","false");\n      var ln=td.getAttribute("data-ln");\n      if(d[ln]!==undefined){\n        td.textContent=d[ln];\n      }\n      td.addEventListener("input", function(){\n        var cur=load();\n        var orig = origText(td);\n        if(td.textContent===orig){ delete cur[ln]; }\n        else { cur[ln]=td.textContent; }\n        save(cur); recheck();\n      });\n    });\n    // 工具条：重置全部 + 导出草稿 + 改动高亮\n    var head=document.querySelector("header");\n    if(head){\n      var btn=document.createElement("button");\n      btn.className="ug-btn"; btn.textContent="↺ 重置编辑草稿";\n      btn.onclick=function(){\n        if(!confirm("确认丢弃本文件所有编辑草稿？")) return;\n        try{ localStorage.removeItem(SKEY); }catch(_){}\n        location.reload();\n      };\n      head.appendChild(btn);\n      // P-rev R11：导出草稿为 .m（应用行级改动），便于回 analyzer 重新生成/分享。\n      var exp=document.createElement("button");\n      exp.className="ug-btn"; exp.textContent="⬇ 导出草稿.m";\n      exp.onclick=function(){\n        var d=load();\n        var lines=[];\n        document.querySelectorAll(".code-edit[data-ln]").forEach(function(td){\n          var ln=td.getAttribute("data-ln");\n          lines.push(d[ln]!==undefined ? d[ln] : origText(td));\n        });\n        var name=(location.pathname.split("/").pop()||"edited").replace(".html",".m");\n        var blob=new Blob([lines.join("\\n")], {type:"text/plain;charset=utf-8"});\n        var a=document.createElement("a");\n        a.href=URL.createObjectURL(blob); a.download=name; a.click();\n        setTimeout(function(){ URL.revokeObjectURL(a.href); }, 1000);\n        // P-rev R29：符号层增量更新提示。symbols.json 是**生成期**产物，编辑只会改\n        // 本页草稿，不会自动刷新它；若不提示，用户会误以为「波及 N 处」已随编辑更新。\n        alert("已导出 " + name + "。\\n\\n"\n            + "提示：本页编辑只保存在浏览器草稿里，符号层（symbols.json，含扇入/波及/依赖）"\n            + "是生成期产物，需重新运行分析器才会更新：\\n"\n            + "    python matlabc.py <源目录> --browse <输出目录>");\n      };\n      head.appendChild(exp);\n      // P-rev R11：显示/隐藏改动行高亮，直观看到「我改了哪些行」。\n      var diff=document.createElement("button");\n      diff.className="ug-btn"; diff.textContent="👁 显示改动";\n      diff.onclick=function(){\n        var on=document.body.classList.toggle("show-draft-diff");\n        diff.textContent=on?"👁 隐藏改动":"👁 显示改动";\n        document.querySelectorAll(".code-edit[data-ln]").forEach(function(td){\n          var ln=td.getAttribute("data-ln"); var v=load()[ln];\n          if(v!==undefined && v!==origText(td)){ td.classList.add("edit-dirty"); }\n          else { td.classList.remove("edit-dirty"); }\n        });\n      };\n      head.appendChild(diff);\n      // P-rev R12：对当前（含草稿）文件做客户端增量重算，即时反馈复杂度/未闭合。\n      var rc=document.createElement("button");\n      rc.className="ug-btn"; rc.textContent="⟳ 重新分析";\n      rc.setAttribute("aria-label","对当前编辑内容做客户端重算");\n      rc.onclick=function(){ recheck(); };\n      head.appendChild(rc);\n    }\n    recheck();\n  });\n})();\n'
LAZY_SEARCH_JS = "\n(function () {\n  'use strict';\n  if (window.__GS_LOADED__) return;\n  var injected = false;\n  function inject() {\n    if (injected) return;\n    injected = true;\n    var s = document.createElement('script');\n    s.src = (window.__CG_SITE_REL__ || '') + '_search.js';\n    s.async = false;\n    // 注入完成后，模拟一次 Ctrl+K 打开面板，用户无感衔接\n    s.onload = function () {\n      if (window.__GS_OPEN__) { window.__GS_OPEN__(); }\n    };\n    document.head.appendChild(s);\n  }\n  function onKey(ev) {\n    var t = ev.target;\n    var typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA'\n                       || t.isContentEditable);\n    if ((ev.ctrlKey || ev.metaKey) && String(ev.key).toLowerCase() === 'k') {\n      if (typing) return;\n      ev.preventDefault();\n      inject();\n      return;\n    }\n    if (ev.key === '/' && !typing) {\n      ev.preventDefault();\n      inject();\n    }\n  }\n  // 首次滚动/交互也触发（scrollspy 与其它键盘导航依赖 _search.js 的能力）\n  function onFirstInteract() {\n    inject();\n    document.removeEventListener('scroll', onFirstInteract);\n    document.removeEventListener('mousemove', onFirstInteract);\n    document.removeEventListener('keydown', onKey);\n  }\n  document.addEventListener('keydown', onKey);\n  document.addEventListener('scroll', onFirstInteract, { passive: true });\n  // P-rev R35：搜索按钮（#nav-search）点击时也触发懒加载，随后由完整模块接管打开\n  document.addEventListener('click', function (ev) {\n    var t = ev.target;\n    while (t && t !== document.body) {\n      if (t.id === 'nav-search') { ev.preventDefault(); inject(); return; }\n      t = t.parentNode;\n    }\n  });\n  // 暴露：搜索按钮/其它入口可主动触发\n  window.__GS_LAZY_LOAD__ = inject;\n})();\n"
GRAPH_JS = '\n(function(){\n  var svg = document.getElementById(\'cg-svg\');\n  if(!svg || typeof CG_DATA === \'undefined\'){ return; }\n  var g = document.getElementById(\'cg-g\');\n  var tip = document.getElementById(\'cg-tip\');\n  var SVGNS = \'http://www.w3.org/2000/svg\';\n  var data = CG_DATA;\n  var nodes = data.nodes, edges = data.edges;\n  var maxIn = Math.max(1, data.maxIn || 1);\n  var N = nodes.length, M = edges.length;\n  var i, j;\n  function sizeOf(nd){ return 4 + Math.sqrt(nd.inDeg) * 3.0; }\n  function colorOf(nd){\n    var t = Math.min(1, nd.inDeg / maxIn);\n    var r = Math.round(60 + t * 180);\n    var gg = Math.round(180 - t * 150);\n    var b = Math.round(70 - t * 40);\n    return \'rgb(\' + r + \',\' + gg + \',\' + b + \')\';\n  }\n  var labelThr = Math.max(2, Math.ceil(maxIn * 0.25));\n  // 初始环形布局\n  for(i = 0; i < N; i++){\n    var ang = 2 * Math.PI * i / Math.max(N, 1);\n    var rad = 60 + Math.sqrt(N) * 14;\n    nodes[i].x = 450 + rad * Math.cos(ang);\n    nodes[i].y = 320 + rad * Math.sin(ang);\n    nodes[i].vx = 0; nodes[i].vy = 0; nodes[i].fixed = false;\n  }\n  // 邻接表（用于悬停高亮）\n  var adj = {};\n  for(i = 0; i < M; i++){\n    var e = edges[i];\n    (adj[e[0]] = adj[e[0]] || []).push(e[1]);\n    (adj[e[1]] = adj[e[1]] || []).push(e[0]);\n  }\n  // 构建 DOM\n  var edgeEls = [], nodeEls = [], labelEls = [];\n  for(i = 0; i < M; i++){\n    var ln = document.createElementNS(SVGNS, \'line\');\n    ln.setAttribute(\'stroke\', \'#bbb\');\n    ln.setAttribute(\'stroke-width\', \'1\');\n    g.appendChild(ln); edgeEls.push(ln);\n  }\n  for(i = 0; i < N; i++){\n    var nd = nodes[i];\n    var c = document.createElementNS(SVGNS, \'circle\');\n    c.setAttribute(\'r\', sizeOf(nd));\n    c.setAttribute(\'fill\', colorOf(nd));\n    c.setAttribute(\'stroke\', \'#444\');\n    c.setAttribute(\'stroke-width\', \'0.5\');\n    c.style.cursor = \'pointer\';\n    c.addEventListener(\'mouseenter\', (function(idx){ return function(ev){ onHover(idx, ev); }; })(i));\n    c.addEventListener(\'mousemove\', function(ev){ moveTip(ev); });\n    c.addEventListener(\'mouseleave\', function(){ onLeave(); });\n    c.addEventListener(\'mousedown\', (function(idx){ return function(ev){ startNodeDrag(idx, ev); }; })(i));\n    c.addEventListener(\'dblclick\', (function(idx){ return function(ev){ nodes[idx].fixed = false; ev.stopPropagation(); }; })(i));\n    c.addEventListener(\'click\', (function(idx){ return function(ev){ onNodeClick(idx, ev); }; })(i));\n    g.appendChild(c); nodeEls.push(c);\n    var t = document.createElementNS(SVGNS, \'text\');\n    t.setAttribute(\'font-size\', \'9\');\n    t.setAttribute(\'fill\', \'#222\');\n    t.setAttribute(\'text-anchor\', \'middle\');\n    t.textContent = nd.name;\n    t.style.pointerEvents = \'none\';\n    t.style.display = (nd.inDeg >= labelThr) ? \'\' : \'none\';\n    g.appendChild(t); labelEls.push(t);\n  }\n  function onHover(idx, ev){\n    var nb = adj[idx] || [];\n    var set = {}; set[idx] = 1;\n    for(var k = 0; k < nb.length; k++){ set[nb[k]] = 1; }\n    for(var q = 0; q < N; q++){\n      nodeEls[q].setAttribute(\'opacity\', set[q] ? \'1\' : \'0.15\');\n    }\n    for(var q2 = 0; q2 < M; q2++){\n      var e2 = edges[q2];\n      var on = (e2[0] === idx || e2[1] === idx);\n      edgeEls[q2].setAttribute(\'stroke\', on ? \'#d73a49\' : \'#eee\');\n      edgeEls[q2].setAttribute(\'stroke-width\', on ? \'2\' : \'1\');\n      edgeEls[q2].setAttribute(\'opacity\', on ? \'1\' : \'0.15\');\n    }\n    var nd = nodes[idx];\n    // P18：悬停提示同时展示函数简要说明\n    var _dline = nd.d ? (\'<br><span style="color:#57606a">\' + nd.d + \'</span>\') : \'\';\n    tip.innerHTML = \'<b>\' + nd.name + \'</b><br>\' + nd.file + \' : L\' + nd.line +\n      \'<br>类型 \' + nd.kind + \' · 复杂度 \' + nd.cx +\n      \'<br>被调用 \' + nd.inDeg + \' · 调用 \' + nd.outDeg + _dline;\n    tip.style.display = \'block\';\n    moveTip(ev);\n  }\n  function onLeave(){\n    for(var q = 0; q < N; q++){ nodeEls[q].setAttribute(\'opacity\', \'1\'); }\n    for(var q2 = 0; q2 < M; q2++){\n      edgeEls[q2].setAttribute(\'stroke\', \'#bbb\');\n      edgeEls[q2].setAttribute(\'stroke-width\', \'1\');\n      edgeEls[q2].setAttribute(\'opacity\', \'1\');\n    }\n    tip.style.display = \'none\';\n  }\n  function moveTip(ev){\n    tip.style.left = (ev.clientX + 14) + \'px\';\n    tip.style.top = (ev.clientY + 14) + \'px\';\n  }\n  // 视图变换（平移 / 缩放）——与 P83 局部图一致的 UX（缩放条 + 百分比 + 复位）\n  var view = { x: 0, y: 0, k: 1 };\n  function applyView(){\n    g.setAttribute(\'transform\', \'translate(\' + view.x + \',\' + view.y + \') scale(\' + view.k + \')\');\n    var pct = document.getElementById(\'cg-zoom-pct\');\n    if(pct){ pct.textContent = Math.round(view.k * 100) + \'%\'; }\n  }\n  function cgZoomBy(factor){\n    var rect = svg.getBoundingClientRect();\n    var sx = rect.width / 2, sy = rect.height / 2;   // 以视图中心为锚点\n    var k2 = view.k * factor;\n    if(k2 < 0.1 || k2 > 8){ return; }\n    view.x = sx - (sx - view.x) * (k2 / view.k);\n    view.y = sy - (sy - view.y) * (k2 / view.k);\n    view.k = k2; applyView();\n  }\n  function cgResetView(){ view.x = 0; view.y = 0; view.k = 1; applyView(); }\n  var _zin = document.getElementById(\'cg-zin\');\n  var _zout = document.getElementById(\'cg-zout\');\n  var _zreset = document.getElementById(\'cg-zreset\');\n  if(_zin){ _zin.addEventListener(\'click\', function(){ cgZoomBy(1.2); }); }\n  if(_zout){ _zout.addEventListener(\'click\', function(){ cgZoomBy(0.83); }); }\n  if(_zreset){ _zreset.addEventListener(\'click\', cgResetView); }\n  // 键盘缩放：聚焦在图区域时可用 +/-/= 缩放、0 复位\n  svg.addEventListener(\'keydown\', function(ev){\n    if(ev.key === \'+\' || ev.key === \'=\'){ cgZoomBy(1.2); ev.preventDefault(); }\n    else if(ev.key === \'-\' || ev.key === \'_\'){ cgZoomBy(0.83); ev.preventDefault(); }\n    else if(ev.key === \'0\'){ cgResetView(); ev.preventDefault(); }\n  });\n  if(document.getElementById(\'cg-svg\')){ document.getElementById(\'cg-svg\').setAttribute(\'tabindex\', \'0\'); }\n  svg.addEventListener(\'wheel\', function(ev){\n    ev.preventDefault();\n    var rect = svg.getBoundingClientRect();\n    var sx = ev.clientX - rect.left, sy = ev.clientY - rect.top;\n    var factor = ev.deltaY < 0 ? 1.12 : 0.89;\n    var k2 = view.k * factor;\n    if(k2 < 0.1 || k2 > 8){ return; }\n    view.x = sx - (sx - view.x) * (k2 / view.k);\n    view.y = sy - (sy - view.y) * (k2 / view.k);\n    view.k = k2; applyView();\n  }, { passive: false });\n  var panning = false, panSX = 0, panSY = 0, panVX = 0, panVY = 0;\n  var dragNode = -1, dragMoved = false;\n  svg.addEventListener(\'mousedown\', function(ev){\n    if(ev.target !== svg && ev.target !== g){ return; }\n    panning = true; panSX = ev.clientX; panSY = ev.clientY;\n    panVX = view.x; panVY = view.y;\n  });\n  function startNodeDrag(idx, ev){\n    ev.stopPropagation();\n    dragNode = idx; dragMoved = false;\n    nodes[idx].fixed = true;\n  }\n  window.addEventListener(\'mousemove\', function(ev){\n    if(panning){\n      view.x = panVX + (ev.clientX - panSX);\n      view.y = panVY + (ev.clientY - panSY);\n      applyView();\n    }\n    if(dragNode >= 0){\n      dragMoved = true;\n      var rect = svg.getBoundingClientRect();\n      var gx = (ev.clientX - rect.left - view.x) / view.k;\n      var gy = (ev.clientY - rect.top - view.y) / view.k;\n      nodes[dragNode].x = gx; nodes[dragNode].y = gy;\n      render();\n    }\n  });\n  window.addEventListener(\'mouseup\', function(){\n    panning = false;\n    if(dragNode >= 0){ /* 保持固定，双击可解除 */ }\n    dragNode = -1;\n  });\n  function onNodeClick(idx, ev){\n    ev.stopPropagation();\n    if(dragMoved){ return; }   // 拖动后不触发跳转\n    window.open(nodes[idx].href, \'_blank\');\n  }\n  // 力导向布局\n  var alpha = 1.0;\n  function tick(){\n    var REP = 9000, REST = 70, SPRING = 0.02, GRAV = 0.006, DAMP = 0.86;\n    var MIN_DIST = 22;   // P18：节点最小间距（防重叠），略大于 2*半径，避免彼此覆盖\n    for(i = 0; i < N; i++){\n      for(j = i + 1; j < N; j++){\n        var a = nodes[i], b = nodes[j];\n        var dx = a.x - b.x, dy = a.y - b.y;\n        var d2 = dx * dx + dy * dy + 0.01;\n        var d = Math.sqrt(d2);\n        var f = REP / d2;\n        var fx = f * dx / d, fy = f * dy / d;\n        a.vx += fx; a.vy += fy;\n        b.vx -= fx; b.vy -= fy;\n        // P18：最小间距硬约束（碰撞分离）——当两节点中心过近时直接沿连线方向各推开一半，\n        // 彻底消除「全局调用图节点互相覆盖、挡住别的函数的调用」的问题。\n        if(d < MIN_DIST){\n          var push = (MIN_DIST - d) * 0.5;\n          var ux = dx / d, uy = dy / d;\n          a.x -= ux * push; a.y -= uy * push;\n          b.x += ux * push; b.y += uy * push;\n        }\n      }\n    }\n    for(i = 0; i < M; i++){\n      var e3 = edges[i];\n      var s = nodes[e3[0]], tt = nodes[e3[1]];\n      var dx2 = tt.x - s.x, dy2 = tt.y - s.y;\n      var d3 = Math.sqrt(dx2 * dx2 + dy2 * dy2) + 0.01;\n      var f2 = (d3 - REST) * SPRING;\n      var fx2 = f2 * dx2 / d3, fy2 = f2 * dy2 / d3;\n      s.vx += fx2; s.vy += fy2;\n      tt.vx -= fx2; tt.vy -= fy2;\n    }\n    var cx = 450, cy = 320;\n    for(i = 0; i < N; i++){\n      var p = nodes[i];\n      p.vx += (cx - p.x) * GRAV;\n      p.vy += (cy - p.y) * GRAV;\n    }\n    for(i = 0; i < N; i++){\n      var pp = nodes[i];\n      if(pp.fixed){ pp.vx = 0; pp.vy = 0; continue; }\n      pp.x += pp.vx * alpha;\n      pp.y += pp.vy * alpha;\n      pp.vx *= DAMP; pp.vy *= DAMP;\n    }\n    alpha *= 0.985;\n  }\n  function render(){\n    for(i = 0; i < M; i++){\n      var ee = edges[i], s = nodes[ee[0]], t = nodes[ee[1]];\n      var ln = edgeEls[i];\n      ln.setAttribute(\'x1\', s.x); ln.setAttribute(\'y1\', s.y);\n      ln.setAttribute(\'x2\', t.x); ln.setAttribute(\'y2\', t.y);\n    }\n    for(i = 0; i < N; i++){\n      var c = nodeEls[i], p = nodes[i];\n      c.setAttribute(\'cx\', p.x); c.setAttribute(\'cy\', p.y);\n      var t2 = labelEls[i];\n      t2.setAttribute(\'x\', p.x);\n      t2.setAttribute(\'y\', p.y - sizeOf(p) - 2);\n    }\n  }\n  var ticksPerFrame = 3, total = 260, frame = 0;\n  if(N > 600){ ticksPerFrame = 2; total = 200; }\n  if(N > 1000){ ticksPerFrame = 1; total = 160; }\n  function loop(){\n    if(frame < total){\n      for(var kk = 0; kk < ticksPerFrame; kk++){ tick(); }\n      frame++; render();\n      requestAnimationFrame(loop);\n    } else {\n      render();\n    }\n  }\n  requestAnimationFrame(loop);\n  applyView();\n  document.getElementById(\'cg-stat\').textContent = \'节点 \' + N + \' / 边 \' + M;\n  // 过滤 / 标签开关\n  window.cgLabelsAll = false;\n  window.cgFilter = function(){\n    var v = +document.getElementById(\'cg-min\').value;\n    document.getElementById(\'cg-minv\').textContent = v;\n    for(var q = 0; q < N; q++){\n      var show = nodes[q].inDeg >= v;\n      nodeEls[q].style.display = show ? \'\' : \'none\';\n      var lbl = (show && (window.cgLabelsAll || nodes[q].inDeg >= labelThr)) ? \'\' : \'none\';\n      labelEls[q].style.display = lbl;\n    }\n    for(var q2 = 0; q2 < M; q2++){\n      var e4 = edges[q2];\n      var show2 = (nodes[e4[0]].inDeg >= v && nodes[e4[1]].inDeg >= v);\n      edgeEls[q2].style.display = show2 ? \'\' : \'none\';\n    }\n  };\n  window.cgToggleLabels = function(){\n    window.cgLabelsAll = document.getElementById(\'cg-lbl\').checked;\n    window.cgFilter();\n  };\n  window.cgRelayout = function(){\n    alpha = 1; frame = 0;\n    for(i = 0; i < N; i++){\n      var ang2 = 2 * Math.PI * i / Math.max(N, 1);\n      var rad2 = 60 + Math.sqrt(N) * 14;\n      nodes[i].x = 450 + rad2 * Math.cos(ang2);\n      nodes[i].y = 320 + rad2 * Math.sin(ang2);\n      nodes[i].vx = 0; nodes[i].vy = 0; nodes[i].fixed = false;\n    }\n    requestAnimationFrame(loop);\n  };\n  // 全局搜索联动：按函数名脉冲高亮节点并平移至视图中心\n  window.cgPulse = function(name){\n    if(!name || typeof name !== \'string\') return;\n    var idx = -1;\n    for(var q = 0; q < N; q++){ if(nodes[q].name === name){ idx = q; break; } }\n    if(idx < 0) return;\n    var nd = nodes[idx];\n    var rect = svg.getBoundingClientRect();\n    var cx2 = rect.width / 2, cy2 = rect.height / 2;\n    view.x = cx2 - nd.x * view.k;\n    view.y = cy2 - nd.y * view.k;\n    applyView();\n    var c = nodeEls[idx];\n    var origFill = c.getAttribute(\'fill\');\n    c.setAttribute(\'fill\', \'#d73a49\');\n    c.setAttribute(\'r\', (sizeOf(nd) + 4).toFixed(1));\n    if(tip) tip.style.display = \'none\';\n    if(window.cgPulseT) clearTimeout(window.cgPulseT);\n    window.cgPulseT = setTimeout(function(){\n      c.setAttribute(\'fill\', origFill);\n      c.setAttribute(\'r\', sizeOf(nd).toFixed(1));\n    }, 1600);\n  };\n})();\n'
VARFLOW_JS = '\n(function(){\n  var cur = { fn: null, param: null };\n  var info = document.getElementById(\'vf-info\');\n  function clearHl(){\n    document.querySelectorAll(\'.var\').forEach(function(el){ el.classList.remove(\'hl\'); });\n    if(info){ info.style.display = \'none\'; info.innerHTML = \'\'; }\n    cur = { fn: null, param: null };\n  }\n  function activate(fn, param){\n    clearHl();\n    var sel = \'.var[data-fn="\' + fn + \'"][data-param="\' + param + \'"]\';\n    var els = document.querySelectorAll(sel);\n    els.forEach(function(el){ el.classList.add(\'hl\'); });\n    if(info){\n      info.style.display = \'block\';\n      info.innerHTML = \'已高亮参数 <b>\' + param + \'</b>（共 \' + els.length +\n        \' 处）· 蓝=读取，橙=写入，灰=声明；再次点击该参数或空白处取消\';\n    }\n    if(els.length){ els[0].scrollIntoView({ block: \'center\' }); }\n    cur = { fn: fn, param: param };\n  }\n  function toggle(fn, param){\n    if(cur.fn === fn && cur.param === param){ clearHl(); return; }\n    activate(fn, param);\n  }\n  document.querySelectorAll(\'.param-pill\').forEach(function(p){\n    p.addEventListener(\'click\', function(ev){\n      ev.stopPropagation();\n      toggle(p.getAttribute(\'data-fn\'), p.getAttribute(\'data-param\'));\n    });\n  });\n  // 局部变量「选中即高亮」：点击源码中任意标识符，高亮同名变量的全部出现位置。\n  // 支持两种作用域：① 仅当前函数（默认，按 data-scope 限定）；② 跨整个文件\n  // （勾选「跨函数同名变量高亮」后，按变量名全局匹配），用于追踪同一变量在多个\n  // 函数间的传递。结构体字段（obj.field）按字段名高亮，即使与某局部变量同名也\n  // 互不干扰（字段用 data-field 区分，普通变量用 :not([data-field]) 排除）。\n  var identCrossFile = false;\n  var curSel = null;\n  function getIdentSel(ident, scope, isField){\n    if(identCrossFile){\n      return isField ? \'[data-field="\' + ident + \'"]\'\n                     : \'[data-ident="\' + ident + \'"]:not([data-field])\';\n    }\n    return isField\n      ? \'[data-field="\' + ident + \'"][data-scope="\' + scope + \'"]\'\n      : \'[data-ident="\' + ident + \'"][data-scope="\' + scope + \'"]:not([data-field])\';\n  }\n  function clearIdentHl(){\n    document.querySelectorAll(\'.hl-ident\').forEach(function(el){ el.classList.remove(\'hl-ident\'); });\n    curSel = null;\n  }\n  // P16-B：调用图 ↔ 源码联动所需的函数名集合（来自全局邻接表 window.__CG__.meta），\n  // 懒加载：首次点击标识符时构建，之后命中直接联动调用图节点高亮。\n  var CG_NAME_SET = null;\n  function ensureCGNameSet(){\n    if(CG_NAME_SET) return;\n    CG_NAME_SET = {};\n    if(window.__CG__ && window.__CG__.meta){\n      for(var i = 0; i < window.__CG__.meta.length; i++){\n        var nm = window.__CG__.meta[i] && window.__CG__.meta[i].n;\n        if(nm) CG_NAME_SET[nm] = 1;\n      }\n    }\n  }\n  function toggleIdent(ident, scope, isField, isStructBase){\n    var sel = getIdentSel(ident, scope, isField);\n    if(curSel === sel){ clearIdentHl(); return; }\n    clearIdentHl();\n    var els = document.querySelectorAll(sel);\n    els.forEach(function(el){ el.classList.add(\'hl-ident\'); });\n    // P34：结构体基名——点击 obj 时，除基名出现位置外，一并高亮其所有字段访问\n    // （obj.field、obj.x …，即 [data-struct="obj"]），实现「结构体变量访问」联动。\n    if(isStructBase){\n      document.querySelectorAll(\'[data-struct="\' + ident + \'"]\').forEach(function(el){\n        el.classList.add(\'hl-ident\');\n      });\n    }\n    curSel = sel;\n    // P31：跳转到定义——找到该变量 / 结构体字段的「声明 / 定义」出现位置（data-kind="d"，\n    // 即 var-d 声明处），平滑滚动 + 脉冲定位；无声明（如纯读取）则回退到首个匹配。\n    var defSel = isField\n      ? \'[data-field="\' + ident + \'"]\' + (identCrossFile ? \'\' : \'[data-scope="\' + scope + \'"]\') + \'[data-kind="d"]\'\n      : \'[data-ident="\' + ident + \'"]:not([data-field])\' + (identCrossFile ? \'\' : \'[data-scope="\' + scope + \'"]\') + \'[data-kind="d"]\';\n    var defEl = document.querySelector(defSel);\n    // P36：结构体字段无独立声明语句，其定义为「首次写入」——回退到 data-rw=\'w\' 的首个出现处，\n    // 使点击字段名同样能跳到定义（此前字段恒无 data-kind=\'d\'，只会回退到 els[0] 即点击元素\n    // 自身，表现为「点了不跳」）。\n    if(!defEl && isField){\n      defEl = document.querySelector(\'[data-field="\' + ident + \'"]\' + (identCrossFile ? \'\' : \'[data-scope="\' + scope + \'"]\') + \'[data-rw="w"]\');\n    }\n    if(!defEl){ defEl = els[0]; }\n    if(defEl){\n      try {\n        defEl.scrollIntoView({block:\'center\', behavior:\'smooth\'});\n        defEl.classList.remove(\'hl-def\'); void defEl.getBoundingClientRect(); defEl.classList.add(\'hl-def\');\n      } catch(e){}\n    }\n    // P16-B：若点击的标识符正好是一个函数名，则在当前页调用图中联动高亮其节点\n    // （自动展开祖先路径并脉冲定位）；点击空白处由 document 监听器统一清除。\n    try {\n      ensureCGNameSet();\n      if(CG_NAME_SET && CG_NAME_SET[ident] && window.cgHighlightName){ window.cgHighlightName(ident); }\n    } catch(e){}\n  }\n  document.querySelectorAll(\'.ident\').forEach(function(el){\n    el.addEventListener(\'click\', function(ev){\n      ev.stopPropagation();\n      clearHl();\n      toggleIdent(el.getAttribute(\'data-ident\'), el.getAttribute(\'data-scope\'),\n                 el.hasAttribute(\'data-field\'), el.hasAttribute(\'data-struct-base\'));\n    });\n  });\n  document.querySelectorAll(\'.var\').forEach(function(el){\n    el.addEventListener(\'click\', function(ev){\n      ev.stopPropagation();\n      toggle(el.getAttribute(\'data-fn\'), el.getAttribute(\'data-param\'));\n      toggleIdent(el.getAttribute(\'data-ident\'), el.getAttribute(\'data-scope\'),\n                 el.hasAttribute(\'data-field\'));\n    });\n  });\n  // 「跨函数同名变量高亮」开关：勾选后，点击变量名即在整个文件内高亮同名变量\n  // （含结构体字段，按字段名），而不仅限当前函数，用于追踪变量跨函数传递。\n  var crossChk = document.getElementById(\'ident-cross-file\');\n  if(crossChk){\n    crossChk.addEventListener(\'change\', function(){\n      identCrossFile = crossChk.checked;\n      clearIdentHl();  // 切换作用域后清除旧高亮，避免状态错乱\n    });\n  }\n  // P35：注释块折叠——勾选后为源码表加 .fold-comments，隐藏纯注释行\n  // P-rev R44：状态持久化，跨页/刷新保持用户偏好；同时联动折叠文件头占位区域。\n  var foldChk = document.getElementById(\'fold-comments\');\n  function applyFold(on){\n    var wrap = document.querySelector(\'.src\');\n    if(wrap){ wrap.classList.toggle(\'fold-comments\', on); }\n    document.querySelectorAll(\'.src-hdr-details\').forEach(function(d){ d.open = !on; });\n  }\n  if(foldChk){\n    try{ var _savedFold = localStorage.getItem(\'pony.fold.comments\') === \'1\'; }\n    catch(_){ _savedFold = false; }\n    foldChk.checked = _savedFold;\n    applyFold(_savedFold);\n    foldChk.addEventListener(\'change\', function(){\n      applyFold(foldChk.checked);\n      try{ localStorage.setItem(\'pony.fold.comments\', foldChk.checked ? \'1\' : \'0\'); }catch(_){}\n    });\n  }\n  // P-rev R58：块注释折叠状态持久化——按「文件+起始行」记住展开/折叠偏好，\n  // 刷新/跨页后恢复，避免每次加载都重新展开已折叠的大段注释。\n  // P-rev R67：按钮文案与真实折叠状态始终同步——初始回显 localStorage 恢复后的\n  // 状态；随后任何单个块的手动折叠/展开（而非仅点按钮）也刷新按钮文字。\n  function _blkAllOpen(){\n    var ds = document.querySelectorAll(\'.src-blk-details[data-blk]\');\n    for(var i=0;i<ds.length;i++){ if(ds[i].open) return true; }\n    return false;\n  }\n  function _syncBlkBtn(){\n    var b = document.getElementById(\'blk-fold-all\');\n    if(b) b.textContent = _blkAllOpen() ? \'折叠块注释\' : \'展开块注释\';\n  }\n  (function(){\n    try{\n      var rel = location.pathname;\n      var saved = JSON.parse(localStorage.getItem(\'pony.fold.blocks\') || \'{}\');\n      var map = saved[rel] || {};\n      document.querySelectorAll(\'.src-blk-details[data-blk]\').forEach(function(d){\n        var k = d.getAttribute(\'data-blk\');\n        if(map[k] === \'open\'){ d.open = true; }\n        d.addEventListener(\'toggle\', function(){\n          var cur = JSON.parse(localStorage.getItem(\'pony.fold.blocks\') || \'{}\');\n          var m = cur[rel] || {};\n          m[k] = d.open ? \'open\' : \'closed\';\n          cur[rel] = m;\n          try{ localStorage.setItem(\'pony.fold.blocks\', JSON.stringify(cur)); }catch(_){}\n          _syncBlkBtn();          // P-rev R67：单块手动切换也回显按钮\n        });\n      });\n    }catch(_){}\n  })();\n  // P-rev R65/R67：块注释统一折叠/展开全部。与逐块持久化（R58）互补：一键把当前页\n  // 所有 %{...%} 块折叠或展开；初始及每次变化均回显按钮文案（R67）。\n  _syncBlkBtn();\n  var blkBtn = document.getElementById(\'blk-fold-all\');\n  if(blkBtn){\n    blkBtn.addEventListener(\'click\', function(){\n      var anyOpen = _blkAllOpen();\n      var target = !anyOpen;   // 有展开的就全部折叠，否则全部展开\n      document.querySelectorAll(\'.src-blk-details[data-blk]\').forEach(function(d){\n        d.open = target;\n        // 触发 toggle 事件以持久化（R58）并回显按钮（R67）\n        var evt = document.createEvent(\'Event\');\n        evt.initEvent(\'toggle\', true, false);\n        d.dispatchEvent(evt);\n      });\n    });\n  }\n  // P41：全文搜索高亮——URL 带 ?q=keyword 时，高亮源码中含关键字的行（行级高亮）\n  (function(){\n    try {\n      var m = location.search.match(/[?&]q=([^&]*)/);\n      if(!m) return;\n      var q = decodeURIComponent(m[1]).trim().toLowerCase();\n      if(!q) return;\n      var rows = document.querySelectorAll(\'.src table tr\');\n      var hit = 0;\n      for(var i = 0; i < rows.length; i++){\n        var code = rows[i].querySelector(\'.code\');\n        if(code && code.textContent.toLowerCase().indexOf(q) >= 0){\n          rows[i].classList.add(\'gs-match\');\n          hit++;\n        }\n      }\n      var info = document.getElementById(\'vf-info\');\n      if(info && hit){ info.innerHTML = \'全文搜索「\' + q + \'」命中 \' + hit + \' 行（已高亮）；清除请刷新页面。\'; }\n    } catch(e){}\n  })();\n  document.addEventListener(\'click\', function(){ clearHl(); clearIdentHl(); if(window.cgClearAll){ window.cgClearAll(); } });\n})();\n'
MATHJAX_INIT_JS = "(function(){var s=document.createElement('script');s.async=true;s.src='https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js';document.head.appendChild(s);})();"

