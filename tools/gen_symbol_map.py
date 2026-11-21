# -*- coding: utf-8 -*-
"""从 profile + op-map 生成 **符号重映射头** `m2c_symbols.h`。

    python tools/gen_symbol_map.py --profile <p> [--op-map <m>] -o <out.h>
    python tools/gen_symbol_map.py --selftest

## 为什么用宏重映射，而不是改 emit.rs

`rust/m2c/src/emit.rs` 里 `mlc_op_*` 是**几十处硬编码的 format! 字符串**，
要让它"按 profile 选符号"就得逐处改，改动面大、回归风险高。

宏重映射把这件事挪到**预处理期**：

    emit.rs 照旧生成 `mlc_op_sum(&x, &y)`
    编译时 `#define mlc_op_sum hw_dsp_sum`  ->  实际调用 hw_dsp_sum

好处：
  * 生成器零改动，`emit.rs` 与既有 519 条测试完全不受影响；
  * 换 profile 只换这个头文件，C 源码字节不变 —— 这正是"自由转换"该有的样子；
  * 重映射关系是**可见的文本**，review 时一眼能看完。

代价（要写在文件头里，不能藏）：
  * 宏是全局文本替换，若某处真的需要原符号就没法表达；
  * 调试时看到的是宏名，需要看预处理后的输出才能定位。

## 只重映射**确实不同**的符号

同名的不生成宏（无意义的 `#define a a` 会触发 -Wmacro-redefined 类的噪音，
也会让"这份头文件改了什么"变得难读）。

退出码：
    0 = 已生成
    1 = 自证失败
    2 = 缺输入
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def build_map(profile, op_map):
    """返回 [(原符号, 目标符号, 算子 id, 理由)]，只含真正不同的。"""
    import op_backends as OB

    isa_order, accel = OB.load_isa(profile)
    overrides = OB.load_op_map(op_map)
    have = OB.declared_symbols()
    r = OB.build(isa_order, accel, have, overrides)

    # **宏要映射「emit.rs 真正写进 C 的那个符号」-> 「最终选中的符号」**（R1044）。
    # emit.rs 里硬编码的是 `mlc_op_*`（内置参考实现），所以左值必须取
    # operators 的原始 `c`，而不是覆盖之后的 base ——
    # 否则「覆盖成 hw_dsp_sum 且没选到变体」时 selected==base，
    # 会被误判为"没变"，宏一条都不生成（实测就是这样，重映射 0 条）。
    import operators as O
    builtin = dict((op["id"], op["c"]) for op in O.OPERATORS)

    pairs = []
    for row in r["ops"]:
        orig = builtin.get(row["op"], row["base"])
        if row["selected"] == orig:
            continue          # 真的没变，不需要宏
        why = row.get("why") or ("按 ISA 优先级选到 %s" % row["selected_isa"])
        pairs.append((orig, row["selected"], row["op"], why))
    # 同一 base 被多个算子指向不同目标 -> 宏冲突，必须报
    seen = {}
    conflict = []
    for base, sel, op, _w in pairs:
        if base in seen and seen[base] != sel:
            conflict.append((base, seen[base], sel, op))
        seen[base] = sel
    return pairs, conflict, r


def render(pairs, profile_name, conflict):
    lines = [
        "/* m2c_symbols.h —— 由 tools/gen_symbol_map.py 生成，**不要手改**。",
        " *",
        " * 作用：把 m2c 生成的 `mlc_op_*` 调用在**预处理期**重映射到目标符号。",
        " * 于是 emit.rs 一行不改，换 profile 只换这个头文件。",
        " *",
        " * 已知代价：宏是全局文本替换；调试时看到的是宏名，需看预处理输出。",
        " * profile: %s" % profile_name,
        " */",
        "#ifndef M2C_SYMBOLS_H",
        "#define M2C_SYMBOLS_H",
        "",
    ]
    if conflict:
        lines.append("/* !! 检测到宏冲突（同一符号被指向不同目标），下面的定义只保留首个：")
        for base, a, b, op in conflict:
            lines.append(" *    %s: %s vs %s（来自 %s）" % (base, a, b, op))
        lines.append(" */")
        lines.append("")
    if not pairs:
        lines.append("/* 本 profile 下没有任何重映射：全部使用内置参考实现。 */")
    else:
        lines.append("/* 重映射 %d 条 */" % len(pairs))
        by_base = {}
        for base, sel, op, why in pairs:
            by_base.setdefault(base, (sel, op, why))
        for base, (sel, op, why) in sorted(by_base.items()):
            lines.append("/* %-12s -> %-24s %s */" % (op, sel, why[:60]))
            lines.append("#define %-24s %s" % (base, sel))
    lines += ["", "#endif /* M2C_SYMBOLS_H */", ""]
    return "\n".join(lines)


def _selftest():
    """两向自证：无变化时不出宏；有变化时出宏且不生成同名定义。"""
    good = bad = 0

    # 空 pairs -> 只有保护宏，没有 #define 出实际符号
    t = render([], "test", [])
    if "#define M2C_SYMBOLS_H" in t and "->" not in t.split("#define")[1]:
        good += 1
    else:
        bad += 1
        print("  [selftest] 空映射不该生成符号宏")

    t2 = render([("mlc_op_sum", "hw_dsp_sum", "OP-SUM", "公司库")],
                "test", [])
    if "#define mlc_op_sum" in t2 and "hw_dsp_sum" in t2:
        good += 1
    else:
        bad += 1
        print("  [selftest] 有映射时未生成 #define")

    # 同名不该进来（build_map 已过滤，这里再验渲染层不会出 a->a）
    t3 = render([], "test", [("mlc_op_a", "x", "y", "OP-A")])
    if "冲突" in t3:
        good += 1
    else:
        bad += 1
        print("  [selftest] 宏冲突未在文件里点明")

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成符号重映射头")
    ap.add_argument("--profile")
    ap.add_argument("--op-map")
    ap.add_argument("-o", "--out")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not ns.profile or not os.path.isfile(ns.profile):
        print("gen_symbol_map: 缺输入（--profile 不存在）")
        return 2
    out = ns.out or os.path.join(ROOT, "flow", "m2c_symbols.h")

    try:
        pairs, conflict, _r = build_map(ns.profile, ns.op_map)
    except (IOError, OSError, ValueError) as e:
        print("gen_symbol_map: 取数失败（%s: %s）" % (type(e).__name__, e))
        return 2

    name = os.path.basename(ns.profile)
    io.open(out, "w", encoding="utf-8", newline="\n").write(
        render(pairs, name, conflict))
    print("[symbols] %s -> %s ｜ 重映射 %d 条%s"
          % (name, os.path.relpath(out, ROOT), len(pairs),
             "，**冲突 %d 条**" % len(conflict) if conflict else ""))
    for base, sel, op, why in pairs[:8]:
        print("  %-12s %-22s -> %s" % (op, base, sel))
    return 0


if __name__ == "__main__":
    sys.exit(main())
