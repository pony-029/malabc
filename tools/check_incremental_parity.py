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


def _selftest():
    """IP1/IP2 两向自证：**相同结果判一致、裸名字判不一致**。

    不跑真分析 —— 判据的对象是「两份结果怎么比」，给它两个替身就够。
    真正昂贵的逐文件扫描留给正式运行，自证必须是毫秒级，
    否则 `check_all` 会被它拖慢。
    """
    class _F(object):
        def __init__(self, rel, fns):
            self.rel = rel
            self.functions = fns

    class _FN(object):
        def __init__(self, name):
            self.name = name
            self.line = 1
            self.complexity = 0

    class _R(object):
        def __init__(self, edges):
            self.files = [_F("a.m", [_FN("a")])]
            self.edges = edges

    stat = {"bad": 0, "good": 0}

    def chk(cond, name):
        if cond:
            stat["good"] += 1
        else:
            stat["bad"] += 1
            print("  [FAIL] %s" % name)

    qual = _R([("a.m:a", "b.m:b")])
    same = _R([("a.m:a", "b.m:b")])
    bare = _R([("a.m:a", "b")])          # R264 的 bug：被调方名字丢了文件前缀
    chk(sig(qual) == sig(same), "IP1 相同结果 → 一致")
    chk(sig(qual) != sig(bare), "IP2 裸名字 vs 限定名 → 不一致")

    print('SELFTEST COUNTS {"bad": %d, "good": %d}'
          % (stat["bad"], stat["good"]))
    return 0 if stat["bad"] == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("root", nargs="?", default=os.path.join(ROOTDIR, "tests", "sample_m"))
    ap.add_argument("--changed", default=None,
                    help="只测这一个文件（默认**逐个文件各测一次**）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--help", "-h", action="store_true")
    args, _ = ap.parse_known_args(argv or sys.argv[1:])
    if args.help:
        print(__doc__)
        return 0
    if args.selftest:
        return _selftest()
    if not os.path.isdir(args.root):
        print("check_incremental_parity: 缺输入（%s）" % args.root)
        return 2

    full = analyze(args.root)
    f1, e1 = sig(full)
    print("full        : files=%d edges=%d" % (len(f1), len(e1)))

    # **逐个文件各测一次**（R264）。只测一个文件是不够的：
    # 这一轮的 bug 是「被**调方**所在文件被重新解析」时才暴露 ——
    # 重解析产生新对象，而其它文件里存着旧对象，标签就退化成裸名字。
    # 换个文件当 `changed`，覆盖的组合完全不同。
    targets = ([args.changed] if args.changed
               else [mf.rel for mf in full.files])
    if not targets:
        print("check_incremental_parity: 语料里没有文件（缺输入 → 红）")
        return 2

    bad = 0
    for ch in targets:
        inc = analyze(args.root, prev=full.files, changed={ch})
        f2, e2 = sig(inc)
        if f1 == f2 and e1 == e2:
            continue
        bad += 1
        print("  [FAIL] 变更 %s 后与全量不一致（files %s / edges %s）"
              % (ch, "同" if f1 == f2 else "异", "同" if e1 == e2 else "异"))
        if f1 != f2:
            print("         IP1 files 不一致")
        if e1 != e2:
            extra = sorted(set(e2) - set(e1))
            missing = sorted(set(e1) - set(e2))
            print("         IP2 edges 不一致（多 %d / 少 %d）"
                  % (len(extra), len(missing)))
            for e in extra[:3]:
                print("           多出：%r" % (e,))
            for e in missing[:3]:
                print("           缺少：%r" % (e,))

    print("scenarios   : %d（每个文件各一次）" % len(targets))
    if bad:
        print("check_incremental_parity: %d 个场景不一致（增量暂不可用）" % bad)
        return 1
    print("check_incremental_parity: OK（%s：%d 个场景，增量与全量逐项相同）"
          % (ROW_SIGNATURE, len(targets)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
