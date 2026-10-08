# -*- coding: utf-8 -*-
"""matlabc ask —— 拿静态分析结果当「事实底座」的问答式代码理解。

和直接问 AI「这个函数干什么的」最大的区别：**它的答案有据可查**。
先把工程扫成结构化事实（函数清单 / 调用图 / 告警优先级），再用 BM25 检索出
真正相关的片段喂给模型 —— 检索不到就回答「报告里没有」，而不是编一段。

它内部长这样：

    你的问题（自然语言）
        │
        ▼
    ┌──────────────────────────────────────────────┐
    │ ① 取得事实底座   --json report.json（已有报告）│
    │                  或 --dir ./myproj（现扫一次） │
    └──────────────────────────────────────────────┘
        │
        ▼  normalize()：把各语言各路径的报告揉成同一套东西
    ┌──────────────────────────────────────────────┐
    │ 函数文档  |  调用图(outgoing/incoming)  |  告警│
    └──────────────────────────────────────────────┘
        │
        ▼  意图识别 + BM25 检索（取最相关的 --topk 条）
    ┌──────────────────────────────────────────────┐
    │ 「谁调用 X」「X 调用谁」「哪里风险最高」「解释 X」│
    └──────────────────────────────────────────────┘
        │
        ▼  组装提示词 → ai_cli
    ┌──────────────────────────────────────────────┐
    │ 离线（没配 provider）：把提示词回显给你看      │
    │ 在线（--provider xx）：给出中文回答            │
    └──────────────────────────────────────────────┘

最小可跑示例（可直接复制）：
    python matlabc_ask.py "main 被谁调用" --dir ./myproj
    python matlabc_ask.py "哪里风险最高" --json report.json
    python matlabc_ask.py "helper 是做什么的" --dir ./myproj --lang matlab
    python matlabc_ask.py "谁调用了 parse_config" --dir ./myproj --provider deepseek
    python matlabc_ask.py "解释 compute_flow" --json r.json --topk 10 --output answer.md

两个入口二选一，都不给就是错：
    --dir   给工程目录，它自己先跑一次分析（慢，但省事）
    --json  给现成的 matlabc --json 报告（快，推荐在 CI 里用）

退出码：
    0  = 正常（离线回显也算成功，但请读输出判断是不是真答案）
    1  = 载入或生成报告失败（stderr 会打 `[matlabc ask] 载入/生成报告失败：...`）
    2  = 参数不全：既没给 --dir 也没给 --json

诚实边界：
  * 检索是**词法**的（BM25），不是向量检索。问法里用函数名/文件名等
    「报告里真出现过的词」，命中率远高于泛泛的描述性提问。
  * 离线模式**不会**产生任何「智能回答」，它只把将要发给模型的提示词回显出来。
    这是设计而非缺陷 —— 便于在没有网络/密钥的机器上检查提示词质量。
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile


# ---------------------------------------------------------------------------
# 归一化：把不同语言/不同路径的 JSON 报告统一为内部模型
# ---------------------------------------------------------------------------
def _norm_func_name(n):
    if isinstance(n, (list, tuple)):
        return " ".join(str(x) for x in n if x).strip()
    return str(n or "").strip()


def normalize(report):
    """返回 (funcs, graph, alerts, todos, stats, lang)。

    funcs:  [{name, rel, line, signature, calls:[name], lang}]
    graph:  {"outgoing":{name:[callee]}, "incoming":{name:[caller]}}
    alerts: [{rule, rel, line, msg, level}]
    todos:  [{rel, func, line, priority, complexity, fan_in, fan_out, ...}]
    """
    lang = (report.get("lang") or "matlab").lower()
    funcs = []
    files = report.get("files") or []
    for f in files:
        rel = f.get("rel") or f.get("path") or ""
        for fn in (f.get("functions") or []):
            name = _norm_func_name(fn.get("name") or fn.get("func"))
            if not name:
                continue
            calls = []
            for c in (fn.get("calls") or fn.get("calls_qualified") or []):
                calls.append(_norm_func_name(c))
            funcs.append({
                "name": name,
                "rel": rel,
                "line": fn.get("line") or fn.get("def_line") or 1,
                "signature": (fn.get("signature") or "").strip(),
                "calls": calls,
                "lang": lang,
            })

    graph = {"outgoing": {}, "incoming": {}}
    cg = report.get("call_graph") or {}
    if isinstance(cg, dict):
        for k, vs in (cg.get("outgoing") or {}).items():
            graph["outgoing"][_norm_func_name(k)] = [_norm_func_name(v) for v in (vs or [])]
        for k, vs in (cg.get("incoming") or {}).items():
            graph["incoming"][_norm_func_name(k)] = [_norm_func_name(v) for v in (vs or [])]
    # C/py/js 路径：edges 列表 {caller, callee}
    for e in (report.get("edges") or []):
        if isinstance(e, dict):
            c = _norm_func_name(e.get("caller"))
            d = _norm_func_name(e.get("callee"))
            if c and d:
                graph["outgoing"].setdefault(c, [])
                if d not in graph["outgoing"][c]:
                    graph["outgoing"][c].append(d)
                graph["incoming"].setdefault(d, [])
                if c not in graph["incoming"][d]:
                    graph["incoming"][d].append(c)

    alerts = []
    for key in ("uninitialized", "taint", "dead_code", "type_mismatch",
                "shape_mismatch", "operator_impact", "dup_code"):
        for a in (report.get(key) or []):
            if isinstance(a, dict):
                alerts.append({
                    "rule": key,
                    "rel": a.get("rel") or a.get("file") or "",
                    "line": a.get("line") or a.get("lineno") or 0,
                    "msg": (a.get("msg") or a.get("message") or a.get("detail")
                            or json.dumps(a, ensure_ascii=False))[:200],
                    "level": a.get("level") or ("error" if key in (
                        "uninitialized", "type_mismatch", "shape_mismatch") else "warning"),
                })
    for h in (report.get("heuristics") or []):
        if isinstance(h, dict):
            alerts.append({
                "rule": h.get("rule") or "heuristic",
                "rel": h.get("rel") or "",
                "line": h.get("line") or 0,
                "msg": (h.get("msg") or h.get("detail") or "")[:200],
                "level": h.get("level") or "warning",
            })

    todos = []
    dt = report.get("doc_todos") or {}
    if isinstance(dt, dict):
        todos = dt.get("todos") or []
    elif isinstance(dt, list):
        todos = dt

    stats = report.get("stats") or {}
    return funcs, graph, alerts, todos, stats, lang


# ---------------------------------------------------------------------------
# BM25（极简实现，零依赖）
# ---------------------------------------------------------------------------
_STOP = set("的 了 是 在 和 与 或 被 谁 哪 里 什么 怎么 如何 吗 呢 这 那 一个 a an the of to in for and or is are was were".split())


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _tokenize(text):
    toks = re.findall(r"[\w]+", (text or "").lower())
    return [t for t in toks if len(t) > 1 and t not in _STOP]


def build_bm25(docs):
    """docs: list[str] -> (tf, idf, doc_len, avgdl, N)"""
    N = len(docs)
    tf = []
    dl = []
    df = {}
    for d in docs:
        tks = _tokenize(d)
        dl.append(len(tks))
        f = {}
        for t in tks:
            f[t] = f.get(t, 0) + 1
        tf.append(f)
        for t in f:
            df[t] = df.get(t, 0) + 1
    idf = {}
    for t, c in df.items():
        idf[t] = max(0.0, (N - c + 0.5) / (c + 0.5))
    avgdl = (sum(dl) / N) if N else 0.0
    return tf, idf, dl, avgdl, N


def bm25_score(query_toks, tf, idf, dl, avgdl, N, idx):
    if N == 0:
        return 0.0
    k1, b = 1.5, 0.75
    score = 0.0
    f = tf[idx]
    for t in query_toks:
        if t not in idf:
            continue
        qf = query_toks.count(t)
        f_t = f.get(t, 0)
        denom = f_t + k1 * (1 - b + b * (dl[idx] / avgdl if avgdl else 0))
        score += idf[t] * ((f_t * (k1 + 1)) / denom) * qf
    return score


# ---------------------------------------------------------------------------
# 意图识别 + 检索
# ---------------------------------------------------------------------------
def _find_subject(question, func_names):
    """从问题中抽取被询问的函数名（优先命中已知函数名）。"""
    q = question.lower()
    # 直接命中已知名（长名优先，避免 subword 误匹配）
    hits = []
    for n in sorted(func_names, key=len, reverse=True):
        if re.search(r"(?<!\w)%s(?!\w)" % re.escape(n.lower()), q):
            hits.append(n)
    if hits:
        return hits[0]
    # 退化：取去除疑问词后的实义词
    q2 = re.sub(r"[？?。\.，,]", " ", question)
    toks = [t for t in _tokenize(q2) if t not in _STOP]
    for t in toks:
        if t in func_names:
            return t
    return toks[0] if toks else ""


def detect_intent(question):
    q = question.lower()
    if re.search(r"谁调用|被谁调用|caller|calls it|调用了.*?的是|的调用者|who calls|callers of|called by", q):
        return "callers"
    if re.search(r"调用了谁|调用谁|callee|调用了哪些|它调用|她调用|他调用|who does .* call|callees of|calls of", q):
        return "callees"
    if re.search(r"风险|复杂|hotspot|热点|优先|最危险|最复杂|问题|缺陷|坏", q):
        return "risk"
    if re.search(r"做什么|干什么|用途|是什么|解释|explain|说明|含义|功能", q):
        return "explain"
    return "retrieve"


def retrieve(question, docs, bm25):
    tf, idf, dl, avgdl, N = bm25
    qt = _tokenize(question)
    scored = [(i, bm25_score(qt, tf, idf, dl, avgdl, N, i)) for i in range(N)]
    scored = [(i, s) for i, s in scored if s > 0]
    scored.sort(key=lambda x: -x[1])
    return [i for i, _ in scored]


def run_ask(question, report, topk=6):
    funcs, graph, alerts, todos, stats, lang = normalize(report)
    func_names = [f["name"] for f in funcs]
    # 文档池：函数文档 + 告警文档
    func_docs = []
    for f in funcs:
        func_docs.append("%s %s 文件:%s 行:%s 调用:%s" % (
            f["name"], f["signature"], f["rel"], f["line"],
            ",".join(f["calls"]) or "-"))
    alert_docs = ["[%s] %s:%s %s" % (a["rule"], a["rel"], a["line"], a["msg"])
                  for a in alerts]
    docs = func_docs + alert_docs
    bm25 = build_bm25(docs)

    intent = detect_intent(question)
    subject = _find_subject(question, func_names)
    parts = []

    if intent in ("callers", "callees"):
        if subject:
            if intent == "callers":
                callers = graph["incoming"].get(subject, [])
                lines = ["函数 %s 的【调用者】(被以下函数调用)：" % subject]
                lines += (["  - %s" % c for c in callers] or ["  （无 / 未被项目内其他函数调用）"])
            else:
                callees = graph["outgoing"].get(subject, [])
                lines = ["函数 %s 的【被调用者】(它调用了)：" % subject]
                lines += (["  - %s" % c for c in callees] or ["  （无内部调用）"])
            parts.append("\n".join(lines))
        else:
            parts.append("（未能从问题中识别出具体函数名，已按相关性检索）")
            idxs = retrieve(question, docs, bm25)[:topk]
            parts.append(_fmt_docs(idxs, docs, func_docs))
    elif intent == "risk":
        lines = ["【风险/复杂度热点 Top %d】" % min(topk, max(1, len(todos)))]
        ranked = sorted(todos, key=lambda t: _int(t.get("priority")), reverse=True)[:topk]
        if ranked:
            for t in ranked:
                lines.append("  - %s/%s 行%d 复杂度%d 扇入%d 扇出%d 优先级%d" % (
                    t.get("rel"), t.get("func"), _int(t.get("line")),
                    _int(t.get("complexity")), _int(t.get("fan_in")),
                    _int(t.get("fan_out")), _int(t.get("priority"))))
        if alerts:
            lines.append("【静态告警 Top %d】" % min(topk, len(alerts)))
            for a in alerts[:topk]:
                lines.append("  - [%s] %s:%s %s" % (a["rule"], a["rel"], a["line"], a["msg"]))
        parts.append("\n".join(lines))
    elif intent == "explain" and subject:
        for f in funcs:
            if f["name"] == subject:
                lines = ["【函数 %s】" % subject,
                         "  签名：%s" % f["signature"],
                         "  位置：%s 行 %s" % (f["rel"], f["line"]),
                         "  调用：%s" % (",".join(f["calls"]) or "-"),
                         "  被调用：%s" % (",".join(graph["incoming"].get(subject, [])) or "-")]
                parts.append("\n".join(lines))
                break
        else:
            parts.append("未在分析中找到函数 %s，已按相关性检索：" % subject)
            idxs = retrieve(question, docs, bm25)[:topk]
            parts.append(_fmt_docs(idxs, docs, func_docs))
    else:
        idxs = retrieve(question, docs, bm25)[:topk]
        parts.append(_fmt_docs(idxs, docs, func_docs))

    context = "\n\n".join(p for p in parts if p)
    overview = _overview(stats, lang, len(funcs), len(alerts))
    return _assemble_prompt(question, overview, context)


def _fmt_docs(idxs, docs, func_docs):
    out = ["【检索到的相关上下文】"]
    for i in idxs:
        out.append("  - %s" % docs[i][:240])
    return "\n".join(out)


def _overview(stats, lang, n_funcs, n_alerts):
    if stats:
        return ("工程概览：语言=%s，文件=%s，函数=%s，类=%s，调用边=%s，告警=%s。"
                % (lang, stats.get("files", "?"), stats.get("functions", n_funcs),
                   stats.get("classes", 0),
                   stats.get("internal_edges", stats.get("call_edges", "?")), n_alerts))
    return "工程概览：语言=%s，函数=%s，告警=%s。" % (lang, n_funcs, n_alerts)


def _assemble_prompt(question, overview, context):
    return (
        "你是代码理解助手。下面是静态分析工具 matlabc 对目标工程的检索结果"
        "（已按相关性/意图筛选），请严格基于这些事实用中文回答，不要编造未给出的信息。\n\n"
        "## 工程概览\n%s\n\n"
        "## 用户问题\n%s\n\n"
        "## 检索上下文\n%s\n\n"
        "## 回答要求\n"
        "1) 只基于上面的上下文作答；2) 涉及函数/文件时给出 文件:行号；"
        "3) 若上下文不足以回答，明确说明「静态分析未覆盖」并给出可进一步分析的方向。"
        % (overview, question, context)
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def _load_report_json(path):
    with io.open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def _gen_report_from_dir(directory, lang):
    """跑一次 matlabc 分析生成临时 JSON 报告（dev 用 matlabc.py，frozen 用 exe 自身）。"""
    frozen = getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")
    here = os.path.dirname(os.path.abspath(__file__))
    if frozen:
        target = [sys.executable]
    else:
        target = [sys.executable, os.path.join(here, "matlabc.py")]
    tmp = tempfile.NamedTemporaryFile(prefix="matlabc_ask_", suffix=".json",
                                      delete=False)
    tmp.close()
    cmd = target + [directory, "--json", tmp.name, "--ai-mode", "off"]
    if lang:
        cmd += ["--lang", lang]
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # R62-R31e 子进程卫生：切 stdin（不继承调用方的管道）+ 墙钟超时。
    # 这里的子进程是本仓的 matlabc.py，正常 1–30s；900s 是给大工程留的余量。
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       stdin=subprocess.DEVNULL, timeout=900,
                       universal_newlines=True, encoding="utf-8", errors="replace",
                       env=env)
    if r.returncode != 0:
        sys.stderr.write("[matlabc ask] 分析失败（rc=%d）：\n%s\n"
                         % (r.returncode, (r.stdout or "")[:800]))
        raise RuntimeError("分析子进程失败")
    return tmp.name


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="matlabc ask",
        description="基于 matlabc 静态分析结果的问答式代码理解（零依赖/离线优先）。")
    ap.add_argument("question", nargs="+", help="自然语言问题（用引号包裹）")
    ap.add_argument("--dir", default=None, help="要分析并问答的工程目录")
    ap.add_argument("--json", dest="json_path", default=None,
                    help="直接载入已有的 matlabc --json 报告")
    ap.add_argument("--lang", default=None,
                    help="--dir 模式透传给分析器（matlab/c/py/js）")
    ap.add_argument("--provider", default=None, help="AI 供应商（缺省离线回显提示词）")
    ap.add_argument("--model", default=None)
    ap.add_argument("--topk", type=int, default=6)
    ap.add_argument("--output", default=None, help="将 AI 响应写入文件")
    ap.add_argument("--config", default=None)
    ap.add_argument("--ai-config", default=None)
    args = ap.parse_args(argv)
    question = " ".join(args.question)

    try:
        if args.json_path:
            report_path = args.json_path
        elif args.dir:
            report_path = _gen_report_from_dir(args.dir, args.lang)
        else:
            sys.stderr.write("[matlabc ask] 必须指定 --dir <工程目录> 或 --json <报告>。\n")
            return 2
        report = _load_report_json(report_path)
    except Exception as e:
        sys.stderr.write("[matlabc ask] 载入/生成报告失败：%s\n" % e)
        return 1

    prompt = run_ask(question, report, topk=args.topk)

    # 交给 ai_cli（离线=回显提示词；在线=给出回答）
    import ai_cli
    pf = tempfile.NamedTemporaryFile(prefix="matlabc_ask_prompt_", suffix=".md",
                                     delete=False, mode="w", encoding="utf-8")
    pf.write(prompt)
    pf.close()
    cli_argv = ["--prompt-file", pf.name, "--task", "explain"]
    if args.provider:
        cli_argv += ["--provider", args.provider]
    if args.model:
        cli_argv += ["--model", args.model]
    if args.config:
        cli_argv += ["--config", args.config]
    if args.ai_config:
        cli_argv += ["--ai-config", args.ai_config]
    if args.output:
        cli_argv += ["--output", args.output]
    return ai_cli.main(cli_argv)


if __name__ == "__main__":
    sys.exit(main())
