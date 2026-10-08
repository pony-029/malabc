# -*- coding: utf-8 -*-
"""快照回放站点渲染（从 matlabc.py 的 P123/P124 区块迁出）。

承载 JSON 快照统计与快照回放 HTML 站点的生成；分析数据由调用方构建后传入。
共享的辅助函数（URL 构造、文件写出、其它页面装配）仍由 matlabc 持有，
于本模块底部再导入，保持单向依赖 renderers -> matlabc。
"""
import os
import os.path as _pp
import json
import html as html_mod
import shutil
from pathlib import Path
from renderers.assets import write_browse_css_tree


def _clean_browse_dir(outdir):
    """P124：生成快照回放站点前清空旧目录（避免残留过时页面）。"""
    if os.path.exists(outdir):
        shutil.rmtree(outdir)


def _json_snapshot_stats(data):
    """P123：从 JSON 快照计算统计（无需重新扫描源码）。返回 dict。"""
    files = data.get("files") or []
    funcs = classes = parse_errors = 0
    for mf in files:
        if not isinstance(mf, dict):
            continue
        funcs += len(mf.get("functions") or [])
        classes += len(mf.get("classes") or [])
        parse_errors += len(mf.get("parse_errors") or [])
    taint = data.get("taint") or {}
    cg = data.get("call_graph") or {}
    return {
        "files": len(files),
        "functions": funcs,
        "classes": classes,
        "edges": len(data.get("edges") or []),
        "parse_errors": parse_errors,
        "global_vars": len(data.get("global_vars") or []),
        "constants": len(data.get("constants") or []),
        "types": len(data.get("types") or []),
        "uninitialized": len(data.get("uninitialized") or []),
        "dead_code": len(data.get("dead_code") or []),
        "type_mismatch": len(data.get("type_mismatch") or []),
        "shape_mismatch": len(data.get("shape_mismatch") or []),
        "taint_flows": len(taint.get("flows") or []),
        "taint_sinks": len(taint.get("sinks") or []),
        "doc_todos": len(data.get("doc_todos") or []),
        "dirs": len(data.get("dirs") or []),
        "call_nodes": len(cg.get("nodes") or []),
        "c_bridge": len(data.get("c_bridge") or []),
    }


def _json_contract_check(data):
    """P123：对 JSON 快照执行契约校验（P113 语义在可交换格式上的投影）。
    缺失必需字段 → error；结构非法项跳过。返回 issues 列表：
    [{"file", "target", "field", "level"}]。"""
    issues = []
    for key in _JSON_TOP_REQUIRED:
        if key not in data:
            issues.append({"file": "<root>", "target": "snapshot",
                           "field": key, "level": "error"})
    files = data.get("files")
    if not isinstance(files, list):
        return issues
    for mf in files:
        if not isinstance(mf, dict):
            continue
        rel = mf.get("rel") or "<unknown>"
        for key in _JSON_FILE_REQUIRED:
            if key not in mf:
                issues.append({"file": rel, "target": "file",
                               "field": key, "level": "error"})
        for idx, fn in enumerate(mf.get("functions") or []):
            if not isinstance(fn, dict):
                continue
            for key in _JSON_FN_REQUIRED:
                if key not in fn:
                    issues.append({"file": rel, "target": "function#%d" % idx,
                                   "field": key, "level": "error"})
        for idx, cls in enumerate(mf.get("classes") or []):
            if not isinstance(cls, dict):
                continue
            for key in _JSON_CLASS_REQUIRED:
                if key not in cls:
                    issues.append({"file": rel, "target": "class#%d" % idx,
                                   "field": key, "level": "error"})
    return issues


def _serialize_model(data):
    """P123：对称化 —— 把 JSON 快照规整为可再序列化的规范模型。
    与 render_json 同构（generated_at 置空，与 --reproducible 对齐），
    支持 --from-json X --json Y 的往返一致性比对。返回 (out, notes)。"""
    try:
        out = json.loads(json.dumps(data, ensure_ascii=False, default=_json_default))
    except Exception as exc:
        return None, {"error": str(exc)}
    out["generated_at"] = ""
    return out, {"generated_at": "cleared"}


def _roundtrip_diff(a, b, path=""):
    """P123：递归比较两个 JSON 值，返回差异路径列表（用于往返一致性报告）。
    dict 按键集合 + 值递归；list 按索引；其余按 !=。"""
    diffs = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            sub = "%s.%s" % (path, k) if path else str(k)
            if k not in a:
                diffs.append("%s: 仅目标有 %r" % (sub, b[k]))
            elif k not in b:
                diffs.append("%s: 仅源有 %r" % (sub, a[k]))
            else:
                diffs.extend(_roundtrip_diff(a[k], b[k], sub))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append("%s: 长度 %d != %d" % (path or "[]", len(a), len(b)))
        for i in range(min(len(a), len(b))):
            diffs.extend(_roundtrip_diff(a[i], b[i], "%s[%d]" % (path, i)))
    elif a != b:
        diffs.append("%s: %r != %r" % (path or "value", a, b))
    return diffs


def render_snapshot_report(data, contract_issues=None):
    """P123：基于 JSON 快照（dict）渲染 Markdown 快照报告 —— 不依赖源码重扫。
    供 --from-json X -o OUT 使用，与对象驱动的 --markdown 渲染器并列。"""
    contract_issues = contract_issues or []
    stats = _json_snapshot_stats(data)
    out = []
    out.append("# MATLAB 分析快照报告（--from-json）")
    out.append("")
    out.append("> 来源：`--json` 导出的可交换快照；`--from-json` 导入后按 dict 渲染，"
               "无需重新扫描源码。")
    out.append("")
    out.append("| 项目 | 值 |")
    out.append("| --- | --- |")
    out.append("| 工具版本 | %s |" % (data.get("version") or ""))
    out.append("| 根目录 | `%s` |" % (data.get("root") or ""))
    out.append("| 生成时间 | %s |" % (data.get("generated_at") or "-"))
    out.append("")
    out.append("## 概览统计")
    out.append("")
    out.append("| 指标 | 数量 |")
    out.append("| --- | --- |")
    _rows = [
        ("文件", "files"), ("函数", "functions"), ("类", "classes"),
        ("调用边", "edges"), ("解析错误", "parse_errors"),
        ("全局变量", "global_vars"), ("常量", "constants"), ("类型", "types"),
        ("未初始化", "uninitialized"), ("死代码", "dead_code"),
        ("类型不一致", "type_mismatch"), ("形状违规", "shape_mismatch"),
        ("污点流", "taint_flows"), ("敏感接收点", "taint_sinks"),
        ("待办清单", "doc_todos"), ("目录节点", "dirs"),
        ("调用图节点", "call_nodes"), ("C 桥接", "c_bridge"),
    ]
    for _label, _key in _rows:
        out.append("| %s | %s |" % (_label, stats.get(_key, 0)))
    out.append("")
    files = data.get("files") or []
    out.append("## 文件清单（%d）" % len(files))
    out.append("")
    if files:
        out.append("| 文件 | 类型 | 行数 | 函数 | 类 | 解析错误 |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        for mf in files:
            if not isinstance(mf, dict):
                continue
            out.append("| `%s` | %s | %s | %d | %d | %d |" % (
                mf.get("rel", ""), mf.get("kind", ""), mf.get("lines", 0),
                len(mf.get("functions") or []), len(mf.get("classes") or []),
                len(mf.get("parse_errors") or [])))
    else:
        out.append("_（快照中无文件）_")
    out.append("")
    out.append("## 函数清单")
    out.append("")
    _has_fn = False
    for mf in files:
        if not isinstance(mf, dict):
            continue
        funcs = mf.get("functions") or []
        if not funcs:
            continue
        _has_fn = True
        out.append("### `%s`" % mf.get("rel", ""))
        out.append("")
        out.append("| 函数 | 类型 | 行 | 输入 | 输出 | 签名 |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        for fn in funcs:
            if not isinstance(fn, dict):
                continue
            out.append("| `%s` | %s | %s | %d | %d | `%s` |" % (
                fn.get("name", ""), fn.get("kind", ""), fn.get("line", 0),
                len(fn.get("inputs") or []), len(fn.get("outputs") or []),
                (fn.get("signature") or "")[:64]))
        out.append("")
    if not _has_fn:
        out.append("_（快照中无函数）_")
        out.append("")
    cg = data.get("call_graph") or {}
    out.append("## 调用图摘要")
    out.append("")
    out.append("| 项 | 值 |")
    out.append("| --- | --- |")
    out.append("| 节点 | %d |" % len(cg.get("nodes") or []))
    out.append("| 入口 | %s |" % ("、".join(cg.get("entries") or [])[:80]))
    out.append("| 歧义调用 | %d |" % len(cg.get("ambiguous") or []))
    out.append("")
    out.append("## 契约校验")
    out.append("")
    if contract_issues:
        out.append("发现 %d 个契约问题：" % len(contract_issues))
        out.append("")
        out.append("| 文件 | 目标 | 缺失字段 | 级别 |")
        out.append("| --- | --- | --- | --- |")
        for it in contract_issues:
            out.append("| `%s` | %s | `%s` | %s |" % (
                it.get("file", ""), it.get("target", ""),
                it.get("field", ""), it.get("level", "")))
    else:
        out.append("_无缺字段，快照满足 P113 契约（JSON 投影）。_")
    out.append("")
    return "\n".join(out) + "\n"


def _run_from_json(args):
    """P123：--from-json 快照导入入口（短路分支，不进入 MATLAB 分析流程）。
    - 默认打印导入摘要；
    - --json OUT：对称化重导出 + 读回往返一致性校验；
    - -o/--output OUT：渲染快照报告（dict 驱动，无需源码重扫）；
    - --max-warnings：契约缺字段数量门禁（> 阈值返回 1）。"""
    path = args.from_json
    data, err = _from_json_load(path)
    if err:
        print("[ERROR] %s" % err, file=sys.stderr)
        return 1
    issues = _json_contract_check(data)
    stats = _json_snapshot_stats(data)
    print("===== JSON 快照导入（P123）=====")
    print("来源   : %s" % path)
    print("版本   : %s" % (data.get("version") or "-"))
    print("根目录 : %s" % (data.get("root") or "-"))
    print("文件 %d | 函数 %d | 类 %d | 调用边 %d | 目录 %d | 契约问题 %d" % (
        stats["files"], stats["functions"], stats["classes"], stats["edges"],
        stats["dirs"], len(issues)))
    if issues:
        print("契约校验：%d 个缺字段问题（--max-warnings 可门禁）" % len(issues))
        for it in issues[:10]:
            print("  [%s] %s:%s 缺 `%s`" % (it["level"].upper(), it["file"],
                                            it["target"], it["field"]))
        if len(issues) > 10:
            print("  ... 其余 %d 条省略" % (len(issues) - 10))
    else:
        print("契约校验：通过（快照满足 P113 契约的 JSON 投影）")
    rc = 0
    if args.json:
        out_data, notes = _serialize_model(data)
        if out_data is None:
            print("[ERROR] 对称化失败：%s" % notes.get("error", ""), file=sys.stderr)
            return 1
        _write_output(args.json,
                      json.dumps(out_data, ensure_ascii=False, indent=2,
                                 default=_json_default),
                      "快照重导出 JSON")
        data2, err2 = _from_json_load(args.json)
        if err2:
            print("往返校验：读回失败：%s" % err2, file=sys.stderr)
            rc = 1
        else:
            diffs = _roundtrip_diff(out_data, data2)
            if diffs:
                print("往返校验：%d 处差异" % len(diffs))
                for d in diffs[:10]:
                    print("  - %s" % d)
                rc = 1
            else:
                print("往返校验：一致（读-写-读逐字段相等；generated_at 已规范化置空）")
    if args.output:
        _write_output(args.output,
                      render_snapshot_report(data, contract_issues=issues),
                      "快照报告")
    if args.max_warnings > 0 and len(issues) > args.max_warnings:
        print("契约问题 %d 超过 --max-warnings=%d，质量门禁未通过"
              % (len(issues), args.max_warnings), file=sys.stderr)
        rc = 1
    # P124：--from-json + --browse —— 快照回放离线浏览站点（无需源码重扫）
    if args.browse:
        try:
            pages = render_snapshot_browse_site(data, args.browse)
            print("快照回放站点（P124）：已生成 %d 页于 %s" % (pages, args.browse))
        except Exception as exc:
            print("[ERROR] 生成快照回放站点失败：%s" % exc, file=sys.stderr)
            rc = 1
    return rc


# ---------------------------------------------------------------------------
# P124：JSON 快照回放浏览站点（--from-json X --browse OUT）
# 直接从 --json 导出的快照（dict）渲染离线自包含 HTML 浏览站点，无需源码重扫；
# 与 render_browse_site（对象驱动）构成「对象 / 快照」双轨站点生成。
# 快照不含源码正文 → 文件页以函数 / 类卡片呈现（签名、调用、文档、指标），
# 并内嵌 snapshot.json 归档副本，可跨机器 / CI 直接回放分析结果。
# ---------------------------------------------------------------------------

def _snapshot_qkey(rel, name):
    """P124：调用图节点键 rel:name（与 --json 的 calls/edges 同构）。"""
    return "%s:%s" % (rel, name)


def _snapshot_index(data):
    """P124：从快照 dict 建立浏览索引 {fn_key, file_by_rel, cls_by_rel, cg}。

    fn_key：{rel:name -> {rel, name, line, kind, signature, qualified}}，用于
    调用关系互相链接；file_by_rel / cls_by_rel 供索引页与文件页直接消费。
    """
    fn_key = {}
    file_by_rel = {}
    cls_by_rel = {}
    for mf in data.get("files") or []:
        if not isinstance(mf, dict):
            continue
        rel = mf.get("rel") or ""
        file_by_rel[rel] = mf
        for fn in mf.get("functions") or []:
            if not isinstance(fn, dict):
                continue
            fn_key[_snapshot_qkey(rel, fn.get("name", ""))] = {
                "rel": rel,
                "name": fn.get("name", ""),
                "line": fn.get("line", 0),
                "kind": fn.get("kind", ""),
                "signature": fn.get("signature", ""),
                "qualified": fn.get("qualified", ""),
            }
        cls_by_rel[rel] = [c for c in (mf.get("classes") or [])
                           if isinstance(c, dict)]
    return {"fn_key": fn_key, "file_by_rel": file_by_rel,
            "cls_by_rel": cls_by_rel, "cg": data.get("call_graph") or {}}


def _snapshot_rel_href(from_rel, to_rel):
    """P124：文件页内指向另一文件页的相对链接（src 目录内，处理子目录层级）。"""
    import posixpath as _pp
    base = _pp.dirname("src/" + _page_rel(from_rel)) or "."
    return _pp.relpath("src/" + _page_rel(to_rel), base)


def _snapshot_fn_href(idx, key, from_rel=None):
    """P124：调用图键 → 文件页函数锚点链接；未解析到项目文件返回 None。

    from_rel 为 None 时返回站点根相对路径（索引页用）；否则返回文件页内
    相对路径（文件页用），保证 src 子目录嵌套时链接不失效。
    """
    info = idx["fn_key"].get(key)
    if not info:
        return None
    if from_rel is not None:
        base = "%s#fn-%s" % (_snapshot_rel_href(from_rel, info["rel"]),
                             info["name"])
    else:
        base = "%s#fn-%s" % (_src_href_from_rel(info["rel"]), info["name"])
    return base


def _snapshot_call_html(idx, items, from_rel=None):
    """P124：把调用项列表渲染为链接/纯文本 <code> 列表（含未解析的裸名）。"""
    if not items:
        return '<span class="muted">无</span>'
    parts = []
    for c in items:
        href = _snapshot_fn_href(idx, c, from_rel)
        esc = html_mod.escape(str(c) if c is not None else "")
        if href:
            parts.append('<a href="%s"><code>%s</code></a>' % (href, esc))
        else:
            parts.append("<code>%s</code>" % esc)
    return " ".join(parts)


def _snapshot_count_html(d):
    """P124：把 {名字: 次数} 渲染为 <code>名字</code>×次数 列表。"""
    if not d:
        return '<span class="muted">无</span>'
    return " ".join(
        "<code>%s</code>\u00d7%d" % (html_mod.escape(str(k)), int(v))
        for k, v in sorted(d.items(), key=lambda kv: str(kv[0]).lower()))


def _snapshot_metric_rows(data, idx):
    """P124：从快照计算函数风险指标行（_compute_function_metrics 的 dict 投影）。

    快照不含圈复杂度 → cx=0；影响面 / 依赖面用 call_graph 出入边做传递闭包
    统计唯一可达函数数，风险 = 影响×3 + 扇入×2 + 依赖 + 扇出 + 圈复杂度。
    """
    cg = idx["cg"]
    incoming = cg.get("incoming") or {}
    outgoing = cg.get("outgoing") or {}

    def _closure(adj, start):
        seen = set()
        stack = list(adj.get(start) or [])
        while stack:
            n = stack.pop()
            if n == start or n in seen:
                continue
            seen.add(n)
            stack.extend(adj.get(n) or [])
        return seen

    rows = []
    for rel in sorted(idx["file_by_rel"]):
        for fn in idx["file_by_rel"][rel].get("functions") or []:
            if not isinstance(fn, dict) or fn.get("kind") == "script":
                continue
            name = fn.get("name", "")
            key = _snapshot_qkey(rel, name)
            fan_in = len(set(incoming.get(key) or []))
            fan_out = len(set(outgoing.get(key) or []))
            impact = len(_closure(incoming, key))
            dependency = len(_closure(outgoing, key))
            cx = 0
            risk = impact * 3 + fan_in * 2 + dependency + fan_out + cx
            if fan_in == 0 and fan_out == 0:
                tag = "孤立"
            elif fan_out >= 8 or (fan_out >= 5 and cx >= 10):
                tag = "上帝函数"
            elif impact >= 5 or fan_in >= 5:
                tag = "关键"
            else:
                tag = "普通"
            rows.append({"name": name, "rel": rel, "line": fn.get("line", 0),
                         "kind": fn.get("kind", ""), "cx": cx, "fan_in": fan_in,
                         "fan_out": fan_out, "impact": impact,
                         "dependency": dependency, "risk": risk, "tag": tag})
    rows.sort(key=lambda r: (-r["risk"], r["rel"].lower(),
                              r["name"].lower(), r["line"]))
    return rows


def _snapshot_unresolved_rows(data, idx):
    """P124：聚合快照 external_calls 为疑似漏检调用行（_collect_unresolved_calls 的投影）。"""
    project = {}
    for rel, mf in idx["file_by_rel"].items():
        for fn in mf.get("functions") or []:
            if not isinstance(fn, dict):
                continue
            project.setdefault(fn.get("name", "").lower(), []).append(
                (rel, fn.get("name", ""), fn.get("line", 0), fn.get("kind", "")))
    agg = {}
    for rel, mf in idx["file_by_rel"].items():
        for fn in mf.get("functions") or []:
            if not isinstance(fn, dict):
                continue
            for nm, c in (fn.get("external_calls") or {}).items():
                agg[nm] = agg.get(nm, 0) + c
    rows = []
    for nm, c in sorted(agg.items(), key=lambda kv: (-kv[1], kv[0].lower())):
        rows.append({"name": nm, "count": c,
                     "in_project": bool(project.get(nm.lower())),
                     "matches": project.get(nm.lower(), [])})
    return rows


def _snapshot_builtin_items(data):
    """P124：汇总快照 builtin_calls（name → 总次数），降序 [(name, cnt), ...]。"""
    agg = {}
    for mf in data.get("files") or []:
        if not isinstance(mf, dict):
            continue
        for fn in mf.get("functions") or []:
            if not isinstance(fn, dict):
                continue
            for bname, c in (fn.get("builtin_calls") or {}).items():
                agg[bname] = agg.get(bname, 0) + c
    return sorted(agg.items(), key=lambda kv: (-kv[1], kv[0].lower()))


def _snapshot_attach_file(idx, items):
    """P124：给快照检查项补 file 字段（func/name → rel 反查）。

    --json 导出的 uninitialized/type_mismatch/dead_code 是扁平数组，不含所属
    文件；render_checks_page 需要 r["file"] 生成跳转链接，这里按函数名反查。
    同名函数取首个命中（快照回放仅作跳转提示，不影响告警内容）。
    """
    by_name = {}
    for rel, mf in idx["file_by_rel"].items():
        for fn in mf.get("functions") or []:
            if not isinstance(fn, dict):
                continue
            by_name.setdefault(fn.get("name", ""), rel)
    out = []
    for r in items:
        if not isinstance(r, dict):
            continue
        r2 = dict(r)
        if not r2.get("file"):
            r2["file"] = by_name.get(r2.get("func") or r2.get("name") or "",
                                     "") or ""
        out.append(r2)
    return out


def _snapshot_page_head(title):
    """P124：快照回放页面公共头部（BROWSE_CSS 同款样式）。"""
    return ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport\" content=\"width=device-width,initial-scale=1">'
            "<title>%s</title><link rel=\"stylesheet\" href=\"browse.css\"></head><body>\n"
            % html_mod.escape(title))


def _snapshot_stat_html(items):
    """P124：统计卡片区 HTML。items 为 [(标签, 数值), ...]。"""
    return "".join(
        '<div class="stat-card"><span class="num">%d</span>'
        '<span class="lbl">%s</span></div>' % (int(n), html_mod.escape(lbl))
        for lbl, n in items)


def _render_snapshot_index(data, idx):
    """P124：快照回放首页——元数据、统计、文件/函数/类索引、子页导航。"""
    cg = idx["cg"]
    files = [f for f in (data.get("files") or []) if isinstance(f, dict)]
    n_fn = sum(len([x for x in (mf.get("functions") or []) if isinstance(x, dict)])
               for mf in files)
    n_cls = sum(len([x for x in (mf.get("classes") or []) if isinstance(x, dict)])
                for mf in files)
    n_edges = len(data.get("edges") or [])
    n_err = sum(len(mf.get("parse_errors") or []) for mf in files)
    n_uninit = len(data.get("uninitialized") or [])
    n_mismatch = len(data.get("type_mismatch") or [])
    n_dead = len(data.get("dead_code") or [])
    issues = data.get("_contract_issues") or []
    sub_links = [
        ("metrics.html", "函数风险度量"),
        ("checks.html", "静态检查（未初始化/类型/死代码）"),
        ("unresolved.html", "疑似漏检调用"),
        ("matlab_lib.html", "MATLAB 内置库函数"),
    ]
    if isinstance(data.get("taint"), dict) and (
            data.get("taint").get("flows") or data.get("taint").get("stats")):
        sub_links.append(("taint.html", "污点流分析"))
    if isinstance(data.get("doc_todos"), dict) and (
            data.get("doc_todos").get("todos") or data.get("doc_todos").get("stats")):
        sub_links.append(("todo.html", "函数待办清单"))
    sub_links.append(("snapshot.json", "快照 JSON 归档副本"))
    sub_html = "".join(
        '<li><a href="%s">%s</a></li>' % (name, html_mod.escape(lbl))
        for name, lbl in sub_links)
    rows = []
    for mf in sorted(files, key=lambda m: (m.get("rel") or "").lower()):
        rel = mf.get("rel") or ""
        nf = len([x for x in (mf.get("functions") or []) if isinstance(x, dict)])
        nc = len([x for x in (mf.get("classes") or []) if isinstance(x, dict)])
        npe = len(mf.get("parse_errors") or [])
        rows.append('<tr><td><a href="%s">%s</a></td><td>%s</td><td>%s</td>'
                    "<td>%d</td><td>%d</td><td>%d</td><td>%d</td></tr>"
                    % (_src_href_from_rel(rel), html_mod.escape(rel),
                       html_mod.escape(str(mf.get("kind") or "")),
                       html_mod.escape(str(mf.get("encoding") or "-")),
                       int(mf.get("lines", 0)), nf, nc, npe))
    fn_rows = []
    for rel in sorted(idx["file_by_rel"]):
        for fn in sorted(idx["file_by_rel"][rel].get("functions") or [],
                         key=lambda f: int(f.get("line", 0))):
            if not isinstance(fn, dict):
                continue
            name = fn.get("name", "")
            href = "%s#fn-%s" % (_src_href_from_rel(rel), name)
            fn_rows.append(
                '<tr><td><a href="%s">%s</a></td><td><a href="%s"><code>%s</code></a></td>'
                "<td>%s</td><td>%d</td><td>%s</td></tr>"
                % (href, html_mod.escape(rel), href, html_mod.escape(name),
                   html_mod.escape(str(fn.get("kind") or "")),
                   int(fn.get("line", 0)),
                   html_mod.escape(str(fn.get("signature") or "-"))))
    cls_rows = []
    for rel in sorted(idx["cls_by_rel"]):
        for c in idx["cls_by_rel"][rel]:
            href = "%s#cls-%s" % (_src_href_from_rel(rel), c.get("name", ""))
            cls_rows.append(
                '<tr><td><a href="%s">%s</a></td><td><a href="%s"><code>%s</code></a></td>'
                "<td>%s</td><td>%d</td></tr>"
                % (href, html_mod.escape(rel), href, html_mod.escape(c.get("name", "")),
                   html_mod.escape(c.get("superclass", "") or "-"),
                   int(c.get("line", 0))))
    parts = []
    A = parts.append
    A(_snapshot_page_head("快照回放：%s" % (data.get("root") or "")))
    A('<header><span class="brand">\u2b8c 快照回放</span>')
    for name, lbl in sub_links[:-1]:
        A('<a href="%s">%s</a>' % (name, html_mod.escape(lbl)))
    A("</header><main>")
    A("<h1>MATLAB 分析快照回放</h1>")
    A('<div class="muted">由 <code>--from-json --browse</code> 生成，'
      "可直接回放分析结果，无需源码重扫</div>")
    A('<table class="meta-tbl">')
    A("<tr><th>来源快照</th><td>%s</td></tr>"
      % html_mod.escape(data.get("version", "") or "-"))
    A("<tr><th>根目录</th><td><code>%s</code></td></tr>"
      % html_mod.escape(data.get("root", "") or "-"))
    A("<tr><th>生成时间</th><td>%s</td></tr>"
      % html_mod.escape(data.get("generated_at", "") or "-"))
    A("<tr><th>调用图节点</th><td>%d</td></tr>" % len(cg.get("nodes") or []))
    A("<tr><th>入口函数</th><td>%d</td></tr>" % len(cg.get("entries") or []))
    A("</table>")
    A("<h2>统计</h2><div class=\"stats-cards\">")
    A(_snapshot_stat_html([("文件", len(files)), ("函数", n_fn), ("类", n_cls),
                           ("调用边", n_edges), ("解析错误", n_err),
                           ("未初始化", n_uninit), ("类型不匹配", n_mismatch),
                           ("死代码", n_dead), ("契约问题", len(issues))]))
    A("</div>")
    A("<h2>子页面</h2><ul>%s</ul>" % sub_html)
    A("<h2>文件列表（%d）</h2><table><tr><th>文件</th><th>类型</th>"
      "<th>编码</th><th>行数</th><th>函数</th><th>类</th><th>解析错误</th></tr>"
      % len(files))
    A("".join(rows))
    A("</table>")
    A("<h2>函数索引（%d）</h2><table><tr><th>文件</th><th>函数</th>"
      "<th>类型</th><th>行</th><th>签名</th></tr>" % n_fn)
    A("".join(fn_rows))
    A("</table>")
    A("<h2>类索引（%d）</h2><table><tr><th>文件</th><th>类</th>"
      "<th>基类</th><th>行</th></tr>" % n_cls)
    A("".join(cls_rows))
    A("</table></main></body></html>")
    return "".join(parts)


def _snapshot_fn_card(idx, rel, fn):
    """P124：单函数卡片 HTML（快照回放，无源码正文）。"""
    cg = idx["cg"]
    incoming = cg.get("incoming") or {}
    name = fn.get("name", "")
    key = _snapshot_qkey(rel, name)
    parts = []
    A = parts.append
    A('<div class="card" id="fn-%s">' % name)
    A("<h2>%s</h2>" % html_mod.escape(name))
    badges = [fn.get("kind") or "function"]
    if fn.get("variadic"):
        badges.append("可变参数")
    A('<div class="badges">%s</div>'
      % " ".join('<span class="badge">%s</span>' % html_mod.escape(b)
                 for b in badges))
    A('<p class="sig">%s</p>' % html_mod.escape(fn.get("signature") or ""))
    A('<table class="meta-tbl">')
    A("<tr><th>限定名</th><td><code>%s</code></td></tr>"
      % html_mod.escape(fn.get("qualified") or "-"))
    A("<tr><th>定义行</th><td>%d</td></tr>" % int(fn.get("line", 0)))
    inputs = fn.get("inputs") or []
    outputs = fn.get("outputs") or []
    if inputs:
        A("<tr><th>输入</th><td>%s</td></tr>"
          % " ".join("<code>%s</code>" % html_mod.escape(str(i))
                     for i in inputs))
    else:
        A("<tr><th>输入</th><td>-</td></tr>")
    if outputs:
        A("<tr><th>输出</th><td>%s</td></tr>"
          % " ".join("<code>%s</code>" % html_mod.escape(str(o))
                     for o in outputs))
    else:
        A("<tr><th>输出</th><td>-</td></tr>")
    A("<tr><th>调用</th><td>%s</td></tr>"
      % _snapshot_call_html(idx, fn.get("calls") or [], rel))
    A("<tr><th>被调用</th><td>%s</td></tr>"
      % _snapshot_call_html(idx, incoming.get(key) or [], rel))
    A("<tr><th>内置调用</th><td>%s</td></tr>"
      % _snapshot_count_html(fn.get("builtin_calls") or {}))
    A("<tr><th>未解析调用</th><td>%s</td></tr>"
      % _snapshot_count_html(fn.get("external_calls") or {}))
    A("</table>")
    header = fn.get("header") or {}
    desc = header.get("description") or ""
    if desc:
        A("<h3>说明</h3><p>%s</p>" % html_mod.escape(desc))
    in_docs = fn.get("input_docs") or {}
    out_docs = fn.get("output_docs") or {}
    if in_docs or out_docs:
        A("<h3>参数文档</h3><table><tr><th>参数</th><th>方向</th><th>说明</th></tr>")
        for p, d in sorted(in_docs.items()):
            A("<tr><td><code>%s</code></td><td>输入</td><td>%s</td></tr>"
              % (html_mod.escape(str(p)),
                 html_mod.escape(str(d) if d is not None else "")))
        for p, d in sorted(out_docs.items()):
            A("<tr><td><code>%s</code></td><td>输出</td><td>%s</td></tr>"
              % (html_mod.escape(str(p)),
                 html_mod.escape(str(d) if d is not None else "")))
        A("</table>")
    A("</div>")
    return "".join(parts)


def _snapshot_class_card(cls):
    """P124：单类卡片 HTML（快照回放）。"""
    name = cls.get("name", "")
    parts = []
    A = parts.append
    A('<div class="card" id="cls-%s">' % name)
    A("<h2>%s</h2>" % html_mod.escape(name))
    A('<table class="meta-tbl">')
    A("<tr><th>基类</th><td>%s</td></tr>"
      % html_mod.escape(cls.get("superclass") or "-"))
    A("<tr><th>定义行</th><td>%d</td></tr>" % int(cls.get("line", 0)))
    A("</table>")
    for sect, label in (("properties", "属性"), ("events", "事件"),
                        ("enumerations", "枚举")):
        items = cls.get(sect) or []
        if items:
            A("<h3>%s（%d）</h3>" % (label, len(items)))
            A("<ul>%s</ul>"
              % "".join("<li><code>%s</code></li>" % html_mod.escape(str(x))
                        for x in items))
    methods = cls.get("methods") or []
    if methods:
        A("<h3>方法（%d）</h3>" % len(methods))
        A("<ul>%s</ul>"
          % "".join("<li><code>%s</code></li>" % html_mod.escape(str(x))
                    for x in methods))
    A("</div>")
    return "".join(parts)


def _render_snapshot_file_page(idx, mf):
    """P124：单文件回放页——文件卡 + 函数卡 + 类卡（快照不含源码正文）。"""
    rel = mf.get("rel") or ""
    parts = []
    A = parts.append
    A(_snapshot_page_head("快照回放：%s" % rel))
    A('<header><span class="brand">\u2b8c 快照回放</span>'
      '<a href="index.html">\u2190 索引</a></header><main>')
    A('<p class="crumbs"><a href="%s">\u2190 返回索引</a></p>' % _up_to_index(rel))
    A("<h1>%s</h1>" % html_mod.escape(rel))
    A('<div class="muted">快照回放模式：JSON 快照未导出源码正文，'
      "以下为文件级分析结果（函数 / 类卡片）</div>")
    A('<div class="card"><h2>文件信息</h2><table class="meta-tbl">')
    A("<tr><th>类型</th><td>%s</td></tr>"
      % html_mod.escape(mf.get("kind", "") or "-"))
    A("<tr><th>编码</th><td>%s</td></tr>"
      % html_mod.escape(mf.get("encoding", "") or "-"))
    A("<tr><th>行数</th><td>%d</td></tr>" % int(mf.get("lines", 0)))
    A("<tr><th>主函数</th><td>%s</td></tr>"
      % html_mod.escape(str(mf.get("main_function") or "-")))
    globals_ = mf.get("globals") or []
    if globals_:
        A("<tr><th>全局变量</th><td>%s</td></tr>"
          % " ".join("<code>%s</code>" % html_mod.escape(str(g))
                     for g in globals_))
    A("</table>")
    header = mf.get("header") or {}
    if header.get("description"):
        A("<h3>说明</h3><p>%s</p>" % html_mod.escape(header["description"]))
    A("</div>")
    parse_errors = mf.get("parse_errors") or []
    if parse_errors:
        A("<h2>解析错误（%d）</h2>" % len(parse_errors))
        A("<ul>%s</ul>"
          % "".join("<li><code>%s</code></li>" % html_mod.escape(str(e))
                    for e in parse_errors))
    functions = [f for f in (mf.get("functions") or []) if isinstance(f, dict)]
    if functions:
        A("<h2>函数（%d）</h2>" % len(functions))
        for fn in sorted(functions, key=lambda f: int(f.get("line", 0))):
            A(_snapshot_fn_card(idx, rel, fn))
    classes = [c for c in (mf.get("classes") or []) if isinstance(c, dict)]
    if classes:
        A("<h2>类（%d）</h2>" % len(classes))
        for cls in sorted(classes, key=lambda c: int(c.get("line", 0))):
            A(_snapshot_class_card(cls))
    A("</main></body></html>")
    return "".join(parts)


def render_snapshot_browse_site(data, outdir):
    """P124：从 JSON 快照 dict 渲染离线自包含浏览站点（--from-json X --browse OUT）。

    生成内容：index.html 索引页、src/<rel>.html 文件页、metrics/checks/unresolved/
    matlab_lib 子页（快照存在 taint/doc_todos 时附 taint/todo 页），并内嵌
    snapshot.json 归档副本。返回生成的页数。
    """
    _clean_browse_dir(outdir)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    idx = _snapshot_index(data)
    pages = 0
    snap, _notes = _serialize_model(data)
    _write_output(os.path.join(outdir, "snapshot.json"),
                  json.dumps(snap, ensure_ascii=False, indent=2,
                             default=_json_default),
                  "快照归档副本")
    _write_output(os.path.join(outdir, "index.html"),
                  _render_snapshot_index(data, idx), "快照回放索引页")
    pages += 1
    for rel in sorted(idx["file_by_rel"]):
        _write_output(os.path.join(outdir, "src", _page_rel(rel)),
                      _render_snapshot_file_page(idx, idx["file_by_rel"][rel]),
                      "快照回放文件页 %s" % rel)
        pages += 1
    sub_pages = [
        ("metrics.html", "函数风险度量",
         render_metrics_page(_snapshot_metric_rows(data, idx))),
        ("checks.html", "静态检查",
         render_checks_page({
             "uninitialized": _snapshot_attach_file(idx,
                                data.get("uninitialized") or []),
             "type_mismatch": _snapshot_attach_file(idx,
                                data.get("type_mismatch") or []),
             "dead_code": _snapshot_attach_file(idx,
                                data.get("dead_code") or []),
             "suppressed": {"names": 0, "all": 0, "lines": 0},
         })),
        ("unresolved.html", "疑似漏检调用",
         render_unresolved_page(_snapshot_unresolved_rows(data, idx),
                                orphaned=[], dynamic=[], indirect=[], index_like=[])),
        ("matlab_lib.html", "MATLAB 内置库函数",
         render_matlab_lib_page(_snapshot_builtin_items(data))),
    ]
    taint = data.get("taint")
    if isinstance(taint, dict) and (taint.get("flows") or taint.get("stats")):
        sub_pages.append(("taint.html", "污点流分析",
                          render_taint_page(taint, data.get("root") or "")))
    todo = data.get("doc_todos")
    if isinstance(todo, dict) and (todo.get("todos") or todo.get("stats")):
        sub_pages.append(("todo.html", "函数待办清单",
                          render_todo_page(todo, data.get("root") or "")))
    for fname, _lbl, html in sub_pages:
        _write_output(os.path.join(outdir, fname), html, "快照回放子页 %s" % fname)
        pages += 1
    return pages



# 以下辅助函数由 matlabc 持有（被多处渲染复用），放到本模块底部再导入，
# 与 matlabc 的「底部再导出 renderers.snapshot」错开，避免部分初始化循环导入。
from matlabc import (
    _src_href_from_rel,
    _write_output,
    _json_default,
    _page_rel,
    _up_to_index,
    render_checks_page,
    render_taint_page,
    render_todo_page,
    render_matlab_lib_page)
from renderers.metrics import render_metrics_page
from renderers.unresolved import render_unresolved_page
# 度量页/未解析调用页已迁出；快照回放内嵌这两类页面，故从此处借用。
from renderers.metrics import render_metrics_page
from renderers.unresolved import render_unresolved_page
