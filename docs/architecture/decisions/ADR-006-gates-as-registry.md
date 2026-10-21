# ADR-006: 门禁是登记制，每道门必须自证

- Status: Accepted
- Date: 2026-10-21

## Context

“加一条检查”最容易变成“写了一段永远返回 0 的代码”。
没有对手方的门禁，比没有门禁更危险：它给人虚假的安全感。

## Decision

每道 `tools/check_*.py` 必须：
- 有 `--selftest`，且自证里至少有一个“必须红”的样本；
- 在 `check_all`、README 质量门表、帮助正文里登记；
- 退出码契约由 `check_help_contract` 双向核对；
- 数字（N 道门/N 个工具）由门自己现算，不手写。

## Consequences

- 加门有固定清单（README/help/ASCII/计数），不会“加了但没人跑”。
- 门本身也会被门检查（`check_help_contract` / `check_readme_parity`）。
- 代价是元数据多，但这正是“可证明”的成本。

## Evidence

- `tools/check_all.py`
- `tools/check_help_contract.py`
- `tools/check_readme_parity.py`
- `tools/check_tool_discoverability.py`
