# matlabc 最终交付报告

> 版本：v1.16.40 ｜ 生成日期：2026-08-27 ｜ 状态：生产就绪（Production-Ready）

---

## 1. 项目概述

`matlabc` 是一个**纯 Python、零第三方运行时依赖**的 MATLAB 静态结构分析工具，用于在无 MATLAB 环境下快速梳理 MATLAB 工程的结构、调用关系、数据流与关键函数风险。

- **单文件架构**：核心逻辑集中于 `matlabc.py`（约 15,597 行），无任何第三方 import（仅标准库），部署即拷贝即用。
- **兼容性**：严格兼容 **Python 3.6.5**（长期固定基线），不使用 3.7+ 语法。
- **安装方式**：`pip install -e .` 后可用 `matlabc` 命令，亦可 `python matlabc.py` / `python -m matlabc` 直接运行。

---

## 2. 版本与规模

| 指标 | 数值 |
| --- | --- |
| 版本 | v1.16.56 |
| 核心代码行数 | ~16,320 行 |
| 模块级函数 | 275 个 |
| 类 | 8 个（`MatlabFunction` / `MatlabClass` / `MatlabFile` + P90 `BaseFrontend`/`PyFrontend`/`JsFrontend`/`CFrontend`/`MatlabFrontend`） |
| 顶层常量 / 正则 / JS/CSS 数据块 | 34 个（含 `GLOBAL_SEARCH_JS` 全站搜索浮层、`UNIFIED_GRAPH_JS` 统一画布脚本） |
| 测试代码 | **154 项测试** |
| 回归样本 | 9 个 `.m` 文件（含 1 个子目录、1 个类、嵌套函数、`arguments` 块、同名函数等） |

---

## 3. 功能全景

### 3.1 核心解析
- 递归目录扫描 + 排除规则（`.git`、`node_modules`、`__pycache__` 等默认排除，`--exclude` 扩展）。
- 语法识别：主函数 / 局部函数 / **嵌套函数** / 脚本 / `classdef`（属性、方法、构造函数、**多继承 `A & B` 与包限定父类**）/ **`arguments` 参数验证块（R2019b+）**。
- 函数签名提取（输入/输出参数、所在文件与行号、类型）。
- 编码自适应：UTF-8 / UTF-8-sig / GBK 中文目录与注释。
- 词法清洗：注释与字符串替换为空格、转置 `A'` 防误判、续行合并、字符串换行复位。

### 3.2 调用分析
- 项目内调用边 + 跨文件调用 + 内置/外部函数统计。
- MATLAB 内置/工具箱函数中文说明库（实际调用处附说明）。
- 动态调用识别：`feval('func')` / `str2func('func')` / `cellfun`/`arrayfun`/`structfun` 等**字符串回调**。
- 函数句柄 `@func`（区分匿名函数 `@(x)`，不误判）。
- 命令形式调用（`foo arg`）、`end` 索引运算符边界（`x(end)`/`x(1:end)`/`x(end+1)` 不误判）。
- 疑似漏检诊断（unresolved 调用分类）。

### 3.3 深度关系分析
- **影响面 / 依赖面传递闭包**（含缓存加速）。
- **追本溯源到根**（入口函数识别、孤立函数、动态调用完整性提示）。
- **关键函数风险度量**：圈复杂度、扇出、扇入、影响面、依赖面、综合评分与风险标签。
- **同名函数歧义可视化与一键切换**（就近解析候选明细 + 预览弹窗候选列表可点击切换解析目标）。
- 循环调用检测、最短可达路径（BFS）。

### 3.4 数据流
- 变量读写识别与跳转定义。
- 结构体字段访问（`obj.val` 读写、跨文件跳转）。
- 注释折叠、字段读写图例。

### 3.5 交互与可视化（`--browse` 站点）
- 全局力导向调用图 + 局部下钻调用图 + 循环调用可视化。
- 函数点击预览（源码片段、语法高亮、双向定位、预览历史、位置记忆）。
- 全文搜索（多关键字 / 正则 / 预览历史）。
- 键盘无障碍、悬浮详情卡片、URL `#` 状态分享、布局稳定性。

### 3.6 输出与工程化
- 输出：Markdown 报告 / Mermaid 图 / Graphviz DOT / HTML 报告 / 结构化 JSON / 交互式站点。
- **可复现构建 `--reproducible`**：全部产物省略时间戳，两次运行逐字节一致（CI 比对友好）。
- 写盘健壮性（自动创建父目录、优雅报错、非零退出码）、`--browse` 旧产物清理。
- 配置文件支持（`--config` JSON 配置继承）。
- **增量分析缓存 `--incremental`**：缓存未变文件解析结果（`.matlabc_cache.pkl`），仅重分析变更文件；缓存命中统计（`cache_hits`/`cache_misses`）导出到 JSON `stats`。
- `setup.py` 打包（`console_scripts` 入口 `matlabc`）。

### 3.7 目录级分析（doxygen 风格，P57–P69）
- **文件夹依赖关系**：目录间调用边（`_compute_folder_edges`）、扇出/扇入汇总、Markdown 章节 + browse 表格 + JSON `folder_edges` + Mermaid/DOT 目录级图（`--folder-graph`）。
- **目录循环依赖检测**：Tarjan SCC 检测循环目录组（`_detect_folder_cycles`），在 Markdown / index / 分层图 / 目录页四处一致标注。
- **目录-函数分层调用图**（`--combined-graph`）：目录为簇、函数为节点，目录内调用灰边、跨目录调用红边，节点可点击跳转，目录簇按耦合度着色。
- **目录索引页**（`dirs/*.html`）：每个目录一个页面，展示文件/函数、依赖目录（扇出/扇入）、本目录内函数调用图（可点击）、概览卡片（文件/函数/类/扇出扇入色阶）+ 循环依赖标注。
- **双向导航闭环**：目录页 ↔ 文件/函数（正向）+ 源码页面包屑 → 目录页（反向）。

### 3.8 类层次分析（doxygen 风格，P81）
- **类继承图（Inheritance Diagram）**：`render_class_hierarchy_svg` 生成父上子下的 UML 泛化继承图 SVG（子类空心三角箭头指向父类），支持 MATLAB 多继承 `classdef C < A & B` 与包限定父类 `pkg.Cls`，节点可点击跳转源码定义行。
- **类层次页面**（`class_hierarchy.html`）：独立页面内嵌继承图 + 类定义明细表（类名/文件/父类/属性/方法）；索引页导航新增「类层次」入口。
- **多继承解析**：`RE_CLASSDEF` 扩展支持 `A & B` 多继承与包限定父类，`MatlabClass.superclasses` 列表（`superclass` 字段向后兼容）。

### 3.9 注释标签聚合（doxygen 风格 \todo/\bug，A1）
- **标签扫描**：`_collect_annotations` 提取 `% TODO/BUG/DEPRECATED/FIXME/NOTE/XXX/HACK/WARNING` 标签（含内容、文件、行号）。
- **聚合列表页**：`render_annotations_page` 生成 `annotations.html`，按标签分组（含中文名与配色）、可点击跳转源码行。

### 3.10 多返回值 / 可变参数签名（A2）
- **解构识别**：`RE_MULTI_ASSIGN` 识别 `[a, b] = foo(x)` 解构调用，`destructured_calls` 记录返回值流向。
- **流向展示**：源码页解构行追加「返回值流向」药丸（`[d, s] ← demod`，悬停展示 `d = y; s = snr` 映射）。
- **可变参数**：`is_variadic()` 识别 `varargout`/`varargin`，JSON 新增 `variadic` 字段。

### 3.11 类协作图（Collaboration Diagram，A3）
- **uses 关系收集**：`_collect_class_collaborations` 聚合「类方法调用另一类方法/构造函数」的引用关系。
- **协作图 SVG**：`render_class_collaboration_svg` 环形布局，实心箭头由引用方指向被引用方、边标签标注次数，与继承图空心三角视觉区分；`class_hierarchy.html` 内嵌「类协作图」章节。

### 3.12 注释公式渲染（MathJax，A4）
- **公式渲染**：源码页引入 MathJax（`MATHJAX_INIT_JS` 异步加载 CDN），注释内 LaTeX 公式（`\(...\)`、`$$...$$`、`\[...\]`）自动渲染，CDN 离线优雅降级为原始文本。

### 3.13 全局成员索引（Member Index，B1）
- **成员聚合**：`_collect_members` 跨文件聚合全部类的属性/事件/枚举/方法（含父类）。
- **索引页**：`render_members_page` 生成 `members.html`，按类分组 + 成员表格（类型/成员/行号）+ 可点击跳转源码定义行。

### 3.14 XML 结构化输出（B2）
- **XML 导出**：`--xml` 参数 + `render_xml`（`_dict_to_et`/`_indent_et` 递归序列化），输出与 `--json` 同构的 XML，供 doxygen 生态工具二次消费。

### 3.15 复杂索引加固 + 跨文件数据流（C3）
- **end 上下文消歧**：`end` 关键字在圆括号/花括号/点索引三种上下文均识别为 keyword（不误当标识符/参数），`switch` 多分支计入圈复杂度。
- **跨文件 global/persistent 索引**：函数级 `global`/`persistent` 声明归属 + `_collect_global_vars` 跨文件聚合，JSON 新增 `global_vars` 字段（`{global: {名: [[文件,函数,行号]]}, persistent: {...}}`）。
- **样本扩充**：`sample_m` 新增 `switch_case.m`（switch/end/try-catch）、`parallel.m`（parfor）、`varargs.m`（varargout/varargin）三个生产形态样本。

### 3.16 静态检查器基础（C3）
- **跨文件字段传递追踪**：`_collect_field_access`/`_collect_cross_file_fields` 聚合结构体字段（`obj.field`）的跨文件读/写，JSON 新增 `field_access` 字段。
- **常量折叠**：`_try_eval_const`（安全白名单求值）+ `_collect_constants` 收集命名常量定义并求值，JSON 新增 `constants` 字段。
- **未初始化变量检测**：`_detect_uninitialized` 检测「读前无写」的局部变量（排除参数/关键字/内置/调用目标/字段），JSON 新增 `uninitialized` 字段。

### 3.17 静态检查器深化（C3）
- **未初始化降误报**：`_detect_uninitialized` 排除 global/persistent 注入、函数句柄 `@name` 引用等合法「读前无写」。
- **类型推断**：`_infer_type`/`_collect_types` 从命名约定 + 赋值形态（`zeros`/`linspace`/字符串/冒号）推断标量/向量/矩阵/结构体/字符串，JSON 新增 `types` 字段。
- **死代码检测**：`_detect_dead_code` 检测 `return` 后不可达语句 + `if` 恒假死分支（结合常量折叠），JSON 新增 `dead_code` 字段。

### 3.18 静态检查器精度（C3）
- **跨函数类型流**：`_infer_func_output_types`（函数返回值类型推断）+ `_collect_type_flow`（调用方多返回值解构继承传播），JSON 新增 `type_flow` 字段。
- **复杂控制流死代码**：`_detect_dead_code` 升级为缩进栈追踪，覆盖嵌套块内 return/break/continue 后不可达。
- **类型不一致告警**：`_detect_type_mismatch` 检测矩阵变量被赋标量等类型冲突，JSON 新增 `type_mismatch` 字段。

### 3.19 静态检查可用性（C3）
- **告警报告化**：`_collect_checks`/`render_checks_page` 生成 `checks.html` 静态检查汇总页（未初始化=高/类型不一致=中/死代码=低，可跳转源码行），索引页新增「静态检查」导航。
- **维度推断深化**：`_infer_dims`/`_collect_dimensions` 从 `zeros(m,n)` 构造器 + 常量折叠推断具体维度（m×n），JSON 新增 `dimensions` 字段。
- **未初始化数据流精确化**：`_detect_uninitialized` + `_in_cond_block`（前向扫描块栈）区分「未初始化」与「仅条件分支赋值的可能未初始化」，JSON 的 `uninitialized` 新增 `reason` 字段。

### 3.20 静态检查收口（C3）
- **形状检查**：`_detect_shape_mismatch` 结合维度推断，检测 `A*B` 矩阵乘法 `n==p` 约束、`A+B`/`A-B` 同维度约束违规，JSON 新增 `shape_mismatch` 字段。
- **多维数组推断**：`_infer_dims`/`_collect_dimensions` 支持 `zeros(m,n,k)` 三维及以上，JSON 的 `dimensions` 新增 `dims` 列表（二维保留 rows/cols 兼容）。
- **告警阈值配置化**：`--checks` 参数 + `_parse_checks_arg`，静态检查开关可配置（`all`/`none`/逗号列表），接入 `render_json`/`render_browse_site`。

### 3.21 静态检查可落地（C3）
- **告警抑制注释**：`_parse_suppressions` 解析 `% analyzer:ignore <check> [name]` 就地标注，接入四个检查（uninitialized/dead_code/type_mismatch/shape_mismatch），支持全抑制 / 变量名 / 函数名三级粒度。
- **增量检查缓存**：`_detect_uninitialized`/`_detect_dead_code` 结果缓存到 `mf._uninitialized`/`mf._dead_code`，随 pickle 增量缓存复用，二次 review 只重算变更文件。
- **压力测试**：`test_c22_stress_test`（30 文件 + 3 层目录 + 类多继承 + switch/parfor/arguments + 中文注释），60s 性能门禁。

### 3.22 静态检查成熟度（C3）
- **行级抑制 + 报告增强**：`_parse_suppressions` 支持 `% analyzer:ignore-next-line <check>` 行级抑制与 `-- 原因` 标注；`_count_suppressed` 统计抑制规模，`checks.html` 展示「已抑制告警数」。
- **跨文件检查增量缓存**：`_collect_field_access`/`_collect_file_constants` 派生数据缓存到 `mf._field_access`/`mf._constants`，type_mismatch/shape_mismatch 的依赖数据增量复用。
- **大规模验证**：`test_c25_large_project`（300 文件 + 5 层目录 + 类多继承 + 混合语法），180s 性能门禁。

### 3.23 性能与健壮性修复（Bugfix）
- **未初始化检测性能**：`_detect_uninitialized` 由 O(n²)（`_in_cond_block` 每行前向扫描）降为 O(n)（增量 `cond_stack` 随行维护块边界），修复巨函数卡死。
- **常量折叠 JSON 安全**：`_try_eval_const` 过滤 `complex`（`(-1)^0.5`）/`inf`（`1e308*10`）/`nan` 等不可序列化值。
- **序列化兜底**：新增 `_json_default`（set/自定义对象转可序列化），`json.dumps` 接入 `default=_json_default`。

### 3.24 注释模板增强（C3）
- **author/date/version 字段**：`_parse_header_comments` 支持 `% AUTHOR:`/`@author`/`作者:`、`% DATE:`/`日期:`、`% VERSION:`/`版本:`，doxygen `@brief`/`@details` → description。
- **自由格式兜底**：无模板标签的注释块整体作为 description（中英文皆可）。
- **文件级 header**：`_parse_file_header` 解析文件顶部注释，`mf.header` + JSON 的 `files[].header`/`functions[].header`（author/date/version 缺失 null）。

### 3.25 引领性收口（C3）
- **`@param`/`@return` 内联标签**：`_parse_header_comments` 支持 `% @param name 说明`/`% @return 说明`/`% @retval`，函数体开头注释也纳入解析。
- **复杂度热力总览**：`_collect_file_metrics`/`_collect_dir_metrics`/`render_complexity_heatmap` 生成 `complexity.html`（文件/目录复杂度热力图 + 颜色编码）。
- **SARIF 门禁**：`--sarif`（SARIF 2.1.0 输出）+ `--max-warnings`（告警超阈值非零退出码）。

### 3.26 UI 深度改进（C3）
- **暗色/浅色主题**：`data-theme="dark"` CSS 变量覆盖（GitHub Dark 语义）+ `maToggleTheme` JS + localStorage 记忆 + header 动态注入切换按钮。
- **文件概览卡片**：源码页顶部展示文件头 description/author/date/version + 复杂度/函数/类数；目录页文件列表展示文件描述。
- **可折叠目录树**：`<details>/<summary>` 替换纯文本 `<pre>`。
- **函数索引分组**：首页函数索引按目录分组（可折叠）。
- **导航分组**：首页导航按「文档/分析/说明/图」分组。

### 3.27 跨文件污点分析（P85）
- **源/汇定义**：`_TAINT_SOURCES`/`_TAINT_SINKS`（20+ 敏感源：`input`/`load`/`fopen`/`webread`/`jsondecode`/`str2num` 等；20+ 危险汇：`fprintf`/`fwrite`/`save`/`eval`/`system`/`writetable` 等），`_taint_regexes` 懒构建、大小写不敏感。
- **传播引擎**：`_collect_taint_call_sites` 用 `_tokenize_matlab` 剔除注释/字符串后扫描函数体收集「源/汇」调用点；`_propagate_taint` 沿 `calls_of` **反向传播**（直接调用汇=level 1，调用受污函数者逐层 +1、封顶 5，仅「有输入参数或脚本」的入口参与传播避免过度污染），输出函数级污点流 + 传播路径 + 源汇标签。
- **安全门禁**：`taint.html` 污点流页（级别徽章 / 源汇标签 / 传播路径 / 关键词与级别筛选）+ JSON `taint` 字段 + **SARIF 新增 `tainted_sink` 规则**，接入 `--sarif`/`--sarif-diff`/`--max-warnings` 门禁（危险输入未净化直达危险输出 → 非零退出码）。

### 3.28 注释完备度评估 + 待办清单生成（P86）
- **三维打分**：`_doc_todo_priority`/`_collect_doc_todos` 以「复杂度(修改风险) × 扇入(影响面) × 头部注释缺失(可维护性)」评估（description 缺 -30、input/output 无文档各 -10、author/version 缺 -10，封顶 100）。
- **待办清单**：`todo.html`「函数待办清单」页（优先级 / 缺失项 / 文档分列，可按优先级筛选、搜索、点表头排序）+ JSON `doc_todos` 字段。
- **优先级判定**：高复杂度（≥8）+ 高扇入（≥2）+ 低文档分（<70）= `high`；中复杂度（≥5）+ 有调用方 + 分 <85 = `medium`。

### 3.29 多语言后端扩展（P87）
- **语言前端抽象**：把「解析层」抽象为语言无关模型（文件→函数→调用→复杂度→依赖），新增轻量 **C 前端**：`_parse_c_source`（函数定义/内部调用/include 依赖/复杂度估算，正确处理单行闭合函数 `int add(int a,int b){return a+b;}`）+ `build_c_model` + `render_c_report`（`c_report.html`：复杂度 TOP、函数总览、include 依赖、内部调用图、未解析调用）。
- **纯 C 模式**：`--lang c` 不要求 .m 文件，独立输出站点与 JSON（`c_model` 字段）。
- **混合模式**：`--mixed` 下 MATLAB 外部调用命中 C 函数名 → **跨语言 MEX 桥接表**（JSON `c_bridge` 字段，`_match_c_bridge`）。

### 3.30 变量级污点 + 待办可执行化 + 语言前端插件化（P88-P90）
- **变量级污点（P88）**：污点从「函数级」精确到「变量级」——`_propagate_var_taint` 沿赋值链追踪受污变量（`var_sites` 记录源赋值/汇实参/赋值流/调用实参位置），`taint.html` 展示变量级污点流。
- **待办可执行化（P89）**：`--todo-export` 把 `doc_todos` 导出为可执行任务清单（含优先级/缺失项/文件位置），直接对接 CI/项目管理。
- **语言前端插件化（P90）**：`BaseFrontend` 定义语言无关前端协议，`PyFrontend`/`JsFrontend` 落地 Python/JavaScript 解析，与 `CFrontend`/`MatlabFrontend` 统一接入模型→站点→JSON 流水线。

### 3.31 污点参数位门禁 + 行动单跟踪 + PY/JS 全链路（P91-P93）
- **污点参数位门禁（P91）**：`--taint-param-gate`/`taint_param_gates` 按「危险汇的参数位」精确门禁——污点变量若出现在危险汇的关键参数位（如 `fprintf(fid, data)` 的 `data` 位）才判违规，降低过度告警。
- **行动单执行跟踪（P92）**：`action` 状态（open/in_progress/done）+ `--action-status` 查询，`action_tracking` JSON 输出，闭环治理「开了单→做没做→改没改」。
- **PY/JS 前端落地（P93）**：`--lang py/js` 独立分析 Python/JavaScript 工程，与 MATLAB/C 统一产出站点/JSON/SARIF。

### 3.32 跨语言统一门禁矩阵 + 字段级污点 + 分支覆盖度量（P94-P96）
- **修复缺陷**：`_propagate_taint` 引用未定义全局常量 `MAX_TAINT_DEPTH`（NameError）——函数前定义 `MAX_TAINT_DEPTH = 5`，默认参数引用它、函数体改用 `max_depth` 局部变量，杜绝运行期 NameError。
- **跨语言统一门禁矩阵（P94）**：新增 `--gate-file gates.json` JSON 声明式门禁（`taint_gates`/`rule_gates`/`max_warnings`/`test_coverage`）+ `--max-warnings-by-rule "uninitialized:10,..."` 按规则独立阈值（CLI 优先合并）；SARIF 基线**自动持久化**到 `.codebuddy/analyzer/sarif_base.json`（指纹行数组），`--sarif-diff` **零参数**自动复用基线；C/PY/JS 模式复用 MATLAB 主流程门禁逻辑（`_apply_unified_gates`），`_persist_and_diff_sarif` 统一「持久化基线 + 增量 diff」。
- **字段级污点（P95）**：`s.name = input()` 只标记 `s.name` 字段受污（`field_taint` 链，不污染整根 `s`）；`y = s.name` 字段→变量传播；`s = struct('a', n)` 整根继承、字段自动带污；字段实参跨函数映射；`exact_sinks[].hits[]` 新增 `field` 标志（True=字段级精确命中），`taint.html` 新增「字段受污」列与字段级徽章。
- **分支覆盖度量（P96）**：`measure_branch_coverage(files, root, lang)` 按函数体区间扫描分支关键字（MATLAB `_RE_BRANCH`、C `_RE_C_CX`、Python/JS 专用集），测试文件引用近似为已覆盖，输出 `covered/total/coverage_percent/per_file/test_refs`，接入 `test_coverage.min_percent` 门禁（不足即非零退出）。

### 3.33 Doxygen 级浏览体验 + 目录树模型 + 函数详情页 + 全站搜索（P100-P112）
- **目录树模型与文件依赖图（P100/P101）**：`_build_dir_tree` 按文件夹分层聚合（函数数/行数/圈复杂度沿路径累加，`metrics` 语义为「本目录+全部后代」）；`_build_file_dep_graph` 跨文件函数调用聚合为 `deps`/`dependents`。双键 `dirs`/`files_graph` 挂载进 `--json` 输出与 `--browse` 模型（JSON_SCHEMA §23/§24）。
- **面包屑与源码大纲（P103/P105）**：`_crumbs_html` 生成 `项目 › 目录 › 文件 › 函数` 面包屑（源码页/目录页/详情页全接入）；源码页新增左侧 sticky 函数大纲（`src-outline`），滚动联动高亮当前函数（`_search.js` scrollspy）。
- **函数详情页（P104/P106）**：`render_func_detail_page` 生成 `func_detail.html` 单模板页 + 预注入 `window.__CG__`/`window.__FD_FLAGS__`（污点/行动单标志），前端按 `?g=<gid>` 渲染签名横幅、复杂度·扇入扇出·污点·行动单徽章、**一阶调用图**（自包含 SVG：被调在左/当前居中/调用者在右，点击节点跳转）、调用者/被调列表；全站函数名可点击直达（源码页「详情」徽章 `func_detail.html?g=`）。
- **全站函数搜索与键盘导航（P107/P108）**：`GLOBAL_SEARCH_JS` → `src/_search.js` 注入所有源码页/详情页，Ctrl+K/`/` 打开浮层（复用 `__CG__.meta`，↑↓ 选择、Enter 跳转、Esc 关闭）、`t` 切换主题、响应式 `@media` 与打印样式（`@media print` 隐藏导航/展开内容）。
- **度量雷达（P111）**：`_mini_radar_svg` 纯 Python 计算五维（复杂度/行数/函数/扇出/扇入）多边形坐标，内联 SVG 零依赖，目录页文件卡展示。
- **Doxygen XML 导出（P112）**：`--export-doxygen-xml OUTDIR` 生成 `index.xml` + 每文件 `<md5>_file.xml`（compounddef，含函数 memberdef `name`/`argsstring`/`param`/`location`），打通 doxygen 工具链/CI 互操作。

### 3.34 对象契约统一治理（P113）
- **契约声明**：`_FN_CONTRACT`/`_CLASS_CONTRACT`/`_MFILE_CONTRACT` 三张表显式声明文件/函数/类对象的必需属性与默认值。标量/None 直接赋值；可变容器（list/dict/set/Counter）用 factory（callable）生成独立实例，杜绝多对象共享可变容器造成交叉污染。
- **统一补齐入口**：`_coerce_fn`/`_coerce_class`/`_coerce_mfile` 递归补齐缺失/为 None 属性（就地、幂等，不覆盖既有值）；公共入口 `coerce_analysis_files(files)` 在 `build_analysis_model` 数据层入口调用，`render_doxygen_xml`/`render_directory_page`/`render_source_page` 入口再做幂等契约前置——「数据层 + 渲染层」双防线，独立调用/第三方复用（如测试 mock）同样安全。
- **渲染层去补丁**：`_build_dir_tree`/`render_directory_page`/`render_source_page`/`render_doxygen_xml`/`build_analysis_model` 数据装配中针对 mf/fn 的散落 getattr 防御全部改为直接属性访问；仅保留语义性防御（增量缓存命中检查 `_field_access`/`_constants` 等、model 可选挂载、C 对象等非契约对象）。
- **契约语义入测试**：合成对象直接调用渲染函数须先经 `coerce_analysis_files`；新增 `test_p113_contract_coercion` 7 个覆盖点（全缺属性补齐/容器独立/不覆盖既有值/类方法递归/文件递归/真实对象幂等/渲染链路回归）。回归 136 项通过。

### 3.35 Python 3.6 语法兼容门禁 `--check-py36`（P114）
- **双通道检测**：① AST 通道用当前解释器 `ast.parse` 解析每个 `.py` 文件，任何 3.7+ 新语法（walrus `:=`、仅位置参数 `/`、f-string 调试 `f"{x=}"`、match 等）直接 `SyntaxError` 记为 `parse_error`（行/列取自异常）；② 正则通道用 `_PY36_RULES` 12 条规则表逐行扫描 3.6「能解析但运行期不可用」或「会被 3.6 误解析」的语法——`match/case`（3.6 会误当函数调用/标识符）、`list[int]` 内置泛型下标（3.9）、`dataclasses`（3.7）、`math.comb/prod/perm`（3.8）、`str.removeprefix/removesuffix`（3.9）、`functools.cache`（3.9）、`zoneinfo`（3.9）等新标准库 API。
- **tokenize 字符串剥除**：`_py36_extract` 先用 `tokenize` 把 STRING/COMMENT/FSTRING_START..END token 替换为等长空白再扫描，门禁工具自身的示例文本（规则表说明里的 `x := y`、`f"{x=}"`）不再自反射误报；f-string 原文经 FSTRING_START..END 区间重建后单独检测调试表达式与表达式内反斜杠（3.6 报 SyntaxError、3.12 才放开）。3.6 无 FSTRING_* token 类型时自动退化，由 AST 通道 parse_error 兜底。
- **CLI 短路**：`--check-py36` 不进入 MATLAB 分析流程，扫描目标 = `dir`（目录递归 `*.py` 或单 `.py` 文件）+ `--check-py36-files`（可多次、逗号分隔追加），缺省自检（`matlabc.py` 自身 + `tests/`）；`--max-warnings` 为退出码门禁（超阈值返回 1），`--json` 落盘 `{tool, command:"check_py36", version, python, targets, stats, issues}`。
- **回归入测试**：新增 `test_p114_check_py36` 7 个覆盖点（规则表结构合法/坏源码逐项命中与精确行号/字符串注释不误报/AST 通道/目录递归与 stats/自检 0 问题/CLI 端到端退出码与 JSON）。自检输出「统计：文件 2 | 问题 0」，回归 139 项全部通过。

### 3.36 JSON 快照对称化 `--from-json`（P123）
- **可交换格式闭环**：与 `--json`（`render_json`）构成对称的「可交换格式」——分析结果导出为独立快照后，可在工具间 / CI 间 / 跨机器无损传递，导入无需重新扫描源码。与 P113（对象契约）、P114（Python 3.6 门禁）构成数据层 / 语法层 / 交换层三层护栏。
- **快照导入短路**：`--from-json FILE` 直接读取 `--json` 导出的快照（`_from_json_load` 校验顶层为 dict），跳过 MATLAB 分析流程，默认打印导入摘要（文件/函数/类/调用边/目录/契约问题数）。
- **契约校验**：`_json_contract_check` 复用 P113 语义在可交换格式上的投影——顶层 `_JSON_TOP_REQUIRED`（version/root/stats/edges/files）、文件级 `_JSON_FILE_REQUIRED`、函数级 `_JSON_FN_REQUIRED`（name/qualified/kind/line/signature/inputs/outputs/variadic/input_docs/output_docs/header/calls/calls_qualified/builtin_calls/external_calls）、类级 `_JSON_CLASS_REQUIRED`，缺失字段逐条报告；`--max-warnings` 为缺字段数量门禁（超阈值返回 1）。
- **对称化重导出 + 往返一致性**：`--from-json X --json Y` 经 `_serialize_model` 规整（`generated_at` 置空，与 `--reproducible` 对齐）重导出，再读回 `_roundtrip_diff` 逐字段递归比对（dict 按键、list 按索引、标量按 `!=`），输出「一致」或差异路径清单，保证读-写-读逐字段相等。
- **快照报告**：`--from-json X -o OUT` 用 `render_snapshot_report` 基于 dict 直接渲染 Markdown 快照报告（概览统计 / 文件清单 / 函数清单 / 调用图摘要 / 契约校验），无需对象模型与源码，可离线复现分析结论。
- **回归入测试**：新增 `test_p123_from_json_roundtrip` 7 个覆盖点（真实快照读回与统计/契约缺字段逐项命中/对称化/往返一致与差异发现/CLI 端到端/坏顶层返回 1/--max-warnings 门禁）。回归 139 项全部通过，兼容 Python 3.6.5。

### 3.37 JSON 快照回放浏览站点 `--from-json X --browse OUT`（P124）
- **双轨站点生成**：对象驱动（`render_browse_site`）与快照驱动（`render_snapshot_browse_site`）并存——后者直接从 JSON 快照 dict 渲染离线自包含 HTML 站点，零源码依赖，与 P123 可交换格式闭环保最后一公里（导出→传递→导入→浏览→归档回放）。
- **页面构成**：`index.html`（元数据 / 统计卡 / 文件列表 / 函数索引 / 类索引 / 子页导航）+ `src/<rel>.html` 文件页（文件卡 + 函数卡 `id="fn-…"` 锚点 + 类卡 `id="cls-…"`：签名、限定名、输入/输出、参数文档、调用/被调用互链、内置调用 ×N、未解析调用）+ 子页（`metrics.html` 函数风险度量 / `checks.html` 静态检查 / `unresolved.html` 疑似漏检 / `matlab_lib.html` 内置库函数；快照含 `taint` / `doc_todos` 时附 `taint.html` / `todo.html`）+ 内嵌 `snapshot.json` 归档副本。
- **快照自适应**：`_snapshot_index` 重建调用图节点索引，函数以 `rel:name` 键互链（src 子目录用 `_snapshot_rel_href` 相对路径，链接不失效）；`_snapshot_attach_file` 给扁平化检查项（uninitialized / type_mismatch / dead_code）按函数名反查补 `file` 字段，checks 页跳转可用；`_snapshot_metric_rows` 以 call_graph 出入边传递闭包计算影响面 / 依赖面（快照不含圈复杂度 → cx=0），风险公式与对象模式一致；`_snapshot_unresolved_rows` 聚合 `external_calls` 为疑似漏检表。
- **复用与门禁**：`metrics / checks / unresolved / matlab_lib / taint / todo` 六页复用既有渲染器（`render_metrics_page` / `render_checks_page` / `render_unresolved_page` / `render_matlab_lib_page` / `render_taint_page` / `render_todo_page`），样式复用 `BROWSE_CSS`；`--from-json` 短路内追加 `--browse` 分支，与 `--json` 重导出 / `-o` 快照报告 / `--max-warnings` 门禁可自由组合。
- **回归入测试**：新增 `test_p124_snapshot_browse` 7 个覆盖点（真实快照站点产物齐全 / 索引页内容 / 文件页函数卡 / 子页内容 / snapshot.json 归档副本合法 / 手工最小快照回放 / 检查项 file 反查补全不崩溃）。回归 139 项全部通过，兼容 Python 3.6.5。

### 3.38 双快照差异对比 `--diff BASE CUR`（P126）
- **CI 场景补齐**：为 P123 可交换格式与 P124 快照回放补齐「基线 vs 当前」变更可观测性——两个 `--json` 导出的快照（典型：`--reproducible` 生成的 CI 基线 vs 当前提交）经 `--diff BASE CUR` 对比，`--fail-on-diff` 提供零漂移门禁（有差异返回退出码 1，无差异返回 0）。
- **五层语义对齐**：文件（key=`rel`，`lines / functions / parse_errors / classes` 字段级明细）、函数（key=`rel:name`，`line / signature / inputs / outputs / variadic / header / input_docs / calls` 字段级明细 + 调用集「+添加 -删除」）、类（key=`rel:name`，`line / superclass / methods` 明细）、调用边（key=`caller → callee`，含跨文件边）、告警（未初始化 / 类型不一致 / 形状不匹配 / 死代码 / 污点流 / 函数待办 / 命名常量 / 全局变量 / 类型声明 / 维度推断十组按 `file:func:line[:name]` 对齐）；全部按 key 而非索引，位置无关、顺序无关，`_diff_keyed` 统一「新增-删除-修改」判定。
- **报告双通道**：stdout 纯文本摘要（`[元数据]` 路径/version/root + `[概览]` 各维度 A→B 计数与变化量 + 各层新增-删除-修改明细 + 结论）+ `-o` 渲染 Markdown 报告（`# 双快照差异对比报告` + 各小节 `text` 代码块）；`generated_at` 时间戳差异忽略，`version` / `root` 差异单列提示；坏 JSON / 缺文件返回 1 并 stderr 报错。
- **稳健与兼容**：`_snapshot_group_list` 兼容 dict 容器带子键（`taint.flows` / `doc_todos.todos`），`_flatten_global_vars` 处理 dict 型 `global_vars`；全程 Python 3.6.5 兼容语法（`%` 格式化、无 walrus、无 3.7+ 特性）。
- **回归入测试**：新增 `test_p126_snapshot_diff` 8 个覆盖点（相同快照完全一致 / 变异快照五层逐层命中 / 函数 line+calls 字段级明细 / 类 methods 明细 / -o Markdown 报告 / --fail-on-diff 有差异退出 1 无差异退出 0 / 坏 JSON 返回 1 / 手工最小快照无差异）。回归 140 项全部通过，兼容 Python 3.6.5。

### 3.39 快照内容寻址指纹 `--fingerprint` / `--verify`（P127）
- **CI 两级缓存定位**：为 P126 差异对比补齐「判变先于定位」——`--verify` 哈希比对 O(1) 秒级判「变/没变」，命中不变则无需跑慢速 `--diff` 语义定位；快照 + 指纹文件一并提交基线库，`--verify` 兼防手工篡改（快照被改 → 指纹失配 → 退出码 1 拦截）。
- **三层内容寻址 SHA-256**：整体（`_fp_sha256` 对规范化全量快照）、逐文件（key=`rel` 对齐，含 `lines / functions / classes` 摘要）、告警组 12 组（`uninitialized` / `type_mismatch` / `shape_mismatch` / `dead_code` / `taint.flows` / `taint.sinks` / `doc_todos.todos` / `constants` / `types` / `dimensions` / `global_vars` / `edges`）；`_fp_canon` 递归规范化 dict 键序（键序无关、list 保序）、剥离顶层 `generated_at` 时间戳（跨运行可复现，与 `--reproducible` 语义一致）。
- **指纹生成 `--fingerprint SNAP`**：stdout 打印整体指纹（ASCII `SNAPSHOT_SHA256` 标记便于脚本消费）+ 逐文件指纹清单 + 告警组指纹；`--json` 落盘指纹文件（`{tool, command:"fingerprint", algorithm:"sha256", version, snapshot{path, sha256, version, excluded, files, functions, classes, edges, generated_at}, files[], groups{}}`）。
- **防篡改校验 `--verify FP [SNAP]`**：重算当前快照三层指纹并与指纹文件逐项比对——整体指纹、文件「新增 FILE_ADDED / 变化 FILE_CHANGED / 删除 FILE_DELETED」、告警组 `GROUP_CHANGED`；任何不一致输出 `VERIFY_RESULT MISMATCH count=N` 并返回退出码 1，一致输出 `VERIFY_RESULT OK` 返回 0；SNAP 可选覆盖指纹文件 `snapshot.path` 记录（快照迁移 / CI 换目录）；坏 JSON / 非法指纹文件（缺 `command=fingerprint`）返回 1 并 stderr 报错。
- **回归入测试**：新增 `test_p127_fingerprint` 8 个覆盖点（相同快照指纹可复现 / 指纹文件结构完整含 excluded / 变异快照触发整体指纹变化 / 一致 verify 返回 0 且 VERIFY_RESULT OK / 篡改 verify 返回 1 且 FILE_CHANGED / 删除文件返回 1 且 FILE_DELETED（含 SNAP 显式路径覆盖）/ 坏 JSON 与非法指纹文件返回 1 / generated_at 时间戳变化不影响 verify 一致性）。回归 141 项全部通过，兼容 Python 3.6.5。

### 3.40 增量缓存内容寻址 `--incremental` 签名升级 + `--incr-report` 缓存健康报告（P133）
- **签名升级（mtime → 内容 SHA-256）**：P71 增量缓存用 `(mtime_ns, size)` 判脏——CI / git checkout / 文件复制 / 换机器后 mtime 全变但内容未变，缓存 100% 失效，增量形同虚设。P133 将 `_file_signature` 升级为 `(SHA-256(内容), size)`，与 P127 快照指纹统一算法；同内容不同 mtime 仍命中，CI 增量收益恢复。
- **缓存路径可配 `--incr-cache PATH`**：覆盖默认 `.matlabc_cache.pkl`，支持把缓存放到工作区外（避免污染仓库）、或按分支/任务隔离多份缓存。
- **缓存健康报告 `--incr-report [text|json|md]`**：透明化"增量到底命中没有"——输出文件总数 / 命中 / 未命中 / 命中率 + 逐文件 hit/miss 清单；json 格式含 `marker:"P133"` 与 `algorithm:"sha256"` 供 CI 脚本消费；`--incr-report-out` 落盘任意格式。
- **兼容与回退**：stats 增补 `cache_total / cache_hit_rate`（未开增量不含）；旧格式签名缓存（mtime,size）与新签名不匹配 → 自动全 miss 重建不崩溃；损坏缓存 `_load_incremental_cache` 返回空 dict → 安全回退全量。
- **回归入测试**：新增 `test_p133_incremental_ca` 8 个覆盖点（首次全 miss 且命中率 0 / 同内容改 mtime 100% 命中 / 改一文件仅该文件 miss / 自定义缓存路径 / json 报告结构含 marker 与 algorithm / md 表格含 rel 与 hit-miss / 损坏缓存回退全量 / 旧格式签名全 miss 重建）。回归 142 项全部通过，兼容 Python 3.6.5。

---

### 3.41 交互与离线增强（P147，全套 8 项）

> 设计原则：**最先进技术 + 离线可用 + 零依赖**。全部基于项目既有前端零件与数据模型，不引入任何外部依赖、不破坏 Python 3.6.5。

- **① 全局调用图缩放/平移/复位（补齐历史不对称）**
  全局 `#cg-svg` 此前遗漏了 P83 局部图已实现的视图变换。现接入 `cgZoomBy`/`cgResetView` + 工具栏 `+/−/复位` + 实时百分比，支持滚轮锚点缩放、拖拽平移、键盘 `+/−/0`、聚焦态。复用 P83 同一套 UX，成本极低。
- **② 搜索结果风险徽章（让交互"有脑子"）**
  `Ctrl+K` 全局搜索命中项，按调用图 `meta.fl`（污点 `t` / 高复杂度 `hd` / 高扇入 `hi`）与同名候选 `dups` 渲染彩色徽章——用户跳过去之前先知道风险。数据层新增 `fl` 标志位（`_build_call_graph_json`）即同步具备可视化呈现。
- **③ `--html` 报告 Mermaid 离线优先（消除离线阻塞）**
  移除原本硬编码的同步 CDN `<script src=cdn.jsdelivr.net>`，改为"在线按需注入、离线回退为静态 `<pre>` 文本"，离线打开报告不再空白/卡网络。
- **④ `--gen-ci [github|gitlab|both|list]` 一键 CI 模板**
  把已齐引擎（`--json`/`--sarif`/`--sarif-diff`/`--fail-on-diff`/`--max-warnings`/`--reproducible`）串成可直接粘贴的 GitHub Actions / GitLab CI 片段，锁定 Python 3.6.5 兼容基线。`list` 打印支持的门禁引擎清单。
- **⑤ `--diff-html BASE CUR` 双栏差异可视化**
  复用 P126 五层差异结构（`_diff_files/_diff_functions/_diff_classes/_diff_edges/_diff_checks`），渲染并排「基线 A / 当前 B」逐文件对比（行级 `+/-/~` 符号 + 彩色高亮 + 暗色主题）。彻底补齐 P126"有数据无视图"缺口。
- **⑥ 告警置信度分级 `confidence`**
  未初始化区分 **high**（读前无写，真问题概率高）与 **medium**（仅条件分支赋值，误报概率较高）。在 JSON `uninitialized[].confidence` / SARIF `properties.confidence` / 静态检查汇总页（高置信计数）同步呈现。
- **⑦ `--min-confidence {low|medium|high}` 门禁**
  仅统计/卡高置信项，直接降低 CI 噪音（`--min-confidence high` 只卡读前无写的真问题）。
- **⑧ 数据-视图同步纪律**
  本次所有新增数据字段都配套可视化，根治历史"数据有、呈现缺"的系统性滞后。
- **回归入测试**：新增 `test_p147_interaction_upgrade`（5 覆盖点：缩放控件/缩放逻辑/meta.fl/搜索徽章样式/Mermaid 离线回退）+ `test_p147b_genci_and_diffhtml_and_confidence`（7 覆盖点：gen-ci both 片段/清单/diff-html 双栏/置信度字段）。回归 144 项全部通过，兼容 Python 3.6.5。

---

### 3.42 实时化与跨版本增强（P150/P152/P151）

- **① `--watch [INTERVAL]` 守护监听（P150，批处理→实时）**
  轮询目录，按 P133 内容 SHA-256 签名（`_file_signature`）检测脏文件，变更即把「除 `--watch` 外」的原参数作为子进程重跑（复用全部分析代码），重生成 `--browse` 站点并写 `watch_status.json`。配套 `watch.html` 用 `<meta http-equiv="refresh">` 纯轮询 + `fetch` 读状态，**零 WebSocket、零依赖、离线可用**——浏览器打开即实时提示守护状态，Ctrl+C 退出。这是工具首次从"一次性批处理"进化为"常驻实时分析器"。
- **② `--incr-format {pickle,json}` 缓存格式（P152，跨版本安全）**
  新增 JSON 缓存格式：结构为 `{version, algorithm:"sha256", entries:{rel:{sig, blob(base64 pickle)}}}`，与 P127 内容指纹哲学统一，跨 Python 版本/工具可读、可人工检查、可被其他工具直接消费；pickle 格式（默认）保留以兼容既有工作流。损坏条目安全跳过（回退全量）。
- **③ 污点流 SVG 路径图（P151，表格→数据流图）**
  taint.html 新增「源→汇」节点链可视化：左源（绿）/ 右汇（红）/ 中间节点（蓝），箭头连接传播路径；**点击表格行高亮对应 SVG 路径**、**hover 节点逐步高亮其上溯链**，把原本的纯表格数据升级为可理解的数据流图。复用既有 SVG 零件（无新依赖）。
- **回归入测试**：新增 `test_p150_watch_and_incrjson_and_taint_svg`（4 覆盖点：json 缓存元信息+复用/--watch 产物 watch.html+status/污点 SVG 路径图容器+节点链）。回归 145 项全部通过，兼容 Python 3.6.5。

### 3.43 P153：AI 审查提示词包（离线、零依赖、纯规则）

- **① `--ai-prompts [PREFIX]` 生成 AI 审查任务书**
  基于 `main` 中已就绪的分析数据（`files` / `model` / `stats` / `checks_for_sarif`），自动汇总成一份**可直接粘贴到任意离线 AI 工具**的结构化审查提示词：含项目概览（文件/函数/类/调用边/污点统计）、P0→P2 分级清单（未初始化变量高置信优先、危险污点链路、高圈复杂度函数 ≥15、高扇入枢纽 ≥6、类型不一致/死代码、同名歧义候选）、以及给 AI 的明确任务指令（按"问题/位置/建议/收益/风险"五要素输出）。
- **② `--ai-prompts-format {md,txt}`**
  Markdown（默认）或纯文本输出；txt 自动剥除 `**`/`` ` `` 等 Markdown 标记，适配纯文本粘贴场景。
- **③ 输出路径**
  `-o PATH` 指定完整输出路径；否则按 `PREFIX` 自动补 `.md`/`.txt` 扩展名（默认 `ai_review_prompts`）。
- **④ 零外部调用**
  仅复用已算好的结构化数据，**不依赖任何在线服务或大模型 API**，彻底离线可用，与本项目"离线、零依赖"总原则一致。把"数据→可行动建议"的最后一环交给用户手头的 AI 工具，而非内嵌模型（避免依赖漂移、保证可审计）。
- **回归入测试**：新增 `test_p153_ai_prompts`（3 覆盖点：md 生成且含 P0-P2 全章节/txt 生成且剥除 Markdown 标记/退出码 0）。回归 146 项全部通过，兼容 Python 3.6.5。

### 3.44 P154：自动生成测试桩骨架（离线、零依赖、纯规则）

- **① `--gen-tests-risk [PREFIX]` 生成测试桩**
  基于 `main` 中已就绪的高风险发现，逐个生成测试桩：`uninitialized`（高置信优先）→ `test_<func>_uninit_<var>`；`type_mismatch` → `test_<func>_type_<var>`；`dead_code` → `test_<func>_deadcode`；高复杂度函数（≥15）→ `test_<func>_smoke`；`tainted_sink`（level≤2 危险汇聚）→ `test_<func>_taint_<var>`。每个桩含**风险说明注释 + `# TODO` 具体补全指引 + 占位断言 `assert True`**，把"该测什么"从人工梳理降级为自动清单。与 P90 的 `--gen-tests`（按语言逐函数生成到目录）互补、命名独立不冲突。
- **② `--gen-tests-format {pytest,unittest}`**
  默认 pytest（顶层 `def test_*`）；可选 unittest（生成 `class TestGenerated(unittest.TestCase)`）。
- **③ 输出与可执行性**
  `-o PATH` 指定完整路径，否则按前缀自动补 `.py`；生成文件**语法合法、可被 pytest 直接 `--collect-only` 收集**（已入回归验证），全绿时仍输出"无高风险发现"占位测试保证文件可执行。
- **④ 零外部调用**
  仅复用已算好的 `checks_for_sarif` / `files` 数据，不依赖任何在线服务，与"离线、零依赖"总原则一致。
- **回归入测试**：新增 `test_p154_gen_tests`（4 覆盖点：生成 .py+含 test_ 函数/五类风险各生成对应桩/生成文件可被 pytest 收集/unittest 风格形态）。回归 147 项全部通过，兼容 Python 3.6.5。

### 3.45 P157：测试腐化清理专项（恢复全绿地基）

- **背景**：随 P147（调用图引入 `fn.complexity`/`fn.header`/`fn.signature` 访问）演进，5 个底层数据测试用的合成桩 `_Fn`/`_Mf` 未同步补齐属性，导致 `AttributeError` 长期红（误报噪音）。
- **根因**：`_build_global_cg` 读取 `fn.complexity`（P147 热点口径）等属性，而测试桩 `_Fn` 仅有 `name/kind/line`。
- **修复**：将 `_Fn` 桩对齐真实 `Function` 行为——补齐 `complexity`（默认 1）、`header`（默认 `{}`）、`signature()`（返回 `name`）、`calls`（默认 `[]`）。改动**仅限测试桩**，不动被测源码。
- **结果**：`test_call_order_preserved` / `test_callgraph_deep_chain_data` / `test_callgraph_cycle_detection` / `test_p52_dup_candidates_visualization` / `test_p80_ambiguous_switch` 全部转绿；完整套件 **147 passed / 0 failed**（82.6s），为后续里程碑建立可信基线。无版本号变更（属测试地基修复，不计入特性里程碑）。

### 3.46 P155：技术债聚合报告（离线、零依赖、可排序债主榜单）

- **① `--debt [PREFIX]` 生成债主榜单**
  基于 `main` 中已就绪的指标，按文件/目录聚合并计算综合 **debt_score**（可解释启发式权重 `_DEBT_W`：`complexity=1.0 / max_complexity=2.0 / fan_in=0.5 / uninit=5.0 / mismatch=3.0 / dead=1.0 / dup_groups=4.0`）。每个文件行含：总复杂度、峰值复杂度、函数数、扇入、未初始化/类型不一致/死代码/歧义组计数。
- **② 输出内容**
  Markdown 含：总览（债分/各风险计数）、**Top20 债主榜单**（按 debt_score 降序）、**目录级 rollup（Top15）**、**修复优先级建议**（先打未初始化/类型不一致→再削峰值复杂度→最后清死代码/歧义）。
- **③ `--debt-format {md,json}`**
  MD 默认；JSON 含 `summary` / `top_debt_files` / `dir_rollup` / `weights`，便于 CI 程序化消费（如设阈值卡口）。
- **④ 零外部调用**
  仅复用已算好的 `files` / `model.callers_of` / `checks_for_sarif` / `_dup_candidates`，与 P153/P154 同数据源，离线可用。
- **回归入测试**：新增 `test_p155_debt`（3 覆盖点：md 生成+降序校验/json 合法+降序校验）。回归 148 项全部通过，兼容 Python 3.6.5。

### 3.47 P156：指标趋势报告（离线、零依赖 Sparkline）

- **① `--trend [PREFIX]` 累积快照**
  把本次分析的关键指标（文件数/函数数/总复杂度/峰值复杂度/未初始化/类型不一致/死代码/债总分）作为一个快照追加进本地趋势基线（JSON，默认 `.debt_trend.json`），并生成 Markdown 趋势报告。基线可提交版本库，长期追踪质量演化。
- **② 零依赖 Sparkline 迷你图**
  `_trend_sparkline` 用 Unicode 方块字符（▁▂▃▄▅▆▇█）绘制各指标演化曲线，**不依赖任何图表库**，纯文本可粘贴。
- **③ 趋势总览 + delta**
  报告含「趋势总览表」（最新值 / 首快照 / Δ / 方向箭头 ↑↓）与「最近快照明细表」，让"是否在变好"一眼可见；不足 2 快照时仅展示当前快照并提示需累积。
- **④ 配置项**
  `--trend-baseline PATH`（默认 `.debt_trend.json`）、`--trend-limit N`（默认 12，控制保留/展示的最近快照数）。
- **⑤ 复用与一致性**
  债总分直接复用 P155 的 `_compute_debt_rows`（已抽取为共用纯计算函数），与 P153/P154/P155 同源，避免口径漂移。
- **回归入测试**：新增 `test_p156_trend`（3 覆盖点：单快照展示/双快照趋势+sparkline 块字符/文件数 delta=1↑）。回归 149 项全部通过，兼容 Python 3.6.5。

### 3.48 P160：质量门禁 CI 闭环（离线、零依赖、指标→门禁回路）

- **① `--gate [BASELINE]` 开启门禁**
  读取 P156 趋势基线（默认 `.debt_trend.json`）。若基线不存在或不足 2 快照，本次快照作为首基线、门禁**直接放行**（避免首扫误伤），并把快照追加持久化，供下次对比。
- **② 三类阈值**
  `--gate-max-debt`（技术债总分硬上限）、`--gate-max-delta`（相对上一快照的债分增量上限，防止质量回退）、`--gate-max-uninit`（未初始化告警数硬上限，0 即零容忍）。
- **③ 判定即退出码**
  任一门禁未过则置 `ok=False` → 进程返回 1，可直接串进 CI 的 `&&` 链（如 `matlabc src --gate .debt_trend.json --gate-max-uninit 0 && echo PASS`）。
- **④ 编码安全的 ASCII 判定令牌**
  stdout 随判定输出 `[P160 GATE: PASS]` / `[P160 GATE: FAIL]` / `[P160 GATE: BASELINE]`，跨平台 GBK/UTF-8 均可可靠解析（中文详情一并输出，但令牌纯 ASCII 不受控制台编码影响）。
- **⑤ 复用与一致性**
  快照捕获/加载/保存复用 P156 的 `_trend_capture_snapshot` / `_trend_load_baseline` / `_trend_save_baseline`，债总分复用 P155 的 `_compute_debt_rows`，与 P153/P154/P155/P156 同源。
- **回归入测试**：新增 `test_p160_gate`（4 覆盖点：首基线放行/未初始化上限零容忍失败/债分上限放行/增量上限回退失败）。回归 150 项全部通过，兼容 Python 3.6.5。

### 3.49 P161：持续质量哨兵（`--watch` + `--gate` 联动，本机保存即把关）

- **① 零改造成本**
  `--watch` 守护把「除 `--watch` 外」的原参数作为子进程重跑，因此 `--gate` 由子进程原样执行，门禁逻辑完全复用 P160，无新代码路径、无新参数解析。
- **② verdict 透传**
  守护捕获重分析子进程的退出码，将其映射为门禁 verdict，写入 `watch_status.json` 的 `gate` 字段（通过=True / 未过=False），并随守护日志打印 `[P161 门禁 通过/未通过]`，浏览器端 watch.html 轮询即可见。
- **③ `.gate_fail` 标记文件**
  门禁未过时自动在 `--browse` 输出目录创建 `.gate_fail`，通过后自动删除。开发者、IDE 插件或本地 CI 可轮询此文件即时感知质量回退（无需解析日志）。
- **④ 复用与一致性**
  零新增依赖，与 P150 守护、P160 门禁、P156 趋势基线、P155 债总分计算同源；趋势基线受 `--trend-limit` 上限保护，watch 高频变更不致基线无限膨胀。
- **回归入测试**：新增 `test_p161_watch_gate`（2 覆盖点：未初始化触发 `.gate_fail` 创建 + `watch_status.json` 含 `gate=false` / 修复后标记删除 + `gate=true`）。回归 151 项全部通过，兼容 Python 3.6.5。

### 3.43 统一代码结构图与跨层闭门（P200-P203）
- **P200 变量实体化**：`build_analysis_model` 现返回 `variables` / `varflow` / `uninit`，变量首次作为一等实体缓存进 `model`（带 `owner_id`，与函数、文件共享同一图对象），可被图引用、可被跨页跳转。
- **P201 统一 `__CG__` v2**：`_build_global_cg` 新增 `folder` / `file` / `variable` 三类节点与 `contain`（包含）/`flow`（数据·污点流）两类边；并把 `down`/`up`/`contain`/`flow` 全部归一为「按 gid 索引的列表」，前端 `UNIFIED_GRAPH_JS` 与 Python 后端 P203 口径完全统一。修复 P201 后端 `_url_encode` 未定义 NameError 与 `contain` dict→list 序列化 KeyError 两处根因缺陷。
- **P202 统一画布 `unified.html`**：新增 `UNIFIED_GRAPH_JS`（离线零依赖）——单画布同时呈现四类节点，`contain` 灰线 / `flow` 红虚线 / `call` 蓝线；单击节点聚焦（叠加函数调用链路）、双击跳源码、类型过滤 chip（文件夹/文件/入口/函数/变量）+ 关键字搜索 + 缩放拖拽。采用「新增独立页」而非改造既有 `initLocalCG`，零侵入、回归面最小。
- **P203 跨层闭环**：`_folder_impact_closure`（改某目录牵动多少代码——内部节点 + 沿调用图上游调用者 + 下游被调的闭包）、`_trace_var_taint_source`（变量污点溯源链——沿 `flow` 找到经手函数再沿调用图 up 追溯到数据入口）、`_gate_by_folder`（按目录聚合债分/未初始化并单独门禁）；新增 CLI `--gate-max-uninit-folder` / `--gate-max-debt-folder`，令牌 `[P203 GATE: PASS/FAIL]`；新增 `folder_impact.html` / `var_taint.html` 两页。
- **回归入测试**：新增 `test_p200_p203_unified_graph_and_folder_gate`（4 覆盖点：统一图产物 + 索引导航 / `__CG__` 含 variable 节点 / `__CG__` 含 contain+flow 边 / 按目录门禁 FAIL↔PASS 切换）。回归 152 项全部通过，兼容 Python 3.6.5。

### 3.44 P203 增强：跨文件 / 大仓库 / CI 矩阵（P203+）
在 P200-P203 既定目标之上补足工程化闭环（v1.16.18）：
- **`--gate-folder-report FILE`**：把「按文件夹门禁」每目录明细（`uninit` / `debt_score` / 是否越界）导出为 JSON（含 `pass` / `per_folder` / `thresholds`），供 CI 按目录并行门禁矩阵消费；
- **`--max-nodes N`**：统一 `__CG__` 节点数硬上限，超出时按「folder>file>function>variable」优先级保留高价值节点、截断低价值变量节点，保障 300+ 文件仓库的 `unified.html` 仍可渲染（截断后 `meta`/`down`/`up`/`contain`/`flow` 仍为完整数组，前端无需感知差异）；
- **C3 跨文件污点聚合**：`_trace_var_taint_source` 接入 `_collect_global_vars`，对 `global` / `persistent` 变量把**其他文件同名声明函数**纳入污点链（共享同一份状态，真正的跨文件数据流节点），`var_taint.html` 新增 `⌥` 跨文件标注；
- **`UNIFIED_GRAPH_JS` 节点分级**：`KIND_PRIORITY` 已支持 folder>file>function>variable，与 `--max-nodes` 截断口径一致；
- **缓存健壮性**：`_build_global_cg` 的跨页缓存由「`id(calls_of)`」改为「`id` + 对象引用 `is` 校验」，杜绝 Python 对象 id 复用导致的脏缓存命中；
- **回归入测试**：新增 `test_p203_enhancements`（3 覆盖点：`--gate-folder-report` JSON / `--max-nodes` 截断保 folder / C3 跨文件污点聚合）。回归 153 项全部通过，兼容 Python 3.6.5。

### 3.45 P204 增强：统一画布图层开关 / SARIF 门禁 / 智能截断 / 跨文件全局状态图（P204+）
按计划「下一步建议」推进四项实质增强（v1.16.19）：
- **① 统一画布图层开关**：`unified.html` 工具栏注入 `包含 / 数据流 / 调用` 三个连线图层按钮（`ug-l-contain` / `ug-l-flow` / `ug-l-call`），`UNIFIED_GRAPH_JS` 的 `buildAdj` 按 `state.layers` 实时过滤 `contain` / `flow` / `call` 三类边，用户可单独显隐任意图层，聚焦「调用关系」或「数据/污点流」时不再被包含边干扰；
- **② `--gate-folder-report-format sarif`**：`--gate-folder-report` 新增 SARIF 2.1.0 输出（规则 `MA-UNINIT-FOLDER` / `MA-DEBT-FOLDER`），可直接接入 GitHub Code Scanning / 常见 CI 安全面板，门禁 FAIL 时非零退出、SARIF 仍落盘；
- **③ `--max-nodes` 智能截断**：含污点（`fl.t`）或未初始化（`fl.uninit`）的变量提升为「函数级」优先级，截断时优先保留风险变量节点（不再一刀切删 variable 导致看不出风险点），cg 新增 `truncated` 标记供前端提示；
- **④ `--global-state FILE`**：新增跨文件全局状态图 `global_state.html`，聚合 `global` / `persistent` 共享状态，标注跨文件声明的隐式共享变量（同一变量名在 ≥2 个文件声明，重构/并行化高危），可排序表格 + global/persistent 双标签切换；
- **回归入测试**：新增 `test_p204_enhancements`（4 覆盖点：SARIF 门禁 / global_state 跨文件冲突 / 智能截断保污点变量 / 统一画布图层开关）。回归 154 项全部通过，兼容 Python 3.6.5。

### 3.46 P205 增强：统一画布下沉 / SARIF 行级定位 / 全局状态下钻 / CI 模板（P205+）
按计划「下一步建议」推进五项实质增强（v1.16.20）：
- **① 聚焦视图跳转统一画布（P205-1）**：`folder_impact.html` / `var_taint.html` 经 `_p203_page` 包装注入「打开统一画布」入口按钮，零风险复用已验证的 `UNIFIED_GRAPH_JS` 图层开关（含/数据流/调用 三类连线可单独显隐），避免两套渲染器拆分维护；
- **② SARIF 行级定位（P205-3）**：`--gate-folder-report-format sarif` 将每个未初始化变量生成独立 result，含 `region.startLine` 真实行号与变量名（如 `c.m` 的 `undef_var` 定位到 `L2`），CI 安全面板可直接跳转问题行；JSON 门禁报告同步新增 `uninit_items: [(line, var)]`；
- **③ `_CG_CACHE` 截断缓存固化（P205-2）**：明确「缓存键含 `max_nodes`，首次构建完整图后任意 `max_nodes` 切换直接命中」设计，满足 300+ 文件仓库的重复渲染性能目标；
- **④ `global_state.html` 冲突下钻（P205-4）**：跨文件冲突变量行可点击展开声明明细（文件/函数/行）+ C3 跨文件数据流高危提示，把 C3 跨文件污点链与全局状态图打通；
- **⑤ CI 矩阵门禁模板（P205-5）**：新增 `ci-examples/`（GitHub Actions + GitLab CI 示例），演示「按目录并行 `--gate` 门禁 + SARIF 上传安全面板」的开箱即用闭环；门禁 FAIL 时非零退出但 SARIF 仍落盘并上传；
- **回归入测试**：P205 覆盖点并入 `test_p204_enhancements`（SARIF 行级 startLine / global_state 下钻 / p203 跳转按钮）。回归 154 项全部通过，兼容 Python 3.6.5。

### 3.47 P206 增强：SARIF 规则细分 / 全局状态调用方追溯 / 单函数数据流图层 / 增量门禁 / 截断横幅（P206+）
按计划「下一步建议」推进五项实质增强（v1.16.21）：
- **① SARIF 规则细分 + helpUri（P206-1）**：`--gate-folder-report-format sarif` 区分 `MA-UNINIT-FOLDER`（目录聚合，兜底）与 `MA-UNINIT-VAR`（变量级行定位）两个独立规则，每个规则含 `helpUri`，CI 面板（GitHub Code Scanning / GitLab）可按规则类型聚合、跳转说明文档；
- **② `global_state.html` 反向追溯调用方（P206-2）**：跨文件冲突变量行下钻时，除声明明细外额外展示「声明函数的调用方（跨文件传播路径）」，复用 `model.callers_of` 反查，真正打通 C3 跨文件污点链与全局状态图；
- **③ `func_detail.html` 数据流图层（P206-3）**：单函数详情页新增「数据流图层」按钮，点击展开涉及本函数的 `flow` 边（变量↔函数 数据/污点流），复用 `fdState.showFlow` 局部状态，不破坏现有 SVG 调用图；
- **④ CI 增量门禁模板（P206-4）**：新增 `ci-examples/github-actions-incremental.yml`，用 `git diff` 计算变更目录并只对变更目录跑 `--gate --incremental`，配合 `.matlabc_cache.pkl` 缓存大幅提速 PR 场景；
- **⑤ unified.html 截断横幅（P206-5）**：画布达 `--max-nodes` 上限时渲染提示横幅（告知已按「文件夹>文件>函数>变量」优先级截断低价值节点、引导调大 `--max-nodes` 或用搜索/下钻聚焦），由 `_ug_trunc_banner` 从 cg JSON 的 `truncated` 标记动态生成；
- **回归入测试**：P206 覆盖点并入 `test_p204_enhancements`（SARIF 规则细分 MA-UNINIT-VAR+helpUri / func_detail 数据流按钮 / unified 截断横幅）。回归 154 项全部通过，兼容 Python 3.6.5。

### 3.47.1 P207 增强：SARIF 严重度分级 / 全局状态双向追踪 / 单函数流图 SVG / 多 SARIF 合并 / 截断变量可点击（v1.16.22）

在 P200-P206 既定目标之上，把「安全面板可用性与数据可寻性」补到闭环（v1.16.22）：

- **① SARIF 严重度分级（P207-1）**：`--gate-folder-report-format sarif` 的 `MA-UNINIT-VAR` 行级结果 `level` 不再固定为 `error`，而由 `_detect_uninitialized` 的 `confidence`（high→`error` / medium→`warning`）映射。`uninit_items` 携带 `(line, var, level)` 三元组，CI 安全面板可按 severity 排序、配置「仅 error 阻断 / warning 仅提示」，避免把中等置信告警误当作硬阻断。
- **② `global_state.html` 双向追踪 sinks（P207-2）**：跨文件冲突变量下钻时，除 P206-2 的「上游调用方」外，新增「下游耦合方（sinks）」——同一全局变量名在**其它**函数也被读写的声明点（跨文件隐式共享状态的下游汇点），以 `.cf3` 紫色区块呈现，配合 `.cf2` 上游区块形成完整双向数据血缘视图。
- **③ `func_detail.html` 流图 SVG 覆盖层（P207-3）**：数据流图层的 `flow` 边由纯文本列表升级为**自包含 SVG 节点-连线图**——本函数居中，入边（其它→本函数）红虚线列左侧、出边（本函数→其它）蓝虚线列右侧，节点可点击跳转对应函数/变量详情页，直观呈现单函数的污点/数据流向。
- **④ 多 SARIF 合并 CI 模板（P207-4）**：新增 `ci-examples/github-actions-sarif-merge.yml` + `ci-examples/merge_sarif.py`，支持按模块/目录并行扫描、各自产出 SARIF 后由 `merge_sarif.py` 去重合并为单一报告上传 code scanning，解决「分片扫描互相覆盖」问题（兼容 Python 3.6.5）。
- **⑤ unified.html 截断变量可点击（P207-5）**：`--max-nodes` 截断时，`_build_global_cg` 记录被丢弃的变量名清单（`truncated_vars`，高价值优先），`_ug_trunc_banner` 将其渲染为可点击 `ug-tv` chip——点击即在搜索框预填变量名并开启「变量」图层聚焦，把「截断后完全看不到这些变量」变为「一键下钻定位」。
- **回归入测试**：P207 覆盖点并入 `test_p204_enhancements`（SARIF 行级 level∈{error,warning} / global_state 含下游 sinks 区块 / func_detail 含 flow SVG 覆盖层 / 截断横幅含可点击 `ug-tv` 且 cg 含 `truncated_vars`）。回归 154 项全部通过，兼容 Python 3.6.5。

### 3.47.2 P208 增强：SARIF 规则补全 / 变量级修复建议 / 全局状态↔单函数双向溯源（v1.16.23）

在 P200-P207 闭环之上，把「安全面板覆盖度 + 问题→修复闭环 + 视图联动」补到生产可用（v1.16.23）：

- **① SARIF 规则补全（P208-2）**：`--gate-folder-report-format sarif` 新增两类独立规则 `MA-TYPE-MISMATCH`（类型不一致，行级定位）与 `MA-DEAD-CODE`（死代码，行级定位），各带 `helpUri` 与 `level=warning`。此前这两类问题仅间接体现在技术债分里，现在 CI 安全面板可对其单独排序/处理，使 SARIF 覆盖全部静态检查类别（uninit / type-mismatch / dead-code / debt）。
- **② 变量级修复建议（P208-1）**：`func_detail.html` 数据流图层对每个落入未初始化索引的 flow 节点，直接渲染「可执行修复建议」卡片（按 `reason` 区分：读前未赋值 / persistent 守卫 / global 显式赋值），把「发现问题」闭环到「可执行修复」，置信度以标签呈现。
- **③ 全局状态↔单函数双向溯源（P208-3）**：`func_detail.html` 支持 `?flow=1` 自动展开数据流图层；`global_state.html` 的上游调用方 / 下游耦合方节点改为可点击链接（`gs-jump`），跳转 `func_detail.html?g=<gid>&flow=1`，打通「全局状态图 ↔ 单函数视图」双向溯源，消除信息孤岛。
- **回归入测试**：P208 覆盖点并入 `test_p204_enhancements`（SARIF 规则含 MA-TYPE-MISMATCH/MA-DEAD-CODE / func_detail 注入 `__UNINIT_INDEX__` 且含 fd-suggest / func_detail 支持 flow=1 且 global_state 含 gs-jump 跳转链接）。回归 154 项全部通过，兼容 Python 3.6.5。

### 3.47.3 P209 增强：SARIF 规则持续补全 / 全局状态耦合图 / 多 SARIF 质量概览（v1.16.24）

在 P200-P208 既定目标之上，把「安全面板覆盖完整 + 全局状态可视化 + CI 质量可见性」补齐到闭环（v1.16.24）：

- **① SARIF 规则持续补全（P209-2）**：`--gate-folder-report-format sarif` 再新增两类独立规则 `MA-SHAPE-MISMATCH`（矩阵/数组形状约束不匹配，行级）与 `MA-TAINT-SINK`（污点变量流入危险输出点，数据流安全，行级），各带 `helpUri` 与 `level=warning`。至此 SARIF 已覆盖全部静态检查类别（uninit / type-mismatch / dead-code / shape-mismatch / taint-sink / debt），CI 安全面板可按规则独立排序/阻断/抑制。
- **② 全局状态耦合关系图（P209-3）**：`global_state.html` 在冲突表之上新增「跨文件耦合关系图」独立区块——自包含 SVG，左列=冲突变量（C3 风险点，红），右列=涉及文件（蓝），连线=文件声明了该变量（隐式共享状态）。直观呈现跨文件全局状态的耦合面与风险集中度，弥补纯表格信息密度瓶颈。
- **③ 多 SARIF 质量概览（P209-5）**：`ci-examples/merge_sarif.py` 增强 `--summary <md>` 选项——合并后按 `ruleId` 聚合 error/warning/note 计数，按严重度（error>warning>note）排序输出「质量概览」Markdown；同时把聚合统计写入合并 SARIF 的 `run.properties.summary`，供 CI 面板/后续脚本消费，使「质量是否在变好」在 PR 之外持续可见。
- **回归入测试**：P209 覆盖点并入 `test_p204_enhancements`（SARIF 规则含 MA-SHAPE-MISMATCH/MA-TAINT-SINK / global_state 含 gs-couple-svg 耦合图区块与渲染函数 / merge_sarif.build_summary 按严重度排序且 render_summary_md 生成概览表）。回归 154 项全部通过，兼容 Python 3.6.5。

### 3.47.4 P210 增强：修复建议闭环到 PR（v1.16.25）

按计划「下一步建议」实现最高优先级项 **P210-1（修复建议闭环到 PR）**——把前序批次（P200-P209）已具备的「发现问题能力」（SARIF / 5 类静态检查 / 变量级修复建议）补齐为「发现问题→修复」的完整闭环：

- **① `--gen-pr [PREFIX]` 一键生成 PR 草稿（P210-1）**：基于本次静态分析结果（未初始化 / 类型不一致 / 死代码 / 形状不匹配 / 污点危险汇聚 5 类），离线聚合输出两份草稿：
  - **PR 描述草稿（`.md`）**：含「概览表」（类别 / 规则 ID / 严重度 / 数量）+「按类别分组的修复清单」（每行级定位 `文件:行` + 函数 + 问题描述 + **可执行修复建议**）+「验证方式」（`--gate` / `--gen-pr` 复验命令）。可直接贴进 PR 描述。
  - **补丁草稿骨架（`.patch`）**：按文件分组，每段为 `diff --git a/<file> b/<file>` 头 + 行级 `@@ 文件 行 N [类别/严重度] @@` 区块 + `# 问题:` / `# 修复:` 注释，便于开发者直接定位并编辑（不篡改源码，符合「闭环到修复」而不越俎代庖的纪律）。
- **② 与 CI 门禁天然衔接**：`--gen-pr` 复用 `--gate` / `--sarif` 已就绪的 `checks_for_sarif` 数据（同一份 5 类结果），故 CI 失败 → 跑 `--gen-pr` → 直接贴进 PR 描述，形成「门禁发现 → 草稿修复」的最小闭环，无需额外配置。
- **③ 输出路径灵活**：支持 `-o <path>` 指定 PR 描述路径（补丁自动取同前缀 `.patch`）；不带参数时默认前缀 `pr_draft`（自动补 `.md` / `.patch`）。
- **④ 空仓库不误报**：无 5 类问题时，两份草稿均明确提示「无需修复 / 无需补丁」，保证闭环在健康仓库上零噪声。
- **⑤ 修复建议启发式**：复用 P208-1 的 `reason→建议` 逻辑并扩展（未初始化按 persistent/global/普通区分；类型/形状/污点按具体字段生成可读修复文案），使 PR 草稿不只是「问题清单」而是「可执行的下一步」。

**回归入测试**：新增 `test_p210_gen_pr`（覆盖 5 类标题、概览表、行级建议、补丁按文件分组、自定义 `-o` 输出）与 `test_p210_gen_pr_empty`（空仓库不误报）。回归 156 项全部通过，兼容 Python 3.6.5。

### 3.47.5 P210 增强：重复代码检测 MA-DUP-CODE（v1.16.26）

按计划「下一步建议」实现第 6 类静态检查——**内容级重复代码检测**（P210-3），补全静态分析的最后一类空白，并与 P210-1 的 PR 链路天然复用：

- **① `_detect_dup_code`（内容级，区别于 P52 同名歧义）**：对每个非脚本函数体抽取「结构指纹」——逐行去除注释/字符串、字面量归一化为 `<LIT>`、普通变量归一化为 `<V>`、保留调用名与操作符（内置函数小写归一），得到可比较的 token 序列；跨函数两两计算 **Jaccard 相似度**，相似度 ≥ `0.80` 且函数体 ≥ `4` 行（`_DUP_MIN_LINES` / `_DUP_SIM_THRESHOLD` 常量可调）判定为重复代码。结果按相似度降序、去重（避免 A-B 与 B-A 双报）。
- **② 全链路接入**：
  - `_collect_checks` 新增 `dup_code` 类别（`enabled` 支持 `"dup_code"`，与既有 5 类并列）；
  - `_sarif_rules` 新增独立规则 `MA-DUP-CODE`（level=warning，含 helpUri）；
  - SARIF 生成逐文件聚合 `dup_code` 行级 result（带 region.startLine 与相似度/重复对描述）；
  - P210-1 的 `_PR_CATS` 新增 `dup_code` 类别 → `--gen-pr` 自动生成「重复代码」章节（含 MA-DUP-CODE 规则 ID、相似度、与重复对函数名、以及「抽取公共函数/子程序」可执行修复建议）与补丁草稿（按文件分组的 `# 问题:`/`# 修复:` 注释）。
- **③ 降噪设计**：脚本函数排除、短函数体（<4 行）排除、行数差过大直接跳过、同一函数名多定义（P52 歧义）也计入但优先报告跨文件/跨函数名对，避免 getter 式短函数与结构无关噪声误报。

**回归入测试**：新增 `test_p210_dup_code`（用 computeA/computeB 两个结构相同、仅变量名不同的函数体，覆盖：PR 描述含「重复代码」章节与 MA-DUP-CODE 规则、相似度≈1.00、补丁按文件分组含修复注释、`_collect_checks` 直查 `dup_code` 键与 `dup_with` 关系及相似度阈值）。回归 **158 项全部通过**，兼容 Python 3.6.5。

### 3.47.6 P211 增强：真实可应用补丁（v1.16.27）

按计划「下一步建议」的最高价值演进——把 P210-1 的「修复建议草案骨架」升级为**真实可合并的补丁**，将闭环从「贴上 PR 描述」推到「直接 `git apply` 修复」：

- **① `--gen-apply-patch [PREFIX]`（P211 核心）**：基于各 `MFile` 的**真实源码行**（`source_lines`）用 `difflib.unified_diff` 生成标准 unified diff（可直接 `git apply`），写入 `<prefix>.git.patch`。仅对**确定性可修复**项生效，避免误改语义：
  - **未初始化（confidence==high）**：在变量读取行之前插入 `    <var> = [];` 初始化声明（取读取行缩进，消除该处未初始化读）；`medium`（条件赋值）留人工，不自动改。
  - **死代码**：删除不可达行（`return` 之后的语句），从后往前改避免行号漂移。
  - 其他类别（类型不一致/形状不匹配/污点/重复代码）语义依赖人工判断，**不自动改**，仍走 P210-1 草稿骨架。
- **② 编辑安全**：每文件独立构造「插入/删除指令」列表，按行号逆序应用（`del` 标记 `None` 后过滤），确保多编辑点互不干扰；unified diff 的 `fromfile`/`tofile` 用仓库相对路径（`a/<rel>`/`b/<rel>`），与 `git apply` 默认前缀兼容。
- **③ `--gen-pr` 增强（P211 联动）**：PR 描述概览后新增「🔧 **可自动修复 N 项**」统计（未初始化 high + 死代码计数）；未初始化(high) 与死代码项的清单行追加「🔧自动补丁」标记，引导开发者优先用 `--gen-apply-patch` 落地。
- **④ 闭环完整性**：现在形成「`--gate`/`--sarif` 门禁发现 → `--gen-pr` 出 PR 描述草稿 → `--gen-apply-patch` 出真实可合并 diff」的三段式最小闭环，确定性 bug 可零人工干预直接修复入 PR。

**回归入测试**：新增 `test_p211_apply_patch`（覆盖：未初始化 high 插入 `<var>=[];` 声明、死代码删除不可达行、unified diff 头格式 `--- a/` `+++ b/`、生成的 patch 通过临时 git 仓库 `git apply --check` 校验为合法可应用、PR 描述标注「可自动修复 / 🔧自动补丁」）。回归 **159 项全部通过**，兼容 Python 3.6.5。

### 3.47.7 P210 增强：大仓库性能基准（P210-2，v1.16.28）

按计划「下一步建议」把 **P203 的 `--max-nodes` 截断设计固化为可复现的回归断言**，防止该性能保护能力在后续迭代中悄然回退——此前 `--max-nodes` 只在手动调参时验证，没有自动化门槛：

- **① `--benchmark [N]`（P210-2 核心）**：自动合成含 **N 个 `.m` 文件**（默认 300）的大仓库，模拟 300+ 文件真实项目。每个文件含 1 个主函数 + 2~4 个 local 函数 + 6~11 个变量（变量节点占大头），使无截断时 `__CG__` 节点数远超阈值，从而可验证 `--max-nodes` 截断确实生效。固定随机种子（`20260825`）保证基准**可复现**。随后运行完整分析 + unified.html 生成并测量构建时延。
- **② 断言门槛（闭环保护）**：
  - 指定 `--max-nodes M` 时，`__CG__` 最终 `meta` 节点数**严格 ≤ M**（直接读 `src/_cgdata.js` 的 `window.__CG__` 统计），验证 P203 截断生效；
  - 构建时延 ≤ `--benchmark-timeout`（默认 60s，CI 安全上限），超出则 `benchmark_pass=False` 且进程退出码 1（可直接当 CI 门禁）。
- **③ 结果可消费**：基准结果（含 `version` / `synthesized_files` / `max_nodes` / `cg_node_count` / `truncated` / `elapsed_sec` / `timeout_sec` / `max_nodes_enforced` / `time_within_limit` / `benchmark_pass`）写入 `--benchmark-out <FILE>`（JSON）或打印到 stdout，便于接入 CI 趋势看板。
- **④ 复用现有管线**：`_run_benchmark` 不重复造轮子，合成仓库后直接调用 `main([...])` 复用全部分析与渲染逻辑，基准反映真实端到端性能（而非孤立微基准）。

**回归入测试**：新增 `test_p210_benchmark`（带 `--max-nodes 400`，断言节点数 ≤400 / `max_nodes_enforced=True` / `benchmark_pass=True` / 时延 ≤180s）+ `test_p210_benchmark_unbounded`（不指定上限，断言仍成功构建且观测到非零节点数）。回归 **160 项全部通过**，兼容 Python 3.6.5。

### 3.47.8 P213 增强：扩展确定性自动修复（v1.16.29）

按计划「下一步建议」把 **P211 的自动补丁能力从「未初始化/死代码」扩展到形状不匹配**，放大三段式闭环收益：

- **① 新增安全可验证的 reshape 修复**：对 `shape_mismatch` 中 **`±` 运算且 `numel(lhs)==numel(rhs)`**（元素总数相等，reshape 为数据无损对齐）的情形，在运算行**前**自动插入 `<lhs> = reshape(<lhs>, size(<rhs>));`，生成真实可 `git apply` 的 unified diff。原运算行保留，仅前置 reshape 使其维度合法——这是确定性、不丢数据的修复。
- **② 严格安全边界（防误修）**：`*` 乘法维度违规、或 `±` 但 `numel` 不等（reshape 会丢数据）的情形**不自动改**，仅在 PR 描述中标注「建议显式转置/reshape（已留人工处理）」，绝不生成可能改变语义的补丁。
- **③ 修复聚合缺口**：修正 `_collect_checks` 此前**未聚合 `shape_mismatch`** 的缺陷（导致 `--gen-pr` 自动修复统计与 `--gen-apply-patch` 均读不到该类别），使闭环链路完整。
- **④ PR 标注联动**：`--gen-pr` 的「可自动修复」统计与清单项「🔧自动补丁」标记覆盖 shape_mismatch 安全项；修复建议文本区分「自动 reshape 已修复」与「需人工」。

**回归入测试**：新增 `test_p213_apply_patch`（覆盖：reshape 插入/原运算行保留/补丁通过 `git apply --check` 校验/`*` 乘法不自动修复的安全边界/PR 描述标注「可自动修复 + reshape + 🔧自动补丁」）。回归 **161 项全部通过**，兼容 Python 3.6.5。

### 3.47.9 P212 增强：增量 git diff 分析（v1.16.30）

按计划「下一步建议」把 **分析模式从「全量目录扫描」升级为「仅扫 git 变更 .m 文件」**，使工具在大仓库日常 PR 流程中开销可控，与 `--benchmark`（全量守护）形成「日常小改快 / 大仓库守护」双模式：

- **① `--git-diff [BASE]`（默认 BASE=HEAD）**：仅分析 `git diff --name-only [BASE]` 列出的变更 `.m` 文件（工作树相对 BASE 的改动），跳过全目录递归 `collect_files`，大仓库 PR 下开销从 O(全量) 降为 O(变更集)。
- **② `--git-diff-staged`**：改用 `git diff --cached --name-only`（暂存区 vs HEAD），适配 pre-commit 钩子与 CI 待合入集场景。
- **③ 优雅降级（不崩）**：非 git 仓库 / git 不可用时 `_get_git_diff_files` 返回 `None`，流程**回退全量分析**并提示；变更集合无 `.m` 时 `_run_incremental_empty` 生成「无改动」空报告（含 `changed_m_files:0`）并正常退出码 0——CI PR 门禁可据此判定「无需 MATLAB 检查」而非失败。
- **④ 复用现有管线**：增量筛选仅在「文件收集」环节介入，后续分析/渲染/门禁/PR/补丁全部复用，无需为增量重写模块。

**回归入测试**：新增 `test_p212_git_diff`（覆盖：基线提交后修改单文件 → `--git-diff HEAD` 仅分析变更文件、未改动文件不出现在产物、空变更集退出码 0、git 缺失时回退全量不崩）。回归 **162 项全部通过**，兼容 Python 3.6.5。

### 3.47.10 P147 延伸：CI 模板增强（v1.16.31）

按计划「下一步建议」把 **已建成的四大能力一步编排成生产流水线**，使闭环从「单条命令」走向「团队日常化」。升级 `--gen-ci` 生成的两个模板：

- **① GitHub Actions 双 job**：
  - `pr-quick`（仅 `pull_request` 触发）：`--git-diff HEAD` 仅扫变更 `.m` → `--json` 快照 + `--sarif` + `--gen-pr` 生成 PR 草稿 + `--gen-apply-patch` 生成真实补丁，三者作为 `pr-autofix` artifact 上传，开发者一键 `git apply`；SARIF 同步上传 GitHub Code Scanning。
  - `full-guard`（push main / 每日 `cron 17 3 * * *`）：全量分析 + `--benchmark 300 --max-nodes 2000 --benchmark-timeout 120` 性能守护（`--max-nodes` 截断断言防能力回退）+ SARIF 基线 `--sarif-diff --fail-on-diff`。
- **② GitLab CI 双 stage**：`matlab_quick`（仅 `merge_request_event`：`--git-diff HEAD` + `--gen-pr` + `--gen-apply-patch`）+ `matlab_guard`（default 分支 / `schedule`：全量 + `--benchmark` 守护），产物归档 `mr-*.md/.git.patch` 与 `benchmark.json`。
- **③ `--gen-ci list` 引擎清单同步扩展**：列出 P212 增量 / P210-1 PR / P211·P213 补丁 / P210-2 守护四大引擎，便于团队核对串接。
- 所有模板仍锁定 `python-version: '3.6.5'`（GitHub）/ `image: python:3.6.5`（GitLab），保持兼容性基线。

**回归入测试**：扩展 `test_p147b_genci_and_diffhtml_and_confidence`，断言 `--gen-ci both` 输出含 `--git-diff` / `--gen-pr` / `--gen-apply-patch` / `--benchmark` / `--max-nodes` 及双 job（`pr-quick`/`matlab_quick` + `full-guard`/`matlab_guard`），且 `--gen-ci list` 列出四大引擎（P147 延伸为增强既有测试，测试总数维持 **162 项**，全量仍全部通过）。兼容 Python 3.6.5。

### 3.47.11 P210-4 增强：交互式耦合图（v1.16.32）

按计划「下一步建议」把 **`global_state.html` 的跨文件耦合关系图（P209-3）升级为可交互**，提升 C3 风险面的可读性：

- **① 缩放 / 平移**：滚轮缩放（`__gs_wheel`，缩放比 0.3~4× 实时显示于 `gs-zoomval`）+ 拖拽平移（`__gs_down/move/up`，`<g transform="translate scale">` 承载），外层 `<svg>` 固定 viewBox、内层 `<g>` 承载 transform，渲染稳定不溢出。
- **② 按严重度筛选**：变量节点按声明数 `n` 分三档（`sev-high` n≥4 / `sev-mid` n≥3 / `sev-low` n=2），前端 `gs-node-v.sev-*` 配色分级；下拉 `gs-sev` 过滤高危/中危/低危。
- **③ 按目录筛选**：从文件名提取顶层目录注入 `graph.dirs`，下拉 `gs-dir` 动态填充，按目录隔离耦合面（如只看某子系统）。
- **④ 过滤后重布局**：`__gs_visible` 计算可见节点集合（两端节点均可见才保留边，避免悬空连线），`__gs_paint` 仅在可见集内重新布局，避免稀疏留白；附「重置视图」按钮与严重度图例。
- **⑤ 数据层增强**：`graph` 新增 `dirs` 列表与 `vars[].sev` 严重度字段，驱动前端着色/筛选。
- **⑥ 顺带修复**：原 `global_state.html` 用 `%` 格式化拼接含大量 `%` 的 `BROWSE_CSS` 会触发 `ValueError`；改为 `replace` 注入数据（`__N_CONFLICT__` / `__N_G__` / `__N_P__` / `__DATA_JSON__`），消除该隐患。

**回归入测试**：新增 `test_p210_coupling_interactive`（覆盖：交互控件 `gs-zoomval`/`gs-sev`/`gs-dir`/重置逻辑、严重度配色类 `sev-high/mid/low`、交互函数 `__gs_paint`/`__gs_wheel`/`__gs_apply`、数据字段 `dirs` 与 `vars.sev`）。回归 **163 项全部通过**，兼容 Python 3.6.5。

### 3.47.12 P213-2 完成：dup_code 提取公共函数自动重构脚手架（v1.16.33）

在 P213 确定性自动修复（uninit / dead_code / shape_mismatch）基础上，补齐「**重复代码 dup_code**」这一最后的高价值自动修复类别，形成 P200–P213 主线自动修复闭环全覆盖：

- **① 设计定位**：提取公共函数属**重构类**修复（需人工决定共享函数放置位置与参数映射），故**不做** git apply 直接可合入的 hunk，而是生成独立的 `### MA-DUP-CODE 重构建议` section 作为确定性重构起点。
- **② 脚手架内容（每对重复）**：
  - 建议共享函数签名骨架 `function [out] = shared_<func>(varargin)`（去歧义前缀 `shared_`）；
  - 两端调用替换模板 `out = shared_<func>(...)`；
  - 两端重复位置定位（`a.m/fooA` ↔ `b.m/fooB` 的 file/func/line）。
- **③ PR 联动**：`--gen-pr` 中为 dup_code 项标注「🔧自动脚手架」（区别于 uninit/dead/shape 的「🔧自动补丁」），PR 顶部 auto 统计文案同步说明「提取公共函数重构脚手架（需人工植入共享函数定义）」。
- **④ 缺陷修复**：`_build_apply_patch` 原 `if not _edits: return ("", 0)` 会在「仅有 dup 而无 uninit/dead/shape」时提前 return 空字符串、丢脚手架；改为该分支先构造 dup section、非空则随其返回（计 1 个重构建议单元）。
- **⑤ 编码安全**：`_build_dup_refactor_section` 内 MATLAB 注释含字面 `%`（如 `% TODO`），统一改用 `.format`/拼接而非 `%` 运算符，规避 `unsupported format character` 隐患（与 P210-4 修复 BROWSE_CSS 同一类根因）。

**回归入测试**：新增 `test_p213b_dup_code_refactor_scaffold`（覆盖：① `--gen-apply-patch` 生成 `MA-DUP-CODE 重构建议` section；② 脚手架含 `function [out] = shared_fooA(varargin)` 签名；③ 两端调用替换模板 `out = shared_fooA(...)`；④ 两端位置 `a.m/fooA`/`b.m/fooB` 定位；⑤ `--gen-pr` 标注「自动脚手架」+「MA-DUP-CODE」）。回归 **164 项全部通过**，兼容 Python 3.6.5。

### 3.47.13 P215 完成：dup_code 重复代码门禁（v1.16.34）

把 P213-2 的「重复代码重构脚手架」接入 CI 质量闸，形成独立于 `--fail-on-diff` 结构差异闸的第二道质量闸：

- **① 新增参数 `--fail-on-dup N`（N≥1）**：在 `main` 末尾返回前统计 `checks_for_sarif["dup_code"]` 对数；`> N` 时打印 `[P215 DUP-FAIL]` + 重构提示并令 `ok=False`（退出码 1），`≤ N` 时打印 `[P215 DUP-PASS]`。默认 `N=0` 不启用、**不影响既有退出码**（与 `--fail-on-diff` 互不干扰）。
- **② CI 模板注入**：`--gen-ci` 的 GitHub `full-guard` 与 GitLab `matlab_guard` 默认追加 `--fail-on-dup 1`（重复对 >1 即失败，逼团队在合并前做提取公共函数重构）；`--gen-ci list` 引擎清单新增「P215 质量闸」一行说明。
- **③ 设计定位**：与 `--fail-on-diff`（结构快照差异）正交——前者管「是不是变了」，后者管「复制粘贴坏味道是不是过多」，双层门禁覆盖「变更安全 + 代码卫生」双维度。
- **④ 二进制安全**：门禁判定纯整数比较，无浮点/字符串格式化风险，兼容 Python 3.6.5。

**回归入测试**：新增 `test_p215_dup_code_gate`（覆盖：① 3 个相似函数 → `--fail-on-dup 1` 返回 1 + `DUP-FAIL`；② 单函数无重复 + `--fail-on-dup 1` → 返回 0 + `DUP-PASS`；③ 默认不带该参数 → 不影响退出码；④ `--gen-ci both` 模板 GitHub+GitLab 各注入一次 `--fail-on-dup 1`）。回归 **165 项全部通过**，兼容 Python 3.6.5。

### 3.47.14 P217 完成：global_state.html 重复代码看板（v1.16.35）

把 P213-2 的「重复代码重构脚手架」从 CLI 文本升级为 `global_state.html` 内的可视化看板，与 P210-4 交互式耦合图形成"结构风险 + 重复风险"双维度质量全景：

- **① 数据层注入**：`_run_global_state` 把 `checks_for_sarif["dup_code"]` 映射为 `dup_code` 数组（含 `file`/`func`/`line`/`similarity`[百分比]/`shared`[`shared_<func>`]/`dup_with`[B 端位置]），随 `global`/`persistent`/`graph` 一并进入 `data_json`。
- **② 第三个 tab**：`global_state.html` 新增「重复代码（N）」tab（`tab-d` + `tbl-d` 容器），与 `global`/`persistent` 并列；切换由 `__gs_show('d')` 驱动，选中时调用 `__render_dup()` 渲染。
- **③ 前端渲染 `__render_dup`**：表格每行展示 函数A位置 / 相似度徽标（`.dup-sim`）/ 重复于函数B位置 / 建议共享函数名 `shared_<func>(varargin)`；无重复时显示阈值提示（占位符 `__DUP_MIN_LINES__`/`__DUP_SIM__` 由 Python 端 replace 注入实际值）。CSS 新增 `.dup-row`/`.dup-sim` 配色，悬停高亮。
- **④ 闭环联动**：看板表格的 `shared_<func>` 命名与 P213-2 脚手架一致，用户从"看板发现重复 → 跳转 `--gen-apply-patch` 脚手架"形成完整治理链路。
- **⑤ 编码安全**：延续 P210-4 的 replace 注入策略，阈值/数量占位符不在 JS 内联 `%` 格式化，规避 `unsupported format character` 隐患。

**回归入测试**：新增 `test_p217_dup_code_dashboard`（覆盖：① html 含 `tab-d`/`tbl-d`；② 数据层注入 `"dup_code"`/`"similarity"`/`"shared"`；③ `__render_dup` 与 `__gs_show('d')` 存在；④ 占位符 `__N_D__`/`__DUP_MIN_LINES__`/`__DUP_SIM__` 均已替换；⑤ 含重复时 tab 文案显示对数且表格含 `shared_fooA`）。回归 **166 项全部通过**，兼容 Python 3.6.5。

### 3.47.15 P214 完成：dup_code 重复对升级为可执行补丁 `--dup-exec-patch`（v1.16.37）

在 P213-2 纯文本重构脚手架基础上，把「重复代码」从「需人工植入共享函数定义」升级为「可直接 `git apply` 的可执行补丁」，补上自动重构闭环的最后一环：

- **① 新增 `--dup-exec-patch` 开关（默认关，回落 P213-2 脚手架）**：开启后 `--gen-apply-patch` 对每对重复代码生成 git-apply 兼容的 unified diff，而非仅文本脚手架。`--gen-ci list` 引擎清单同步说明。
- **② 公共行提取 `_dup_extract_common_lines(lines_a, lines_b)`**：基于 P210-3 的 `_dup_line_fingerprint`（去变量/常量/字面量归一化）逐行比对两端真实函数体/片段，结构相同的行（含「同名不同变量」的赋值）进 `shared_<func>`；结构不同的行（差异行）标记保留。
- **③ 共享函数 `_dup_shared_func_src`**：生成 `function [out] = shared_<func>(varargin)` 骨架，内联公共行 + 差异位置 `varargin` 占位 TODO（保守安全，差异行不由自动逻辑臆造）。
- **④ 共享函数落地独立新文件 `shared_<func>.m`（关键修正）**：初版尝试追加到原文件末尾，但 difflib 会把「原文件删除的公共行」与「shared 内相同的公共行」误判为「行移动」，导致 git apply 后主体公共行未被真正删除（残留重复）。改为落到独立新文件后，原文件只做「删公共 + 插调用」，无重复行，difflib 正确生成删除 hunk，git apply 语义干净。
- **⑤ `_build_dup_executable_patch` 统一收敛**：按文件聚合编辑指令，a.m/b.m 各自删除公共段 + 插入 `out = shared_<func>(...);` 调用占位（差异行保留不动），shared 函数走独立创建 diff（`@@ -0,0 +1,N @@`）。
- **⑥ 编码安全**：MATLAB 注释含字面 `%`，所有脚手架/补丁文本构造沿用 `.format`/字符串拼接（无 `%` 操作符），兼容 Python 3.6.5。

**回归入测试**：新增 `test_p214_dup_exec_patch`（覆盖：① `--dup-exec-patch` 产出 `function [out] = shared_fooA(varargin)` 真实定义（在独立 `shared_fooA.m` 内）；② 两端插入 `out = shared_fooA(...);` 调用占位；③ 原文件生成 `-` 删除 hunk（公共行被删）；④ 合法 unified diff 结构（`--- a/`/`+++ b/`/`@@`）；⑤ 关闭开关回落 P213-2 脚手架且不出现 P214 标记）。回归 **168 项全部通过**，兼容 Python 3.6.5。至此 dup 修复形成完整闭环：发现→脚手架(P213-2)→可执行补丁(P214)→门禁(P215)→看板(P217)→片段级粒度(P216)。

---

### 3.47.16 P216 完成：dup_code 片段级检测下沉（v1.16.36）

把 P210-3 的重复检测从「整个函数体」粒度细化到「函数内连续行块」粒度，覆盖散落的复制粘贴坏味道：

- **① 新增 `_best_continuous_frag(tokens_a, tokens_b, min_lines, sim_threshold)`**：滑窗连续块比对——对 a 的每个起点、b 的每个窗口（窗口长 = 较短序列长，由长到短取首个达阈），用顺序一致性 Jaccard（连续块应逐行一致，而非集合相等）找最佳对齐。性能 O(len_a·len_b·w)，配合 `--max-nodes` 守护不会在大库失控。
- **② `_detect_dup_code` 扩展片段级分支**：函数级 Jaccard `< sim_threshold(0.80)` 但存在**连续 ≥`_DUP_MIN_LINES`(4) 行**且相似度 ≥`frag_threshold(0.92)` 的子序列时，上报 `kind="fragment"`，并带 `frags:[{file,func,start,end}×2]` 精确行区间（两端各一个）。函数级与片段级去重互不误报（fragment 用独立 key 含行偏移）。
- **③ `--json` 顶层新增 `dup_code` 字段**：此前 `dup_code` 仅存在于 SARIF/PR/apply-patch 路径（`checks_for_sarif`），`--json` 透出后程序化消费完整（含 `kind`/`frags`）。
- **④ 全链路联动**：a) P213-2 脚手架对 fragment 渲染「重复片段区间」而非函数首行；b) P217 看板对 fragment 显示「片段」标签（`.dup-frag`）+ `[start-end]` 精确区间；c) P215 门禁自然覆盖（fragment 计入重复对数量，阈值语义更贴合"坏味道数量"）。
- **⑤ 编码安全**：片段级 `frags` 区间计算纯整数运算，无格式化风险，兼容 Python 3.6.5。

**回归入测试**：新增 `test_p216_dup_fragment_detection`（覆盖：① 两函数整体不相似但含 4 行相同初始化块 → 上报 `kind=fragment` + `frags` 精确区间 `[2-5]↔[2-5]`；② 不误报为 `kind=function`；③ 经 `--json` 顶层 `dup_code` 透出校验；④ P213-2 脚手架含「重复片段区间」；⑤ P217 看板对 fragment 不崩溃）。回归 **167 项全部通过**，兼容 Python 3.6.5。

---

### 3.47.17 P218 + P220 完成：dup_code 门禁双档位 + 检测阈值 CLI 化（v1.16.38）

在 P215 门禁与 P216 片段级检测基础上，把 dup 能力从「检测/呈现」推进到「可治理、可调参」：

- **① P218：`--fail-on-dup` 升级为双档位**。原实现仅支持纯整数（超阈值硬失败、返回退出码 1）。现支持两种档位：
  - `warn:N` 档——重复对数 > N 时仅打印 `[P215/P218 DUP-WARN]` 告警、**不返回退出码 1**（不阻断 CI），供团队先做「看见坏味道」的渐进式治理，待历史债收敛后再收紧到 fail 档；
  - `fail:N` / 纯整数 `N` 档——维持原硬失败语义（返回退出码 1），`--gen-ci full-guard` 默认注入的 `fail:1` 不受影响。
  - 新增 `_parse_dup_gate(raw)` 统一解析 `warn:/fail:/纯数字` 三形态（容错非数字回落 `("fail", 0)`），门禁分支据 `mode` 决定 `ok` 是否置 False。
- **② P220：检测阈值 CLI 化并全链路贯穿**。把 P210-3 函数级阈值（`--dup-sim`，默认 0.80）与 P216 片段级参数（`--dup-frag-min-lines` 默认 4、`--dup-frag-sim` 默认 0.92）暴露为 CLI，便于按项目容忍度调参（调高更严格、调低更易报重复）。
  - 新增 `_detect_dup_code` 的 `frag_threshold` 默认值由硬编码 `0.92` 收敛到常量 `_DUP_FRAG_THRESHOLD`（与 `_DUP_SIM_THRESHOLD`/`_DUP_MIN_LINES` 统一口径）。
  - 新增 `dup_opts` 字典（含 `min_lines`/`sim`/`frag_sim`），透传路径：`main` 构造 → `_collect_checks(files, ..., dup_opts=)` / `render_json(..., dup_opts=)` → `_detect_dup_code(min_lines=, sim_threshold=, frag_threshold=)`。`_collect_checks`/`render_json` 各自新增可选 `dup_opts=None` 参数，缺省回落常量，零回归面。
  - 贯穿范围覆盖 `--json` / `--sarif` / `--gen-pr` / `--gen-apply-patch` / `--fail-on-dup` 全部路径，阈值行为在所有输出形式下一致。

**回归入测试**：新增 `test_p218_fail_gate_modes`（覆盖 `warn:0`/`warn:1`/`fail:1`/纯 `1` 解析为正确 mode+阈值、warn 档不置 `ok=False`）与 `test_p220_dup_threshold_cli`（覆盖 `--dup-sim`/`--dup-frag-min-lines`/`--dup-frag-sim` 经 `dup_opts` 贯穿到 `_detect_dup_code`）。回归 **169 项全部通过**，兼容 Python 3.6.5。

---

### 3.47.18 P221 完成：dup 可执行补丁的参数自动映射（AST 级）（v1.16.39）

在 P214 可执行补丁（共享函数落地独立文件 + 调用占位）基础上，进一步消除「人工补参」的最后一步阻力：把「调用占位 `(...)` + `varargin` 共享函数」升级为「按两端函数 AST 签名自动推导真实参数」，使重构补丁 open-box 即用、git apply 后无需二次编辑即可运行。

- **① 新增 AST 级辅助**：
  - `_dup_used_vars(lines)`：从公共行提取被引用标识符（排除关键字/内置），支撑「参数需哪些输入」推断；
  - `_dup_infer_shared_signature(common, in_a, in_b, out_a, out_b)`：仅当两端映射**一致且确定**时返回真实签名 `(in_params, out_param)`，否则返回 `(None, "out")` 触发保守回落；
  - `_dup_rewrite_out_var(line, out_param)`：映射确定时把公共段输出变量统一改写为 `out_param`（两端同名输出 y 时沿用 y；不同名时不强行改写）；
  - `_find_func_obj(mf, name)`：从 MFile 按名取 `FunctionInfo`，供取 `inputs`/`outputs`。
- **② 映射规则（保守安全）**：
  - **输入参数** = 公共行引用变量 ∩ （A.inputs ∩ B.inputs）；若公共行引用了既非两端输入交集、也非两端输出交集的变量 → 无法用固定签名表达 → 回落 `varargin`；
  - **输出参数** = 公共行最后一条赋值的左侧变量，**仅当**该变量同时位于 A.outputs ∩ B.outputs（两端同名输出）才沿用其名；否则（两端输出名不同 y vs z、或公共段输出不在输出交集）→ **整体回落** `(None, "out")`，共享函数体保留原样、调用占位回落 `(...)`，绝不生成 `out = y * 2;` 这类未定义变量的语义错误改写。
- **③ 贯穿 P214 链路**：`_build_dup_executable_patch` 现调用 `_dup_infer_shared_signature` 推断签名，传入 `_dup_shared_func_src`（真实参数时生成 `function [y] = shared_fooA(x)` 并改写输出变量，否则 `function [out] = shared_fooA(varargin)` 原样体）；调用占位从 `(...)` 升级为 `out = shared_fooA(x);`（映射确定时）或 `out = shared_fooA(...)`（回落时）。

**回归入测试**：新增 `test_p221_ast_param_mapping`（覆盖 ① 同输入同输出名场景生成 `function [y] = shared_fooA(x)` + `y = shared_fooA(x);` 开箱即用；② 两端输出名不同 y/z 场景保守回落 `function [out] = shared_fooA(varargin)` + 原样体 + `out = shared_fooA(...)`；③ `_dup_infer_shared_signature` 单元级同/异输出名返回；④ `_dup_rewrite_out_var` 单元级改写规则；⑤ `--gen-apply-patch --dup-exec-patch` 经 CLI 端到端产出真实参数补丁）。回归 **170 项全部通过**，兼容 Python 3.6.5。

---

### 3.47.19 卡死修复 + P219 完成：报告死循环治理与 dup↔冲突变量交叉高亮（v1.16.40）

#### 一、卡死修复（报告生成阶段无限循环/极端规模治理）

定位到两类导致「程序在报告生成阶段卡死（表现为长时间无响应、疑似卡在 HTML 报告步骤）」的根因：

- **① 污点传播死循环（`_propagate_taint` 的 `while changed:` 缺收敛上限）**：迭代传播「调用受污函数者受污」时，原代码仅用 `changed` 布尔标志控制循环，未设迭代次数上限。在复杂调用图（循环依赖 + 特定边界：某函数的污染等级 `level` 恰好触发 `cand_level > max_depth` 的 `continue` 分支导致 `best` 反复被同一上游污染）下，可能不收敛而**无限循环**。现已添加硬上限 `max_iters = len(fn_meta) + 2`，即使理论不收敛也必然在有限次迭代后终止（污点集单调增，至多 `len(fn_meta)` 次即饱和，+2 为安全余量）。
- **② 全局调用图无节点上限（`_build_global_cg` 默认 `max_nodes=None`）**：`render_html` 与 `render_browse_site` 将完整全局调用图（含每个函数的调用边 + 变量节点）内联进 HTML/JSON。超大型项目（数百文件、数千函数）可能生成 GB 级 JSON，导致 `json.dumps` 序列化与 `_write_output` 写盘极慢甚至卡死。现已将 `_build_global_cg` 的 `max_nodes` 参数贯穿 `render_html` / `render_browse_site` / `render_source_page` 三处调用（默认 None 即保持原行为不限制），并复用已有的 `--max-nodes` CLI 开关（如 `--max-nodes 8000`）供用户在超大项目上显式设上限防御。

#### 二、P219：dup_code ↔ 冲突变量交叉高亮

在 P217 全局状态看板基础上，把「重复代码」与「跨文件冲突变量」两个独立看板打通：

- **数据层**：P217 的 `dup_code` 数据行新增 `vars` 字段——由 `_dup_used_vars` 从 dup 对 `body_a` 区间（函数 A 的主体源码行）提取涉及变量名；冲突变量（global/persistent）行渲染加 `data-var="变量名"` 属性（联动目标）。
- **前端联动（纯 JS，零 Python 计算开销）**：dup 看板中涉及变量渲染为可悬停的 `<span class="dup-var" data-var="x">`；悬停时 `__gs_link_dup_var(x)` 自动切到冲突 tab 并高亮同名变量（`gs-linked` 红底标红）；反向 `__gs_link_conflict_var(x)` 从冲突变量悬停高亮 dup 看板中涉及该变量的行。CSS 新增 `.dup-var` / `.gs-linked` / `tr.gs-linked-row` 样式。
- **价值**：直观暴露「同一变量既被多函数跨文件共享（隐式状态冲突 C3 风险）又出现在 copy-paste 重复代码段」的双重坏味道——这类代码既难维护又易引入状态一致性 bug，是重构最高优先级候选。

**回归入测试**：新增 `test_p219_cross_highlight`（覆盖 ① `--global-state` 产物含 `dup_code` 数据层与 `vars` 字段；② 冲突变量行含 `data-var` 属性；③ 联动 JS 函数 `__gs_link_dup_var`/`__gs_link_conflict_var` 注入；④ `_dup_used_vars` 单元级正确提取变量（注释内变量不误提））。回归 **171 项全部通过**，兼容 Python 3.6.5。

### 3.47.20 P224 语义级重复检测 + P225 重构 ROI 评分 + P226 演化追踪基线（v1.16.41）

#### 一、P224：语义级重复检测（Semantic Dup）
**问题**：原 dup_code 基于 token 指纹 + Jaccard，对「变量改名 / 语句顺序交换 / 等价常量写法」无效——这是整个重复检测领域的根本性盲区。

**方案**：在 `_dup_line_fingerprint` 之上叠加语义归一化层 `_dup_line_fingerprint_semantic`：
- **可交换运算符排序**：`2+a` 与 `a+2` 在语义层产生相同指纹（加法/乘法二元操作数按 token 序排序，使字面量/变量位置交换不再影响匹配）；
- **MATLAB 常量符号化**：`2*pi`/`pi*2` → `<PI2>` 一致归一（标识符 pi 被识别为数学常量而非普通变量）；`pi`/`eps`/`inf`/`nan`/`i`/`j` → `<PI>`/`<EPS>` 等；
- **保守回落**：`--dup-semantic`（默认开）/ `--no-dup-semantic`（关闭回落纯结构指纹）双开关，向后兼容。

**新增函数**：`_dup_line_fingerprint_impl`（统一入口，含语义开关）、`_dup_semantic_const_norm`（常量符号化，回溯替换 `数字*pi` 为 `<PI2>`）、`_dup_sort_commutative`（可交换操作数排序）。

#### 二、P225：重构 ROI 评分 + TopN 建议清单
**问题**：原报告只报「这里有重复」，不告诉用户重构值不值得。

**方案**：为每条 dup 记录计算 `roi = 可消除行数 × (出现次数−1) ÷ 提取复杂度`：
- `saved_lines` = 重复块有效行数 × (重复处数 − 1)，即提取共享函数后其余 N−1 处可删的行；
- `complexity` = 公共块内 if/for/while/switch/try/parfor 分支数 + 1（基础提取成本）；
- `_compute_dup_roi(rec)` 计算单条，`_rank_dup_by_roi(dups, top_n=10)` 按 ROI 降序排序；
- 看板（`--global-state`）dup tab 新增「重构优先级 Top 10」区块（`#t-d-roi`），ROI≥8 红底、≥4 橙底、其余绿底，直观呈现最该重构的重复。

#### 三、P226：dup_code 演化追踪基线（跨运行 diff）
**问题**：每次运行是独立快照，无法感知「这次新出现了什么重复 / 之前报的重复被重构了吗 / 两端开始分叉了吗」。

**方案**：
- `_dup_save_baseline(dups, path)`：将 dup 结果摘要（稳定键 + 相似度 + 行区间）写入 `<项目根>/.dup_baseline.json`（覆盖式）；
- `_dup_pair_key(rec)`：以 `file:func:line` 规范化键跨运行对齐同一对（忽略易变字段）；
- `_dup_diff_baseline(dups, path)`：返回三类变化——`new`（新出现）、`gone`（消失/已重构）、`drift`（相似度下降>0.05，分叉度增大）；
- CLI：`--dup-baseline PATH`（指定基线路径）、`--dup-update-baseline`（运行后更新基线，建议 CI 每次成功后执行）、`--dup-diff`（打印演化摘要不写新基线）。

**验证**：
- P224 单元级：`a+b`≡`b+a`、`x*2`≡`2*x` 语义指纹一致；`2*pi` 在语义层正确归一为 `<PI>`（结构层 `pi` 被误判为变量名）；
- P225：`bigA`/`bigB`（7行块，2处）ROI=7.00、可消除7行；`smallC`/`smallD`（3行<min_lines=4）正确不检出；
- P226：基线建立→不变无变化→删beta报gone→改alpha公共行（15行函数改1行，相似度1.0→0.82）正确报drift。

**版本与文档**：VERSION/setup.py → 1.16.41；本报告新增 §3.47.20；测试矩阵 171 → 174 项（新增 `test_p224_semantic_fingerprint` / `test_p225_roi_ranking` / `test_p226_baseline_diff`）。

---

### 3.47.21 P227 语义dup误报抑制 + P228 跨语言IR重复检测 + P229 演化趋势SVG（v1.16.42）

在 P224/P225/P226 的 dup_code 体系上补齐「质量过滤 → 跨语言 → 可视化」三段，形成完整闭环。

#### 一、P227：语义 dup 误报抑制（标准库惯用法降权）
**痛点**：P224 语义层仍会把 MATLAB 标准「惯用法样板」（`zeros`/`ones` 初始化、`for k=1:N` 循环、`if isempty` 守卫、`try/catch`、`persistent` 初始化、`x(end)` 取值等）两两高相似误报为业务重复，造成大量噪声。
**方案**：新增 `_dup_idiom_score(rec)` 估算每条 dup 的惯用法占比（含惯用法 keyword 的行占比 + 弱骨架命中数），`_apply_dup_idiom_suppression(dups, ratio_threshold=0.5)` 对惯用法占比 ≥0.5 且弱骨架 ≥1 的记录打 `idiomatic=True` 标记，并把 ROI 折减为 25%（折减后仍保留但沉底）。看板 dup tab 与「重构优先级 Top10」对 idiomatic 记录灰显（⚠样板标签），把语言特性噪声从业务重复中分离。
**验证**：`test_p227_idiom_suppression` —— 惯用法样板（zeros+for+isempty）被标 idiomatic 且 ROI 折减 4.0→1.0；纯业务重复（a+b 算术）不被误判。

#### 二、P228：跨语言重复检测（MATLAB ↔ Python，IR 层）
**痛点**：同一逻辑常被用 Python 重写一遍（如工具函数、算法移植），源码层面无法直接 Jaccard，但 IR（控制流骨架 + 调用语义 + 字面量角色）高度同构。
**方案**：新增 `_dup_ir_tokenize(line, lang)` 把两语言源码归一为语言无关 IR token（变量→`<V>`、字面量→`<LIT>`、控制流→FOR/IF/...骨架、调用名→PRINT/ALLOC0/LEN/EMPTY 等语义键），`_detect_cross_lang_dup(mf_list, py_list, threshold=0.3)` 以「骨架 Jaccard（0.6）+ 全 token Jaccard（0.25）+ 连续片段相似度（0.15）」综合判定，返回 `kind="cross-lang"` 记录（含 `file2`/`func2`）。CLI `--py-dir DIR` 指定 Python 目录，运行后与 MATLAB 函数做跨语言比对，结果合并进统一 `dup_code` 出口（看板 dup tab 标「跨语言 ↔」）。
**关键修复**：IR 归一化中语义键（ALLOC0 等）原被误判为变量 `<V>`，已在 `_dup_ir_tokenize` 增加 `_sem_keys` 保留分支修复；相似度改用骨架集合为主，使 `for i=1:n; y(i)=0` ↔ `for i in range(n): y[i]=0` 正确识别。

#### 三、P229：演化趋势 SVG 图
**痛点**：P226 的 `--dup-update-baseline` 每次覆盖单点基线，无法看趋势。
**方案**：`_dup_save_baseline` 升级为追加式（保留 `history` 序列，每步记录 `new/gone/drift/total` 计数），`_dup_render_trend_svg(path, out_svg)` 用纯 stdlib（兼容 Python 3.6.5）绘制四线趋势 SVG（new 红 / gone 绿 / drift 橙 / total 蓝），含坐标轴、图例、历史快照序号。CLI `--dup-trend-svg OUT.svg` 触发，历史不足 2 次时报「样本不足」提示。
**验证**：`test_p229_trend_svg` —— 空基线报「不存在」、1 次报「不足」、2 次生成合法 `<svg>` 含 `polyline`、历史累积 2 条且第二次 `gone=2`。

**闭环状态**：dup_code 体系现覆盖「结构→语义→ROI→演化基线→误报抑制→跨语言→趋势可视化」全链路。
**版本与文档**：VERSION/setup.py → 1.16.42；本报告新增 §3.47.21；README/JSON_SCHEMA/STRUCTURE 版本同步；测试矩阵 174 → 177 项（新增 `test_p227_idiom_suppression` / `test_p228_cross_lang` / `test_p229_trend_svg`）。

---

### 3.47.22 P217b dup 看板交互化 + 趋势内嵌 + 历史 JS 转义 bug 修复（v1.16.43）

对 `--global-state` 生成的 dup 看板做深度前端现代化改造（零依赖原生 JS，严格兼容 Python 3.6.5 生成约束，不引入任何框架/库以守住离线零依赖契约）。

#### 一、dup 主表交互化
- **排序**：表头点击切换相似度/ROI/文件名升/降序，下拉 `dup-sort` 亦可；`__dup_sortkey` 支持数值与字典序两类 key。
- **搜索**：`dup-q` 实时过滤（文件/函数名 + 跨语言对端 `file2/func2`），`__dup_match` 统一匹配。`dup-filter` 即时重渲染。
- **筛选 chip**：`全部 / 跨语言 / 惯用法样板 / 片段级`（`data-f` 驱动 `__dup_fchip`），惯用法样板（P227）一键隔离、跨语言对（P228）一键聚焦。
- **分页**：`per=12` 分页器（`__dup_go`），大重复集不卡 UI。
- 视觉升级：卡片化容器、sticky 工具栏、表头排序箭头指示、移动端响应式（窄屏隐藏次要列）、键盘/无障碍（aria-label）。

#### 二、趋势图内嵌看板（P229 闭环到看板）
- `--dup-baseline` 指向的基线含 ≥2 条历史时，看板自动新增「演化趋势」tab（`tab-t`），经 `_dup_load_trend` 把 `history` 注入 `__GS__.dup_trend`。
- `__render_trend` 用原生 SVG 绘制 new/gone/drift/total 四线，支持**数据点 hover tooltip**（展示该快照时间与四项计数）与**图例点击显隐**单条线（`__trend_toggle`）。原独立 `--dup-trend-svg` 命令行通道仍保留（P229）。

#### 三、修复历史 JS 转义 bug（关键正确性）
原 P204 看板中多处内联事件 `onmouseover="fn(\'var\')"` 在 Python 三重引号模板里被写成字面 `\'`，**生成到 HTML 后浏览器解析为 `SyntaxError`，导致整个 `<script>` 中断**（全局状态图/变量悬停联动全部失效）。本次统一改为 `data-var`/`data-drill` 数据属性 + `this.getAttribute(...)` 传递，修复 `__gs_link_conflict_var` / `__gs_link_dup_var` / `__gs_drill` / `__trend_toggle` / `__dup_fchip` 共 5 处。
**验证手段升级**：引入 `node --check` + 极简 DOM stub 运行时校验（`_chk_dom.js`），对生成 HTML 的 `<script>` 做语法与运行时双重校验，确保交互函数无异常。

#### 四、验证
- `test_p217b_dup_dashboard_interactions` —— 搜索框/排序/筛选 chip/分页辅助函数就位；趋势数据层注入与宿主节点存在；**断言生成 JS 不含字面 `\'`**（防回归）；`__render_trend` 声明存在。
- `test_p217_dup_code_dashboard` / `test_p226_baseline_diff` / `test_p229_trend_svg` / `test_p228_cross_lang` / `test_p227_idiom_suppression` 全绿无回归。
- 端到端：生成 `global_state.html` 后 `node --check` 通过；DOM stub 执行 `__render_dup`/`__render_trend`/`__dup_filter`/`__dup_fchip`/`__dup_go` 无运行时错误。

**闭环状态**：dup_code 体系完成「结构→语义→ROI→演化基线→误报抑制→跨语言→趋势可视化→看板交互闭环」全链路，且前端 JS 正确性获自动化校验守护。
**版本与文档**：VERSION → 1.16.43；本报告新增 §3.47.22；JSON_SCHEMA 版本同步 + §26.1 补交互契约；测试矩阵 177 → 178 项（新增 `test_p217b_dup_dashboard_interactions`）。

---

### 3.47.23 P217c dup 看板深度增强：行内嵌 diff + 暗色主题/持久化 + 前端 JS 自动校验入 CI（v1.16.44）

在 P217b 交互化基础上，把 dup 看板从「可视化」推向「可诊断、可复用、可守护」。

#### 一、P217d 行内嵌并排 diff（最有直观价值）
- 每条 dup 记录在分析阶段即用 `_dup_side_by_side`（difflib.SequenceMatcher opcode 对齐）预生成两端函数体**行级并排 diff**，作为 `diff` 字段仅注入 `--global-state` 看板数据层（**不进入 `--json` 出口**，避免污染程序化消费）。
- 看板每行新增「＋」展开按钮，点击经 `__dup_toggle_diff` 内嵌渲染并排视图：左列 A（函数A）、右列 B（函数B），按 `eq`（相同）/ `rep`（替换差异）/ `del`（仅A）/ `ins`（仅B）四色标注；sticky 头部显示「相同 N · 差异 M · 仅A X · 仅B Y」四项计数与两端文件·函数名。
- 该特性让工程师**直接看到"哪几行重复"**而非仅相似度百分比，是重构决策的最直接依据。

#### 二、P217c 暗色主题 + 视图偏好持久化
- tabs 栏新增 🌙/☀ 主题切换按钮（`__gs_toggle_theme`），以 `:root[data-theme="dark"]` + GitHub Dark 语义轻量覆盖全局状态图核心容器与 dup/trend 全部类（不逐项重写亮色 CSS，控制膨胀）。
- 用户视图状态经 `localStorage` 持久化：`gs-view` 存 `{tab, q, sort, f}`，`gs-theme` 存 `dark/light`；刷新页面即恢复上次查看的 tab、搜索词、排序、筛选与主题——**大项目反复排查时不丢上下文**。
- 写入点覆盖 tab 切换（`__gs_show`）、搜索/排序（`__dup_filter`）、筛选（`__dup_fchip`）、主题切换（`__gs_toggle_theme`），读取点在初始化 IIFE 中恢复。

#### 三、P217g 前端 JS 自动校验纳入 CI（防回归护栏）
- 历史教训：P204 看板因 Python 三重引号模板写入字面 `\'` 使生成 JS 含 `\'`，浏览器 `SyntaxError` 致整段 `<script>` 中断（悬停联动全失效），且长期处于"能生成但浏览器崩"的静默状态。
- 新增 `test_p217g_frontend_js_sanity`：生成含 dup + 趋势基线的 `global_state.html` → 抽取 `<script>` → **`node --check` 真语法校验**（环境有 node 时）；无 node 时优雅降级为纯 Python 结构断言（关键：断言生成 JS **不含字面 `\'`**，锁定转义 bug 指纹）。
- 此后任何 JS 模板改动若再次引入转义错误，CI 立即红灯，杜绝静默回归。

#### 四、验证
- `test_p217d_dup_inline_diff`（含 `_dup_side_by_side` 算法单测：相同对全 eq、含差异对正确标 rep/eq）+ `test_p217c_theme_persist` + `test_p217g_frontend_js_sanity` 全绿。
- 沿用 P217b 的端到端冒烟（动态生成重复对 → `_run` 子进程 → 结构 + `node --check` 双校验），确认 diff 注入、主题按钮、持久化逻辑、暗色 CSS 齐备且 JS 语法合法。
- 全量前端相关（`test_p217_dup_code_dashboard` / `test_p217b` / `test_p217d` / `test_p217c` / `test_p217g` / `test_p226` / `test_p229` / `test_p228` / `test_p227` / `test_p54` / `test_p59`）无回归。

**闭环状态**：dup_code 体系达成「结构→语义→ROI→演化基线→误报抑制→跨语言→趋势可视化→看板交互→行内 diff 诊断→主题/持久化→CI 语法守护」完整工程闭环，前端质量具备自动化防线。
**版本与文档**：VERSION/setup.py → 1.16.44；README 变更日志追加 1.16.44 行；JSON_SCHEMA/STRUCTURE 版本同步；本报告新增 §3.47.23；测试矩阵 178 → 181 项（新增 `test_p217d_dup_inline_diff` / `test_p217c_theme_persist` / `test_p217g_frontend_js_sanity`）。

---

### 3.47.24 P217i 看板闭环：diff 一键生成共享函数脚手架（v1.16.45）

在 P217d（行内嵌并排 diff）之上补齐 dup 体系最后一环——**从"看到重复"直接到"消除重复"的脚手架**。

#### 一、一键生成共享函数脚手架
- 每条并排 diff 头部新增「📋 生成共享函数」按钮（`__dup_build_scaffold`），从已注入看板的 `diff` 数据现场生成，无需重新分析、不污染 `--json`。
- 生成策略（稳健、零风险、可人工接管）：
  - **公共体（eq 行，双端文本一致）** → 直接作为 `shared_<func>` 函数主体；
  - **差异点（rep 行）** → 标注 `% DIFF 抽象点：A:… | B:…`，提示工程师把该处分支抽象为 `varargin` 参数或子分支；
  - **仅单边（del/ins 行）** → `% 仅 A 存在` / `% 仅 B 存在` 注释保留，避免信息丢失；
  - 函数名 `<func>` 中非法字符（非 `[A-Za-z0-9_]`）归一为 `_`，保证合法 MATLAB 标识符。
- 产出 `function [out] = shared_<func>(varargin)` 骨架 + 头注释（标注来源两端函数）+ `out = []; % TODO` 占位，并附带**两端调用方改写建议**（`fooA(...)→shared_fooA(...)` / `fooB(...)→shared_fooA(...)`）。

#### 二、弹窗预览 + 复制（含暗色适配）
- `__dup_show_modal` 渲染模态框：标题 `shared_<func>.m`、`<pre>` 预览 `.m` 文本、`调用方改写建议` 区、底部「复制 .m / 复制调用建议 / 关闭」三按钮。
- 复制走 `navigator.clipboard.writeText`（现代浏览器）+ `textarea` + `execCommand('copy')` 降级（兼容旧环境）。
- 弹窗与按钮均含 `:root[data-theme="dark"]` GitHub Dark 语义样式，与 P217c 主题切换一致。

#### 三、验证
- `test_p217i_scaffold`：结构与 node **DOM-stub 运行时双校验**——stub `document`/`localStorage`/`navigator`，运行 `__dup_build_scaffold` 后断言 modal 标题为 `shared_fooA.m`、预览含正确 `function [out] = shared_fooA` 头 + 公共体 `y = y * 2;` + DIFF 标注 `y = foo(x);`。
- 沿用 P217g 的 `node --check` 守护，确认脚手架 JS 无语法/转义回归（`\n` 经 `\\n` 正确转义，未复用历史 bug 指纹）。
- 全量前端相关（P217b/d/c/g/i、P204、P227/228/229、P226、P54/P59 文档一致性）无回归。

**闭环状态**：dup_code 体系达成「结构→语义→ROI→演化基线→误报抑制→跨语言→趋势可视化→看板交互→行内 diff 诊断→主题/持久化→CI 语法守护→**一键脚手架消除**」完整工程闭环，从发现到重构动作一步打通。
**版本与文档**：VERSION/setup.py → 1.16.45；README 变更日志追加 1.16.45 行；JSON_SCHEMA/STRUCTURE 版本同步；本报告新增 §3.47.24；测试矩阵 181 → 182 项（新增 `test_p217i_scaffold`）。

---

### 3.47.25 P217 闭环收官：跨 tab 跳转 + 趋势下钻 + 批量脚手架 + AST 差异识别 + 全站主题统一（v1.16.46）

把本轮规划的全部 5 个下一步（P217e/f/l/k/j）一次性落地，dup 体系达成完整工程闭环。

#### 一、P217e 跨 tab 跳转闭环（看板 ↔ 源码站双向）
- dup 行函数A 与 diff 头部 A/B 各加「🔗」链接（`__gs_open_src`），点击 `window.open('src/<rel>.html#hs-<func>')` 跳 `--browse` 源码站并定位到对应函数卡（锚点 `hs-<func>` 由 P124 源码页提供）。
- 配合 P219 的 dup↔冲突变量联动，形成"看板诊断 → 源码现场"闭环。

#### 二、P217f 趋势图下钻（从看图到看函数级变化）
- 趋势 SVG 点加 click 事件委托（`host.onclick` → `__trend_drill(i)`），弹窗显示该快照相对前一快照的 **new/gone/drift 函数对明细**——从基线 history 的 `pairs` 字段计算（本步有、前步无 = new；反之 gone；key 同而 similarity 变 = drift）。
- 复用 `__dup_show_modal`（`isHtml=true` 渲染 HTML 明细），含 🌙/☀ 暗色适配。

#### 三、P217l 批量脚手架（一次产出 TopN 共享函数）
- 重构优先级 TopN（P225）表头加「📦 批量生成」（`__dup_batch_scaffold`）：遍历 `dup_roi_top` 中带 diff 的记录，复用 `__dup_make_scaffold` 核心，聚合为 `batch_shared_<N>.m` 可复制文本块（每函数用 `=====` 分隔 + 调用建议）。
- 修复：`dup_roi_top` 注入时同步携带 `_dup_rows` 的 `diff` 字段（原仅原始 dup_code 无 diff，导致批量无产出）——建立 `_dup_rows_idx` 按 (file,func,line) 取 diff。

#### 四、P217k AST 差异变量识别（半自动脚手架增强）
- 新增 `__dup_diff_tokens`（词法级）：对 rep 行两端用 `[A-Za-z_]\w*` 抽取标识符求差集，识别"差异变量"（如 `foo` vs `bar`）。
- `__dup_make_scaffold` 据此在函数头注释标注「差异参数候选」并在 DIFF 行给出「参数化: pN(token)」提示，调用建议改为 `shared_<func>(varargin{N})`。**安全、可解释**，不引入完整 AST 替换的误改风险，为后续深度改写（P217k-2）奠基。

#### 五、P217j 全站主题统一
- `--browse` 站点 `GLOBAL_SEARCH_JS` 顶部加主题恢复（读 `localStorage.gs-theme` 设 `data-theme`），与 `--global-state` 共用 key `gs-theme`；browse 主题切换 `maToggleTheme` 同步写 `gs-theme`。跨站刷新即恢复统一暗色偏好。

#### 六、验证
- 新增 5 个回归（均含 node 运行时校验）：`test_p217j_cross_site_theme`（源码级 GLOBAL_SEARCH_JS 含 gs-theme + global-state 写 gs-theme）、`test_p217e_cross_tab_jump`（`__gs_open_src` 运行时不抛错）、`test_p217f_trend_drill`（`__trend_drill(1)` 弹 `dup-trend-#1`）、`test_p217l_batch_scaffold`（`__dup_batch_scaffold` 弹 `batch_shared_<N>.m`）、`test_p217k_diff_tokens`（脚手架含 `foo`/`bar` 参数化提示）。
- 沿用 P217g 的 `node --check` 守护，本次修复 `__gs_open_src` 正则 `/\\/g` 转义（`\\\\` 才能生成 JS 字面 `\\`，否则 `SyntaxError`），再次验证转义护栏有效。
- 全量前端相关（P217b/d/c/g/i/j/e/f/l/k、P204、P227/228/229、P226、P54/P59 文档一致性）无回归。

**闭环状态**：dup_code 体系达成「结构→语义→ROI→演化基线→误报抑制→跨语言→趋势可视化→交互→行内 diff→脚手架→跨 tab 定位→趋势下钻→批量生成→AST 差异识别→全站主题统一」**完整工程闭环**，从"发现重复"到"消除重复"全链路工具化、可诊断、可守护。
**版本与文档**：VERSION/setup.py → 1.16.46；README 变更日志追加 1.16.46 行；JSON_SCHEMA/STRUCTURE 版本同步；本报告新增 §3.47.25；测试矩阵 182 → 187 项（新增 `test_p217j_cross_site_theme` / `test_p217e_cross_tab_jump` / `test_p217f_trend_drill` / `test_p217l_batch_scaffold` / `test_p217k_diff_tokens`）。

---

### 3.47.26 P217 深度闭环：AST 精确重构 + CI 门禁 + 影响分析 + 关系图 + 组织库（v1.16.47）

把"闭环收官"后的 5 个下一步（P217m/n/p/q/o）一次性落地，dup 体系从"可用工具链"升级为"团队级工程基础设施"。

#### 一、P217m 深度 AST 改写（精确签名）
- 脚手架生成接入 **P221 AST 级参数映射**（`_dup_infer_shared_signature`）：在 `_dup_rows` 构造 diff 时，取 A/B 函数 `FunctionInfo` 的 inputs/outputs + 公共行，推断共享函数**精确签名**（如 `function [y] = shared_fooA(x, k)`），注入 `diff.signature`。
- JS `__dup_make_scaffold` 优先用精确签名（真实参数名），确定不了时回落 `varargin`（保持 P217k 差异 token 标注）。把"消除重复"从半自动（varargin + 提示）推向**精确参数化**。

#### 二、P217n CI 门禁（`--dup-fail-gate`）
- 新增独立于 `--fail-on-dup` 的绝对值闸，支持三种形式：`MAX_TOTAL`（总对上限）/ `MAX_TOTAL:MAX_NEW`（总上限 + 相对基线增量上限，需 `--dup-baseline`）/ `%RATE`（重复率 = dup对数/总函数数×100）；`warn:` 前缀仅告警不阻断。
- 接入主流程 `ok` 退出码，配合 `--dup-baseline` 实现"增量重复率门禁"，可直接用于 CI 流水线。

#### 三、P217p 重构影响分析
- diff 注入 `callers`（反向 callsite 扫描，`_dup_callers_of_func` 用 `callers_of` 映射），列出 A/B 函数的所有调用方（rel/fn/line）。
- 脚手架调用建议追加"调用方（需同步修改 N 处）"清单——改完 shared 后，工程师一眼看到要同步改动的 N 个调用点。

#### 四、P217q 关系图（力导向）
- dup 看板新增「关系图」tab（`__render_dup_graph`）：确定性力导向布局（节点=函数、边=重复对；颜色=重复度、边粗=相似度、点击节点跳源码站 P217e）。从"列表/趋势"升级到"网络拓扑"视角，一眼识别高重复枢纽函数。

#### 五、P217o 组织级指纹库（`--dup-org-baseline`）
- 新增可共享的重复指纹库（即普通 `.dup_baseline.json`，天然可提交/Git LFS 共享）。加载后，当前命中的重复对若已存在于组织库则标注「🌐组织已知」（`org_match`），并支持 `org` chip 过滤——跨项目/团队识别"通行重复"，沉淀最佳实践。
- 指纹对齐：直接复用基线 `pairs` 的 key（`_dup_pair_key`），与当前检测完全对齐，零额外映射成本。

#### 六、验证
- 新增 5 个回归（含 node 运行时校验）：`test_p217m_ast_signature`（精确签名 `[y]=shared_fooA(x,k)` + 差异 token 保留）/ `test_p217n_dup_fail_gate`（上限0阻断、warn 仅告警、%RATE 解析）/ `test_p217p_refactor_impact`（callers 注入 + 调用建议含调用方）/ `test_p217q_force_graph`（SVG 渲染 + 节点可点击）/ `test_p217o_org_baseline`（自身基线作 org 库触发标注）。
- 沿用 P217g 的 `node --check` 守护（本次新增力导向图、org 标注等大量 JS 均通过语法校验）。
- 修复 P217m 引发的旧测试断言漂移（`test_p217i_scaffold`/`test_p217k_diff_tokens` 适配精确签名模式）。
- 全量前端相关（P217b/d/c/g/i/j/e/f/l/k/m/n/p/q/o、P204、P227/228/229、P226、P54/P59 文档一致性）无回归。

**闭环状态**：dup_code 体系达成「结构→语义→ROI→演化基线→误报抑制→跨语言→趋势可视化→交互→行内 diff→脚手架→跨 tab 定位→趋势下钻→批量生成→AST 差异识别→全站主题→**AST 精确签名→CI 门禁→重构影响→关系图→组织库**」**团队级工程基础设施闭环**，覆盖从发现、诊断、重构到团队协同与 CI 守门的完整生命周期。
**版本与文档**：VERSION/setup.py → 1.16.47；README 变更日志追加 1.16.47 行；JSON_SCHEMA/STRUCTURE 版本同步；本报告新增 §3.47.26；测试矩阵 187 → 192 项（新增 `test_p217m_ast_signature` / `test_p217n_dup_fail_gate` / `test_p217p_refactor_impact` / `test_p217q_force_graph` / `test_p217o_org_baseline`）。

---

### 3.47.27 P217 终局闭环：自动补丁生成 + PR 门禁报告（v1.16.48）

把上一轮建议的两项终局能力落地，dup 体系从"能诊断、给建议"跃迁到"**一键消除重复 + 评审环节自动守门**"。

#### 一、P217r 自动补丁生成（`--dup-emit-patch`）
- **补齐 P214 的关键缺口**：P214 可执行补丁只改写 A/B 函数体本身，所有调用方仍指向旧函数名（`fooA(...)`），补丁合入后必然编译失败——这是"可应用"与"可运行"之间的最后一公里。
- 新增 `_build_dup_callers_patch`：以**文本级全文件 callsite 扫描**（而非依赖 `model.callers_of` 调用图）定位每一处调用，把 `\b<func>\s*\(` 改写为 `shared_<func>(`，逐文件整体重建后统一 diff。
  - 选择文本扫描而非调用图：调用图只覆盖被解析为已知函数的边，而调用点改写需要的是源码文本级的每一处调用，二者目标（文本）严格一致，且更完备。
- **安全边界**：跳过 `function ...` 定义行（由 P214 主体 hunk 负责改写），不触碰同名字符串，避免误伤。
- 输出补丁 = 共享函数新建 + 两端主体替换 + **全部调用点同步**，可直接 `git apply`。

#### 二、修复 P214 遗留缺陷：hunk 头粘连（补丁真正可应用）
- 发现 P214 生成 hunk 时用 `fromfile="a/<f>\n"` + `lineterm=""`，导致 hunk 头与首行内容粘连成
  `@@ -1,6 +1,3 @@ function y = fooA(x, k)`，不符合 unified diff 规范，**`git apply` 会报 corrupt patch 拒收**。
- 新增 `_normalize_unified_diff`：在 P217r 落盘前把 `@@ ... @@` 与内容拆成两行（幂等，已规范的补丁不受影响）。
  采用"落盘前规范化"而非改 P214 源头，保证既有 P211/P214 测试零回归。

#### 三、P217s PR 门禁报告（`--dup-pr-report`）
- 产出可直接贴到 PR 评论区的 Markdown 报告：总览（重复对/函数总数/重复率）+ 相对基线的**新增·已修复·漂移**明细
  + **预计可消除行数（ROI）估算**（保守：min(两端 body 行数) × 相似度）+ 重构优先级 Top-N + 一键重命令。
- 把质量门禁从 CI 流水线**前移到评审环节**：评审者一眼看到"本次新增 2 对重复、预计可消除 ~8 行"。
- 无基线时优雅降级（跳过 diff 小节，仅总览 + 优先级）。

#### 四、验证
- 新增 2 个回归：`test_p217r_emit_patch`（含**内置 unified diff 应用器** ` _apply_unified_patch_text`——
  环境无 git，故自实现严格按语义校验的应用器：逐 hunk 上下文行匹配 + 增删语义，等价于 `git apply` 核心校验；
  断言共享函数新建、两端公共行已删除、调用方确实改写为 `shared_fooA(1, 2)`/`shared_fooA(3, 4)`）/
  `test_p217s_pr_report`（总览、新增明细、ROI 列、优先级、一键命令、无基线降级）。
- 全量 27 项前端+补丁+文档一致性回归**全过**（含 `test_p211_apply_patch`，确认 P217r 未破坏 P214 主体行为）。

**闭环状态**：dup_code 体系达成「结构→语义→ROI→演化基线→误报抑制→跨语言→趋势可视化→交互→行内 diff→脚手架→跨 tab 定位→趋势下钻→批量生成→AST 差异识别→全站主题→AST 精确签名→CI 门禁→重构影响→关系图→组织库→**自动补丁→PR 报告**」**终局闭环**，从"发现重复"到"一键消除重复并在评审环节自动守门"全生命周期贯通。
**版本与文档**：VERSION/setup.py → 1.16.48；README 变更日志追加 1.16.48 行；JSON_SCHEMA/STRUCTURE 版本同步；本报告新增 §3.47.27；测试矩阵 192 → 194 项（新增 `test_p217r_emit_patch` / `test_p217s_pr_report`）。

---

### 3.47.28 P217 可信闭环：重构补丁自证验证 + 增量索引加速（v1.16.49）

上一轮实现了"一键消除重复"（P217r），但**补丁是否正确**尚无自动证明。本轮补上信任闭环与性能底座。

#### 一、P221s 重构补丁自证验证（`--dup-verify-patch`）
- 新增 `_rerun_analysis_on_dir`：复制 main() 核心流水线（collect_files → parse_file → 索引 → analyze_calls → 复杂度 → _collect_checks），可在**任意目录**进程内重跑完整分析。
- 新增产品级 unified diff 应用器 `_apply_unified_patch_text`（无 git 依赖）：逐 hunk **逐字校验**上下文与删除行，**全量校验通过后才落盘**（原子性），任一处不符即拒绝。
- 验证流程：临时副本应用补丁 → 重跑分析 → 对比**四项不变量**：
  | 不变量 | 含义 | 失败含义 |
  |---|---|---|
  | 补丁可应用 | 上下文逐字匹配 | 补丁与代码不同步 |
  | 重复对减少 | dup 数 ≤ 重构前 | 重构无效 |
  | 无新告警 | uninit/dead/shape/taint 总数不增 | 引入回归 |
  | 调用边不丢 | 调用图边数不减 | 调用点漏改（最危险） |
- **绝不污染源码树**：全部在临时副本完成。
- `--dup-verify-apply`：**仅验证通过才落盘**——"要么安全重构、要么完全不动"。
- 输出 `DUP-VERIFY-PASS` / `DUP-VERIFY-FAIL`（与 P217n 的 `DUP-GATE-*` 风格统一），失败时退出码非零可阻断 CI。
- 实测：重复对 1→0、告警 0→0、调用边 2→4、改动 5 个文件，判定 PASS。

#### 二、P217x 增量索引与评分缓存（`--dup-cache`）——**profile 驱动的优化范式**
- 初版只缓存函数 token 序列，实测**加速仅 1.05x**。未凭直觉继续，而是用 `cProfile` 定位：
  | 阶段 | 耗时 | 占比 |
  |---|---|---|
  | `_apply_dup_idiom_suppression`（P227 惯用法评分） | 0.514s | **63%** |
  | `_compute_dup_roi`（P225） | 0.145s | 18% |
  | token 构建（原以为的瓶颈） | 0.139s | 17% |
- **关键修正**：真正热点是 `_dup_idiom_score`。它是**纯函数**（输出只取决于主体源行内容），故按**主体源文本 SHA-256** 缓存，跨运行复用。
- 结果：端到端 **0.359s → 0.102s（3.5x 加速）**，且 `(file, func, similarity, idiomatic, roi)` **逐条完全一致**（缓存是纯优化，绝不影响结果）。
- token 缓存保留（100% 命中率，对超大文件解析场景有益），签名用**内容 SHA-256**（非 mtime），故 git checkout / 换机器后仍可命中。

#### 三、P217x-2 两处**数学严格**剪枝（零漏报）
- **Jaccard 长度上界剪枝**：由 `Jaccard ≤ min(|A|,|B|)/max(|A|,|B|)`，上界不达标则相似度必不达标 → 安全跳过昂贵的交集计算。对函数体长度差异大的真实仓库效果显著。
- **片段长度下界剪枝**：任一端有效行数 < `min_lines` 时，不可能存在长度 ≥ min_lines 的公共连续片段 → 安全跳过昂贵的 `_best_continuous_frag`。
- 两者均为**数学严格**（非启发式，不漏报），已由 `test_p217x_dup_cache` 用"暴力全比较"对照验证：`brute pairs == pruned pairs, missing=0`。

#### 四、验证
- 新增 2 个回归：`test_p221s_verify_patch`（正例 PASS + 坏补丁 FAIL 且非零退出 + **源码逐字未变**）/ `test_p217x_dup_cache`（结果一致性 + 100% 命中 + **剪枝零漏报** + 变更自动失效）。
- **全量 29 项回归全过**（含 P211 补丁、P227 惯用法抑制、P228 跨语言等，确认剪枝与缓存未改变任何既有结果）。
- 修复 CLI 在非 UTF-8 终端（GBK）输出 emoji 的乱码问题：控制台改用 ASCII 标记（`PASS`/`FAIL`），Markdown 报告（UTF-8 文件）保留 ✅/❌。

**闭环状态**：dup_code 体系达成「…→自动补丁→PR 报告→**补丁自证验证**→**增量索引加速**」**可信闭环**——不仅能一键生成重构补丁，还能**自动证明补丁正确**（重复减少、无新告警、调用不丢），并在大仓库上保持 3.5x 分析效率。
**版本与文档**：VERSION/setup.py → 1.16.49；README 变更日志追加 1.16.49 行；JSON_SCHEMA/STRUCTURE 版本同步；本报告新增 §3.47.28；测试矩阵 194 → 196 项（新增 `test_p221s_verify_patch` / `test_p217x_dup_cache`）。

---

### 3.47.29 P217 正确性闭环：语义等价性验证 + 补丁冲突合并 + 两处真实缺陷修复（v1.16.50）

上一轮实现了「补丁自证验证」（P221s），但它只证明**结构不变量**（重复减少/无新告警/调用边不丢），未证明**语义等价**。本轮在推进建议项时，先做了"验证现有能力是否真的正确"，结果**发现并修复了两处会静默改变程序行为的真实缺陷**——这是本轮最大价值。

#### 〇、先诊断再动手：发现两处真实缺陷（本轮最大价值）

| # | 缺陷 | 影响 | 修复 |
|---|---|---|---|
| **A** | `_dup_shared_func_src`：`"% ↓ ..." % _nd` 中 `%` 优先级高于 `+`，`"% TODO"` 被当作格式说明符 | `n_diff>0`（存在真实差异行）时**必抛 ValueError**，补丁**静默不生成** | 改为纯字符串拼接 |
| **B** | `_dup_extract_common_lines` 仅用结构指纹判定公共行；指纹把未解析函数名归一化为 `<V>`，使 `y = foo(x);` 与 `y = bar(x);` **指纹完全相同** | 共享函数静默采用 **A 端版本** → **B 端被悄悄改成调用 `foo`**（行为静默变化，且 P221s 的结构检查查不出来，因为二者都是外部调用、无调用边） | 新增「调用位置标识符」比对：不同则**保守判为差异行**，保留在各自函数体内 |

缺陷 B 的实证（修复前 vs 修复后，样本 pA/pB 仅一处调用不同）：

| | 修复前 | 修复后 |
|---|---|---|
| `shared_pA.m` | 含 `foo(x)` | **不含** `foo(` |
| `pA.m` | — | 保留 `foo(x)` |
| `pB.m` | **被改写成 `foo(x)`** | 保留 `bar(x)` ✅ |

> 关键认知：**指纹相同 ≠ 语义相同**。这一发现直接催生了 P217y 的设计（把"语义等价"作为一等公民来验证），也说明 P221s 的结构检查不足以保障正确性。

#### 一、P217y 语义等价性验证（`--dup-verify-equiv`）
静态证明「提取共享函数不改变程序行为」，**无需执行 MATLAB**。四项检查：

| 检查 | 内容 | 失败含义 |
|---|---|---|
| **C1 调用一致性** | 对齐行是否调用了不同函数（`foo()` vs `bar()`） | 指纹相同但语义不同的**假重复** |
| **C2 输出契约** | 两端输出参数集合一致 | 提取后丢失返回值 |
| **C3 参数映射完备** | 公共体自由变量全部落在实参中 | 回落 varargin，需人工确认 |
| **C4 副作用** | 共享体含 I/O、eval、global 等 | 提取改变执行时机/上下文 |

判定：`EQUIVALENT`（等价）· `PARTIAL`（部分等价，非真重复）· `REVIEW`（建议复核）· `UNSOUND`（不等价）。
配 `--dup-verify-patch` 自动附带等价性章节；`--dup-strict-equivalence` 令 UNSOUND 阻断 CI。

#### 二、P217z 补丁冲突合并
多对重复同时重构时，同一文件可能既被「主体 hunk」改写（自身是重复函数）、又被「调用点 hunk」改写（它调用了别的重复函数），区间重叠会让 `git apply` **整体拒收**——这是多对重复一键重构的实际阻塞点。
`--dup-emit-patch` 现自动检测重叠并合并为单一 diff（**重叠删除取并集、插入按 hunk 顺序拼接**，语义不丢失）；无重叠时零改动（幂等、零 churn）。
实证：`pA.m` 两 hunk 重叠 → 合并为 1 段 → 应用后同时得到 `shared_pA(...)`（主体）与 `shared_qA(x, 2)`（调用点，实参个数匹配）。

#### 三、P217r 调用点改写加固（修复自身引入的隐患）
P214 是**委派式**重构：原函数**并未删除**，仅把公共行换成 shared_* 调用，**差异行仍留在原函数体内**。因此：
- 带差异行时改写调用点 → **绕过保留逻辑**（行为改变）；
- 共享函数形参数常少于原函数 → 按位置传参**错位**（如 `mA(x,2)` → `shared_mA(x,2)`，但后者只有 1 个形参）。

现改为**「可证明安全才改写」**：① 重复对无差异行（原函数成为纯转发壳）；② 共享函数形参与原入参**同名同序**。否则跳过并打印原因（原函数照常工作，零风险）。

#### 四、验证
- 新增 3 个回归：`test_p217y_semantic_equivalence`（四种判定全覆盖：EQUIVALENT/PARTIAL/REVIEW/UNSOUND，并验证 C2、C4 具体检出）/ `test_p217z_patch_merge`（重叠检测 + 合并为单段 + 可应用 + 实参个数匹配）/ `test_p217r_safe_caller_rewrite`（确认安全路径未被一刀切关闭）。
- 更新 `test_p217r_emit_patch`：断言「不安全则不改写」「差异行不进共享函数」「两端各自保留自己的调用」。
- **全量 32 项回归全过**。

**闭环状态**：dup_code 体系达成「…→自动补丁→自证验证→**语义等价性证明**→**冲突合并**」**正确性闭环**——不仅能量化重构效果，更能**证明重构没有改变程序行为**，并修掉了两处会静默改写的真实缺陷。
**版本与文档**：VERSION/setup.py → 1.16.50；README 变更日志追加 1.16.50 行；JSON_SCHEMA/STRUCTURE 版本同步；本报告新增 §3.47.29；测试矩阵 196 → 199 项（新增 `test_p217y_semantic_equivalence` / `test_p217z_patch_merge` / `test_p217r_safe_caller_rewrite`）。

### 3.47.30 P270 前端交互重构与引领特性：共享内核 + 命令面板 + 可分享深链 + 键盘导航/无障碍（v1.16.52）

本轮目标：把"查看源码/前端交互有问题"从主观描述变成**可验证、可分享、可无障碍访问**的体验。整体策略是"先重构共享内核、再在其上叠加引领性特性"——新能力一次建成、全站生效。

#### 一、共享 JS 内核 `CORE_JS`（消除 3 份重复 + 修复真实缺陷）

此前主题逻辑散落 3 处且 localStorage key 互不统一（一处读 `gs-theme`、一处写 `ma-theme`）。新增单一数据源 `CORE_JS`，统一 key 为 `gs-theme`，并新增 `?theme=` URL 覆盖与系统 `prefers-color-scheme` 适配；browse 站点 / report.html / global_state.html 三端复用同一份，注入顺序置于样式之前（杜绝暗色闪烁 FOUC）。

#### 二、全站命令面板（Ctrl+K / `/`）——引领特性

升级既有搜索浮层为**真·命令面板**：`_build_gs_index` 生成「函数 / 文件 / 目录 / 全局变量」四类跳转索引并独立成 `src/_index.js` 全站共享。链接按页面深度用 `__CG_SITE_REL__` 拼接，彻底消除此前在 `src/` 页硬编码 `func_detail.html?g=` 造成的又一类死链。

#### 三、可分享深链 `DEEPLINK_JS`——引领特性

把全局状态图的 tab/筛选/排序/搜索/分页状态**双向同步到 URL hash**（如 `#tab=fuzzy&f=cross&sort=roi&q=foo`），URL 优先于 localStorage；任意视图可复制链接分享、刷新可还原，且默认值（`f=all`/`page=0`）不污染 hash。

#### 四、键盘导航与无障碍 `KBD_JS`

新增 `?` 帮助浮层、Esc 关闭任意浮层、`t`/`g`/`d`/`h`/`/` 全局快捷键、焦点锁定与归还；所有产物添加 `skip-link` 与 `<main>` 语义包裹。

#### 五、配套基建与回归

`fe_audit.py` 的 DOM stub 测试 harness 全面升级（appendChild 注册元素、addEventListener/dispatchEvent 事件派发、KeyboardEvent 桩、location.hash 读写）。新增回归 `test_p270_deeplink_shareable`（深链序列化往返）/ `test_p270_keyboard_a11y`（帮助浮层开合 + 三端注入 + skip-link）。

**版本与文档**：VERSION/setup.py → 1.16.52；README 变更日志追加 1.16.52 行；STRUCTURE 版本同步；本报告新增 §3.47.30；全量测试矩阵 205 项全部通过。

### 3.47.31 P271 前端交互彻底重构：统一命令面板 + 引擎去重 + 源码行深链 + 面板 2.0 + 全站无障碍基线（v1.16.53）

本轮沿用「先重构共享内核、再在其上叠加引领特性」的策略，五轮全部自动化执行并逐轮回归验证。

#### 一、R1 合并双搜索 → 统一命令面板

browse 首页此前存在**两套搜索**（内联 `#search` 与全局浮层），交互割裂、实现重复。现统一由命令面板驱动：索引式检索，覆盖「函数 / 文件 / 目录 / 全局变量 / 源码全文」五类目标。**修复真实缺陷**：主题切换读写 key 不对称（读 `gs-theme`、写 `ma-theme`），导致按 `t` 切换主题后刷新丢失。

#### 二、R2 调用图引擎去重 + 脉冲交互统一

`@keyframes cgPulseAnim` 在 report 与 browse 两处各写一份完全相同的定义（复制漂移风险），抽为共享常量 `CG_PULSE_CSS`，两处内嵌同一份。并让全域调用图页（`UNIFIED_GRAPH_JS`）也暴露 `window.cgPulse`，使命令面板的「悬停结果 → 调用图脉冲」在**全站一致**生效（此前仅函数详情页支持）。

#### 三、R3 源码行深链（引领特性）

新增 `#Lx`（单行）/ `#Lx-y`（区间）行高亮 + 平滑滚动定位 + `hashchange` 响应；点击行号单元格**一键复制本行链接**。此前 `#L` 仅靠浏览器原生锚点：无高亮、不能选区间、无法便捷复制——「这段代码」现在可分享。配套 `LINE_DEEPLINK_JS` 与 `ln-hl` 样式。

#### 四、R4 命令面板 2.0（引领特性）

- **模糊打分排序**：子序列匹配（`fda` → `fooDetailA`），并按下优先级加权：完全相等 > 前缀 > 词首（`_`/`.`/`/`/camelCase 边界）> 子串 > 子序列。
- **最近访问**：localStorage 持久化（上限 12、自动去重），空查询即展示，越用越顺手。
- **Shift+Enter 跨站深链**：跳到全局状态页并预置筛选（`#tab=fn&q=foo`），链接可直接分享。
- **修复死链**：Enter 跳转此前硬编码 `func_detail.html?g=`，在 `browse/src/` 页会解析成 `src/func_detail.html`（死链）；统一改走 `hrefFor()` 按 `SITE_REL` 计算。

#### 五、R5 全站无障碍基线

全部 21 个 HTML 产物补齐 `lang` / `skip-link` 锚点 / `<main>` 语义地标。关键发现：此前 16 个页面**只有 `.skip-link{...}` 的 CSS 文本、没有真实锚点元素**——仅做子串匹配会让所有页面误判为「已具备无障碍」，是本轮修复前审计的真实盲区。

#### 六、配套基建

测试 DOM stub harness 大幅增强：可用 `classList`（add/remove/contains/toggle）、`window.dispatchEvent`、`window.scrollTo`；并修复 harness 自身缺陷——`window` 对象字面量在 `localStorage`/`document` 赋值之前求值，导致 `window.localStorage` 恒为 `undefined`（改用惰性 getter）。

新增回归 `test_p271_single_search_entrypoint` / `test_p271_palette_fulltext` / `test_p271_r2_graph_pulse_unified` / `test_p271_r3_source_line_deeplink` / `test_p271_r4_palette_two` / `test_p271_r5_a11y_baseline`；全量测试矩阵 **211 项**全部通过，前端审计 ERROR 0。

**版本与文档**：VERSION/setup.py → 1.16.53；README 变更日志追加 1.16.53 行；JSON_SCHEMA/STRUCTURE 版本同步；本报告新增 §3.47.31。

### 3.47.32 P271 续：验证体系升级（审计补盲区 + CI 门禁 + jsdom 真实 DOM）+ 深链与面板再扩展（v1.16.54）

P271 前五轮靠「改代码时顺手发现」揪出 3 个真实缺陷（主题 key 不对称、Enter 死链、无障碍只有 CSS 文本）。
这说明**静态审计存在盲区**。本轮把重心从「继续加特性」转向「让缺陷能被自动发现」。

#### 一、审计补两个盲区（S9 / S10）

- **S9 无障碍基线**：校验 `lang` / **skip-link 锚点元素** / `<main>` 地标，并进一步校验
  skip-link 的**实际跳转目标存在**。关键教训：此前只做子串匹配（`'skip-link' in html`），
  而 `BROWSE_CSS` 里含 `.skip-link{...}` 规则文本，会让**所有页面**误判为「已具备」——
  实际 16 个页面只有 CSS、没有锚点。S9 上线即查出 **report.html 缺 skip-link 与 `<main>`**（真实缺口）。
- **S10 JS 内硬编码导航**：检测 `location.href = 'func_detail.html?g=' + …` 这类写法——
  在 `browse/src/` 子目录页会解析成 `src/func_detail.html`（死链），是 P269/P271 反复出现的同一类问题。

#### 二、CI 门禁（防回退）

新增 `ci-examples/github-actions-frontend-gate.yml`：default 与 `--offline --enforce-offline`
双矩阵 + 离线产物零外链冒烟。同时新增 `test_p271_fe_audit_gate_selfcheck`，
让**门禁本身也被回归覆盖**——后续引入死链/运行时异常/无障碍缺失时，本地测试先于 CI 变红。

#### 三、jsdom 真实 DOM 验证（S11）

新增 `fe_dom_check.js`（fe_audit 的可选 S11 检查，缺 jsdom 时降级为 WARN）。
S5 的手写 stub 只能捕获「脚本一跑就抛异常」；S11 在**真实 DOM** 中验证：
主题切换是否真持久化（含 key 对称性）、命令面板能否打开并产出**可跳转**结果、
`#L` 深链是否真高亮、skip-link 目标是否存在。

已做**双向有效性验证**：注入缺陷（破坏 skip-link 目标 / 把写 key 改成 `ma-theme`）能稳定报错；
正常站点 33 页零误报。过程中还定位并修掉了检查脚本自身的 3 个陷阱
（file:// URL 缺盘符 → 外部脚本加载失败；未等脚本执行就检查；
`win.close()` 过早导致「document undefined」假象；`file://` 是 opaque origin 需注入 localStorage）。

#### 四、修复 R4 的一个跨页集成缺陷

命令面板 Shift+Enter 生成的 `#tab=fn&q=…` 使用了全局状态页**并不存在**的页签
（该页只有 `g`/`p`/`d`/`t`/`dg`），`__gs_show()` 静默失效——「链接生成了，点过去却没反应」。
已改为合法页签，并新增测试把「面板 tab 取值 ⊆ 目标页真实页签」这一跨页约定锁定。

#### 五、深链与面板再扩展

- **视图状态深链**：新增声明式 `VIEWSTATE_JS`，页面只需声明
  「控件 id → hash 键 → 默认值 → 变更回调」即可获得双向同步。已接入 index.html，
  调用图视图可经 `#cgmin=2&cglbl=1` 分享。
- **报告页命令面板**：`--html` 报告是自包含单文件，没有详情页/源码页可跳，此前无法用 Ctrl+K。
  现通过新增的 `__GS_FN_HREF__` 钩子把函数映射到**页内锚点**（热点图 `hs-fn-<gid>` 或度量表行 `fn-<名>-<行>`）；
  解析不到则返回 null、该项不显示——**绝不产出死链**。

#### 六、仓库清理

147 个根目录历史临时产物移入 `archive/_tmp_root/`（**移动而非删除**，被代码/文档引用的 7 项保留原位）。

新增回归 `test_p271_fe_audit_gate_selfcheck` / `test_p271_real_dom_interaction_check` /
`test_p271_viewstate_deeplink_and_valid_tabs` / `test_p271_report_page_palette`；
全量测试矩阵 **215 项**全部通过，前端审计 ERROR 0。

**版本与文档**：VERSION/setup.py → 1.16.54；README 变更日志追加 1.16.54 行；JSON_SCHEMA/STRUCTURE 版本同步；本报告新增 §3.47.32。

### 3.47.33 P271 续（后半）：CI 门禁落地 + 前端使用指南 + 文档防漂移（v1.16.54）

#### 一、CI 门禁真正启用（从「有工具」到「起作用」）

把 `ci-examples/github-actions-frontend-gate.yml` **落地为 `.github/workflows/frontend-gate.yml`** 并启用
（push/PR 自动触发，`workflow_dispatch` 支持手工）。三个 job：

- `fe-audit`：default 与 `--offline --enforce-offline` 双矩阵；
- `offline-smoke`：生成离线站点并断言**零外部引用**（本项目主要交付场景）；
- `unit-tests`：跑全量单元测试。

落地过程中发现并修掉一处「一进 CI 就失败」的问题：示例里写死源码目录 `matlab_src`，
而**该目录在本仓库并不存在**。改用仓库自带的 `tests/sample_m`（12 个 `.m`），
保证任何一次 checkout 都能跑通；同时把源码目录抽成 `env.FE_SRC`，用户改一处即可指向自己的代码。
`ci-examples/` 中的旧副本改为**指针文件**，避免同一份工作流出现两份而逐渐漂移。

#### 二、门禁自身也被守护

新增 `test_p271_ci_gate_workflow_usable`，校验：工作流存在且 YAML 合法、
**引用的源码目录真实存在且含 `.m` 文件**、用到的 `fe_audit` 参数（`--json` / `--offline` /
`--enforce-offline` / `--strict`）都受支持。这些都是「CI 里才暴露、本地极难发现」的问题。

#### 三、前端使用指南

新增 `matlabc_FRONTEND_GUIDE.md`，面向**使用产物的人**（而非开发本工具的人）：
全局快捷键、命令面板（模糊匹配 / 最近访问 / Shift+Enter）、三类可分享深链
（源码行 `#L42` / `#L42-58`、调用图 `#cgmin=2&cglbl=1`、全局状态 `#tab=d&q=fooA`）、
离线内网、无障碍、以及本地自查命令。README 第六节已补充入口。

#### 四、文档防漂移（本轮最有价值的一项）

新增 `test_p271_frontend_guide_matches_impl`，把指南里写的**快捷键、深链参数、全局状态页页签**
与实现逐一比对。动机很直接：文档写了但代码没有（或改名了），用户按文档操作会「没反应」，
而这类问题**不会让任何测试变红**，只能靠文档与实现之间的断言兜底。

该测试**立即查出一处真实漂移**：README 第六节第 5 条仍写着「索引页顶部输入框实时过滤函数名」，
而该内联搜索框在 P271 R1 已被移除、统一为命令面板——已修正。

**版本与文档**：VERSION/setup.py → 1.16.54；README 变更日志追加（含第六节漂移修正）；
新增 `matlabc_FRONTEND_GUIDE.md`；新增回归 `test_p271_ci_gate_workflow_usable` /
`test_p271_frontend_guide_matches_impl`；全量测试矩阵 **217 项**全部通过，前端审计 ERROR 0。

### 3.47.34 P271 续（第三轮）：大规模验证 + 审计提速 7.4x + 修两处工具缺陷（v1.16.54）

#### 一、大规模验证（前端改造的真实验收）

用 200 文件合成仓库（218 页 HTML / 38.2 MB）验证 R1–R5 的全部前端改造：
**审计 0 error、0 warn**。生成耗时 3.4s、200 文件全量分析 5.1s（节点数受 `--max-nodes`
严格截断）。说明统一命令面板、深链、行级分享、无障碍等改造在**真实规模**下没有问题——
此前所有验证都基于 12 文件的小样例，规模效应（大数据量索引、深度目录、分页）并未被覆盖。

#### 二、审计提速 7.4x（218 页：214.5s → 29.0s）

剖析发现耗时几乎全在**进程启动**，而非检查逻辑本身：

| 检查 | 原实现 | 耗时（218 页） | 新实现 |
|---|---|---|---|
| S1 语法 | 每脚本块一个 `node --check` 进程 | ~150s | 单进程 + `vm.Script` 逐个编译 |
| S5 运行时 | 每页一个 node 进程 | 43.6s | 单进程 + 每页**独立 vm 上下文** |
| S11 真实 DOM | jsdom 全量加载 | ~240s | **按页型采样**（默认 12 页）→ 12.0s |

S5 的关键设计是**页间隔离**：若把所有页简单拼进同一进程，页 A 里的
`window.__GS_LOADED__ = true` 会让页 B 的脚本提前 `return`，从而**漏掉页 B 整页的真实错误**。
假阴性比慢危险得多，故用 `vm.createContext` 为每页建独立上下文，并加回归测试锁定该性质。

S11 采样依据：交互缺陷通常**按页型聚集**（同一模板生成的页面行为一致），
故按「关键页面 + 每个目录取一页」去重采样，几乎不损失检出率而把耗时压到常数级；
需要全量时用 `--s11-limit=0`。

#### 三、修两处「工具自身问题被误当成产品问题」的缺陷

这类缺陷危害最大——它们让排查方向完全跑偏：

- **(a) `fe_audit.py` 在 Windows GBK 控制台崩溃**：审计结果含非 GBK 字符时 `print` 抛
  `UnicodeEncodeError`，表现为「加了 `--json` 却没有任何输出、退出码 1」。
  极易被读成「审计发现了严重问题」，实际是工具自己崩了。已统一 stdout/stderr 为 UTF-8。
- **(b) S5 的 DOM stub 制造假故障**：`getElementById` 对未知 id 返回 `null`，
  而 stub 不解析 HTML，页面里真实存在的元素（如 `<div id="fd-root">`）查不到，
  `el.innerHTML = ...` 就会抛异常 → 报出**并不存在的产品缺陷**。已改为返回桩元素。

#### 四、顺带修复：S5 的同步异常盲区

旧 S5 依赖 `process.on('uncaughtException')` 收集错误，但**同步抛出的异常**会导致：
末尾的结果输出行执行不到，而进程因已注册 handler 又不会退出（rc 仍为 0）→ **静默漏检**。
新实现直接捕获同步异常，检测能力严格变强（也正是它暴露了上面 (b) 的假故障）。

#### 五、备份机制

新增 `backup_files.py`（`save` / `restore` / `list` / `status`），
以文件级「最近一次已知良好」快照替代 git 作为安全网（按要求不使用 git/CI）。

新增回归 `test_p271_audit_batch_checks_still_detect`；全量测试矩阵 **218 项**全部通过，
大规模（218 页）审计 ERROR 0，前端审计 ERROR 0。

**版本与文档**：README 变更日志追加；新增 `fe_js_syntax.js` / `fe_js_runtime.js` /
`backup_files.py`；本报告新增 §3.47.34。

### 3.47.35 P271 第四轮：按证据排优先级的前端交互改造（v1.16.55）

本轮改变做法：**先扫描产物定位真实缺口，再按优先级改造**，而不是凭经验猜测。
扫描发现命令面板已 100% 覆盖（22/22 页），真正缺口在别处。

#### 一、R1 响应式基线（22 页中 17 页缺 viewport）

`<meta name="viewport">` 缺失时，移动设备按桌面宽度（约 980px）渲染再整体缩放，
文字极小、必须手动放大拖动——**等于移动端完全不可用**。已全站补齐（含 report.html，
它在 f-string 模板里、缩进与其他页不同，是唯一漏网的一个，由回归测试兜住）。

配套窄屏适配：宽表（如 12 列的度量表）改为「块级 + 横向滚动」，避免挤成不可读的竖条；
导航换行并给足触摸目标间距；源码行号列收窄；命令面板在窄屏上移。

> 踩坑：批量注入时 HTML 的双引号**必须转义**（`<meta name="viewport">` 直接放进
> Python 双引号字符串会破坏语法）。已先修复再验证产物无转义残留（20 页全部正确）。

#### 二、R2 操作反馈与系统偏好

- **复制反馈（真实缺陷）**：源码行「点击行号复制链接」此前**成功与失败都没有任何提示**——
  用户无法判断结果（静默成功看起来和静默失败一模一样）。新增全站共享 Toast
  （`role="status"` + `aria-live="polite"`，读屏可播报），成功/失败均明确提示。
- **`prefers-reduced-motion`**：前庭敏感用户开启后，脉冲高亮、平滑滚动、Toast 过渡
  会引发不适。已统一降级为无动画。特别注意：**CSS 的 `scroll-behavior` 覆盖不了
  JS 的 `behavior:'smooth'`**，故在 JS 里也判断了一次。
- **`prefers-contrast: more`**：提升边框与文字对比，服务弱视用户。

#### 三、R3 命令面板动作化（引领特性）

此前面板只能跳转、不能执行。新增命令注册表与 `>` 命令模式：
切换主题、复制本页链接、回到首页、打开统一图/度量/重复代码/函数详情/全局状态等。

关键设计是**无「幽灵命令」**：每条命令带 `when()` 判定在当前页是否可用。
报告（`--html`）是自包含单文件，若列出「回到站点首页」却无 `index.html` 可跳，
点了就是死链——比不提供该命令更糟。实测：站点页 8 条命令，报告页自动收敛为 2 条。

另将回车与点击统一到 `activate()`，避免两条路径行为不一致（此前点击只是跟随 href）。

#### 四、R4 调用图键盘可达

统一代码结构图（UNIFIED_GRAPH_JS）的节点此前**既无 `tabindex` 也无键盘处理**，
只有鼠标 `click`/`dblclick`——键盘与读屏用户完全无法使用该图。已补齐：
`tabindex` / `role="button"` / `aria-label`；`Enter` 打开源码页、`空格` 聚焦
（与鼠标双击/单击一一对应）；且**重绘后恢复焦点**（`render()` 会重建节点 DOM，
不恢复则键盘用户被弹回页面开头，无法连续操作）。

顺带修好 R2 的脉冲功能：该页节点此前缺 `cg-node-g`/`data-gid`，
命令面板的悬停脉冲在这里其实是失效的。

#### 五、质量保障

新增 4 项回归（`test_p271_r1_responsive_baseline` / `r2_toast_and_motion_prefs` /
`r3_palette_commands` / `r4_callgraph_keyboard`）；S11 增加常驻的图节点可达性检查，
并做了**反向验证**（去掉 `tabindex` 即报「8 个节点不可聚焦」），确认不是空转。
指南一致性测试扩展覆盖新特性，并新增**章节编号重复**检查（本次编辑就撞过号）。

大规模（200 文件 / 218 页）验证 **ERROR 0**，审计 20.8s；全量测试矩阵 **222 项**通过。

**版本与文档**：VERSION/setup.py → 1.16.55；README 变更日志追加；
`matlabc_FRONTEND_GUIDE.md` 新增命令模式、调用图键盘操作、移动端章节；
本报告新增 §3.47.35。

### 3.47.36 P271 第五轮：借鉴 MATLAB Agentic Toolkit 的设计原则改造信息呈现（v1.16.56）

#### 〇、先分析了 MathWorks 官方的 matlab-agentic-toolkit

仓库：<https://github.com/matlab/matlab-agentic-toolkit>（Apache-2.0）。

它由**两部分技术**组成：把 MATLAB 接入 AI agent 的 **MCP Server**，以及
MathWorks 用 MATLAB 工程实践构建的**精选 Skills**。MCP 侧的典型能力包括
`run_matlab_code`（执行代码并捕获输出/图形）、`check_matlab_code`（跑 Code Analyzer
返回诊断）、`run_matlab_file`、`shareMATLABSession`（连接用户已有的桌面 MATLAB 会话），
并以 **resources 形式**提供 `matlab_coding_guidelines` 供 agent **按需读取**。
Skills 侧按 MATLAB / 各工具箱分组，官方明确建议
「只安装与当前工作相关的技能组 —— 加载越少，agent 越可靠」。

**定位差异**：该工具包解决「让 AI agent 会用 MATLAB」，本工具解决
「让人会读一个 MATLAB 工程」。但其中**四条信息呈现原则**是可迁移的，本轮据此改造。

| # | 借鉴的原则 | 在本工具中的落地 |
|---|---|---|
| 1 | 只加载相关的技能组（越少越可靠） | 命令面板**分类作用域** `fn:` / `file:` / `dir:` / `var:` / `@` |
| 2 | 技能目录「分组 + 一行价值说明」 | 结果**分组显示** + 每项**一行上下文** |
| 3 | MCP resources「按需读取」 | 选中项的**预览面板**（不跳转即可看详情） |
| 4 | `check_matlab_code` 把诊断返回到代码位置 | 源码**函数定义行的内联诊断徽章** |

#### 一、R1 面板作用域（scoping）

结果太多时用前缀限定类别。只输前缀（如 `fn:`）即列出该类别全部，便于浏览。
两个易被忽略但关键的处理：

- **限定生效必须在界面上告知**（面板顶部提示条），否则用户会以为「搜不到东西」；
- **未识别的前缀按原文搜索，绝不吞掉用户输入**（如 `zzz:fooA` 不能退化成搜 `fooA`）。
  这一点专门加了断言：若被误判为作用域，测试就会失败。

#### 二、R2 结果分组 + 一行说明

结果按「命令 → 函数 → 文件 → 目录 → 全局变量 → 全文」分组，同类聚在一起；
每项显示一行上下文（函数=文件:行号、变量=定义于…、命令=作用说明）。
同时**移除项内冗余的类别徽章**（分组标题已表达同一信息，重复只会增加噪音）。

> 关键约束：分组后的**渲染顺序必须与内部 `list` 顺序一致**，
> 否则键盘 ↑↓ 的选中高亮会跳位（选中第 3 项却高亮别处）。
> 实现方式是在 `search()` 内按分组序完成排序，渲染时只负责插入分组标题。

#### 三、R3 预览面板（按需读取）

选中某项时右侧显示详情而**不跳走**：函数展示圈复杂度、扇入/扇出、风险标记；
全文命中展示整行并高亮关键词。窄屏（≤720px）自动堆叠到结果下方。
数据全部取自页面已注入的 `__CG__` / `__GS_INDEX__` / `__SEARCH_DATA__`，
**不发起任何请求**（离线可用）。

#### 四、R4 源码内联诊断

把分析结论放回**代码所在的位置**：函数定义行直接挂出
「复杂度 7 · 调用 3 · 被调用 12」，高复杂度（≥15）或高扇入（≥8）用黄色告警样式突出，
点击直达函数详情页。**非定义行不加徽章**——否则每行都挂，噪音会淹没代码本身。

#### 五、质量保障

新增 4 项回归（`test_p271_r5_palette_scope` / `r6_palette_grouping` /
`r7_palette_preview` / `r8_source_inline_diagnostics`），
并把指南一致性测试扩展到新特性（含**章节编号重复**检查——本次编辑确实撞过号）。

> 踩坑记录：测试 body 里用 `//` 行注释会吞掉后续代码——这些 Python 字符串
> 拼接后**全在一行**，注释会把后面的语句和 `}` 一起注释掉，表现为难以理解的
> 「Unexpected end of input」。已统一改用 `/* */`。

大规模（200 文件 / 218 页）验证 **ERROR 0**，审计 21.2s；全量测试矩阵 **226 项**通过。

**版本与文档**：VERSION/setup.py → 1.16.56；README 变更日志追加；
`matlabc_FRONTEND_GUIDE.md` 新增限定搜索范围、结果分组与预览、源码内联诊断；
本报告新增 §3.47.36。

### 3.47.37 革命性变化：从「代码浏览器」升级为「代码审查工作台」（v1.16.56）

#### 〇、先下载并分析了官方工具包

环境无 git，改用 GitHub 源码归档（codeload）下载并解压到 `_ref/matlab-agentic-toolkit-main`，
重点读取两个与我们最相关的技能：

- `skills-catalog/matlab-core/matlab-review-code` —— 官方代码审查标准
- `skills-catalog/matlab-software-development/matlab-modernize-code` —— 现代化速查表

（按要求，只精读**需要改动/可落地的部分**，未通读全部 24 个技能组、上千个文件。）

#### 一、为什么是「革命性」的

此前所有轮次都在优化**怎么看代码**（搜索、跳转、分组、预览、响应式）。
本轮改变的是站点本身的定位：

> 不只是让人看代码，而是**直接告诉你要改什么、属于哪一级严重度、以及怎么改**。

这是从「浏览器（viewer）」到「工作台（workbench）」的转变。

#### 二、合规总览页 `compliance.html`（新页面）

- **合规得分卡**：按官方严重度加权扣分（error ×8、warning ×3、suggestion ×1），
  给出 0–100 的得分与等级（良好 / 待改进 / 需重点整改）；
- **按官方三级严重度分组的发现清单**：每条都带「怎么改」，并可直接跳到源码行；
- **按文件下钻**的分布表（按 error → warning 数量排序，一眼看出先改哪个文件）。

#### 三、四类检查（依据官方清单）

| 类别 | 覆盖内容 |
|---|---|
| 命名约定 | 函数 lowerCamelCase、类 PascalCase、文件名与主函数名一致 |
| 函数质量 | 位置参数 >6、返回值 >4、长度 >50 行、嵌套 >3 层、圈复杂度 ≥15、缺 `arguments` 块、缺 H1 帮助行 |
| 现代化 | 18 项官方速查表：`datenum`→`datetime`、`csvread`→`readmatrix`、`xlsread`→`readtable`、`str2num`→`str2double`、`uicontrol`→`uibutton`、`containers.Map`→`dictionary`、`clear all`→`clearvars` 等；`eval`/`evalc`/`evalin`/`assignin` 列为**高危** |
| 可移植性 | 硬编码反斜杠路径（Windows 专用写法） |

#### 四、源码行内联现代化标记

用到废弃/不推荐 API 的行直接挂出 `⚠ csvread → readmatrix` 标记，
悬停显示官方推荐的替代方案；高危动态执行用红色区分。
性能上先做**文件级预筛**（只对本文件真正用到的 API 逐行匹配），
避免「每行 × 全表」在大文件上变慢。

#### 五、「需要人工复核」面板

官方明确指出 checkcode / Code Analyzer **查不出**这些项目，本工具自动检出并集中提示：
魔数（条件判断里的裸数字）、遮蔽内置函数（`sum = 0` 覆盖 `sum()`）、深层嵌套、缺 H1、硬编码路径。

面板上明确写出「**自动检查没报 ≠ 没问题**」，并特别注明官方原文：
**`subplot` 并未废弃**，只是新代码推荐 `tiledlayout`/`nexttile`，**不要盲目替换**——
避免本工具给出与官方相悖的建议。

#### 六、过程中的两个真问题

- **`eval` 一度漏检**：我定义了 `HIGH_RISK_DYNAMIC` 却忘了把它纳入扫描表，
  导致官方清单里**首要高危项**没被检出。已补进 `MODERNIZE_MAP`，并由回归测试锁定。
- **测试 flakiness**：`test_comments_visible_in_source` 原用固定目录 `tests/_t_cmt_*`，
  Windows 上 `rmtree` 偶发 OSError，会让整轮测试**随机**变红（本次全量运行即遇到一次）。
  已改为 `tempfile.mkdtemp()` 彻底消除。

#### 七、验证

新增 `test_p271_r9_review_workbench`：断言引擎真能产出发现（非空转）、
四类检查全覆盖、`eval` 必被检出、合规页链接无死链、源码页渲染出替代方案。
全量测试矩阵 **227 项**通过；80 文件规模的产物（99 页）审计 **ERROR 0**。

**版本与文档**：README 变更日志追加；本报告新增 §3.47.37 与 §3.47.38。
参考源码留存于 `_ref/matlab-agentic-toolkit-main/`，供后续按需精读。

### 3.47.38 P214 区间级抑制（v1.16.62）

#### 一、动机
C3 抑制原先只有三档：文件级 `ignore`、名称级 `ignore <name>`、行级 `ignore-next-line`。
对「连续几十行都需抑制」的真实场景（手写数值核心、自动生成代码段）只能逐行写 `ignore-next-line`，噪声大。
新增第四档——**区间级抑制**。

#### 二、语法
`% analyzer:disable [<check>]` ……（区间内所有行）…… `% analyzer:enable [<check>]`：
- `disable`/`enable` 必须成对；之间的行（不含两端）对该 `<check>` 全部抑制；
- 缺省 `<check>` = 抑制全部检查；指定具体检查名（uninitialized / type_mismatch / shape_mismatch / dead_code …）时仅抑制该检查；
- 未闭合的 `disable` 视为抑制到文件末尾；嵌套/错配按最近匹配闭合。

#### 三、实现
- `_parse_suppressions` 新增 `_RE_SUPPRESS_DISABLE` / `_RE_SUPPRESS_ENABLE`，用栈记录未闭合区间，算出 `block_lines: {行号: set(检查名)}`（与 `next_line` 同构）；
- `dead_code` / `type_mismatch` / `shape_mismatch` / `uninitialized` 四个检查函数各增加一处 `or (ln in block_lines and "<check>" in block_lines[ln])` 消费；
- `_count_suppressed` 增加 `blocks` 计数；`checks.html` 抑制汇总新增「区间级 N」展示。

#### 四、验证
- 新增 `test_p214_block_suppression`：块内未初始化变量被抑制、块外照常报告、区间计数 = 1；
- 既有 `test_c20_suppression` / `test_c23_suppression_next_line` 无回归；dead_code / type / shape 三个检查函数回归全绿；lint 0 错误。

**版本与文档**：本报告新增 §3.47.38；§9 路线图「块级抑制」由 P2 转为 ✅ 已完成。

### 3.47.39 P215 抑制原因汇总（v1.16.63）

#### 一、动机
P214 把 C3 抑制扩到四档后，`checks.html` 仅展示"已抑制 N 条"的汇总数。但**抑制疲劳**（suppression fatigue）是真实风险：抑制一旦写下就再没人复审，可能掩盖真实缺陷。需要把"抑制了什么、为什么、在哪"**显式摊开**，让评审一眼可审计。

#### 二、实现
- `_count_suppressed` 在原有四档计数（names/all/lines/blocks）基础上，新增 `details: [str]`：
  - 名称级条目带 `-- 原因`（如 `f.m: 名称级 v 的 uninitialized（原因：历史遗留）`）；
  - 文件级条目带 `*` 原因；
  - 行级条目标注行号与 `ignore-next-line`；
  - 区间级按连续行聚合为 `[a, b]` 区间（如 `f.m: 区间级 uninitialized 第 5–6 行（2 行，disable/enable）`），避免逐行刷屏。
- `checks.html` 在抑制汇总行下方新增可折叠 `<details>` 明细（默认收起、上限 200 条防膨胀），每条经 `html.escape` 转义。

#### 三、验证
- 新增 `test_p215_suppression_details`：断言 `details` 含名称级+原因、区间级行区间聚合，且 `blocks==1`；
- 既有抑制测试（C20/C23/P214）与 `test_c14_checks_page`（`checks.html` 渲染）无回归；lint 0 错误。

**版本与文档**：本报告新增 §3.47.39；§9 路线图「抑制原因汇总报告」由 P2 转为 ✅ 已完成；新增 `matlabc_FEATURES.md` / `matlabc_USAGE.md` 两份当前版本文档。

### 3.47.40 P216 内置函数工具箱化 + 按模块动态足迹（v1.16.64）

#### 一、动机
用户反馈：内置函数统计"还是静态的，所有内置函数都是一个样子"——不同模块本应依赖不同工具箱（信号处理 / 图像处理 / 控制系统 …），但当前 `MATLAB_BUILTINS` 是**全局扁平集合**，`matlab_builtin_desc` 对未登记函数统一返回"未单独收录"文案，报告只做**全局聚合**，看不出模块差异。

#### 二、实现（superpower 方案）
- 新增 `_TOOLBOX_GROUPS` + `matlab_builtin_toolbox(name)`：把已知内置按 MATLAB 工具箱归类，未归入者归 `MATLAB 基础`，消除"千篇一律"。
- `matlab_builtin_desc` 注入工具箱（如 `（信号处理工具箱）`），差异化每个内置的说明。
- 新增 `builtin_toolbox_breakdown(files)`：按工具箱聚合调用次数 + 涉及模块集合。
- 报告新增「内置函数按工具箱分布」章节（工具箱 / 调用次数 / 涉及模块数 / 代表函数）。
- `render_function_builtin_dims` 给每个内置标注 `[工具箱]`，并输出本函数 `Toolbox footprint`——**每个模块的内置足迹随模块而不同**。

#### 三、验证
- 新增 `test_p216_toolbox_breakdown`：`fft→信号处理`、`abs→MATLAB 基础`、`builtin_toolbox_breakdown` 按工具箱区分模块、`render_function_builtin_dims` 含工具箱标签与 footprint，全绿。
- 同步收口 `test_builtin_dim_line_registered_and_missing`（该测试在 P216 前已因 heuristic 重构红灯）：未登记维度内置明确标"维度未登记"、非内置明确区分。
- `py_compile` 零告警；lint 0 错误。

**版本与文档**：本报告新增 §3.47.40；§9 路线图新增「内置函数工具箱化」✅ 已完成；新增设计文档 `BUILTIN_TOOLBOX_DESIGN.md`（superpower 方案）。

---

## 4. 测试矩阵（178 项，全部通过）

| 类别 | 覆盖内容 |
| --- | --- |
| 端到端冒烟（~10 项） | `--browse` 站点、HTML 报告、SVG 调用图、全局力导向图、热点调用图、首页/函数页生成 |
| 调用图交互（~12 项） | 循环调用、URL 状态分享、跨文件跳转、节点点击跳转不坍缩、最短路径 BFS、序列化顺序、键盘无障碍 |
| 调用溯源与影响面（~8 项） | 溯源顺序/注释、影响面/依赖面闭包、风险度量、根函数补全、溯源完整性、动态调用 |
| 变量/结构体（~4 项） | 变量跳转定义、结构体字段识别、字段读写、注释折叠 |
| 函数预览（~6 项） | 预览弹窗、源码片段、语法高亮、双向定位、预览历史 |
| 健壮性与正确性（~8 项） | `arguments` 块、嵌套函数 body 边界、`end` 索引、写盘健壮性、旧产物清理 |
| 可复现构建（2 项） | 单元（JSON 时间戳）+ 端到端（不同 PYTHONHASHSEED 全产物 MD5 一致） |
| 文档与打包（3 项） | 文档一致性核验、打包链路验收、样本扩充回归 |
| 目录级分析（~13 项） | 文件夹依赖边/循环检测、分层调用图（可点击/耦合度）、目录索引页、双向导航、目录内调用图、概览卡片 |
| 类层次与歧义切换（2 项） | 类继承图（多继承解析/继承图 SVG/类层次页面/导航）、同名函数歧义一键切换 |
| 文档生成器补齐 A1-A4（4 项） | 注释标签聚合、多返回值/可变参数签名、类协作图、注释公式渲染（MathJax） |
| 索引与生态 B1-B2（2 项） | 全局成员索引（members.html）、XML 结构化输出（--xml） |
| 工程加固 C1-C2（1 项） | 性能基准阈值门禁、ext-leak 一键跳转 |
| 复杂索引与跨文件数据流（2 项） | end 关键字上下文消歧、global/persistent 跨文件聚合 + 样本扩充 |
| 静态检查器基础（3 项） | 跨文件字段传递追踪、常量折叠、未初始化变量检测 |
| 静态检查器深化（3 项） | 未初始化降误报、类型推断、死代码检测 |
| 静态检查器精度（3 项） | 跨函数类型流、复杂控制流死代码、类型不一致告警 |
| 静态检查可用性（3 项） | 告警报告化、维度推断深化、未初始化数据流精确化 |
| 静态检查收口（3 项） | 形状检查、多维数组推断、告警阈值配置化 |
| 静态检查可落地（3 项） | 告警抑制注释、增量检查缓存、压力测试 |
| 静态检查成熟度（3 项） | 行级抑制+报告增强、跨文件检查缓存、大规模验证 |
| 性能与健壮性修复（3 项） | 未初始化 O(n²)→O(n)、常量折叠 JSON 安全、序列化兜底 |
| 注释模板增强（2 项） | author/date/version 中英文标签、文件级 header 解析 |
| 引领性收口（3 项） | @param/@return 内联标签、复杂度热力总览、SARIF 门禁 |
| UI 深度改进（1 项） | 暗色主题、文件概览卡片、可折叠目录树、索引分组、导航分组 |
| 跨文件污点分析（1 项） | 源/汇收集、反向传播封顶 5、危险入口判定、SARIF `tainted_sink` 门禁、JSON `taint` 字段 |
| 注释完备度待办清单（1 项） | 三维打分、优先级判定、缺失项清单、JSON `doc_todos` 字段 |
| 多语言后端 C 前端（1 项） | C 函数/调用/include 解析、单行闭合函数、`--lang c` 纯 C 模式、`--mixed` 桥接、JSON `c_model`/`c_bridge` |
| 变量级污点+待办+前端插件化（1 项） | 变量级污点流、`--todo-export` 可执行清单、`BaseFrontend`/`PyFrontend`/`JsFrontend` 语言前端插件化 |
| 参数位门禁+行动单+PY/JS 落地（1 项） | `--taint-param-gate` 参数位门禁、action 状态跟踪、`--lang py/js` 全链路分析 |
| 统一门禁矩阵+字段级污点+分支覆盖（1 项） | MAX_TAINT_DEPTH 修复、`--gate-file`/`--max-warnings-by-rule` 统一门禁矩阵、SARIF 基线自动持久化+零参数 diff、`s.name` 字段级污点（`field_taint`）、`measure_branch_coverage` 分支覆盖度量+`test_coverage` 门禁 |
| 目录树/文件依赖/函数详情页/面包屑/雷达/Doxygen XML（1 项） | P100 `dirs` 目录树模型、P101 `files_graph` 文件依赖图、P103 面包屑、P104 `func_detail.html` 函数详情页（一阶调用图）、P105 源码大纲、P107 全站搜索、P108 响应式/打印、P111 度量雷达、P112 `--export-doxygen-xml` 导出；`--json` 含 `dirs`/`files_graph` |
| 统一图与跨层闭环（1 项） | P200 变量实体化进 `model`、P201 `__CG__` v2 四类节点 + `contain`/`flow` 边（down/up/contain/flow 统一为按 gid 索引的列表）、P202 `unified.html` 统一画布（`UNIFIED_GRAPH_JS` 离线零依赖、类型过滤+搜索+缩放）、P203 `_folder_impact_closure`/`_trace_var_taint_source`/`_gate_by_folder` + `folder_impact.html`/`var_taint.html` + `--gate-max-uninit-folder`/`--gate-max-debt-folder` |

> 所有测试在 `python tests/test_matlabc.py` 一键运行，退出码 0 表示全部通过。

---

## 5. 性能数据

| 场景 | 规模 | 耗时 |
| --- | --- | --- |
| 回归样本（`tests/sample_m`） | 9 文件 / 15 函数 / 8 调用边 / 90 行 | **0.043s** |
| 历史大样本（README 实测） | 300 文件 / 343 函数 / 1437 调用边 | **~0.8s** |

- 传递闭包（影响面/依赖面）已加 `_IMPACT_CACHE` / `_DEPENDENCY_CACHE` 缓存。
- 前端预览/闭包结果已加 `__CG_CLOSURE_CACHE__` 缓存，避免重复计算。

---

## 6. 架构说明

单文件分层结构（详见 `matlabc_STRUCTURE.md`）：

```
[词法层] scrub_source / _logical_statements
    ↓
[解析层] parse_file / parse_function_line / analyze_calls / resolve_call
    ↓
[数据层] MatlabFunction / MatlabClass / MatlabFile
    ↓
[分析层] _impact_layers / _dependency_layers / _trace_roots / _compute_function_metrics
    ↓
[渲染层] render_markdown_report / render_html / render_browse_site / render_json
    ↓
[入口层] main (argparse / config) → 打包 console_scripts
```

- **数据流**：`collect_files` → `parse_file`（结构）→ `analyze_calls`（调用）→ `build_analysis_model`（统一模型）→ 各渲染函数。
- **就近解析规则**：同名被调函数按「同文件 → 同目录 → 其余路径序」解析，歧义通过 `ambiguous_calls` 标记并在预览/报告透明化。

---

## 7. 质量保障

- **静态检查**：`python -W error::SyntaxWarning -m py_compile matlabc.py` 零告警。
- **Lint**：主文件与测试文件均无 lint 错误。
- **可复现性**：不同 `PYTHONHASHSEED` 下两次运行全产物逐字节一致。
- **文档一致性**：`test_p54_docs_consistency` 自动守护 setup.py / README / STRUCTURE 版本同步。
- **打包链路**：`pip install -e .` + `matlabc --version` 实测通过（`test_p55` 自动化守护入口）。

---

## 8. 已知边界与限制（诚实披露）

1. **变量 vs 函数静态歧义**：`x(i)` 的 `x` 若为变量，会被记为「外部调用」，这是 MATLAB 静态分析固有的符号歧义，需人工结合上下文判断。
2. **同名函数就近解析是启发式**：按「同文件 → 同目录 → 其余路径序」，可能不完全符合预期（已通过歧义可视化 + 预览弹窗「点击切换解析目标」缓解，用户可一键跳转到期望的同名实现）。
3. **嵌套函数边界依赖缩进启发式**：`end_style` 判定用「顶格 end」信号，对**完全无缩进**的极端旧式代码可能误判（后果仅为 body 边界偏大，不崩溃不漏函数）。
4. **动态调用常量限制**：`feval(variable)` 等非常量字符串无法静态解析，仅记录为 unresolved。
5. **增量缓存为进程外可选**：`--incremental` 默认关闭，开启后复用未变文件的解析结果（调用分析因全局相关仍全量重做，仅跳过词法清洗 + 结构扫描）。
6. **匿名函数不单独建节点**：`@(x) …` 内的调用归属其外层函数，不生成独立调用图节点。

---

## 9. 未来路线图

| 优先级 | 方向 | 说明 |
| --- | --- | --- |
| ✅ 已完成 | 增量分析缓存（P71） | 基于 mtime+size 签名缓存未变文件，仅重分析变更文件，含命中统计与性能基准 |
| ✅ 已完成 | 歧义切换交互（P80） | 预览弹窗同名候选可点击，一键切换解析目标 |
| ✅ 已完成 | 类继承图（P81） | doxygen 风格 Class Hierarchy：多继承解析 + 父上子下继承图 + 类层次页面 |
| ✅ 已完成 | 注释标签聚合（A1） | `% TODO/BUG/DEPRECATED/FIXME/NOTE` 标签提取 + `annotations.html` 聚合列表页 |
| ✅ 已完成 | 多返回值/可变参数签名（A2） | `[a,b]=foo(x)` 解构 + 返回值流向药丸 + `varargout`/`varargin` 识别 |
| ✅ 已完成 | 类协作图（A3） | 类方法间 uses 关系可视化（实心箭头协作图） |
| ✅ 已完成 | 注释公式渲染（A4） | 注释内 LaTeX 公式经 MathJax 渲染，离线优雅降级 |
| ✅ 已完成 | 全局成员索引（B1） | 类属性/事件/枚举/方法跨文件聚合索引页（`members.html`） |
| ✅ 已完成 | XML 结构化输出（B2） | 与 JSON 同构的 XML（`--xml`），接入 doxygen 生态 |
| ✅ 已完成 | ext-leak 一键跳转（C2） | 疑似漏检调用名点击跳转到同名定义 |
| ✅ 已完成 | 性能门禁（C1） | 300 文件首次解析 30s 绝对阈值，防 O(n²) 退化 |
| ✅ 已完成 | 复杂索引加固（C3） | `end` 关键字上下文消歧 + `switch` 多分支配对锁定 |
| ✅ 已完成 | 跨文件数据流基础（C3） | 函数级 global/persistent 归属 + `global_vars` JSON 索引 |
| ✅ 已完成 | 样本扩充（C3） | 新增 switch/parfor/varargs 三个生产形态样本 |
| ✅ 已完成 | 跨文件字段传递（C3） | 结构体字段跨文件读/写聚合（`field_access`） |
| ✅ 已完成 | 常量折叠（C3） | 命名常量表达式求值（`constants`） |
| ✅ 已完成 | 未初始化检测（C3） | 读前无写局部变量告警（`uninitialized`） |
| ✅ 已完成 | 未初始化降误报（C3） | 排除 global/persistent/函数句柄注入的合法读前无写 |
| ✅ 已完成 | 类型推断基础（C3） | 标量/向量/矩阵/结构体/字符串推断（`types`） |
| ✅ 已完成 | 死代码检测（C3） | return 后不可达 + if 恒假分支（`dead_code`） |
| ✅ 已完成 | 跨函数类型流（C3） | 函数返回值类型 + 调用方解构继承（`type_flow`） |
| ✅ 已完成 | 复杂控制流死代码（C3） | 嵌套块内 return/break/continue 后不可达 |
| ✅ 已完成 | 类型不一致告警（C3） | 矩阵变量被赋标量等（`type_mismatch`） |
| ✅ 已完成 | 告警报告化（C3） | 静态检查汇总页（`checks.html`，按严重度分级） |
| ✅ 已完成 | 维度推断深化（C3） | `zeros(m,n)` 结合常量折叠推断具体维度（`dimensions`） |
| ✅ 已完成 | 未初始化数据流精确化（C3） | 条件分支赋值区分「未初始化」/「可能未初始化」 |
| ✅ 已完成 | 多维数组推断（C3） | `zeros(m,n,k)` 三维及以上维度（`dims`） |
| ✅ 已完成 | 形状检查（C3） | `A*B`/`A+B`/`A-B` 维度约束违规（`shape_mismatch`） |
| ✅ 已完成 | 告警阈值配置（C3） | `--checks` 静态检查开关可配置 |
| ✅ 已完成 | 告警抑制注释（C3） | `% analyzer:ignore` 就地标注抑制告警 |
| ✅ 已完成 | 增量检查缓存（C3） | uninitialized/dead_code 结果随 pickle 缓存复用 |
| ✅ 已完成 | 压力测试（C3） | 30 文件多形态项目 + 60s 性能门禁 |
| ✅ 已完成 | 大规模验证（C3） | 300 文件 + 5 层目录 + 类多继承 + 180s 门禁 |
| ✅ 已完成 | 跨文件检查增量缓存（C3） | field_access/constants 派生数据缓存到 mf |
| ✅ 已完成 | 行级抑制 + 报告增强（C3） | ignore-next-line + 原因标注 + 已抑制数展示 |
| ✅ 已完成 | 跨文件污点分析（P85） | 源/汇收集 + 反向传播封顶 5 + SARIF `tainted_sink` 门禁 |
| ✅ 已完成 | 注释完备度待办清单（P86） | 复杂度×扇入×缺注释三维打分 + `todo.html` |
| ✅ 已完成 | 多语言后端 C 前端（P87） | `--lang c` 纯 C 模式 + `--mixed` MATLAB↔C 桥接 |
| ✅ 已完成 | 变量级污点精确化（P88） | 源赋值→赋值传播→实参→形参映射→汇实参精确命中（`exact` 标志），`fprintf('静态串')` 不误报 |
| ✅ 已完成 | 待办可执行化（P89） | `doc_suggestion`/`test_suggestion` + 受污联动 `joint_priority` + `--todo-export` 行动单 |
| ✅ 已完成 | 语言前端插件化 + 测试生成（P90） | `register_frontend` 注册表、`#include` 跨文件依赖边、`--lang c --checks` 启发式、`--gen-tests` 骨架生成 |
| ✅ 已完成 | 污点参数位门禁 + SARIF 变量级指纹（P91） | `--taint-gate "fprintf:2,system:*"` 参数位级门禁、`exact_sinks` 每实参变量列表 + `param_index`、SARIF 变量级指纹 `var:name:sink:paramIndex`、`taint.html` 汇调用行号→源码跳转 |
| ✅ 已完成 | 行动单执行跟踪（P92） | `% analyzer:done` 抑制标注、`--todo-base` 基线差异（resolved/added/kept + `completion_rate`）、`todo.html` 已处理统计卡 |
| ✅ 已完成 | Python/JS 前端落地 + 分支覆盖提示（P93） | `PyFrontend`/`JsFrontend` 注册、`--lang py/js` 启发式、C 启发式扩展 4 条、`--gen-tests` 分支覆盖 `TODO` 占位 |
| P2 | 真实 MATLAB 工程验证 | 接入真实生产仓库（数千文件、混合编码、巨型文件）验证 |
| ✅ 已完成 | 块级抑制（P214, v1.16.62） | 支持 `% analyzer:disable ... enable` 区间抑制，覆盖块内所有行 |
| ✅ 已完成 | 抑制原因汇总报告（P215, v1.16.63） | checks.html 新增可审计「抑制明细」（文件路径/名称/原因/行区间），防抑制疲劳 |
| ✅ 已完成 | 内置函数工具箱化 + 按模块动态足迹（P216, v1.16.64） | 内置按 MATLAB 工具箱归类，报告新增「按工具箱分布」+ 函数卡片 Toolbox footprint，消除"一个样子" |
| 下一轮 | 见 GAP 文档第十一节 | 三轮新建议（污点参数位门禁、可执行化闭环、前端深化） |

---

## 10. 交付清单

| 文件 | 说明 |
| --- | --- |
| `matlabc.py` | 核心实现（单文件，v1.16.64，约 16,390 行） |
| `tests/test_matlabc.py` | 回归测试矩阵（含 P214 块级抑制） |
| `tests/sample_m/` | 12 文件回归样本（含 3 个生产形态样本） |
| `matlabc_README.md` | 使用文档 + 完整版本历史 |
| `matlabc_STRUCTURE.md` | 代码结构索引（自动生成） |
| `matlabc_JSON_SCHEMA.md` | JSON 输出字段契约 |
| `setup.py` | 打包配置（console_scripts 入口） |
| `analyzer_config.example.json` | 配置文件示例 |
| `matlabc_DELIVERY_REPORT.md` | 本交付报告 |
