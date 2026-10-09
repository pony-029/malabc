#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P207-4/P209-5: 合并多个 SARIF 2.1.0 文件为单个报告（兼容 Python 3.6.5）。

用法:
    python merge_sarif.py <输入目录或文件...> <输出文件.sarif> [--summary 质量概览.md]
    python merge_sarif.py a.sarif b.sarif merged.sarif --summary overview.md

说明:
    - 读取每个输入的 SARIF（标准 2.1.0），取首个 tool/driver 作为主 driver；
    - 将所有 runs[].results 汇聚到主 run 下（去重：同 ruleId+同 location 视为重复）；
    - 保留并合并 artifacts（文件清单），避免 code scanning 找不到源文件；
    - P209-5：若指定 --summary，额外输出「质量概览」Markdown（按 ruleId 聚合计数 +
      严重度排序 error>warning>note），并写入合并 SARIF 的 run.properties 供后续消费。

退出码：0 = 合并成功且输出已落盘；1 = 输入里找不到任何 SARIF 文件；2 = 用法错误（参数不足 / --summary 缺路径）

  为什么要把退出码写在这里（R39/C''9）：这个脚本是被**直接复制进用户 CI** 的示例。
  用户会在流水线里按退出码分支；脚本一旦在退出码上说谎，用户的流水线会长期静默
  失效 —— 而这类谎言除了本文件自己的帮助正文，没有任何东西看得见。
  本仓的退出码契约（tools/check_help_contract.py::CI_PY_EXIT_CONTRACT）就是盯它的。
"""
import sys
import os
import json
import glob


_SEV_ORDER = {"error": 0, "warning": 1, "note": 2, "none": 3}


def _sev(r):
    lv = (r.get("level") or "warning").lower()
    return lv if lv in _SEV_ORDER else "warning"


def build_summary(results):
    """P209-5: 按 ruleId 聚合计数，并按严重度（error>warning>note）排序返回列表。"""
    agg = {}
    for r in results:
        rid = r.get("ruleId") or "unknown"
        d = agg.setdefault(rid, {"ruleId": rid, "error": 0, "warning": 0, "note": 0, "total": 0})
        d[_sev(r)] = d.get(_sev(r), 0) + 1
        d["total"] += 1
    rows = list(agg.values())
    rows.sort(key=lambda x: (_SEV_ORDER.get(_sev_first(x), 9), -x["total"], x["ruleId"]))
    return rows


def _sev_first(d):
    for s in ("error", "warning", "note"):
        if d.get(s):
            return s
    return "warning"


def render_summary_md(rows, n_total, src_count):
    """P209-5: 渲染质量概览 Markdown 段落。"""
    lines = []
    lines.append("# 静态分析质量概览（SARIF 合并）\n")
    lines.append("- 合并来源 SARIF 数：%d" % src_count)
    lines.append("- 合并后结果总数：%d\n" % n_total)
    lines.append("| 规则 | error | warning | note | 合计 |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for r in rows:
        lines.append("| %s | %d | %d | %d | %d |" %
                      (r["ruleId"], r["error"], r["warning"], r["note"], r["total"]))
    lines.append("")
    lines.append("> 排序规则：error 优先于 warning 优先于 note。")
    return "\n".join(lines)



def _iter_sarif_paths(inputs):
    paths = []
    for it in inputs:
        if os.path.isdir(it):
            paths.extend(sorted(glob.glob(os.path.join(it, "**", "*.sarif"), recursive=True)))
        elif os.path.isfile(it):
            paths.append(it)
        else:
            # 可能是目录名前缀（github artifacts 解压后为 _scan_parts/sarif-xxx/xxx.sarif）
            paths.extend(sorted(glob.glob(os.path.join(it, "**", "*.sarif"), recursive=True)))
    # 去重保序
    seen = set()
    out = []
    for p in paths:
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.add(ap)
            out.append(p)
    return out


def _result_key(r):
    locs = r.get("locations") or []
    loc = locs[0] if locs else {}
    pl = loc.get("physicalLocation") or {}
    uri = (pl.get("artifactLocation") or {}).get("uri", "")
    region = pl.get("region") or {}
    return (r.get("ruleId"), uri, region.get("startLine"), r.get("message", {}).get("text", ""))


def main(argv):
    if len(argv) < 3:
        sys.stderr.write("usage: merge_sarif.py <input...> <output.sarif> [--summary overview.md]\n")
        return 2
    inputs = argv[1:-1]
    out_path = argv[-1]
    summary_path = None
    if "--summary" in inputs:
        _idx = inputs.index("--summary")
        if _idx + 1 < len(inputs):
            summary_path = inputs[_idx + 1]
            del inputs[_idx:_idx + 2]
        else:
            sys.stderr.write("--summary requires a path\n")
            return 2

    sarif_paths = _iter_sarif_paths(inputs)
    if not sarif_paths:
        sys.stderr.write("no SARIF files found\n")
        return 1

    merged = None
    seen_keys = set()
    merged_artifacts = {}

    for sp in sarif_paths:
        with open(sp, "r", encoding="utf-8") as f:
            data = json.load(f)
        runs = data.get("runs") or []
        if not runs:
            continue
        run = runs[0]
        if merged is None:
            # 以首个文件为骨架
            merged = {
                "version": data.get("version", "2.1.0"),
                "$schema": data.get("$schema", "https://json.schemastore.org/sarif-2.1.0.json"),
                "runs": [{"tool": run.get("tool", {}), "results": [],
                           "artifacts": []}],
            }
        results = run.get("results") or []
        for r in results:
            k = _result_key(r)
            if k in seen_keys:
                continue
            seen_keys.add(k)
            merged["runs"][0]["results"].append(r)
        # 合并 artifacts
        for art in (run.get("artifacts") or []):
            aidx = art.get("index")
            uri = (art.get("location") or {}).get("uri", "")
            if uri and uri not in merged_artifacts:
                merged_artifacts[uri] = art
                if aidx is not None:
                    art["index"] = len(merged["runs"][0]["artifacts"])
                merged["runs"][0]["artifacts"].append(art)

    if merged is None:
        merged = {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "matlabc"}},
                                                 "results": [], "artifacts": []}]}

    # P209-5：在 run.properties 写入按 ruleId 聚合的严重度统计，供后续消费/CI 展示
    _results = merged["runs"][0]["results"]
    _summary_rows = build_summary(_results)
    merged["runs"][0]["properties"] = {
        "summary": {
            "total": len(_results),
            "by_rule": [{"ruleId": r["ruleId"], "error": r["error"],
                          "warning": r["warning"], "note": r["note"],
                          "total": r["total"]} for r in _summary_rows],
        }
    }
    if summary_path:
        _md = render_summary_md(_summary_rows, len(_results), len(sarif_paths))
        try:
            with open(summary_path, "w", encoding="utf-8") as sf:
                sf.write(_md)
            sys.stderr.write("wrote summary -> %s\n" % summary_path)
        except Exception as e:
            sys.stderr.write("warning: failed to write summary: %s\n" % e)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    n = len(_results)
    sys.stderr.write("merged %d results from %d files -> %s\n" % (n, len(sarif_paths), out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
