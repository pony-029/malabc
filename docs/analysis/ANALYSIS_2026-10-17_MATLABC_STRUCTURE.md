# 2026-10-17 · matlabc 结构与提交史深度分析

> 目的：回答三个问题 —— 这个 34,229 行的单文件到底长什么样？它是怎么写成的？
> 动它之前，应该先动哪里、拿什么当判据？
>
> 全部读数**现测**（`ast` 解析 + `git log` 统计），不引用记忆、不引用文档里的散文数字。

---

## §0 一句话结论

**结构不是「到处都烂」，而是「12 个函数烂」**：706 个函数的中位数只有 **21 行**，
但 `main` 一个函数就 **2,020 行**；`>200 行` 的函数共 **12 个**，`>500 行` 的 **4 个**。
**成因是时间**：仓库只有 **138 个提交**，全部落在 **2026-10-08 → 10-17 这 10 天**，
`refactor` 关键词只出现过 **1 次**。
**代价已经可测**：文档与门禁的改动次数**超过**产品代码（README 65 次、tests 62 次、
README_CN 59 次、check_help_contract 50 次 vs `matlabc.py` 46 次）。

---

## §1 测量面（分母先摆出来）

| 项 | 口径 | 读数 |
| --- | --- | --- |
| 被测文件 | `matlabc.py` | 34,229 行（按 `\n` 计） |
| 结构解析 | `ast.parse` + `end_lineno` | 706 函数 / 11 类 |
| 函数体总行 | 所有函数 `end-lineno+1` 之和 | 28,093 行，占全文 **82.1%** |
| 提交史 | `git rev-list --count HEAD` | **138** |
| 时间跨度 | 首个 / 最后一个提交日期 | 2026-10-08 → 2026-10-17（10 天） |
| 文件热度 | `git log --name-only` 分组计数 | 见 §2 |

> 读数在提交 `3923ebe` **之前**测得。P0 工具 `tools/analyze_structure.py` 可随时重跑：
> 同一份结论在 `3923ebe` 之后实测为 **139 commits**、`matlabc.py` 被改 **47** 次
> （本文件与工具自身也进了那次提交）。**数字会动，判据不变**。

---

## §2 仓库级：10 天、138 提交、文档比代码改得多

### 2.1 提交节奏

```
commits = 138
first   = 2026-10-08
last    = 2026-10-17
按月份：2026-10 = 138（全部）
```

⇒ 平均 **13.8 提交/天**。这是"冲刺式开发"的典型形态，**没有任何一段稳定的重构窗口**。

### 2.2 提交信息的关键词分布（`git log --format=%s`，138 条）

| 关键词 | 出现次数 | 说明 |
| --- | --- | --- |
| `R\d+` | 119 | 几乎每次提交都挂轮次号（R30–R109） |
| `feat` | 43 | 功能 |
| `docs` | 32 | 文档 |
| `gate` | 15 | 门禁 |
| `fix` | 10 | 修复 |
| `refactor` | **1** | 重构只发生过一次 |
| `probe` | 0 | 探针写在仓外，不进提交 |

### 2.3 文件热度：治理成本 > 功能成本

| 文件 | 被多少提交改过 |
| --- | --- |
| `README.md` | **65** |
| `tests/test_matlabc.py` | 62 |
| `README_CN.md` | 59 |
| `tools/check_help_contract.py` | 50 |
| `matlabc.py` | **46** |
| `tools/check_all.py` | 34 |
| `CONTRIBUTING.md` | 28 |
| `docs/EVOLVE_ROADMAP_360.md` | 23 |
| `docs/KERNEL_RUN.md` | 21 |

**读法**：产品文件（`matlabc.py`）被改 46 次，而**文档 + 测试 + 门禁合计 298 次**。
这不是"文档写得好"，而是**每加一个功能要同步 4–6 处治理文件**：
两份 README 的质量门表、`check_help_contract` 的登记表、`check_all` 的树与门数、
`CONTRIBUTING` 的散文数字。

⚠ 这正是 R110/R111 反复踩的坑：**门数散文写在 `matlabc.py` 的 docstring 里，
而 `matlabc.py` 的 sha256 被 `check_kernel_snapshot` 的 W2 钉死** ⇒
"加一道门" = "一次 59 分钟整树重跑"。10 天里没人有时间为这件事重构。

---

## §3 单文件内部：健康的中位数 + 极端的长尾

### 3.1 分布

```
n=706   sum=28,093   mean=39.8
p50=21   p75=41   p90=78   p99=240   max=2,020
>50 行: 139    >100 行: 44    >200 行: 12    >500 行: 4    >1000 行: 2
```

**中位数 21 行**说明绝大多数函数是健康的；**12 个函数 >200 行**说明问题高度集中。
重构 ROI 最高的就是这 12 个。

### 3.2 长尾清单（按行数降序，前 12）

| 行数 | 起始行 | 函数 | 性质 |
| --- | --- | --- | --- |
| **2,020** | L32185 | `main` | **上帝函数**：argparse + 全部分支 + 落盘 |
| **1,158** | L18033 | `_run_global_state` | 全局状态分析（可拆） |
| 573 | L29092 | `render_source_page` | HTML 渲染（应在 `renderers/`） |
| 540 | L24042 | `render_browse_site` | HTML 渲染 |
| 354 | L13867 | `_run_p204_p223_integration` | 集成分支 |
| 288 | L269 | `_build_global_cg` | 调用图构建 |
| 279 | L29856 | `render_browse_index` | HTML 渲染 |
| 266 | L3617 | `_parse_header_comments` | 头注释解析 |
| 240 | L14223 | `render_json` | **JSON 契约出口** |
| 240 | L4935 | `render_markdown_report` | 报告渲染 |
| 214 | L27835 | `_builtin_shape` | 内置函数形状表 |
| 213 | L28088 | `_es_eval` | 表达式求值 |

### 3.3 三类可归并的长尾

1. **渲染类 5 个（1,777 行）**：`render_source_page` / `render_browse_site` /
   `render_browse_index` / `render_compliance_page` / `render_directory_page`。
   而 `renderers/` 目录**已经存在**（`csite.py` 1,749 行）⇒ 职责重叠，不是"没地方放"。
2. **入口类 2 个（3,178 行）**：`main` + `_run_global_state`。
3. **契约出口 2 个（480 行）**：`render_json` + `render_markdown_report`
   —— 它们改一个键就要同步 README/schema/门禁，是最该"单一出口"的部分。

### 3.4 模块级依赖

顶层 import 35 个不同模块，其中**仓内模块 6 个**：
`binfmt` / `callrel` / `entity_model` / `fe_audit` / `frontends` / `pyast_frontend` / `renderers`。
`fe_audit` 是**从未提交**的产物（`check_known_red.py` 在册），导入失败被吞掉——
这是一条已知的"产品经由测试依赖缺失文件"的隐式耦合。

---

## §4 三个结构性问题（按可修性排序）

### 问题 A：`main` 是唯一入口，也是唯一障碍

2,020 行里混了四件事：**参数解析**、**模式分发**、**分析编排**、**产物落盘**。
后果可测：LSP 插件只能起子进程（冷启动压不到 2 秒）；`--help` 与 `--json` 的任何改动
都要读它；`check_help_contract` 每次改帮助都要动这个函数。

### 问题 B：渲染函数留在产品文件里，而 `renderers/` 已存在

5 个 `render_*` 共 1,777 行在 `matlabc.py`，而 `renderers/csite.py` 也有 1,749 行。
**两处都能生成 HTML**，但只有一处被门禁覆盖（`check_browse_clean_manifest` 只管清理清单）。

### 问题 C：治理成本已经超过功能成本

§2.3 的 46 vs 298 是硬读数。具体到本轮：为了把门数从 21 改到 23，
我改了 `matlabc.py` 三次，让两次整树重跑作废。

---

## §5 深度分析方案（可执行，每阶段带判据）

### P0 仪器化（1 轮）
把本文件 §1–§3 的测量做成 `tools/analyze_structure.py`：`ast` 解析 `matlabc.py`，
输出函数数 / 分布 / 长尾清单 / 治理成本比。
**判据**：读数与本文逐项相等；`--json` 输出可被下一个阶段直接消费。

### P1 切 `main`（3 轮）
把 `main` 按三段切：`cli_entry()`（argparse + 归一）、`run_pipeline(opts)`（编排）、
`emit_outputs(result, opts)`（落盘）。
**判据**：`--help` 逐字节不变（`check_help_contract` 的规范形容差 0 已经能验）；
`--json` 的 `--fingerprint` 不变；`main` 行数 < 200。

### P2 抽渲染（4 轮）
5 个 `render_*` 搬到 `renderers/`，`matlabc.py` 只留调用。
**判据**：`--browse` 站点全目录**逐字节不变**（`renderers/snapshot.py` 的指纹能做）；
`renderers/` 与 `matlabc.py` 之间不出现新的模块级环（`check_import_graph` G1）。

### P3 抽分析（5 轮）
`parse_file` / `analyze_calls` / `_c_heuristic_checks` 等搬到 `analyzer/`，
`matlabc.py` 只剩编排。
**判据**：`--json` 的五类计数与迁移前**逐项相等**（`facts.py` 的 `expected_counts` 直接可用）；
`--from-json` 回放仍成立。

### P4 事实层反向接线（3 轮）
分析器直接产 facts，`render_json` 由 facts 聚合。
**判据**：`check_facts_replay` 的 FT1–FT3 全绿，且 `facts.py` 不再需要 `expected_counts`
（报表由事实生成，而不是两边各算一遍）。

### P5 治理瘦身（4 轮）
把「门数散文」从 `matlabc.py` 移出；`check_help_contract` 的登记表与 README 表行
改为「由 `tools/` 清单派生」而不是两边手写。
**判据**：新增一道门时，需要手工修改的文件数从 **6** 降到 **2**（README 两侧 + 门本身）。

---

## §6 30 轮落地表

| 轮 | 阶段 | 动作 | 判据 |
| --- | --- | --- | --- |
| R112–R113 | P0 | `tools/analyze_structure.py` | 读数与本文相等 |
| R114–R116 | P1 | 切 `main` 三段 | `--help` 逐字节 + `main` < 200 行 |
| R117–R120 | P2 | 5 个 `render_*` 外迁 | 站点逐字节不变 + 无新环 |
| R121–R125 | P3 | 分析函数迁 `analyzer/` | 五类计数逐项相等 |
| R126–R128 | P4 | facts 反向接线 | FT1–FT3 绿 + 不再双算 |
| R129–R132 | P5 | 治理瘦身 | 加门需改文件数 6 → 2 |
| R133–R140 | 收束 | 长尾复审 | `>200 行` 函数 12 → 4 |

---

## §7 风险与反模式

1. **不要按目录结构重构，按判据重构。** 每一步都必须有「迁移前后逐字节/逐计数相等」的对手方；
   没有它，重构只是在移动代码。
2. **不要一次切 `main`。** 2,020 行一次切完，`--help` 那 0 容差的判据会把几十处措辞差异一起暴露，
   修不动。分三段，每段单独收口。
3. **不要在改 `matlabc.py` 的同一轮里跑别的门禁**。R108 §12 的规矩：
   动它就要整树重跑；那就只动值得付这次重跑的东西。
4. **不要把「文档同步」当成免费动作。** §2.3 已经量出 298 次治理改动；
   P5 的目标就是把它降下来，而不是继续加登记表。
