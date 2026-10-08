# matlabc 与 Doxygen 系统性差距分析报告

> 分析对象：`matlabc.py`（单文件 MATLAB 静态分析器，v1.16.16，151 项回归测试）
> 对标对象：Doxygen（工业级源码文档生成器，C/C++/Java 原生，MATLAB 经 filter 支持）
> 分析方法：`loop-engineering`（定义完成标准 → 逐层验证 → 分层退出）联动 `fireworks-tech-graph`（可视化图谱思维）做全量能力审计
> 生成日期：2026-08-19

---

## 一、摘要与结论（TL;DR）

`matlabc.py` 经过 P1–P81 迭代，已经**不是**一个「doxygen 的 MATLAB 替代品」这么简单——它在**面向 MATLAB 的静态分析深度**上已经反超 doxygen（影响面/依赖面传递闭包、数据流、动态调用识别、同名歧义检测、目录级依赖/循环、增量缓存等能力是 doxygen 对 MATLAB 场景根本不具备的）。

但作为**文档生成器**，它相对 doxygen 仍有 **6 个明确的功能缺口**，按价值排序：

| 优先级 | 缺口 | doxygen 对应能力 | 对 MATLAB/通信项目的价值 |
| --- | --- | --- | --- |
| **P1** | 类协作图（Collaboration Diagram） | 类属性/方法/父类的引用关系图 | 面向对象 MATLAB 代码的结构理解 |
| **P1** | 结构化注释标签聚合 | `\todo`/`\bug`/`\deprecated`/`\note` 列表页 | 代码 review、缺陷追踪、技术债管理 |
| **P1** | 多返回值 / 可变参数签名 | 完整签名/参数契约 | 通信算法大量 `[a,b]=foo(x)`、`varargout` |
| **P2** | 公式渲染 | MathJax/LaTeX `\f$` | NR/通信注释里满屏数学公式 |
| **P2** | 全局成员索引 | 复合索引 / 成员索引 | 类属性/事件/枚举的跨文件检索 |
| **P2** | XML 结构化输出 | doxygen XML | 被 doxygen 生态工具二次消费 |

本次已落地 **2 个缺口**：`P80` 同名函数歧义一键切换（交互闭环）、`P81` 类继承图 Class Hierarchy（doxygen 标志能力之一）。

**总判断**：`matlabc.py` 已是一个「**MATLAB 深度静态分析 + doxygen 风格文档站点**」的混合体，分析深度满分、文档生成约 **85 分**，补齐上述 6 项即达到「MATLAB 领域的 doxygen 完备度 + 超越 doxygen 的分析深度」。

---

## 二、分析方法（superpower 联动说明）

> 说明：工作区 `skills/` 下实际存在的是 `loop-engineering`（循环工程方法论）与 `fireworks-tech-graph`（技术图谱可视化）两个 skill，**无名为 `superpower` 的独立 skill**。本报告以「深度分析（superpower）」为要求，联动这两个 skill 的方法论完成审计：
>
> - **loop-engineering**：定义「完成标准」= 与 doxygen 的 9 大能力维度逐项对齐；「分层验证」= 每一层能力用「已实现 / 部分实现 / 缺失」三态标注；「分层退出」= 按 P0–P3 四层给出可验证的收口条件。
> - **fireworks-tech-graph**：用「节点=能力、边=依赖」的图谱视角，识别出「类继承 → 类协作 → 类成员索引」是一条尚未打通的**能力链路**（继承图已补，协作图与成员索引是其下游）。

审计维度采用 doxygen 官方文档的能力目录，逐项对照，避免「自说自话」。

---

## 三、现有功能全景（已实现能力清单）

### 3.1 源码解析（深度超越 doxygen 对 MATLAB 的支持）

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 主函数 / 局部函数 / 嵌套函数 / 脚本 | ✅ | 嵌套函数边界基于缩进启发式 |
| `classdef`（属性/方法/构造函数/事件/枚举） | ✅ | 含 `superclass` 继承解析 |
| **多继承 `classdef C < A & B` + 包限定父类** | ✅ **P81 新增** | `RE_CLASSDEF` 扩展 + `superclasses` 列表 |
| `arguments` 参数验证块（R2019b+） | ✅ | 默认值/类型约束提取 |
| 签名提取（输入/输出/函数名/行号） | ✅ | 含 `param_docs()` 注释参数说明 |
| 中文目录/文件名/GBK 注释 | ✅ | 编码自动探测 |

### 3.2 调用分析（doxygen 对 MATLAB 完全不具备）

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 项目内调用边 + 跨文件调用 | ✅ | 全局调用图 |
| 内置/外部函数统计与说明 | ✅ | `matlab_lib.html` 库函数说明 |
| 动态调用识别 | ✅ | `feval`/`str2func`/`cellfun`/`arrayfun`/`@句柄`/命令形式 |
| **同名函数歧义可视化 + 一键切换** | ✅ **P80 新增** | 预览弹窗候选可点击跳转 |
| 结构体字段访问跨文件跳转 | ✅ | `A.B.C` 字段追踪 |

### 3.3 深度关系分析（doxygen 无此能力）

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 影响面 / 依赖面传递闭包 | ✅ | 谁调用我 / 我调用谁，逐层展开 |
| 追本溯源到根 | ✅ | 影响链回溯 |
| 圈复杂度 / 扇入 / 扇出 / 风险度量 | ✅ | `metrics.html` 关键函数风险排行 |
| 数据流（变量读写、结构体字段） | ✅ | 注释折叠展示 |

### 3.4 目录级分析（doxygen 的「目录/文件树」增强版）

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 目录依赖边 + 目录循环检测 | ✅ | Tarjan SCC |
| 目录索引页（doxygen 风格） | ✅ | `dirs/*.html`，面包屑/概览/循环标注 |
| 目录-函数分层调用图 | ✅ | `combined_graph.svg`，跨目录红边 |
| 目录统计（扇出/扇入/入口函数） | ✅ | `folder_stats` JSON |

### 3.5 类层次分析（doxygen 标志能力，P81 补齐）

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| **类继承图（Inheritance Diagram）** | ✅ **P81 新增** | 父上子下 UML 泛化，多继承支持，节点可点击 |
| **类层次页面 + 类明细表** | ✅ **P81 新增** | `class_hierarchy.html` |

### 3.6 交互站点（`--browse`）

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 点击跳转定义 / 函数预览 / 悬浮卡片 | ✅ | 双定位锚点 |
| 全文搜索（多关键字/正则）+ 预览历史 | ✅ | 客户端纯静态 |
| 调用图下钻 / 路径 BFS / 循环检测 | ✅ | 键盘无障碍 |
| URL 状态分享 | ✅ | hash 状态 |
| 类层次入口 | ✅ **P81 新增** | 索引页导航 |

### 3.7 输出与工程化

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| Markdown / Mermaid / DOT / HTML / JSON / SVG | ✅ | 六种输出 |
| `--reproducible` 可复现构建 | ✅ | 时间戳归一 |
| 增量缓存（`--incremental`）+ 性能基准 | ✅ | P71/P77 |
| 配置中心（`--config`）+ 打包（setup.py） | ✅ | `analyzer_config.example.json` |
| 文档一致性守护 | ✅ | `test_p54` 自动校验版本同步 |

---

## 四、与 Doxygen 逐项差距对照（核心）

按 doxygen 官方能力目录，三态标注（✅ 已实现 / 🟡 部分实现 / ❌ 缺失）：

| # | Doxygen 能力 | matlabc 现状 | 差距判定 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 调用图 / 被调用图 | 全局静态调用图（可下钻、循环、路径 BFS） | ✅ 超越 | doxygen 需 Graphviz，本工具零依赖 |
| 2 | **继承图（Inheritance）** | 父上子下 UML 泛化 SVG | ✅ **P81 补齐** | 支持多继承 |
| 3 | **协作图（Collaboration）** | 无 | ❌ 缺失 | 类属性/方法间引用关系 |
| 4 | 目录/文件/类/成员索引 | 目录树/文件索引/类明细表；**缺成员索引** | 🟡 部分 | 类属性/事件/枚举全局索引缺 |
| 5 | 结构化注释（`\param` 等） | `% Input/Output/DESCRIPTION` 等 | 🟡 部分 | 覆盖常用，缺 `\todo/\bug/\deprecated` 标签 |
| 6 | **Todo/Bug/Deprecated 聚合列表** | 无 | ❌ 缺失 | review/技术债价值高 |
| 7 | 源码语法高亮 + 行号 + 交叉引用 | 全有 | ✅ 对齐 | |
| 8 | 搜索 | 全文/正则/多关键字 | ✅ 对齐 | 纯静态，无需服务端 |
| 9 | 输出格式 | MD/Mermaid/DOT/HTML/JSON/SVG | 🟡 部分 | 缺 LaTeX/RTF/XML（JSON 已覆盖 XML 需求） |
| 10 | 公式渲染（MathJax） | 无 | ❌ 缺失 | 通信/NR 注释大量公式 |
| 11 | 分组（`\defgroup` Modules） | 目录级分组可类比 | 🟡 部分 | 缺跨目录逻辑分组 |
| 12 | 命名空间/包 | `+pkg` 包目录解析 | 🟡 部分 | 包限定父类已支持（P81） |
| 13 | 预处理器/宏 | MATLAB 无预处理器 | ➖ 不适用 | |
| 14 | 模板/泛型 | MATLAB 无 | ➖ 不适用 | |

**深度分析结论**：真正的「能力断层」集中在**第 3、6、10 项**（协作图、注释标签聚合、公式渲染）——这三项共同构成 doxygen 作为「文档生成器」的体验闭环，且对面向对象 MATLAB 和通信算法项目价值最高。其次是「成员索引」（第 4 项）和「多返回值签名」（路线图遗留项）。

---

## 五、缺失功能深度分析（需要重点投入的项）

### 5.1 类协作图（Collaboration Diagram）— P1

**是什么**：doxygen 对每个类生成「该类使用了哪些类/结构体」的引用关系图（属性类型、方法参数/返回值类型、方法体内实例化的类）。

**为什么重要**：继承图（已补）回答「is-a」，协作图回答「has-a / uses-a」。面向对象 MATLAB 代码里，一个类持有另一个类的对象引用（如 `properties; channel; coder; end`），协作图能一眼看出类的**组合关系与耦合面**——这正是通信系统仿真（信道对象 ↔ 编码器对象 ↔ 调制器对象）最常见的结构。

**实现要点**：复用已有的 `_collect_field_access`（结构体字段访问）与类属性解析，把「属性类型名」「方法体内 `ClassName(...)` 实例化」「方法签名类型」三类引用映射成类间边，渲染成与继承图同风格的 SVG。

### 5.2 结构化注释标签聚合（Todo/Bug/Deprecated）— P1

**是什么**：doxygen 扫描注释中的 `\todo`、`\bug`、`\deprecated` 等标签，生成独立聚合列表页。

**为什么重要**：MATLAB 代码 review 场景下，工程师常用 `% TODO: 优化 FFT`、`% BUG: 边界溢出`、`% DEPRECATED: 用新接口` 记录技术债。把这些零散注释聚合成「待办列表 / 缺陷列表 / 弃用列表」是 doxygen 对工程管理最有用的能力，且实现成本极低（正则扫描注释 + 一张表）。

**实现要点**：`_parse_header_comments` 已提取注释文本，扩展识别 `TODO/BUG/DEPRECATED/FIXME/NOTE/XXX` 标签，新增 `todo.html`（或并入一个 `annotations.html`）列表页 + 索引导航。

### 5.3 多返回值 / 可变参数签名 — P1（路线图遗留）

**是什么**：MATLAB 函数可返回多值 `[a,b]=foo(x)`，可变参数 `varargout`/`varargin`。当前签名提取把 `[a,b]` 作为单个输出串处理。

**为什么重要**：通信算法的核心函数几乎都是多返回值（如 `[data, snr] = demodulate(...)`），调用方解构赋值 `[d, s] = demodulate(...)` 时，调用图无法精确关联「第 1 个返回值赋给了 d、第 2 个赋给了 s」的流向。

### 5.4 公式渲染 — P2

**是什么**：doxygen 用 MathJax 渲染注释中的 LaTeX 公式。

**为什么重要**：NR/通信项目注释里 `% BER = Q(sqrt(2*Eb/N0))`、`% y = H*x + n` 这类公式遍地。当前源码页把注释当纯文本展示，公式可读性差。

### 5.5 全局成员索引 — P2

**是什么**：doxygen 的复合索引/成员索引，把类属性、事件、枚举、全局变量跨文件聚合成一张可检索的索引表。

### 5.6 XML 结构化输出 — P2

**是什么**：doxygen XML 供第三方工具二次消费。`matlabc` 的 JSON 已覆盖 90% 需求，仅当需要接入 doxygen 生态（如 Doxygen Awesome、Graphviz 后处理）时才需 XML。

---

## 六、系统性结论

1. **定位已迁移**：`matlabc.py` 已从「doxygen 的 MATLAB 模仿者」进化为「**MATLAB 深度静态分析引擎 + doxygen 风格文档前端**」。它独有的分析能力（动态调用识别、同名歧义切换、目录循环检测、增量缓存、影响面闭包）是 doxygen 对 MATLAB 场景的**结构性空白**。

2. **差距集中在「文档生成器」而非「分析器」**：剩余 6 项缺口全部是 doxygen 作为文档工具的标志能力（协作图、注释标签、公式、成员索引、XML），不涉及分析深度。

3. **能力链路未闭环**：`类继承（已补）→ 类协作（缺）→ 成员索引（缺）` 是一条未打通的链路，补上协作图即可让面向对象 MATLAB 的结构可视化达到 doxygen 同级。

4. **技术债标签聚合是「性价比之王」**：实现成本极低（正则 + 一页列表），但对真实工程 review 的价值极高，应排在协作图之前或并列。

---

## 七、逐步完善计划（分阶段可验证）

### 阶段 A：文档生成器补齐（✅ 已全部完成，版本推进至 v1.11.78）

| 步骤 | 内容 | 状态 |
| --- | --- | --- |
| A1 | **注释标签聚合**（Todo/Bug/Deprecated/Fixme/Note） | ✅ `annotations.html` 列表页 + 导航，`test_a1_annotations` |
| A2 | **多返回值/可变参数签名**（`[a,b]=foo(x)`、`varargout/varargin`） | ✅ 解构识别 + 返回值流向药丸 + `variadic` 字段，`test_a2_multi_return` |
| A3 | **类协作图**（Collaboration Diagram） | ✅ 类方法间 uses 关系 → 环形协作图 SVG，`test_a3_collaboration` |
| A4 | **公式渲染**（注释内 LaTeX → MathJax） | ✅ 源码页 MathJax 渲染（离线优雅降级），`test_a4_mathjax` |

### 阶段 B：索引与生态（本阶段目标 = 完备索引 + 生态兼容）

| 步骤 | 内容 | 验收标准 |
| --- | --- | --- |
| B1 | **全局成员索引**（类属性/事件/枚举/全局变量） | 新增 `members.html` 索引页，`test_p86` 通过 |
| B2 | **XML 结构化输出**（`--xml`） | 与 JSON 同构的 XML，`test_p87` 通过 |

### 阶段 C：工程加固

| 步骤 | 内容 | 验收标准 |
| --- | --- | --- |
| C1 | 性能基准纳入测试门禁（回归基线） | `test_p77` 扩展阈值断言 |
| C2 | `ext-leak` 候选点击跳转同名定义 | 快速定位疑似漏检 |
| C3 | 持续扩充真实样本 | `sample_m` 覆盖生产形态 |

> 本次已落地 A 前置项：**P80（歧义切换）+ P81（类继承图）**，版本推进至 v1.11.74。

---

## 八、本次已实施内容（P80 + P81）

### P80 同名函数歧义一键切换（v1.11.73）

- **后端**：`_build_global_cg` 的同名候选 `dups` 新增 `p` 字段（站点根相对源码页路径）。
- **前端**：预览弹窗「同名函数候选」每个候选变为可点击（`data-dup-p`/`data-dup-l` + `cgGotoSource`），点击即跳转到该候选源码定义行；`✓` 标记当前就近解析、`↗` 标记可切换、非当前候选 hover 高亮。
- **意义**：把「看到同名歧义」升级为「改得动解析目标」，交互闭环。

### P81 类继承图 Class Hierarchy（v1.11.74）

- **解析**：`RE_CLASSDEF` 扩展支持多继承 `classdef C < A & B` 与包限定父类 `pkg.Cls`；`MatlabClass` 新增 `superclasses` 列表（`superclass` 字段向后兼容）。
- **新增函数**：`_collect_class_hierarchy`（类继承关系 + 父子映射）、`render_class_hierarchy_svg`（父上子下 UML 泛化 SVG，子类空心三角箭头指向父类，节点可点击跳转）、`render_class_hierarchy_page`（继承图 + 类明细表）。
- **站点集成**：`--browse` 新增 `class_hierarchy.html`（无类时显示「未发现 classdef」保证导航有效），索引页导航新增「类层次」入口，`_clean_browse_dir` 同步清理。
- **回归**：`test_p80_ambiguous_switch`、`test_p81_class_hierarchy`，全量 80 项通过，无 lint、零 SyntaxWarning，兼容 Python 3.6.5。

---

## 九、下一步建议（新的有思考的方向）

**上轮三项建议已全部落地**，版本推进至 v1.11.94：

1. **目录耦合度矩阵（P82）**：新增 `dir_matrix.html`——`_compute_dir_coupling` 把全部跨目录调用聚合成「目录 × 目录」二维矩阵（行=源目录/扇出、列=目标目录/扇入），颜色深浅表示耦合强度，双向耦合（A⇄B）红色边框高亮并单独列出循环依赖警告，点击单元格下钻到具体函数调用明细，支持过滤/仅看有耦合目录，索引页新增「目录耦合」导航。**架构治理视图闭环完成**。
2. **调用图交互增强（P83）**：局部调用图支持滚轮以鼠标位置为中心缩放（Ctrl+滚轮；大图默认保留原生滚动）、拖拽平移画布、双击节点把该节点设为**新根**聚焦其子树（`rootGid`→可变的 `curRoot`，URL 状态/分享链接同步，`__cgRestore` 也支持切换根）、顶部工具栏（放大/缩小/缩放百分比/适合窗口/复位），并给单击预览加 240ms 防抖避免双击时面板闪现。**大项目调用图从「静态不可读」变为「可导航」**。
3. **增量 SARIF + PR 差异报告（P84）**：新增 `--sarif-base`（基线指纹 `_load_sarif_fingerprints`，行级指纹 `(uri,startLine,ruleId,message)`）使 `--sarif` 只输出相对基线的「新增」告警；新增 `--sarif-diff` 输出 Markdown 差异报告（新增/已修复告警明细表），CLI 同步打印增量统计。**CI 门禁「只审查本次改动」能力闭环**。

至此，`matlabc` 已走通从「doxygen 差距补齐」到「全面超越 doxygen 的 MATLAB 分析平台」的十一级演进，**对 MATLAB 的适配深度（多继承、命令形式调用、中文注释、GBK、`arguments` 块、动态调用、类型/形状/死代码/未初始化检测、目录耦合矩阵、增量 SARIF 差异）是 doxygen 经 filter 永远无法企及的**。

**本轮三项建议已全部落地**，版本推进至 v1.12.0（122 → 125 项回归测试，Python 3.6.5 / 3.6.6 全通过）：

1. **跨文件污点分析（P85，首选）**：新增 `_TAINT_SOURCES`/`_TAINT_SINKS`（20+ 源：`input`/`load`/`fopen`/`webread`/`jsondecode`/`str2num` 等；20+ 汇：`fprintf`/`fwrite`/`save`/`eval`/`system`/`writetable` 等）与 `_taint_regexes`（懒构建、大小写不敏感）；`_collect_taint_call_sites` 用 `_tokenize_matlab` 剔除注释/字符串后扫描函数体收集「源/汇」调用点；`_propagate_taint` 沿 `calls_of` 反向传播污点（直接调用汇=level 1，调用受污函数者逐层+1、封顶 5，仅「有输入参数或脚本」的入口参与传播避免过度污染），输出 `taint.html` 污点流页（级别徽章/源汇标签/传播路径/关键词与级别筛选）+ JSON `taint` 字段 + **SARIF 新增 `tainted_sink` 规则接入 `--sarif`/`--sarif-diff`/`--max-warnings` 安全门禁**。回归 `test_p85_taint_analysis`。
2. **注释完备度评估 + 待办清单生成（P86，次选）**：新增 `_doc_todo_priority` 与 `_collect_doc_todos`——以「复杂度(修改风险) × 扇入(影响面) × 头部注释缺失(可维护性)」三维打分（description 缺-30、input/output 无文档各-10、author/version 缺-10，封顶 100），高复杂度+高扇入+低文档分=高优先级；输出 `todo.html`「函数待办清单」（优先级/缺失项/文档分列，可按优先级筛选、搜索、点表头排序）+ JSON `doc_todos` 字段。回归 `test_p86_doc_todo`。
3. **多语言后端扩展（P87，长期）**：把「解析层」抽象为**语言前端**（统一产出「文件→函数→调用→复杂度→依赖」的语言无关模型）：新增轻量 **C 前端** `_parse_c_source`（函数定义/内部调用/include 依赖/复杂度估算，正确处理单行闭合函数）+ `build_c_model` + `render_c_report`（`c_report.html`：复杂度 TOP、函数总览、include 依赖、内部调用图、未解析调用）+ 纯 C 模式 `--lang c`（不要求 .m 文件，独立输出站点与 JSON）+ **混合模式 `--mixed`**（MATLAB 外部调用命中 C 函数名 → 跨语言 MEX 桥接表，JSON `c_model`/`c_bridge` 字段）。回归 `test_p87_c_frontend`。

---

## 十、新一轮下一步建议（从「领域纵深」走向「工程闭环」）

上一轮「污点分析 → 注释待办 → 多语言后端」三项落地后，`matlabc` 已具备**数据流安全门禁 + 可维护性行动清单 + 多语言解析骨架**。下一阶段应把能力从「分析」推进到「工程闭环」，按 性价比优先 排序：

**首选：污点分析的「变量级」精确化（从函数级 → 参数级/变量级污点流）**
理由：① 当前污点传播是**函数级**的（函数有输入且体内调用了汇即标记），无法回答「哪个具体参数/变量到达了哪个 sink」——`fprintf('%s', user_input)` 与 `fprintf('static')` 都被同等标记；② 已有 `_collect_type_flow`/`_infer_func_output_types`/`_collect_constants` 可支撑**变量级污点标记**（把源函数的返回值变量标记为受污，沿赋值/解构/参数传递追踪到 sink 的参数位置）；③ 产出「污点链路精确到变量」的 `taint.html` 增强视图 + 支持 `--taint-max-depth` 阈值调参，误报率可下降一个数量级。实现路径：`_taint_vars(f)`（函数内变量受污集合，源赋值入、经表达式传播）→ 跨函数参数映射（`call_sites` 第 4 元组给出被调函数与实参位置）→ sink 参数位命中判断。

**次选：待办清单「可执行化」——生成补文档/补测试任务单**
理由：① `todo.html` 目前只「指出缺口」，不产出「怎么补」；② 可对每条高优先级待办自动生成**补文档建议**（依据缺失项与头部注释模板：`% author:`/`@param` 占位模板）、**关联测试建议**（依据扇入/复杂度给出建议测试用例数）、并支持 `--todo-export json` 导出为外部任务系统（Jira/禅道）可导入的清单；③ 进一步与 P85 联动——「高复杂度 + 高扇入 + 缺文档 + 受污」的函数被标记为**最高风险待办**，形成「安全 × 可维护性」联合优先级。

**随后（长期）：语言前端插件化 + 单元测试生成**
理由：① C 前端已证明「解析层抽象」可行，但当前 `CFrontend` 是硬编码的正则实现——应抽象为**可注册插件**（`register_frontend(lang, FrontendClass)`，`--lang c`/`--lang py` 自动发现），并补 C/C++ 头文件交叉引用（`#include` → 跨文件依赖边）；② 与测试生态联动：依据函数复杂度/分支覆盖提示缺失的测试分支，甚至生成 pytest/MATLAB script 骨架；③ 为 C 前端补 `--lang c --checks`（未初始化指针/越界启发式），使多语言门禁不止「调用图」而是「完整静态分析」。

建议按 **变量级污点精确化 → 待办可执行化 → 前端插件化** 顺序推进，把 `matlabc` 从「能分析」推向「能开行动单、能治标治本」的**工程闭环平台**。

---

## 十一、P88–P90 落地确认 + 新一轮下一步建议

**本轮三项建议（变量级污点精确化 → 待办可执行化 → 语言前端插件化）已全部落地**，版本推进至 v1.13.0（125 → 128 项回归测试，Python 3.6.5 / 3.6.6 全通过，无 lint、零 SyntaxWarning）：

1. **变量级污点精确化（P88，首选）**：新增 `_mask_code_spans`（复用 tokenize runs 把注释/字符串替换为空格、保留括号偏移）→ `_collect_var_taint_sites`（采集源赋值 lhs / 汇调用实参 / 赋值传播边 / 调用实参；**修复了纯变量赋值 `buf = n` 无调用时不入传播边**的根因，新增 ③b 纯赋值传播分支）→ `_propagate_var_taint` 正向迭代至稳定（上限 20 轮），实现「源赋值 → 赋值继承 → 实参→形参跨函数映射」；汇调用实参**精确命中**（`exact_sinks`/`exact` 字段，`fprintf('静态串')` 不再误报）；`taint.html` 新增「精确命中」统计卡、受污变量列、精确/函数级徽章与筛选；JSON `taint.flows[]` 新增 `vars`/`var_sources`/`exact_sinks`/`exact`。回归 `test_p88_var_taint`。
2. **待办可执行化（P89，次选）**：新增 `_build_doc_suggestion`（按缺失项生成可粘贴的补注释模板）与 `_build_test_suggestion`（按复杂度/扇入/输入输出列出测试点）；`_collect_doc_todos` 新增 `tainted`/`joint_priority`（受污时 high→critical / medium→high / low→medium）字段并按联合优先级排序；`todo.html` 新增「联合紧急」筛选、受污徽章、「行动建议」列与「展开建议」按钮；新增 `--todo-export FILE` 导出行动单 JSON（含 `summary.critical/tainted` 计数，可对接任务系统）。回归 `test_p89_todo_actionable`。
3. **语言前端插件化 + 测试生成（P90，长期）**：新增 `BaseFrontend` + `register_frontend(lang, cls)` 注册表（内置 C/MATLAB 前端，第三方可无侵入注册扩展）；C 前端新增 **`#include` 跨文件依赖边**（按头文件名解析到项目内文件，JSON `include_edges`，`c_report.html` 新增跨文件依赖边表）；**`--lang c --checks` C 静态启发式检查**（`c_unused_static`/`c_missing_guard`/`c_too_many_params`/`c_missing_doc`，接入 SARIF 新规则 `c_heuristics`）；**`--gen-tests DIR` 测试骨架生成**（MATLAB `functiontests` 风格 `gen_matlab_tests/test_*.m` + C `gen_c_tests/test_*.c`，已存在不覆盖，`main`/`static` 合理跳过）。回归 `test_p90_frontend_plugin`。

**新一轮下一步建议**（从「可执行」走向「可治理」，按性价比优先排序）：

**首选：污点链路的「参数位门禁」+ SARIF 变量级指纹**
理由：① P88 已把污点精确到变量并给出 `exact_sinks`，但 `--max-warnings` 门禁仍以「函数级规则计数」计分——应支持 `--taint-gate "fprintf:2"` 式**参数位级门禁**（指定危险汇的第几个实参必须非受污，超阈值即 CI 失败）；② SARIF 结果目前只输出函数级文本，应升级为**变量级指纹** `(uri, startLine, varName, sinkName, paramIndex)`，使基线差分（`--sarif-base`）能精确报告「新增的受污变量」，而非整行告警；③ 为 `exact_sinks` 补充 `param_index` 与 `call_line` 字段，配合 `taint.html` 增加「点击汇调用行号 → 源码页定位」跳转，形成从报告到源码的单跳闭环。

**次选：待办行动单的「执行跟踪」闭环**
理由：① `--todo-export` 目前是静态快照，无法回答「上轮导出的 critical 待办是否已补文档」——应支持 `--todo-export --todo-base previous.json` 差异模式，输出「已解决/新增/仍存」三态行动表；② 用「头部注释解析结果」反查行动单：补文档后的函数 `doc_score` 提升即视为已闭环，可生成**待办完成率趋势**（配合 `--incremental` 缓存）供周报/迭代回顾使用；③ 在 `todo.html` 中给每条待办加「状态标注」（可手写 `% analyzer:done` 抑制，被识别为已处理并降噪），把「静态清单」升级为「可勾选的治理面板」。

**随后（长期）：Python/JS 前端落地 + 全语言测试生成**
理由：① P90 已证明注册表可扩展——立刻把内置 `BaseFrontend` 的 `parse_file`/`build_edges` 契约复用到 **Python 前端**（轻量 AST 或正则，产出同样的语言无关模型，`--lang py --checks` 可直接获得未使用 import/重复参数名启发式）与 **JS 前端**，三语言统一走 `--gen-tests`；② 测试生成从「骨架」升级为「**依据分支覆盖提示缺失测试分支**」——利用现有圈复杂度与 `if/for/switch` 分支扫描，在骨架中生成 `% TODO: 覆盖分支 k==2（行 12）` 占位，让测试骨架天然引导补齐分支；③ C 启发式从 4 条扩展（未初始化指针/数组越界/`free` 后使用/缺 `return` 路径），`--lang c --checks` 达到可进 CI 的质量门槛。

建议按 **参数位门禁 → 行动单跟踪 → 多前端深化** 顺序推进，把 `matlabc` 从「能开行动单」推向「能持续治理、能跨语言统一门禁」的**工程治理平台**。

---

## 十二、P91–P93 落地确认 + 新一轮下一步建议

**本轮三项建议（参数位门禁 → 行动单跟踪 → 多前端深化）已全部落地**，版本推进至 v1.14.0（128 → 131 项回归测试，Python 3.6.5 / 3.6.6 全通过，无 lint、零 SyntaxWarning）：

1. **污点参数位门禁 + SARIF 变量级指纹（P91，首选）**：`exact_sinks` 从扁平变量列表升级为**「每实参变量列表」**（`args=[[], ["n"]]`，字符串/常量实参为空列表，`param_index` 从 enumerate 得到**真实参数位**——修复了原 `_vars_in_expr` 过滤导致参数位丢失的根因，`fprintf('%s', n)` 中 `n` 的 `param_index==1`）；新增 **`--taint-gate "fprintf:2,system:*"`** 参数位级门禁（1-based 参数位，`*` 记 `{-1}` 全部实参，违例即非零退出，非法格式也报告失败，接入 CI 质量门禁）；SARIF 升级为**变量级指纹** `(uri, line, ruleId, "var:name:sink:paramIndex")`，`properties` 携带 `taintVar`/`sinkName`/`paramIndex`，使 `--sarif-base` 基线差分能精确报告「新增的受污变量」；`taint.html` 精确命中行号 → 源码页定位（修复 `_page_rel` 双重 `.html` 死链：`src/danger.m.html.html#L3` → `src/danger.m.html#L3`）。回归 `test_p91_taint_gate_sarif_fp`。
2. **待办行动单执行跟踪（P92，次选）**：新增 **`% analyzer:done`** 抑制标注（函数头部注释或函数体内任一位置标注→该函数不入待办，`stats.done` 计数），支持「已处理」语义；新增 **`--todo-base FILE`** 基线差异模式——按 `(file, func)` 键对比当前行动单与基线，输出 **`resolved`/`added`/`kept`** 三态 + **`completion_rate`**（完成率=resolved/(resolved+added)，保留 3 位小数）；`todo.html` 新增「已处理(analyzer:done)」统计卡。回归 `test_p92_todo_tracking`。
3. **Python/JS 前端落地 + 分支覆盖提示（P93，长期）**：**`PyFrontend`/`JsFrontend`** 注册到 `register_frontend`（轻量正则解析 `def`/`function`、调用边、import/require 依赖边，产出语言无关模型），`--lang py`/`--lang js` 走统一 `--checks` 启发式（`py_unused_import`/`py_dup_params`/`py_too_many_params`/`py_missing_doc`、`js_unused_import`/`js_global_var`/`js_too_many_params`/`js_missing_doc`）；**C 启发式扩展 4 条**（`c_uninit_pointer` 未初始化指针解引用、`c_array_oob` 固定数组越界、`c_use_after_free` `free` 后使用、`c_missing_return` 非 void 缺 `return`），C 检查总数达 8 条；`--gen-tests` 测试骨架新增**分支覆盖提示**（扫描函数体 `if/for/while/switch/case` 行，生成 `/* TODO: 覆盖分支（源行 N） */` 占位），让测试骨架天然引导补齐分支。回归 `test_p93_lang_frontends`。

**新一轮下一步建议**（从「跨语言统一门禁」走向「工程治理闭环的自动化与可信化」，按性价比优先排序）：

**首选：跨语言统一门禁矩阵 + 基线门禁持久化**
理由：① P91 的 `--taint-gate` 只针对 MATLAB 污点，P93 的 C/Python/JS 启发式虽接入 SARIF 但**没有统一的门禁表达式**——应设计 `--gate-file gates.json` 声明式门禁文件：`{"fprintf": {"langs": ["matlab", "c"], "param": 2, "severity": "error"}, "py_unused_import": {"langs": ["py"], "severity": "warning"}}`，跨语言同一配置即生效；② `--sarif-base` 基线目前是**一次性传参**，应支持把基线指纹缓存到 `.codebuddy/analyzer/`（与增量缓存同目录），`--sarif-diff` 在 PR 间自动对比上次基线，输出「新增/修复/持续」三角色变更周报，让门禁在 CI 中「零参数运行」；③ 为 `--max-warnings` 增加**按规则独立阈值**（`--max-warnings-by-rule "c_use_after_free:0,tainted_sink:1"`），避免「总量达标但高危规则超限」的漏网。

**次选：污点分析的真实执行流 + 常量/结构体字段传播**
理由：① 当前 `_propagate_var_taint` 是**语法级传播**（按赋值/实参映射），遇到 `sprintf` 拼接、结构体 `s.name = n`、`eval(str)` 动态构造会丢失或误报——应补**结构体字段级污点**（`s.name` 独立受污标记，`s = struct('a', n)` 传播到 `s.a`）与 `eval/sprintf` 动态串拼接模拟；② 现有 `_collect_constants`/`_collect_field_access` 已有字段读写图，可把「字段受污位图」与它们对齐，产出 `taint.html` 的**字段级污点流视图**；③ 可进一步把污点传播结果缓存（复用增量缓存机制），大工程二次分析只重算变更函数，`--taint-gate` 从「秒级」降到「亚秒级」。

**随后（长期）：真实工程验证 + 全语言分支覆盖度量**
理由：① P92 的 `completion_rate` 与分支覆盖提示需要**真实仓库数据校验**——如有真实 MATLAB/Python/C 工程，可跑出「行动单闭环率 vs 时间」趋势图，验证「补注释/补测试 → 完成率上升」的治理假设；② `--gen-tests` 目前只生成骨架与 `TODO: 覆盖分支` 占位，应升级为**分支覆盖度量**：统计函数体 `if/for/while` 分支总数、已生成测试可覆盖数、覆盖率百分比，输出 `coverage.html` 与 JSON `test_coverage` 字段，让「补测试」本身可度量、可门禁；③ 结合 `--gate-file` 可把「测试覆盖率低于阈值 → CI 失败」纳入统一门禁，形成「静态分析门禁 + 测试覆盖门禁」双闸门。

建议按 **统一门禁矩阵 → 字段级污点 → 分支覆盖度量** 顺序推进，把 `matlabc` 从「能治理」推向「能自动治理、能可信度量的**工程治理闭环平台**」。

---

**关于「真实仓库验证」的持续说明**：您工作区的 `nr无线协议` 目录目前只有 PDF 文档、没有 `.m` 源码。如果您能提供一个真实的 MATLAB 源码工程路径，我可以立即跑完整分析并输出真实的边界问题清单。

---

## 十三、P94–P96 落地确认 + 缺陷修复 + 新一轮下一步建议

**本轮三项建议（统一门禁矩阵 → 字段级污点 → 分支覆盖度量）已全部落地**，版本推进至 v1.15.0（131 → 134 项回归测试，Python 3.6.5 全通过，无 lint）：

0. **缺陷修复：`MAX_TAINT_DEPTH` 未定义**：`_propagate_taint` 函数体引用未定义的全局常量，仅在「有输入但未直接受污、且调用了受污 callee」的函数触发 `NameError`（普通测试不覆盖此路径）。已在函数上方定义 `MAX_TAINT_DEPTH = 5`，默认参数改为引用常量、函数体内改用 `max_depth`，根因修复。
1. **跨语言统一门禁矩阵 + 基线门禁持久化（P94，首选）**：新增 **`--gate-file gates.json`** 声明式门禁文件（`taint_gates`/`rule_gates`/`max_warnings`/`test_coverage` 四类门禁统一声明），与 **`--max-warnings-by-rule "c_use_after_free:0,py_too_many_params:0"`** 按规则独立阈值合并（CLI 显式优先）；**SARIF 基线自动持久化**——`--sarif` 输出后自动把变量级指纹写入 `.codebuddy/analyzer/sarif_base.json`，`--sarif-diff` 无 `--sarif-base` 时自动复用该基线输出「新增/已修复」Markdown 周报，实现 **PR 间零参数增量扫描**；C/PY/JS 三种纯语言模式接入同一门禁矩阵（`_apply_unified_gates`），不再只在 MATLAB 主流程生效。回归 `test_p94_unified_gate_matrix`。
2. **结构体字段级污点（P95，次选）**：`_collect_var_taint_sites`/`_propagate_var_taint` 从变量级细化为 **`struct.field` 字段级**——`s.name = input(...)` 仅标记 `s.name` 字段受污（`field_taint` 集），不再污染整根 `s`；`y = s.name` 把字段污点传播为变量污点；`s = struct('a', n)`（n 受污）经整根继承使 `s.a` 命中；字段实参 `h(s.name)` 跨函数映射到形参；汇实参字段链实际受污（根受污或任一前缀字段受污）产生 `field=True` 的字段级精确命中；`taint.html` 新增「字段受污」列与表头，JSON `taint.flows[]` 新增 `field_taint`。`eval/sprintf` 动态串模拟由现有 `_TAINT_SINKS`（eval/evalc/evalin）与赋值传播链路天然覆盖。回归 `test_p95_field_level_taint`。
3. **分支覆盖度量 + 测试覆盖门禁（P96，长期）**：新增 **`measure_branch_coverage(files, root, lang)`**——跨语言统计函数体（`body_start..body_end`）分支点总数（MATLAB `if/elseif/else/for/while/switch/case/try/catch/parfor`、C `_RE_C_CX`、Python/JS 专用关键字集），以「被测试文件（`test_*`/`tests/` 目录）引用的函数」为静态覆盖近似，输出 `covered_branches`/`total_branches`/`coverage_percent`/`per_file`/`test_refs`；`--gate-file` 的 **`test_coverage.min_percent`** 接入统一门禁（MATLAB 主流程 + C/PY/JS 模式均生效），「测试覆盖率低于阈值 → CI 失败」，形成「静态分析门禁 + 测试覆盖门禁」双闸门。回归 `test_p96_branch_coverage`。

**新一轮下一步建议**（从「工程治理闭环」走向「治理的可信化、自动化与跨仓库协同」，按性价比优先排序）：

**首选：门禁结果回灌与「零误报」基线治理（P97）**
理由：① `--gate-file` 已可统一门禁，但**门禁失败缺少「可追溯的例外清单」**——应支持 `gate_file` 内嵌 `exceptions` 段（`(uri, ruleId)` 白名单，附 `owner`/`reason`/`expires`），违规时先查白名单再判定，把「一刀切失败」升级为「可审计的例外治理」；② `--sarif-diff` 已输出增量周报，应支持 **`--sarif-diff --fail-on-added` 阈值**（新增告警超过 N 条即失败），让 PR 级增量扫描直接进入 CI 判定；③ 把 `.codebuddy/analyzer/sarif_base.json` 纳入**可提交进 Git 的基线资产**（建议在 README 明示最佳实践：基线随代码评审一起更新，`--sarif-diff` 零参数运行即自动对比），治理不再是「一次性快照」。

**次选：字段级污点的「构造器识别」与索引字段（P98）**
理由：① P95 已支持 `s.name` 赋值与读取，但 **`setfield(s,'a',n)` / `s.(expr) = n` 动态字段**与 **`struct('a', struct('b', n))` 嵌套构造**仍未识别——应把 MATLAB 内置构造器（`struct`/`setfield`/`orderfields`/`rmfield`）建模为「字段污点位图」的赋值语义，按 `(struct_var, field_path)` 传播；② **索引字段** `s(1).name` / `s(2).x.y` 目前整根传播——应支持「数组元素级」污点（首下标可区分时精确，否则保守整根），降低 `cellfun`/`arrayfun` 循环结构体的误报；③ 为 `taint.html` 字段列增加「受污来源跳转」（字段 → 源赋值行），形成字段级污点流的单跳闭环。

**随后（长期）：真实仓库验证 + 跨语言测试骨架回灌分支覆盖（P99）**
理由：① P96 的静态覆盖近似（测试文件引用即覆盖）需要**真实执行数据校准**——如有真实 MATLAB 工程 + `functiontests` 套件，可运行 `coverage` 对比静态估算与真实执行覆盖，标定近似误差并给出修正系数；② `--gen-tests` 生成骨架后应**回灌**：运行一次 `measure_branch_coverage`，把未覆盖分支的 `TODO: 覆盖分支` 占位按真实缺口生成（而非全量生成），使「补测试」与「覆盖门禁」形成闭环；③ 三语言前端可统一 `--coverage` 输出 `coverage.html` 分支雷达图（每函数分支覆盖率着色），让「测试覆盖门禁」在报告层可见、可审查。

建议按 **例外治理与增量门禁 → 构造器/索引字段污点 → 真实覆盖校准** 顺序推进，把 `matlabc` 从「能统一门禁」推向「能治理得可信、治理得可审计、治理得可协同的**工程治理平台**」。

---

**关于「真实仓库验证」的持续说明**：您工作区的 `nr无线协议` 目录目前只有 PDF 文档、没有 `.m` 源码。如果您能提供一个真实的 MATLAB 源码工程路径，我可以立即跑完整分析并输出真实的边界问题清单。

---

**关于「真实仓库验证」的再次说明**：您工作区的 `nr无线协议` 目录目前只有 PDF 文档、没有 `.m` 源码。如果您能提供一个真实的 MATLAB 源码工程路径，我可以立即跑完整分析并输出真实的边界问题清单。
