# -*- coding: utf-8 -*-
"""SARIF 2.1.0 导出与增量差异报告（从 matlabc.py 迁出）。

承载静态检查告警→SARIF JSON 与 PR 差异 Markdown；规则表与指纹相关函数
（_SARIF_RULES / _sarif_result_fp / _sarif_fp_detail）由 matlabc 持有并在底部导入。
"""
import json as _json


def render_sarif(checks, root, base_fps=None, return_stats=False):
    """C3：导出 SARIF（Static Analysis Results Interchange Format）2.1.0。

    把静态检查告警（未初始化/死代码/类型不一致/形状不匹配）转成 SARIF，
    可直接接入 GitHub/GitLab 代码扫描面板。checks 来自 _collect_checks。

    P84 增量模式：传入 base_fps（基线指纹集合，见 _load_sarif_fingerprints）
    时，results 只保留「相对基线新增」的告警；return_stats=True 时额外返回
    {"added": [...], "fixed": [...]} 差异明细，供 --sarif-diff PR 报告使用。
    无基线时 stats 为空列表（不启用差异计算）。"""
    import json as _json
    rules = []
    results = []

    def _loc(file, line):
        return {"physicalLocation": {
            "artifactLocation": {"uri": file},
            "region": {"startLine": line},
        }}

    for rule_id, short_desc, level in _mL._SARIF_RULES:
        rules.append({"id": rule_id, "shortDescription": {"text": short_desc},
                      "defaultConfiguration": {"level": level}})

    for r in checks.get("uninitialized", []):
        results.append({
            "ruleId": "uninitialized", "level": "warning",
            "message": {"text": "变量 %s 在函数 %s 中%s" % (r["name"], r["func"], r.get("reason", "未初始化"))},
            "properties": {"confidence": r.get("confidence", "low")},   # P147：置信度
            "locations": [_loc(r.get("file", ""), r["line"])],
        })
    for r in checks.get("dead_code", []):
        results.append({
            "ruleId": "dead_code", "level": "note",
            "message": {"text": "%s" % r.get("reason", "死代码")},
            "locations": [_loc(r.get("file", ""), r["line"])],
        })
    for r in checks.get("type_mismatch", []):
        results.append({
            "ruleId": "type_mismatch", "level": "warning",
            "message": {"text": "变量 %s 类型从 %s 变为 %s" % (r["name"], r["from_type"], r["to_type"])},
            "locations": [_loc(r.get("file", ""), r["line"])],
        })
    for r in checks.get("tainted_sink", []):
        if r.get("var"):
            # P91：变量级指纹——精确到 (uri, line, var, sink, paramIndex)
            res = {
                "ruleId": "tainted_sink", "level": "warning",
                "message": {"text": "污点变量 %s 在函数 %s 中流入 %s 第 %d 实参（%s），"
                            "传播级别 %d"
                            % (r["var"], r.get("func", ""),
                               r.get("sink_name", "?"),
                               r.get("param_index", 0) + 1,
                               "、".join(r.get("sinks", [])),
                               r.get("level", 1))},
                "locations": [_loc(r.get("file", ""), r["line"])],
                "properties": {"taintVar": r["var"],
                               "sinkName": r.get("sink_name", ""),
                               "paramIndex": r.get("param_index", 0)},
            }
        else:
            res = {
                "ruleId": "tainted_sink", "level": "warning",
                "message": {"text": "污点数据在函数 %s 中流入危险输出点（%s），传播级别 %d"
                            % (r.get("func", ""), "、".join(r.get("sinks", [])),
                               r.get("level", 1))},
                "locations": [_loc(r.get("file", ""), r["line"])],
            }
        results.append(res)
    # P90：C 静态启发式检查（未用 static / 缺头文件卫士 / 参数过多 / 缺注释）
    for r in checks.get("c_heuristics", []):
        results.append({
            "ruleId": "c_heuristics", "level": r.get("level", "note"),
            "message": {"text": "%s" % r.get("msg", "C 启发式检查")},
            "locations": [_loc(r.get("file", ""), r["line"])],
        })
    # P93：Python / JavaScript 静态启发式检查（未用 import / 隐式全局等）
    for _rk in ("py_heuristics", "js_heuristics"):
        for r in checks.get(_rk, []):
            results.append({
                "ruleId": _rk, "level": r.get("level", "note"),
                "message": {"text": "%s" % r.get("msg", "启发式检查")},
                "locations": [_loc(r.get("file", ""), r["line"])],
            })

    stats = {"added": [], "fixed": []}
    if base_fps is not None:
        current = set()
        added_results = []
        for r in results:
            fp = _mL._sarif_result_fp(r)
            current.add(fp)
            if fp not in base_fps:
                added_results.append(r)
        stats["added"] = [_mL._sarif_fp_detail(_mL._sarif_result_fp(r)) for r in added_results]
        stats["fixed"] = [_mL._sarif_fp_detail(fp) for fp in sorted(base_fps - current)]
        results = added_results

    sarif = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {"driver": {"name": "matlabc",
                                "version": _mL.VERSION, "rules": rules}},
            "results": results,
        }],
    }
    text = _json.dumps(sarif, ensure_ascii=False, indent=2)
    if return_stats:
        return text, stats
    return text


def render_sarif_diff_md(stats, base_path, root):
    """P84：把增量差异统计（render_sarif return_stats 的结果）渲染成 Markdown
    PR 差异报告——新增告警 / 已修复告警明细表，供 CI 评论或人工审查使用。"""
    added = stats.get("added", []) or []
    fixed = stats.get("fixed", []) or []
    lines = []
    A = lines.append
    A("# SARIF 增量差异报告")
    A("")
    A("- 基线 SARIF：`%s`" % base_path)
    A("- 新增告警：**%d** 条" % len(added))
    A("- 已修复告警：**%d** 条" % len(fixed))
    A("")
    A("## 新增告警（%d 条）" % len(added))
    A("")
    A("| 文件 | 行 | 规则 | 消息 |")
    A("| --- | --- | --- | --- |")
    if not added:
        A("| _（无）_ | | | |")
    for d in added:
        A("| `%s` | %s | `%s` | %s |"
          % (d.get("uri", ""), d.get("line"), d.get("ruleId"), d.get("message", "")))
    A("")
    A("## 已修复告警（%d 条）" % len(fixed))
    A("")
    A("| 文件 | 行 | 规则 | 消息 |")
    A("| --- | --- | --- | --- |")
    if not fixed:
        A("| _（无）_ | | | |")
    for d in fixed:
        A("| `%s` | %s | `%s` | %s |"
          % (d.get("uri", ""), d.get("line"), d.get("ruleId"), d.get("message", "")))
    A("")
    A("_由 matlabc v%s 生成。_"
      % (_mL.VERSION))
    return "\n".join(lines)






# ---------------------------------------------------------------------------
# 统一分析数据层（供 --browse 与 --html 共用）

# R52：以下名称仍由 matlabc 持有，但不再 `from matlabc import` —— 那是 import 期
# 回边（matlabc 底部又再导出 renderers.sarif）。改为惰性代理，见 renderers/_late.py。
from renderers._late import late as _mL
