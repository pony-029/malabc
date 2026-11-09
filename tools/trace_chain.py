# -*- coding: utf-8 -*-
"""校验追踪链的**完整性**：每个 `in` 都必须能追溯到更早某个 `out`。

## 这条判据防什么

逐步追踪最容易被写坏的方式，不是"少记一步"，而是**记了一步却不接上**：
某步的 `in` 明明来自上一步，但摘要对不上（占位、写错、或中间换了产物）。
那种情况下列表看起来完整、每步都 ok，**唯独链路是断的**。

R735 实测就抓到一次：`S9.in` 是空串的 sha（`e3b0c442…`）—— 一眼看不出，
跑这条判据立刻暴露。

用法：
    python tools/trace_chain.py [目录]      # 0=全通 1=有断链 2=缺输入
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACES = os.path.join(ROOT, "flow", "traces")


def check(rows):
    """返回 [(step, in, 原因)]；空列表 = 链路完整。"""
    seen = set()
    breaks = []
    for r in rows:
        i = str(r.get("in") or "")
        o = str(r.get("out") or "")
        if i and i != "-" and i not in seen:
            breaks.append((r.get("step"), i[:12], "该摘要没有更早的产出"))
        if o and o != "-":
            seen.add(o)
    return breaks


def main(argv=None):
    args = argv or sys.argv[1:]
    d = args[0] if args else TRACES
    if not os.path.isdir(d):
        print("找不到追踪目录：%s" % d)
        return 2
    files = sorted(f for f in os.listdir(d) if f.endswith(".jsonl"))
    if not files:
        print("目录里没有 .jsonl：%s" % d)
        return 2

    total_bad = 0
    for f in files:
        rows = [json.loads(l) for l in
                io.open(os.path.join(d, f), encoding="utf-8") if l.strip()]
        bad = check(rows)
        total_bad += len(bad)
        print("%-16s 步 %2d ｜ 断链 %d%s"
              % (f[:-6], len(rows), len(bad),
                 "" if not bad else "  " + ", ".join(
                     "%s:%s(%s)" % (s, dg, why) for s, dg, why in bad[:3])))
    print()
    if total_bad:
        print("trace_chain: %d 处断链" % total_bad)
        return 1
    print("trace_chain: OK（%d 条链，全部可追溯）" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
