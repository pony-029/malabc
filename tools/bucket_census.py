# -*- coding: utf-8 -*-
"""**桶构成普查**：任何"X 的主因是 Y"的结论，必须先跑这个。

## 为什么会有这个工具

同一个错误在本项目里出现过三次：

| 轮次 | 我的结论 | 采样后的真相 |
|---|---|---|
| R641 | `strlit` 985 条 = 可丢弃的输出语句 | 主体是 `isa(x,'char')` 类型判断 |
| R646 | `slice2d` 369 条 = 形状未知的二维下标 | 真下标只占 0.2%，多数是 `ones(2,3)` |
| R672 | `cond` 822 条的主因是 `&&` | `&&` 只占 165，主因是"条件里嵌调用" 513 |

三次都是**没打开桶看构成**就写结论，然后按结论排期。所以把这一步做成命令，
让"写结论"必须经过它。

## 用法

    python tools/bucket_census.py <mir> <桶名> [--top 12] [--samples 3]

输出：该桶里每条语句的**形态标签**分布 + 每类的前几条原文。
标签按**形态**命名（`has_and` / `dot_field` / `call_in_cond`），
不是按语义命名 —— 语义命名会让人按名字行动而不看样本。
"""
import argparse
import collections
import io
import os
import re
import sys

#: 形态标签：**只看文本特征**，不猜含义。名字即判据。
RULES = (
    ("has_andand", lambda t: "&&" in t),
    ("has_oror", lambda t: "||" in t),
    ("has_amp", lambda t: bool(re.search(r"[^&]&[^&]", t))),
    ("has_dot_field", lambda t: bool(re.search(r"[A-Za-z_]\w*\.\w+", t))),
    ("has_bracket", lambda t: "[" in t or "]" in t),
    ("has_brace", lambda t: "{" in t or "}" in t),
    ("has_string", lambda t: "'" in t),
    ("has_colon", lambda t: ":" in t),
    ("has_call", lambda t: bool(re.search(r"[A-Za-z_]\w*\s*\(", t))),
    ("has_paren_comma", lambda t: ("(" in t and "," in t)),
)


def label(text):
    hits = [name for name, fn in RULES if fn(text)]
    return "+".join(hits) if hits else "plain"


def census(mir_path, bucket, top=12, nsamples=3):
    counts = collections.Counter()
    samples = collections.defaultdict(list)
    prev = ""
    total = 0
    for ln in io.open(mir_path, encoding="utf-8", errors="replace"):
        ln = ln.rstrip("\n")
        if ln.startswith("# why:"):
            prev = ln[6:].strip()
        elif ln.startswith("unmapped:"):
            if prev == bucket:
                t = ln[9:].strip()
                k = label(t)
                counts[k] += 1
                total += 1
                if len(samples[k]) < nsamples:
                    samples[k].append(t[:76])
            prev = ""
    return total, counts, samples


def main():
    ap = argparse.ArgumentParser(description="桶构成普查（写结论前置）")
    ap.add_argument("mir")
    ap.add_argument("bucket")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--samples", type=int, default=3)
    a = ap.parse_args()

    if not os.path.isfile(a.mir):
        print("找不到 MIR：%s" % a.mir)
        print("先生成：python translate/mir.py <目录> --recursive -o %s" % a.mir)
        return 2

    total, counts, samples = census(a.mir, a.bucket, a.top, a.samples)
    if total == 0:
        print("桶 `%s` 在该 MIR 里没有条目（桶名拼错？先列可用桶）" % a.bucket)
        return 1

    print("桶 `%s` 共 %d 条，按**形态**分布：" % (a.bucket, total))
    for k, v in counts.most_common(a.top):
        print("  %-26s %5d  (%4.1f%%)" % (k, v, 100.0 * v / total))
        for s in samples[k]:
            print("        " + s)
    print("\n**下一步写结论时，请引用上面的分布，而不是凭印象挑第一个。**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
