# -*- coding: utf-8 -*-
"""静态内存预算：从 MIR 算峰值（**唯一实现**）。

`tools/project_budget.py`（命令行）与 `project_map.run_build()`（构建期）
都调这里，避免两处口径打架 —— 这与「配置唯一 reader」是同一条纪律。

口径
====
   单变量字节 = 元素数 × 类型宽度      （`arg:x:f64:3,2` → 6×8 = 48）
   单函数字节 = 所有 arg/ret/var 之和   （保守上界，不做活跃区间分析）
   工程字节   = 各函数之和             （池是全局的，函数间不共享）

**推不出就跳过，不猜**：类型未知或形状含非数字时，该变量不计入
（宁可在调用方显示"未被计入"的口径差异，也不要一个假精确的数字）。
"""
import re

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
            continue
        b = w * n
        out[cur]["bytes"] += b
        out[cur]["vars"].append((name, b))
    return out


def report(per_func, pool=None):
    """返回 (ok, data, 超限明细)。`pool=None` 表示只算不判。"""
    total = sum(v["bytes"] for v in per_func.values())
    data = {
        "functions": {k: v["bytes"] for k, v in per_func.items()},
        "total_bytes": total,
        "pool_bytes": pool,
        "within_budget": None if pool is None else total <= pool,
    }
    if pool is None or total <= pool:
        return True, data, None
    rows = []
    for fn, v in per_func.items():
        for name, b in v["vars"]:
            rows.append((b, fn, name))
    rows.sort(reverse=True)
    data["over_by"] = total - pool
    data["top"] = [{"func": f, "var": n, "bytes": b} for b, f, n in rows[:5]]
    return False, data, rows[:5]
