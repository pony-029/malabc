# -*- coding: utf-8 -*-
"""二进制跳（binhop）的**装置登记表** —— R82 Phase B 的单一事实源骨架（R82-0-4）。

T2 的目标是把「源码里的一次调用」往下连成多跳链：

    源码函数 ──▶ 二进制导出符号 ──▶ 它所在的库 ──▶ 那个库依赖的库 ──▶（GPU kernel）

链上**每一跳**都必须回答一个问题：**这一跳是哪个装置造出来的？**
答不出来，那条边就是「猜的」——而猜出来的边比没有边更坏（R82 §4 黑帽 K2）。

所以：每条 `binhop` 边的 `hop.via_device` 必须登记在本表里。
未登记 ⇒ 护栏 U4 红（`tools/check_unified_graph.py`）。

一图看懂（本表的作用位置）：

    unified_graph.Edge(kind="binhop", hop=Hop(via_device="elf.dynsym"))
                                                            │
                                                            ▼
                                          HOP_DEVICES 里必须**有**这一条
                                                            │
                                          没有 ──▶ U4 红（不许猜）

**Phase 0 的性质**：这里只登记**今天真的存在**的装置（对应 `binfmt/` 里已落地的
解析器）。Phase B 会**继续追加**真正开始造跳的那些装置；本表刻意留空的部分，
由「空白登记表 ⇒ 引用它的判据必须红」这条自证守住（不是静默空转）。
"""

# device_id -> 它读什么、产出什么（及它的实现在哪个文件里）
HOP_DEVICES = {
    # ── 二进制符号来源（binfmt/，R44–R71 已落地）────────────────────────
    "elf.dynsym": "ELF 动态符号表 → 导出/导入符号（binfmt/elf.py）",
    "elf.needed": "ELF DT_NEEDED → 直接依赖库名（binfmt/elf.py）",
    "pe.exports": "PE 导出表 → 导出符号（binfmt/pe.py）",
    "pe.imports": "PE 导入表 → 直接依赖 DLL 名（binfmt/pe.py）",
    "macho.exports": "Mach-O LC_SYMTAB 外部符号 → 导出符号（binfmt/macho.py）",
    "macho.dylib": "Mach-O LC_LOAD_DYLIB → 直接依赖 dylib 名（binfmt/macho.py）",
    # ── GPU 内容来源（binfmt/gpu.py，R68/R71 已落地）────────────────────
    "gpu.fatbin": "CUDA fatbin → kernel 名（binfmt/gpu.py）",
    "gpu.ptx": "PTX 文本 → kernel 名（binfmt/gpu.py）",
    "gpu.hsaco": "AMD HSACO → kernel 名（binfmt/gpu.py）",
    "gpu.spirv": "Vulkan SPIR-V → kernel 名（binfmt/gpu.py）",
    # ── 桥接（matlabc.py，R72 已有 `--mixed`）──────────────────────────
    "mex.bridge": "MEX 入口 mexFunction → C 实现（matlabc.py `--mixed`，P87）",
}


def is_registered(device_id):
    """`device_id` 是否登记在册。空 id 恒为 False（不是「默认为真」）。"""
    return bool(device_id) and device_id in HOP_DEVICES


def unregistered_devices(ids):
    """返回 `ids` 里**未登记**的那一批（保持输入顺序、去重）。"""
    seen = []
    for d in ids:
        if d not in seen:
            seen.append(d)
    return [d for d in seen if not is_registered(d)]


def census():
    """按前缀分组的直方图（`elf.*` / `pe.*` / …）——**派生量**，不手写数字。"""
    buckets = {}
    for k in HOP_DEVICES:
        p = k.split(".", 1)[0]
        buckets[p] = buckets.get(p, 0) + 1
    return buckets
