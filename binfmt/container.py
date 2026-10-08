"""binfmt 入口：容器识别、分发、统一报告组装。

对外 API（三个，别扩散）：
    sniff(path)                                 -> "pe" | "elf" | "macho" | ""
    parse(path, scan_cap=..., with_gpu=True)    -> BinaryReport
    to_text(rep) -> str                          （见 report.py）

识别与分发（魔数互不冲突，唯一边界见下）：

    文件头 4096 字节
         │
         ├─ \\x7fELF ─────────────▶ elf.parse()
         ├─ MZ ......... PE\\0\\0 ──▶ pe.parse()
         ├─ feedface/feedfacf ───▶ macho.parse()      （thin）
         └─ cafebabe ────────────▶ 先消歧 ─┬─ 像 fat ─▶ macho.parse()
                                          └─ 不像   ─▶ ""（是 Java class，不认）
         │
         └─ 都不像 ─▶ BinaryReport + notes（说明支持什么、GPU 二进制该指哪）
         │
         ▼
      with_gpu=True 时追加 gpu.analyze()：在容器里定位 CUDA/HIP/Vulkan 内容

设计纪律：
  * 全流程 seek + 定长 read，单次 I/O <= MAX_CHUNK（防大文件把内存打爆）。
  * 解析失败返回「部分结果 + notes」，**不抛异常**（除文件本身不可读）——
    半个答案加一句说明，好过一个栈回溯。
  * GPU 分析是可关闭的独立阶段（with_gpu=False 时只解析容器）。
  * 唯一已知歧义：Mach-O fat 的 0xCAFEBABE 与 Java class 撞车，用 fat 结构
    合理性（nfat_arch + 各 arch 的 offset/size 是否落在文件内）消歧。
"""
import io
import os

from . import elf, macho, pe, gpu
from .model import (
    CONTAINER_ELF, CONTAINER_MACHO, CONTAINER_PE, BinaryReport,
)

HEAD_BYTES = 4096


def sniff(path):
    """识别容器类型。三者魔数互不冲突；唯一边界是 Mach-O fat 的
    0xCAFEBABE 与 Java class 撞车，用 fat 结构合理性消歧。"""
    try:
        with io.open(path, "rb") as f:
            head = f.read(HEAD_BYTES)
    except OSError:
        return ""
    if elf.sniff(head):
        return CONTAINER_ELF
    if pe.sniff(head):
        return CONTAINER_PE
    if macho.thin_magic(head):
        return CONTAINER_MACHO
    if macho.fat_magic(head):
        try:
            fsize = os.path.getsize(path)
        except OSError:
            fsize = 0
        if macho.looks_like_fat(head, fsize):
            return CONTAINER_MACHO
        return ""       # 疑似 Java class，不认
    return ""


def parse(path, scan_cap=gpu.DEFAULT_SCAN_CAP, with_gpu=True):
    """解析一个二进制文件。文件不存在/不可读时抛 OSError（调用方负责）。"""
    if not os.path.isfile(path):
        raise OSError("文件不存在: %s" % path)
    kind = sniff(path)
    if kind == CONTAINER_PE:
        rep = pe.parse(path, scan_cap=scan_cap)
    elif kind == CONTAINER_ELF:
        rep = elf.parse(path, scan_cap=scan_cap)
    elif kind == CONTAINER_MACHO:
        rep = macho.parse(path, scan_cap=scan_cap)
    else:
        rep = BinaryReport(path=path)
        try:
            with io.open(path, "rb") as f:
                head = f.read(16)
        except OSError:
            head = b""
        rep.notes.append("binfmt: 无法识别的容器类型（前 16 字节 %s）"
                         % head.hex(" "))
        rep.notes.append("binfmt: 当前支持 PE / ELF / Mach-O；"
                         "若这是 GPU 二进制（.cubin/.ptx/.hsaco/.spv），"
                         "它应被包在某个容器里，请直接指向该容器文件")
        return rep
    if with_gpu:
        gpu.analyze(rep, path, scan_cap=scan_cap)
    return rep
