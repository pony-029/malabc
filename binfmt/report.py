"""binfmt 文本报告渲染（给 CLI 用）。

一份报告长这样（节选示意）：

    == <path>  [elf/x86_64]  ==
    sections : 31      （有 GPU 相关段的用 * 标出）
    symbols  : 1284 export / 96 import / 171 gpu_kernel
    deps     : libc.so.6, libstdc++.so.6, ...
    * GPU
      backends          : cuda
      parseable         : yes
      suspect objects   : 412      <- 便宜判据（数 \\x7fELF）
      kernels (named)   : 171      <- 精确判据（节名表 .text._Z）
      preview           : cublas…splitKreduce_kernel, …

渲染纪律（**不隐藏负面状态**）：
  * parseable=False 的 GPU blob **必须显示出来**，且带原因 —— 不可解析
    和「没有 GPU 内容」是两件事，前者意味着我们的结论不可靠。
  * suspect（便宜判据）与 confidence（严格判据）**分两列**显示，绝不合并。
  * 截断 / 预算耗尽一律进「Note」区，**不静默**（探针 limit=5 的教训）。
"""
from .model import SYM_EXPORT, SYM_GPU_KERNEL, SYM_IMPORT, SYM_DYNAMIC


def _human(n):
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KiB" % (n / 1024.0)
    if n < 1024 * 1024 * 1024:
        return "%.1f MiB" % (n / (1024.0 * 1024))
    return "%.2f GiB" % (n / (1024.0 * 1024 * 1024))


def to_text(rep, max_kernels=20, max_sections=40, max_deps=30):
    L = []
    L.append("=" * 78)
    L.append("file      : %s" % rep.path)
    L.append("container : %s   arch=%s   bits=%d   endian=%s   flavour=%s"
             % (rep.container or "?", rep.arch or "?", rep.bits,
                rep.endian or "?", rep.flavour or "?"))
    L.append("symbols   : %d   dependencies: %d   gpu_blobs: %d"
             % (len(rep.symbols), len(rep.dependencies), len(rep.gpu_blobs)))
    # R33/C'5 + R36/C''6：验证等级必须出现在**报告里**，不能只写在源码 docstring 里。
    # 报告是用户唯一会读的东西；声明在那儿看不到，等于没说。
    # 两条轴分开写：「无真实语料」与「无任何验证」是**不同**的话 ——
    # 前者意味着合成夹具已经过了，后者意味着连夹具都没有。
    if not getattr(rep, "verified", True):
        _fx = getattr(rep, "fixture_verified", False)
        if _fx:
            L.append("verified  : NO  ⚠ 未验证（无**真实语料**，本机无该容器样本）"
                     "；已过合成夹具 —— 结论仅供参考")
        else:
            L.append("verified  : NO  ⚠ 未验证（**既无真实语料也无合成夹具**）"
                     " —— 结论仅供参考")
    L.append("=" * 78)

    if rep.sections:
        L.append("")
        L.append("sections (%d):" % len(rep.sections))
        L.append("  %-14s %12s %12s  %s" % ("name", "vsize", "file_off", ""))
        for s in rep.sections[:max_sections]:
            mark = "  <== GPU (%s)" % s.gpu_hint if s.gpu_hint else ""
            L.append("  %-14s %12s %12d  %s%s"
                     % (s.name, _human(s.vsize), s.file_off, s.kind, mark))
        if len(rep.sections) > max_sections:
            L.append("  ... 另有 %d 个段未显示" % (len(rep.sections) - max_sections))

    if rep.gpu_blobs:
        L.append("")
        L.append("GPU content (%d blob):" % len(rep.gpu_blobs))
        for b in rep.gpu_blobs:
            state = "parseable" if b.parseable else "NOT-PARSEABLE"
            L.append("  [%s] backend=%s section=%s via=%s size=%s"
                     % (state, b.backend or "?", b.section,
                        b.detected_by, _human(b.size)))
            L.append("       kernels=%(k)d  uniq=%(u)d  index_entries=%(i)d"
                     "  suspect_co=%(s)d  confidence_co=%(c)d%(t)s"
                     % {"k": len(b.kernels), "u": len(set(b.kernels)),
                        "i": b.index_entries, "s": b.suspect_code_objects,
                        "c": b.confidence_code_objects,
                        "t": "  [TRUNCATED]" if b.truncated else ""})
            if b.reason:
                L.append("       reason: %s" % b.reason)
            for t in b.targets[:10]:
                L.append("       target: %s" % t)
            shown = 0
            for k in sorted(set(b.kernels)):
                if shown >= max_kernels:
                    break
                dm = ""
                if k.startswith("_Z"):
                    from .gpu import demangle_itanium
                    d = demangle_itanium(k)
                    if d:
                        dm = "   -> %s" % d
                L.append("       kernel: %s%s" % (k, dm))
                shown += 1
            rest = len(set(b.kernels)) - shown
            if rest > 0:
                L.append("       ... 另有 %d 个独立 kernel 名未显示" % rest)
    else:
        L.append("")
        L.append("GPU content: 无（未发现 GPU 段名，magic 兜底也未命中）")

    if rep.dependencies:
        L.append("")
        L.append("dependencies (%d):" % len(rep.dependencies))
        for d in rep.dependencies[:max_deps]:
            L.append("  %-16s %s" % (d.kind, d.name))
        if len(rep.dependencies) > max_deps:
            L.append("  ... 另有 %d 条未显示" % (len(rep.dependencies) - max_deps))

    counts = {}
    for s in rep.symbols:
        counts[s.kind] = counts.get(s.kind, 0) + 1
    if counts:
        L.append("")
        L.append("symbol kinds: " + "  ".join("%s=%d" % kv for kv in sorted(counts.items())))
        ex = [s.name for s in rep.symbols if s.kind == SYM_EXPORT][:10]
        if ex:
            L.append("  sample exports: %s" % ", ".join(ex))
        gk = [s.name for s in rep.symbols if s.kind == SYM_GPU_KERNEL][:10]
        if gk:
            L.append("  sample gpu_kernel: %s" % ", ".join(gk))

    if rep.notes:
        L.append("")
        L.append("notes (%d):" % len(rep.notes))
        for n in rep.notes:
            L.append("  - %s" % n)

    return "\n".join(L)


def to_summary_line(rep):
    """一行摘要，给批量扫描用。"""
    gpu = ""
    if rep.gpu_blobs:
        parts = []
        for b in rep.gpu_blobs:
            parts.append("%s:%s%s" % (b.backend or "?",
                                      len(b.kernels),
                                      "" if b.parseable else "!"))
        gpu = "gpu[" + ",".join(parts) + "]"
    return "%-10s %-10s %-8s sym=%-6d dep=%-4d %s%s" % (
        rep.container or "?", rep.arch or "?", rep.flavour or "?",
        len(rep.symbols), len(rep.dependencies), gpu,
        "" if getattr(rep, "verified", True) else
        ("  [UNVERIFIED/NO-CORPUS]" if getattr(rep, "fixture_verified", False)
         else "  [UNVERIFIED/NONE]"))
