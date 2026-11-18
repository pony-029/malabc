# -*- coding: utf-8 -*-
"""**项目大脑**：把"失败登记表"从静态笔记变成会干预流程的机制。

    python tools/brain.py advise "要给报告加一个新字段"     # 动手前先问
    python tools/brain.py record --title "..." --symptom "..." \\
        --root-cause "..." --rule "..." --witness tools/xxx.py
    python tools/brain.py report                            # 出 flow/brain.html
    python tools/brain.py status                            # 一行健康度

## 三种角色，缺一不可

| 阶段 | 做什么 | 没有它会怎样 |
|---|---|---|
| **动手前** `advise` | 按任务描述检索历史上同类的坑，返回「规则 + 见证」 | 同样的错换个场景再犯一次 |
| **处置后** `record` | 追加一条（自动校验 witness 存在） | 教训留在对话里，下一个人看不到 |
| **回顾时** `report` | 统计 + 聚类 + 生成"下一步建议" | 只有明细没有方向 |

## `advise` 的检索为什么是词袋而不是模型

不需要语义理解 —— 因为**错误的描述本身就很具体**（"列全 0"、"witness 不存在"、
"README 没提"）。词袋 + 权重足够把相关条目排到前面，而且**可复现、可解释**
（能说出"因为命中了 字段/中断 这几个词"）。

接 LLM 时替换 `_score` 即可，接口不变。
"""
import argparse
import io
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "flow", "failures.json")
HTML = os.path.join(ROOT, "flow", "brain.html")

STOP = set("""
的 了 是 在 和 与 或 都 也 就 而 及 对 从 到 把 被 让 给 用 一个 一种 这 那 它
the a an is are was were to of in on for and or not with by as at it this that
""".split())


def load():
    if not os.path.isfile(REG):
        return {"version": 1, "entries": []}
    return json.load(io.open(REG, encoding="utf-8"))


def save(d):
    io.open(REG, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n")


def _tokens(text):
    """粗分词：英文按词、中文按 2-gram —— 够用且不引入依赖。"""
    text = (text or "").lower()
    out = set()
    for w in re.findall(r"[a-z_][a-z0-9_]{2,}", text):
        if w not in STOP:
            out.add(w)
    han = re.findall(r"[\u4e00-\u9fff]+", text)
    for seg in han:
        for i in range(len(seg) - 1):
            out.add(seg[i:i + 2])
    return out


def _score(query, e):
    """命中权重：`rule` 与 `symptom` 最重要（它们最接近"下次会遇到的样子"）。"""
    q = _tokens(query)
    if not q:
        return 0.0
    s = 0.0
    for field, w in (("rule", 3.0), ("symptom", 2.5), ("title", 2.0),
                     ("root_cause", 1.5)):
        t = _tokens(e.get(field) or "")
        if t:
            s += w * len(q & t) / (len(t) ** 0.5)
    return s


def advise(text, k=5, log=True):
    d = load()
    ranked = sorted(((_score(text, e), e) for e in d["entries"]),
                    key=lambda x: -x[0])
    hits = [(s, e) for s, e in ranked if s > 0][:k]
    # **留痕在 advise 里**，不在 CLI 里（R935）：流程监控是直接调函数的，
    # 若只在 CLI 记录，那条最有价值的调用（每阶段自动咨询）反而不会留痕。
    if log:
        _append_usage("advise", text, hits)
    return hits


def record(title, symptom, root_cause, rule, witness, status="fixed",
           commit="", note=""):
    """追加一条。**witness 必须存在** —— 没有见证的错误只算故事。"""
    d = load()
    if witness and not os.path.exists(os.path.join(ROOT, witness)):
        return None, "witness 不存在：%s（没有见证 = 没做防复发）" % witness
    used = {e["id"] for e in d["entries"]}
    n = 1
    while ("F%03d" % n) in used:
        n += 1
    e = {"id": "F%03d" % n, "title": title, "symptom": symptom,
         "root_cause": root_cause, "rule": rule, "witness": witness,
         "status": status, "commit": commit}
    if note:
        e["note"] = note
    d["entries"].append(e)
    save(d)
    return e, ""


def health(d=None):
    d = d or load()
    es = d["entries"]
    fixed = sum(1 for e in es if e["status"] == "fixed")
    wit = sum(1 for e in es if e.get("witness")
              and os.path.exists(os.path.join(ROOT, e["witness"])))
    return {"total": len(es), "fixed": fixed, "open": len(es) - fixed,
            "witnessed": wit,
            "coverage": (100.0 * wit / len(es)) if es else 0.0}


#: 给项目的建议 —— 由**登记内容**推出，不是写死的文案
TOPICS = [
    ("登记/记账", ("登记", "记账", "README", "发现性", "字段", "列")),
    ("报错文案", ("文案", "报错", "TODO", "归因", "消息")),
    ("格式化/模板", ("格式化", "模板", "CSS", "转义", "string.Template")),
    ("解析/切分", ("解析", "切分", "end", "深度", "depth", "块")),
    ("契约/默认值", ("契约", "默认", "严格", "宽松", "断言", "判据")),
    ("数据通道", ("stdout", "接通", "sidecar", "捕获", "数据源")),
]


def suggestions(d=None, k=4):
    """按"未闭 + 高频类别"给下一步建议。"""
    d = d or load()
    out = []
    for e in d["entries"]:
        if e["status"] != "fixed":
            out.append((100, "先闭合 %s：%s" % (e["id"], e["title"])))
    counts = {}
    for e in d["entries"]:
        blob = " ".join(str(e.get(f) or "") for f in
                        ("title", "symptom", "root_cause", "rule"))
        for name, kws in TOPICS:
            if any(kw in blob for kw in kws):
                counts[name] = counts.get(name, 0) + 1
    for name, c in sorted(counts.items(), key=lambda x: -x[1]):
        if c >= 2:
            out.append((c * 10, "「%s」类已犯 %d 次 —— 该为它加一条**自动判据**，"
                               "而不是继续靠记性" % (name, c)))
    out.sort(key=lambda x: -x[0])
    return [t for _, t in out[:k]]


def render(d=None):
    from string import Template

    d = d or load()
    h = health(d)
    es = sorted(d["entries"], key=lambda e: e["id"])
    sug = suggestions(d)

    cards = []
    for e in es:
        color = "#2ea043" if e["status"] == "fixed" else "#d29922"
        lab = "已修" if e["status"] == "fixed" else "未闭"
        cards.append("""
    <section class="e">
      <h3><span class="id">{id}</span> {title}
          <span class="badge" style="background:{c}">{lab}</span></h3>
      <p><b>现象</b> {sym}</p>
      <p><b>根因</b> {rc}</p>
      <p class="rule"><b>规则</b> {rule}</p>
      <p class="wit"><b>见证</b> <code>{w}</code>{cm}</p>
    </section>""".format(id=e["id"], title=e["title"], c=color, lab=lab,
                         sym=e["symptom"].replace("<", "&lt;"),
                         rc=e["root_cause"].replace("<", "&lt;"),
                         rule=e["rule"].replace("<", "&lt;"),
                         w=e["witness"],
                         cm=(" ｜ 修复 " + e["commit"]) if e.get("commit") else ""))

    sug_html = "".join("<li>%s</li>" % s for s in sug) or "<li>暂无</li>"
    tpl = Template("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>项目大脑 · 失败知识与反馈</title>
<style>
  :root{--bg:#f6f8fa;--fg:#1f2328;--mut:#57606a;--card:#fff;--line:#d0d7de}
  @media (prefers-color-scheme:dark){
    :root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--card:#161b22;--line:#30363d}
  }
  *{box-sizing:border-box}
  body{margin:0;padding:34px 20px;background:var(--bg);color:var(--fg);
       font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
  .wrap{max-width:960px;margin:0 auto}
  h1{font-size:26px;margin:0 0 6px}
  .sub{color:var(--mut);margin:0 0 22px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
        gap:12px;margin:0 0 22px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;
       padding:14px 16px}
  .kpi b{display:block;font-size:23px;font-variant-numeric:tabular-nums}
  .kpi span{color:var(--mut);font-size:12.5px}
  .panel{background:var(--card);border:1px solid var(--line);border-radius:14px;
         padding:16px 20px;margin:0 0 16px}
  .panel h2{font-size:16px;margin:0 0 10px}
  .panel ol{margin:0;padding-left:22px}
  .panel li{margin:4px 0;font-size:13.5px}
  .e{background:var(--card);border:1px solid var(--line);border-radius:12px;
     padding:14px 18px;margin:0 0 10px}
  .e h3{font-size:15px;margin:0 0 8px;display:flex;align-items:center;gap:9px}
  .id{font:12px ui-monospace,Consolas,monospace;color:var(--mut)}
  .badge{color:#fff;font-size:11px;padding:1px 8px;border-radius:999px;
         font-weight:600;margin-left:auto}
  .e p{margin:3px 0;font-size:13.5px}
  .e b{color:var(--mut);font-weight:600;margin-right:6px}
  .rule{background:rgba(46,160,67,.07);border-radius:8px;padding:7px 10px}
  .wit{color:var(--mut);font-size:12.5px}
  footer{color:var(--mut);font-size:12.5px;margin-top:20px;text-align:center}
</style></head><body><div class="wrap">
  <h1>项目大脑 · 失败知识与反馈</h1>
  <p class="sub">$n 条真实错误 ｜ 每条都带"下次再犯会红的见证" ｜ 生成于 $ts</p>
  <div class="kpis">
    <div class="kpi"><b>$n</b><span>登记条目</span></div>
    <div class="kpi"><b>$fx</b><span>已修</span></div>
    <div class="kpi"><b>$op</b><span>未闭</span></div>
    <div class="kpi"><b>$cov%</b><span>见证覆盖率</span></div>
  </div>
  <section class="panel">
    <h2>给项目的下一步建议（由登记内容推出）</h2>
    <ol>$sug</ol>
  </section>
  $cards
  <footer>由 <code>tools/brain.py report</code> 生成 — 建议不是写死的文案，
          而是按"未闭条目 + 高频类别"算出来的</footer>
</div></body></html>
""")
    return tpl.substitute(n=h["total"], fx=h["fixed"], op=h["open"],
                          cov="%.0f" % h["coverage"], ts=time.strftime("%Y-%m-%d %H:%M"),
                          sug=sug_html, cards="\n".join(cards))


def check():
    """**作为门执行**：有未闭条目、或条目缺合法见证 → 非零。

    为什么让大脑当门：知识库只有被**流程强制读取**时才真的起作用。
    放在这里而不是只做 `report`，是为了让"有未闭条目"这件事**卡住提交**，
    而不是躺在一个没人打开的页面里。
    """
    d = load()
    es = d["entries"]
    bad = []
    for e in es:
        w = (e.get("witness") or "").strip()
        if not w or not os.path.exists(os.path.join(ROOT, w)):
            bad.append("%s 的 witness 不成立：%r（没有见证 = 没做防复发）"
                       % (e["id"], w))
        if e.get("status") == "open":
            bad.append("%s 未闭合：%s（规则：%s）"
                       % (e["id"], e["title"], e.get("rule", "")))
    if bad:
        for b in bad:
            print("- %s" % b)
        print("brain check: %d 处未处理" % len(bad))
        return 1
    print("brain check: OK（%d 条，全部闭合且见证成立）" % len(es))
    return 0


#: 使用痕迹：每次 `advise` 命中都记一行，证明"大脑真的被读过"。
#: 没有它，"接进流程"只是口头承诺 —— 和登记表没人读是同一类问题。
USAGE = os.path.join(ROOT, "flow", "brain-usage.jsonl")


def _append_usage(cmd, query, hits):
    try:
        line = json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                           "cmd": cmd, "query": (query or "")[:120],
                           "hits": [e["id"] for _, e in hits]},
                          ensure_ascii=False)
        f = io.open(USAGE, "a", encoding="utf-8", newline="\n")
        with f:
            f.write(line + "\n")
    except (IOError, OSError):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="项目大脑：失败知识 + 反馈")
    ap.add_argument("cmd", choices=("advise", "record", "report", "status",
                                    "check"))
    ap.add_argument("text", nargs="?", help="advise 的任务描述")
    ap.add_argument("--title"), ap.add_argument("--symptom")
    ap.add_argument("--root-cause", dest="root_cause")
    ap.add_argument("--rule"), ap.add_argument("--witness")
    ap.add_argument("--status", default="fixed")
    ap.add_argument("--commit", default="")
    ns = ap.parse_args(argv)

    if ns.cmd == "status":
        h = health()
        print("brain: %d 条（已修 %d / 未闭 %d）｜见证覆盖 %.0f%%"
              % (h["total"], h["fixed"], h["open"], h["coverage"]))
        return 0

    if ns.cmd == "check":
        return check()

    if ns.cmd == "advise":
        hits = advise(ns.text or "")   # 留痕在 advise 内部统一记
        if not hits:
            print("[brain] 没有历史条目与这次任务相关 —— 但请动手后回来 record")
            return 0
        print("[brain] 动手前请先看这 %d 条（按相关度排序）：" % len(hits))
        for s, e in hits:
            print("  %s [%.1f] %s" % (e["id"], s, e["title"]))
            print("        规则：%s" % e["rule"])
            print("        见证：%s（%s）" % (e["witness"], e["status"]))
        return 0

    if ns.cmd == "record":
        for k in ("title", "symptom", "root_cause", "rule", "witness"):
            if not getattr(ns, k):
                print("record 缺 --%s" % k.replace("_", "-"), file=sys.stderr)
                return 2
        e, err = record(ns.title, ns.symptom, ns.root_cause, ns.rule,
                        ns.witness, ns.status, ns.commit)
        if err:
            print(err, file=sys.stderr)
            return 1
        print("[brain] 已登记 %s：%s（见证 %s）" % (e["id"], e["title"],
                                                  e["witness"]))
        return 0

    io.open(HTML, "w", encoding="utf-8", newline="\n").write(render())
    print("[brain] HTML -> %s" % HTML)
    return 0


if __name__ == "__main__":
    sys.exit(main())
