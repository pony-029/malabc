# -*- coding: utf-8 -*-
"""**语义映射建议器**：读一个 MATLAB 工程，产出「哪些 .m 该合成一个 .c」的 JSON。

    python tools/map_suggest.py <工程目录> -o map.json
    python tools/map_suggest.py <工程目录> --max-files 8 --dry-run

## 它是什么，不是什么

**是**：按"人类会怎么分模块"的语义规则做聚类 ——
目录/包边界（`@sdpvar/`、`+solvers/`）、调用连通性（互相调用的文件属于同一模块）、
命名前缀（`yalmip2*` 是一族）。

**不是**：LLM。它是**确定性规则**，所以：

* 可复跑（同输入同输出）
* 每条建议都带 `why` —— 人能看到"为什么这几个被放在一起"
* 与 `mode:"ai"` 的约定一致：产出 JSON 供人**确认后再用**，不直接改工程

之所以先做规则版：真接了 LLM 也是同样的产出格式（`groups` + `why`），
而规则版**零成本、可对照**——将来换 LLM 时它就是基线。

## 输出

```json
{"version": 1, "mode": "ai",
 "groups": [{"name": "sdpvar", "sources": [...], "why": "同一 MATLAB 包 @sdpvar"}],
 "unmatched": "own",
 "stats": {...}}
```

`groups[].why` 是**给人和 LLM 看的理由**，`map_config.normalize()` 会忽略它
（配置里多一个字段不影响加载）。
"""
import argparse
import io
import json
import os
import re
import sys

FUNC_DEF = re.compile(r"^\s*function\s+(?:\[[^\]]*\]|\w+)?\s*=?\s*(\w+)?", re.M)
CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
KEYWORDS = {"if", "for", "while", "switch", "case", "end", "function", "else",
            "elseif", "otherwise", "return", "break", "continue", "try", "catch"}
#: 目标：一个 .c 不超过这么多源文件（超过就说明"合得太粗"，编译定位会变难）
DEFAULT_MAX_FILES = 12


def _read(p):
    return io.open(p, encoding="utf-8", errors="replace").read()


def _module_key(rel):
    """按目录/包边界给一个"模块键"。MATLAB 的包目录以 `+` 开头，类目录以 `@` 开头。"""
    parts = rel.replace("\\", "/").split("/")
    for seg in parts[:-1]:
        if seg.startswith(("@", "+")):
            return seg.lstrip("@+")
    if len(parts) >= 2:
        return parts[0]
    return "_root"


def scan(root):
    """返回 {文件名: {"rel", "funcs", "calls", "module"}}。"""
    info = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "_m2c")]
        for f in files:
            if not f.endswith(".m"):
                continue
            p = os.path.join(base, f)
            rel = os.path.relpath(p, root).replace("\\", "/")
            txt = _read(p)
            funcs = [m.group(1) for m in FUNC_DEF.finditer(txt) if m.group(1)]
            calls = set(CALL.findall(txt)) - KEYWORDS
            info[f] = {"rel": rel, "funcs": funcs or [f[:-2]],
                       "calls": calls, "module": _module_key(rel)}
    return info


def group(info, max_files=DEFAULT_MAX_FILES):
    """两步聚类：① 按模块键（目录/包）② 同模块内按调用连通性再切分。

    第 ② 步是必要的：一个目录里可能塞了互不相关的几十个文件，
    全合成一个 `.c` 会让"改一个文件"变成"重编整个模块"。
    """
    by_name = {}
    for f, d in info.items():
        for fn in d["funcs"]:
            by_name[fn] = f

    groups = []
    mods = {}
    for f, d in info.items():
        mods.setdefault(d["module"], []).append(f)

    for mod, files in mods.items():
        # union-find：调用关系把文件连起来（只在同一模块内连）
        parent = {f: f for f in files}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for f in files:
            for c in info[f]["calls"]:
                tgt = by_name.get(c)
                if tgt and tgt in parent:      # 只在本模块内连
                    union(f, tgt)

        clusters = {}
        for f in files:
            clusters.setdefault(find(f), []).append(f)

        for _, members in clusters.items():
            members.sort()
            # 太大的簇先按文件名前缀切（`yalmip2cplex` / `yalmip2gurobi` …）
            buckets = []
            if len(members) > max_files:
                pref = {}
                for f in members:
                    m = re.match(r"([A-Za-z]+_?[A-Za-z]*)", f)
                    key = (m.group(1).lower() if m else "_")[:12]
                    pref.setdefault(key, []).append(f)
                for k, v in pref.items():
                    buckets.append((v, "模块 %s 内同前缀 %r（%d 个文件）"
                                    % (mod, k, len(v))))
            else:
                buckets.append((members, "模块 %s 内互相调用连通（%d 个文件）"
                                % (mod, len(members))))

            # **`--max-files` 必须真的生效**（R921）：前缀切完仍可能超限
            # （yalmip 里 `test_global*` 有 82 个文件全部同前缀，切了等于没切）。
            # 超限的桶按文件名顺序**分块**，每块 ≤ max_files ——
            # 分块是"少信息"的做法，但比"一个 .c 装 82 个函数"更可维护，
            # 且理由会写在 `why` 里（人能看到它为什么被拆开）。
            for v, why in buckets:
                if len(v) <= max_files:
                    groups.append({"name": _uniq(v[0], len(groups)),
                                   "sources": v, "why": why})
                    continue
                for start in range(0, len(v), max_files):
                    chunk = v[start:start + max_files]
                    groups.append({
                        "name": _uniq(chunk[0], len(groups)),
                        "sources": chunk,
                        "why": "%s；因超过 max-files=%d，按名序分块（%d/%d）"
                               % (why.split("（")[0], max_files,
                                  start // max_files + 1,
                                  (len(v) + max_files - 1) // max_files)})

    groups.sort(key=lambda g: (-len(g["sources"]), g["name"]))
    return groups


def _uniq(first, idx):
    """组名取第一个文件名（去扩展名），冲突时加序号 —— 重名两组会互相覆盖。"""
    base = re.sub(r"[^\w]", "_", os.path.splitext(os.path.basename(first))[0])
    return base if idx == 0 else "%s_%d" % (base, idx)


def main(argv=None):
    ap = argparse.ArgumentParser(description="按语义规则建议 MATLAB→C 的映射分组")
    ap.add_argument("root", help="MATLAB 工程目录")
    ap.add_argument("-o", "--output", metavar="FILE", help="写到该 JSON（默认打印）")
    ap.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES,
                    help="单个 .c 最多纳多少个源文件（默认 %d）" % DEFAULT_MAX_FILES)
    ap.add_argument("--dry-run", action="store_true", help="只打印摘要，不写文件")
    ns = ap.parse_args(argv)

    if not os.path.isdir(ns.root):
        print("不是目录：%s" % ns.root, file=sys.stderr)
        return 2
    info = scan(ns.root)
    if not info:
        print("该目录下没有 .m 文件", file=sys.stderr)
        return 2

    groups = group(info, ns.max_files)
    covered = sum(len(g["sources"]) for g in groups)
    spec = {
        "version": 1, "mode": "ai", "groups": groups, "unmatched": "own",
        "stats": {"m_files": len(info), "groups": len(groups),
                  "grouped_files": covered,
                  "max_group": max((len(g["sources"]) for g in groups), default=0)},
    }
    print("[suggest] %d 个 .m -> %d 个建议模块（最大 %d 个文件/模块）"
          % (len(info), len(groups), spec["stats"]["max_group"]))
    for g in groups[:12]:
        print("   %-22s %2d 个文件 ｜ %s"
              % (g["name"], len(g["sources"]), g["why"]))
    if len(groups) > 12:
        print("   …共 %d 组" % len(groups))

    if ns.dry_run or not ns.output:
        if not ns.output:
            print(json.dumps(spec, ensure_ascii=False, indent=2))
        return 0
    io.open(ns.output, "w", encoding="utf-8", newline="\n").write(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    print("[suggest] 已写出：%s（**请人工确认后再用于转换**）" % ns.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
