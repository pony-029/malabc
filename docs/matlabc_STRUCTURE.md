# matlabc.py 代码结构索引

> 自动生成，用于快速定位代码位置（行号可能随改动偏移，重新生成即可）。

- **版本**: 1.16.57
- **总行数**: 17570

## 顶层常量 / 正则 / 大块数据

| 名称 | 行号 | 内容预览 |
| --- | --- | --- |
| `VERSION` | 58 | "1.16.57" |
| `DEFAULT_EXCLUDE` | 56 | {".git", ".svn", ".hg", "__pycache__", "node_modules"} |
| `MATLAB_BUILTINS` | 61 | set(""" |
| `MATLAB_BUILTIN_DOCS` | 130 | { |
| `MATLAB_KEYWORDS` | 611 | set(""" |
| `RE_FUNC_START` | 620 | re.compile(r"^\s*function\b", re.IGNORECASE) |
| `RE_CLASSDEF` | 621 | re.compile( |
| `RE_BLOCK` | 625 | re.compile(r"^\s*(?P<blk>properties\ |
| `RE_CTRL` | 626 | re.compile(r"^\s*(?P<blk>if\ |
| `RE_END` | 627 | re.compile(r"^\s*end\b", re.IGNORECASE) |
| `RE_CALL` | 628 | re.compile(r"(?<![\w\.])@?([A-Za-z]\w*)\s*\(") |
| `RE_MULTI_ASSIGN` | 630 | re.compile(r"\[\s*([^\]]+?)\s*\]\s*=\s*(... |
| `RE_METHOD_CALL` | 631 | re.compile(r"(?<!\w)([A-Za-z]\w*)\s*\.\s*([A-Za-z]\w*)\s*\(" |
| `RE_COMMAND_ARGS` | 634 | re.compile(r"^\s*([A-Za-z]\w*)\s+([A-Za-z0-9_'\".@])") |
| `RE_COMMAND_BARE` | 635 | re.compile(r"^\s*([A-Za-z]\w*)\s*$") |
| `RE_HANDLE` | 638 | re.compile(r"@([A-Za-z]\w*)") |
| `RE_FEVAL_STR` | 644 | re.compile( |
| `RE_DYNAMIC` | 648 | re.compile(r"\b(eval\ |
| `RE_IDENT` | 649 | re.compile(r"[A-Za-z_]\w*") |
| `RE_PROP` | 650 | re.compile(r"^\s*(?P<name>\w+)") |
| `M_EXTS` | 653 | (".m",) |
| `TODO_JS` | 3109 | """ |
| `FRONTEND_REGISTRY` | 3517 | {}   # lang -> Frontend 类（register_front... |
| `TAINT_JS` | 4715 | """ |
| `HTML_CG_CSS` | 5675 | """ |
| `MAX_CALLGRAPH_DEPTH` | 6001 | 4 |
| `MAX_CALLGRAPH_NODES` | 6002 | 60 |
| `MAX_TAINT_DEPTH` | 3222 | 5   # P94 修复：污点反向传播深度上限（此前 _propagate_taint 引用未定义常量） |
| `_RE_C_CX` | 3736 | re.compile(r"\b(?:if\|for\|while\|switch\|case\|else\|do\|catch)\b"...  # P96 C 分支关键字 |
| `_RE_BRANCH` | 9274 | re.compile(...  # P96 MATLAB 分支关键字（if/for/while/switch/case 等） |
| `BROWSE_CSS` | 6825 | """（含暗色、折叠树、语法高亮 + P103 面包屑、P105 源码大纲、P104 详情页、P111 雷达、P107 搜索浮层、P108 响应式、P112 打印） |
| `BROWSE_JS` | 7270 | 索引页交互 JS（tab/过滤/排序/主题切换/SEARCH_DATA 全文搜索） |
| `GLOBAL_SEARCH_JS` | 7389 | P107/P108：全站函数搜索浮层（Ctrl+K / `/`）+ 键盘导航（↑↓/Enter/Esc/t 主题）+ 源码大纲 scrollspy，由 src/_search.js 注入 |
| `GRAPH_JS` | 7421 | """ |
| `VARFLOW_JS` | 7060 | """ |
| `MATHJAX_INIT_JS` | 7218 | ( |
| `LOCALCG_INIT_JS` | 7224 | """ |
| `DIRMATRIX_JS` | 10735 | """ |

## 模块级函数 / 类

| 类型 | 名称 | 行号 | 说明 |
| --- | --- | --- | --- |
| def | `matlab_builtin_desc` | 545 | 返回 MATLAB 内置/工具箱函数的中文说明。 |
| def | `collect_used_builtins` | 562 | 汇总项目源码中实际调用的 MATLAB 内置函数（name -> 调用次数），按次数降序返回列表。 |
| def | `render_matlab_builtin_section` | 574 | 返回「MATLAB 内置库函数说明」HTML 片段（标题 + 表格）。 |
| def | `render_matlab_lib_page` | 591 | 生成独立的「MATLAB 内置库函数说明」页面（--browse 模式专用）。 |
| def | `_tail_nonspace` | 659 | 返回列表 out 末尾最多 k 个非空白字符（保持原顺序），用于区分「转置运算符」与「字符串引号」。 |
| def | `scrub_source` | 671 | 把注释、字符串内容替换为空格，保留换行，便于后续正则解析。 |
| class | `MatlabFunction` | 773 |  |
| def | `_parse_header_comments` | 865 | 从函数定义行上方的 % 注释块中提取结构化信息。 |
| def | `_parse_file_header` | 1133 | C3：解析文件顶部注释块（第一个 function/classdef 之前的注释）， |
| class | `MatlabClass` | 1148 |  |
| class | `MatlabFile` | 1164 |  |
| def | `_empty_fn_header` | 1193 | P113：函数头部结构化注释的完整默认结构（与 _parse_header_comments 对齐）。 |
| def | `_FN_CONTRACT` | 1203 | P113：MatlabFunction 必需属性契约（key -> 默认值或默认值 factory）。 |
| def | `_CLASS_CONTRACT` | 1231 | P113：MatlabClass 必需属性契约。 |
| def | `_MFILE_CONTRACT` | 1244 | P113：MatlabFile 必需属性契约（含 header/brief 渲染落点）。 |
| def | `_coerce_fn` | 1261 | P113：补齐 MatlabFunction 缺失/为 None 的属性为契约默认值（就地，幂等）。 |
| def | `_coerce_class` | 1269 | P113：补齐 MatlabClass 缺失属性，并递归契约化其 methods。 |
| def | `_coerce_mfile` | 1279 | P113：补齐 MatlabFile 缺失属性，并递归契约化 functions/classes。 |
| def | `coerce_analysis_files` | 1291 | P113：统一契约化入口——对一批文件对象就地补齐默认属性（幂等），build_analysis_model 与三个渲染函数双防线调用。 |
| def | `_PY36_RULES` | 1317 | P114：Python 3.6 语法门禁规则表（12 条：rule_id/名称/所需版本/级别/正则/说明，覆盖 walrus/posonly/f-string 调试/match/case/内置泛型下标/新标准库 API）。 |
| def | `_py36_check_ast` | 1358 | P114：AST 通道——3.6 解释器 ast.parse 解析；3.7+ 新语法直接 SyntaxError 记为 parse_error。 |
| def | `_py36_blank_token` | 1378 | P114：把单个 STRING/COMMENT/FSTRING token 区间替换为等长空白（支持跨行字符串）。 |
| def | `_py36_extract` | 1394 | P114：tokenize 词法级剥除字符串/注释/FSTRING_* 为等长空白，并收集 f-string 原文（重建 FSTRING_START..END 区间）供专属规则扫描。 |
| def | `_py36_check_regex` | 1438 | P114：正则通道——阶段 A 对 f-string 原文检测调试表达式/反斜杠，阶段 B 对剥除后代码逐行扫描其余 10 条规则。 |
| def | `_py36_discover_targets` | 1473 | P114：把 --check-py36 目标（目录/单 .py 文件）展开为 *.py 路径列表（递归 + DEFAULT_EXCLUDE 排除）。 |
| def | `check_py36_compat` | 1500 | P114：执行 Python 3.6 语法门禁，返回 (issues, stats)；缺省自检（工具自身 + tests/）。 |
| def | `parse_arg_list` | 1547 | 从 'a, b{1}, c.d, ~, varargin' 提取参数名（最后一个标识符）。 |
| def | `parse_function_line` | 1200 | 解析 function 定义行，返回 (qualified_name, outputs, inputs) 或 None。 |
| def | `_top_function` | 1229 | 返回解析栈中最近的 function 元素（MatlabFunction），无则 None。 |
| def | `_detect_end_style` | 1241 | P49：预扫描判定文件是否「显式 end 风格」（函数/方法以 end 显式结束）。 |
| def | `parse_file` | 1257 |  |
| def | `_logical_statements` | 1452 | 把 scrubbed[start-1:end] 中 `...` 续行合并为逻辑语句，返回 [(起始行号, 合并文本), ...]。 |
| def | `analyze_calls` | 1479 | 在函数体内匹配调用，建立项目内调用边 + 内置/外部调用统计。 |
| def | `resolve_call` | 1599 | 返回调用目标的具体函数对象（MatlabFunction），否则 None。 |
| def | `render_tree` | 1630 | 生成目录树文本。files: [(rel, kind)] |
| def | `_timestamp` | 1655 | P51：返回输出时间戳字符串；reproducible=True 时返回空串（可复现构建）。 |
| def | `render_markdown_report` | 1660 | 生成 Markdown 结构报告。callers_of/calls_of 可选：传入后追加「关键函数风险度量」表（P30 |
| def | `build_call_graph` | 1880 | 从边列表构建有向图邻接表。返回 (出边表, 入边表, 所有节点集合)。 |
| def | `render_call_chain` | 1893 | 生成「从入口到末端」的调用树文本行列表（树形缩进，标注调用层级）。 |
| def | `render_call_detail` | 1931 | 逐函数列出：它调用了谁、被谁调用（双向关系）。 |
| def | `_mermaid_label` | 1968 | Mermaid 节点 label 转义（反斜杠与引号）。 |
| def | `_dot_label` | 1973 | Graphviz DOT 字符串转义（反斜杠与引号）。 |
| def | `render_mermaid` | 1978 | 生成 Mermaid flowchart。file_graph=文件级聚合；folder_graph=文件夹级聚合（P57）。 |
| def | `render_dot` | 2028 | 生成 Graphviz DOT 文件。file_graph=文件级聚合；folder_graph=文件夹级聚合（P57）。 |
| def | `_collect_global_vars` | 2063 | C3：聚合跨文件 global/persistent 变量（跨文件数据流基础）。 |
| def | `_collect_field_access` | 2081 | C3：收集每个函数的结构体字段访问（obj.field 的读/写，函数内粒度）。 |
| def | `_collect_cross_file_fields` | 2125 | C3：跨文件聚合结构体字段访问（读/写），追踪字段在函数间的传播。 |
| def | `_try_eval_const` | 2154 | C3：安全求值 MATLAB 常量表达式，返回 (value, ok)。 |
| def | `_collect_constants` | 2195 | C3：收集命名常量定义（NAME = 常量表达式）并折叠求值。 |
| def | `_collect_file_constants` | 2205 | C3：收集单文件命名常量（供 _collect_constants 聚合 + 增量缓存复用）。 |
| def | `_infer_type` | 2237 | C3：从变量名 + 赋值 RHS 推断基础类型。 |
| def | `_collect_types` | 2264 | C3：收集函数内变量的基础类型推断。 |
| def | `_infer_func_output_types` | 2306 | C3：推断函数输出参数的类型（从函数体内 `output = rhs` 赋值形态）。 |
| def | `_collect_type_flow` | 2339 | C3：跨函数类型流——函数返回值类型推断 + 调用方解构继承传播。 |
| def | `_taint_regexes` | 2407 | 懒构造「源/汇」调用正则（大小写不敏感，匹配 `name (` 跨空白调用）。 |
| def | `_collect_taint_call_sites` | 2421 | P85：扫描每个函数体，收集「污点源 / 污点汇」调用点。 |
| def | `_mask_code_spans` | 2450 | P88：把 tokenize 结果中的注释/字符串 span 替换为空格，其余字符原样保留。 |
| def | `_scan_paren_block` | 2463 | P88：从 open_idx（应指向 '('）扫描到匹配的 ')'，返回括号内文本。 |
| def | `_split_top_level_args` | 2482 | P88：按顶层逗号分割实参文本（忽略括号内的逗号）。返回实参列表。 |
| def | `_vars_in_expr` | 2503 | P88：从表达式提取变量名（排除纯数字与 MATLAB 关键字/常量）。 |
| def | `_extract_lhs_vars` | 2516 | P88：从赋值 '=' 位置往前提取 lhs 变量列表。 |
| def | `_collect_var_taint_sites` | 2539 | P88：变量级污点站点收集——源赋值 / 汇实参 / 赋值传播 / 调用实参。 |
| def | `_field_chains_in_expr` | 2539 | P95：从表达式提取全部字段链（如 s.a.b → ["s.a.b"]），供字段级污点判定。 |
| def | `_extract_lhs_fields` | 2556 | P95：从赋值 LHS 提取「字段受污目标」（s.name 形式）。 |
| def | `_chain_effectively_tainted` | 2570 | P95：判定字段链是否被 field_taint 集 / 整根变量集有效覆盖。 |
| def | `_propagate_var_taint` | 2658 | P88：变量级污点传播——在函数级 flows 基础上细化到「哪个变量受污」。 |
| def | `_parse_taint_gate` | 2757 | P91：解析 --taint-gate "sink:idx[,sink:idx...]"。 |
| def | `_taint_gate_violations` | 2783 | P91：参数位门禁——统计「受污变量流入指定汇的指定实参」的违例。 |
| def | `_propagate_taint` | 2808 | P85：沿调用图传播污点，生成污点流报告。 |
| def | `_parse_rule_max` | 2931 | P94：解析 --max-warnings-by-rule "rule:N,..." 为规则阈值 dict。 |
| def | `_count_by_rule` | 2955 | P94：按规则统计告警数（checks_for_sarif → {rule: n}）。 |
| def | `_rule_gate_violations` | 2973 | P94：规则级门禁违例——告警数超过该规则阈值则记录。 |
| def | `_parse_gate_file` | 2984 | P94：解析 --gate-file gates.json（taint_gates/rule_gates/max_warnings/test_coverage）。 |
| def | `_default_sarif_base` | 3038 | P94：自动基线路径——<root>/.codebuddy/analyzer/sarif_base.json。 |
| def | `_save_sarif_fingerprints` | 3046 | P94：把 SARIF 指纹行数组持久化到自动基线文件。 |
| def | `_load_fp_list_file` | 3064 | P94：读取指纹行数组文件（裸数组，兼容 --sarif-diff 零参数复用）。 |
| def | `_doc_todo_priority` | 2909 | P86：按 复杂度 × 扇入 × 文档分 判定补注释优先级。 |
| def | `_build_doc_suggestion` | 2922 | P89：按缺失项生成「补文档建议」文本（可粘贴到 Doxygen 头注释）。 |
| def | `_build_test_suggestion` | 2943 | P89：按复杂度/扇入/输入输出生成「补测试建议」文本（含测试点清单）。 |
| def | `_collect_doc_todos` | 2964 | P86：注释完备度评估——复杂度 × 扇入/扇出 × 头部注释缺失 → 待办清单。 |
| def | `_diff_todo_actions` | 3074 | P92：行动单差异——按 (file, func) 键对比上一轮 --todo-export 行动单。 |
| def | `measure_branch_coverage` | 3140 | P96：分支覆盖度量——按函数体区间扫描分支关键字（MATLAB/C/PY/JS），测试文件引用近似已覆盖，输出 covered/total/coverage_percent/per_file/test_refs。 |
| def | `render_todo_page` | 3170 | P86：生成「函数待办清单」页面（todo.html，--browse 模式专用）。 |
| def | `collect_c_files` | 3325 | P87：收集根目录下的 C/C++ 源码文件（.c/.h）。 |
| def | `_parse_c_source` | 3346 | P87：轻量 C 源码解析——提取函数定义、函数调用、include 依赖。 |
| def | `build_c_model` | 3419 | P87：把 C 文件解析结果组装为统一模型。 |
| def | `_rel_of` | 3468 | P87：把绝对路径转为相对当前工作目录的 rel（保持与 MATLAB 端一致）。 |
| class | `BaseFrontend` | 3484 | P90：语言前端插件基类。 |
| def | `register_frontend` | 3520 | P90：注册语言前端插件。lang 为唯一标识；重复注册时后注册者覆盖。 |
| def | `get_frontend` | 3527 | P90：按 lang 取前端插件实例；未注册返回 None。 |
| def | `_c_file_lines` | 3533 | P90：按 C 模型同款策略读取文件行（UTF-8，容错替换）。 |
| def | `_prev_nonspace_lines` | 3542 | P90：取指定行之前的 n 个非空行（用于判断函数定义前是否有注释）。 |
| def | `_c_heuristic_checks` | 3553 | P90：C 静态启发式检查（--lang c --checks）。 |
| def | `_func_body_lines` | 3682 | P93：取函数定义行之后的函数体行区间（到下一个函数定义前或文件末尾）。 |
| def | `_gen_c_tests` | 3694 | P90：为 C 函数生成测试骨架（<out>/gen_c_tests/test_<func>.c）。 |
| def | `_gen_matlab_tests` | 3761 | P90：为 MATLAB 函数生成测试骨架（<out>/gen_matlab_tests/test_<func>.m）。 |
| def | `gen_tests_for_lang` | 3820 | P90：按语言前端生成测试骨架，返回 (count, rel 列表)。 |
| def | `_parse_py_source` | 3856 | P93：轻量 Python 解析——def 函数、调用边、import 列表。 |
| def | `_parse_js_source` | 3915 | P93：轻量 JavaScript 解析——function/箭头函数、调用边、import 列表。 |
| def | `_build_ext_model` | 3978 | P93：把 Python/JS 文件解析结果组装为统一语言无关模型。 |
| def | `_py_heuristic_checks` | 4009 | P93：Python 静态启发式——未使用 import / 重复参数名 / 参数过多 / 缺注释。 |
| def | `_js_heuristic_checks` | 4069 | P93：JavaScript 静态启发式——未使用 import / 隐式全局 / 参数过多 / 缺注释。 |
| def | `_gen_py_tests` | 4133 | P93：为 Python 函数生成 pytest 骨架（<out>/gen_py_tests/test_<func>.p |
| def | `_gen_js_tests` | 4168 | P93：为 JavaScript 函数生成 Node assert 骨架（<out>/gen_js_tests/test |
| class | `PyFrontend` | 4205 | P93：Python 前端插件（轻量解析 + pytest 骨架生成）。 |
| class | `JsFrontend` | 4256 | P93：JavaScript 前端插件（轻量解析 + Node assert 骨架生成）。 |
| class | `CFrontend` | 4307 | P90：C/C++ 前端插件（复用 P87 轻量解析器）。 |
| class | `MatlabFrontend` | 4344 | P90：MATLAB 前端插件（解析复走主流程，测试生成独立实现）。 |
| def | `_match_c_bridge` | 4364 | P87：MATLAB ↔ C 混合桥接——MATLAB 外部调用命中 C 函数名。 |
| def | `render_c_report` | 4388 | P87：生成 C 语言前端分析报告（c_report.html）。 |
| def | `render_c_index_html` | 4533 | P87：纯 C 模式（--lang c）的简易索引页，导航到 C 分析报告。 |
| def | `_run_c_only` | 4566 | P87：纯 C 分析入口（--lang c）。 |
| def | `_run_ext_only` | 4653 | P93：Python/JS 前端入口（--lang py / --lang js）。 |
| def | `render_taint_page` | 4758 | P85：生成「污点流分析」页面（taint.html，--browse 模式专用）。 |
| def | `_detect_dead_code` | 4901 | C3：检测函数内死代码（控制流路径分析）。 |
| def | `_detect_type_mismatch` | 4960 | C3：检测同一变量类型不一致（如矩阵变量被赋标量，潜在的维度/类型隐患）。 |
| def | `_infer_dims` | 5017 | C3：从矩阵构造器推断具体维度（结合常量折叠，支持多维数组）。 |
| def | `_collect_dimensions` | 5040 | C3：收集变量具体维度（从 zeros/ones/eye/randn/rand 构造器 + 常量折叠）。 |
| def | `_detect_shape_mismatch` | 5079 | C3：形状检查——结合维度推断，检测二元矩阵运算的形状约束违规。 |
| def | `_json_default` | 5148 | C3：JSON 序列化兜底——把不可序列化对象（set/Path/自定义对象）转成可序列化形式。 |
| def | `render_json` | 6086 | 导出结构化 JSON（便于程序化处理 / 二次分析）。 |
| def | `_from_json_load` | 6294 | P123：读取 --json 导出的快照文件，返回 (data, error)；顶层必须为 dict。 |
| def | `_json_snapshot_stats` | 6306 | P123：从 JSON 快照计算统计（无需重新扫描源码）。 |
| def | `_json_contract_check` | 6340 | P123：对快照执行契约校验（P113 语义在可交换格式上的投影），缺必需字段 → error。 |
| def | `_serialize_model` | 6377 | P123：对称化——规整快照为可再序列化模型（generated_at 置空，与 --reproducible 对齐）。 |
| def | `_roundtrip_diff` | 6389 | P123：递归比较两个 JSON 值，返回差异路径（往返一致性报告）。 |
| def | `render_snapshot_report` | 6412 | P123：基于 dict 渲染 Markdown 快照报告（概览/文件/函数/调用图/契约校验）。 |
| def | `_run_from_json` | 6513 | P123：--from-json 快照导入入口（短路分支）；--json 重导出+往返校验，-o 快照报告，--max-warnings 门禁；P124：--browse 渲染快照回放站点。 |
| def | `_snapshot_qkey` | 6592 | P124：调用图节点键 rel:name（与 --json 的 calls/edges 同构）。 |
| def | `_snapshot_index` | 6597 | P124：从快照 dict 建立浏览索引 {fn_key, file_by_rel, cls_by_rel, cg}。 |
| def | `_snapshot_rel_href` | 6628 | P124：文件页内指向另一文件页的相对链接（src 目录内，处理子目录层级）。 |
| def | `_snapshot_fn_href` | 6635 | P124：调用图键 → 文件页函数锚点链接；未解析到项目文件返回 None。 |
| def | `_snapshot_call_html` | 6652 | P124：把调用项列表渲染为链接/纯文本 <code> 列表（含未解析的裸名）。 |
| def | `_snapshot_count_html` | 6667 | P124：把 {名字: 次数} 渲染为 <code>名字</code>×次数 列表。 |
| def | `_snapshot_metric_rows` | 6676 | P124：从快照计算函数风险指标行（_compute_function_metrics 的 dict 投影）。 |
| def | `_snapshot_unresolved_rows` | 6727 | P124：聚合快照 external_calls 为疑似漏检调用行（_collect_unresolved_calls 的投影）。 |
| def | `_snapshot_builtin_items` | 6751 | P124：汇总快照 builtin_calls（name → 总次数），降序 [(name, cnt), ...]。 |
| def | `_snapshot_attach_file` | 6765 | P124：给快照检查项补 file 字段（func/name → rel 反查），供 checks 页跳转。 |
| def | `_snapshot_page_head` | 6790 | P124：快照回放页面公共头部（BROWSE_CSS 同款样式）。 |
| def | `_snapshot_stat_html` | 6798 | P124：统计卡片区 HTML。items 为 [(标签, 数值), ...]。 |
| def | `_render_snapshot_index` | 6806 | P124：快照回放首页——元数据、统计、文件/函数/类索引、子页导航。 |
| def | `_snapshot_fn_card` | 6916 | P124：单函数卡片 HTML（快照回放，无源码正文）。 |
| def | `_snapshot_class_card` | 6981 | P124：单类卡片 HTML（快照回放）。 |
| def | `_render_snapshot_file_page` | 7011 | P124：单文件回放页——文件卡 + 函数卡 + 类卡（快照不含源码正文）。 |
| def | `render_snapshot_browse_site` | 7061 | P124：从 JSON 快照 dict 渲染离线自包含浏览站点（--from-json X --browse OUT），内嵌 snapshot.json 归档副本。 |
| def | `_snapshot_diff_key` | 7129 | P126：快照项差异键 file:func:line[:name]。 |
| def | `_diff_map` | 7145 | P126：条目列表按 key_fn 建索引（保留首个同名项）。 |
| def | `_diff_keyed` | 7157 | P126：按 key 对齐的两索引差异（新增/删除/修改）。 |
| def | `_call_set_desc` | 7169 | P126：调用名集合「+添加 -删除」描述。 |
| def | `_diff_section_lines` | 7176 | P126：一层差异 dict 渲染为报告行。 |
| def | `_diff_files` | 7193 | P126：文件层差异（key=rel，lines/functions/parse_errors 字段级明细）。 |
| def | `_collect_fn_map` | 7225 | P126：全快照函数索引 rel:name。 |
| def | `_fn_diff_detail` | 7239 | P126：函数字段级差异明细（行/签名/参数/文档/调用集）。 |
| def | `_diff_functions` | 7258 | P126：函数层差异（新增/删除/修改）。 |
| def | `_collect_class_map` | 7266 | P126：全快照类索引 rel:name。 |
| def | `_class_diff_detail` | 7280 | P126：类字段级差异明细（行/父类/方法集）。 |
| def | `_diff_classes` | 7296 | P126：类层差异。 |
| def | `_edge_key` | 7304 | P126：调用边差异键 caller → callee。 |
| def | `_diff_edges` | 7309 | P126：调用边层差异（含跨文件边）。 |
| def | `_snapshot_group_list` | 7319 | P126：取告警/索引组条目列表（兼容 dict 容器带子键）。 |
| def | `_flatten_global_vars` | 7327 | P126：global_vars 扁平化为 scope:name 索引。 |
| def | `_diff_checks` | 7341 | P126：十组告警/索引差异（未初始化/类型/污点/待办/常量/类型声明等）。 |
| def | `_diff_overview_lines` | 7379 | P126：概览行——文件/函数/类/边/告警计数 A→B。 |
| def | `_diff_meta_lines` | 7423 | P126：元数据行——路径/version/root/generated_at。 |
| def | `_diff_snapshot_report` | 7439 | P126：汇总双快照差异报告（rows + has_diff）。 |
| def | `_diff_report_markdown` | 7468 | P126：Markdown 差异报告（-o 输出）。 |
| def | `_run_diff` | 7484 | P126：--diff BASE CUR 入口（退出码，--fail-on-diff 门禁）。 |
| def | `_fp_canon` | 7524 | P127：规范化任意 JSON 值——dict 按键排序、list 保序、递归剥离顶层 generated_at（键序无关）。 |
| def | `_fp_sha256` | 7536 | P127：对规范化值计算 SHA-256 十六进制摘要（确定性 JSON 序列化）。 |
| def | `_fp_group_value` | 7543 | P127：提取告警组字段值——dict 型组（taint/doc_todos）取子字段，缺失用空列表。 |
| def | `_fp_build_fingerprint` | 7551 | P127：构建指纹 dict——整体 + 逐文件 + 告警组三层 SHA-256。 |
| def | `_run_fingerprint` | 7596 | P127：--fingerprint FILE 入口（SNAPSHOT_SHA256 输出，--json 落盘指纹文件）。 |
| def | `_run_verify` | 7627 | P127：--verify FP [SNAP] 入口（VERIFY_RESULT OK/MISMATCH，不一致退出 1）。 |
| def | `_file_signature` | 15253 | P133：文件签名（内容 SHA-256 + size）——由 P71 mtime+size 升级，CI/git checkout 后 mtime 全变仍可命中缓存。 |
| def | `_render_incr_report` | 15267 | P133：增量缓存健康报告——text/json/md 三种格式（命中/未命中/命中率/逐文件状态，json 含 marker=P133）。 |
| def | `_xml_tag` | 7692 | B2：把 dict key 清洗为合法 XML 元素名（非标识符字符替换为 _，数字开头补前缀）。 |
| def | `_dict_to_et` | 5345 | B2：把 dict/list/标量递归填充为 ElementTree 节点（与 --json 数据结构同构）。 |
| def | `_indent_et` | 5360 | B2：ElementTree 缩进美化（生成可读 XML）。 |
| def | `render_xml` | 5378 | B2：导出结构化 XML（与 --json 数据结构同构，供 doxygen 生态工具二次消费）。 |
| def | `_persist_and_diff_sarif` | 4983 | P94：统一基线持久化 + 增量 diff——C/PY/JS 模式自动写入 sarif_base.json 并产出差异统计。 |
| def | `_apply_unified_gates` | 5038 | P94：统一门禁矩阵执行——C/PY/JS 模式复用 MATLAB 主流程门禁（taint/rule/max_warnings/test_coverage）。 |
| def | `_sarif_result_fp` | 5408 | P84：SARIF 告警指纹——(uri, startLine, ruleId, message)，用于跨版本增量比对。 |
| def | `_load_sarif_fingerprints` | 5428 | P84：读取基线 SARIF 文件，返回其全部告警的指纹集合。 |
| def | `_sarif_fp_detail` | 5443 |  |
| def | `render_sarif` | 5447 | C3：导出 SARIF（Static Analysis Results Interchange Format）2.1.0 |
| def | `render_sarif_diff_md` | 5559 | P84：把增量差异统计（render_sarif return_stats 的结果）渲染成 Markdown |
| def | `_inline_md` | 5597 | 行内 Markdown → HTML：`code`、**bold**，其余字符先做 HTML 转义（防注入）。 |
| def | `md_to_html` | 5605 | 轻量级 Markdown → HTML：标题 / 表格 / 代码块 / 引用 / 列表 / 段落，统一安全转义。 |
| def | `render_html` | 5774 | 生成自包含 HTML（含 Mermaid 图 + 热点函数离线 SVG 调用图）。 |
| def | `build_analysis_model` | 5856 | 构建统一「分析数据层」：供 --browse 与 --html 渲染共用，避免重复计算 |
| def | `_cg_path_panel_html` | 5889 | P20：调用路径查找面板（最短可达路径 BFS）。起止两个函数名输入框 + 查找/清除按钮 |
| def | `_dir_label_of` | 6479 | P100：相对路径的目录标签（'(root)' 或目录相对路径，'/' 分隔）。 |
| def | `_build_dir_tree` | 6485 | P100：目录树模型 dirs——按文件夹分层聚合文件（函数/行/圈复杂度沿路径累加），供目录导航、JSON 输出消费。 |
| def | `_build_file_dep_graph` | 6526 | P101：文件依赖图 files_graph——跨文件函数调用聚合 deps/dependents，变更影响评估。calls_of=None 返回 {}。 |
| def | `_crumbs_html` | 9808 | P103：面包屑导航 HTML（末项当前页无链接，其余可点）。 |
| def | `_mini_radar_svg` | 9821 | P111：五维度量雷达小图（内联 SVG，纯 Python 计算多边形坐标，零依赖）。 |
| def | `_fd_extra_flags` | 9852 | P104 辅助：按 __CG__.meta 顺序计算每个函数的污点/行动单标志 {gid:[ta,to]}。 |
| def | `render_func_detail_page` | 10003 | P104/P106：函数详情页 func_detail.html——单模板页+预注入 __CG__/__FD_FLAGS__，前端渲染签名横幅/徽章/一阶调用图（自包含 SVG）/调用者·被调列表/面包屑。 |
| def | `render_doxygen_xml` | 10037 | P112：Doxygen 兼容 XML 导出（index.xml + 每文件 compounddef，含 memberdef/location）。 |
| def | `_cg_impact_panel_html` | 5905 | P22：影响面 / 依赖面（传递闭包）交互面板。一个函数名输入 + 影响面/依赖面/清除 |
| def | `render_html_hotspot_callgraphs` | 5921 | 为 --html 合并报告内嵌「热点函数调用图」：取圈复杂度 Top N 的函数， |
| def | `_render_call_tree` | 6005 | 生成 doxygen 风格调用树（嵌套 <ul>）。 |
| def | `_collect_sarif_fps_from_text` | 6009 | P94：从 SARIF 文本中提取告警指纹行（配合自动基线复用）。 |
| def | `_dup_candidates` | 6049 | P52：收集项目内的同名函数候选，返回 {lower_name: [(fn, mf), ...]}， |
| def | `_build_global_cg` | 6063 | 构建前端「按需下钻」调用图所需的全局邻接表（一次分析仅构建一次，跨页缓存复用）。 |
| def | `_render_callgraph_host` | 6134 | 生成单个函数的「按需下钻」调用图容器（占位 div）；真实 SVG 由前端 |
| def | `_cg_site_rel` | 6145 | 返回从某源码页目录到「站点根」的相对路径前缀（用于拼接节点 href）。 |
| def | `_rel_to_src_asset` | 6161 | 源码页内指向 src/ 目录下共享资源（如 _cgdata.js）的相对链接。 |
| def | `_tokenize_matlab` | 8522 | 把一行 MATLAB 源码切成带类型的词法片段（基于原始字符偏移）。 |
| def | `_highlight_source_line` | 8605 | 对单行源码做语法高亮，并与调用点链接（call_sites）合并。 |
| def | `_compute_complexity` | 8699 | 为每个非脚本函数估算圈复杂度（分支点数量 + 1 的近似）。 |
| def | `_anchor_id` | 8723 |  |
| def | `_render_func_header_html` | 8727 | 将函数的结构化头部注释渲染为 HTML 片段（用于函数卡片内嵌展示）。 |
| def | `_page_rel` | 8818 | 源码页相对 src 目录的页面路径（raw，不编码），既用于写盘也用于 href。 |
| def | `_src_href` | 8830 | 返回 browse 站点中某文件的源码页面相对路径（相对站点根）。 |
| def | `_rel_href` | 8835 | 源码页内指向另一文件的相对链接（src 目录内，处理子目录层级）。 |
| def | `_up_to_index` | 8842 | 源码页内指向站点根 index.html 的相对链接（两个参数均按站点相对路径计算）。 |
| def | `_dir_page_name` | 8849 | P65：目录页文件名（安全化）——doxygen 风格目录索引页，路径含特殊字符时用 _ 替换。 |
| def | `_to_dir_page` | 8857 | P66：源码页内指向其所属目录页的相对链接（doxygen 式反向导航）。 |
| def | `_to_dir_page_from` | 8862 | P73：源码页内指向任意目录页的相对链接（函数卡片里的文件夹调用链接）。 |
| def | `_filter_calls_of_intra_dir` | 8869 | P67：过滤 calls_of，只保留本目录内函数之间的调用边（用于目录页内嵌调用图）。 |
| def | `render_directory_page` | 8886 | P65：生成目录索引页（doxygen 风格）——展示该目录的文件/函数、依赖目录（扇出/扇入）。 |
| def | `render_browse_site` | 9032 | 生成可交互跳转的 HTML 源码浏览站点。返回入口 index.html 路径。 |
| def | `_find_assignment_pos` | 9185 | 在单行中找到顶层（不在括号/字符串/注释内）的赋值运算符 '=' 位置。 |
| def | `_lhs_assigned_vars` | 9225 | 返回赋值语句 LHS 中每个顶层逗号元素首个标识符（被赋值变量名）。 |
| def | `_analyze_varflow` | 9255 | 分析文件中每个函数的参数（input/output）在函数体内的读写使用。 |
| def | `_detect_uninitialized` | 9317 | C3：检测函数内「疑似未初始化变量」（读前无写 + 条件分支赋值后使用）。 |
| def | `_render_param_flow_pills` | 9419 | 渲染函数卡片中的「参数流向」可点击药丸（点击高亮源码读写位置）。 |
| def | `_fn_desc` | 9448 | 返回函数结构化头部注释里的「函数说明」（description），供调用列表 / 图注释展示。 |
| def | `_fn_src_snip` | 9467 | P39/P40：返回函数「头部注释（向上 N 行）+ 定义行 + 函数体（向下 M 行）」的带行号、 |
| def | `_transitive_closure` | 9508 | BFS 求某函数的传递闭包，按「最短距离」分层。返回 {depth: [fn, ...]}（不含自身）。 |
| def | `_clear_closure_cache` | 9535 | P44：清空传递闭包缓存（每次分析开始前调用，避免 id 复用导致脏缓存）。 |
| def | `_impact_layers` | 9546 | 影响面：谁（直接 + 间接）调用了 fn → 沿 callers_of（上游）传递闭包（带缓存）。 |
| def | `_dependency_layers` | 9556 | 依赖面：fn（直接 + 间接）调用了谁 → 沿 calls_of（下游）传递闭包（带缓存）。 |
| def | `_trace_roots` | 9567 | P32：溯源到根——返回「无人调用（入口）但可传递调用到 fn」的最终祖先入口函数列表 |
| def | `_trace_status` | 9579 | P43：返回函数溯源状态： |
| def | `_collect_orphaned` | 9589 | P43：收集「无法溯源到根」的函数（有调用方但上溯无法到达入口，即处于调用循环）。 |
| def | `_render_impact_dependency_html` | 9601 | 生成某函数「影响面 / 依赖面（传递闭包）」折叠区块（供源码页函数卡片）。 |
| def | `_compute_function_metrics` | 9670 | 计算每个项目内函数的耦合风险指标（P23）：扇入 / 扇出 + 传递影响面 / 依赖面 + 圈复杂度。 |
| def | `_render_metrics_table` | 9711 | 渲染「关键函数风险度量」HTML 表格（可选只取前 top_n 行）。 |
| def | `render_metrics_page` | 9733 | 生成独立的「关键函数风险度量」页面（--browse 模式专用）。 |
| def | `_collect_unresolved_calls` | 9755 | P25：收集「疑似漏检调用」诊断数据。汇总每个函数中未解析到项目/内置的调用名 |
| def | `_collect_dynamic_calls` | 9774 | P43：汇总各函数的动态执行调用（eval/run/evalin/evalc 等，需人工确认调用关系）。 |
| def | `_render_unresolved_table_html` | 9786 | 渲染「疑似漏检调用诊断」HTML 表格。link_fn(rel, line)->href（可选，browse 用）。 |
| def | `render_unresolved_page` | 9812 | 生成独立的「疑似漏检调用诊断」页面（--browse 模式专用）。 |
| def | `render_static_callgraph_svg` | 9864 | P30：生成整个项目调用图的**静态 SVG**（左→右分层布局：入口/孤立函数在左，被调函数 |
| def | `render_folder_function_graph_svg` | 9967 | P62：生成「目录-函数」分层调用图 SVG（doxygen 风格）——目录作为簇（圆角容器）， |
| def | `_collect_class_hierarchy` | 10101 | P81：收集项目内全部 classdef 的继承关系。 |
| def | `render_class_hierarchy_svg` | 10128 | P81：生成 doxygen 风格的「类继承图（Inheritance Diagram）」SVG。 |
| def | `_collect_class_collaborations` | 10235 | A3：收集类间协作（uses）关系——某类的任一方法调用了另一类的任一方法/构造函数。 |
| def | `render_class_collaboration_svg` | 10258 | A3：生成 doxygen 风格的「类协作图（Collaboration Diagram）」SVG。 |
| def | `render_class_hierarchy_page` | 10338 | P81：生成独立的「类层次（Class Hierarchy）」页面（--browse 模式专用）， |
| def | `_collect_annotations` | 10405 | A1：扫描全部源码注释，聚合 TODO/BUG/DEPRECATED/FIXME/NOTE 等标签。 |
| def | `render_annotations_page` | 10425 | A1：生成「注释标签聚合」页面（--browse 模式专用），doxygen 风格 |
| def | `_collect_checks` | 10466 | C3：聚合静态检查结果（未初始化 / 死代码 / 类型不一致），补 file 字段。 |
| def | `render_checks_page` | 10491 | C3：生成「静态检查」汇总页（checks.html，--browse 模式专用）。 |
| def | `_collect_file_metrics` | 10567 | C3：收集文件级复杂度指标（总复杂度/函数数/类数/行数），按复杂度降序。 |
| def | `_collect_dir_metrics` | 10582 | C3：收集目录级复杂度/耦合度指标（按目录聚合文件复杂度）。 |
| def | `render_complexity_heatmap` | 10600 | C3：生成「复杂度热力总览」页面（complexity.html，--browse 模式专用）。 |
| def | `_collect_members` | 10648 | B1：收集全部类的成员（属性/事件/枚举/方法），用于全局成员索引。 |
| def | `render_members_page` | 10670 | B1：生成「全局成员索引（Member Index）」页面（--browse 模式专用）， |
| def | `_json_js_esc` | 10726 | 把 Python 字符串转义为 JS 字符串字面量内容（不含外层引号）。 |
| def | `render_dir_coupling_matrix` | 10796 | P82：生成「目录耦合度矩阵」页面（dir_matrix.html，--browse 模式专用）。 |
| def | `render_source_page` | 10945 | 渲染单个源码文件页：顶部函数索引 + 可跳转源码 + 按需下钻调用图。 |
| def | `_render_hotspot_section` | 11296 | 渲染首页「热点分析」：核心枢纽 / 高风险 / 孤立函数。 |
| def | `_render_callgraph_section` | 11338 | 渲染首页「交互式全局调用图」：节点=函数、边=调用关系（离线 SVG 力导向）。 |
| def | `render_browse_index` | 11408 | 渲染浏览站点索引页：目录树 + 全量函数索引 + 类汇总。 |
| def | `render_tree_browse` | 11624 | 目录树（叶子文件加跳转链接，目录节点加目录页链接）。 |
| def | `_src_href_from_rel` | 11685 |  |
| def | `_compute_folder_edges` | 11689 | P57：计算文件夹之间的调用边（目录级依赖关系）。 |
| def | `_compute_dir_coupling` | 11726 | P82：计算目录耦合矩阵（目录 × 目录 跨目录调用次数 + 明细）。 |
| def | `_detect_folder_cycles` | 11778 | P61：检测目录依赖图中的循环目录（Tarjan 强连通分量，size > 1）。 |
| def | `render_folder_dependencies` | 11831 | P57：渲染「文件夹调用关系」Markdown 章节。 |
| def | `_render_folder_deps_section` | 11892 | P60：渲染 browse 索引页「文件夹依赖关系」区块——目录间调用边表 + 每个目录的 |
| def | `_compute_folder_stats` | 11964 | 按父目录聚合调用统计。 |
| def | `_render_e2e_chain_html` | 12013 | 渲染端到端调用链路（从入口到叶子），每步附带函数描述。 |
| def | `_render_e2e_walk` | 12048 | 递归渲染端到端调用链的每一步。 |
| def | `_write_output` | 12084 | P48：统一写盘入口——自动创建父目录并捕获写入异常。 |
| def | `_safe_print_md` | 12101 | P87 补充：GBK 控制台安全打印——无法用 stdout 编码表示的字符以 ? 代替。 |
| def | `_clean_browse_dir` | 12124 | P48：清理 --browse 输出目录中的旧产物，避免残留「幽灵页面」。 |
| def | `_file_signature` | 12159 | P71：文件签名（mtime_ns + size），用于增量缓存判断文件是否变更。 |
| def | `_reset_call_analysis` | 12168 | P71：清空函数对象的调用分析结果（复用缓存的结构信息后重新做调用分析）。 |
| def | `_load_incremental_cache` | 12183 | P71：加载增量缓存（pickle），失败返回空 dict。 |
| def | `_save_incremental_cache` | 12192 | P71：保存增量缓存（pickle），失败静默忽略。 |
| def | `collect_files` | 12201 |  |
| def | `collect_empty_dirs` | 12222 | P74：收集「不含 .m 文件」的目录（空目录），使其也纳入分析展示。 |
| def | `_parse_suppressions` | 12272 | C3：解析告警抑制注释（就地标注）。 |
| def | `_count_suppressed` | 12312 | C3：统计告警抑制注释数量（文件级/名称级/行级），用于 checks.html 展示「已抑制」规模。 |
| def | `_parse_checks_arg` | 12329 | C3：解析 --checks 参数，返回启用的检查集合（None 表示全部启用）。 |
| def | `_load_config` | 12344 | 读取 JSON 配置文件，返回字典。 |
| def | `_extract_config_arg` | 12370 | 从 argv 提前取出 --config 值，返回 (config_dict, 去掉 --config 后的 argv)。 |
| def | `main` | 12393 | 解析真正的参数前，先从 argv 中提取 --config（若存在）， |

## 主要分节注释

- L58: `# ---...---`
- L60: `# ---...---`
- L124: `# ---...---`
- L126: `# ---...---`
- L617: `# ---...---`
- L619: `# ---...---`
- L656: `# ---...---`
- L658: `# ---...---`
- L770: `# ---...---`
- L772: `# ---...---`
- L861: `# ---...---`
- L863: `# ---...---`
- L1179: `# ---...---`
- L1181: `# ---...---`
- L1226: `# ---...---`
- L1228: `# ---...---`
- L1449: `# ---...---`
- L1451: `# ---...---`
- L1627: `# ---...---`
- L1629: `# ---...---`
- L2382: `# ---...---`
- L2384: `# ---...---`
- L2906: `# ---...---`
- L2908: `# ---...---`
- L3304: `# ---...---`
- L3306: `# ---...---`
- L3481: `# ---...---`
- L3483: `# ---...---`
- L5853: `# ---...---`
- L5855: `# ---...---`
- L5998: `# ---...---`
- L6000: `# ---...---`
- L8509: `# ---...---`
- L8511: `# ---...---`
- L9179: `# ---...---`
- L9181: `# ---...---`
- L10723: `# ---...---`
- L10725: `# ---...---`
- L12081: `# ---...---`
- L12083: `# ---...---`
