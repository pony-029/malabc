# -*- coding: utf-8 -*-
"""**私有指令集使用计划**：哪些调用点够格走向量/私有 ISA 实现。

    python tools/isa_plan.py <MIR 目录> --profile <p> [--json]
    python tools/isa_plan.py --selftest

## 问题

私有指令集（公司自研 NEON-like、DSP、或 Veriloom 将来要接的汇编后端）都有
**触发门槛**：数组长度得是某个倍数、得够长、得对齐。而"够不够格"必须由
**真实形状**判断，不能靠人拍。

## 为什么条件不能写成表达式字符串

很多方案会写：

    condition: "is_vector && length % 128 == 0"

这句话在配置里**永远不会生效**（没人执行它），除非工具去 `eval()`——
而 eval 会带来两个问题：配置即代码（注入面），以及**无法静态校验**
（写错了要等运行到那条路径才知道）。

所以本工具把条件**结构化**：

    {"min_len": 128, "len_multiple": 16, "require_align": 64}

三个字段各自可校验：min_len 是正整数、len_multiple 是正整数、
require_align 是 2 的幂。语义清晰，且能被门读。

## 判定口径

对每个 `op:` 语句，取其**输出数组**（`op:OP-XXX:dst:...` 的 dst）在
同函数 `ret`/`arg` 里的形状，算出 `numel`；然后逐条要求判定：

* `numel >= min_len`
* `numel % len_multiple == 0`
* 若 `require_align` 给定，则元素字节数 × 对齐要求 ≤ 段首址约束——
  本仓还没有地址分配，所以这一项只做**记录**，不判负（诚实边界）。

形状未知 -> **判为"不够格"**，并计入 `unknown`。理由：把"不知道"当成
"够格"会让向量路径在运行时越界读——那比慢更糟。

退出码：
    0 = 已产出计划
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

F64 = 8


def load_isa_rules(path):
    """读 profile 的 custom_isa 段。返回 {op_id: rule}。"""
    p = json.load(io.open(path, encoding="utf-8"))
    rules = (p.get("custom_isa") or {}).get("rules") or []
    out = {}
    for r in rules:
        op = r.get("op")
        if not op:
            raise ValueError("custom_isa.rules 有一条缺 op")
        cond = r.get("condition") or {}
        if not isinstance(cond, dict):
            raise ValueError("%s 的 condition 必须是对象（结构化，不用表达式）" % op)
        for k in ("min_len", "len_multiple", "require_align"):
            v = cond.get(k)
            if v is None:
                continue
            if not isinstance(v, int) or v <= 0:
                raise ValueError("%s.condition.%s 必须是正整数" % (op, k))
        al = cond.get("require_align")
        if al is not None and (al & (al - 1)):
            raise ValueError("%s.condition.require_align=%d 不是 2 的幂" % (op, al))
        out[op] = {"c": r.get("c"), "header": r.get("header"),
                   "condition": cond, "fallback": r.get("fallback")}
    return out


def _prod(shape):
    n = 1
    for d in shape:
        n *= int(d)
    return n


def scan(src):
    """返回 [(func, op_id, dst, numel 或 None)]。"""
    import mir as M
    calls = []
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".m"):
            continue
        try:
            txt, _st = M.to_mir(
                io.open(os.path.join(src, fn), encoding="utf-8",
                        errors="replace").read())
        except Exception:                      # noqa: BLE001
            continue
        shapes = {}
        func = None
        ops = []
        for ln in txt.splitlines():
            s = ln.strip()
            if s.startswith("func:"):
                func = s[5:]
                shapes, ops = {}, []
                continue
            m = re.match(r"^(arg|ret):([A-Za-z_]\w*):\w+(?::([\d,]+))?$", s)
            if m and m.group(3):
                shapes[m.group(2)] = [int(x) for x in m.group(3).split(",") if x]
            if s.startswith("op:"):
                parts = s.split(":")
                if len(parts) >= 3:
                    ops.append((parts[1], parts[2]))
            if s == "end" and func:
                for op_id, dst in ops:
                    n = shapes.get(dst)
                    calls.append((func, op_id, dst,
                                  _prod(n) if n else None))
                func = None
    return calls


def plan(calls, rules):
    """逐调用点判定。返回 {"eligible": [...], "rejected": [...], ...}。"""
    elig, rej, unknown = [], [], 0
    for func, op_id, dst, numel in calls:
        rule = rules.get(op_id)
        if not rule:
            continue
        cond = rule["condition"]
        if numel is None:
            unknown += 1
            rej.append({"func": func, "op": op_id, "dst": dst,
                        "why": "形状未知，不够格（不把「不知道」当成够格）"})
            continue
        bad = []
        if cond.get("min_len") and numel < cond["min_len"]:
            bad.append("numel %d < min_len %d" % (numel, cond["min_len"]))
        if cond.get("len_multiple") and numel % cond["len_multiple"]:
            bad.append("numel %d 不是 %d 的倍数"
                       % (numel, cond["len_multiple"]))
        if bad:
            rej.append({"func": func, "op": op_id, "dst": dst,
                        "why": "；".join(bad)})
        else:
            e = {"func": func, "op": op_id, "dst": dst, "numel": numel,
                 "c": rule.get("c"), "header": rule.get("header")}
            if cond.get("require_align"):
                e["align"] = cond["require_align"]
                e["align_note"] = "需在生成期注入 aligned(N)；本仓尚无地址分配"
            elig.append(e)
    return {"eligible": elig, "rejected": rej, "unknown_shape": unknown,
            "considered": len(elig) + len(rej)}


def _selftest():
    """两向自证：够格必须够格、不够格必须拒、形状未知必须拒。"""
    good = bad = 0
    rules = {"OP-MATMUL": {"c": "isa_mmul", "header": "isa.h",
                           "condition": {"min_len": 128, "len_multiple": 16}}}

    r = plan([("f", "OP-MATMUL", "y", 256)], rules)
    if len(r["eligible"]) == 1:
        good += 1
    else:
        bad += 1
        print("  [selftest] 256 元素应够格（>=128 且 %16==0）")

    r2 = plan([("f", "OP-MATMUL", "y", 120)], rules)
    if not r2["eligible"] and len(r2["rejected"]) == 1:
        good += 1
    else:
        bad += 1
        print("  [selftest] 120 元素应被拒（<128）")

    r3 = plan([("f", "OP-MATMUL", "y", 130)], rules)
    if not r3["eligible"] and "倍数" in r3["rejected"][0]["why"]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 130 元素应因不是 16 的倍数被拒")

    r4 = plan([("f", "OP-MATMUL", "y", None)], rules)
    if not r4["eligible"] and r4["unknown_shape"] == 1:
        good += 1
    else:
        bad += 1
        print("  [selftest] 形状未知必须被拒并计入 unknown")

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="私有指令集使用计划")
    ap.add_argument("src", nargs="?")
    ap.add_argument("--profile")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not ns.src or not os.path.isdir(ns.src):
        print("isa_plan: 缺输入（MIR 目录不存在）")
        return 2
    if not ns.profile or not os.path.isfile(ns.profile):
        print("isa_plan: 缺输入（--profile 不存在）")
        return 2
    try:
        rules = load_isa_rules(ns.profile)
    except (IOError, OSError, ValueError) as e:
        print("isa_plan: profile 不合法 —— %s" % e)
        return 2
    if not rules:
        print("isa_plan: profile 里没有 custom_isa.rules（无私有 ISA 声明）")
        return 2

    r = plan(scan(ns.src), rules)
    if ns.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0

    print("[isa] 规则 %d 条 ｜ 命中调用点 %d ｜ 够格 %d ｜ 退回通用 %d（形状未知 %d）"
          % (len(rules), r["considered"], len(r["eligible"]),
             len(r["rejected"]), r["unknown_shape"]))
    for e in r["eligible"][:8]:
        print("  ✅ %-16s %-12s numel=%-8d -> %s"
              % (e["op"], e["func"], e["numel"], e["c"]))
    for e in r["rejected"][:6]:
        print("  ⤵  %-16s %-12s %s" % (e["op"], e["func"], e["why"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
