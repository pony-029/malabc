# -*- coding: utf-8 -*-
"""**外部契约校验**：MATLAB + C 混合工程里，把「外部加速库」接进来之前的体检。

    python tools/ext_contract.py --op-map <m> [--profile <p>]
    python tools/ext_contract.py --selftest

## 场景

算法部门常见做法：MATLAB 写业务逻辑，矩阵乘/卷积这类热点用 C + 向量指令
（NEON / AVX / 自定义 DSP）手写。转换器要做的不是反编译那些 C，而是
**声明式登记 + 校验 + 生成调用桩**。

## 最致命的坑：dtype 不一致

本仓运行时是 **f64**（`mlc_array` 的 data 是 double，`prod(shape)×8`）。
而这类加速库几乎清一色是 **float32**（`sgemm` 的 s 就是 single）。

把 f64 缓冲区传给 `float*` 参数，后果不是"差一点精度"，而是：

    按 4 字节步长解释原本 8 字节的元素 -> 读到的是半个 double 的位模式 -> 全错

所以 `dtype` **必须显式声明**，且不是 f64 就必须报出来，让人决定是
「换 dgemm」还是「在桩里做转换 + 接受精度损失」——**不能让工具替人默认**。

## 校验项

| 项 | 规则 | 为什么 |
|---|---|---|
| `dtype` | 必须声明；非 `f64` 报**错误** | 见上 |
| `align` | 必须是 2 的幂且 ≤ 4096 | 对齐要求写错会让向量指令崩 |
| `header` | 必填，且路径不含 `..` | 生成工程要能 include 到 |
| `lib` | 可选；给了就必须是 `.a` / `.so` / `.c` | 免得"链接了个目录" |
| `why` | 必填（沿用 op-map 的规矩） | 覆盖必须可审计 |

退出码：
    0 = 全部契约合法（dtype 全是 f64 或已显式接受）
    1 = 有契约不合法（这是**结论**，列清楚）
    2 = 缺输入
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "translate"))

#: 本仓运行时唯一支持的 dtype。换它等于换整个 ABI。
NATIVE_DTYPE = "f64"

ALLOWED_LIB_EXT = (".a", ".so", ".lib", ".c", ".o")


def check_override(op_id, spec):
    """校验单条外部契约。返回 (errors, warnings, info)。"""
    errs, warns, info = [], [], {}
    if not isinstance(spec, dict):
        return ["%s: 必须是对象" % op_id], warns, info

    c = spec.get("c")
    if not c:
        errs.append("%s: 缺 c（目标 C 函数名）" % op_id)

    why = (spec.get("why") or "").strip()
    if not why:
        errs.append("%s: 缺 why（覆盖必须写清理由）" % op_id)

    dt = spec.get("dtype")
    if not dt:
        errs.append("%s: 缺 dtype —— 本仓运行时是 %s，不声明就无法判断能否直传"
                    % (op_id, NATIVE_DTYPE))
    elif str(dt).lower() != NATIVE_DTYPE:
        errs.append(
            "%s: dtype=%s 与本仓运行时 %s 不一致 —— 直传会按错误步长解释内存"
            "（不是精度问题，是结果全错）。要么换 d* 版本，要么在桩里显式转换"
            % (op_id, dt, NATIVE_DTYPE))
    else:
        info["dtype"] = "native"

    hdr = (spec.get("header") or "").strip()
    if not hdr:
        errs.append("%s: 缺 header（生成工程要 include）" % op_id)
    elif ".." in hdr.replace("\\", "/"):
        errs.append("%s: header 含 ..，不允许跳出工程目录" % op_id)

    al = spec.get("align")
    if al is not None:
        if not isinstance(al, int) or al <= 0:
            errs.append("%s: align 必须是正整数" % op_id)
        elif al & (al - 1):
            errs.append("%s: align=%d 不是 2 的幂" % (op_id, al))
        elif al > 4096:
            errs.append("%s: align=%d 超过 4096，通常是写错了" % (op_id, al))

    lib = (spec.get("lib") or "").strip()
    if lib:
        if os.path.splitext(lib)[1].lower() not in ALLOWED_LIB_EXT:
            errs.append("%s: lib 的扩展名不在 %s" % (op_id, ALLOWED_LIB_EXT))
        # 给了 lib 却没 header，等于"链接了但不知道签名"
        if not hdr:
            warns.append("%s: 有 lib 但没 header，调用点无法校验签名" % op_id)

    # 向量指令集隔离提示（不判错，只提醒）
    isa = (spec.get("isa") or "").strip()
    if isa and isa.lower() not in ("", "scalar"):
        info["isa"] = isa
        if not spec.get("fallback"):
            warns.append(
                "%s: 声明了 isa=%s 但没给 fallback —— 换平台时这条映射会失效，"
                "建议写 fallback 指向标量实现" % (op_id, isa))
    return errs, warns, info


def audit(path):
    """读 op-map 并逐条校验。"""
    d = json.load(io.open(path, encoding="utf-8"))
    ov = d.get("overrides") or {}
    errs, warns = [], []
    for k, v in sorted(ov.items()):
        e, w, _i = check_override(k, v)
        errs.extend(e)
        warns.extend(w)
    return {"path": path, "count": len(ov), "errors": errs, "warnings": warns}


def _selftest():
    """两向自证：合法的必须过；f32 必须被判错（这是最危险的静默失败）。"""
    good = bad = 0

    ok = {"c": "accel_dgemm", "why": "公司库", "dtype": "f64",
          "header": "accel/matmul.h", "align": 64}
    e, w, _i = check_override("OP-MATMUL", ok)
    if not e:
        good += 1
    else:
        bad += 1
        print("  [selftest] 合法契约被拒：%r" % (e,))

    f32 = dict(ok)
    f32["dtype"] = "f32"
    e2, _w2, _i2 = check_override("OP-MATMUL", f32)
    if any("dtype" in x for x in e2):
        good += 1
    else:
        bad += 1
        print("  [selftest] f32 契约未判错（最危险的一条）")

    noal = dict(ok)
    noal["align"] = 48          # 不是 2 的幂
    e3, _w3, _i3 = check_override("OP-ADD", noal)
    if any("2 的幂" in x for x in e3):
        good += 1
    else:
        bad += 1
        print("  [selftest] 非 2 的幂对齐未判错")

    nodt = {"c": "x", "why": "y", "header": "h.h"}
    e4, _w4, _i4 = check_override("OP-ADD", nodt)
    if any("缺 dtype" in x for x in e4):
        good += 1
    else:
        bad += 1
        print("  [selftest] 缺 dtype 未判错")

    print('SELFTEST COUNTS {"bad": %d, "good": %d}' % (bad, good))
    return 0 if bad == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="外部契约校验")
    ap.add_argument("--op-map")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ns = ap.parse_args(argv)

    if ns.selftest:
        return _selftest()
    if not ns.op_map or not os.path.isfile(ns.op_map):
        print("ext_contract: 缺输入（--op-map 不存在）")
        return 2
    try:
        r = audit(ns.op_map)
    except (IOError, OSError, ValueError) as e:
        print("ext_contract: 读不出（%s）" % type(e).__name__)
        return 2

    if ns.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 1 if r["errors"] else 0

    print("[契约] %s ｜ 条目 %d ｜ 错误 %d ｜ 警告 %d"
          % (os.path.basename(ns.op_map), r["count"],
             len(r["errors"]), len(r["warnings"])))
    for x in r["errors"]:
        print("  [E] %s" % x)
    for x in r["warnings"]:
        print("  [W] %s" % x)
    return 1 if r["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
