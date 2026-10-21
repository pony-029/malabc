# ADR-007: 二进制分析只读元数据，不执行、不反汇编

- Status: Accepted
- Date: 2026-10-21

## Context

分析 PE/ELF/Mach-O/GPU 容器时，执行样本或反汇编会带来安全与可移植性风险；
而多数问题（“这个符号归谁”“依赖了谁”）只需要元数据就能回答。

## Decision

`binfmt/` 只读容器/段/节/依赖/导出表；`binhops.py`/`callrel.py` 读跳转与调用关系；
输出三态 `library / gpu_kernel / missing`；不可解析是一等状态，不猜测。

## Consequences

- 分析器可以安全地跑在不可信样本上。
- 无法回答“这段代码做了什么”，只能回答“它声明了什么”。
- 归属结论必须带依据，不能从名字反推实现。

## Evidence

- `binfmt/pe.py`
- `binfmt/elf.py`
- `binfmt/macho.py`
- `binfmt/gpu.py`
- `binhops.py`
