# ADR-008: 架构评审记录与发布闸

- Status: Accepted
- Date: 2026-10-21
- Diagrams: 00-overall

## Context

快照和逐图版本记录能回答“图什么时候变”，但回答不了“这次变更谁看过、
结论是什么”。发布时如果只靠口头确认，评审就不可追溯。

## Decision

每次发布在 `docs/architecture/REVIEWS.md` 留一行：
版本 / 日期 / 变更图 / 复核人 / 结论（pass/warn/fail）/ 备注。
`tools/record_arch_review.py --check` 要求当前 `matlabc.py` 版本有评审行；
`tools/release_arch_check.py` 在发布闸里同时跑快照、版本记录、PNG 与评审记录。

## Consequences

- 评审从“一次性动作”变成可追溯记录。
- 版本升了但没评审，发布闸会红。
- 评审结论不替代 ADR；ADR 解释“为什么”，REVIEWS 记录“谁在何时确认”。

## Evidence

- `docs/architecture/REVIEWS.md`
- `tools/record_arch_review.py`
- `tools/release_arch_check.py`
