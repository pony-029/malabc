# ADR-005: MATLAB→C 走确定性算子映射，未验证是一等状态

- Status: Accepted
- Date: 2026-10-21
- Diagrams: 10-porting

## Context

“让 LLM 直接写 C”无法评审：同一段 MATLAB 每次可能生成不同的 C，
而且没人能证明语义等价。

## Decision

`translate/` 把 MATLAB 语句确定性映射为算子；`c_runtime/` 是 C 落点；
`translate/golden/` 用 golden 对比双侧结果；有编译器时真编译执行；
`port_ledger.json` 逐算子记录 `verified` / 未验证状态。
未验证不是失败，而是**明确的一等状态**，必须被看见。

## Consequences

- 每个算子的状态可审计；新增算子必须先有 golden。
- C 侧接口受 `mlc.h` ABI 契约约束（禁止裸 `double*`）。
- 没有编译器时不会假装 verified。

## Evidence

- `translate/operators.py`
- `translate/fidelity.py`
- `c_runtime/include/mlc.h`
- `port_ledger.json`
- `tools/check_translate_port.py`
