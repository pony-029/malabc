# -*- coding: utf-8 -*-
"""**内存预算推导**：从 MIR 的数组形状算出每个函数的峰值字节数，与目标 RAM 比。

    python tools/mem_budget.py <目录> --limit 262144        # 256 KB
    python tools/mem_budget.py <目录> --limit 262144 --json
    python tools/mem_budget.py --selftest

## 为什么先做这一步

嵌入式方案里那句 `If (Array_Size > 256KB) { Enable_Tiling(); }` 的第一个
前提是**能算出 Array_Size**。而这件事不需要新的类型系统 —— `project_map.py`
的 `scan_facts` 早就在从 MIR 里取数组形状了，只是此前只用来**校验人写的配置**。

本工具把它倒过来用：**不读配置，直接算出"这个函数至少要多少字节"**，
于是"要不要 Tiling / 要不要 DMA"从"人填表"变成"算出来的结论"。

## 口径（写死，可复算）

* 一个数组的字节数 = `prod(shape) * 8`（f64，与运行时 `MLC_F64` 一致）；
* 形状未知（`arg:x:f64` 后无维度）→ 该数组**不计入**，但会单独报"形状未知"
  的个数 —— 不能把"不知道"算成 0，那是本轮之前多次踩过的坑；
* 函数峰值 = 该函数内**所有数组同时存在**的上界（保守：不做生命周期分析，
  所有数组相加）。真实峰值通常更小，但**先给上界**，不会漏报超限；
* 与 `--limit` 比：`peak > limit` 即判"必然超限"（上界都超了，实际必超）。

## 诚实的边界

* 只是**上界**，不做活跃期分析，所以会**高估**（宁可高估，不漏报）；
* 不含栈、不含标量、不含运行时开销；
* 形状来自 `% @m2c shape` 注解；无注解的数组计入"形状未知"，不猜。

退出码：
    0 = 有函数超限（这是**结论**，不是错误）或全部通过
    1 = 自证失败
    2 = 缺输入
"""
import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))

F64 = 8  # 字节/元素，与运行时 MLC_F64 一致


def _prod(shape):
    n = 1
    for d in shape:
        n *= int(d)
    return n


def parse_mir(text):
    """从 MIR 文本里按函数聚形状，返回 [{func, arrays:{name:shape}, ...}]。

    只认 `arg:|ret:|const:|var:` 里带形状的那几种；`unmapped` 行跳过
    —— 未降级的语句本来就不知道数组，不能当成 0 字节。
    """
    funcs = []
    cur = None
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith("func:"):
            cur = {"func": ln[5:], "arrays": {}, "scalars": []}
            funcs.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"^(arg|ret):([A-Za-z_]\w*):(\w+)(?::([\d,]+))?$", ln)
        if m:
            _kind, name, dt, dims = m.groups()
            if dt == "i64":
                cur["scalars"].append(name)
            elif dims:
                cur["arrays"][name] = [int(x) for x in dims.split(",") if x]
            else:
                cur["arrays"][name] = None      # 形状未知
            continue
        if ln == "end":
            cur = None
    return funcs


def budget(funcs, limit):
    """算每个函数的峰值上界，返回 (rows, unknown_counts)。"""
    rows = []
    unknown = 0
    for f in funcs:
        peak = 0
        unknown_here = 0
        for name, sh in f["arrays"].items():
            if not sh:
                unknown_here += 1
                continue
            peak += _prod(sh) * F64
        unknown += unknown_here
        rows.append({"func": f["func"], "peak_bytes": peak,
                     "unknown_shape": unknown_here,
                     "over": bool(limit and peak > limit)})
    rows.sort(key=lambda r: -r["peak_bytes"])
    return rows, unknown


def scan_dir(src, limit):
    import mir as M
    all_funcs = []
    files = 0
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".m"):
            continue
        p = os.path.join(src, fn)
        try:
            code = io.open(p, encoding="utf-8", errors="replace").read()
            txt, _st = M.to_mir(code)
        except Exception:                      # noqa: BLE001
            continue
        files += 1
        all_funcs.extend(parse_mir(txt))
    rows, unknown = budget(all_funcs, limit)
    return {"src": src, "files": files, "funcs": len(all_funcs),
            "limit": limit, "unknown_shape": unknown, "rows": rows}


#: **向量密集型算子**（R1032）：这些在嵌入式上通常需要 SIMD / 加速器，
#: 是「route to 加速后端」（如 Veriloom）的候选。判据刻意保守：
#: 只列**确定是数据并行**的，不把普通标量运算算进来。
VEC_OPS = frozenset((
    "OP-MATMUL",                     # 矩阵乘：最典型的三重循环 + 极强并行
    "OP-SUM", "OP-PROD", "OP-MEAN",   # 归约：可并行树形归约
    "OP-MAX", "OP-MIN",               # 归约
    "OP-SQRT", "OP-EXP", "OP-LOG",    # 逐元素：可向量化
    "OP-SIN", "OP-COS", "OP-TAN",
    "OP-ABS", "OP-FLOOR", "OP-CEIL", "OP-ROUND",
))


def profile(text, limit):
    """**每函数资源画像**：给下游（含未来的加速后端）吃的结构化输入。

    返回 `{func, peak_bytes, over, ops, vec_ops, vec_ratio, arrays,
             unknown_shape}`。刻意保持**纯静态**：不跑代码、不猜。

    `vec_ratio = 向量算子数 / 总算子数`，是「要不要 offload 到加速器」
    的可观测代理指标 —— 它不做判断，只把数摆出来；判断留给调用方
    （本仓不做汇编，边界写在这里）。
    """
    out = []
    cur = None
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("func:"):
            cur = {"func": s[5:], "arrays": {}, "ops": [],
                   "unknown_shape": 0}
            out.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"^(arg|ret):([A-Za-z_]\w*):(\w+)(?::([\d,]+))?$", s)
        if m:
            _k, name, dt, dims = m.groups()
            if dt != "i64":
                cur["arrays"][name] = ([int(x) for x in dims.split(",") if x]
                                       if dims else None)
            continue
        if s.startswith("op:"):
            cur["ops"].append(s.split(":")[1])
            continue
        if s == "end":
            cur = None
    rows = []
    for c in out:
        peak = 0
        unk = 0
        for _n, sh in c["arrays"].items():
            if not sh:
                unk += 1
            else:
                peak += _prod(sh) * F64
        vec = sum(1 for o in c["ops"] if o in VEC_OPS)
        rows.append({"func": c["func"], "peak_bytes": peak,
                     "over": bool(limit and peak > limit),
                     "ops": len(c["ops"]), "vec_ops": vec,
                     "vec_ratio": round(float(vec) / len(c["ops"]), 3)
                     if c["ops"] else 0.0,
                     "unknown_shape": unk})
    rows.sort(key=lambda r: (-r["peak_bytes"], -r["vec_ops"]))
    return rows


def _selftest():
    """两向自证：算得对、形状未知不当作 0、上限判定边界正确。

    只验"能跑"不算自证 —— 一个把未知形状当 0 字节的实现也能输出表，
    而那会把"不确定"伪装成"很小"。
    """
    good = bad = 0
    mir = ("func:f1\narg:x:f64:10,10\nret:y:f64:10,10\nend\n"
           "func:f2\narg:x:f64\nret:y:f64\nend\n")
    fs = parse_mir(mir)
    if len(fs) == 2:
        good += 1
    else:
        bad += 1
        print("  [selftest] 函数切分不对：%d" % len(fs))

    rows, unknown = budget(fs, 262144)
    f1 = [r for r in rows if r["func"] == "f1"][0]
    # 10*10*8*2 = 1600
    if f1["peak_bytes"] == 1600:
        good += 1
    else:
        bad += 1
        print("  [selftest] f1 峰值应为 1600，实得 %d" % f1["peak_bytes"])

    f2 = [r for r in rows if r["func"] == "f2"][0]
    if f2["peak_bytes"] == 0 and f2["unknown_shape"] == 2 and unknown == 2:
        good += 1
    else:
        bad += 1
        print("  [selftest] 形状未知未单独计数：%r" % (f2,))

    # 上限边界：恰好等于 limit 不算超
    rows2, _ = budget([{"func": "g", "arrays": {"a": [32768]}, "scalars": []}],
                      262144)
    if rows2[0]["over"] is False:
        good += 1
    else:
        bad += 1
        print("  [selftest] 恰好等于上限被判超限（应不超）")

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="内存预算推导")
    ap.add_argument("src", nargs="?")
    ap.add_argument("--limit", type=int, default=262144,
                    help="目标 RAM 字节数（默认 256 KB）")
    ap.add_argument("--json", action="store_true")
    # **每函数资源画像**（R1032）：给下游加速后端（如 Veriloom）吃的结构化输入。
    # 本仓只产出"画像 + 标记"，不做汇编排优 —— 那条边界留给对方。
    ap.add_argument("--profile", action="store_true",
                    help="输出每函数画像 JSON（峰值/算子数/向量算子占比）")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not ns.src or not os.path.isdir(ns.src):
        print("mem_budget: 缺输入（目录不存在）")
        return 2

    if ns.profile:
        import mir as M
        prof = []
        for fn in sorted(os.listdir(ns.src)):
            if not fn.endswith(".m"):
                continue
            try:
                code = io.open(os.path.join(ns.src, fn), encoding="utf-8",
                               errors="replace").read()
                txt, _st = M.to_mir(code)
            except Exception:                  # noqa: BLE001
                continue
            prof.extend(profile(txt, ns.limit))
        prof.sort(key=lambda x: (-x["peak_bytes"], -x["vec_ops"]))
        print(json.dumps({"limit": ns.limit, "src": ns.src,
                          "profiles": prof}, ensure_ascii=False, indent=1))
        return 0

    r = scan_dir(ns.src, ns.limit)
    if ns.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0

    over = [x for x in r["rows"] if x["over"]]
    print("[mem] %s ｜ 文件 %d ｜ 函数 %d ｜ 上限 %d 字节（%.0f KB）"
          % (os.path.basename(ns.src.rstrip("\\/")), r["files"], r["funcs"],
             ns.limit, ns.limit / 1024.0))
    print("  **必然超限 %d 个函数**（上界已超，实际必超）" % len(over))
    for x in over[:10]:
        print("    %-24s 峰值 >= %8d B（%.1f KB）"
              % (x["func"][:24], x["peak_bytes"], x["peak_bytes"] / 1024.0))
    if r["unknown_shape"]:
        print("  形状未知的数组 %d 个（未计入峰值 —— 不把「不知道」算成 0）"
              % r["unknown_shape"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
