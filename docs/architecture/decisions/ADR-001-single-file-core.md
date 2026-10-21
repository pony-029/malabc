# ADR-001: 单文件内核，零第三方依赖

- Status: Accepted
- Date: 2026-10-21

## Context

matlabc 需要在一台只装了 Python 3.6.5 的机器上直接运行，且要能单文件分发。
早期试过拆包，但部署方经常把整个目录拷来拷去，路径一漂就找不到模块。

## Decision

保留 `matlabc.py` 作为单文件内核（解析/模型/分析/渲染入口都在里面）；
`frontends/`、`renderers/`、`analyzer/` 只是可选的薄模块，不引入任何第三方依赖。
文件过大用 `docs/matlabc_STRUCTURE.md` 的结构索引来缓解，而不是拆包。

## Consequences

- 部署只需一个 `matlabc.py`；3.6.5 可跑。
- 单文件会持续变大（当前 ~3.3 万行），靠结构索引与门禁约束组织。
- 任何“为了优雅而拆包”的改动都必须先回答：部署方能不能接受多文件。

## Evidence

- `matlabc.py`
- `docs/matlabc_STRUCTURE.md`
- `tools/check_py36_clean.py`
