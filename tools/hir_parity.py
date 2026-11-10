# -*- coding: utf-8 -*-
"""**逐函数对拍**：默认路径 vs `--hir-emit`，三项必须全等。

## 为什么要对拍，而不是看总量

总量相等（96 op / 165 src）只说明**总数**一样，不排除"这个函数少一条、那个多一条"。
而切换默认是全量行为变更 —— 一个函数的行号错位，就会让某人看到的诊断指向错误行。

三项：
1. **算子多重集**：同一函数，两条路径产出的 `OP-*` 集合必须相同；
2. **行号集合**：`# src:` 的取值集合必须相同（同集合，不要求同顺序 —— 折树会改顺序）；
3. **数值**：用 Rust VM 跑两条路径的 MIR，位模式必须相同（可选，`--values`）。

用法：
    python tools/hir_parity.py [语料目录] [--values]
"""
import argparse
import collections
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
M2C = os.path.join(ROOT, "rust", "m2c", "target", "release",
                   "m2c.exe" if os.name == "nt" else "m2c")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"
CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")


def _run(cmd, timeout=300):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _gen(extra, name):
    out = os.path.join(WORK, name)
    r = _run([sys.executable, MIR_PY, CORPUS] + extra + ["-o", out])
    if r.returncode != 0:
        raise SystemExit("生成失败：%s" % r.stdout.decode("utf-8", "replace")[-300:])
    return out


def _split(text):
    """按 `func:` 切块 → {name: (ops, srcs)}。"""
    blocks, cur, buf = {}, None, []
    for ln in text.split("\n"):
        s = ln.strip()
        if s.startswith("func:"):
            if cur:
                blocks[cur] = buf
            cur, buf = s[5:].strip(), []
            continue
        if cur is None:
            continue
        buf.append(s)
    if cur:
        blocks[cur] = buf
    out = {}
    for name, lines in blocks.items():
        ops = [l.split(":")[1] for l in lines if l.startswith("op:")]
        srcs = [l.split(":", 1)[1].strip() for l in lines if l.startswith("# src:")]
        out[name] = (ops, srcs, lines)
    return out


def _vm(mir_path):
    r = _run([M2C, "run", "--mir", mir_path], 180)
    return r.stdout.decode("utf-8", "replace").strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description="默认 vs hir-emit 逐函数对拍")
    ap.add_argument("corpus", nargs="?", default=CORPUS)
    ap.add_argument("--values", action="store_true", help="额外比数值（起 VM）")
    a = ap.parse_args(argv)

    # 基准路径必须**显式**关掉 HIR 产出：默认已改为 hir-emit，
    # 不显式关的话两边是同一条路，对拍恒成立（假绿）。
    base = _gen(["--no-hir-emit"], "parity_base.mir")
    hem = _gen(["--hir-emit"], "parity_he.mir")
    B = _split(io.open(base, encoding="utf-8").read())
    H = _split(io.open(hem, encoding="utf-8").read())

    only_b = sorted(set(B) - set(H))
    only_h = sorted(set(H) - set(B))
    bad = []
    for name in sorted(set(B) & set(H)):
        ob, sb, _ = B[name]
        oh, sh, _ = H[name]
        if collections.Counter(ob) != collections.Counter(oh):
            bad.append((name, "算子不同", "%d vs %d" % (len(ob), len(oh))))
        elif collections.Counter(sb) != collections.Counter(sh):
            bad.append((name, "行号不同", "%d vs %d" % (len(sb), len(sh))))

    print("函数数：默认 %d ｜ hir-emit %d ｜ 交集 %d"
          % (len(B), len(H), len(set(B) & set(H))))
    if only_b:
        print("只在默认：%s" % ", ".join(only_b[:5]))
    if only_h:
        print("只在 hir-emit：%s" % ", ".join(only_h[:5]))
    print("差异：%d 个函数" % len(bad))
    for n, why, detail in bad[:8]:
        print("   ✗ %-16s %s（%s）" % (n, why, detail))

    val_diff = []
    if a.values and not bad and os.path.isfile(M2C):
        vb, vh = _vm(base), _vm(hem)
        if vb != vh:
            lb, lh = vb.splitlines(), vh.splitlines()
            for x, y in zip(lb, lh):
                if x != y:
                    val_diff.append((x, y))
            print("数值差异行：%d（前 3：%r）" % (len(val_diff), val_diff[:3]))
        else:
            print("数值：两条路径完全一致")

    ok = not bad and not only_b and not only_h and not val_diff
    print("\nhir_parity: %s" % ("OK（逐函数三项全等）" if ok
                                else "有差异（%d）" % (len(bad) + len(val_diff))))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
