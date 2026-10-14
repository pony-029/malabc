# R101 复盘 —— Python 前端 **`ast` 化**（槽 25）+ 实体层接上产物 + 对等表 **6 格**转绿 + E5 后半

> 承接 R100 §9 的 ★★★ 主刀建议（槽 25 `py_ast_frontend`）。
> 用户长期指令（逐字）：**「每一次都可以使用 superpower skill，联动的必要的 skill
> 深度思考，按照下一步建议实现保证每一次都是真正的实现，并且持续规划 360 轮，
> 720 分钟不断修复和改进，并且最后完整后给出下一次建设性的意见」**
> —— 本轮按此执行：六顶思考帽开场（§3 白帽侦察）→ 按建议落地 → 全程实测 → §13 给下一轮建议。

---

## §1 用户诉求（逐字）与拆解

| 用户原话（跨轮，仍生效） | 本轮落点 |
| --- | --- |
| 「我要的是整个系统的代码的**完全分析**……每一个文件，每一个函数/**甚至每一个变量**都要分析」 | **变量级实体层**：Python 的类属性 / 实例属性（`self.x`）**首次**进载荷（§6） |
| 「三者有**共同的一个基本点**就是对工程代码的深度分析」 | 语言无关 **Entity 契约**（R97 立的槽 24）本轮**真正接上产物**（§5.3 / §6） |
| 「属于三者**差异的点也要各自体现**出来」 | 对等登记表逐格现算；本轮 py 列 5 格 + js 列 1 格转绿（§7） |
| 「更一层的代码中涉及的**动态链接库也务必解析**出来」 | 已有（R100），本轮**未触碰**；`E7–E10` 仍留给槽 34（§9） |
| 「按照下一步建议实现」 | R100 §9 的 ★★★ 主刀 = 槽 25（§4–§6） |

---

## §2 蓝帽：本轮做了什么（一页纸）

```
Python 前端 ast 化（槽 25）
  ├─ 新建 pyast_frontend.py          41,699 B / CRLF / 933 行（双层调度器）
  │    ├─ ast 优先；SyntaxError/ValueError/RecursionError/MemoryError ⇒ 降级词法层
  │    └─ **降级必须写进 limitations**（「我没读到」≠「确实没有」）
  ├─ matlabc.py 接线（7 处锚点）
  │    ├─ _parse_py_source 变双层调度器；原体改名 _parse_py_source_lexical
  │    ├─ 复杂度关键字 → 引用 pyast_frontend.COMPLEXITY_KEYWORDS（单一事实源）
  │    ├─ include_edges 不再硬编码 []（**口径分裂**消灭，py/js 一起受益）
  │    └─ 载荷新增 entities（py 有键；js/asm **根本不写这个键**）
  ├─ entity_model.py 接 py 适配器（_is_property + py_entities）
  │    └─ LANG_SUPPORT["py"]: no → **yes**（并删理由）；R97 的失效句改掉
  ├─ 对等登记表：py 列 5 格 no → yes，**js 的 deps_edges_json 也 → yes**
  │    └─ 记分牌 41/15/8 → **47/9/8**
  └─ 顺手堵一个**新发现的判据空洞**：E5 加「派生数字现算」（§8 / §9）
       └─ 首跑即抓到 2 条：两份 README 里 R96 起就没对过的 40/16/8
```

**门禁**：`check_all.py` 21 个护栏 —— 改完 `matlabc.py` 当期 **2 道红**
（`check_parity_registry` 与 `check_kernel_snapshot` 的 W2），收尾后 **0 红**（§12）。
**门数不变（仍 21 个脚本 / 20 道门 + runner）**；`ROW_SIGNATURE` 仍是 `E1–E6`（§9）。

---

## §3 白帽：起点侦察（**以源码与实测为准，不轻信文档声明**）

起点：HEAD `7220e45`（R100），工作区干净（仅新增 `pyast_frontend.py`）。

先跑一次 `tools/check_parity_registry.py --measure`，把「今天哪几格是空的」钉成**实测**：

```
capability                 matlab   c        py       js
call_edges_qualified       yes      -        no       no
call_edges_oneline_body    -        yes      no       no
deps_edges_json            -        yes      no       no
classes                    yes      -        no       no
entities                   yes      no       no       no
```

五格 py 的**根因**逐条定位到行（不靠猜）：

| 格 | 根因（源码位置） |
| --- | --- |
| `call_edges_qualified` | 词法扫描器**跳过前一个字符是 `.` 的调用点**（`obj.m()` 不成边） |
| `call_edges_oneline_body` | 单行函数体（`def f(v): return g(v)`）里的调用点在定义行被跳过 |
| `classes` | 词法层**原理上**看不见 class（页面无 `classes` 键） |
| `entities` | 同上，且没有实体层 |
| `deps_edges_json` | **口径分裂**：站点用现算 `_ext_dep_edges`，载荷却硬编码 `"include_edges": []` |

### §3.1 红线清单（动手前先立）

| 红线 | 为什么 |
| --- | --- |
| `check_kernel_snapshot` 的 **W2** 必红 | 改 `matlabc.py` 一个字节 ⇒ 快照 stale ⇒ **只能重跑**（只改表 = 把没跑过的数写成跑过的） |
| `check_ir_attribution` 的 **I1** 必须仍是**恰 3 处**写点 | 且**不许下标赋值**造第二容器（`Assign(Subscript("unresolved"))` 会被判 I1） |
| `check_py_js_frontend_shapes` 的 `WANT` 行号/`params` **不许漂** | 那是**手写期望**（独立于产品），钉着 `m → {"params": ["self"], "line": 23}` |
| `HELP_*_SNAPSHOT` | 动 `--help` 正文就得重刷；本轮实测**未动**（§11） |
| 判据签名若变 ⇒ **8 处级联** | 本轮**刻意不变**（§9） |

---

## §4 槽 25 落地：`pyast_frontend.py`

### §4.1 为什么是「双层调度」而不是「换掉词法层」

R66 / R67 把词法扫描器打磨到能挡住文档字符串里的假定义、能跨行取形参 —— 但它在
**原理上**看不见限定调用（`obj.m()`）、看不见单行函数体里的调用点，也没有类 / 字段 /
装饰器 / 注解。`ast` 一次解决这几件事；可它会被 3.7+ 新语法（或 Python 2 风格）
拒掉，而那些文件在词法层**仍然读得出来**。

⇒ **`ast` 优先，失败降级到词法层，而降级必须写进页面的 `limitations`**
（`>= MIN_LIMITATION` 字符），`parser` 键从 `ast` 变 `lexical`。
只静默降级的话，下游会把「词法读不出类」当成「这个文件没有类」——
这正是本仓反复栽的那类**空集判据**。

### §4.2 页面契约（恒 8 键）

`PAGE_FIELDS = (rel, path, functions, imports, classes, globals, parser, limitations)`

AST 页面在旧 9 个函数字段之上**加** `decorators` / `annotations` / `is_async`
（`AST_FUNCTION_FIELDS`），且 `page_problems(strict)` 按**页面自报的 `parser`**
决定该不该带这三个键 —— ast 页面**必须带**，lexical 页面**必须不带**。
（判据跟着 `parser` 走，而不是跟着「谁调的」走。）

### §4.3 判据族 `P1–P5` 与自证

`param_problems` / `function_problems` / `attribute_problems` / `class_problems` /
`page_problems` / `fallback_problems` / `limitation_problems` —— 全是**纯函数**，
`--selftest` 直接喂合成页面，**不另写一份「自证专用」判定逻辑**。

自证：`SELFTEST COUNTS {"bad": 13, "good": 19}`，rc=0。

### §4.4 三项**独立**证据（不靠自证自说自话）

| 证据 | 手段 | 读数 |
| --- | --- | --- |
| ① 自证 | `pyast_frontend.py --selftest` | `{"bad": 13, "good": 19}` |
| ② **装置①**：把**两个门自己的夹具**喂给 ast 层 | `_r101/probe_r101_ast.py` | `ALL PASS`：`shapes.py 9 + neg.py 1 = 10`（**等于棘轮**）、`neg.py 认出的函数 ['real']`（三引号里的 `def ghost` 未误识）、五格信号全 `yes`、`边 4 条 / 未解析 2 条` |
| ③ 3.6 兼容 | `matlabc.py --check-py36 pyast_frontend.py` | 通过（0 问题） |

⚠ 证据②的要害：用的**不是我自己写的夹具**，而是
`check_py_js_frontend_shapes.py` 的 `SHAPES_PY` / `NEG_PY` / `WANT` 与
`check_parity_registry.py` 的 py `FIXTURES` —— 于是「新前端会让既有门漂」这件事
在**动手接线之前**就被证否了，而不是接线之后靠门报警。

---

## §5 接线：`matlabc.py` 七处锚点

| 锚点 | 改动 |
| --- | --- |
| `imports` | 新增 `import pyast_frontend as _py_ast` / `import entity_model as _em` |
| `def_py` | `_parse_py_source` → 双层调度器；**原体改名** `_parse_py_source_lexical` |
| `kw_tuple` | `for kw in ("if ", "elif ", …)` → `for kw in _py_ast.COMPLEXITY_KEYWORDS` |
| `summary_doc` | 旧 docstring 说 `include_edges` **恒为 0** —— 那句**已失效**，改掉 |
| `summary_ret` | `"include_edges": 0` → `len(_deps)`（现算） |
| `ext_payload` | `"include_edges": []` → 现算；并**展开** `**_ext_entity_entries(_efiles, lang)` |
| `ext_entities` | 新增 `_ext_entity_entries`（在 `_emit_lang_site` 之前） |

补丁形状对账（`git diff -U0`）：**删除行恰 8 条**，全是被替换的锚点，**零附带删除**。

### §5.1 复杂度关键字的**单一事实源**

词法层原来是内联 tuple `("if ", "elif ", "for ", "while ", " and ", " or ", "try", "except ")`。
ast 层要按**同一组**关键字统计非结构化的 `and/or`，两处各写一份必然分叉 ⇒
改成 `pyast_frontend.COMPLEXITY_KEYWORDS`（**一个量只许有一份实现**，§4x-5）。

⚠ **如实交代口径差异（不改既有读数）**：词法层按**行内关键字**累加；ast 层按 **AST 结构**
（`If`/`For`/`AsyncFor`/`While`/`Try`/`ExceptHandler` 各 1，`BoolOp` 记
`len(values) - 1`，基 1）。**两者不是同一个量**。已核实 `tests/test_matlabc.py`
对 py `complexity` **没有硬期望**，所以这不是回归；但它是**必须写下来的口径变化**。

### §5.2 口径分裂：`include_edges` **硬编码空数组**

站点早就用现算的 `_ext_dep_edges(model, lang)` 渲染 `deps.html`，而载荷里那句
`"include_edges": []` 是**写死的**。旧 docstring 给出的理由是：

> 「那是 C 的 `#include` 依赖边，扩展前端**没有这个概念**」

—— 而事实是 Py / JS **有** `_ext_dep_edges`（与 C 逐位同形），只是站点在用、载荷没给。
**那是口径分裂，不是「没有」**（R83 ①：「口径类缺陷比功能类危险」——所有读数一起错且都自洽）。

⇒ 两档现算**同一份**：full 档的 `include_edges` 与 summary 档的计数**守恒**。

### §5.3 `entities` 的键策略：**有键 / 无键**（而不是「非空 / 空数组」）

初版写成 `_ext_entities(files, lang)`，对 **js/asm 也写** `"entities": []`。
自查抓到：对等表的 `s_entities(run)` 读的是「载荷里**出现**实体 / 字段类键」——
给 js 一个 `entities: []` 就等于让它**宣称一条不存在的通道**（会**假绿**）。

⇒ 改名 `_ext_entity_entries(files, lang)`：**只 py** 返回 `{"entities": [...]}`，
其余返回 `{}`，调用点用 `**` 展开。**「有通道、本次为空」与「没有这条通道」必须分得开**。

---

## §6 实体层：`entity_model.py` 接上 py 适配器

R97（槽 24）立的契约本轮**第一次真正接上产物**：

| 改动 | 内容 |
| --- | --- |
| 新增 `_is_property(decorators)` | 装饰器文本**尾段**等于 `property`；非字符串一律 False（**不猜**） |
| 新增 `py_entities(files)` | 读 `pyast_frontend` 的原生键（`classes` / `globals`） |
| `LANG_SUPPORT["py"]` | `no` + 理由 → **`yes` + 空理由**（两向登记表：`yes` 不许留理由） |
| docstring「边界」段 | R97 那句「本模块**不接线进 `matlabc.py` 的产物**」**已失效** ⇒ 改掉 |

**失效的散文比缺的散文危险**：留着那句话，下一个人会据此以为「改了适配器也不会动任何读数」。

### §6.1 真读数 vs 哨兵（不许臆造）

`_class_page` 给出的 `methods` **只有名字**（参数与行号在文件级 `functions[]` 里），
所以 `method` / `property` 成员的 **`line` 只能是哨兵 0**；
而属性的 `line` / `annotation` 是**真读数**（拿得到），所以**不走哨兵**。

实测（真产物）：

```
class K: line 7, bases ["object"]
members: method __init__(line 0) · property get(line 0) · field x(line 8) · field v(line 11)
global CONST(line 0)
```

### §6.2 自证

`{"bad": 13, "good": 16}`（`good` 从 R97 的 7 涨到 16 = 新增 9 条 py 正例/反例）。

---

## §7 对等表：py **5 格** + js **第 6 格**

`tools/check_parity_registry.py --measure`（**现跑公开 CLI**，绝不从表或源码字符串反推）：

```
capability                 matlab   c        py       js
call_edges_qualified       yes      -        yes      no      ← py no→yes
call_edges_oneline_body    -        yes      yes      no      ← py no→yes
deps_edges_json            -        yes      yes      yes     ← py no→yes  AND  js no→yes
classes                    yes      -        yes      no      ← py no→yes
entities                   yes      no       yes      no      ← py no→yes
```

### §7.1 为什么是 6 格而不是 5 格（**必须写下来**）

R100 §9 预测「5 格」（只算 py）。实测是 **6 格**，多出来的是 **js 的 `deps_edges_json`**：

`"include_edges": []` 硬编码在 `_run_ext_only` 里，而那是 **py / js 共用的一段代码** ⇒
改一处，两条语言一起变。这不是「顺带」，是**同一处口径分裂**的第二个受害者。
（当初 §3.3 的缺口表把 py/js 分成两行，掩盖了「它们同源」这件事。）

⇒ 记分牌 **`yes` 41 · `no` 15 · `na` 8 → `yes` 47 · `no` 9 · `na` 8**（64 格不变）。

### §7.2 py 列清空、js 列剩 4 格

剩余 `no` 共 9 格：MATLAB 4（`metrics_complexity` / `unresolved_attribution` /
`callgraph_projection` / `heuristics_channel`——**通道不同**，§3.2 的口径分裂）、
C 1（`entities`）、**JS 4**（`classes` / `entities` / `call_edges_qualified` /
`call_edges_oneline_body`）。

---

## §8 发现（本轮最有价值的一条）：三个互相矛盾的数，**没有任何判据在看**

### §8.1 事实

R99 把 `site_same_page_names` 的 MATLAB 列从 `no` 改成 `yes`：

| 处 | 改了吗 |
| --- | --- |
| 机器块 `cap.site_same_page_names` | ✅ 改了 |
| 合计行 `合计 64 格：yes 41 · no 15 · na 8` | ✅ 改了 |
| **§3.3 标题**「真实的缺口：**16** 格」 | ❌ **没改**（其下表求和 = 15） |
| **§3.3 缺口表**逐行 | ❌ 未与标题对账 |
| **两份 README** 的记分牌 `40 yes / 16 no / 8 na` | ❌ **从 R96 起就没对过**（机器块一直是 41/15） |

⇒ 同一份文档里同时挂着 **41/15/8**、**16**、**15** 三个互相矛盾的数。

### §8.2 为什么没人报

`E5` 的原文是「**人读表 ⇄ 机器块逐格一致**」—— 它比的是**格子**。
**合计行、§3.3 标题、缺口表求和、README 记分牌都不是格子**，所以不在任何判据的视野里。

这正是 R82 那条：**「门禁绿 = 恒等式成立 ≠ 覆盖度足够」**（R90 / R96 之后**第 5 次**应验）。

### §8.3 处置

① 三处数字**改对**（本文档同批）；② **给 E5 加「派生数字现算」后半**（§9）。
加完实测：`check_parity_registry.py` 首跑即报 **2 条**，正是两份 README 的
`(40,16,8)` vs 块里的 `(47,9,8)` —— **判据第一次运行就精确命中了它被设计来抓的东西**。

⚠ 顺带修正一处**旧账**：§3.3 标题写「16 格」而它下面的表加出来是 **15**、机器块也是 15
—— 那个 16 从来没有来源（是 R96 时代的数）。本轮一并改成与表、与合计**三处一致**。

---

## §9 E5 后半：**不新开编号**（`E7–E10` 已由槽 34 预留）

### §9.1 首版撞号（实测抓出）

首版补丁把新判据命名 **`E7`**，`ROW_SIGNATURE` 由 `E1–E6` 改 `E1–E7`。
落地后读计划才发现 `docs/EVOLVE_ROADMAP_360.md` 第 34 行早就写着：

```
34 | 7  | t2   | bin_parity_gate | 动态库能力对等判据并入 E 族（**E7–E10**） | -
```

⇒ **抢编号等于让那条槽的登记当场变错**。已 `git checkout` 回滚，改为**并进 E5**。

### §9.2 为什么并进 E5 是**语义正确**的（不是将就）

E5 的定义本来就是「**文档 ⇄ 机器块**一致」。「从格子里算出来的字」正是同一族的另一半：
它们同样只依赖机器块，同样只需要「现算再比」。**不新开编号，也不需要新判据族名字。**

### §9.3 收益：**零处级联**

判据签名保持 `E1–E6` ⇒ R96 实测的那 **8 处级联**（`check_all.py` 树行 / `MIN_GUARDS` /
`GUARD_CONTRACT` / `tests/test_matlabc.py` 写死的门数 / README 门表行 / README 散文门数 ×2 /
`CONTRIBUTING.md` / `matlabc.py` 帮助正文）**一处都不用动**。

⇒ 教训：**加判据族之前先读计划里有没有预留编号**。

### §9.4 E5 后半的四小条

| 条 | 判据 |
| --- | --- |
| `E5a` | 合计行恰好 1 处，`(N, yes, no, na)` == 块里数出来的（含 N == 能力数 × 语言数） |
| `E5b` | 缺口标题「真实的缺口：N 格」恰好 1 处，N == 块里 `no` 的格数 |
| `E5c` | 缺口表**格数列求和** == `no` 的格数（**0 行也红** —— 空集上「求和相等」恒真，R99 的教训） |
| `E5d` | 两份 README 的记分牌句必须在场**且**等于块里数出来的（缺句子也红：删掉 ≠ 没这回事） |

自证：`SELFTEST COUNTS {"bad": 0, "good": 35}`（26 → 35，新增 9 条断言）。
补丁形状：`git diff -U0` **删除行恰 4 条**，全为被替换的锚点。

---

## §10 事故与量具错清单（**先问量具错还是对象错**）

| # | 现象 | 裁定 | 处置 |
| --- | --- | --- | --- |
| 1 | `_complexity` 自证红（实测 2 / 期望 3） | **对象错** | 只判 `iter_child_nodes(cur)` 的孩子，而 `If` 就是 `node.body` 直接子节点 ⇒ 循环里先判 `cur` 自己再压栈 |
| 2 | `_self_attrs` 自证红（`self.v = v` 收不到） | **对象错** | 同一类错（只判孩子）⇒ `rec(node)` 先判 `node` 自己 |
| 3 | 初版 `entities: []` 给所有语言 | **对象错（自查抓到）** | 改 `_ext_entity_entries`：js/asm **不写这个键**（否则 js 假绿） |
| 4 | 顺序反了 ⇒ py 侧 CLI `rc=1`（`AttributeError: module 'entity_model' has no attribute 'py_entities'`） | **顺序**错 | 先落地 `entity_model` 再落地 `matlabc`；其余 py 落 `no` 全是 rc≠0 的**连带**（不是灾难性回归） |
| 5 | 补丁脚本 `apply()` 的反向核对把自己挡住 | **量具错** | 加性锚点（`new` 含 `old`）⇒ 反向「查 `old` 不存在」恒假 ⇒ **反向只查 `new` 唯一** |
| 6 | 删除类锚点 `("x\n", "")` 让唯一性检查恒假（`text.count("")` = 长度+1） | **量具错** | 删除**必须带上下文行**；并加「`new` 为空 = 设计错误」断言 |
| 7 | 收缩型替换被「目标文本已存在 ⇒ 已应用过」误判 | **量具错** | 判据改 `new not in old` 时才查存在性（`new ⊂ old` = 收缩，本来就存在） |
| 8 | 补丁脚本里 `H_OLD/H_NEW` **跨段重名**，后一组覆盖前一组 ⇒ `sig_head` 实际改的是样本、**头部从未被改**（两次同锚点替换第二次静默 no-op，**不报错**） | **量具错** | 改名 `DS_OLD/DS_NEW`；记：**同名变量跨段复用是补丁脚本的静默错误源** |
| 9 | 探针报「函数载荷只有 9 键、没有 `decorators`」，差点据此断言「ast 字段被引擎丢掉」 | **量具错**（第 3 次形态） | **夹具被 shell heredoc 二次加工**：`if a:\n` 里的 `\n` 变成 `/n` ⇒ 文件语法错误 ⇒ 引擎走**降级路径** ⇒ 读到的是 lexical 形态。改判：产品正确（12 键 + `parser=ast`） |
| 10 | `pyast_frontend` 里 `\ufffd`/`\uXXXX` 等非 ASCII 字面量经写入工具规范化 | **已知** | 产品文件一律走**装置源按字节搬运 + 换行转换**（`install_*.py`），并用「装置源 == 仓内文件（只差行尾）」自证 |

⚠ 第 9 条的可复现教训：**探针夹具要落文件再喂**（走文件写入），**不要走 shell 字面量**。

---

## §11 级联：**零处**（判据签名不变的收益）

| 可能出现级联的地方 | 结果 | 证据 |
| --- | --- | --- |
| `HELP_BYTES_SNAPSHOT` / `HELP_CANON_SNAPSHOT` | **未动** | `check_help_contract.py` 全绿（说明 `--help` 字节未变） |
| `check_ir_attribution.py` 的 I1 写点 | **仍恰 3 处** | 该门全绿（未造第二容器） |
| `check_py_js_frontend_shapes.py` 的 `WANT` | **未漂** | 该门全绿（Python 10 个函数 == 棘轮） |
| `check_py36_clean.py` | **77 个 .py 全过** | 含新文件 `pyast_frontend.py` |
| `check_doc_flags.py` / `check_import_graph.py` / README 对等 | 全绿 | `check_all.py` 实测 |
| 判据签名级联（8 处） | **不需要** | §9.3 |
| **内核快照 W2** | **必红 ⇒ 重跑** | §14 |

---

## §12 数字表（全部**现算**）

| 量 | 值 | 怎么来的 |
| --- | --- | --- |
| `pyast_frontend.py` | 41,699 B / 933 行（CRLF） | 与装置源只差行尾（已自证） |
| `pyast_frontend.py --selftest` | `bad 13 / good 19` | 直接跑 |
| `entity_model.py --selftest` | `bad 13 / good 16` | 直接跑（R97 是 7） |
| 装置① `probe_r101_ast.py` | `ALL PASS`（10 个函数 = 棘轮；ghost 未误识；五格信号全亮） | 直接跑 |
| `matlabc.py` 补丁 | `+74 行 / +2959 字符`（删除行恰 **8**） | `git diff -U0` 逐行对账 |
| `entity_model.py` 补丁 | `+123 行 / +5502 字符`（删除行恰 **6**） | 同上 |
| 对等门补丁 | `+211 行 / +8264 字符`（删除行恰 **4**） | 同上 |
| 对等门自证 | `bad 0 / good 35`（26 → 35） | 直接跑 |
| 对等表记分牌 | `yes` 47 · `no` 9 · `na` 8（64 格） | `--measure` 现跑 |
| `tests/test_entity_contract.py` | 8 passed（6 原有 + C6/C6b） | `pytest -q` |
| 全门禁 | 21 个护栏全绿（收尾） | `check_all.py` |
| 门数 | 脚本 21 + runner = 22；**未变** | `MIN_GUARDS = 21` |

---

## §13 未结与下一轮建议（按优先级）

| 优先 | 动作 | 预期把哪几格 / 哪件事变绿 |
| --- | --- | --- |
| ★★★ | **槽 26 `c_entity_layer`**：C 的 `struct`/`union`/`enum`/`typedef`/全局变量/字段正向识别（R87 的 `_is_type_decl` **只做排除**，正向未做） | `entities` 的 **C 列**（1 格）⇒ 记分牌 **48/8/8** |
| ★★★ | **JS 侧同形改造**（js 的 `classes` / `entities` / 限定调用 / 单行体）—— 与槽 25 是**同一件事的另一半**，且**共用同一段载荷构建代码** | JS 的 4 格 |
| ★★ | **MATLAB 4 个 `no` 的通道对等**（`metrics_complexity` / `unresolved_attribution` / `heuristics_channel` / `callgraph_projection`）。前三个是 §3.2 的「口径分裂」；第四个是「**给了开关却静默不产出**」（rc=0、无文件、无提示）—— 要么真产出、要么**明确拒绝** | 4 格 |
| ★★ | **`--json-level summary` 下实体层的信息损失**：现在 `classes`/`globals` 降级成 `n_<键>` 计数 ⇒ C6 那条「载荷 entities == `py_entities(payload files)`」**只在 full 档成立**。要么 summary 档也留一个 `n_entities`，要么**在文档里明写这条限制**（现在只在测试 docstring 里） | 口径清晰度 |
| ★★ | **`entity_model` 的契约跨语言同形判据**：现在 `py_entities` / `matlab_entities` 各有一套「成员种类」映射，没有判据断言「**同一份源码**在两种语言下的**实体字段集**完全一致」 | 契约强度 |
| ★ | **E5 后半的「自维持」缺口**：`E5d` 依赖两份 README 里**存在**那句记分牌；若有人删句，判据会红 —— 但若有人**连判据一起删**，就静默了。可考虑把「记分牌句必须在场」登记进 `check_readme_parity.py` 的**结构**判据（那是 README 的另一个门） | 判据韧性 |
| ★ | R92–R100 复盘入库；MATLAB `binaries.html`；`_r100/corpus_dynlib/libdemo.dll`（44,824 B）是否入库 | 债务 |
| ★ | **`hash()` 配色、`--callgraph` 静默不产出**这类「静默失败」全量排查（R99 已修一处 `_kind_color`） | 静默失败面 |

### §13.1 给用户的一句话建议

**下一步做槽 26（C 实体层）。** 理由：槽 25 与槽 26 是**同一份契约的两条腿** ——
契约（`entity_model.py`）已经跑通一条腿（py），第二条腿（C）**只需要补正向识别**，
不需要再设计；而它一落地，`entities` 这一格就只剩 JS（与 `classes` 一起做），
记分牌会从 47/9/8 走到 48/8/8 → 再走到 **52/4/8**（只剩 MATLAB 的 4 个通道类缺口）。
把「实体层」这一族**一次做完**，比分散到多轮更省上下文（契约、判据族、自证、级联
都只需复用本轮已经踩平的那条路）。

---

## §14 内核快照（W2 重跑）

（本节由 `_r82/probe_kernel_r84.py --arms c asm` + `gen_kernel_run_doc.py` 的实测读数填写，
见 `docs/KERNEL_RUN.md`。）

- **为什么必须重跑**：本轮改了 `matlabc.py` ⇒ `check_kernel_snapshot.py` 的 W2 报
  `provenance.matlabc_sha256` 与 `matlabc_bytes` 陈旧。**只改表不改跑** = 把一个没跑过的数
  写成跑过的，是本仓的**红线**。
- **跑的是什么**：`python _r82/probe_kernel_r84.py --arms c asm`（cwd = 语料根，
  分母 = C 族扩展名的 62,704 个文件；三条铁律见该脚本 docstring）。
- **收尾**：`gen_kernel_run_doc.py` → `docs/KERNEL_RUN.md`，再 `--check` 复核。
