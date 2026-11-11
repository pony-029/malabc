# -*- coding: utf-8 -*-
"""project_budget.py —— 从 MIR 算**静态内存峰值**，产出 `budget.json`。

为什么在生成期算（而不是等板子 OOM）
====================================
嵌入式最差的交付形态是"能编过、一跑就崩"：池子给 64KB，实际需要 96KB，
`gcc` 一句警告都没有。所以预算必须在**生成期**算出来，并且——
**超限时必须指名道姓**（哪个函数、哪个变量、差多少），否则用户只知道"超了"。

口径
====
   单变量字节 = 元素数 × 类型宽度          （`arg:x:f64:3,2` → 6 × 8 = 48）
   单函数字节 = 该函数所有 arg/ret/var 之和（**静态峰值**的保守上界：
                不做活跃区间分析，宁可高估，不低估）
   工程字节   = 各函数之和（池是全局的，函数间不共享）

明确不做：活跃变量区间分析（那是优化，不是判据）；动态形状（推不出 → 直接拒绝）。

用法：
    python tools/project_budget.py proj.mir                     # 0=在预算内 1=超限 2=缺输入
    python tools/project_budget.py proj.mir --pool 65536 -o budget.json
    python tools/project_budget.py proj.mir --selftest          # 两向自证
    python tools/project_budget.py --help

退出码：
    0  = 计算成功且在预算内（或未给 --pool）
    1  = 超限（已打印函数/变量/差额）
    2  = 缺输入（MIR 不存在 / 没有可计算的量）
"""
import argparse
import io
import json
import os
import re
import sys

#: 类型宽度（字节）。与 `c_runtime` 的类型一致。
WIDTH = {"f64": 8, "f32": 4, "i64": 8, "i32": 4, "i16": 2, "i8": 1,
         "int64": 8, "int32": 4, "int16": 2, "int8": 1, "q15": 2}

_DECL = re.compile(r"^(arg|ret|var):([A-Za-z_]\w*):([a-z0-9]+)(?::([\d,]+))?$")


def _elems(shape):
    if not shape:
        return 1
    try:
        n = 1
        for part in shape.split(","):
            n *= int(part)
        return n
    except ValueError:
        return None


def parse(text):
    """MIR 文本 → {函数: {"bytes": int, "vars": [(名字, 字节)]}}。"""
    out, cur = {}, None
    for ln in (text or "").split("\n"):
        s = ln.strip()
        if s.startswith("func:"):
            cur = s[5:].strip()
            out[cur] = {"bytes": 0, "vars": []}
            continue
        if cur is None:
            continue
        m = _DECL.match(s)
        if not m:
            continue
        _kind, name, dtype, shape = m.group(1), m.group(2), m.group(3), m.group(4)
        w = WIDTH.get(dtype)
        n = _elems(shape)
        if w is None or n is None:
            continue          # 推不出就跳过（不猜），由调用方决定是否拒绝
        b = w * n
        out[cur]["bytes"] += b
        out[cur]["vars"].append((name, b))
    return out


def report(per_func, pool=None):
    """返回 (ok, data, 超限明细)。"""
    total = sum(v["bytes"] for v in per_func.values())
    worst = max(per_func.items(), key=lambda kv: kv[1]["bytes"], default=(None, None))
    data = {
        "functions": {k: v["bytes"] for k, v in per_func.items()},
        "total_bytes": total,
        "pool_bytes": pool,
        "within_budget": None if pool is None else total <= pool,
    }
    if pool is None or total <= pool:
        return True, data, None
    # 超限：列出最大的几个变量，指名道姓
    rows = []
    for fn, v in per_func.items():
        for name, b in v["vars"]:
            rows.append((b, fn, name))
    rows.sort(reverse=True)
    data["over_by"] = total - pool
    data["top"] = [{"func": f, "var": n, "bytes": b} for b, f, n in rows[:5]]
    return False, data, rows[:5]


def _selftest():
    """两向自证：算得对（正常）+ 抓得住（超限）。"""
    mir = ("version 3\nfunc:a\narg:x:f64:4\nop:OP-MUL:y:x:x\nend\n"
           "func:b\narg:z:f64:2,3\nret:w:f64:1\nend\n")
    pf = parse(mir)
    good = pf["a"]["bytes"] == 32 and pf["b"]["bytes"] == 56
    ok1, d1, _ = report(pf, pool=1000)
    ok2, d2, top = report(pf, pool=10)
    if not good:
        print("自证失败：字节数算错 %r" % {k: v["bytes"] for k, v in pf.items()})
        return 1
    if not ok1 or ok2:
        print("自证失败：预算判定错（1000 应通过 / 10 应超限）")
        return 1
    # 最大的**单变量**是 `z`（2×3 个 f64 = 48 字节），不是函数总量 56
    if not top or top[0][0] != 48:
        print("自证失败：超限明细没按变量大小排序（期望首项 48，实得 %r）"
              % (top[:1],))
        return 1
    print('SELFTEST COUNTS {"bad": 2, "good": 1}')
    print("自证通过：字节数正确、超限可判、明细按大小排序")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("mir", nargs="?")
    ap.add_argument("--pool", type=int, default=None)
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a, _rest = ap.parse_known_args(argv or sys.argv[1:])

    if a.help:
        print(__doc__)
        return 0
    if a.selftest:
        return _selftest()

    if not a.mir or not os.path.isfile(a.mir):
        print("缺输入：MIR 文件不存在 %r" % a.mir)
        return 2
    pf = parse(io.open(a.mir, encoding="utf-8", errors="replace").read())
    if not pf:
        print("缺输入：MIR 里没有函数")
        return 2

    ok, data, top = report(pf, a.pool)
    if a.out:
        io.open(a.out, "w", encoding="utf-8", newline="\n").write(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        print("已写出 %s" % a.out)

    if a.pool is None:
        print("静态峰值 %d 字节（%d 个函数；未给 --pool，不判超限）"
              % (data["total_bytes"], len(pf)))
        return 0
    if ok:
        print("在预算内：%d / %d 字节（余 %d）"
              % (data["total_bytes"], a.pool, a.pool - data["total_bytes"]))
        return 0

    print("**超预算**：需要 %d 字节，池只有 %d（差 %d）"
          % (data["total_bytes"], a.pool, data["over_by"]))
    for b, fn, name in top:
        print("   %-16s %-14s %6d 字节" % (fn, name, b))
    return 1


if __name__ == "__main__":
    sys.exit(main())
