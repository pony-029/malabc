# 能力对等登记表 —— MATLAB / C / Python / JavaScript

> 这张表回答一个问题：**今天哪几格是空的、为什么空。**
>
> 它由 `tools/check_parity_registry.py`（第 20 道登记制护栏 / 第 21 个护栏脚本，判据族 **E1–E6**）守住：
> 机器块里的每一格都必须与**现跑公开 CLI 得出的实测**一致，**两向**都响 ——
> 登记 `yes` 而实测为假 ⇒ 红（登记未实现）；实测为真而登记不是 `yes` ⇒ 红（实现未登记）；
> 非 `yes` 的格必须写理由，而 `yes` 的格**不许**留理由（陈旧理由 ⇒ 红）。

## 1. 怎么读这张表

* **格子**：`yes` = 实测成立；`no` = **该有而还没有**（缺口）；`na` = 语言形态上不适用。
* **`na` 不许用来掩盖「没实现」**：门自己有一份探针名单（`PROBED`）。凡门里**有**
  探针的格，登记成 `na` 就**直接红**；凡门里**没有**探针的格，才轮到 `na`，且理由必须
  说清「这个语言形态上为什么测不了」。
* **实测怎么来**：每语言在**合成夹具**上跑一次公开 CLI
  （`--json --json-level full --callgraph --browse`），信号只在**那个能力的专属文件**
  范围内读。实测**绝不**从这张表或源码字符串反推 —— 否则 E2 的两个方向都永远不响。
* 复核：`python tools/check_parity_registry.py --measure` 会把人读矩阵重新打一遍。

## 2. 能力矩阵

| 能力 | MATLAB | C | Python | JavaScript | 怎么测的 |
| --- | --- | --- | --- | --- | --- |
| `functions` | yes | yes | yes | yes | `fn_basic`/`mintra` 里两个定义都出现在载荷 `files[].functions` |
| `call_edges` | yes | yes | yes | yes | `fn_basic`/`mintra` 至少一条非跨文件边进载荷 `edges` |
| `call_edges_cross_file` | yes | yes | yes | yes | callgraph 的 `cross_file.cross > 0`（MATLAB 走载荷 `edges[].cross_file`） |
| `call_edges_qualified` | yes | na | no | no | `class_cls`/`Muse` 上至少一条边（属性 / 方法调用 `obj.m()`） |
| `call_edges_oneline_body` | na | yes | no | no | `oneline` 上至少一条边（花括号单行函数体内的调用点） |
| `deps_edges_json` | na | yes | no | no | 载荷 `include_edges` 非空 |
| `deps_site_page` | na | yes | yes | yes | 站点 `deps.html` 文本里出现依赖目标名 |
| `classes` | yes | na | no | no | 载荷 `files[].classes` 非空 |
| `entities` | yes | no | no | no | 载荷里出现实体 / 字段类键（`field_access` / `types` / `structs` …） |
| `metrics_complexity` | no | yes | yes | yes | 某个函数载荷 `complexity > 1` |
| `unresolved_attribution` | no | yes | yes | yes | 载荷 `unresolved` 非空（调了一个项目里不存在的名字） |
| `callgraph_projection` | no | yes | yes | yes | `--callgraph` 产物存在且 `call_relations.edges_total` 是整数 |
| `heuristics_channel` | no | yes | yes | yes | 载荷 `heuristics` 非空（无注释函数触发一条） |
| `asm_insights` | na | yes | na | na | 载荷出现 `asm` 键 |
| `browse_site` | yes | yes | yes | yes | `--browse` 产出站点且含 HTML |
| `site_same_page_names` | no | yes | yes | yes | 站点同时有 `index.html` / `funcs.html` / `file/` / `dir/` |

**合计 64 格：`yes` 40 · `no` 16 · `na` 8。**

## 3. 三类发现

### 3.1 「四家都有」的 4 条共性底座

`functions`、`call_edges`、`call_edges_cross_file`、`browse_site`
四项四语言全绿 —— 跨文件调用、站点产出这些**已经真的通了**（R86–R92 的移植结果
在这一层得到独立确认）。

### 3.2 特有的通道：不是缺口，是**口径分裂**

有四项能力在 MATLAB 侧走**另一条通道**，而 C / Py / JS 共用一条：

| 能力 | C / Python / JS | MATLAB |
| --- | --- | --- |
| `metrics_complexity` | 函数载荷自带 `complexity` | 只在 Markdown 报告与站点 `complexity.html` |
| `unresolved_attribution` | 载荷 `unresolved` 数组 | **没有**未解析归因出口（站点却有 `unresolved.html`） |
| `heuristics_channel` | 载荷 `heuristics` 数组 | 检查结果分在 `p204_p223` / `uninitialized` 等各自键里 |
| `site_same_page_names` | 10 个顶层页（`file/`+`funcs.html`+`dir/`） | 46 个顶层页（`dirs/`+`func_detail.html`+…） |

这四条是本轮**最有用的读数**：它们说明「对等」不只是「有没有」，还有
**「同一个东西从哪条通道出来」**。R92 让 C / Py / JS 的站点同形；MATLAB 的站点
是另一套，两者在页集层面**不同形** —— 这正是槽 29（画布对等）的靶。

### 3.3 真实的缺口：16 格，按可修性排序

| 缺口 | 格数 | 形态 | 去向 |
| --- | --- | --- | --- |
| `entities`（C / Py / JS） | 3 | C 的 `struct`/`enum`/`typedef`/字段、Py 的类与实例属性、JS 的对象字面量都不进载荷 | 槽 25（Py `ast` 前端）/ 槽 26（C 实体层） |
| `classes`（Py / JS） | 2 | 载荷没有 `classes` 键；`class` 里的方法被当成顶层函数列出，**类本身丢失** | 槽 25 |
| `call_edges_qualified`（Py / JS） | 2 | 属性 / 方法调用不成边：前端跳过前一个字符是 `.` 的调用点 | 槽 25 / 槽 28 |
| `call_edges_oneline_body`（Py / JS） | 2 | 单行函数体里的调用点收不到（JS：定义行自身被跳过；Py：同形） | 槽 25 |
| `deps_edges_json`（Py / JS） | 2 | 依赖边只进站点 `deps.html`，**不进载荷**（口径分裂） | 槽 28（度量对等，顺带修假边） |
| `callgraph_projection`（MATLAB） | 1 | 给了 `--callgraph` **静默不产出**（rc=0、无文件）—— 「没听懂却假装听懂」 | 槽 24–29 任一 |
| `metrics_complexity` / `unresolved_attribution` / `heuristics_channel` / `site_same_page_names`（MATLAB） | 4 | 见 3.2 的口径分裂 | 槽 28 / 槽 29 |

⚠ `callgraph_projection` 那一格值得单独说：**它不是「不支持」，是「假装修持」**。
CLI 收下开关、退出码 0、终端没有任何提示、盘上没有文件 —— 用户会以为画好了。
本仓在别处对这件事有大写的规定（「我没听懂却假装听懂」），所以这一格应当尽快消掉，
要么真产出、要么**明确拒绝**（非零退出并说清原因）。

## 4. 机器块（E1–E6 的地面真相）

块内 `键 | 值`：`cap.<能力>` 给出四语言状态；`cap.<能力>.evidence` 是「怎么测的」；
非 `yes` 的格用 `cap.<能力>.why.<语言>` 写理由。人读表与这个块**逐格一致**（E5）。

<!-- PARITY v1 -->
```text
parity.schema | v1
parity.langs | matlab c py js
cap.functions | matlab=yes c=yes py=yes js=yes
cap.functions.evidence | `fn_basic`/`mintra` 里两个定义都出现在载荷 `files[].functions`
cap.call_edges | matlab=yes c=yes py=yes js=yes
cap.call_edges.evidence | `fn_basic`/`mintra` 至少一条非跨文件边进载荷 `edges`
cap.call_edges_cross_file | matlab=yes c=yes py=yes js=yes
cap.call_edges_cross_file.evidence | callgraph 的 `cross_file.cross > 0`（MATLAB 走载荷 `edges[].cross_file`）
cap.call_edges_qualified | matlab=yes c=na py=no js=no
cap.call_edges_qualified.evidence | `class_cls`/`Muse` 上至少一条边（属性 / 方法调用 `obj.m()`）
cap.call_edges_qualified.why.c | C 没有成员调用语法：`p.a` 不是调用，函数指针 `p->fp()` 属于间接调用，这一行对 C 不适用
cap.call_edges_qualified.why.py | Python 的属性 / 方法调用不产边：前端跳过前一个字符是 `.` 的调用点，该夹具实测 0 条边
cap.call_edges_qualified.why.js | JavaScript 同形：`.m(` 形态被跳过，`class_cls.js` 实测 0 条边
cap.call_edges_oneline_body | matlab=na c=yes py=no js=no
cap.call_edges_oneline_body.evidence | `oneline` 上至少一条边（花括号单行函数体内的调用点）
cap.call_edges_oneline_body.why.matlab | MATLAB 的函数体以 `end` 收束，没有花括号单行体这种形态
cap.call_edges_oneline_body.why.py | `def f(v): return g(v)` 这种单行函数体里的调用点收不到（实测 0 条边）
cap.call_edges_oneline_body.why.js | 定义行自身被跳过 ⇒ 花括号单行体里的调用点收不到（实测 0 条边）
cap.deps_edges_json | matlab=na c=yes py=no js=no
cap.deps_edges_json.evidence | 载荷 `include_edges` 非空
cap.deps_edges_json.why.matlab | MATLAB 没有 `#include` / `import` 语法，文件级依赖走另一条通道（`files_graph` / `folder_edges`）
cap.deps_edges_json.why.py | 依赖边只进站点 `deps.html`，不进载荷：实测 `include_edges` 为空而 `deps.html` 提到目标模块
cap.deps_edges_json.why.js | 同上的口径分裂：站点有依赖页，载荷里没有 `include_edges` 条目
cap.deps_site_page | matlab=na c=yes py=yes js=yes
cap.deps_site_page.evidence | 站点 `deps.html` 文本里出现依赖目标名
cap.deps_site_page.why.matlab | 同上：没有 include / import，就没有依赖页可言
cap.classes | matlab=yes c=na py=no js=no
cap.classes.evidence | 载荷 `files[].classes` 非空
cap.classes.why.c | C 没有 `class` 语法（结构化类型是 `struct`，见 entities 那一行）
cap.classes.why.py | 载荷没有 `classes` 键：`class` 里的方法被当成顶层函数列出，类本身丢失
cap.classes.why.js | 载荷没有 `classes` 键：`class` 语法被识别成 `constructor` 等方法，类本身丢失
cap.entities | matlab=yes c=no py=no js=no
cap.entities.evidence | 载荷里出现实体 / 字段类键（`field_access` / `types` / `structs` …）
cap.entities.why.c | C 的 `struct` / `union` / `enum` / `typedef` 与字段不进载荷（该夹具里 0 处命中）；R87 的 `_is_type_decl` 只做排除，正向识别未做
cap.entities.why.py | Python 的类属性 / 实例属性不进载荷（没有实体层）
cap.entities.why.js | JavaScript 的对象字面量与类字段不进载荷（没有实体层）
cap.metrics_complexity | matlab=no c=yes py=yes js=yes
cap.metrics_complexity.evidence | 某个函数载荷 `complexity > 1`
cap.metrics_complexity.why.matlab | MATLAB 的复杂度只落在 Markdown 报告与站点 `complexity.html`，函数载荷里没有 `complexity` 字段
cap.unresolved_attribution | matlab=no c=yes py=yes js=yes
cap.unresolved_attribution.evidence | 载荷 `unresolved` 非空（调了一个项目里不存在的名字）
cap.unresolved_attribution.why.matlab | MATLAB 载荷没有 `unresolved` 键：未解析调用没有统一归因出口（站点却有 `unresolved.html`）
cap.callgraph_projection | matlab=no c=yes py=yes js=yes
cap.callgraph_projection.evidence | `--callgraph` 产物存在且 `call_relations.edges_total` 是整数
cap.callgraph_projection.why.matlab | 给了 `--callgraph` 静默不产出：rc=0、盘上无文件、终端无提示 —— 「没听懂却假装听懂」，比明确拒绝更差
cap.heuristics_channel | matlab=no c=yes py=yes js=yes
cap.heuristics_channel.evidence | 载荷 `heuristics` 非空（无注释函数触发一条）
cap.heuristics_channel.why.matlab | MATLAB 的检查结果分在 `p204_p223` / `uninitialized` / `shape_mismatch` 等各自键里，不共用 C / Py / JS 的 `heuristics` 数组
cap.asm_insights | matlab=na c=yes py=na js=na
cap.asm_insights.evidence | 载荷出现 `asm` 键
cap.asm_insights.why.matlab | MATLAB 是解释型语言，没有汇编层可分析
cap.asm_insights.why.py | Python 是解释型语言，没有汇编层可分析
cap.asm_insights.why.js | JavaScript 是解释型语言，没有汇编层可分析
cap.browse_site | matlab=yes c=yes py=yes js=yes
cap.browse_site.evidence | `--browse` 产出站点且含 HTML
cap.site_same_page_names | matlab=no c=yes py=yes js=yes
cap.site_same_page_names.evidence | 站点同时有 `index.html` / `funcs.html` / `file/` / `dir/`
cap.site_same_page_names.why.matlab | MATLAB 站点是另一套：46 个顶层页（`dirs/` + `func_detail.html` + `members.html` …），与 C / Py / JS 的 10 页不同名
```
<!-- /PARITY v1 -->

## 5. 这道门怎么工作

1. 在临时目录里写四份合成夹具（每语言一份，每种调用形态一个专属文件）；
2. 每语言跑一次公开 CLI（`--json --json-level full --callgraph --browse`）；
3. 从**产物**读 56 个在册探针的信号（`yes` / `no`）；
4. 与机器块逐格对账（E2），逆向也响；理由两向（E3）；能力名单两向（E4）；
   人读表 ⇄ 块逐格一致（E5）；缺输入 / CLI 跑不起来 / 实测空集一律红（E6）。

实测成本：四语言各一次、每次约 0.5 s（合成夹具只有几十行），门整体 **~3 s**。

## 6. 下一步

| 顺序 | 动作 | 预期把哪几格变绿 |
| --- | --- | --- |
| 1 | Python 前端 `ast` 化（槽 25） | `classes` / `entities` / `call_edges_qualified` / `call_edges_oneline_body` 的 Py 列（4 格）+ `deps_edges_json` 的 Py 列 |
| 2 | C 实体层（槽 26） | `entities` 的 C 列 |
| 3 | 度量对等（槽 28） | `metrics_complexity` 的 MATLAB 列、`deps_edges_json` 的 Py / JS 列 |
| 4 | 画布对等（槽 29） | `site_same_page_names` 的 MATLAB 列 |
| 5 | 任一槽顺手 | `callgraph_projection` 的 MATLAB 列（**要么真产出、要么明确拒绝**） |

⚠ 顺序不是「重要程度」，是**可修性**：前三项都已有落地轮次与现成的判据族，
最后一项只差一个决定的入口。
