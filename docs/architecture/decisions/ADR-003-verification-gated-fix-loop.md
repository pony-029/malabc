# ADR-003: 修复闭环必须验证门控，失败必回退

- Status: Accepted
- Date: 2026-10-21

## Context

自动修复（尤其 LLM 生成的补丁）可能在“减少一条告警”的同时引入新问题。
如果直接落地，用户看到的不是修复，而是更难回滚的破坏。

## Decision

修复按“应用 → 确定性重扫 → 自证”走：
- 只有“无新增告警且总数下降”才接受；
- 否则回退到基线，换策略重试，穷尽轮次后进 tier-2 检查点；
- `--review-gate` 下即使验证通过也不自动落地，改出审查产物并 exit 3；
- `--draft-pr` 可把候选补丁开成 Draft PR，`gh` 缺失时优雅降级。

## Consequences

- 闭环不会无限循环，也不会把未验证的补丁留在工作区。
- 每轮都有可复核的 patch/JSON/MD 产物。
- 验证失败不是“工具坏了”，而是明确的人工检查点。

## Evidence

- `agent_loop.py`
- `matlabc_flow.py`
- `docs/matlabc_USAGE.md` 2.2.4
- `tools/check_architecture_docs.py`（架构图 08）
