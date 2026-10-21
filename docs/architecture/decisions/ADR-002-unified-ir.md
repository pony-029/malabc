# ADR-002: 统一 IR 与单一归因点

- Status: Accepted
- Date: 2026-10-21

## Context

MATLAB、C、Python、JavaScript、汇编各自有一套“函数/调用/文件”的形状。
如果每个语言各自解析、各自渲染，同一条告警会在不同出口长出不同口径。

## Decision

`frontends/ir.py` 是唯一的 IR 与归因判定点；`FRONTEND_REGISTRY` 登记每种语言的前端；
`build_analysis_model` 产出的模型同时喂给报告、站点、JSON/SARIF、LSP 与 MCP。
新增语言 = 新增一个 frontend，不是新增一条管线。

## Consequences

- 同一份代码在报告/站点/LSP 里说同一件事。
- 归因错误只需修一个点；`check_ir_attribution` 双向核对。
- 前端必须适配 IR，不能各自定义“函数”形状。

## Evidence

- `frontends/ir.py`
- `unified_graph.py`
- `entity_model.py`
- `tools/check_ir_attribution.py`
