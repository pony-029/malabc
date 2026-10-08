# matlabc · AI 驱动能力路线图

> 用 superpower 四步框架（定界 → 盘点 → 差距根因 → 引领性结论）系统梳理：
> **AI 能为 matlabc 这个项目本身驱动什么**，并给出可执行的阶段性计划。
> 配套：`matlabc_USAGE.md`、`matlabc_FEATURES.md`、`ai_review_prompts.md`、
> `AI_CLI_INTERFACE_DESIGN.md`、`OPERATOR_CATALOG.md`。

---

## 1. TL;DR（三句话结论）

1. **定位**：matlabc 当前处于「AI 管道对齐、智能层浅」阶段——`ai_cli.py` 已具备多供应商（含国产大模型）、离线优先、脱敏、diff 解析等**基础设施**，但**编排与领域智能尚未落地**。
2. **最大差距**：缺失三样东西——「基于已分析模型的可检索/可问答底座」「把 `ai_config.schema.json` 里 `flow` 编排真正跑起来的修复-验证闭环」「面向 Simulink/仿真/自主驱动的领域深度」。
3. **下一步**：先建**检索/ grounding 底座**（解锁「问答式理解」与「有依据的审查」），再闭环**修复-验证**（解锁「补丁」），随后补**仿真优化**与**自主驱动**方向。

---

## 2. 分析方法（联动了哪些能力）

| 维度 | 方法/来源 | 产出 |
| --- | --- | --- |
| 现状锚定 | 通读 `ai_cli.py`、`ai_config.schema.json`、`--ai-mode`/`--gen-apply-patch` 等现有代码 | 能力清单（见 §3） |
| 差距识别 | 对照「审查 / 问答 / 补丁 / 仿真 / 自主」五大诉求逐项标注 | 三态矩阵（§3）+ 根因（§4） |
| 完成标准 | 每个阶段给出可验收的「 Done 定义」 | 分阶段计划（§5） |
| 工程化 | 复用现有零依赖 `ai_cli` 适配器，避免重复造轮子 | 落地建议 |

---

## 3. 现状全景（能力清单 × 三态）

图例：✅ 已实现 · 🟡 部分/浅层 · ❌ 缺失 · ➖ 不适用

| # | 能力 | 现状 | 说明 |
| --- | --- | --- | --- |
| C1 | 多供应商适配（OpenAI 兼容 + 国产：DeepSeek/通义/智谱/Kimi/百川/豆包/零一/阶跃/文心/讯飞） | ✅ | `ai_cli.PROVIDER_PRESETS` + 中文别名 |
| C2 | 离线优先（无密钥自动降级为「打印/写出提示词」） | ✅ | `--ai-mode prompts/offline` |
| C3 | 密钥脱敏、仅读环境变量、绝不落盘 | ✅ | `SECRET_RE` + 约定 |
| C4 | 任务模板 review/fix/explain/tests/refactor | ✅ | `TASK_GUIDE` |
| C5 | diff 解析与补丁抽取（`parse_unified_diff`） | 🟡 | 能抽，但「抽取→应用→自证无新告警」未闭环 |
| C6 | 修复闭环钩子（`--gen-apply-patch/--gen-tests-risk/--gen-pr`） | 🟡 | 钩子存在，`ai_config` 的 `flow` 字段「ai_cli 当前仅参考」，**未真正编排** |
| C7 | 代码库问答（RAG over 分析结果） | ❌ | 没有把分析结果做成可检索索引 |
| C8 | 自然语言 → 图查询（谁调用 X / 哪里有风险） | ❌ | `matlabc.py` 已产出调用图/热点，但未被问答消费 |
| C9 | Simulink/仿真优化建议（建模层重构、代码生成 CRL 提示等） | ❌ | AI 任务仍是「通用代码审查」，不感知模型语义 |
| C10 | 自主「快速响应/驱动」：自动分诊告警→出补丁→验证→报告 | ❌ | 无 agent loop |
| C11 | 能力封装为可复用 skill（skill-creator 打包） | ❌ | 未对外封装 |

**结论**：C1–C4 已是行业级底座；C5–C6 半截子；C7–C11 空白。这正是「管道对齐、智能层浅」。

---

## 4. 差距根因（不只说缺，还说为什么缺）

- **为什么 C7/C8 缺**：静态分析产出的是「结构化模型」（文件/函数/类/调用边/告警/SARIF），但 `ai_cli` 只把**单条文本 prompt** 丢给模型，没有把整个工程索引成可检索上下文。问答必然「无依据、易幻觉」。
- **为什么 C6 半截子**：`ai_config.schema.json` 的 `flow.steps/auto_apply` 是**声明先于实现**——schema 画好了，但编排器（`ai_cli` 之外）没有消费它。缺一个「驱动器」。
- **为什么 C9 缺**：matlabc 已能解析 Simulink/MATLAB，但 AI 任务模板是语言无关的（review/fix…），没有「模型级」提示词与领域知识注入点（如 Stateflow/代码生成/代数环）。
- **为什么 C10 缺**：自主驱动 = 把 C5+C6+C7 串成 loop。缺 loop 编排（可借 `loop-engineering` 方法论定义完成标准）。

---

## 5. 引领性结论 + 分阶段计划

### 定位 / 判断
- **定位**：AI 基础设施领先、智能闭环缺失。
- **判断**：差距性质 = 「结构性空白（检索底座、编排器）」+「领域深度不足（仿真/自主）」，不是「单点 bug」。因此应**先补结构性底座，再填领域深度**。

### 阶段计划

#### P0 · 检索/grounding 底座（解锁「问答式理解」与「有依据的审查」）
- **做什么**：
  - 把 `matlabc.py` 的分析结果（artifact model + 调用图 + 热点 + SARIF）序列化为**可检索索引**（轻量：本地向量或 BM25，零依赖优先；可选接入 RAG 知识库）。
  - 新增 `matlabc ask "<自然语言>"` 子命令：把问题 + 相关片段组装给模型（复用 `ai_cli`）。
  - 内置图查询意图识别：识别「谁调用 X」「X 的扇入/扇出」「最高风险函数」等，直接查图后喂模型。
- **验收标准**：
  - `matlabc ask "main 函数被谁调用"` 能返回基于真实调用图的答案（含文件:行号）。
  - 审查任务能自动附带「相关函数源码 + 告警上下文」，而非裸 prompt。

#### P1 · 修复-验证闭环（解锁「补丁」）
- **做什么**：
  - 实现 `ai_config.flow` **真正编排器**：`steps=[review, fix, apply, verify, report]`，`auto_apply` 受 `--dry-run` 保护。
  - `fix` 产出 ```` ```diff ```` → `parse_unified_diff` 抽取 → 应用 → **重跑 matlabc 自证「无新增告警」** → 通过才保留（复用现有 `--gen-apply-patch` 钩子）。
  - 失败/冲突时回退并给出 human-in-the-loop 报告。
- **验收标准**：
  - 对一个已知 uninit/taint 告警，端到端跑出「补丁已应用且重扫 0 新增告警」的自证结论。
  - `auto_apply=false`（默认）时只产出草案，不改动源码。

#### P2 · 仿真/Simulink 优化（领域深度）
- **做什么**：
  - 注入领域知识：Stateflow/代数环/代码生成（CRL/Embedded Coder）提示词。
  - 新增 `sim-optimize` 任务：针对模型给出「可简化模块」「冗余计算」「代码生成友好度」建议。
  - 在交互站点里给 Simulink 节点加「AI 优化建议」侧栏（复用 `renderers` 资产体系）。
- **验收标准**：对示例 Simulink 工程，能产出 ≥3 条**模型级**优化建议（非通用代码审查）。

#### P3 · 自主驱动 / 快速响应（agent 闭环）
- **做什么**：
  - 用 `loop-engineering` 定义「分诊→出方案→验证→报告」的 agent loop，分层退出（遇到无法自证的改动转人工）。
  - 新增 `--autopilot`：给定告警集，自主跑 P0+P1，产出 PR 草案 + 变更摘要。
  - 把成熟能力封装为 skill（`skill-creator`），可一键「对当前工程做 AI 体检」。
- **验收标准**：对一批告警，`--autopilot` 在无人干预下完成「分诊→补丁→自证→摘要」，且所有改动可一键回滚。

---

## 6. 下一步（写给现在的你）

1. **立刻可做（低风险）**：把 `ai_config.schema.json` 的 `flow` 编排器补全（P1 的 50%），因为底座 `ai_cli` 已就绪，只需一个「驱动器」脚本消费 `flow` 字段。
2. **本周**：落地 P0 检索底座的最小版（BM25 over 分析结果，零依赖），先打通 `matlabc ask`。
3. **本月**：P1 闭环打通后，把 `ai_cli` 的 `fix` 能力接进 GUI 的「AI 体检」按钮，用户点一下即得补丁草案。
4. **衡量指标**：以「AI 建议被采纳率」「自证通过率」「无新增告警率」而非「调用次数」衡量智能层价值。

> 一句话：matlabc 不缺「连大模型的能力」，缺的是「让大模型**基于本工程事实**去审查、问答、修代码、优化仿真、并自主跑闭环」的**编排与领域底座**。先把 P0 的检索底座和 P1 的 flow 编排器做出来，其余三个方向会顺势解锁。

---

## 7. 实施进展（持续更新）

- **P0 检索/grounding 底座：✅ 已实现**（`matlabc_ask.py` + `matlabc ask` 子命令）
  - 零依赖 BM25，归一化 MATLAB/C/Python/JS 四类报告（函数文档 + 调用图 + 告警/优先级）。
  - 意图识别：谁调用 X / X 调用谁 / 风险热点 / 解释 X（中英文）。
  - 复用 `ai_cli`：离线回显提示词，在线（deepseek/qwen/ernie/…）给中文回答。
  - 验证：C 工程 `who calls add` 正确返回调用者；MATLAB 解释/风险意图正确；图为空时优雅降级。
  - 已知限制：MATLAB 调用图解析对小样本/表达式内调用覆盖弱（见 §8 下一步 ①）。
- **P1 修复-验证闭环：✅ 已实现**（`matlabc_flow.py` + `matlabc flow` 子命令）
  - 真正驱动 `ai_config.flow.steps`（review→fix→apply→verify→report），默认不落盘（`auto_apply=false`）。
  - `fix` 复用确定性补丁引擎（`--gen-apply-patch`）；`apply` 优先 `git apply`、回退进程内严格校验；`verify` 以「重扫后各规则告警数不增加」为自证标准。
  - **顺带修复** `_build_apply_patch` 长期 bug：difflib 把函数上下文行从 hunk 体首「移走」导致补丁非法（`git apply`/严格校验均拒）；新增 `_fix_diff_function_context` 还原首上下文行，补丁现合法可应用。
  - 验证：dead_code 样例 `flow --auto-apply` 应用后告警 `dead_code:1 → 0`，自证通过(PASS)，RC=0。
- **P225 交互站点显示修复：✅ 已修复**（`renderers/assets.py`）
  - **根因一（顶栏溢出）**：`BROWSE_CSS` 常量（新版，含 `header{flex-wrap:wrap}` 与 `.nav-toggle/.topnav/.nav-group` 响应式导航）与落盘镜像 `page_css/browse.css`（旧版，缺这些规则）**漂移**；`write_browse_css_tree` 优先读镜像 → 线上顶栏 30+ 链接平铺不可折叠 → 横向溢出。
  - **根因二（多页面样式孤儿）**：全站审计（HTML class × CSS 选择器交叉）发现 **24 个类被页面引用却零 CSS 定义**，其中 `.site-header/.topbar/.container/.content/.data-table` 是结构骨架类，导致合规/总览/标定/维度/算子影响/变量流/目录矩阵/函数库 8 个独立页面布局退化。
  - **修复**：① 同步镜像为常量内容；② 在 `write_browse_css_tree` 加**漂移守卫**（以常量为唯一事实来源，检测到不一致即告警并回写镜像）；③ 补齐 24 个孤儿类（含深色主题适配）。
  - **验证**：重新生成站点后孤儿类归零（仅剩 JS 字符串误报）、关键规则全部落盘、selftest 通过、lint 零错误。
- **P225-L 调用图/语义解析质量（表达式内调用覆盖盲区）：✅ 已修复**（`matlabc.py` + `renderers/unresolved.py` + `tests/test_matlabc.py`）
  - **实证定位（而非拍脑袋）**：用脚本把模块里调用提取正则序列直接跑 27 组棘手 MATLAB 表达式，发现「嵌套/数组内/索引内/逻辑内/cell 内/匿名内」调用**已覆盖**（证明"表达式内调用基本 OK"）；**真正的盲区是"被修饰后的间接调用"**——提取器对它们返回 `(none)`：
    - `C{1}(x)` 元胞元素作函数句柄调用；`A(i)(x)` 索引后调用；`obj.(v)(x)` 动态字段方法调用。
  - **结构性空白**：旧提取器只识别"名字直接后跟 `(`"的调用，缺"被 cell/索引/动态字段修饰后调用"的识别。
  - **修复**：① 新增 `RE_INDIRECT_CALL`/`RE_DYNAMIC_METHOD` 两个正则 + `MatlabFunction.indirect_calls` 维度（提示性，不强行解析运行期目标）；② 在 `analyze_calls` 提取；③ 序列化进 `report.json`、`src/symbols.json`（符号层）、诊断页 `unresolved.html` 新增「间接调用」区块；④ 加 `_collect_indirect_calls` 收集器。
  - **验证**：探针确认三类盲区全部捕获（且纯索引 `A(i)` 不误判）；端到端样例 `disp_cell→{fns:1}`、`dyn_call→{.name:1,a:1}` 正确落盘并展示；新增回归测试 `test_p225_indirect_call_detection`（5 项断言）通过；selftest 通过、lint 零错误。
- **P225-M 索引/数组调用歧义消歧：✅ 已修复（标注而非删除）**（`matlabc.py` + `renderers/unresolved.py` + `tests/test_matlabc.py`）
  - **实证再评估（关键纠偏）**：先验证「调用图边」其实已安全——`analyze_calls` 只对 `resolve_call` 成功（已知函数）建边，解析不到的名字进 `external_calls`/`unresolved`，**不产生假边**。所以真正的噪声是诊断页「疑似漏检调用」里把**变量索引**（`buffer(1)`/`signal(end)`）误列。
  - **修复（保守、零假边风险）**：新增 `RE_INDEX_CALL`（仅取强索引信号 `:` / `end` / 数字开头，如 `A(:)/A(end)/A(1)/A(2,3)`），**刻意不**捕获 `A(i)`（循环索引同形）、`plot(x,y)`（双参真调用同形）等高风险同形，避免误删真实调用。命中且解析不到函数时，改记 `index_like_calls`（标注），从 unresolved 噪声剥离。
  - **验证**：正则 13 组判定全对；端到端 `buffer(1)`/`signal(end)` 正确进 `index_like_calls` 并在 `unresolved.html` 标注；`unknownFun(bar)`（真外部调用）、`plot(x,y)`（双参同形）**不被误标**；新增回归测试 `test_p225_index_like_call_diversion` 通过；P225 系列 3 测试全过、selftest 通过、lint 零错误。
- **P225-CI 调用图提取回归基线：✅ 已建立**（`tests/test_callgraph_coverage.py` + `matlabc.py` 微调）
  - **建设动机（superpower 实证护栏）**：把"调用提取覆盖 + 歧义判定"固化为数据驱动的黄金用例集，使后续任何提取规则改动都有自动护栏。建基线过程中**顺带发现并修复一个真 bug**：
    - **多字符索引后调用 `myHandle(i)(x)` 泄漏**：`RE_CALL` 命中 `myHandle(` 后，因该名未解析且非索引信号（`i` 非数字），被计入 `external_calls`，同时 `RE_INDIRECT_CALL` 又记为 `indirect_calls` → **双重计数且假「缺失调用」**。已加 `RE_INDIRECT_CALL` 守卫跳过，并**把索引/间接检测移到 `len(name)>1` 门限之上**，使单字符数组索引 `M(end)`（最常见形式）也能被标注为 `index_like`（此前静默丢弃）。
  - **内容**：`test_p225_callgraph_coverage_baseline` 覆盖全部分类维度（精确边 / 句柄 / feval 字符串 / 间接 cell·索引后·动态字段 / 索引样式 / 外部 / 内置）并含**反向防漏断言**（间接/索引样式绝不污染 `external_calls`）；`test_p225_callgraph_coverage_index_signal_precision` 验证索引信号精确性（强信号捕获、双参/单变量同形不误标）。
  - **验证**：2 测试通过；P225 系列共 5 测试全过、selftest 通过、lint 零错误。
- **P225-OOP 方法调用接收者就近解析（类名限定）：✅ 已落地第一刀**（`matlabc.py` `analyze_calls` 方法调用块 + `tests/test_callgraph_coverage.py::test_p225_oop_qualified_method_resolution`）
  - **根因（superpower 实证）**：`resolve_call` 只用裸函数名 `index`，**完全忽略已构建的 `qualified_index`**；而 `analyze_calls` 方法调用块（原 4492 行）只取 `RE_METHOD_CALL` 的**方法名**去解析 → `ClassName.helper()` 被错解到同名自由函数 / 别类同名方法，OOP 调用边既漏又歧义。`--instr` 运行时调用图桥经核查**在 matlabc 中并不存在**（trace 命中全是 `_ref/` 里 MATLAB 自带工具链文档），属绿地大工程且需真实 MATLAB 运行时，故本轮不交付，改做可落地的静态 OOP 改进。
  - **修复（unambiguous，零假边）**：recv 是项目内类名时（`ClassName.method` / 静态方法 / 以类名调实例方法 `ClassName.method(obj,...)`），先以 qualified key `classname.method` 解析；**仅当 `qualified_index` 中确有 `class_name==recv` 的类方法**才采用并标记 `resolved_qualified`（排除同名自由函数 qualified 名巧合误判）。实例变量 `obj.method` 的接收者类型推断本轮**未做**（脆弱启发式易产假边），列为下一步。
  - **验证**：新测试构造「类方法 helper + 同名自由函数 helper」对照，`MyClass.run` 内 `MyClass.helper(self,x)` 正确解析到 `MyClass.helper` 且**不**误连同名自由函数；3 测试通过；P225 系列共 6 测试全过、selftest 通过、lint 零错误。
- **P225-OOP 实例方法接收者类型推断：✅ 已落地**（`matlabc.py` 新增 `_collect_var_class` + `analyze_calls` 方法调用块增强 + `tests/test_callgraph_coverage.py::test_p225_oop_instance_method_receiver_inference`）
  - **根因与思路（superpower 实证）**：类名限定仅覆盖 `ClassName.method`；更普遍的是 `var = ClassName(...)` 后 `var.method()`（类内/跨类互调），静态解析器此前把它当裸方法名 → 漏边或歧义。MATLAB 变量为**函数级作用域**（非块级），故可做轻量、bounded 的构造赋值扫描：整函数体扫 `var = ClassName(...)`（含 `Class.static(...)` 工厂），建 `{var: 类名}` 映射。
  - **修复（保守、零假边）**：`recv.method` 当 recv 是上述映射中的变量时，绑定到 `ClassName.method`——**仅当目标类方法确实存在于 `qualified_index`** 才采用；若 var 被后继重赋为异类则属已知局限（已记录）。与类名限定共用 `resolved_qualified` 标记，确保不误标歧义。
  - **验证**：新测试构造「`MyClass`(含构造函数 `MyClass`+方法 `compute`) + 同名自由函数 `compute` + `driver`(`m = MyClass(x); r = m.compute(2)`)」，`driver` 的 `m.compute` 正确绑到 `MyClass.compute` 且**不**误连同名自由函数，`MyClass(x)` 构造调用也正确解析到 `MyClass` 构造函数；全 4 测试通过；P225 系列共 7 测试全过、selftest 通过、lint 零错误（调试中发现并修正的是**测试断言**大小写问题，非代码缺陷）。
- **P225-OOP 类内互调零成本补全：✅ 已落地**（`matlabc.py` `analyze_calls` 方法调用块增强 + `tests/test_callgraph_coverage.py::test_p225_oop_class_internal_this_obj_binding` / `::test_p225_oop_class_internal_first_param_binding`）
  - **根因与思路（superpower 实证）**：实例方法推断覆盖 `var = ClassName(...)` 后调用；但更常见的类内互调是**直接 `this.foo()` / 首参对象 `.foo()`**（不显式构造）。MATLAB 方法的**首参即对象自身**（约定名 `this`/`obj`/`self` 或首参变量），故无需变量扫描即可零成本绑定：当调用方 `func.class_name == C` 且 recv 为约定对象时，直接绑 `C.method`。
  - **修复（保守、零假边）**：仅当 `C` 确有名为 `key` 的方法（存在于 `qualified_index`）才采用；与既有类名限定 / 构造赋值共用 `resolved_qualified` 标记，绝不误标歧义。三路径优先级：类名限定 → 构造赋值变量 → 类内互调（this/obj/首参）→ 裸名回退。
  - **验证**：`this.helper` 与首参 `self.render` 两测试均正确绑到本类方法、不误连同名自由函数；调用图覆盖测试全 6 通过；P225 系列累计 9 测试全过、selftest 通过、lint 零错误。
- **① 跨文件同名方法消歧增强：✅ 已落地**（`matlabc.py` `resolve_call` 新增 `prefer_class` 参数 + 四处调用路径接入 `func.class_name` + `tests/test_callgraph_coverage.py::test_p225_oop_prefer_class_disambiguation`）
  - **根因（superpower 实证）**：原 `resolve_call` 就近逻辑（同文件→同目录→路径序）对 OOP 不足——**类方法常定义在独立文件**（`@MyClass` 类文件夹或方法分文件），与调用方不在同文件/同目录，导致裸调用 `foo()` 在类内时可能被就近误链到**其他目录的同名自由函数**。
  - **修复（保守、零假边）**：`resolve_call` 新增 `prefer_class`；当存在该类同名方法候选时，**先收窄到该类方法再走就近逻辑**（无该类候选则完全回退原逻辑，不影响非 OOP）。四处调用路径（方法调用裸名回退 / 命令形式 / 函数句柄 / feval 动态）均传入 `prefer_class=func.class_name`，OOP 消歧全局一致。
  - **验证**：精准单测构造「`MyClass` 类方法(在 `@MyClass/` 子目录) + 根目录同名自由函数」对照，断言：跨文件调用方（仍是 MyClass 方法）`prefer_class` 命中类方法；无 `prefer_class` 时就近取自由函数（反例成立）；调用图覆盖测试全 7 通过；P225 系列累计 10 测试全过、selftest 通过、lint 零错误。
- **④ PyInstaller 单文件 exe 构建脚本：✅ 已交付并验证**（`build_exe.py`，产出 `dist_bin/matlabc.exe` + `dist_bin/gui.exe`）
  - **根因**：项目早有 `dist_bin/matlabc.exe` 但**无构建脚本/spec**，不可复现。经核查 `gui.analyzer_target()`（gui.py:202）冻结态调用**同目录的 `matlabc.exe`**（CLI 分析器），故正确打包是**两个 `--onefile` 单文件 exe**：`matlabc.exe`(控制台, `matlabc.py`) + `gui.exe`(窗口, `gui.py`，运行 spawn 同目录 `matlabc.exe`)。单打其一会导致 GUI 无法启动分析。
  - **交付**：`build_exe.py`（`--clean` / `--cli` / `--gui` 选项，`--specpath` 指向构建目录避免污染根，隐藏导入 `matlabc`）。实测 `py -3 build_exe.py --clean` 成功产出两 exe；`matlabc.exe --help` 运行正常（GUI 为 windowed 无控制台）。
  - **用户问答回应**：「单独一个文件包含 exe 能直接运行吗」——PyInstaller `--onefile` 生成的单文件 exe 双击即运行、目标机无需 Python（代价：体积大、启动略慢）；`.py` 里直接塞 exe 二进制不行（需运行时释放）。现已可一键复现。
- **下一步优先级调整**：P0、P1、P225、P225-L、P225-M、P225-CI、P225-OOP(类名限定+实例方法+类内互调)、①跨文件消歧、④exe 构建 均已落地。调用图/语义解析的**静态盲区 + 提取护栏 + OOP 四路径解析 + 可复现单文件交付**已补全。下一刀建议：① **方法级精确边回流到类协作浏览**（类节点点击展开方法调用明细，闭环 OOP 可读性红利）；或 ② **静态→运行时调用图桥**（`--instr` 插桩 trace，攻克 `cell` 句柄 / `obj.(v)` / `feval` 字符串目标，需 MATLAB 运行时）；或 ③ 推进 P2 仿真优化与 P3 自主驱动。

---

## 8. 新的建设性意见（补充）

1. **① 调用图/语义解析是全局瓶颈**：你的 991 文件工程「调用边=0」与 ask 在小样本「图为空」同源——MATLAB 前端对表达式内调用（`y = helper(x)+1`）、跨文件解析覆盖不足。**优先补强 `resolve_call` 与表达式级调用抽取**，浏览站点与 ask 会同时变强。
2. **② ask 从「检索」升级为「图谱对话」**：当前 ask 是单轮检索。下一步接 `loop-engineering` 做多轮：模型追问→再检索→收敛，并把回答锚定到 文件:行号 生成可点击链接（复用 `renderers` 资产）。
3. **③ P1 修复闭环：✅ 已落地**（见 §7）。下一步把它从「确定性补丁」升级为「AI 补丁」——`fix` 步骤除确定性引擎外，新增 `ai_cli task=fix` 产出的 ```` ```diff ```` 经 `_apply_unified_patch_text` 应用并自证，覆盖 uninit/medium、类型、污点等确定性引擎不管的类别。
4. **④ 仿真/Simulink 深化**：注入 Stateflow/代数环/代码生成（CRL/Embedded Coder）领域知识，在交互站点给 Simulink 节点加「AI 优化建议」侧栏。
5. **⑤ 自主驱动 `--autopilot`**：分诊→补丁→自证→摘要，遇无法自证改动转人工，所有改动可一键回滚。
6. **⑥ 调用图质量红利已现**：本次为打通 P1 发现并修复了 `--gen-apply-patch` 的非法补丁 bug——同样的「函数上下文错位」也可能影响 `ai_cli task=fix` 产出的 diff 应用。建议把 `_fix_diff_function_context` 也接到 AI 补丁应用路径，统一收敛 diff 合法性。
