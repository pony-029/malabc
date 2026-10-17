# -*- coding: utf-8 -*-
"""增量重算的**一致性判据**（I2）：增量结果必须与全量逐项相同。

R225 背景：`analyzer.api.analyze(root, prev=..., changed=...)` 早就支持
"复用上次解析"，但一直没人验证它给出的**答案是否相同**。

第一次验证就发现不一致：

    full        : files=13 edges=9
    incremental : files=13 edges=10     ← 多一条边

**更快但答案不同，那不是优化，是错误答案。** 所以这个脚本存在的意义
不是"证明增量对"，而是"在用它之前先证明它对"。

两个容易踩的点（都实测过）：
  - `prev` 期望的是**文件列表**（元素要有 `.rel`），不是 `PipelineResult`；
    传整个结果会 `AttributeError: 'list' object has no attribute 'rel'`
  - `changed` 是**相对路径**集合（如 `a.m`），不是绝对路径

退出码：
    0  = 增量与全量一致
    1  = 不一致（增量还不能用）
    2  = 缺输入
"""
import argparse
import os
import sys

ROOTDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOTDIR)
from analyzer.api import analyze          # noqa: E402

ROW_SIGNATURE = "IP1–IP2"


def sig(res):
    files = []
    for mf in res.files:
        files.append((
            mf.rel,
            tuple((f.name, f.line, f.complexity) for f in (mf.functions or [])),
        ))
    edges = sorted(tuple(e) if not isinstance(e, dict)
                   else (e.get("caller"), e.get("callee"))
                   for e in res.edges)
    return files, edges


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("root", nargs="?", default=os.path.join(ROOTDIR, "tests", "sample_m"))
    ap.add_argument("--changed", default="a.m",
                    help="要标记为变更的相对路径（默认 a.m）")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv or sys.argv[1:])
    if args.help:
        print(__doc__)
        return 0
    if not os.path.isdir(args.root):
        print("check_incremental_parity: 缺输入（%s）" % args.root)
        return 2

    full = analyze(args.root)
    inc = analyze(args.root, prev=full.files, changed={args.changed})

    f1, e1 = sig(full)
    f2, e2 = sig(inc)
    print("full        : files=%d edges=%d" % (len(f1), len(e1)))
    print("incremental : files=%d edges=%d" % (len(f2), len(e2)))

    bad = 0
    if f1 != f2:
        bad += 1
        print("  [FAIL] IP1 files 不一致")
    if e1 != e2:
        bad += 1
        extra = sorted(set(e2) - set(e1))
        missing = sorted(set(e1) - set(e2))
        print("  [FAIL] IP2 edges 不一致（多 %d 条 / 少 %d 条）"
              % (len(extra), len(missing)))
        for e in extra[:5]:
            print("         多出：%r" % (e,))
        for e in missing[:5]:
            print("         缺少：%r" % (e,))

    if bad:
        print("check_incremental_parity: %d 项不一致（增量暂不可用）" % bad)
        return 1
    print("check_incremental_parity: OK（%s：增量与全量逐项相同）" % ROW_SIGNATURE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
