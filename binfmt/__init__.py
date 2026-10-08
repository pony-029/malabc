"""binfmt —— 二进制文件分析：把「看不见的二进制」变成可归因的证据。

本包在本项目的定位（详见 docs/analysis/ANALYSIS_2026-10-08_BINARY_GPU_INTEGRATION.md）：
    不是「多支持一种输入格式」，而是给 renderers/unresolved.py 的**未解析调用**
    提供归属证据 —— 让一个找不到定义的调用能被分成三类：

        源码里调用了 foo()，但定义找不到
                        │
                        ▼
        ┌───────────────────────────────────────────────┐
        │ binfmt 提供证据                                │
        ├───────────────────────────────────────────────┤
        │ ① 来自某个动态库   -> 在导入表/动态符号里        │
        │ ② 来自某个 GPU 算子-> 在 fatbin / HSACO / SPIR-V │
        │ ③ 真的漏了         -> 哪儿都找不到（这才是缺陷）  │
        └───────────────────────────────────────────────┘

数据流（一条直线，没有回头路）：

    path ──▶ sniff()  ──▶ pe / elf / macho 解析器 ──▶ BinaryReport
             │                      │                       │
             │ 魔数识别容器          │ 段/符号/依赖           │
             │                      ▼                       ▼
             │              gpu.analyze()          attribute.py
             │              （可在容器里定位 CUDA      （把源码侧未解析调用
             │                fatbin / HIP HSACO /     归因到这里的证据）
             │                Vulkan SPIR-V 并提取
             │                kernel 名）              report.py 渲染成文本

术语纪律（**两套词不能混用**）：
    kernel  = GPU 算子（CUDA / ROCm / Vulkan 的 device 函数）
    operator/kind = 本项目原有的跨语言检测规则（_CROSS_LANG_KIND_META）
    GPU kernel 一律以 kind="gpu_kernel" 进入 Symbol 表，**不进入算子目录**。

零依赖：全部用标准库（struct / io / os）。pyelftools 只在 tests/ 做差分验证，
缺失时显式 SKIP，**不作运行时依赖**。

诚实边界：
  * 不执行任何二进制，不做反汇编，不做符号执行 —— 只读元数据。
  * 「不可解析」是一等状态：GpuBlob.parseable=False 必须带非空 reason，
    绝不静默变成「没找到算子」。
"""
from .container import parse, sniff
from .model import (
    ATTR_GPU_KERNEL, ATTR_LIBRARY, ATTR_MISSING, ATTR_SOURCE,
    CONTAINER_ELF, CONTAINER_MACHO, CONTAINER_PE,
    DEP_IMPORT_MODULE, DEP_LINK_FLAG, DEP_NEEDED, DEP_RPATH, DEP_RUNPATH,
    BinaryReport, Dependency, GpuBlob, Section, Symbol,
    SYM_DYNAMIC, SYM_EXPORT, SYM_GPU_KERNEL, SYM_IMPORT,
)
from . import attribute, gpu
from .report import to_summary_line, to_text

__version__ = "1.0.0"

__all__ = [
    "parse", "sniff", "to_text", "to_summary_line", "gpu", "attribute",
    "BinaryReport", "GpuBlob", "Section", "Symbol", "Dependency",
    "CONTAINER_PE", "CONTAINER_ELF", "CONTAINER_MACHO",
    "SYM_EXPORT", "SYM_IMPORT", "SYM_DYNAMIC", "SYM_GPU_KERNEL",
    "DEP_NEEDED", "DEP_IMPORT_MODULE", "DEP_RPATH", "DEP_RUNPATH", "DEP_LINK_FLAG",
    "ATTR_SOURCE", "ATTR_LIBRARY", "ATTR_GPU_KERNEL", "ATTR_MISSING",
]
