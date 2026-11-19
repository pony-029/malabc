# -*- coding: utf-8 -*-
"""**缺口归因**：把未映射语句按"缺口性质"分类，回答"下一刀该切哪"。

    python tools/gap_attrib.py <目录> [-o flow/gap.json]

## 为什么要有它

`unmapped_stats.py` 告诉我"降级率 20.3%"，但不告诉我**剩下的 79.7% 里
哪些能修、哪些修不了**。而这两者的攻关成本差一个数量级：

* **语法缺口**（如 `if (n == 0)` 的括号）—— 改几行解析器就行；
* **运行时缺口**（string / cell / reshape / 外部内置）—— 要新增 C 侧类型与算子。

不分清楚，就会一直挑"看起来简单"的那条去试，而它可能正好是修不了的。

## 分类判据（写死，可复核）

| 类别 | 判据 | 成本 |
|---|---|---|
| `string-switch` | `case '…'` | 需 string 运行时 |
| `string-assign` | 赋值右侧是字符串字面量 | 需 string 运行时 |
| `cell` | 含 `{` / `}` | 需 cell 运行时 |
| `type-predicate` | `isscalar/isvector/isempty/ischar/…` | 有形状可静态折叠，否则需运行时 |
| `builtin-call` | `x = f(...)` 且 f 是已知需运行时的内置（reshape/permute/sort/…） | 需运行时 |
| `index-assign` | `x = x(...)` / 逻辑索引 | 需运行时 |
| `flatten` | 含 `(:)` | 语法 + 运行时 |
| `numeric-switch` | `case <数>` / `case {…}` | **语法可解** |
| `other` | 其余 | 待定 |

退出码：
    0 = 归因完成
    2 = 缺输入（目录不存在或没有 .m）
"""
import argparse
import collections
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))
import mir as M  # noqa: E402

PRED = re.compile(r"\b(isscalar|isvector|ismatrix|isempty|ischar|isnumeric|"
                  r"islogical|isstruct|iscell|issparse|isa|class)\s*\(")
#: 需要 C 侧运行时的内置（纯语法救不了）
RT_BUILTIN = ("reshape", "permute", "ipermute", "sort", "sortrows", "unique",
              "lower", "upper", "tolower", "toupper", "strcmp", "sprintf",
              "num2str", "str2num", "fieldnames", "setfield", "getfield",
              "rows", "columns", "randperm", "pdist2", "accumarray")
CALL1 = re.compile(r"^([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\(")


def classify(t):
    s = t.strip()
    if re.match(r"^case\s+['\"]", s):
        return "string-switch"
    if re.match(r"^case\b", s):
        return "numeric-switch"
    if re.search(r"\{|\}", s):
        return "cell"
    if re.search(r"'[^']*'", s) and "=" in s:
        return "string-assign"
    if PRED.search(s):
        return "type-predicate"
    m = CALL1.match(s)
    if m and m.group(2) in RT_BUILTIN:
        return "builtin-call"
    if re.search(r"\(:\)", s):
        return "flatten"
    if re.match(r"^[A-Za-z_]\w*\s*=\s*[A-Za-z_]\w*\s*\(", s):
        return "index-assign"
    return "other"


#: 每一类"能不能靠语法解决"的结论（写死，供排序用）
COST = {
    "numeric-switch": "语法（低）",
    "flatten": "语法+运行时（中）",
    "type-predicate": "有形状可折叠（中）",
    "string-switch": "需 string 运行时（高）",
    "string-assign": "需 string 运行时（高）",
    "cell": "需 cell 运行时（高）",
    "builtin-call": "需运行时/外部实现（高）",
    "index-assign": "需运行时（高）",
    "other": "待定",
}


def scan(src):
    cat = collections.Counter()
    ex = {}
    for f in sorted(os.listdir(src)):
        if not f.endswith(".m"):
            continue
        try:
            code = io.open(os.path.join(src, f), encoding="utf-8",
                           errors="replace").read()
            txt, _st = M.to_mir(code)
        except Exception:                  # noqa: BLE001
            continue
        for ln in txt.splitlines():
            if not ln.startswith("unmapped:"):
                continue
            t = ln[len("unmapped:"):].strip()
            k = classify(t)
            cat[k] += 1
            ex.setdefault(k, t[:70])
    tot = sum(cat.values())
    return {"source": src, "total": tot,
            "cats": [{"kind": k, "n": v, "pct": round(100.0 * v / tot, 1),
                      "cost": COST.get(k, "待定"), "sample": ex[k]}
                     for k, v in cat.most_common()]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="缺口归因")
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "flow", "gap.json"))
    ns = ap.parse_args(argv)
    if not os.path.isdir(ns.src):
        print("gap_attrib: 缺输入（目录不存在）")
        return 2
    d = scan(ns.src)
    if not d["total"]:
        print("gap_attrib: 缺输入（没有未映射语句）")
        return 2
    io.open(ns.out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, indent=1) + "\n")
    print("[gap] %s ｜ 未映射 %d 条" % (ns.src, d["total"]))
    for c in d["cats"]:
        print("  %5d (%4.1f%%) %-16s %-24s %s"
              % (c["n"], c["pct"], c["kind"], c["cost"], c["sample"]))
    print("[gap] -> %s" % os.path.relpath(ns.out, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
