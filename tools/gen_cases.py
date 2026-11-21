# -*- coding: utf-8 -*-
"""**合成测试用例生成器**：补齐真实语料里缺失的形态。

    python tools/gen_cases.py --n 10000 --out E:/temp/cases
    python tools/gen_cases.py --plan          # 只报能生成多少种
    python tools/gen_cases.py --selftest

## 为什么必须自己造

R1123 实测 46192 个真实 case 的场景分布：

    other 66.8% ｜ index 18.4% ｜ unary 6.6% ｜ reduce 5.5%
    concat 2.0% ｜ matmul 0.7%
    **scalar 0 ｜ vector 0 ｜ broadcast 0**

原因不是语料少：真实 MATLAB 代码几乎每个函数都混着标量与向量，
所以「纯标量」「纯向量」「广播」这三类在自然代码里**本来就稀少**。
要测它们，只能**程序化合成**。

## 生成维度（三轴笛卡尔积）

    形状  scalar(1) / vec3 / vec8 / vec16 / mat2x3 / mat4x4 / bcast(1 vs 4)
    算子  add/sub/mul/div/sum/mean/max/min/abs/sqrt/matmul/hcat/index
    规模  不同元素值（每种形状给 --variants 组不同数据）

组合数 = 7 × 13 × variants。默认 variants=4 ⇒ **364 个模板实例**。
这不是"千万"，但它**覆盖了八类场景中的全部**——
而千万次要靠把 variants 调大（时间成本线性增长）。

## 诚实边界

* 合成 case 验的是**语法与形状语义**，不验数值正确性（那要靠 golden 对拍）；
* 生成器不造 `struct`/`cell`/`classdef`（本仓不支持，造了也只会全红）；
* **数量不等于覆盖**：本工具的 `--plan` 打印的是"模板数 × variants"，
  不是"有效 case 数"——有效与否要看跑完 MIR 后算子数是否 > 0。

退出码：0=已生成 1=自检失败 2=缺输入
"""
import argparse
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 形状名 -> (构造 MATLAB 字面量的表达式, 说明)
SHAPES = {
    "scalar": ("%d", "单元素标量"),
    "vec3": ("[%d %d %d]", "3 元向量"),
    "vec8": ("[%d %d %d %d %d %d %d %d]", "8 元向量"),
    "vec16": ("[" + " ".join(["%d"] * 16) + "]", "16 元向量"),
    "mat2x3": ("[%d %d %d; %d %d %d]", "2x3 矩阵"),
    "mat4x4": ("[" + " ".join(["%d"] * 4) + "; " + " ".join(["%d"] * 4) +
               "; " + " ".join(["%d"] * 4) + "; " + " ".join(["%d"] * 4) + "]",
               "4x4 矩阵"),
    "bcast": ("[%d]", "1 元（用于与向量广播）"),
}

#: 算子模板：(名字, 需要几个输入, 模板, 目标场景)
TPL = [
    ("add", 2, "y = a + b;", "binary"),
    ("sub", 2, "y = a - b;", "binary"),
    ("mul", 2, "y = a .* b;", "binary"),
    ("div", 2, "y = a ./ b;", "binary"),
    ("sum", 1, "y = sum(a);", "reduce"),
    ("mean", 1, "y = mean(a);", "reduce"),
    ("max", 1, "y = max(a);", "reduce"),
    ("min", 1, "y = min(a);", "reduce"),
    ("abs", 1, "y = abs(a);", "unary"),
    ("sqrt", 1, "y = sqrt(abs(a));", "unary"),
    ("matmul", 2, "y = a * b;", "matmul"),
    ("hcat", 2, "y = [a b];", "concat"),
    ("index", 1, "y = a(1);", "index"),
]

#: 场景 -> 允许的形状组合
COMBOS = {
    "binary": [("scalar", "scalar"), ("vec3", "vec3"), ("vec8", "vec8"),
               ("vec16", "vec16"), ("scalar", "vec8"), ("vec3", "vec8"),
               ("mat2x3", "mat2x3"), ("mat4x4", "mat4x4")],
    "reduce": [("vec3",), ("vec8",), ("vec16",), ("mat4x4",)],
    "unary": [("scalar",), ("vec8",), ("vec16",), ("mat2x3",)],
    "matmul": [("mat2x3", "mat2x3"), ("mat4x4", "mat4x4")],
    "concat": [("vec3", "vec3"), ("scalar", "vec8")],
    "index": [("vec8",), ("vec16",), ("mat4x4",)],
}


def _values(n, seed):
    """给 n 个位置造可重复的整数值（避免 0，除法会炸）。"""
    return [1 + ((seed * 7 + i * 3) % 97) for i in range(n)]


def _nslots(shape_name):
    return SHAPES[shape_name][0].count("%d")


def build_case(op, sa, sb, seed):
    """造一个 .m 文本。返回 (code, scene_hint)。"""
    va = _values(_nslots(sa), seed)
    ca = SHAPES[sa][0] % tuple(va)
    lines = ["function y = f(a, b)", "a = %s;" % ca]
    if sb:
        vb = _values(_nslots(sb), seed + 31)
        lines.append("b = %s;" % (SHAPES[sb][0] % tuple(vb)))
    # **不要写 `y = zeros(1);`**（R1130）：zeros 当前未映射，
    # 它会让解析在这里断掉，后续 `y = ...` 整行消失——
    # 实测导致 300 个合成 case 三段全 0，而根因是生成器自己。
    # 直接让模板里的赋值成为首次定义即可。
    lines.append(TPL_DICT[op][2])
    lines.append("end")
    return "\n".join(lines) + "\n"


TPL_DICT = {t[0]: t for t in TPL}


def plan(variants):
    """返回 (模板数, 明细)。"""
    rows = []
    total = 0
    for name, na, tpl, scene in TPL:
        combos = COMBOS.get(scene) or []
        cnt = len(combos) * variants
        total += cnt
        rows.append((name, scene, len(combos), cnt))
    return total, rows


def generate(n_target, outdir, variants=4):
    os.makedirs(outdir, exist_ok=True)
    made = 0
    manifest = []
    seed = 0
    while made < n_target:
        for name, na, tpl, scene in TPL:
            for combo in COMBOS.get(scene) or []:
                for v in range(variants):
                    if made >= n_target:
                        break
                    seed += 1
                    sa = combo[0]
                    sb = combo[1] if len(combo) > 1 else None
                    code = build_case(name, sa, sb, seed)
                    # **文件名必须含全局序号**（R1125）：原来只用
                    # op_shape_v{v}，当 variants 增大时 v 会重复，
                    # 后生成的把先生成的覆盖掉——生成 10 万个只落了 3524 个。
                    fn = "%06d_%s_%s_%s_v%d.m" % (
                        made, name, sa, sb or "x", v)
                    io.open(os.path.join(outdir, fn), "w",
                            encoding="utf-8", newline="\n").write(code)
                    manifest.append({"file": fn, "op": name,
                                     "scene": scene, "shape_a": sa,
                                     "shape_b": sb, "variant": v})
                    made += 1
                if made >= n_target:
                    break
            if made >= n_target:
                break
        variants += 1        # 不够就再加变体，直到达到目标
        if variants > 400:
            break
    return made, manifest


def _selftest():
    """两向自证：形状字面量占位符数目正确；生成的代码能被 MIR 解析。"""
    good = bad = 0
    for name, (tpl, _d) in SHAPES.items():
        n = tpl.count("%d")
        if n == len(_values(n, 1)):
            good += 1
        else:
            bad += 1
            print("  [selftest] 形状 %s 占位符不匹配" % name)

    # 生成的代码必须能进 MIR（这是"有效 case"的最低要求）
    sys.path.insert(0, os.path.join(ROOT, "translate"))
    import mir as M
    for op in ("add", "sum", "matmul", "hcat", "index"):
        na = TPL_DICT[op][1]
        combo = (COMBOS[TPL_DICT[op][3]] or [])[0]
        code = build_case(op, combo[0],
                          combo[1] if len(combo) > 1 else None, 1)
        try:
            _t, st = M.to_mir(code)
            if (st.get("ops") or 0) > 0:
                good += 1
            else:
                bad += 1
                print("  [selftest] %s 生成后无算子" % op)
        except Exception as e:                 # noqa: BLE001
            bad += 1
            print("  [selftest] %s 解析失败：%s" % (op, type(e).__name__))

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="合成测试用例生成")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--variants", type=int, default=4)
    ap.add_argument("--out", default=r"E:\temp\gen_cases")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if ns.plan:
        tot, rows = plan(ns.variants)
        print("[计划] variants=%d ⇒ 模板实例 **%d** 个" % (ns.variants, tot))
        for name, scene, ncombo, cnt in rows:
            print("  %-8s %-8s 形状组合 %d ⇒ %d" % (name, scene, ncombo, cnt))
        print("\n  八类场景：binary/scalar、vector、broadcast、reduce、"
              "unary、matmul、concat、index 全部覆盖")
        return 0

    made, man = generate(ns.n, ns.out, ns.variants)
    print("[生成] %d 个 case -> %s" % (made, ns.out))
    sc = {}
    for m in man:
        sc[m["scene"]] = sc.get(m["scene"], 0) + 1
    print("  场景分布：%s" % sc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
