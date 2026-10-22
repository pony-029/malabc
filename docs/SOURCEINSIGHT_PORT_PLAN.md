# Source Insight 4 功能移植计划

> 分析对象：`docs/SourceInsight4UserGuide4092.pdf`（Source Insight 4.0 User Guide，2018-03-19，436 页，1007 条书签）。
> 目标：把 Source Insight 的**项目模型 + 符号数据库 + 上下文/关系视图**移植到本项目，而不是照搬一个 Windows 编辑器外壳。
> 结论先行：**可移植的是“行为与数据模型”，不可直接移植的是“Windows UI、专有二进制格式、完整宏方言”**。
> P0 产物：规格见 [`docs/si/`](si/)，原型见 `tools/mlc_project.py`。

---

## 0. 三句话结论

1. Source Insight 的核心不是编辑器，而是**项目级符号数据库 + 增量解析 + 三套联动视图**（Project / Context / Relation）。
2. 本项目已经有可复用的分析内核（`frontends/ir.py`、`entity_model.py`、`unified_graph.py`、`facts.py`、`callrel.py`、LSP/MCP），缺的是**项目持久化、SQLite 符号库、工程级检索、编辑器面板**。
3. 建议按 **P0 内核（项目/符号/增量/导航/检索）→ P1 生产力（书签/片段/大纲/比较/布局）→ P2 自动化（宏/插件/源码管理）** 分 6 个阶段，**6–8 个月**达到“行为等价的 70%”；完整像素级复刻不建议。

---

## 1. 这份文档的结构与“可移植含量”

| 章节 | 页码 | 内容 | 对移植的价值 |
| --- | --- | --- | --- |
| Chapter 1 Getting Started | 15–22 | Key Benefits、安装/激活、v3/v4 差异、v4 新特性 | 确定“为什么移植”：导航、引用、调用图、预览、实时高亮 |
| Chapter 2 User Interface | 23–38 | Source 窗口、Symbol 窗口、Panel 停靠、Toolbar | UI 参考；不必复刻 Windows 停靠体系 |
| Chapter 3 Features and Concepts | 39–156 | 项目、解析、符号、浏览、上下文/关系、搜索、片段、书签、布局、性能 | **核心规格书**，P0/P1 的主要来源 |
| Chapter 4 Command Reference | 157–374 | ~200 个用户命令的逐条说明 | **验收清单**：每个命令映射为 CLI/LSP/MCP/UI 动作 |
| Chapter 5 Macro Language | 375–420 | 类 C 宏语言、记录、字符串/窗口/符号/项目/搜索 API | 插件 API 参考；不建议实现完整 SI 宏解释器 |
| Chapter 6 Macro Event Handlers | 421–426 | 应用/文档/项目/状态栏事件 | 事件总线设计参考 |
| Index | 427–436 | 索引 | 检索用 |

> 说明：指南没有把 `.sip_sym` 作为公开文件名。第 155–156 页列出的项目文件是
> `Name.siproj`（主项目）、`Name.siproj_settings`、`Name.siwork`（工作区）、
> `Name.snippets.xml`、`Name.SearchResults`、`Name.sip._*`（内部数据）以及 `Backup/`、`cache/`。
> 你看到的 `.sip_sym`（或 `.sip_symy`）应是某个版本/目录下的内部符号数据文件；
> **它没有公开 schema，不应作为兼容目标**。正确做法是：导入 `.siproj` 的文件清单，重新解析源码建自己的符号库。

---

## 2. Source Insight 功能全景（8 类）

| 类别 | SI 的关键功能 | 优先级 |
| --- | --- | --- |
| A. 项目与工作区 | `.siproj` 项目、源目录/规范化路径、添加/移除文件、Master File List、文件/符号/文件夹/类型视图、导入外部符号、Base/Common 项目、只读项目、项目 Web 版、布局/工作区 | **P0** |
| B. 解析与符号库 | 语言/文件类型、内置与自定义语言、点分符号名（`Class.member`）、定义解析顺序、C/C++/C#/Java/HTML/PHP、条件解析/Inactive Code、Token Macros、名称片段索引、增量同步、引用索引、导入库 | **P0** |
| C. 导航与分析 | Jump to Definition、Jump to Caller、Browser Mode、Project Symbol List、调用树/引用树、Context Window、Relation Window（Outline/Graph）、关系规则/调用图过滤/多窗口、引用高亮、Project Report、Smart Rename、文件/目录比较 | **P0/P1** |
| D. 搜索 | 当前文件/多文件/项目搜索、Search Results、Source Links、正则/多行、替换、关键字/名称片段、Project Search Bar | **P0/P1** |
| E. 编辑生产力 | Snippets（全局/项目/语言特定/变量）、Clips、Bookmarks、选择历史前进/后退、Outlining/折叠、Code Beautifier、HTML 生成、编码、文件缓冲/崩溃恢复、语法格式/引用高亮、符号补全、视觉主题 | **P1** |
| F. 自动化与扩展 | 命令行/批处理同步、用户命令、自定义命令（外部工具 + 解析 source link）、XML 配置/主配置/项目配置、宏语言、事件处理器、源码管理（ClearCase/Git）、性能调优 | **P1/P2** |
| G. UI 外壳 | Source 窗口/Overview Scroller、Symbol 窗口、Panel 停靠/分组/半透明、Toolbar、Project/File Search Bar、Browse Toolbar | **P2** |
| H. 平台/运维 | 安装/激活/许可、CHM 帮助、注册表、Sihook、备份/恢复、路径变量 | **不移植** |

### 2.1 最值得“行为等价”的 7 个差异点

1. **项目级符号数据库**：不是“扫一遍目录”，而是持久化、可增量更新的声明/引用索引。
2. **点分符号名**：`Class.member`、`NS.func`，并支持同名重载/多义选择。
3. **定义解析顺序**：当前项目 → 项目导入库 → 全局导入库 → 项目符号路径 → Base 项目。
4. **Context Window**：光标所在标识符的声明、基类型、宏展开、引用位置的即时预览。
5. **Relation Window**：Contains / Calls / Calls+Callers / References，Outline + Graph 两种视图，可多窗口。
6. **名称片段匹配**：`CreateWindow` 索引为 `Create` + `Window`，支持乱序前缀匹配。
7. **条件解析**：全局/项目条件变量，Inactive Code 样式，Token Macro 处理宏声明。

---

## 3. 本项目现状（可复用 vs 缺口）

| 能力 | 现状 | 证据/组件 |
| --- | --- | --- |
| 多语言前端 | ✅ 已有 MATLAB/C/Python/JS | `frontends/ir.py`、`FRONTEND_REGISTRY` |
| 实体/类型模型 | ✅ 契约级 | `entity_model.py`（class/struct/union/enum/typedef/members/bases） |
| 调用图/关系 | ✅ 有界投影 | `unified_graph.py`、`callrel.py` |
| 事实层 | ✅ 位置级 | `facts.py` |
| 文件变更检测 | ✅ 指纹差分 | `analyzer/index.py`（mtime+size+sha256） |
| LSP 后端 | 🟡 定义/引用/悬停/大纲/语义 token | `matlabc_lsp.py`；缺 `didChange`、completion、rename、typeHierarchy、workspace/symbol |
| 项目模型 | ❌ 只有目录 + CLI 配置 | 无 `.siproj` 类项目文件 |
| 符号持久化 | ❌ 进程内 + 整盘 JSON/pickle | `.matlabc_cache.pkl`、`.matlabc_lsp_cache.json` |
| 增量粒度 | 🟡 文件级指纹，但 LSP 缓存用全局最大 mtime | 改一个文件可能整盘失效 |
| 工程级检索 | ❌ 只有函数名子串 | `matlabc_mcp.py t_search` |
| 全文/正则/FTS | ❌ | 无 SQLite/FTS5 |
| 编辑器面板 | ❌ GUI 是 Tkinter 参数表单 | `gui.py`；VS Code 只有 TreeView/Webview 雏形 |
| 书签/片段/布局/主题 | ❌/🟡 | 无编辑器级实现 |
| 编码探测 | ✅ | `utf-8-sig/utf-8/gb18030/gbk/latin-1` |
| 比较 | 🟡 仅任务 diff | `--diff`、VS Code `diffTaskById` |
| 源码管理 | 🟡 只读 git | `git diff --name-only`、`agent_loop` patch |
| 宏/事件/插件 | ❌ 只有 frontend 注册点 | 无事件总线/脚本 API |
| 大工程性能 | 🟡 已量化瓶颈 | YALMIP ~1665 文件 ≈30s；全局缓存失效 |

**最可复用的 5 个组件**：`frontends/ir.py`、`unified_graph.py`、`entity_model.py`、`analyzer/index.py`、`matlabc_lsp.py`。
**最大的 5 个缺口**：项目模型、SQLite 符号库、工程级检索、编辑期语义（didChange/completion/rename/typeHierarchy）、UI 外壳。

---

## 4. 移植边界：哪些做，哪些不做

### 必须移植（P0，决定“像不像”）

- 项目文件 + 源目录 + 文件清单 + 文件类型
- 符号数据库（声明/引用/点分名/作用域）
- 增量解析 + 后台同步 + 引用索引
- 定义/引用/调用者/被调用者/类层次
- Context + Relation 两套视图（至少 API/面板）
- 工程级搜索 + 结果 + source link
- 名称片段匹配
- 条件解析（C/C++ 优先）

### 可以后置（P1）

书签、片段、Clips、选择历史、折叠、比较、编码、布局/工作区、主题、补全、Smart Rename、Project Report、HTML 导出、Code Beautifier。

### 不建议移植（非目标）

- Windows 安装/激活/许可/注册表/CHM
- 精确复刻 MDI/停靠/半透明面板
- 专有 `.sip._*` / `.sip_sym` 二进制格式
- 完整 Source Insight 宏方言（应提供 Python 插件/事件 API；只做常见宏的兼容层）
- ClearCase 等特定商业源码管理集成（保留通用 Custom Command）

---

## 5. 目标架构

### 5.1 项目模型：`.mlcproj`（JSON，可读、可 diff）

```json
{
  "schema": 1,
  "name": "my_project",
  "root": ".",
  "source_dirs": ["src", "include"],
  "file_types": {"c": "c", "h": "c", "m": "matlab", "py": "python"},
  "include": ["**/*.c", "**/*.h", "**/*.m"],
  "exclude": ["build/**", "**/.git/**"],
  "master_file_list": null,
  "conditions": {"DEBUG": 1, "PLATFORM": "win32"},
  "settings": {"name_fragments": true, "index_references": true}
}
```

- 兼容导入 `.siproj`：只读取文件清单/源目录；**不读取符号库**。
- 兼容 Master File List：文本文件，一行一个文件或目录；变更时双向同步。
- 每个项目一个数据目录：`.mlc/project.db`、`.mlc/cache/`、`.mlc/backup/`。

### 5.2 符号数据库：SQLite（stdlib，可选 FTS5）

```sql
projects(id, name, root, settings_json, created_at)
files(id, project_id, path, lang, mtime_ns, size, sha256,
      parse_status, indexed_at)
symbols(id, file_id, name, dotted_name, kind, line, col,
        end_line, scope_id, signature, type_name, flags)
refs(id, symbol_id, file_id, line, col, kind, context)
edges(id, src_symbol_id, dst_symbol_id, kind, file_id, line,
      confidence)
includes(file_id, included_path, resolved_file_id)
conditions(project_id, name, value)
bookmarks(project_id, file_id, line, col, note)
snippets(project_id, name, lang, body)
workspaces(project_id, name, state_json)
```

- 索引：`symbols(dotted_name)`、`refs(symbol_id)`、`edges(src/dst)`、`files(path)`。
- 名称片段：`name_fragments(fragment, symbol_id)`，或 FTS5 trigram；无 FTS5 时用 `LIKE` + 前缀索引。
- 事务：单文件解析一个事务；批量同步分批提交，避免长锁。

### 5.3 索引流水线

```
collect_files → file_type → parse (frontends/ir) → symbols/refs/edges
      ↑                                             ↓
  fingerprint (mtime/size/sha256) ← analyzer/index.py
      ↓
  changed/deleted/added → incremental update → invalidate dependents
```

- **per-file** 指纹，不再用全局最大 mtime。
- 条件解析：先建 `conditions` 表，再按宏值裁剪 `#if/#ifdef/#elif`；`Inactive Code` 标记。
- Token Macro：`token_macros` 表（name/replacement/scope），解析期做 token 级替换。
- 后台 worker：单写者 SQLite + 多解析线程；UI/LSP 读快照，不阻塞。

### 5.4 查询/API 层

- LSP：`textDocument/definition`、`references`、`documentSymbol`、`workspace/symbol`、`typeHierarchy`、`didChange`（debounce）、`completion`、`rename`、`codeAction`。
- 自定义方法：`mlabc/context`、`mlabc/relation`、`mlabc/search`、`mlabc/project`。
- CLI：`mlabc project init/add/remove/sync`、`mlabc symbol find`、`mlabc refs`、`mlabc callers`、`mlabc search`。
- MCP：把上述能力暴露为工具，AI 可直接查询项目符号库。

### 5.5 UI 策略

**不要从零写编辑器。** 优先复用 VS Code：

- TreeView：Project Files / Symbols / Categories / Bookmarks / Search Results。
- Webview：Context 预览、Relation Outline/Graph、Project Report。
- QuickPick：Jump to Symbol、名称片段、命令面板。
- 原生：Diff Editor（文件/目录比较）、Outline/Folding、Snippets、Bookmarks、Workspace/Layout。
- 非 VS Code 用户：保留 CLI + HTML 站点（`renderers/csite.py`）+ LSP。

### 5.6 自动化/宏

- 先做 **Python 插件 API + 事件总线**（project/document/save/status），覆盖 SI 宏的常见用途。
- 自定义命令：JSON 定义 `name/run/parse_source_links`，支持 `%f` 等变量。
- 不实现 SI 宏解释器；如必须，做“常见宏子集”转译层，并把不支持的函数显式报错。

---

## 6. 分阶段计划（含验收）

> 估算：1 名资深工程师 6–8 个月；2–3 人 3–4 个月。含 UI 外壳与宏兼容的“全量复刻”约 9–12 个月。

| 阶段 | 周期 | 交付 | 验收 |
| --- | --- | --- | --- |
| P0 Foundation | 1–2 周 | `.mlcproj` schema、SQLite schema、feature ID/追踪表、导入 `.siproj`/MFL 的决策 | 能用 1 个真实工程建项目；schema 评审通过 |
| P1 Project + Symbol DB | 4–6 周 | 项目创建/打开/添加/同步；per-file 索引；符号/引用/边入库；名称片段 | 10k 文件首索引可接受；单文件改动只重解析该文件；`symbol find` <50ms |
| P2 Navigation + Context/Relation | 4–6 周 | definition/references/callers/callees/typeHierarchy；Context/Relation API + VS Code 面板；LSP workspace/symbol | 20 个黄金查询全对；关系视图可截断且标注 truncated |
| P3 Search + Rename | 3–4 周 | 工程搜索（regex/多行/大小写/文件过滤）、结果面板、source link、Smart Rename（dry-run+undo） | 100k LOC 搜索 <1s；重命名可回滚；结果可跳转 |
| P4 Editing Productivity | 3–4 周 | 书签、片段/Clips、选择历史、折叠、比较、编码、布局/工作区 | 面板状态可恢复；书签/片段持久化；比较可用 |
| P5 UI/Workspace Hardening | 3–4 周 | VS Code 面板整合、主题、Project Report、HTML 导出 | e2e 通过；大工程不卡死；可离线 |
| P6 Automation | 3–4 周 | Python 插件 API、事件总线、Custom Commands、Git 集成 | 示例插件；事件触发；外部命令 source link |
| P7 Performance/Parity | 持续 | 基准、FTS、缓存、导入兼容、feature matrix 收口 | 1M 行工程有可重复基准；P0 功能全绿 |

### P0 立即可做的 5 件事

1. 冻结 `.mlcproj` 与 SQLite schema（先写文档，不写代码）。
2. 把 `analyzer/index.py` 的 per-file 指纹接到一个最小 `project sync`。
3. 用 `entity_model` + `unified_graph` 落 `symbols/refs/edges` 三张表。
4. 在 `matlabc_lsp.py` 补 `workspace/symbol` 与 `didChange`（debounce），先让 VS Code 能用。
5. 用 1 个真实工程（YALMIP 或 Linux 子树）建立“项目打开 → 符号查询”的基准。

---

## 7. 文档拆分（建议 10 份）

| 文档 | 内容 | 何时写 |
| --- | --- | --- |
| `docs/si/00-overview.md` | 目标/非目标、术语、与 SI 的差异声明 | P0 |
| `docs/si/01-feature-inventory.md` | PDF 1007 条书签 → 功能 ID → 优先级 → 现状 | P0 |
| `docs/si/02-project-model.md` | `.mlcproj`、MFL、导入 `.siproj`、源目录/文件类型 | P0 |
| `docs/si/03-symbol-db.md` | SQLite schema、点分名、作用域、引用/边、FTS | P0 |
| `docs/si/04-parsing.md` | 语言注册、条件解析、Token Macro、增量/失效 | P1 |
| `docs/si/05-navigation.md` | 定义/引用/调用/类层次/Context/Relation | P1 |
| `docs/si/06-search-edit.md` | 搜索/正则/source link/rename/书签/片段/比较 | P1 |
| `docs/si/07-ui.md` | 面板/布局/主题/VS Code 映射 | P1 |
| `docs/si/08-automation.md` | 插件 API/事件/Custom Command/Git | P2 |
| `docs/si/09-performance.md` | 基准、索引预算、缓存、百万行验收 | P2 |
| `docs/si/10-traceability.md` | SI 章节/命令 → 功能 ID → 代码 → 测试 | 持续 |

> 本文件是总纲；P0 已落 `00`–`05`（总览/功能清单/项目模型/符号库/MATLAB 适配/30 轮路线），
> 并用 `tools/mlc_project.py` + `tests/test_mlc_project.py` 兑现了最小原型。

---

## 8. 风险与决策点

1. **“全部移植”范围失控**：SI 有 ~200 个命令 + 宏 API + Windows UI。先冻结“行为等价 70%”的定义。
2. **符号语义**：C/C++ 重载、模板、宏、条件编译是深水区；先支持 C 子集 + 条件表，模板显式降级。
3. **性能**：SQLite 单写者 + 后台解析；避免每次查询全量 JSON。
4. **UI 成本**：不要自研编辑器；VS Code 扩展是最短路径。
5. **格式兼容**：`.sip._*`/`.sip_sym` 不公开；只导入文件清单，符号重新解析。
6. **许可/法律**：不要复制 SI 的图标、帮助文本、专有格式；功能行为可参考，实现独立。

---

## 9. 参考锚点（便于逐条对照）

- 项目与符号库：指南 p40–p57
- 条件解析/Token Macro：p60–p65
- 名称片段：p66–p67
- 文件类型：p72–p73
- 导航/引用/调用树/Context/Relation：p74–p76、p90–p97
- 搜索/正则/source link：p104–p111
- 片段/书签/比较/编码：p98–p130
- 配置/主题/布局/工作区/性能：p138–p153
- 项目文件清单：p154–p156
- 命令参考：p157–p374
- 宏/事件：p375–p426

---

## 9. 预算与暂停条件（R453）

为什么写这一节：SI 线与「MATLAB → C 移植」线**并行**，而两者抢的是同一份
注意力与同一套发版门禁。没有硬约束时，最先崩掉的是"发版前全量跑门"这个习惯 ——
而它是所有其它判据的前提。

### 9.1 门禁预算

| 约束 | 数值 | 理由 |
|---|---|---|
| 发版关键门总墙钟 | **≤ 5s** | 超过 5s，人就会开始"这次先不跑了" |
| 新门是否进发版 | 默认 **不进** | 进发版需满足：单门 ≤ 0.5s，或支持 `--fast` 跳过重活 |
| 慢门（>1s） | 必须有**带理由的白名单** | 否则 ⚠ 天天亮，很快没人看 |

> 现状（1.7.2）：发版 3.8s、全检 23.4s。全检慢在 L4（Octave 启停）与真编译，
> 它们属于 CI/手工，不属于发版。

### 9.2 暂停条件

**任一触发即暂停 SI 线，全部精力回到移植线**（恢复条件见右列）：

| # | 触发条件 | 恢复条件 |
|---|---|---|
| S1 | 发版墙钟 > 5s | 降到 ≤5s，或把新门降级为 CI-only |
| S2 | 移植线 **PA2（未对拍函数数）连续两轮未下降** | 有一轮实测下降 |
| S3 | SI 线连续两轮没有"可验证交付"（有测试且进 CI） | 出现一条进 CI 的测试 |

### 9.3 为什么用"PA2"当移植线指标

PA2 = 解释器算不出来、因而**无法对拍**的函数数。它同时受两件事影响：
支持面（算子/语法）与注解覆盖。**它下降，说明真的多了一个函数被两边算过**；
而"能生成的函数数"只说明转换器没崩。
