# malabc 架构图（archify）

> 本目录用 **archify** 画出 malabc 的**总框架 + 11 个模块 + 数据流 + 时序**（14 张）。
> 每张图都是 `candidate.json`（可编辑源）+ `.html`（可交互产物）+ `.svg`（独立矢量），不是截图。
>
> 生成器：`D:\work\rea\archify`（`archify render / validate / check`）。
> 图型：`architecture`（组件/连线）、`workflow`（工序/分支）、`lifecycle`（状态机）、
> `dataflow`（数据管线）、`sequence`（调用时序）。

---

## 1. 一眼看懂：14 张图

| # | 图 | 类型 | 文件 | 它回答的问题 |
| --- | --- | --- | --- | --- |
| 00 | **总框架** | architecture | [html/00-overall.html](html/00-overall.html) | 这个工程由哪些层/模块组成？主干怎么走？ |
| 01 | 入口与 CLI | workflow | [html/01-entry.html](html/01-entry.html) | 一条命令如何走到分析内核？退出码怎么来？ |
| 02 | MATLAB 前端 | workflow | [html/02-matlab-frontend.html](html/02-matlab-frontend.html) | 源码如何变成函数/调用边？unresolved 在哪判定？ |
| 03 | 多语言前端 + IR | workflow | [html/03-multilang-ir.html](html/03-multilang-ir.html) | C/Py/JS/asm 如何归因？IR 的唯一判定点在哪？ |
| 04 | 分析引擎 | architecture | [html/04-analysis.html](html/04-analysis.html) | 调用图/影响面/依赖/污点/维度/检查如何共享模型？ |
| 05 | 渲染与输出 | workflow | [html/05-render.html](html/05-render.html) | 一份模型如何出五种出口（报告/站点/JSON/SARIF/补丁）？ |
| 06 | LSP 与 VS Code | architecture | [html/06-lsp.html](html/06-lsp.html) | 编辑器里的诊断/大纲/跳转从哪来？ |
| 07 | AI 与 MCP | architecture | [html/07-ai-mcp.html](html/07-ai-mcp.html) | 外部 Agent 如何调用工程理解能力？离线怎么降级？ |
| 08 | 修复闭环 | lifecycle | [html/08-fix-loop.html](html/08-fix-loop.html) | 修复如何验证/回退/进人工复核/记入记忆？ |
| 09 | 门禁与 CI | workflow | [html/09-gates.html](html/09-gates.html) | 39 道门如何被组织、增量、发版与进 CI？ |
| 10 | MATLAB→C 移植 | architecture | [html/10-porting.html](html/10-porting.html) | 契约/算子/保真/台账如何把 MATLAB 落到 C？ |
| 11 | 二进制分析 | architecture | [html/11-binary.html](html/11-binary.html) | PE/ELF/Mach-O/GPU 如何回答“这个名字归谁”？ |
| 12 | **数据流** | dataflow | [html/12-dataflow.html](html/12-dataflow.html) | 三类输入如何汇成一份模型，再被多种出口消费？ |
| 13 | **一次 LSP 请求** | sequence | [html/13-sequence.html](html/13-sequence.html) | 打开文件到大纲/诊断，800ms 超时后怎么兜底？ |

索引页：[`index.html`](index.html)。

**独立 SVG**：每张图的矢量版在 `svg/<id>.svg`（14 个，样式已裁剪为 ~4–5 KB，
可直接嵌入 Markdown）；总框架 `svg/00-overall.svg` 已嵌入根 `README_CN.md`。

**英文版**：`en/svg/<id>.svg`（14 张，英文标签；由 `tools/build_arch_svg_en.py`
构建，说明见 [`en/README.md`](en/README.md)）；英文 README 使用 `en/svg/00-overall.svg`。

**一页式导览**：[`../ARCHITECTURE_MAP.md`](../ARCHITECTURE_MAP.md)（按模块嵌入 14 张图）；
**模块边界**：[`MODULE_GRAPH.md`](MODULE_GRAPH.md)（Mermaid，边由 import graph 现算）；
**评审清单**：[`REVIEW_CHECKLIST.md`](REVIEW_CHECKLIST.md)（新增/修改/删除各要过哪些门）；
**术语表**：[`GLOSSARY.md`](GLOSSARY.md)（AD9 的中英规范译法 + 机器块）；
**快照/版本**：[`SNAPSHOTS.json`](SNAPSHOTS.json) · [`VERSIONS.md`](VERSIONS.md)；
**PNG**：[`png/`](png/)（14 张，汇报/幻灯片用）；
**决策记录**：[`decisions/`](decisions/) · [索引](decisions/README.md)（8 条 ADR：单文件内核 / 统一 IR / 验证门控闭环 / 轻薄编辑器 / 确定性移植 / 登记制门禁 / 二进制只读 / 评审记录；另有 1 对替代链示例）。
**评审记录**：[`REVIEWS.md`](REVIEWS.md)（版本 / 日期 / 变更图 / 复核人 / 结论）。

---

## 2. 逐模块说明

### 00 总框架

- **入口**：`matlabc_boot.py` 路由 CLI / ask / flow / GUI；真正内核是单文件 `matlabc.py`。
- **前端**：MATLAB（`parse_file`/`analyze_calls`）+ 多语言（`FRONTEND_REGISTRY`/`frontends/ir.py`）。
- **模型/分析**：`entity_model.py`、`unified_graph.py`、`facts.py` + 调用/影响面/污渍/维度/检查。
- **四种出口**：`renderers/` 报告与站点、`matlabc_lsp.py` 编辑器、`matlabc_mcp.py` Agent、`matlabc_flow.py` 修复闭环。
- **两条新线**：`translate/ + c_runtime/`（MATLAB→C）、`binfmt/`（二进制元数据）。
- **门禁**：`tools/check_*.py` + `check_all.py` + `.github/workflows/`。

### 01 入口与 CLI

- `matlabc_boot.py` 只做路由；`matlabc.py` 负责 argparse、配置合并、扫描、分析、输出。
- 配置优先级：CLI 显式参数 > `analyzer_config.json` > 内置默认。
- 模式：`analyze` / `--html` / `--browse` / `--json` / SARIF / patch / `--mcp` / `--lsp` / `--flow` / GUI。
- 退出码：`0=ok`、`1=error`、`2=unimplemented`；由 `check_help_contract` 双向核对。

### 02 MATLAB 前端

- `scrub_source`：注释/字符串替换为空格，**保留换行与行号**。
- `_logical_statements`：合并 `...` 续行，避免跨行调用漏检。
- `parse_file`：识别 `function`/`classdef`/块/两种 `end` 风格，产出 `MatlabFile/Function/Class`。
- `analyze_calls` / `resolve_call`：建项目内调用边 + 外部调用计数。
- `frontends/matlab.py`：MATLAB 侧 **unresolved 的唯一判定点**（`external_calls` 形状，不许抹平）。

### 03 多语言前端 + IR

- `FRONTEND_REGISTRY`：`lang → Frontend 类`；C/Py/JS/asm 各自一个前端。
- C：`_parse_c_source` / `build_c_model`；Py：`pyast_frontend`；JS：行锚定 + 跨行/箭头形态。
- `frontends/ir.py::resolve_calls`：C/Py/JS 共用「解析不到的调用」判定点。
- `IR_LANG_OWNERS`：每语言谁负责 unresolved；`check_ir_attribution` 两向核对。
- `binfmt/` 提供导出表/内核名，帮助 `mex`/`calllib` 边界归因（只读元数据，不执行）。

### 04 分析引擎

- 调用图：`build_call_graph` + `callers_of/calls_of`；影响面：上游/下游闭包。
- 依赖：`#include` / `addpath` / 文件级边；污点：源/汇站点 + 变量级/字段级传播。
- 维度：`_make_dims_probe_script` + 内置函数维度引擎；检查：未初始化/死代码/缺文档/风险。
- 复杂度/热点：圈复杂度 × 调用者数；重复：函数级指纹。
- `facts.py`：结论 ⇄ 位置，可重放；`unified_graph.py`：跨语言节点/边/规则统一图。

### 05 渲染与输出

- `build_analysis_model` 是统一数据层，`renderers/` 只消费它。
- 单页：Markdown / `--html`（内嵌调用图，`report.css` + `app.js` 同源）。
- 多页：`--browse` 站点（`index/src/funcs/deps/dir/rule`，四语言同形）。
- 机器数据：`--json`（full/summary/compact）、SARIF 2.1.0、`--export-doxygen-xml`。
- 修复产物：patch、测试骨架、PR 描述草稿。
- 纪律：页面外链了什么，就必须把那个文件写出来（无死链）。

### 06 LSP 与 VS Code

- `vscode/extension.js`：命令、视图、CodeLens、关系侧栏；`lspClient.js` 是零 npm 的手写客户端。
- `matlabc_lsp.py`：stdio JSON-RPC；`initialize/didOpen/didSave`、`documentSymbol`、`definition`、`references`、`hover`、`semanticTokens`。
- `analyzer/api.analyze` 产出 `PipelineResult`；`_load_cache/_save_cache` 缓存结构层 + 诊断。
- 大纲：800ms 超时后本地兜底（脚本按 `%%` 分节；无分节用文件名），缓存命中缺 `source_lines` 时回读磁盘。

### 07 AI 与 MCP

- `matlabc_mcp.py`：stdio MCP server，工具 `stats/outline/search/explain/impact/gen_patch`。
- `matlabc_ask.py`：自然语言问答；`ai_cli.py`：多供应商（deepseek/qwen/zhipu/moonshot/…）。
- `matlabc_flow.py`：LLM 修复源（无 key 时退回确定性补丁）；`analyzer_memory.py`：误报抑制 + learned_fixes。
- AI 只吃 `unmapped`/无策略的输入，不替代确定性段。

### 08 修复闭环

- `agent_loop.py`：基线分析 → 尝试循环 → `fix_source` → 应用 → **重扫验证** → 接受/回退。
- 验证判据：`no_new_alerts && progress`；失败用 `git apply -R` 或快照恢复，绝不留下半截。
- 出口：tier 0（无事）/ tier 1（已验证）/ tier 2（检查点 + 可选 Draft PR）。
- `--review-gate`：验证通过也不落地，回退并产出审查产物，`exit 3`。
- 记忆：只有接受后才 `record_learned_fix`。

### 09 门禁与 CI

- `tools/check_all.py` 自动发现并运行 `tools/check_*.py`（当前 39 道），每道门必须 `--selftest` 两向自证。
- `gate_cache.py`：指纹命中则复用结论（只省时间，不省凭据）。
- `release.py` 的 `GATES` 是发版清单；`check_release_gates` 守“写了却从没跑过”。
- CI：`ci.yml`（Windows 主链路）+ `port-ci.yml`（ubuntu/windows，`--require-c`）。
- 手工门：`lsp_selftest.py`、`sweep_cli.py`（不进 `check_all`，避免拖慢）。

### 10 MATLAB→C 移植

- `translate/operators.py`：11 个算子（add/sub/mul/div/sum/mean/max/min/index/transpose/matmul）。
- `translate/adapters.py`：ADP-1/2/3（名字/arity、dtype/rank、错误映射），生成两侧胶水。
- `translate/fidelity.py` + `translate/golden/`：11 个 golden；有编译器时**真编译执行**。
- `c_runtime/include/mlc.h`：ABI 契约（`mlc_array`/`mlc_status`/`owns_data`，禁止裸 `double*`）。
- `c_runtime/src/mlc_ops.c`：9 个算子已 `verified`（MinGW gcc 16.2.0 真编译）；transpose/matmul 仍 `MLC_UNIMPLEMENTED`。
- `port_ledger.json`：逐算子状态；`--sync-ledger` 只按 C 结果升级。
- `translate/contracts/matlab_c_constraints.json`：双侧约束（1-based/列主序/隐式扩展/UB/错误模型）。

### 11 二进制分析

- `binfmt/pe.py` / `elf.py` / `macho.py`：依赖、导出表、段/节元数据。
- `binfmt/gpu.py`：CUDA fatbin/cubin、AMD HSA、Vulkan SPIR-V 的 kernel 名。
- `binhops.py` / `callrel.py`：跳转/调用关系；`attribute.py` / `resolve.py`：名字归属。
- `--binary-attach`：把二进制读数接到源码分析；输出三态 `library / gpu_kernel / missing`。
- 纪律：**不执行、不反汇编**；不可解析是一等状态。

### 12 数据流

- 三类输入：工程源码（`.m/.c/.py/.js`）、配置/快照、二进制元数据。
- 三列前端：MATLAB `parse_file`、多语言 `frontends/ir.py`、`binfmt`（只读依赖/导出表）。
- 三列模型：`entity_model` / `unified_graph` / `facts`；分析侧共享 `build_analysis_model`。
- 消费侧：报告/站点、JSON/SARIF、LSP/MCP——新增出口只写渲染器，不改分析内核。

### 13 一次 LSP 请求

- 正常路径：打开文件 → `initialize` → `run_pipeline` → `documentSymbol` → 大纲。
- 缓存：`_load_cache` 命中时不必重新解析；诊断与大纲共享同一份模型。
- 800ms：客户端超时不是“工具坏了”，而是切到本地兜底；兜底按 `%%` 分节，
  无分节时显示文件名，绝不返回空白大纲。

---

## 2.5 模块归属（主文件 / 最近提交）

| 模块 | 主文件 | 最近提交 |
| --- | --- | --- |
| 00 总框架 | `matlabc.py` · `matlabc_boot.py` | `5ffcc7e` 2026-10-22 |
| 01 入口与 CLI | `matlabc.py` · `matlabc_boot.py` · `matlabc_help.py` · `gui.py` | `5ffcc7e` 2026-10-22 |
| 02 MATLAB 前端 | `matlabc.py` · `frontends/matlab.py` | `5ffcc7e` 2026-10-22 |
| 03 多语言 + IR | `frontends/ir.py` · `matlabc.py` · `pyast_frontend.py` | `5ffcc7e` 2026-10-22 |
| 04 分析引擎 | `matlabc.py` · `facts.py` · `entity_model.py` · `unified_graph.py` | `5ffcc7e` 2026-10-22 |
| 05 渲染与输出 | `renderers/` · `matlabc.py` | `5ffcc7e` 2026-10-22 |
| 06 LSP + VS Code | `matlabc_lsp.py` · `vscode/` | `f198b08` 2026-10-22 |
| 07 AI / MCP | `matlabc_mcp.py` · `matlabc_ask.py` · `ai_cli.py` | `6a03133` 2026-10-20 |
| 08 修复闭环 | `agent_loop.py` · `matlabc_flow.py` · `analyzer_memory.py` | `2caf526` 2026-10-10 |
| 09 门禁 / CI | `tools/` · `.github/workflows/` | `174aa34` 2026-10-22 |
| 10 MATLAB→C 移植 | `translate/` · `c_runtime/` · `port_ledger.json` | `f198b08` 2026-10-22 |
| 11 二进制分析 | `binfmt/` · `binhops.py` · `callrel.py` | `6cf824b` 2026-10-13 |

> 最近提交由 `git log -1 --format='%h %ad' --date=short -- <主文件>` 现算；
> 改动主文件后重跑即可，不要手写提交号。
>
> 责任人落点：`.github/CODEOWNERS`。`check_architecture_docs.py` 的 AD7 会逐条
> 核对关键模块是否都有 owner，且 owner 必须以 `@` 开头。

---

## 3. 如何重新生成

```bash
# 1) 校验 candidate（14/14 必须 ok）
node D:/work/rea/archify/archify/bin/archify.mjs validate architecture \
  docs/architecture/candidates/00-overall.json --quality showcase

# 2) 渲染（注意：本机 D: 同卷硬链接发布会报 “multiple hard-link names”，
#    先渲染到 C: 临时目录，再复制回 docs/architecture/html/）
node D:/work/rea/archify/archify/bin/archify.mjs render architecture \
  docs/architecture/candidates/00-overall.json %TEMP%/00-overall.html --quality showcase
copy %TEMP%/00-overall.html docs/architecture/html/00-overall.html

# 3) 产物校验
node D:/work/rea/archify/archify/bin/archify.mjs check \
  docs/architecture/html/00-overall.html

# 4) 导出瘦身 SVG（中文）与英文标签 SVG
python tools/export_arch_svg.py --all
python tools/build_arch_svg_en.py

# 5) 改图后看 base/head 版式差异（delta HTML + receipt）
python tools/arch_compare.py --id 00-overall

# 6) 发布前冻结快照/版本、导出 PNG、补源码证据
python tools/snapshot_arch.py --write
python tools/build_arch_versions.py --write
python tools/export_arch_png.py --all
python tools/apply_arch_sources.py --write

# 7) 发布评审：快照 diff / PNG diff / 发布总闸
python tools/snapshot_arch.py --diff 1.16.72 current
python tools/export_arch_png.py --baseline      # 当前 png/ 冻结为基线
python tools/diff_arch_png.py --max-ratio 0.005 --fail-on-change
python tools/release_arch_check.py --check
```

> 纯 Python 快跑门在 `.github/workflows/arch-docs.yml`：AD1–AD11、SVG 哈希清单、
> 英文 SVG、模块边界图、归属表、版本快照、逐图版本、PNG 存在性、源码证据、评审记录、
> 中英 README 对等、行尾约定；不依赖 archify/Node。

### 换一台电脑

- **只读 / 评审**：`git clone` 后直接打开 `index.html` 或 README 里的 SVG，
  不需要 archify / Node；纯 Python 门可直接跑：
  `python tools/release_arch_check.py --check`。
- **要重新渲染**：安装 Node + archify，设置环境变量 `ARCHIFY_BIN` 指向
  `archify.mjs`（Windows `set ARCHIFY_BIN=...`，macOS/Linux `export ARCHIFY_BIN=...`）。
  仓库里的 `D:/work/rea/archify` 只是本机默认值，不是硬依赖。
- **换机可复现**：克隆后跑 `check_architecture_docs` + `release_arch_check`
  全绿，说明提交的 HTML/SVG/PNG/清单自足；`apply_arch_sources --check`
  会用克隆里的 Git 历史验证 revision。CI 另有
  [`.github/workflows/fresh-clone.yml`](../../.github/workflows/fresh-clone.yml)
  在全新 checkout 上重复这套门。

类型映射：

| 图 | 类型 |
| --- | --- |
| 00 / 04 / 06 / 07 / 10 / 11 | `architecture` |
| 01 / 02 / 03 / 05 / 09 | `workflow` |
| 08 | `lifecycle` |
| 12 | `dataflow` |
| 13 | `sequence` |

---

## 4. 验证证据（本轮实跑）

| 检查 | 结果 |
| --- | --- |
| `archify validate`（14 个 candidate） | **14/14 ok**（12 张 architecture/workflow/lifecycle 走 showcase；dataflow/sequence 走 standard，0 errors） |
| `archify render`（14 张） | **14/14 成功** |
| `archify check`（14 个 HTML） | **14/14 通过** |
| 独立 SVG（14 个） | **14/14 XML 解析通过**；CSS 裁剪到 **4–5 KB**（丢弃 @font-face，靠系统等宽兜底） |
| SVG 渲染烟测 | `00-overall` 1444×744 **3585 色 / 40.89% 非白**；`12-dataflow` 980×520 **4430 色 / 57.57%**；`13-sequence` 1020×700 **3752 色 / 63.04%** |
| SVG 体积 | **3.7 MB → 353 KB**（约 10.5×，单张 17–41 KB） |
| 架构文档门 | `python tools/check_architecture_docs.py` → **OK（AD1–AD11）** |
| 离线版式（AD6） | 14/14：viewBox（dataflow/sequence）、id 唯一、连线端点已知、sequence y≥160 且间距≥28、标签长度 |
| 责任人（AD7） | 13 个关键模块全部有 `.github/CODEOWNERS` 负责人，owner 均为 `@pony-029` |
| 图片路径（AD3） | 根 README 的本地图片全部存在；总框架中文/英文各嵌各的图 |
| 陈旧门 | `python tools/export_arch_svg.py --check` → **OK（14 条清单与 candidate/html/svg 一致）** |
| 快跑 CI | `.github/workflows/arch-docs.yml`（AD1–AD11 + 清单 + 英文 SVG + 模块图 + 归属表 + 快照 + 版本记录 + PNG + PNG 基线 + 评审记录 + 源码证据 + README 对等 + 行尾）；YAML 可解析：1 job / 15 steps |
| ADR（AD11） | **8 条**（含 ADR-008 评审记录）；14 张图挂 `adr`；`Status`/`Diagrams` 双向；`decisions/README.md` 全登记；无孤儿 |
| 替代链示例（R39） | `decisions/examples/`：ADR-100 Superseded ⇄ ADR-101 Accepted，**双向互指** |
| 发布总闸（R32/R40） | `release_arch_check.py --check` → 快照/版本/PNG/基线/评审 **5/5 OK** |
| 自动上一版本（R41） | `--diff`（无参）→ 无上一版本时安全跳过；`--selftest` **4/4**；手动 `--diff 1.16.72` → **0 changes** |
| PNG 基线（R40） | `png_baseline/` 14 张 + `BASELINE.json`（583 KB）；默认 diff **0 changes** |
| PNG 阈值（R33） | 同尺寸改 0.04% 像素：`--max-ratio 0.0001` → **exit 1**；`0.5` → **exit 0** |
| 源码批量校验（R34/R37） | **1 次全局** `git cat-file --batch-check`，**0.75 s** 覆盖 137 条 sources（原 14 次 8.3 s） |
| 评审记录（R36） | `REVIEWS.md`：**1.16.72 / pass / pony-029**；`record_arch_review --check` 通过 |
| 快照 diff（R15） | `snapshot_arch --diff 1.16.72 current` → **0 changes** |
| PNG diff（R26） | `diff_arch_png` 能报尺寸/像素变化；`--fail-on-change` 可当评审闸 |
| 源码证据校验（R17） | 14 张图 / **137 条 sources**（107 + 30）；`git cat-file` 验 revision 与文件存在 |
| 模块边界（R16） | `python tools/build_module_graph.py` → 57 个运行时模块 / 20 条跨组边；`--check` 可复现 |
| 索引搜索（R14） | Chrome `?q=sequence` → 15 卡片中仅 1 张可见；`?q=no-such` → 0 张 + “无结果” |
| 版式差异（R13） | `python tools/arch_compare.py --id 00-overall --head <changed>` → delta HTML **2,163,473 B** + receipt **2,022 B** |
| 根 README | 中英两份都链接 `docs/architecture/index.html`；中文用 `svg/00-overall.svg`，英文用 `en/svg/00-overall.svg` |
| `.html` / `.svg` 行尾 | **LF**（`00-overall.html` CRLF=0；SVG 由导出器按 LF 写） |
| 术语表（AD9） | `GLOSSARY.md` 38 条术语；14/14 节点 label 命中规范译法 |
| 源码链接（R17） | `00-overall` HTML 内嵌 `archify-source-evidence-data`：`verified:true` / 30 条引用 / GitHub blob 链接 |
| 主题/响应式（R19/R20） | `?theme=light` 生效；390×844 单列渲染（1100 色 / 5.79% 非白） |
| pre-commit（R21） | `.githooks/pre-commit` 跑 5 道快跑门；`install_git_hooks.py --check` 只读 |
| 归属表（R10） | `build_ownership_table.py --check`：12 个模块的最近提交与 `git log` 一致 |
| 快照（R15） | `SNAPSHOTS.json`：1.16.72 / 14 张 / 4.6 KB；`--check` 通过 |
| 版本记录（R22） | `VERSIONS.md`：14 行 `since`/`changed_in`；`--check` 通过 |
| PNG（R26） | 14 张，**582 KB**；`--check` 魔数通过 |
| 源码证据扩展（R17） | 01–13 共 **107 个节点**有 `sources`；00-overall 30 条引用 |
| 术语覆盖（AD10） | **80/80 = 100%**（阈值 90%） |
| 产物体积 | HTML 约 **10.1 MB**（14 张） + SVG 约 **344 KB** + PNG **582 KB** |

> 说明：这是**架构/流程图**，回答“模块怎么组织、数据怎么流”；不是函数级调用图。
> 函数级调用图请用 `python matlabc.py <dir> --browse <out>` 或 `--callgraph`。
