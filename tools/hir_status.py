# -*- coding: utf-8 -*-
"""产出 `flow/hir_status.json`：HIR 在链路上的**当前真实状态**。

## 为什么要有这个文件

`接管 57/57`、`hir-emit 58/58` 这些数字此前只出现在某次运行输出和总结里 ——
**图与页面上没有它们**，于是"图说 HIR 在链上"仍然只是一句设计主张。

这个工具跑一次真实流程，把数字写成 JSON；`flow_steps.py` 读它渲染到 index。
数字因此**不可手写**，只能来自运行。

用法：
    python tools/hir_status.py            # 写 flow/hir_status.json
    python tools/hir_status.py --check     # 校验 json 与当前跑出来的一致（CI 用）
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIR_PY = os.path.join(ROOT, "translate", "mir.py")
CORPUS = os.path.join(ROOT, "translate", "examples", "numeric")
OUT = os.path.join(ROOT, "flow", "hir_status.json")
WORK = os.environ.get("M2C_TMP") or r"E:\temp\matlabc"


def _run(cmd, timeout=300):
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def measure():
    """跑 `mir.py --via-hir`，解析接管率与恒等率。"""
    tmp = os.path.join(WORK, "hir_status.mir")
    r = _run([sys.executable, MIR_PY, CORPUS, "--via-hir", "-o", tmp])
    out = r.stdout.decode("utf-8", "replace")
    m = re.search(r"\[hir\] 接管 (\d+)/(\d+)（恒等 (\d+)）", out)
    if not m:
        return None
    mapped, total, same = (int(m.group(i)) for i in (1, 2, 3))
    return {
        "via_hir_rc": r.returncode,
        "mapped": mapped,
        "total": total,
        "identical": same,
        "participation": round(100.0 * mapped / max(1, total), 1),
        "identical_rate": round(100.0 * same / max(1, total), 1),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="HIR 链路状态")
    ap.add_argument("--check", action="store_true", help="校验 json 是否仍与实跑一致")
    a = ap.parse_args(argv)

    cur = measure()
    if cur is None:
        print("拿不到 [hir] 汇总行 —— mir.py 的输出变了？")
        return 1

    if a.check:
        if not os.path.isfile(OUT):
            print("缺 flow/hir_status.json（先跑一次不带 --check 的）")
            return 1
        old = json.load(io.open(OUT, encoding="utf-8"))
        keys = ("mapped", "total", "identical")
        if all(old.get(k) == cur.get(k) for k in keys):
            print("hir_status: OK（接管 %d/%d，恒等 %d）"
                  % (cur["mapped"], cur["total"], cur["identical"]))
            return 0
        print("hir_status: 快照过期 —— 文件里 %r，实跑 %r"
              % ({k: old.get(k) for k in keys}, {k: cur.get(k) for k in keys}))
        return 1

    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        json.dumps(cur, ensure_ascii=False, indent=2) + "\n")
    print("hir_status: 接管 %d/%d（%.1f%%）｜ 恒等 %d"
          % (cur["mapped"], cur["total"], cur["participation"], cur["identical"]))
    print("已写出 flow/hir_status.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
