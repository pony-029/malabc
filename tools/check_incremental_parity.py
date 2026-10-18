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
import io
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


def _edge_cases(root):
    """单文件改动**之外**的三件事：新增文件、删除文件、多文件同时改。

    R269：原来的扫描只把「某一个已存在的文件」标记为 changed。
    而删除文件时增量会留下一条指向幽灵的边：

        ('a.m:c', 'd.m:d', True)      ← d.m 已经不存在了

    因为 `a.m` 没有重解析，它 `call_sites` 里仍存着已删文件的函数对象，
    而全量会重解析 `a.m`、在那里解析不到 `d`。

    这条判据就是那次发现变来的：**每个场景都与一次全新的全量分析逐项比**。
    返回 `(场景名, 是否一致)` 列表。
    """
    import shutil
    import tempfile

    def add_file(work):
        with io.open(os.path.join(work, "zz_new.m"), "w",
                     encoding="utf-8", newline="") as fh:
            fh.write(u"function r = zz_new(a)\nr = a + 1;\nend\n")

    def del_file(work):
        p = os.path.join(work, "d.m")
        if os.path.exists(p):
            os.remove(p)

    def two_files(work):
        for name, fn in (("a.m", "added"), ("b.m", "b_extra")):
            with io.open(os.path.join(work, name), "a",
                         encoding="utf-8", newline="") as fh:
                fh.write(u"\nfunction w = %s(a)\nw = a;\nend\n" % fn)

    cases = [("新增文件", add_file, {"zz_new.m"}),
             ("删除文件", del_file, set()),
             ("两文件同时改", two_files, {"a.m", "b.m"})]

    out = []
    for label, mutate, changed in cases:
        work = tempfile.mkdtemp(prefix="incr_edge_")
        try:
            copy_root = os.path.join(work, "corpus")
            shutil.copytree(root, copy_root)
            junk = os.path.join(copy_root, ".matlabc_lsp_cache.json")
            if os.path.exists(junk):
                os.remove(junk)
            base = analyze(copy_root)          # 变更前（prev 的来源）
            mutate(copy_root)
            inc = analyze(copy_root, prev=base.files, changed=changed)
            full = analyze(copy_root)          # 变更后（真值）
            f1, e1 = sig(full)
            f2, e2 = sig(inc)
            out.append((label, f1 == f2 and e1 == e2,
                        sorted(set(e2) - set(e1))[:3],
                        sorted(set(e1) - set(e2))[:3]))
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return out


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

    # 再加三件「单文件之外」的事：新增 / 删除 / 多文件同时改。
    # 删除那条曾经红过 —— 见 `_edge_cases` 的说明。
    edge_bad = 0
    for label, ok, extra, missing in _edge_cases(args.root):
        if ok:
            print("  [OK  ] 边缘：%s" % label)
            continue
        edge_bad += 1
        print("  [FAIL] 边缘：%s 与全量不一致" % label)
        for e in extra:
            print("         多出：%r" % (e,))
        for e in missing:
            print("         缺少：%r" % (e,))

    if bad or edge_bad:
        print("check_incremental_parity: %d 个场景不一致（增量暂不可用）"
              % (bad + edge_bad))
        return 1
    print("check_incremental_parity: OK（%s：%d 个文件场景 + 3 个边缘场景，"
          "增量与全量逐项相同）" % (ROW_SIGNATURE, len(targets)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
