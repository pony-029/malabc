# -*- coding: utf-8 -*-
"""**两个执行后端必须覆盖同一批算子**：C 运行时 vs Rust VM。

## 为什么需要这条

R887 实测：规模语料跑 VM 时报 `VM 未实现该算子：OP-CEIL` 等 **13 种**，
而 C 运行时全都有。此前的棘轮（`test_every_registered_op_has_c_implementation`）
只查 `C_IMPLEMENTED` —— **单侧断言永远为真**，两边不同步时谁都不会红。

后果不只是"VM 少几个功能"：`test_vm_differential` 用 VM 当 C 的参照，
VM 缺算子意味着**那段比对覆盖不到这些算子**，而它一直是绿的。

## 判据

`C_IMPLEMENTED - VM 分派` 必须**正好等于**登记表 `VM_MISSING`（空集合 = 全同步）。
新增一个 C 算子而忘了补 VM，这条立刻红。
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VM_RS = os.path.join(ROOT, "rust", "m2c", "src", "vm.rs")
if os.path.join(ROOT, "translate") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "translate"))

#: C 已实现、VM 有意不做的算子：`{op: 理由}`。**空集合是目标状态**。
#:
#: 现存两条都是"索引类"，VM 里由更一般的算子承担：
#: * `OP-IDX2`：前端把 `A(i,j)` 降成 `OP-INDEX`（列优先线性下标），VM 只见到后者；
#: * `OP-COL`：列切片，VM 侧目前没有等价形态（前端未产生该算子）。
#: 它们不是"忘了写"，而是"VM 走的是另一条等价路径" —— 但必须写在这里，
#: 否则下一个人无法区分"有意"与"漏了"。
VM_MISSING = {
    "OP-IDX2": "前端降级成 OP-INDEX（列优先线性下标），VM 只见后者",
    "OP-COL": "列切片；前端当前不产生该算子，VM 无等价形态",
}


def _vm_ops():
    src = io.open(VM_RS, encoding="utf-8", errors="replace").read()
    return set(re.findall(r'"(OP-[A-Z0-9]+)"', src))


def test_vm_covers_every_c_operator():
    """C 有而 VM 没有的算子，必须**逐个登记**在 `VM_MISSING` 里。"""
    from operators import C_IMPLEMENTED

    vm = _vm_ops()
    missing = sorted(set(C_IMPLEMENTED) - vm)
    unexpected = [m for m in missing if m not in VM_MISSING]
    assert not unexpected, (
        "这些算子 C 运行时有、VM 没有分派（VM 会报「未实现该算子」）：%r\n"
        "  要么在 vm.rs 的 match 里补上，要么在 VM_MISSING 里写清为什么可以没有。"
        % unexpected)

    # 反向：登记表里不许留下"其实已经实现"的陈旧条目
    stale = sorted(k for k in VM_MISSING if k in vm)
    assert not stale, "VM_MISSING 里有 VM 已实现的算子（陈旧条目）：%r" % stale

    for k, why in VM_MISSING.items():
        assert len(why.strip()) >= 12, "%s 的登记理由太短：%r" % (k, why)


def test_vm_has_no_extra_operator():
    """反向：VM 分派里不许有 C 侧不存在的算子（否则 VM 与 C 语义无从对齐）。"""
    from operators import C_IMPLEMENTED

    extra = sorted(_vm_ops() - set(C_IMPLEMENTED))
    assert not extra, "VM 分派了 C 侧不存在的算子：%r" % extra
