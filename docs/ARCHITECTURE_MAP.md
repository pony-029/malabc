# malabc 架构图导览（按模块）

> 14 张图的**一页式入口**：总框架 + 11 个模块 + 数据流 + 一次 LSP 请求。
> 可交互版本在 [`architecture/index.html`](architecture/index.html)；英文标签版在
> [`architecture/en/README.md`](architecture/en/README.md)。
> 每张图的源文件是 `architecture/candidates/<id>.json`，产物是 `architecture/html/<id>.html`。

## 总框架

[![00 总框架](architecture/svg/00-overall.svg)](architecture/html/00-overall.html)

## 模块

| # | 图 | 它回答的问题 |
| --- | --- | --- |
| 01 | [![01 入口与 CLI](architecture/svg/01-entry.svg)](architecture/html/01-entry.html) | 一条命令如何走到分析内核？退出码怎么来？ |
| 02 | [![02 MATLAB 前端](architecture/svg/02-matlab-frontend.svg)](architecture/html/02-matlab-frontend.html) | 源码如何变成函数/调用边？unresolved 在哪判定？ |
| 03 | [![03 多语言前端 + IR](architecture/svg/03-multilang-ir.svg)](architecture/html/03-multilang-ir.html) | C/Py/JS/asm 如何归因？IR 的唯一判定点在哪？ |
| 04 | [![04 分析引擎](architecture/svg/04-analysis.svg)](architecture/html/04-analysis.html) | 调用图/影响面/依赖/污点/维度/检查如何共享模型？ |
| 05 | [![05 渲染与输出](architecture/svg/05-render.svg)](architecture/html/05-render.html) | 一份模型如何出五种出口？ |
| 06 | [![06 LSP 与 VS Code](architecture/svg/06-lsp.svg)](architecture/html/06-lsp.html) | 编辑器里的诊断/大纲/跳转从哪来？ |
| 07 | [![07 AI 与 MCP](architecture/svg/07-ai-mcp.svg)](architecture/html/07-ai-mcp.html) | 外部 Agent 如何调用工程理解能力？ |
| 08 | [![08 修复闭环](architecture/svg/08-fix-loop.svg)](architecture/html/08-fix-loop.html) | 修复如何验证/回退/进人工复核/记入记忆？ |
| 09 | [![09 门禁与 CI](architecture/svg/09-gates.svg)](architecture/html/09-gates.html) | 39 道门如何被组织、增量、发版与进 CI？ |
| 10 | [![10 MATLAB→C 移植](architecture/svg/10-porting.svg)](architecture/html/10-porting.html) | 契约/算子/保真/台账如何把 MATLAB 落到 C？ |
| 11 | [![11 二进制分析](architecture/svg/11-binary.svg)](architecture/html/11-binary.html) | PE/ELF/Mach-O/GPU 如何回答“这个名字归谁”？ |

## 数据流、时序与模块边界

| # | 图 | 它回答的问题 |
| --- | --- | --- |
| 12 | [![12 数据流](architecture/svg/12-dataflow.svg)](architecture/html/12-dataflow.html) | 三类输入如何汇成一份模型，再被多种出口消费？ |
| 13 | [![13 一次 LSP 请求](architecture/svg/13-sequence.svg)](architecture/html/13-sequence.html) | 打开文件到大纲/诊断，800ms 超时后怎么兜底？ |
| 14 | [模块边界（Mermaid）](architecture/MODULE_GRAPH.md) | 模块级 import 的跨组边有多少？环在哪？ |

## 维护

> 总框架 `00-overall` 的 HTML 已内嵌源码证据（`archify-source-evidence-data`，
> `verified:true`，30 条 Git 引用）；其余图可按体检清单逐步补 `sources`。

- 新增/修改/删除一张图，按 [`architecture/REVIEW_CHECKLIST.md`](architecture/REVIEW_CHECKLIST.md) 走。
- 中英规范译法见 [`architecture/GLOSSARY.md`](architecture/GLOSSARY.md)（AD9）。
- 版本快照：[`architecture/SNAPSHOTS.json`](architecture/SNAPSHOTS.json)；
  逐图首次/最近提交：[`architecture/VERSIONS.md`](architecture/VERSIONS.md)。
- 汇报用 PNG：[`architecture/png/`](architecture/png/)（14 张）。
- 架构决策记录：[`architecture/decisions/`](architecture/decisions/)（8 条 ADR，
  AD11 检查每张图都挂了决策、Status/Diagrams 双向、且没有孤儿 ADR）。
- 评审记录：[`architecture/REVIEWS.md`](architecture/REVIEWS.md)（版本 / 复核人 / 结论）。
- 图的可编辑源在 `architecture/candidates/`；不要手改 `html/` 或 `svg/`。
- 重新生成：`python tools/export_arch_svg.py --all`；英文版：`python tools/build_arch_svg_en.py`。
