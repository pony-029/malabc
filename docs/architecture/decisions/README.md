# 架构决策记录（ADR）索引

> 每张架构图在 `FLOW_INDEX.json` 的 `adr` 里挂决策；每条 ADR 用 `Diagrams:`
> 反指图，AD11 会检查双向与孤儿。`Status` 只能是 Proposed / Accepted /
> Superseded / Deprecated；`Superseded` 必须与 `Supersedes`/`Superseded by` 互指。

| ADR | Status | Diagrams | 决策 |
| --- | --- | --- | --- |
| [ADR-001](ADR-001-single-file-core.md) | Accepted | 00-overall, 01-entry | 单文件内核 |
| [ADR-002](ADR-002-unified-ir.md) | Accepted | 02-matlab-frontend, 03-multilang-ir, 04-analysis, 05-render, 12-dataflow | 统一 IR |
| [ADR-003](ADR-003-verification-gated-fix-loop.md) | Accepted | 08-fix-loop | 验证门控修复闭环 |
| [ADR-004](ADR-004-thin-editor-client.md) | Accepted | 06-lsp, 07-ai-mcp, 13-sequence | 轻薄编辑器客户端 |
| [ADR-005](ADR-005-deterministic-porting.md) | Accepted | 10-porting | 确定性移植 |
| [ADR-006](ADR-006-gates-as-registry.md) | Accepted | 00-overall, 09-gates | 登记制门禁 |
| [ADR-007](ADR-007-binary-read-only.md) | Accepted | 11-binary | 二进制只读 |
| [ADR-008](ADR-008-architecture-review-record.md) | Accepted | 00-overall | 架构评审记录与发布闸 |

## 替代链示例

[`examples/`](examples/) 里放了一对**示例** ADR（ADR-100 Superseded →
ADR-101 Accepted），用来演示 `Status` 与 `Supersedes`/`Superseded by`
的互指格式。它们**不是项目决策**，也不进 `FLOW_INDEX`；AD11 只扫描本目录
根下的 `ADR-*.md`，因此不会把示例当成孤儿。
| ADR-009 | Rust 用于移植管线（MIR + 发射器），交付物仍是 C | Accepted | [ADR-009-rust-for-port-pipeline.md](ADR-009-rust-for-port-pipeline.md) |
