# matlabc 特性说明（v1.16.62）

> 纯 Python、零第三方依赖的 MATLAB / C / Python / JavaScript 代码结构梳理、静态分析与质量门禁工具。
> 无需安装 MATLAB，无需联网（默认离线优先），可在 Windows / macOS / Linux 上运行。
> 本文件描述**当前版本（v1.16.62）**已落地的能力；使用方式与参数见配套 [`matlabc_USAGE.md`](matlabc_USAGE.md)。

---

## 1. 一句话定位

把"看代码"升级为"工作台"：不仅梳理调用关系，还直接告诉你**哪里有隐患、属于哪一级严重度、怎么改、能否一键生成修复/测试/PR**；并把所有结论接入 **CI 质量门禁**（SARIF / 退出码 / 趋势基线）。

---

## 2. 支持的语言

| 语言 | 前端 | 关键能力 |
| --- | --- | --- |
| MATLAB（默认） | 内置 | 函数 / 类 / 脚本 / 嵌套函数 / `arguments` 块 / 结构体字段 / 全局状态全量解析 |
| C（`--lang c`） | C 前端（P87） | 函数 / 调用 / `#include` 跨文件依赖边、启发式静态检查 |
| Python（`--lang py`） | Py 前端（P93） | 函数 / 调用 / 静态检查，含 **Python 3.6 语法兼容门禁**（`--check-py36`） |
| JavaScript（`--lang js`） | JS 前端（P93） | 函数 / 调用 / 静态检查 |
| 混合（`--mixed`） | MATLAB + C | MATLAB↔C 跨语言 MEX 桥接（P87） |

---

## 3. 能力矩阵

### 3.1 代码结构与调用关系
- **目录结构树**：递归扫描全部 `.m` / `.c` / `.py` / `.js`，按目录树展示。
- **语法解析**：`function` / `classdef` / 局部函数 / 嵌套函数 / 脚本 / 主函数 / 类方法 / 构造函数 / `arguments` 参数验证块。
- **签名提取**：输入/输出参数（含多返回值 `[a,b]` 解构、`varargin`/`varargout`）、函数名、所在文件与行号。
- **调用分析**：项目内调用边 + 跨文件调用 + 内置/外部函数统计 + 动态调用（`feval`/`str2func`/字符串回调）+ 函数句柄。
- **深度关系**：影响面 / 依赖面传递闭包、追本溯源到根、关键函数风险度量（圈复杂度 / 扇出 / 扇入）、同名函数歧义可视化与一键切换。
- **类层次**：类继承图（支持多继承 `A & B` 与包限定父类）、类协作图（uses 关系）、全局成员索引（属性 / 事件 / 枚举 / 方法）。

### 3.2 交互式浏览站点（`--browse`）
- 点击跳转定义、函数预览弹窗、全文搜索（多关键字 / 正则）、预览历史、调用图下钻。
- **守护模式（`--watch`）**：文件变更（内容 SHA-256 签名）自动重分析并重生成站点，配套 `watch.html`（纯轮询、零 WebSocket、离线可用）。
- **离线优先（`--offline`）**：产物不含任何外部 CDN 引用，纯内网零外网请求；公式与 Mermaid 图回退为静态源码展示。
- **大仓保护（`--max-nodes`）**：统一调用图 `__CG__` 节点数硬上限，超出按"文件夹→文件→函数→变量"优先级截断，保证 300+ 文件仓库仍可打开。

### 3.3 静态检查（C3 四类 + 跨语言）
| 检查 | 说明 |
| --- | --- |
| `uninitialized` | 读前无写局部变量（排除 global/persistent/函数句柄注入；区分"未初始化 / 可能未初始化"，高置信才卡 CI） |
| `type_mismatch` | 同一变量类型不一致（矩阵变量被赋标量等；scalar↔vector 视为兼容） |
| `dead_code` | return 后不可达 + if 恒假分支（含嵌套块内 return/break/continue 后不可达） |
| `shape_mismatch` | `A*B` / `A+B` / `A-B` 维度约束违规 |
| 跨语言检查 | C 未用 static、缺头文件守卫、悬空指针、数组越界、use-after-free、缺返回值；Py 未用 import、重复参数、参数过多、缺文档；JS 未用 import、全局变量、参数过多、缺文档 |

### 3.4 告警抑制（C3，四档粒度）
> 就地标注，不改业务语义，仅让分析器对该处"睁只眼闭只眼"。

| 档位 | 语法 | 作用域 |
| --- | --- | --- |
| 文件级 | `% analyzer:ignore <check>` | 该文件所有 `<check>` |
| 名称级 | `% analyzer:ignore <check> <name> [-- 原因]` | 仅 `<name>` 的 `<check>`（可附原因） |
| 行级 | `% analyzer:ignore-next-line <check>` | 仅下一行 |
| **区间级（P214）** | `% analyzer:disable [<check>]` … `% analyzer:enable [<check>]` | 区间内（不含两端）所有行；缺省 = 全部检查；未闭合视为到文件末尾；嵌套按最近匹配闭合 |

`checks.html` 汇总页会展示"已抑制"规模（名称级 / 文件级 / 行级 / 区间级）。

### 3.5 跨文件污点分析（P85+）
- 源（用户输入 / 文件 / 网络）/ 汇（危险调用 `system`/`fprintf`/`eval` 等）收集、反向传播（封顶 5 层）、危险入口判定。
- **变量级精确命中**：源赋值→传播→实参→形参映射→汇实参精确匹配（`exact` 标志）。
- **参数位门禁（`--taint-gate`）**：`fprintf:2`（第 2 实参受污即违例）/ `system:*`（任一实参受污即违例）。
- 输出 SARIF `tainted_sink` + JSON `taint` 字段。

### 3.6 注释完备度 / 技术债
- 注释标签聚合（`TODO/BUG/DEPRECATED/FIXME/NOTE`）→ `annotations.html` 技术债清单（可跳转源码行）。
- 注释完备度待办清单：复杂度 × 扇入 × 缺注释三维打分、优先级判定、缺失项清单（`doc_todos`）。
- 技术债聚合报告（`--debt`）：圈复杂度 + 扇入风险 + 未初始化/类型不一致/死代码密度 + 同名歧义 → 可排序"债主榜单"。
- 指标趋势（`--trend`）：跨快照演化（零依赖 Sparkline 迷你图）。

### 3.7 重复代码治理（P215+）
- 函数级 + 片段级相似度检测（结构指纹 Jaccard，可叠加语义归一化：可交换运算符排序、常量符号化）。
- 演化追踪（`--dup-baseline` / `--dup-diff` / `--dup-trend-svg`）、组织级指纹库（`--dup-org-baseline`）。
- **PR 闭环**：`--gen-pr`（PR 描述草稿 + 补丁骨架）、`--gen-apply-patch`（git apply 适用 unified diff）、`--dup-emit-patch`（完整重构补丁 + 调用方改写）、`--dup-verify-patch`（自证验证：可应用 / 重复减少 / 无新告警 / 调用边不丢）、`--dup-verify-equiv`（语义等价性报告）。
- CI 门禁：`--fail-on-dup`、`--dup-fail-gate`（总上限 / 新增上限 / 重复率）。

### 3.8 修复闭环到 PR（P210+）
- `--gen-pr`：聚合 5 类静态问题（uninit / type_mismatch / dead_code / shape_mismatch / taint_sink）为 PR 描述草稿 + 补丁骨架。
- `--gen-apply-patch`：对确定性可修复项（未初始化 high 补 `= [];`、死代码删行）生成**真实可应用** unified diff。
- `--gen-tests-risk`：基于高风险点自动生成 pytest / unittest 测试桩骨架。
- `--ai-prompts`：把分析结论汇总为可粘贴到任意离线 AI 工具的结构化审查提示词。

### 3.9 CI / 质量门禁体系
- **SARIF 2.1.0**：`--sarif` 接入 GitHub / GitLab 代码扫描；`--sarif-base` + `--sarif-diff` 做 PR 级增量（新增 / 已修复）差异报告（基线自动持久化）。
- **统一门禁矩阵（`--gate-file` / `--max-warnings-by-rule`）**：污点参数位门禁、按规则独立阈值、全局告警阈值、分支覆盖门禁。
- **趋势门禁（`--gate` / `--gate-max-debt` / `--gate-max-delta` / `--gate-max-uninit[-folder]` / `--gate-max-debt-folder`）**：把技术债快照接入 CI 退出码。
- **可复现构建（`--reproducible`）**：JSON 省略时间戳，两次输出逐字节一致（CI 比对友好）。
- **指纹两级缓存（`--fingerprint` / `--verify`）**：内容寻址 SHA-256（整体 + 逐文件 + 告警组），防篡改；配合 `--diff` 定位变更。
- **一键接入（`--gen-ci github|gitlab|both`）**：自动串接 `--json` + `--sarif` + `--sarif-diff` + `--fail-on-diff` + `--max-warnings` + `--reproducible`，模板可直接粘贴进仓库。

### 3.10 增量与性能
- **增量分析（`--incremental`）**：基于内容 SHA-256 签名缓存未变文件，仅重分析变更文件（CI 增量收益关键）。
- **git diff 增量（`--git-diff` / `--git-diff-staged`）**：仅分析 `git diff` 涉及的 `.m` 文件，日常 PR 开销极小。
- **大仓性能基准（`--benchmark`）**：合成 N 个文件跑完整分析 + `unified.html`，断言节点数受 `--max-nodes` 限制、时延在上限内（默认 60s）。

### 3.11 多格式输出
Markdown 报告、Mermaid 图、Graphviz DOT、HTML 报告、可点击浏览站点、结构化 JSON / XML、Doxygen 兼容 XML、双快照差异报告（`--diff` / `--diff-html`）。

### 3.12 维度 / 定标 / 算子分析（P224 系列）

面向信号处理类 MATLAB 工程（如 5G NR 信道建模），把「数据维度、变量缩放/归一化、算子触发」三条分析链路打通，并在**同一函数作用域**内关联，避免跨函数同名误配。

- **维度视图（`dims.html`，P224-W / P224-T / P224-T2）**：每个调用内置函数的函数一行，实测其「输入/输出维度」（来自 `_infer_file_dims` 对 `sum/mean/std/imresize/reshape/...` 的实测算），是被测代码的真实数组尺寸而非工具箱文档的理论尺寸。跨文件结构体/类成员维度按「同文件 → 同目录」就近解析；同名冲突时**保守拒绝并显式标记 `⚠ 冲突已排除`**，杜绝误标；P224-T2 进一步**列出冲突来源文件与各自维度**（而非仅一个布尔位），便于人工核对；缓存按文件内容 SHA 防陈旧（P224-W）。
- **维度↔定标联动（P224-V）**：每个函数标注「函数内定标」列——仅取该函数代码区 `[fstart,fend]` 内的定标站点（复用 `_collect_scaling_patterns`），类别用中文标签（如 `uint8_norm→整数/像素归一化`），横幅提示"其中 N 个函数内检测到定标模式"。同一函数作用域内打通"实测维度"与"变量缩放/归一化"。
- **定标→维度反推（P224-R）**：所有已识别定标/归一化（`÷255`、`mean/std`、`min-max`、角度换算、`log/dB`、通用缩放）均为**量纲或数值范围变换，不改变数组维度**。定标页与维度视图显式标注「不改维度 / 维度不变」，防止阅读者把"归一化"误解为"形状变化"。
- **算子工程影响（`operator_impact.html`，P221-A / P224-U）**：目录全量检测算子的"命中 / 零命中"覆盖（含静默盲区 `silent`）；并校验 `catalog_fired`（实际触发计数）在真实代码上真实累加——引入一致性守卫，对"已触发但不在目录"的键错位**显式暴露**而非静默隐藏，避免"统计自洽但计数失灵"。
- **分析总览 / 健康度仪表盘（`overview.html`，P224 收口）**：把维度标注覆盖率、定标站点数量、算子目录覆盖（命中 / 零命中 / 未纳管）、结构体成员覆盖（冲突 / 未定义）与工程规模汇成单页；导航栏新增「分析总览」入口，一眼掌握数据维度 / 缩放 / 算子全景。
- **函数产出维度（`dims.html`，P224-Y）**：维度视图除「内置调用维度」外，新增展示每个函数的「产出（返回变量）维度」——取函数签名输出变量在末尾变量环境中的真实维度（如 `function y = f(); y = ones(3,4); end` 标注 `y: 3×4`），让用户一眼看到函数返回何种尺寸数组；无内置调用的纯数组算术函数也会因此进入维度视图，覆盖率进一步提升。
- **变量字段流动（`varflow.html`，P225-A）**：逐函数展示每个变量的「定义位置 ← 来源变量」def-use 链与实测维度，回答「这个变量从哪来、被哪些语句改写、维度是什么」。与污点分析互补——污点只跟踪敏感源到危险汇的传播，本视图覆盖**任意变量**的通用流动。底层在 `_infer_function_dims` 维度推导循环内零开销并行走查 `def`（写）/ `use`（读）关系（字段级 `.` 成员引用被区分），随维度推导一次算清，缓存于 `_INFER_VARFLOW_CACHE`。
- **跨文件变量溯源（`varflow.html`，P225-D）**：在 P225-A 之上，沿调用图把「实参→形参」「返回值→接收变量」绑定成统一数据流有向图（`_build_varflow_xfile` + `window.__VARFLOW_X__`），前端对任意「函数.变量」做 BFS，列出**上游（数据来源）**与**下游（数据流向）**的完整跨模块链。变量卡片上的 `↔N` 标注其跨文件边数量。例如 `main.b` → `helper.x` → `sub.y` → `sub.r` → `helper.z` → `main.out` 的整条链路可被一次追踪还原。
- **执行追踪维度推断脚手架（P225-E，终局·超越静态）**：静态维度推断对「动态结构体字段、跨调用返回绑定」等存在歧义。终局方案是用真实运行时（Octave/MATLAB）实跑函数回填尺寸。已落地可验证脚手架：`detect_matlab_runtime()`（无运行时优雅返回 None）、`_parse_dims_probe()`（解析 `VAR: h x w` 探针输出）、`_make_dims_probe_script()`（为单函数生成可运行探针 .m）。**激活条件**：环境具备 Octave/MATLAB；届时在 `_build_dims_view_data` 处对 `detect_matlab_runtime()` 非 None 的函数叠加执行回填维度。本沙箱无运行时，故仅脚手架+测试落地，实跑回填待运行时就绪。
- **模块调度统计（`schedule.html`，P225-B）**：从既有调用分析聚合「各模块真实调度流程」——被调用热度 Top（核心调度点）、入口函数（入度 0）、以及 函数→函数 的调用次数与调用行分布（可按被调方/调用方聚合）。数据全部来自 `func.call_sites` 与 `model.callers_of`，零重复解析。
- **维度反查（`dims.html`，P225-C）**：在维度视图新增「从尺寸找调用点」面板——输入一个尺寸（如 `3×4`/`1×N`/`1x3`），列出所有内置调用中尺寸匹配的输入/输出调用点（函数、内置名、行、匹配维度），与上方函数列表构成维度关系的双向定位。内置调用逐次 `in`/`out` 维度已在 `__DIMS_VIEW__` 中，反查纯前端渲染。
- **AI CLI 引入时机（P225-F）**：`--ai-mode {off,prompts,ask,auto}` 把"何时引入 AI"交还给用户选择——`off` 纯静态；`prompts` 仅生成离线提示词包（不联网）；`ask` 运行结束交互询问是否调用在线 AI 审查（非交互环境自动降级为 prompts）；`auto` 自动调用（需 `MA_AI_PROVIDER` 与密钥）。任何缺配置/失败都优雅降级，绝不拖垮静态分析主流程。
- **图形界面启动器（P225-G）**：`gui.py`——基于标准库 tkinter 的**零依赖桌面 GUI**（跨 Windows/Linux/macOS），把庞大命令行收敛为友好表单：选工程目录、勾选输出（浏览站点/HTML/JSON/SARIF/MD）、选择 AI 时机、一键分析并流式显示日志、点击打开结果。`build_cli_args(form)` 为纯函数，表单→CLI 映射可无界面单测。
- **一键打包发布（P225-H）**：`build_dist.py`（PyInstaller 单文件）+ `build_release.bat`（Windows）/ `build_release.sh`（Linux·macOS）把工具打成免 Python 的**单个**可执行程序 `matlabc(.exe)`（双击=GUI、带参数=CLI，统一入口 `matlabc_boot.py`），自动打包 `renderers/assets` 资源；PyInstaller 不能交叉编译，故在各目标平台分别"一键发布"。

---

## 4. 架构（单文件分层）

```
[词法层] scrub_source / _logical_statements
    ↓
[解析层] parse_file / parse_function_line / analyze_calls / resolve_call
    ↓
[数据层] MatlabFunction / MatlabClass / MatlabFile
    ↓
[分析层] _impact_layers / _dependency_layers / _trace_roots / _compute_function_metrics
          + 静态检查器（uninit / type / dead_code / shape / taint / dup_code）
    ↓
[渲染层] render_markdown_report / render_html / render_browse_site / render_json / SARIF
    ↓
[入口层] main (argparse / config) → 打包 console_scripts；GUI 启动器 `gui.py`（tkinter 零依赖）；一键打包 `build_dist.py`（PyInstaller 单文件，跨 Windows/Linux/macOS）
```

- **数据流**：`collect_files` → `parse_file`（结构）→ `analyze_calls`（调用）→ `build_analysis_model`（统一模型）→ 各渲染函数。
- **就近解析规则**：同名被调按"同文件 → 同目录 → 其余路径序"解析，歧义通过 `ambiguous_calls` 标记并透明化。

---

## 5. 输出产物一览

| 产物 | 触发参数 | 用途 |
| --- | --- | --- |
| 控制台 Markdown 报告 | `dir`（默认） | 快速查看 |
| 报告文件 | `-o` / `--html` / `--mermaid` / `--dot` | 归档 / 评审 |
| 浏览站点 | `--browse` | 交互式源码跳转 |
| 结构化数据 | `--json` / `--xml` / `--export-doxygen-xml` | 二次开发 / doxygen 生态 |
| 静态分析 | `--sarif` / `--checks` | CI 代码扫描 |
| 技术债 / 趋势 | `--debt` / `--trend` / `--gate` | 质量度量 |
| PR 闭环 | `--gen-pr` / `--gen-apply-patch` / `--gen-tests-risk` | 修复落地 |
| 重复代码治理 | `--dup-*` / `--fail-on-dup` | 复制粘贴坏味道治理 |
| 图形界面 | `gui.py` | 零依赖桌面 GUI 启动器（勾选输出 / AI 时机 / 一键分析） |
| 一键打包 | `build_dist.py` / `build_release.*` | 打成单文件可执行，免 Python 分发 |

---

## 6. 当前版本亮点（v1.16.62）

- **区间级告警抑制（P214）**：`% analyzer:disable … enable` 覆盖块内所有行，与既有三档（文件 / 名称 / 行级）并列，C3 抑制四档化。
- 重复代码治理全链路（检测 / 演化追踪 / PR 补丁 / 自证验证 / CI 门禁）。
- 离线优先 + 大仓 `--max-nodes` 渲染保护，纯内网可用。
- 统一门禁矩阵 + 趋势门禁 + 一键 CI 模板，质量回路闭合。
- **维度 / 定标 / 算子分析（P224 系列）**：维度视图实测数组尺寸 + 跨文件就近解析与冲突保守拒绝（P224-T/W）；维度↔定标同函数域联动（P224-V）；定标→维度反推标注"不改维度"（P224-R）；算子目录命中/零命中覆盖与触发计数一致性守卫（P221-A / P224-U）。
- **AI 引入时机可选（P225-F）**：`--ai-mode` 让用户在 off/prompts/ask/auto 间选择 AI 何时介入，离线优先、失败优雅降级。
- **零依赖图形界面（P225-G）**：`gui.py` 基于 tkinter，免装第三方即可在三大平台使用友好启动器。
- **一键跨平台打包（P225-H）**：PyInstaller 单文件 + 各平台一键脚本，免 Python 分发**单个** `matlabc(.exe)`（GUI 与 CLI 合一）。

> 详细版本演进见 `matlabc_DELIVERY_REPORT.md`；使用参数见 `matlabc_USAGE.md`。

## 实现进度（P225 路线 · 持续改进）

| 步骤 | 内容 | 状态 |
|---|---|---|
| ① 布局溢出修复 | 页眉 flex 换行，窄屏不再被 30 链接顶破 | ✅ |
| ② AI 引入时机 `--ai-mode` | off / prompts / ask / auto，离线优先优雅降级 | ✅ |
| ③ 零依赖 GUI 启动器 `gui.py` | tkinter 表单，流式日志，原生打开结果 | ✅ |
| ④ 跨平台打包 | PyInstaller 单文件 + `build_release.bat/.sh`；产物平铺 `dist_bin/` 根；已修复 `--help` 崩溃 | ✅（Windows 已验证） |
| ⑤ 索引导航重构（治本） | 抽共享 `_site_header_html` / `_site_nav_html`：导航**分组**（浏览/分析/视图/图）+ **移动端折叠菜单**；并加冒烟测试回归守护 | ✅ |
| ⑥ 激活执行追踪终局 | 接 Octave/MATLAB 实跑回填维度 | ⬜ 需本机装运行时（暂不可在本环境验证） |
| ⑦ GUI 增强 | **配置 JSON 加载/保存/回填**（`--config`）+ **界面重新设计**（标题栏 + 卡片式布局 + 浅/深主题）+ 语言选择器 + 检查项输入 | ✅ |
| ⑧ Linux / macOS 实跑发布 | 各平台跑 `build_release.sh`（PyInstaller 不能交叉编译） | ⬜ 需对应环境 |

### 本轮（2026-09-23）交付要点
- 修复「Windows 下没看到 exe」：产物实为嵌套子目录；已改为平铺 `dist_bin/` 根并清理 `_build/` 中间产物；同时修复帮助串字面 `%` 导致 `--help` 崩溃（`.py` 与 exe 均受益）。
- 索引导航重构：30 个平铺链接改为「浏览 / 分析 / 视图 / 图」四个分组，窄屏（≤880px）折叠为「导航菜单」按钮，解决溢出与可扫读性。
- GUI 新增语言下拉（auto/matlab/c/py/js → `--lang`）。
- 测试：`test_analyzer_smoke` 新增导航结构回归断言；`gui.py --selftest` 与 9 项相关测试全绿；静态 lint 0。
