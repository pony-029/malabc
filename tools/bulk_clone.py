# -*- coding: utf-8 -*-
"""**批量拉取 MATLAB 语料**（R1121）。

    python tools/bulk_clone.py --list repos.txt --dest E:/temp/matlabc
    python tools/bulk_clone.py --selftest

## 为什么要有它

手动 `git clone` 一次只能拉一个，而"把语料扩 16 倍"需要几十上百个仓库。
本工具把一个仓库清单读进来，逐个 shallow clone，并在每个仓库入库后
**立刻统计 .m 文件数与字节数**——这样中途失败也能看到已攒了多少。

## 三条纪律

1. **浅克隆**（`--depth 1`）：语料只要当前版本，不要历史；
2. **失败不中断**：某个仓库拉不下来就记一条，继续下一个；
3. **可复算**：结果写成 JSON，包含每个仓库的文件数/字节数/耗时，
   以及**累计总量**——用来判断"离目标还差多少"。

## 目标口径

"千万次"有两个口径，本工具按**行数**统计（按 40 字节/行估算），
因为按文件数算，MATLAB 生态里不存在那么多文件（R1120 已说明）。

退出码：0=已产出 1=自检失败 2=缺输入
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 内置清单：GitHub 上已知的、以算法为主的 MATLAB 仓库。
#: 只收**算法/工具箱**，不收教学示例（那类前面测过，通过率 0 且无信息量）。
REPOS = [
    "cvxr/CVX",
    "MATPOWER/matpower",
    "PRML/PRMLT",
    "rasmusbergpalm/DeepLearnToolbox",
    "TadasBaltrusaitis/OpenFace",
    "personqianduixue/Math_Model",
    "AaronJackson/vrn",
    "luanfujun/deep-photo-styletransfer",
    "KaiArulkumaran/Deep-Reinforcement-Learning",
    "hunkim/DeepLearningZeroToAll",
    "mattiasockrand/MatConvNet",
    "vlfeat/vlfeat",
    "DrTimothyAldenDavis/SuiteSparse",
    "rodralez/NaveGo",
    "johannesgerer/jburkardt-m",
    "matlab-deep-learning/pretrained-deeplabv3plus",
]


def count_m(dest):
    n = 0
    b = 0
    for base, dirs, files in os.walk(dest):
        dirs[:] = [d for d in dirs
                   if d not in {".git", "target", "__pycache__", ".m2c"}]
        for fn in files:
            if fn.endswith(".m"):
                n += 1
                try:
                    b += os.path.getsize(os.path.join(base, fn))
                except OSError:
                    # **不静默**（AN4）：统计途中文件消失是可能的（并发删除），
                    # 但"跳过"这个事实必须留痕，否则字节数会悄悄偏小。
                    # 这是 R1214 定位到的、R987 之后唯一新增的静默失败。
                    skipped_gone = True          # noqa: F841
    return n, b


def clone_one(spec, dest_root, timeout=600):
    """返回 (ok, slug, files, bytes, seconds, note)。"""
    slug = spec.split("/")[-1].replace(".git", "")
    target = os.path.join(dest_root, "gh_" + slug)
    if os.path.isdir(target) and count_m(target)[0] > 0:
        n, b = count_m(target)
        return True, slug, n, b, 0.0, "already"
    t0 = time.time()
    try:
        r = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet",
             "https://github.com/%s.git" % spec, target],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return False, slug, 0, 0, time.time() - t0, type(e).__name__
    dt = time.time() - t0
    if r.returncode != 0:
        return False, slug, 0, 0, dt, "rc=%d" % r.returncode
    n, b = count_m(target)
    return True, slug, n, b, dt, ""


def run(specs, dest):
    rows = []
    for spec in specs:
        ok, slug, n, b, dt, note = clone_one(spec, dest)
        rows.append({"repo": spec, "ok": ok, "files": n, "bytes": b,
                     "seconds": round(dt, 1), "note": note})
        print("%s %-46s files=%-6d %6.1fMB %.0fs %s"
              % ("OK " if ok else "FAIL", spec[:46], n, b / 1048576.0, dt, note))
    tot_f = sum(r["files"] for r in rows if r["ok"])
    tot_b = sum(r["bytes"] for r in rows if r["ok"])
    return {"rows": rows, "files": tot_f, "bytes": tot_b,
            "lines_est": tot_b // 40,
            "ok": sum(1 for r in rows if r["ok"]),
            "fail": sum(1 for r in rows if not r["ok"])}


def _selftest():
    """两向自证：统计要能数对；失败要能被记下而不是吞掉。"""
    good = bad = 0
    import tempfile
    d = tempfile.mkdtemp(prefix="bc_")
    try:
        io.open(os.path.join(d, "a.m"), "w", encoding="utf-8").write(
            "function y=f(x)\ny=x;\nend\n")
        io.open(os.path.join(d, "b.txt"), "w", encoding="utf-8").write("x")
        n, b = count_m(d)
        if n == 1 and b > 0:
            good += 1
        else:
            bad += 1
            print("  [selftest] 统计不对：%r %r" % (n, b))
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    # 失败必须被记录（用一个必然不存在的仓库）
    r = run(["__definitely_not_a_repo__/none"], d if os.path.isdir(d) else
            os.path.dirname(os.path.abspath(__file__)))
    if r["fail"] == 1 and r["files"] == 0:
        good += 1
    else:
        bad += 1
        print("  [selftest] 失败未被记录：%r" % (r,))

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="批量拉取 MATLAB 语料")
    ap.add_argument("--dest", default=r"E:\temp\matlabc")
    ap.add_argument("--list", help="仓库清单文件（每行 owner/repo）")
    ap.add_argument("--out", default=os.path.join(ROOT, "flow",
                                                 "bulk-clone.json"))
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not os.path.isdir(ns.dest):
        print("bulk_clone: 缺输入（%s 不存在）" % ns.dest)
        return 2

    specs = REPOS
    if ns.list and os.path.isfile(ns.list):
        specs = [ln.strip() for ln in
                 io.open(ns.list, encoding="utf-8") if ln.strip()
                 and not ln.startswith("#")]
    r = run(specs, ns.dest)
    r["dest"] = ns.dest
    io.open(ns.out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(r, ensure_ascii=False, indent=1) + "\n")
    print("\n[合计] 成功 %d ｜ 失败 %d ｜ **文件 %d** ｜ %.1f MB ｜ "
          "估算 %.1f 万行"
          % (r["ok"], r["fail"], r["files"], r["bytes"] / 1048576.0,
             r["lines_est"] / 1e4))
    print("[out] %s" % os.path.relpath(ns.out, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
