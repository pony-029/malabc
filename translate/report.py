# -*- coding: utf-8 -*-
"""转换过程可视化 v2：**播放器**。

## 交互设计（为什么这样设计）

转换有两条天然的轴，播放器必须同时支持：

| 轴 | 单位 | 用户想做的事 |
|---|---|---|
| **阶段轴** | 源码 → MIR → 生成的 C → 运行结果 | "这一步它做了什么？" |
| **函数轴** | 第 1 个函数 → 第 N 个 | "整体进展如何？哪些卡住了？" |

于是播放器是**二维**的：
* `◀ ▶` 在**阶段**上步进（同一函数内）；
* `⏮ ⏭` 在**函数**上跳（保持当前阶段号）；
* `▶ 播放` 沿"函数×阶段"的**扁平日程**自动前进（每个阶段一帧）；
* 速度 0.5× / 1× / 2× / 4×，`↻` 循环，进度条可直接 seek。

## 帧的呈现

* 代码类阶段（②③）**逐行显现**（打字机），让"它正在生成"可视；
* 状态色常驻在标题上，所以快进时也能立刻看出哪几个是红的；
* 键盘：`空格` 播放/暂停、`←/→` 阶段、`Home/End` 首尾、`1..4` 直跳阶段。

## 为什么自己写而不引库

报告要能**离线双击打开**（发给别人看），任何 CDN 依赖都会在离线时白屏。
所以：单文件 HTML + 内联 CSS/JS，零外部请求。
"""
import argparse
import html
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "c_runtime")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release", "m2c.exe")
MIR_PY = os.path.join(HERE, "mir.py")

COLORS = {
    "numeric": ("#15803d", "#dcfce7"),
    "stub": ("#b45309", "#fef3c7"),
    "shape": ("#6d28d9", "#ede9fe"),
    "rejected": ("#475569", "#f1f5f9"),
    "skipped": ("#64748b", "#f1f5f9"),
    "error": ("#b91c1c", "#fee2e2"),
}


def _run(cmd, cwd=None, timeout=600):
    return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=timeout)


def analyze(m, workdir):
    """把一个 .m 走完整链路，返回四栏内容与状态。"""
    card = {"file": os.path.basename(m), "src": "", "mir": "", "c": "",
            "run": "", "status": "error", "name": ""}
    try:
        card["src"] = open(m, encoding="utf-8", errors="replace").read().strip()
    except IOError:
        return card

    mir = os.path.join(workdir, os.path.basename(m) + ".mir")
    r = _run([sys.executable, MIR_PY, m, "-o", mir], timeout=300)
    if r.returncode != 0 or not os.path.isfile(mir):
        msg = (r.stdout or b"").decode("utf-8", "replace")
        # 「没有顶层 function」是**脚本/纯文档**，不是失败。
        # 归到 error 会让 error 这个分类失去意义（它该只表示编译/运行失败）。
        if "没有识别到 function" in msg or "没有识别到函数" in msg:
            card["status"] = "skipped"
            card["run"] = "该文件没有顶层 function（脚本或纯文档），不参与转换。"
        else:
            card["run"] = msg[-600:]
        return card

    text = open(mir, encoding="utf-8", errors="replace").read()
    card["mir"] = text.strip()

    func, reject, unmapped, shape_missing = "", False, 0, False
    #: 卡点分类（跨工程对比的原料）：`reject:` 的原因 + `# why:` 的归因码
    reasons = []
    for ln in text.splitlines():
        if ln.startswith("func:"):
            func = ln[5:].strip()
        elif ln.startswith("reject:"):
            reject = True
            for r in ln[7:].strip().split(","):
                if r.strip():
                    reasons.append("reject:" + r.strip())
        elif ln.startswith("# why:"):
            reasons.append("why:" + ln[6:].strip())
        elif ln.startswith("unmapped:"):
            unmapped += 1
        elif ln.startswith("arg:"):
            p = ln.split(":")
            if len(p) < 4 or not p[3].strip():
                shape_missing = True
    card["name"] = func
    card["reasons"] = reasons

    if not func:
        card["status"] = "skipped"
        card["run"] = "该文件没有顶层 function（脚本或纯文档），不参与转换。"
        return card
    if reject:
        card["status"] = "rejected"
        card["run"] = "签名无法用固定 C 签名表达（varargin / struct / cell）—— 拒绝，而不是猜。"
        return card
    if unmapped:
        card["status"] = "stub"
    elif shape_missing:
        card["status"] = "shape"

    gen = os.path.join(workdir, "gen_" + os.path.splitext(os.path.basename(m))[0])
    r = _run([M2C, "build", "--mir", mir, "--out", gen,
              "--name", os.path.splitext(os.path.basename(m))[0]], timeout=300)
    if r.returncode != 0:
        card["status"] = "error"
        card["run"] = r.stdout.decode("utf-8", "replace")[-800:]
        return card

    parts = []
    for dirpath, _dn, fns in os.walk(os.path.join(gen, "src")):
        for fn in fns:
            if fn.endswith(".c") and fn != "main.c":
                parts.append(os.path.join(dirpath, fn))
    card["c"] = "\n\n".join(open(p, encoding="utf-8", errors="replace").read().strip()
                            for p in parts)[:6000]

    if card["status"] == "stub":
        card["run"] = "函数是**桩**（含未映射语句）—— 不跑，也不假装有结果。"
        return card
    if card["status"] == "shape":
        card["run"] = "入参缺形状注解 —— 无法构造输入。"
        return card

    exe = os.path.join(workdir, "run_" + os.path.splitext(os.path.basename(m))[0] + ".exe")
    cc = shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        card["run"] = "没有 C 编译器，跳过运行。"
        return card
    r = _run([cc, "-std=c99", "-O1",
              "-I", os.path.join(gen, "include"), "-I", os.path.join(RT, "include"),
              os.path.join(gen, "src", "gen.c"), os.path.join(gen, "src", "main.c"),
              os.path.join(RT, "src", "mlc_runtime.c"),
              os.path.join(RT, "src", "mlc_ops.c"), "-o", exe, "-lm"], timeout=600)
    if r.returncode != 0:
        card["status"] = "error"
        card["run"] = r.stdout.decode("utf-8", "replace")[-900:]
        return card
    r = _run([exe], timeout=120)
    out = r.stdout.decode("utf-8", "replace").strip()
    if out:
        card["status"] = "numeric"
        card["run"] = out
    else:
        card["status"] = "error"
        card["run"] = "(进程退出，但没有任何输出)"
    return card


PAGE = u"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MATLAB → C 转换回放</title>
<style>
:root{--bg:#f6f8fb;--card:#fff;--fg:#0f172a;--mut:#64748b;--bd:#e3e8ef;
 --code:#0f172a;--codebg:#f8fafc;--accent:#2563eb}
[data-theme="dark"]{--bg:#0b1120;--card:#111827;--fg:#e5e7eb;--mut:#94a3b8;
 --bd:#1f2937;--code:#e5e7eb;--codebg:#0b1120;--accent:#60a5fa}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
.top{padding:14px 22px 10px;border-bottom:1px solid var(--bd);background:var(--card)}
h1{font-size:16px;margin:0 0 6px;font-weight:650;display:flex;gap:10px;align-items:center}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 2px}
.chip{font-size:11.5px;padding:2px 9px;border-radius:999px;font-weight:650}
/* 播放器 */
.player{position:sticky;top:0;z-index:9;background:var(--card);
 border-bottom:1px solid var(--bd);padding:10px 22px 12px}
.row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
button{background:var(--card);color:var(--fg);border:1px solid var(--bd);
 border-radius:8px;padding:6px 11px;cursor:pointer;font-size:13px;line-height:1}
button:hover{border-color:var(--accent);color:var(--accent)}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
button.primary:hover{opacity:.92;color:#fff}
select{background:var(--card);color:var(--fg);border:1px solid var(--bd);
 border-radius:8px;padding:5px 8px;font-size:12.5px}
.pos{font:12.5px ui-monospace,Consolas,monospace;color:var(--mut);min-width:96px}
.track{flex:1;min-width:180px;display:flex;align-items:center;gap:10px}
input[type=range]{flex:1;accent-color:var(--accent);height:4px}
.stages{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.stg{font-size:12px;padding:4px 10px;border-radius:999px;border:1px solid var(--bd);
 color:var(--mut);cursor:pointer;user-select:none}
.stg.on{border-color:var(--accent);color:var(--accent);font-weight:650;
 background:color-mix(in srgb,var(--accent) 10%,transparent)}
/* 卡片 */
.wrap{padding:16px 22px 60px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;
 overflow:hidden;margin-bottom:14px;transition:box-shadow .2s}
.card.active{box-shadow:0 0 0 2px var(--accent)}
.hd{display:flex;align-items:center;gap:10px;padding:9px 14px;
 border-bottom:1px solid var(--bd);cursor:pointer}
.nm{font-weight:650;font-family:ui-monospace,Consolas,monospace}
.badge{font-size:11.5px;font-weight:650;padding:2px 9px;border-radius:999px}
.file{color:var(--mut);font-size:12px;margin-left:auto}
.pane{padding:0;border-top:1px solid var(--bd)}
.pane:first-of-type{border-top:none}
.ttl{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);
 padding:6px 13px;background:color-mix(in srgb,var(--fg) 3%,transparent)}
pre{margin:0;padding:9px 13px;overflow:auto;max-height:300px;
 font:12px/1.55 ui-monospace,Consolas,monospace;color:var(--code);background:var(--codebg);
 white-space:pre-wrap;word-break:break-word}
.hide{display:none}
.kbd{font:11.5px ui-monospace,monospace;color:var(--mut);border:1px solid var(--bd);
 border-radius:5px;padding:1px 5px}
.foot{color:var(--mut);font-size:12px;padding:6px 0}
</style></head><body>

<div class="top">
  <h1>MATLAB → MIR → C 转换回放 <span class="kbd">空格</span> 播放
    <span class="kbd">←</span><span class="kbd">→</span> 阶段
    <span class="kbd">1</span>–<span class="kbd">4</span> 直跳</h1>
  <div class="chips">__CHIPS__</div>
</div>

<div class="player">
  <div class="row">
    <button id="first" title="第一个函数">⏮</button>
    <button id="prev" title="上一阶段">◀</button>
    <button id="play" class="primary">▶ 播放</button>
    <button id="next" title="下一阶段">▶</button>
    <button id="last" title="最后一个函数">⏭</button>
    <span class="pos" id="pos">1 / 1</span>
    <div class="track">
      <input type="range" id="seek" min="0" max="0" value="0">
    </div>
    <select id="speed">
      <option value="0.5">0.5×</option>
      <option value="1" selected>1×</option>
      <option value="2">2×</option>
      <option value="4">4×</option>
    </select>
    <button id="loop" title="循环播放">↻</button>
    <button id="mode" title="切换聚焦 / 总览">聚焦</button>
    <button id="theme" title="明暗主题">◐</button>
  </div>
  <div class="stages" id="stages">
    <span class="stg" data-i="0">① 源码</span>
    <span class="stg" data-i="1">② MIR</span>
    <span class="stg" data-i="2">③ 生成的 C</span>
    <span class="stg" data-i="3">④ 运行结果</span>
  </div>
</div>

<div class="wrap" id="wrap">__CARDS__</div>

<script>
(function(){
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var N = cards.length, STAGES = 4;
  var total = N * STAGES;
  var idx = 0, playing = false, timer = null, loop = false, focus = true;

  var $ = function(id){ return document.getElementById(id); };
  var seek = $('seek'); seek.max = Math.max(0, total - 1);

  function stageOf(i){ return i % STAGES; }
  function cardOf(i){ return Math.floor(i / STAGES); }

  // 逐行显现：让"正在生成"可见（打字机效果）
  function reveal(pre){
    if (!pre) return;
    var lines = pre.getAttribute('data-lines') || '';
    var all = pre.textContent;
    if (pre.getAttribute('data-done') === '1'){ return; }
    pre.textContent = '';
    var arr = all.split('\\n'), k = 0;
    var step = Math.max(1, Math.ceil(arr.length / 26));
    var t = setInterval(function(){
      pre.textContent += arr.slice(k, k + step).join('\\n') + (k + step < arr.length ? '\\n' : '');
      k += step;
      if (k >= arr.length){ clearInterval(t); pre.setAttribute('data-done','1'); }
    }, 22);
    void lines;
  }

  function render(scroll){
    var ci = cardOf(idx), si = stageOf(idx);
    cards.forEach(function(c, k){
      var on = (k === ci);
      c.classList.toggle('active', on);
      c.classList.toggle('hide', focus && !on);
      // 阶段可见性
      Array.prototype.forEach.call(c.querySelectorAll('.pane'), function(p, pi){
        p.classList.toggle('hide', on && pi > si);
      });
    });
    Array.prototype.forEach.call($('stages').children, function(el, i){
      el.classList.toggle('on', i === si);
    });
    $('pos').textContent = (idx + 1) + ' / ' + total +
      '  ·  函数 ' + (ci + 1) + '/' + N;
    seek.value = idx;

    if (scroll && cards[ci]) {
      cards[ci].scrollIntoView({behavior:'smooth', block:'center'});
    }
    // 当前阶段的代码逐行显现
    var pane = cards[ci] && cards[ci].querySelectorAll('.pane')[si];
    if (pane) { var pre = pane.querySelector('pre'); if (pre) reveal(pre); }
  }

  function go(i, scroll){
    idx = Math.max(0, Math.min(total - 1, i));
    render(scroll !== false);
  }

  function stop(){ playing = false; clearInterval(timer); $('play').textContent = '▶ 播放'; }

  function tick(){
    if (idx >= total - 1){
      if (loop) { go(0, true); return; }
      stop(); return;
    }
    go(idx + 1, true);
  }

  $('play').onclick = function(){
    if (playing) { stop(); return; }
    playing = true; this.textContent = '⏸ 暂停';
    tick();
    timer = setInterval(tick, 1700 / parseFloat($('speed').value));
  };
  $('next').onclick = function(){ stop(); go(idx + 1); };
  $('prev').onclick = function(){ stop(); go(idx - 1); };
  $('first').onclick = function(){ stop(); go(0, true); };
  $('last').onclick = function(){ stop(); go(total - 1, true); };
  seek.oninput = function(){ stop(); go(parseInt(this.value, 10), false); };
  $('speed').onchange = function(){
    if (playing){ clearInterval(timer); timer = setInterval(tick, 1700 / parseFloat(this.value)); }
  };
  $('loop').onclick = function(){ loop = !loop; this.style.color = loop ? 'var(--accent)' : ''; };
  $('mode').onclick = function(){
    focus = !focus; this.textContent = focus ? '聚焦' : '总览'; render(false);
  };
  $('theme').onclick = function(){
    var r = document.documentElement;
    r.dataset.theme = r.dataset.theme === 'dark' ? '' : 'dark';
  };
  Array.prototype.forEach.call($('stages').children, function(el){
    el.onclick = function(){
      stop();
      go(cardOf(idx) * STAGES + parseInt(el.dataset.i, 10), false);
    };
  });
  document.addEventListener('keydown', function(e){
    if (e.target && /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
    if (e.code === 'Space'){ e.preventDefault(); $('play').click(); }
    else if (e.code === 'ArrowRight'){ stop(); go(idx + 1); }
    else if (e.code === 'ArrowLeft'){ stop(); go(idx - 1); }
    else if (e.code === 'Home'){ stop(); go(0, true); }
    else if (e.code === 'End'){ stop(); go(total - 1, true); }
    else if (/^Digit[1-4]$/.test(e.code)){
      stop(); go(cardOf(idx) * STAGES + (parseInt(e.code.slice(5), 10) - 1), false);
    }
  });
  cards.forEach(function(c, k){
    c.querySelector('.hd').onclick = function(){ stop(); go(k * STAGES, true); };
  });

  render(false);
})();
</script>
</body></html>
"""

CARD = u"""<div class="card" data-status="__STATUS__">
  <div class="hd">
    <span class="nm">__NAME__</span>
    <span class="badge" style="color:__C__;background:__BG__">__STATUS__</span>
    <span class="file">__FILE__</span>
  </div>
  <div class="pane"><div class="ttl">① MATLAB 源码</div><pre>__SRC__</pre></div>
  <div class="pane"><div class="ttl">② MIR</div><pre>__MIR__</pre></div>
  <div class="pane"><div class="ttl">③ 生成的 C</div><pre>__CCODE__</pre></div>
  <div class="pane"><div class="ttl">④ 运行结果</div><pre>__RUN__</pre></div>
</div>"""

CHIP = u'<span class="chip" style="color:__C__;background:__BG__">__K__ __V__</span>'


def build(path, out, limit, reasons=None):
    """生成单页报告。`reasons` 若给一个 dict，会累积本工程所有卡点（跨工程对比用）。"""
    if os.path.isdir(path):
        files = []
        for dirpath, _dn, fns in os.walk(path):
            for fn in sorted(fns):
                if fn.endswith(".m"):
                    files.append(os.path.join(dirpath, fn))
        files.sort()
    else:
        files = [path]
    files = files[:limit]

    work = tempfile.mkdtemp(prefix="m2c_report_",
                            dir=os.environ.get("M2C_TMP") or None)
    cards, counts = [], {}
    try:
        for m in files:
            card = analyze(m, work)
            counts[card["status"]] = counts.get(card["status"], 0) + 1
            if reasons is not None:
                for r in card.get("reasons") or []:
                    reasons[r] = reasons.get(r, 0) + 1
            c, bg = COLORS.get(card["status"], ("#334155", "#f1f5f9"))
            cards.append(CARD
                         .replace("__NAME__", html.escape(card["name"] or card["file"]))
                         .replace("__FILE__", html.escape(card["file"]))
                         .replace("__STATUS__", card["status"])
                         .replace("__C__", c).replace("__BG__", bg)
                         .replace("__SRC__", html.escape(card["src"]))
                         .replace("__MIR__", html.escape(card["mir"]))
                         .replace("__CCODE__", html.escape(card["c"]))
                         .replace("__RUN__", html.escape(card["run"])))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    chips = []
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        c, bg = COLORS.get(k, ("#334155", "#f1f5f9"))
        chips.append(CHIP.replace("__K__", k).replace("__V__", str(v))
                     .replace("__C__", c).replace("__BG__", bg))
    chips.append('<span class="chip">共 %d 个函数</span>' % len(files))

    doc = (PAGE.replace("__CHIPS__", "".join(chips))
           .replace("__CARDS__", "\n".join(cards)))
    open(out, "w", encoding="utf-8", newline="\n").write(doc)
    print("共 %d 个函数 ｜ %s" % (len(files),
                                 " ｜ ".join("%s %d" % kv for kv in counts.items())))
    print("已写出 %s（%.1f KB）" % (out, os.path.getsize(out) / 1024.0))
    return counts


INDEX = u"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MATLAB → C 转换演示（多库）</title>
<style>
:root{--bg:#f6f8fb;--card:#fff;--fg:#0f172a;--mut:#64748b;--bd:#e3e8ef;--accent:#2563eb}
[data-theme="dark"]{--bg:#0b1120;--card:#111827;--fg:#e5e7eb;--mut:#94a3b8;--bd:#1f2937;--accent:#60a5fa}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
header{padding:22px 26px 10px;border-bottom:1px solid var(--bd);background:var(--card)}
h1{font-size:17px;margin:0 0 4px;font-weight:650}
.sub{color:var(--mut);font-size:12.5px}
.wrap{padding:18px 26px 60px;max-width:1100px}
table{width:100%;border-collapse:collapse;background:var(--card);
 border:1px solid var(--bd);border-radius:12px;overflow:hidden}
th,td{padding:10px 13px;text-align:left;border-bottom:1px solid var(--bd);font-size:13px}
th{font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--mut);font-weight:600}
tr:last-child td{border-bottom:none}
a{color:var(--accent);text-decoration:none;font-weight:600}
a:hover{text-decoration:underline}
.n{font-family:ui-monospace,Consolas,monospace}
.bar{display:flex;height:9px;border-radius:999px;overflow:hidden;
 background:color-mix(in srgb,var(--fg) 8%,transparent);min-width:120px}
.bar i{display:block}
.badge{font-size:11px;font-weight:650;padding:1px 7px;border-radius:999px}
button{background:var(--card);color:var(--fg);border:1px solid var(--bd);
 border-radius:8px;padding:6px 12px;cursor:pointer;font-size:12.5px}
.legend{margin:14px 0;display:flex;gap:12px;flex-wrap:wrap;color:var(--mut);font-size:12px}
.h2{font-size:15px;margin:26px 0 4px;font-weight:650}
.tag{display:inline-block;font:11.5px ui-monospace,Consolas,monospace;
 color:var(--mut);background:color-mix(in srgb,var(--fg) 6%,transparent);
 border-radius:6px;padding:1px 6px;margin-right:5px}
/* 全流程条 */
.flow{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
 gap:10px;margin:10px 0 18px}
.step{position:relative;background:var(--card);border:1px solid var(--bd);
 border-radius:12px;padding:12px 14px 11px}
.step .no{position:absolute;top:-9px;left:12px;width:20px;height:20px;
 border-radius:50%;background:var(--accent);color:#fff;font:600 11.5px/20px
 -apple-system,sans-serif;text-align:center}
.step b{display:block;margin:4px 0 3px;font-size:13.5px}
.step .d{color:var(--fg);font-size:12px;opacity:.85;
 font-family:ui-monospace,Consolas,monospace}
.step .ev{color:var(--mut);font-size:11.5px;margin-top:5px}
/* 实测数字 */
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 4px}
.kpi{background:var(--card);border:1px solid var(--bd);border-radius:12px;
 padding:11px 16px;min-width:120px}
.kpi .v{font:650 22px/1.2 ui-monospace,Consolas,monospace}
.kpi .k{color:var(--mut);font-size:11.5px;margin-top:3px}
</style></head><body>
<header>
  <h1>MATLAB → C 转换演示（多库汇总）</h1>
  <span class="sub">__SUMMARY__</span>
</header>
<div class="wrap">

  <h2 class="h2" style="margin-top:4px">转换全流程（每一格的证据都能点开核对）</h2>
  <div class="sub">同一条命令跑完五步，产物全部可在工程页里逐帧回放。</div>
  <div class="flow">
    <div class="step"><div class="no">1</div><b>源解析</b>
      <div class="d">`.m` → 函数/参数/形状注解</div><div class="ev">证据：① 源码面板</div></div>
    <div class="step"><div class="no">2</div><b>MIR</b>
      <div class="d">语句 → 算子序列（`op:`/`setb:`/`fill:`）</div><div class="ev">证据：② MIR 面板</div></div>
    <div class="step"><div class="no">3</div><b>发射 C</b>
      <div class="d">MIR → `src/gen.c`（含工程骨架）</div><div class="ev">证据：③ 生成的 C 面板</div></div>
    <div class="step"><div class="no">4</div><b>编译</b>
      <div class="d">`gcc -std=c99` + 运行时</div><div class="ev">失败会显式记为 `error`</div></div>
    <div class="step"><div class="no">5</div><b>运行</b>
      <div class="d">驱动构造输入 → 打印结果</div><div class="ev">证据：④ 运行结果面板</div></div>
  </div>

  <div class="stats">__STATS__</div>

  <h2 class="h2">各工程结果</h2>
  <div class="legend">__LEGEND__
    <button onclick="var r=document.documentElement;
      r.dataset.theme=r.dataset.theme==='dark'?'':'dark';">切换主题</button>
  </div>
  <table>
    <tr><th>工程</th><th>函数</th><th>分布</th><th>numeric</th><th>主要卡点</th><th>详情</th></tr>
    __ROWS__
  </table>

  <h2 class="h2">跨工程卡点对比</h2>
  <div class="sub">同一份统计口径下，各库卡在什么上 —— 这是"哪类代码最难"的直接证据。</div>
  <table>
    <tr><th>卡点</th><th>次数</th><th>分布</th><th>出现在</th></tr>
    __COMPARE__
  </table>
</div>
</body></html>
"""

ROW = u"""<tr>
  <td><b>__NAME__</b></td>
  <td class="n">__TOTAL__</td>
  <td><div class="bar">__BARS__</div></td>
  <td class="n"><b>__NUM__</b> (__PCT__%)</td>
  <td>__TOP__</td>
  <td><a href="__LINK__">回放 →</a></td>
</tr>"""


def build_site(dirs, outdir, limit):
    """把**多个工程**的转换结果汇成一个可点开的站点。

    这是「演示页面的机制」：一条命令产出 index + 每个工程一页，
    不再每次手工拼页面。工程名取目录名，页名 `proj_<name>.html`。
    """
    # 输出目录必须**干净**：写进一个已有内容的目录会静默合并，
    # 用户看到的 index 里混着别的工具产出的文件（实测踩过一次）。
    if os.path.isdir(outdir) and os.listdir(outdir):
        print("输出目录非空，拒绝写入：%s" % outdir)
        print("（换一个空目录，或先手动清理 —— 静默合并会让站点混入无关文件）")
        return 2
    os.makedirs(outdir, exist_ok=True)
    rows, total_all, num_all = [], 0, 0
    order = ["numeric", "stub", "shape", "rejected", "skipped", "error"]
    per_proj, all_reasons, agg = [], {}, {}
    TOTAL_ROW = u"""<tr>
  <td><span class="tag">%s</span>%s</td>
  <td class="n">%d</td>
  <td><div class="bar">%s</div></td>
  <td>%s</td>
</tr>"""

    # 工程必须真实存在：把输出目录误当成输入是最容易犯的一次错，
    # 而它的表现是"多了一个空工程"，不会报错。
    bad = [d for d in dirs if not os.path.isdir(d)]
    if bad:
        print("不是目录，已跳过：%s" % ", ".join(bad))
        print("（`--site` 的输入是**工程目录**，输出用 -o 指定）")
    dirs = [d for d in dirs if os.path.isdir(d)]
    if not dirs:
        print("没有任何工程目录")
        return 2

    for d in dirs:
        name = os.path.basename(os.path.abspath(d.rstrip("\\/"))) or "root"
        page = "proj_%s.html" % name
        print("[%s] 分析中…" % name)
        rs = {}
        counts = build(d, os.path.join(outdir, page), limit, reasons=rs)
        per_proj.append((name, rs))
        for k, v in rs.items():
            all_reasons[k] = all_reasons.get(k, 0) + v
        n = sum(counts.values())
        total_all += n
        num_all += counts.get("numeric", 0)
        for k, v in counts.items():
            agg[k] = agg.get(k, 0) + v
        bars = "".join(
            '<i style="width:%.2f%%;background:%s" title="%s %d"></i>'
            % (100.0 * counts[k] / n if n else 0, COLORS.get(k, ("#334155",))[0], k, counts[k])
            for k in order if counts.get(k))
        top = sorted(rs.items(), key=lambda kv: -kv[1])[:3]
        top_html = "".join('<span class="tag">%s×%d</span>'
                           % (html.escape(k), v) for k, v in top) or "—"
        rows.append(ROW.replace("__NAME__", html.escape(name))
                    .replace("__TOTAL__", str(n))
                    .replace("__BARS__", bars)
                    .replace("__NUM__", str(counts.get("numeric", 0)))
                    .replace("__PCT__", "%.0f" % (100.0 * counts.get("numeric", 0) / n if n else 0))
                    .replace("__TOP__", top_html)
                    .replace("__LINK__", page))

    legend = "".join(
        '<span class="badge" style="color:%s;background:%s">%s</span>'
        % (COLORS[k][0], COLORS[k][1], k) for k in order)

    # 跨工程卡点排行：同一口径下各库分别卡在什么上
    cmp_rows = []
    top_all = sorted(all_reasons.items(), key=lambda kv: -kv[1])[:10]
    vmax = top_all[0][1] if top_all else 1
    for label, cnt in top_all:
        who = [nm for nm, rs in per_proj if label in rs]
        bar = '<div class="bar"><i style="width:%.1f%%;background:#94a3b8"></i></div>' % (
            100.0 * cnt / vmax)
        cmp_rows.append(TOTAL_ROW % (html.escape(label.split(":")[0]),
                                     html.escape(label.split(":", 1)[-1]),
                                     cnt, bar,
                                     "".join('<span class="tag">%s</span>' % html.escape(w)
                                             for w in who[:4])))
    if not cmp_rows:
        cmp_rows.append('<tr><td colspan="4" class="sub">没有卡点（全部 numeric）</td></tr>')

    summary = "共 %d 个工程 ｜ %d 个函数 ｜ 真能算 %d（%.1f%%）" % (
        len(dirs), total_all, num_all,
        100.0 * num_all / total_all if total_all else 0)

    def kpi(val, key, color=None):
        style = ' style="color:%s"' % color if color else ""
        return ('<div class="kpi"><div class="v"%s>%s</div>'
                '<div class="k">%s</div></div>' % (style, val, key))

    stats = (kpi(len(dirs), "工程")
             + kpi(total_all, "函数总数")
             + kpi(num_all, "真能算 numeric", COLORS["numeric"][0])
             + kpi(agg.get("stub", 0), "桩（含未映射）", COLORS["stub"][0])
             + kpi(agg.get("rejected", 0), "签名拒绝", COLORS["rejected"][0])
             + kpi(agg.get("skipped", 0), "跳过（无 function）", COLORS["skipped"][0])
             + kpi(agg.get("error", 0), "编译/运行失败",
                   COLORS["error"][0] if agg.get("error") else COLORS["numeric"][0]))

    doc = (INDEX.replace("__SUMMARY__", html.escape(summary))
           .replace("__STATS__", stats)
           .replace("__LEGEND__", legend).replace("__ROWS__", "\n".join(rows))
           .replace("__COMPARE__", "\n".join(cmp_rows)))
    p = os.path.join(outdir, "index.html")
    open(p, "w", encoding="utf-8", newline="\n").write(doc)
    print("\n" + summary)
    print("已写出 %s（%.1f KB）" % (p, os.path.getsize(p) / 1024.0))
    return 0


def main():
    ap = argparse.ArgumentParser(description="MATLAB → C 转换回放（HTML 播放器）")
    ap.add_argument("source", nargs="+", help="一个或多个 .m / 目录（--site 时为工程目录）")
    ap.add_argument("-o", "--out", default=None,
                    help="单页模式输出文件；--site 模式输出目录")
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--site", action="store_true",
                    help="多工程模式：生成 index.html + 每个工程一页")
    a = ap.parse_args()
    if not os.path.isfile(M2C):
        print("m2c 未构建：cd rust/m2c && cargo build --release")
        return 2
    if a.site:
        return build_site(a.source, a.out or "m2c-site", a.limit)
    counts = build(a.source[0], a.out or "report.html", a.limit)
    return 0 if counts.get("error", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
