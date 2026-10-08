# matlabc JSON 输出结构说明（Schema）

> 对应版本：v1.16.57 ｜ 用于程序化二次消费 `--json` 输出。字段契约随版本演进，本文件与实现保持同步。`--json` 导出的快照可被 `--from-json`（P123）导入做契约校验 / 对称化重导出 / 快照报告，可经 `--from-json X --browse OUT`（P124）离线渲染为快照回放浏览站点（零源码依赖，站点内嵌 `snapshot.json` 归档副本），可经 `--diff BASE CUR`（P126）做双快照差异对比（文件/函数/类/调用边/告警五层按 key 对齐的「新增-删除-修改」，`-o` 渲染 Markdown 差异报告，`--fail-on-diff` 供 CI 基线门禁），并可经 `--fingerprint SNAP` + `--verify FP [SNAP]`（P127）做快照内容寻址指纹（整体 + 逐文件 + 告警组三层 SHA-256，忽略 `generated_at` 时间戳，`--json` 落盘指纹文件，`--verify` 防篡改校验，不一致返回退出码 1）。v1.16.9 起调用图元数据（`src/_cgdata.js` 的 `meta[].fl`）新增风险标志位 `fl:{t,hd,hi}`（污点/高复杂度/高扇入），供前端搜索风险徽章消费；v1.16.10 起 `--incr-format json` 缓存采用与指纹一致的 `{version, algorithm, entries}` 结构，增量缓存亦成为可程序化消费的契约。**v1.16.17 起** `--browse` 站点的 `src/_cgdata.js`（即 `window.__CG__`）在既有 `meta`/`down`/`up` 之外新增 `folder`/`file`/`variable` 节点类型与 `contain`（包含）/`flow`（数据·污点流）两类边，且 `down`/`up`/`contain`/`flow` 均统一为「按 gid 索引的列表」（`contain[gid]` = 该节点的子节点 gid 列表，`flow[gid]` = 与变量交互的函数 gid 列表），前端 `UNIFIED_GRAPH_JS` 与 Python 后端 P203 闭包计算共享同一索引口径，便于程序化二次消费统一图谱。**v1.16.28 起** 新增 `--benchmark [N]` 大仓库性能基准模式，输出 JSON 基准报告（字段：`version` / `synthesized_files` / `max_nodes` / `cg_node_count` / `truncated` / `elapsed_sec` / `timeout_sec` / `max_nodes_enforced` / `time_within_limit` / `benchmark_pass`），用于把 P203 的 `--max-nodes` 截断保护固化为可复现回归断言。

---

## 1. 顶层字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `version` | string | 工具版本号（如 `"1.11.51"`） |
| `generated_at` | string | 生成时间（ISO 8601）；`--reproducible` 时为空字符串 `""` |
| `root` | string | 被分析目录的路径 |
| `stats` | object | 统计概览，见 §2 |
| `edges` | array | 全部调用边（函数级），见 §3 |
| `files` | array | 每个 `.m` 文件的详情，见 §4 |
| `call_graph` | object | 调用图（出入边 + 入口 + 同名歧义），见 §5 |
| `folder_edges` | array | 目录间调用边（`--json` 时输出），见 §6 |
| `folder_cycles` | array&lt;array&lt;string&gt;&gt; | 目录循环依赖组（Tarjan SCC，`--json` 时输出），见 §7 |
| `folder_stats` | array | 目录统计（文件数/函数数/类数/内部边/跨目录出/入/入口函数，`--json` 时输出），见 §8 |
| `global_vars` | object | 跨文件 global/persistent 变量索引（C3），见 §9 |
| `field_access` | object | 跨文件结构体字段访问（读/写）聚合（C3），见 §10 |
| `constants` | array | 命名常量定义（常量折叠求值，C3），见 §11 |
| `uninitialized` | array | 疑似未初始化变量（读前无写，C3），见 §12 |
| `types` | array | 变量类型推断（标量/向量/矩阵/结构体/字符串，C3），见 §13 |
| `dead_code` | array | 死代码检测（return/break/continue 后不可达 + if 恒假，C3），见 §14 |
| `type_flow` | array | 跨函数类型流（返回值类型 + 调用方解构继承，C3），见 §15 |
| `type_mismatch` | array | 类型不一致告警（矩阵变量被赋标量等，C3），见 §16 |
| `dimensions` | array | 具体维度推断（zeros/ones/eye + 常量折叠，C3），见 §17 |
| `shape_mismatch` | array | 形状检查（矩阵乘法/加减维度约束违规，C3），见 §18 |
| `taint` | object/null | P85 污点流分析（敏感输入 → 危险输出的传播路径），见 §19；未传入且无 `calls_of` 时为 `null` |
| `doc_todos` | object/null | P86 注释完备度评估 + 函数待办清单，见 §20；未传入且无 `callers_of` 时为 `null` |
| `c_model` | object | P87 C 语言前端模型（仅 `--lang c`/`--mixed` 时输出），见 §21 |
| `c_bridge` | array | P87 MATLAB↔C 桥接调用（仅 `--mixed` 时输出），见 §22 |
| `py_model` | object | P93 Python 前端模型（仅 `--lang py` 时输出），见 §21（lang=`"py"`） |
| `js_model` | object | P93 JavaScript 前端模型（仅 `--lang js` 时输出），见 §21（lang=`"js"`） |
| `dup_code` | array | P215+ 重复代码检测（默认开；`--no-dup` 关闭）。每项见 §23：`{kind, file, func, line, similarity, saved_lines, roi, idiomatic, dup_with[]}`；P228 跨语言对 `kind="cross-lang"` 含 `file2`/`func2`；P226 通过 `--dup-baseline`/`--dup-diff` 做演化 diff |

---

## 2. `stats` 对象

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `files` | int | `.m` 文件总数 |
| `scripts` | int | 脚本文件数（无函数/类） |
| `function_files` | int | 函数文件数 |
| `class_files` | int | 类定义文件数 |
| `functions` | int | 函数/方法总数 |
| `classes` | int | 类总数 |
| `total_lines` | int | 源码总行数 |
| `internal_edges` | int | 项目内调用边总数 |
| `cross_file_edges` | int | 跨文件调用边数 |
| `cache_hits` | int | 增量缓存命中的文件数（仅 `--incremental` 时存在） |
| `cache_misses` | int | 增量缓存未命中/重新解析的文件数（仅 `--incremental` 时存在） |

---

## 3. `edges` 数组元素

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `caller` | string | 调用方标签，格式 `文件路径:函数名` |
| `callee` | string | 被调用方标签，格式 `文件路径:函数名` |
| `cross_file` | boolean | 是否跨文件调用 |

---

## 4. `files` 数组元素

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `rel` | string | 相对被分析目录的文件路径 |
| `kind` | string | 文件类型：`function` / `class` / `script` |
| `encoding` | string | 实际使用的解码编码（如 `utf-8-sig`） |
| `lines` | int | 文件总行数 |
| `parse_errors` | array&lt;string&gt; | 解析错误列表（通常为空） |
| `globals` | array&lt;string&gt; | 声明的全局变量名 |
| `classes` | array | 类定义列表，见 §4.1 |
| `functions` | array | 函数/方法列表，见 §4.2 |

### 4.1 `files[].classes[]` 元素

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 类名 |
| `line` | int | `classdef` 定义行号 |
| `superclass` | string/null | 父类名（无则为 `null`） |
| `properties` | array&lt;string&gt; | 属性名 |
| `events` | array&lt;string&gt; | 事件名 |
| `enumerations` | array&lt;string&gt; | 枚举名 |
| `methods` | array&lt;string&gt; | 方法名 |

### 4.2 `files[].functions[]` 元素

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 函数短名 |
| `qualified` | string | 完整名（含包/对象前缀） |
| `kind` | string | 类型：`main` / `local` / `method` / `constructor` / `script` |
| `line` | int | 定义行号 |
| `signature` | string | 函数签名（如 `function [y] = foo(x)`） |
| `inputs` | array&lt;string&gt; | 输入参数名 |
| `outputs` | array&lt;string&gt; | 输出参数名 |
| `variadic` | object | A2：可变参数标志 `{"varargout": bool, "varargin": bool}` |
| `header` | object | C3：结构化头部注释 `{author, date, version, description, notice, reference, inputs, outputs, calling, called_by, update_notes}`（author/date/version 缺失为 null） |
| `input_docs` | object | 输入参数说明（`{参数名: 说明字符串或 null}`，缺失为 null） |
| `output_docs` | object | 输出参数说明（`{参数名: 说明字符串或 null}`，缺失为 null） |
| `calls` | array&lt;string&gt; | 项目内被调函数（`文件路径:函数名`，已就近解析） |
| `calls_qualified` | array&lt;string&gt; | 限定名被调函数 |
| `builtin_calls` | object | MATLAB 内置调用（`{函数名: 次数}`） |
| `external_calls` | object | 未识别调用（`{函数名: 次数}`，可能外部/工具箱） |

---

## 5. `call_graph` 对象

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `nodes` | array&lt;string&gt; | 全部节点标签（`文件路径:函数名`） |
| `entries` | array&lt;string&gt; | 入口函数（无调用方的节点） |
| `outgoing` | object | 出边表 `{调用方标签: [被调标签...]}` |
| `incoming` | object | 入边表 `{被调标签: [调用方标签...]}` |
| `ambiguous` | array | 同名函数歧义，见 §5.1 |

### 5.1 `call_graph.ambiguous[]` 元素

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `caller` | string | 存在歧义调用的调用方（`文件路径:函数名`） |
| `name` | string | 被调短名 |
| `candidates` | int | 同名候选数量（>1 表示歧义） |

---

## 6. `folder_edges` 数组元素（目录级依赖）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `src` | string | 源目录（根目录以 `(root)` 表示） |
| `dst` | string | 目标目录 |
| `count` | int | 该方向的跨目录调用边数 |
| `calls` | array | 具体调用点，见 §6.1 |

### 6.1 `folder_edges[].calls[]` 元素

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `caller` | string | 调用方（`文件路径:函数名`） |
| `callee` | string | 被调用方（`文件路径:函数名`） |

---

## 7. `folder_cycles` 数组元素（目录循环依赖）

外层数组：每个元素是一个「循环目录组」（彼此形成循环依赖的目录列表，按字母序）。

| 层级 | 类型 | 说明 |
| --- | --- | --- |
| `folder_cycles[]` | array&lt;string&gt; | 一组彼此循环依赖的目录名（如 `["a", "b"]` 表示 `a ↔ b`） |

---

## 8. `folder_stats` 数组元素（目录统计）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `dir` | string | 目录名（根目录为 `(root)`） |
| `files` | int | 该目录下的文件数 |
| `functions` | int | 函数数 |
| `classes` | int | 类数 |
| `internal_edges` | int | 目录内调用边数 |
| `out` | int | 跨目录出边数（调用其他目录） |
| `in` | int | 跨目录入边数（被其他目录调用） |
| `entry_funcs` | array&lt;string&gt; | 入口函数（`文件路径:函数名`，无调用方） |

---

## 9. `global_vars` 对象（跨文件 global/persistent 变量索引，C3）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `global` | object | `{变量名: [[文件路径, 函数名, 行号], ...]}` —— 跨文件聚合的 global 声明位置 |
| `persistent` | object | `{变量名: [[文件路径, 函数名, 行号], ...]}` —— 函数内 persistent 声明位置 |

---

## 10. `field_access` 对象（跨文件结构体字段访问，C3）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `字段名` | object | `{reads: [[文件, 函数名, 行号, 基名], ...], writes: [[文件, 函数名, 行号, 基名], ...]}` |

---

## 11. `constants` 数组元素（常量折叠，C3）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 常量名（赋值左侧标识符） |
| `value` | number/string/bool | 折叠后的常量值 |
| `file` | string | 所在文件相对路径 |
| `line` | int | 定义行号 |
| `raw` | string | 原始表达式文本 |

---

## 12. `uninitialized` 数组元素（疑似未初始化变量，C3）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 变量名 |
| `line` | int | 首次「读前无写」出现行号 |
| `func` | string | 所属函数名 |
| `reason` | string | `未初始化（读前无写）` / `可能未初始化（仅条件分支赋值）` |

---

## 13. `types` 数组元素（变量类型推断，C3）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 变量名 |
| `type` | string | 推断类型：`struct`/`matrix`/`vector`/`scalar`/`string` |
| `file` | string | 所在文件相对路径 |
| `line` | int | 定义行号 |
| `func` | string | 所属函数名 |

---

## 14. `dead_code` 数组元素（死代码检测，C3）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `file` | string | 所在文件相对路径 |
| `line` | int | 死代码行号 |
| `func` | string | 所属函数名 |
| `reason` | string | 原因：`return 后不可达` / `break/continue 后不可达` / `if 条件恒假（死分支）` |

---

## 15. `type_flow` 数组元素（跨函数类型流，C3）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `caller` | string | 调用方（`文件:函数`） |
| `var` | string | 调用方接收变量名（多返回值解构的左侧变量） |
| `type` | string | 继承的类型（`struct`/`matrix`/`vector`/`scalar`/`string`） |
| `callee` | string | 被调方（`文件:函数`） |
| `output` | string | 被调方对应输出参数名 |
| `line` | int | 调用行号 |

---

## 16. `type_mismatch` 数组元素（类型不一致告警，C3）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 变量名 |
| `func` | string | 所属函数名 |
| `file` | string | 所在文件相对路径 |
| `from_type` | string | 首次推断类型 |
| `to_type` | string | 后续推断类型（不一致） |
| `from_line` | int | 首次赋值行号 |
| `line` | int | 冲突赋值行号 |

---

## 17. `dimensions` 数组元素（具体维度推断，C3）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 变量名 |
| `file` | string | 所在文件相对路径 |
| `line` | int | 定义行号 |
| `func` | string | 所属函数名 |
| `dims` | array&lt;int&gt; | 维度列表（任意维，如 `[4,4,8]`） |
| `rows` | int | 行数（仅二维时输出，向后兼容） |
| `cols` | int | 列数（仅二维时输出，向后兼容） |

---

## 18. `shape_mismatch` 数组元素（形状检查，C3）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `op` | string | 运算符（`*` / `+` / `-`） |
| `file` | string | 所在文件相对路径 |
| `line` | int | 行号 |
| `func` | string | 所属函数名 |
| `lhs` | string | 左操作数变量名 |
| `rhs` | string | 右操作数变量名 |
| `lhs_dims` | array&lt;int&gt; | 左操作数维度 |
| `rhs_dims` | array&lt;int&gt; | 右操作数维度 |

---

## 19. `taint` 对象（P85 污点流分析）

沿调用图反向传播的敏感数据流门禁。数据格式见 `_propagate_taint`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `flows` | array | 受污函数流列表，见 §19.1 |
| `stats` | object | 统计：`total`（受污函数总数）、`direct`（直接调用汇）、`propagated`（反向传播）、`danger_entries`（危险入口数）、`sink_calls`（汇调用点总数）、`source_calls`（源调用点总数）、`covered_files`（涉及文件数）、`exact`（P88 变量级精确命中数）、`var_flows`（P88 变量传播边数） |

### 19.1 `taint.flows[]` 元素

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `rel` | string | 所在文件相对路径 |
| `func` | string | 函数名 |
| `line` | int | 汇调用行（direct）或函数定义行（propagated） |
| `level` | int | 传播深度（direct 为 1，反向传播逐级 +1，封顶 5） |
| `kind` | string | `direct`（体内直接调用汇）/ `propagated`（沿调用图反向传播） |
| `sinks` | array&lt;string&gt; | 命中的危险汇函数名（如 `fprintf`/`save`/`system`/`eval`） |
| `sources` | array&lt;string&gt; | 命中的敏感源函数名（如 `input`/`fopen`/`webread`） |
| `path` | array&lt;string&gt; | 传播路径（`[当前函数, ..., 直接受污函数]`） |
| `has_inputs` | bool | 是否有输入参数或为脚本（外部输入可流入） |
| `vars` | array&lt;string&gt; | P88 受污变量集合（源赋值 lhs + 赋值传播 + 实参→形参映射后） |
| `field_taint` | array&lt;string&gt; | P95 字段级受污链集合（如 `["s.name"]`；`s.name = input(...)` 只标记字段受污，不污染整根 `s`） |
| `var_sources` | array | P88 变量级源赋值 `[{line, vars, source}]`（`vars` 为该行 lhs 变量列表，如 `n ← input`） |
| `exact_sinks` | array | P91/P95 精确命中汇调用 `[{line, call_line, sink, args, arg_fields, vars, hits, param_indices}]`——`args` 为「每实参变量列表」（`[[], ["n"]]`，字符串/常量实参为空列表），`arg_fields` 为「每实参字段链列表」（P95，如 `[[], ["s.name"]]`），`hits` 为 `[{var, param_index, field}]`（`field=True` 表示字段级命中，`param_index` 为真实参数位 0-based），`param_indices` 为命中参数位数组 |
| `exact` | bool | P88 是否存在变量级/字段级精确命中（区别于仅函数级） |

---

## 20. `doc_todos` 对象（P86 注释完备度评估）

数据格式见 `_collect_doc_todos`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `todos` | array | 待办清单，见 §20.1 |
| `stats` | object | 统计：`total_funcs`（函数总数）、`need_doc`（需补注释数）、`high`/`medium`/`low`（各级优先级数）、`critical`（P89 联合紧急数）、`tainted`（P89 受污函数数）、`avg_score`（平均文档分）、`done`（P92 `% analyzer:done` 已处理数，不计入待办） |

### 20.1 `doc_todos.todos[]` 元素

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `rel` | string | 所在文件相对路径 |
| `func` | string | 函数名 |
| `line` | int | 定义行号 |
| `kind` | string | 函数类型（`main`/`local`/`method`/`constructor`） |
| `complexity` | int | 圈复杂度 |
| `fan_in` | int | 扇入（被调用次数） |
| `fan_out` | int | 扇出（体内调用数） |
| `doc_score` | int | 文档分（100 起扣，缺 description -30、输入 -10/个、输出 -10/个、author -10、version -10，下限 0） |
| `missing` | array&lt;string&gt; | 缺失项（`description`/`input:x`/`output:x`/`author`/`version`） |
| `priority` | string | 优先级：`high`（复杂度≥8 且扇入≥2 且分<70）/ `medium`（复杂度≥5 且有调用方且分<85）/ `low` |
| `tainted` | bool | P89 是否在污点流中（与 `taint.flows[]` 的 `(rel, func)` 匹配） |
| `joint_priority` | string | P89 联合优先级：受污时 `high`→`critical`/`medium`→`high`/`low`→`medium`，否则等同 `priority` |
| `doc_suggestion` | string | P89 补文档建议（按缺失项逐条给出可粘贴的注释模板） |
| `test_suggestion` | string | P89 补测试建议（按复杂度/扇入/输入输出列出的测试点清单） |

> 说明：`--todo-export FILE` 把 `todos[]` 导出为行动单 JSON——顶层含 `version`/`generator`/`count`/`summary`（`critical`/`tainted`/`done` 计数）与 `actions[]`（每项含上述全部字段），可直接对接任务系统。`--todo-base FILE` 传入基线行动单时，输出顶部追加 `diff` 对象：`{resolved: [{file, func}...], added: [...], kept: [...]}`（按 `(file, func)` 键对比）与 `completion_rate`（resolved / resolved+added 的完成率，保留 3 位小数）。

---

## 21. `c_model` 对象（P87 C 语言前端模型）

仅 `--lang c` / `--mixed` 模式输出。数据格式见 `render_json`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `lang` | string | 固定 `"c"` |
| `files` | array | C 文件详情，见 §21.1 |
| `edges` | array | 内部调用边 `[{caller, callee, line, file}]` |
| `include_edges` | array | P90 `#include` 跨文件依赖边 `[{from, include, to}]`，`to` 为项目内解析到的文件 rel，`null` 表示系统库/项目外未解析 |
| `unresolved` | array | 未解析调用 `[{callee, line, file}]` |
| `heuristics` | array | P90/P93 静态启发式检查 `[{file, line, func, kind, msg, level}]`（`--checks` 开启；C kind ∈ `c_unused_static`/`c_missing_guard`/`c_too_many_params`/`c_missing_doc`/`c_uninit_pointer`/`c_array_oob`/`c_use_after_free`/`c_missing_return`；Python kind ∈ `py_unused_import`/`py_dup_params`/`py_too_many_params`/`py_missing_doc`；JS kind ∈ `js_unused_import`/`js_global_var`/`js_too_many_params`/`js_missing_doc`） |

### 21.1 `py_model` / `js_model` 对象（P93 Python/JavaScript 前端模型）

仅 `--lang py` / `--lang js` 模式输出，与 `c_model` 同构（`lang` 分别为 `"py"`/`"js"`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `lang` | string | 固定 `"py"` 或 `"js"` |
| `files` | array | 源文件详情，字段与 §21.2 对齐（`rel`/`functions[]`；`functions[].params`/`calls`/`line`） |
| `edges` | array | 内部调用边 `[{caller, callee, line, file}]` |
| `import_edges` | array | `import`/`require` 跨文件依赖边 `[{from, imp, to}]`，`to` 为项目内解析到的文件 rel，`null` 表示第三方/未解析 |
| `unresolved` | array | 未解析调用 `[{callee, line, file}]` |
| `heuristics` | array | 启发式检查（同 `c_model.heuristics`；Python kind ∈ `py_unused_import`/`py_dup_params`/`py_too_many_params`/`py_missing_doc`；JS kind ∈ `js_unused_import`/`js_global_var`/`js_too_many_params`/`js_missing_doc`） |

### 21.2 `c_model.files[]` 元素

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `rel` | string | 相对路径 |
| `includes` | array&lt;string&gt; | `#include` 头文件列表 |
| `macros` | array | 宏定义 `[{name, value, line}]` |
| `functions` | array | 函数列表，见 §21.2 |

### 21.2 `c_model.files[].functions[]` 元素

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 函数名 |
| `line` | int | 定义行号 |
| `returns` | string | 返回类型 |
| `params` | array&lt;string&gt; | 参数列表 |
| `complexity` | int | 圈复杂度（if/for/while/switch/case 计数） |
| `calls` | array | 体内调用 `[函数名, 行号]` |

---

## 22. `c_bridge` 数组（P87 MATLAB↔C 桥接调用）

仅 `--mixed` 模式输出。数据格式见 `_match_c_bridge`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `matlab` | string | MATLAB 函数名 |
| `mfile` | string | MATLAB 文件相对路径 |
| `c_file` | string | 被调 C 函数所在文件相对路径 |
| `c_func` | string | 被调 C 函数名 |
| `count` | int | 调用次数 |

---

## 23. `dirs` 对象（P100 目录树模型）

顶层新增键 `dirs`（P100 起）：按文件夹分层聚合的目录树，对标 Doxygen Files 导航。由 `_build_dir_tree` 生成：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 目录名（根为 `"(root)"`，子目录为 basename） |
| `path` | string | 目录相对路径（根为 `""`，`/` 分隔） |
| `files` | array | 直属文件 `[{rel, name, funcs, lines, complexity, kind}]`（不含子目录文件） |
| `children` | array | 子目录节点（同构递归，DFS 有序） |
| `metrics` | object | `{funcs, lines, complexity}`——本目录及全部后代文件的聚合度量（沿路径累加） |

## 24. `files_graph` 对象（P101 文件依赖图）

顶层新增键 `files_graph`（P101 起）：跨文件函数调用聚合为文件级依赖，用于变更影响评估。由 `_build_file_dep_graph` 生成：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `键` | string | 文件相对路径（`/` 分隔） |
| `值.deps` | array&lt;string&gt; | 本文件直接调用的其他文件（跨文件调用目标，去重排序） |
| `值.dependents` | array&lt;string&gt; | 直接调用本文件的其他文件（反向引用） |

> 说明：仅统计跨文件调用（同文件内部调用不计数）；`calls_of` 缺失时整个 `files_graph` 为 `{}`。与 `--browse` 站点的目录依赖矩阵共用同一份数据源。

---

## 25. 注意事项

- `folder_edges` 仅在通过 CLI `--json` 输出时存在（`main` 传入 `calls_of`）；直接调用 `render_json` 不传 `calls_of` 时省略该字段。
- `generated_at` 在 `--reproducible` 下为空字符串，使两次运行输出逐字节一致。
- `edges` 与 `call_graph` 的节点标签统一使用 `文件路径:函数名` 格式（`/` 分隔路径，无盘符）。
- 同名函数按「同文件 → 同目录 → 其余路径序」就近解析，歧义通过 `call_graph.ambiguous` 与 `files[].functions[].calls` 的实际指向体现。
- `--export-doxygen-xml OUTDIR`（P112）输出的 Doxygen 兼容 XML 与 `--json` 的 `dirs/files_graph` 同源：`index.xml` 列出全部文件 compound，每文件 XML 含函数 `memberdef`（`name`/`argsstring`/`location`）。

## 26. `dup_code` 数组（P215+ 重复代码检测）

默认开启（`--no-dup` 关闭），跨函数/跨文件/语义级（P224）/跨语言（P228）重复均落入此数组。每项字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `kind` | string | `"function"`（整函数重复）/`"fragment"`（片段级重复）/`"cross-lang"`（P228 MATLAB↔Python 跨语言 IR 重复） |
| `file` | string | 主体函数所在文件（跨语言时为 MATLAB 端） |
| `func` | string | 主体函数名 |
| `line` | int | 主体函数起始行 |
| `similarity` | number | 相似度 0~1（语义归一化后 Jaccard/连续片段加权，P224） |
| `saved_lines` | int | 若提取公共函数可消除的行数（P225） |
| `roi` | number | 重构 ROI = `saved_lines × (出现次数−1) ÷ 提取复杂度`（P225）；P227 惯用法误报折减 25% |
| `idiomatic` | bool | P227 标记：主要由 MATLAB 标准惯用法（zeros/for/isempty/...）构成，疑似样板误报，看板灰显 |
| `idiom_ratio` | number | P227 惯用法行占比（0~1） |
| `frags` | array | 片段级重复精确行区间 `[{start,end},{start,end}]`（P216） |
| `dup_with` | array | 重复对列表 `[{file, func, line}...]`（同语言） |
| `file2` / `func2` | string | 仅 `kind="cross-lang"`：跨语言对端文件/函数（Python 端） |

演化追踪（P226）：`--dup-baseline PATH` 指定基线（默认 `<root>/.dup_baseline.json`）；`--dup-update-baseline` 运行后追加历史快照（含 `new/gone/drift/total` 计数序列）；`--dup-diff` 打印 `new`（新增）/ `gone`（消失=已重构）/ `drift`（相似度下降>0.05 分叉）三类。`--dup-trend-svg OUT.svg`（P229）读取历史序列绘制四线趋势 SVG。`--no-dup-semantic`（P224）可回落纯结构指纹，`--py-dir DIR`（P228）指定 Python 目录做跨语言比对。

### 26.1 `--global-state` 看板 dup tab 交互化（P217b, v1.16.43）

`--global-state OUT.html` 生成的全局状态图看板，其「重复代码」tab（P217）升级为交互式（零依赖原生 JS，兼容 Python 3.6 生成约束）：
- **排序**：表头点击按相似度/ROI/文件名排序（升/降切换），下拉框 `dup-sort` 亦可选择。
- **搜索**：`dup-q` 搜索框实时按 文件/函数名（含跨语言对端 `file2`/`func2`）过滤。
- **筛选 chip**：`全部 / 跨语言 / 惯用法样板 / 片段级` 四类一键切换（`data-f` 属性驱动 `__dup_fchip`）。
- **分页**：`per=12` 分页（`__dup_go`），大重复集不卡顿。
- **趋势 tab（P229 内嵌）**：当 `--dup-baseline` 指向的基线含 ≥2 条历史时，看板新增「演化趋势」tab（`tab-t`），内嵌 `__render_trend` 以原生 SVG 绘制 new/gone/drift/total 四线；支持**数据点 hover tooltip**（显示快照时间与该点四项计数）与**图例点击显隐**单条线（`__trend_toggle`）。趋势数据经 `_dup_load_trend` 从基线条带读入并注入看板 `__GS__.dup_trend`。
- **修复**：原 P204 看板中 `onmouseover="fn(\'var\')"` 在 Python 三重引号模板里生成字面 `\'` 导致浏览器 `SyntaxError`，已全部改为 `this.getAttribute('data-var')` 数据属性传递（`__gs_link_conflict_var` / `__gs_link_dup_var` / `__gs_drill` / `__trend_toggle` / `__dup_fchip`）。
- **行内嵌并排 diff（P217d, v1.16.44）**：分析阶段对每条 dup 记录用 `_dup_side_by_side`（difflib.SequenceMatcher）预生成两端函数体行级 diff，作为 `diff` 字段**仅注入 `--global-state` 看板数据层（`__GS__.dup_code[i].diff`），不进入 `--json` 出口**。结构：`diff = {a:{file,func,rows:[[type,no,text],...]}, b:{...}, stats:{eq,diff,del,ins}}`，`type ∈ eq/rep/del/ins`。看板每行「＋」按钮经 `__dup_toggle_diff(gi)` 内嵌渲染并排视图（左A右B四色标注，sticky 头部显示四计数）。
- **暗色主题 + 视图持久化（P217c, v1.16.44）**：看板 tabs 新增 🌙/☀ 切换（`__gs_toggle_theme`，`[data-theme="dark"]` GitHub Dark 语义轻量覆盖）；搜索词/排序/筛选/tab 经 `localStorage`（`gs-view` / `gs-theme`）持久化，刷新即恢复。
- **前端 JS 自动校验（P217g, v1.16.44）**：`test_p217g_frontend_js_sanity` 抽取生成 HTML 的 `<script>` 做 `node --check` 真语法校验（+ 纯 Python 降级断言「不含字面 `\'`」），把 JS 模板改动纳入 CI 回归守护，杜绝转义 bug 静默回归。
- **一键生成共享函数脚手架（P217i, v1.16.45）**：每条 diff 头部「📋 生成共享函数」按钮（`__dup_build_scaffold`）从 `__GS__.dup_code[i].diff` 现场提取公共体（eq 行）为 `shared_<func>` 主体、rep 行标 `DIFF 抽象点`、del/ins 注释保留，生成 `function [out] = shared_<func>(varargin)` 骨架 + 两端调用方改写建议，弹窗（`__dup_show_modal`）预览并支持复制（navigator.clipboard + execCommand 降级）。把「诊断（diff）」直接转化为「消除（重构脚手架）」动作，闭合 dup 体系最后一环。
- **跨 tab 跳转（P217e, v1.16.46）**：dup 行与 diff 头部「🔗」链接 `__gs_open_src(file,func)` → `src/<rel>.html#hs-<func>`，跳 `--browse` 源码站并定位函数卡（`hs-<func>` 锚点由 P124 源码页提供），看板与源码站双向闭环。
- **趋势下钻（P217f, v1.16.46）**：趋势 SVG 点 click 委托 `__trend_drill(i)`，从基线 history `pairs` 计算该快照相对前驱的 new/gone/drift 函数对，弹窗明细（`__dup_show_modal` + `isHtml`）。
- **批量脚手架（P217l, v1.16.46）**：`dup_roi_top` 注入时同步携带 `_dup_rows` 的 diff（`_dup_rows_idx` 按 (file,func,line) 取），ROI 表头「📦 批量生成」`__dup_batch_scaffold` 复用 `__dup_make_scaffold` 核心，聚合 `batch_shared_<N>.m` 可复制。
- **AST 差异变量识别（P217k, v1.16.46）**：`__dup_diff_tokens` 词法级抽取 rep 行两端差异标识符，脚手架标注「差异参数候选」+ 参数化提示（`varargin{N}`），半自动、安全，为深度 AST 改写奠基。
- **全站主题统一（P217j, v1.16.46）**：`--browse` 的 `GLOBAL_SEARCH_JS` 读取 `gs-theme`（与 `--global-state` 共用 localStorage key），跨站共享暗色偏好。
- **AST 精确签名（P217m, v1.16.47）**：dup diff 数据注入 `signature: {in:[参数…], out:输出变量}`（P221 AST 推断两端输入输出一致时的精确参数名）；脚手架 `__dup_make_scaffold` 优先生成 `function [out] = shared_<func>(in…)` 真实签名，否则回落 varargin（半自动）。
- **CI 门禁（P217n, v1.16.47）**：`--dup-fail-gate SPEC`（`MAX_TOTAL` / `MAX_TOTAL:MAX_NEW` / `%RATE` + `warn:` 前缀），独立接入主流程 `ok` 退出码；配合 `--dup-baseline` 实现增量重复率门禁。
- **重构影响分析（P217p, v1.16.47）**：dup diff 注入 `callers: {a:[{rel,fn,line}…], b:[…]}`（反向 callsite 扫描），脚手架调用建议列出"改完 shared 后需同步修改的调用方"。
- **关系图（P217q, v1.16.47）**：全局状态图 dup tab 新增「关系图」（`__render_dup_graph`），力导向布局（节点=函数/边=重复对），节点点击跳源码站（P217e）。
- **组织级指纹库（P217o, v1.16.47）**：`--dup-org-baseline` 加载可共享 `.dup_baseline.json`，命中的重复对标 `org_match=true`（看板 🌐组织已知 + `org` chip 过滤），跨项目/团队识别通行重复。
- **自动补丁生成（P217r, v1.16.48）**：`--dup-emit-patch OUT.patch` 产出完整可执行重构补丁（git apply 兼容）= 共享函数新建 + 两端主体替换 + **全部调用点同步改写**（`fooA(` → `shared_fooA(`，文本级全文件 callsite 扫描）。补丁经 `_normalize_unified_diff` 规范化 hunk 头（修 P214 `lineterm=""` 导致的 `@@ ... @@` 粘连，否则 git apply 拒收）。
- **PR 门禁报告（P217s, v1.16.48）**：`--dup-pr-report OUT.md` 产出 Markdown 评审报告（总览/重复率 + 相对基线的 新增·已修复·漂移明细 + ROI 可消除行数估算 + 重构优先级 Top-N + 一键重命令），供 CI 机器人贴 PR 评论；无基线时优雅降级。
- **补丁自证验证（P221s, v1.16.49）**：`--dup-verify-patch IN.patch` 在**临时副本**上应用补丁后重跑完整分析，校验四项不变量（补丁可应用 / 重复对减少 / 不引入新告警 / 调用边不丢），输出 `DUP-VERIFY-PASS` / `DUP-VERIFY-FAIL`（验证失败退出码非零，可阻断 CI）；`--dup-verify-report OUT.md` 出对比报告；`--dup-verify-apply` 仅在验证通过后落盘（"要么安全重构、要么完全不动"）。绝不污染源码树。
- **语义等价性验证（P217y, v1.16.50）**：`--dup-verify-equiv OUT.md` 静态证明「提取共享函数不改变程序行为」（无需执行 MATLAB）。四项检查：**C1 调用一致性**（识破 `foo()` vs `bar()` 这类「指纹相同但语义不同」的假重复——结构指纹会把未解析函数名归一化为 `<V>`）/ **C2 输出契约一致** / **C3 参数映射完备** / **C4 副作用扫描**（I/O、eval、global 等）。判定：`EQUIVALENT` 等价 · `PARTIAL` 部分等价 · `REVIEW` 建议复核 · `UNSOUND` 不等价。配 `--dup-verify-patch` 时自动附带等价性章节；`--dup-strict-equivalence` 令 UNSOUND 阻断 CI。
- **补丁冲突合并（P217z, v1.16.50）**：多对重复同时重构时，同一文件可能既被「主体 hunk」改写又被「调用点 hunk」改写，区间重叠会让 `git apply` 整体拒收。`--dup-emit-patch` 自动检测重叠并合并为单一 diff（重叠删除取并集、插入按序拼接，语义不丢失）；无重叠时零改动（幂等）。
- **两处真实缺陷修复（v1.16.50）**：① `_dup_shared_func_src` 在 `n_diff>0` 时因 `%` 优先级高于 `+` 导致 `"% TODO"` 被当作格式符而必抛 `ValueError`（补丁静默不生成）；② `_dup_extract_common_lines` 仅凭指纹判定公共行，使 `y = foo(x);` 与 `y = bar(x);` 被误判为同一行，共享函数会静默采用 A 端版本 → **B 端行为被悄悄改写**；现增加「调用位置标识符」比对，不同则保守判为差异行并保留在各自函数体内。
- **增量索引与评分缓存（P217x, v1.16.49）**：`--dup-cache [CACHE.json]`（默认 `.dup_token_cache.json`）缓存两类纯函数结果——① 文件级函数 token 序列（按内容 SHA-256 + size 签名，内容寻址，git checkout/换机器仍可命中）；② dup 对的 idiom 惯用法评分（按主体源文本 SHA-256，profile 显示此为该阶段最大热点，占 63%）。缓存是**纯优化**：启用前后 `(file, func, similarity, idiomatic, roi)` 逐条相同；文件变更自动失效。实测端到端加速 **3.5x**。派生文件 `<CACHE>.idiom.json` 存评分缓存。
