# -*- coding: utf-8 -*-
"""shape_suggest.py —— 从源码线索**建议** `% @m2c shape`，而不是让人凭猜。

## 为什么需要它

实测 YALMIP：1204 个函数里 1067 个被显式拒绝，剩下 137 个里只有 13 个无未映射语句，
而**没有一个带形状注解** → `main` 无法驱动 → L3b/L4 全 0。

也就是说：**挡住对拍的已经不是转换能力，而是"没人写注解"**。
那就把这件事变成"机器给建议、人来确认"。

## 它怎么猜（三条线索，全部可解释）

1. `arg = zeros(m,n)` / `ones(m,n)` / `eye(m)`  → 形状 `m,n`（字面量才算）
2. `arg = [1 2 3]`                              → 形状 `3`
3. 函数体里 `arg(i)` / `arg(i,j)` 的下标上界     → 至少这么大

**猜不出来就写 `?`** —— 宁可留空，不给一个看起来确定的错值。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from translate import mir as M  # noqa: E402

_FILL = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(zeros|ones|eye)\s*\(\s*"
                   r"(\d+)\s*(?:,\s*(\d+)\s*)?\)")
_LITERAL = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*\[\s*([-\d\s.;]+)\]\s*;")
_IDX = re.compile(r"([A-Za-z_]\w*)\s*\(\s*([^()]*?)\s*\)")


def _guess(body_lines, name):
    """给一个参数猜形状；猜不出返回 None。"""
    for ln in body_lines:
        m = _FILL.match(ln)
        if m and m.group(1) == name:
            rows = int(m.group(3))
            cols = int(m.group(4)) if m.group(4) else 1
            return [rows, cols] if cols > 1 else [rows]
        m = _LITERAL.match(ln)
        if m and m.group(1) == name:
            nums = [x for x in re.split(r"[\s;]+", m.group(2).strip()) if x]
            if nums and all(re.fullmatch(r"-?\d+", x) for x in nums):
                return [len(nums)]
    top = 0
    for ln in body_lines:
        for m in _IDX.finditer(ln):
            if m.group(1) != name:
                continue
            parts = [p.strip() for p in m.group(2).split(",") if p.strip()]
            if len(parts) == 1 and parts[0].isdigit():
                top = max(top, int(parts[0]))
    if top:
        return [top]
    return None


def analyse(path):
    """返回 [(函数名, [(参数, 建议形状 或 None)])]，只含**没有注解**的参数。

    **被拒函数直接跳过**：它们（varargin/@方法/cell/struct）加注解也没用，
    留着只会把真正的建议淹掉。判定复用 `mir.reject_reason`，不另写一份。
    """
    src = io.open(path, encoding="utf-8", errors="replace").read()
    out = []
    for f in M.split_functions(src):
        if M.reject_reason(f, path):
            continue
        need = []
        types = f.get("types") or {}
        shapes = f.get("shapes") or {}
        if not f["args"]:
            continue
        for a in f["args"]:
            if (types.get(a) or "") == "i64":
                continue          # 标量下标：本来就按 i64 传，不需要形状
            if shapes.get(a):
                continue          # 已有注解
            need.append((a, _guess(f["lines"], a)))
        if need:
            out.append((f["name"], need))
    return out


def _scan(src_dir):
    files = []
    for dp, dn, fn in os.walk(src_dir):
        dn[:] = sorted(d for d in dn if not d.startswith("."))
        for f in sorted(fn):
            if f.lower().endswith(".m"):
                files.append(os.path.join(dp, f))
    return files


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("用法: python tools/shape_suggest.py <目录或 .m> [--limit N]")
        return 2
    target = argv[0]
    limit = 40
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    files = [target] if os.path.isfile(target) else _scan(target)

    rows = []
    for p in files:
        try:
            for name, need in analyse(p):
                rows.append((os.path.relpath(p, target if os.path.isdir(target)
                                             else os.path.dirname(target)),
                             name, need))
        except Exception:      # noqa: BLE001 - 单个文件坏不该中断扫描
            continue

    if not rows:
        print("没有找到需要注解的函数")
        return 0

    known = sum(1 for _, _, need in rows if all(g for _, g in need))
    print("需要注解的函数：%d（其中 %d 个全部参数都能推断）" % (len(rows), known))
    for rel, name, need in rows[:limit]:
        parts = []
        for a, g in need:
            parts.append("%s=%s" % (a, ("x".join(str(x) for x in g)) if g else "?"))
        print("  %-46s %-22s %s" % (rel, name, " ".join(parts)))
    if len(rows) > limit:
        print("  …（还有 %d 个，用 --limit 调整）" % (len(rows) - limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
