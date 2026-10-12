# R78 复盘：C-1「解析层下沉」—— 注释与内联汇编进入模型

> 承接 `docs/SUPERPOWER_PLAN_R77.md` 的 **C-1**（该方案里唯一「不做就白做」的一步）。
> 方法论：六顶思考帽 × 苏格拉底式追问；白帽一律以「查源码 + 实测」为准，不认叙述。
> 本轮：`--lang c` 的注释与内联汇编进模型/JSON；新增 `--lang asm` 浅层汇编前端。
> **一行都没动 `_c_lex`** —— 8 类既有规则在语料上逐位不变（下方有对照读数）。

---

## 0 一图看懂

```
                 ┌──────────────────────────────────────────────────────┐
   源码 .c/.h ──▶│ _c_lex（**原样不动**）  → 函数 / 调用 / include / 8 类规则 │
                 └──────────────────────────────────────────────────────┘
                 ┌──────────────────────────────────────────────────────┐
   源码 .c/.h ──▶│ _c_comments(text)      → file.comments[]             │  ← R78 新增
                 │ _c_asm_tokens(text)    → 独立词法（**不折叠 `#` 行**）  │
                 │ _c_inline_asm(text)    → file.asm[]（模板/输出/输入/   │
                 │                            clobber/限定符/goto/函数） │
                 └──────────────────────────────────────────────────────┘
                 ┌──────────────────────────────────────────────────────┐
   源码 .S/.s ──▶│ _asm_file_model(text)  → symbols/labels/insn_hist/    │  ← R78 新增
        /.asm    │                            comments/directives        │
                 └──────────────────────────────────────────────────────┘
                                          │
                        ┌─────────────────┴──────────────────┐
                        ▼                                    ▼
              CLI / JSON（新键，旧键不动）          L3 渲染层（C-2，下一轮）
```

---

## 1 动因：为什么必须「下沉」而不是给页面打补丁

R77 白帽已经量出三个硬事实（全部可复现）：

| 事实 | 证据 | 后果 |
|---|---|---|
| 汇编**零解析** | `matlabc.py` 全文搜 `__asm__` / `asm` → **0 命中** | 没有任何字段承载内联汇编 |
| `.S` **零覆盖** | `_C_SOURCE_EXTS` 只有 8 个 C 系扩展名 | 内核 **1,358 个 `.S`** 从未被看过一眼 |
| 注释**被主动丢弃** | `_c_lex` 的注释分支只做行计数、不留正文 | 无注释可渲染、可翻译 |

若只在渲染层补，CLI / JSON 仍然看不见这些数据 —— 每个消费者都得自己再写一遍抽取器，
那就是**第二事实源**。所以本轮的落点是**模型**，不是页面。

---

## 2 白帽：开写前先钉住的一件事（它决定了实现形态）

### 2.1 `_c_lex` 会把 `#` 行折叠成一个不透明 token

`_c_lex`（`matlabc.py:7193`）遇到 `#` 就把整条预处理指令（含反斜杠续行）折叠成**一个**
`pp` token。而内核里最常见的写法恰恰在宏体里：

```c
/* include/asm-generic/barrier.h:21 */
#define nop()	asm volatile ("nop")
```

### 2.2 量化：宏体内的内联汇编占多少

`_r78/probe_asm_scope.py`（仓库外独立探针）全树实测：

| 口径 | 读数 |
|---|---|
| `.c/.h` 内联汇编候选总数 | **13,632** |
| 其中在 `#` 行 / 宏续行里 | **1,964（14.4%）** |
| 含汇编的文件 | 1,724（其中含**宏体内**汇编的文件 422） |
| `include/` 子树的占比 | **93.1%**（`_kernel\corpus\linux-6.19.14\include`） |

⇒ **结论（绿帽）**：内联汇编抽取**不能**复用 `_c_lex` 的 token 流。必须另写一份词法，
唯一的差别就是「`#` 行不再折叠」。这不是洁癖 —— 复用会**静默丢掉 14.4%**。

> 配套纪律：新词法与 `_c_lex` 共用**同一套**注释/字符串识别规则与**行计数口径**，
> 否则注释行号会与函数/告警行号整体错位，而**没有任何别的测试会发现**。

---

## 3 实现

### 3.1 新增函数（全部在 `matlabc.py`）

| 函数 | 职责 |
|---|---|
| `_c_comments(text)` | 注释抽取：`[{line, col, style, text, block_end}]`，`style ∈ {line, block}` |
| `_c_asm_tokens(text)` | **内联汇编专用**词法；`#` 行按普通代码继续词法化 |
| `_c_asm_operand(text, toks, j, close)` | 一个操作数 `[name] "constraint" (expr)` |
| `_c_asm_record(...)` | 按**顶层** `:` 分节：模板 / 输出 / 输入 / clobber / 标签 |
| `_c_inline_asm(text)` | 扫描 `asm` / `__asm__` / `__asm` + 限定符 + `(...)` |
| `_attach_asm_funcs(asm, funcs)` | 挂所属函数名（宏体内的保持 `None`，不猜） |
| `_c_comment_stats(files)` / `_c_asm_stats(files)` | 顶层汇总（键全部排序 ⇒ 运行间逐字节一致） |
| `_asm_file_model(text, rel, path)` | `.S/.s/.asm` 极简前端 |
| `_ext_file_payload(pf)` | 把**扩展块**带进 JSON（见 §5 缺陷 D1） |

### 3.2 数据结构（与 R77 §6.2 的对照）

| 字段 | 落点 | 说明 |
|---|---|---|
| `comments` | file 级（模型 + JSON） | `{line, col, style, text, block_end}` |
| `asm` | file 级（模型 + JSON） | `{line, kind, qualifiers, template, outputs, inputs, clobbers, labels, has_goto, func}` |
| `asm` / `comment_stats` | JSON 顶层 | 汇总（明细仍在 `files[]`） |
| `asm_file_stats` | JSON 顶层（`--lang asm`） | 文件 / 符号 / 标签 / 指令 / 宏 / 指令 TOP32 |
| ~~`func.asm_refs` / `func.comment_ref`~~ | **未做（有意）** | 见 §5 偏差 D2 |
| `_ASM_SOURCE_EXTS` | 模块级常量 | `.S` / `.s` / `.asm`，**独立**于 `_C_SOURCE_EXTS` |

### 3.3 「没动 `_c_lex`」是可以证的，不是自述

`git diff` 里 `_c_lex` 的函数体**字节未变**；并且 §4 有行为对照（内核子树上 8 类规则逐位相同）。

---

## 4 效果读数（全部实测）

### 4.1 旧键逐位不变（硬判据①）

| 语料 | 文件 | 函数 | 旧键对照 | 新增内容 |
|---|---|---|---|---|
| `security` | 258 | 3,694 | **逐位相同** | comments 6,591 · asm 0 |
| `lib` | 651 | 6,141 | **逐位相同** | comments 53,783 · asm **1,472**（33 文件） |
| `include/asm-generic` | 152 | 465 | **逐位相同** | comments 904 · asm 1（`#define nop()` 里那条） |

对账脚本 `_r78/regress_r78.py`：C1 旧顶层键 / C2 每文件 4 字段 / C3 每函数 8 字段
**逐个**相等；C4 要求新键**有内容**（否则「不变」只是空断言 —— 空断言的对手方）。

### 4.2 抽取器比探针更准（一处「量具错」的现场）

`lib`：探针裸正则 1,473 条，抽取器 1,472 条。定位到唯一差异：
`lib/crypto/sha1.c:29` 的 **注释**里写着 `asm("":"+m" (W(t))` ——
抽取器正确跳过（它在 `/* */` 里），**探针多算了**。
⇒ 记一条：**探针的裸正则不是判据**；先问「量具错还是对象错」。

### 4.3 内联汇编的结构提取（`lib` 抽样）

```
statements 1,472 · files_with_asm 33 · with_goto 0
输出/输入/inout = 304 / 830 / 40 · 具名操作数 157
qualifiers = {volatile: 1340}
clobbers   = {%g1,%g2,%r8..%r15,%rax,%rbx,%rcx,%rdx, ebx,ecx,edx, cc,
              memory, mach, macl, r0,r1,r2}
```

`clobber` 里出现 `%g1`（SPARC）、`r0..r2`（ARM）、`%rax`（x86）—— 说明
**多架构代码被如实读出来**，没有按某一架构硬编码。

### 4.4 `.S` 前端（整棵内核，`--lang asm`）

**1,369 个汇编文件 / 4 秒 / 零崩溃**（`.S` 1,358 + `.asm` 11）：

| 读数 | 值 |
|---|---|
| 符号（`.globl`/`.weak`） | 1,375 |
| 标签 | 11,249 |
| 指令总数 | **201,677** |
| `#` 指令（含 `#define`） | 56,865（其中宏 5,625） |
| 注释 | 30,921 |
| 指令 TOP | `mov.l`(4813) `mov`(4759) `add`(3805) `nop`(2450) `mov.w`(1811) `ld`(1732) `addi`(1700) |

`mov.l`（SH）、`addi`（MIPS/RISC-V/PowerPC）、`ld`（ARM）同现 ⇒ 多架构如实覆盖。

---

## 5 缺陷与偏差（诚实交代）

**D1（本轮自己踩到并已修）** `_run_ext_only` 只挑 `rel/imports/functions` 三个通用字段
⇒ 汇编的 `symbols/labels/insn_hist` 在 JSON 这一层**被静默丢掉**。
这是第一次实测发现（`--lang asm --json` 里 symbol 全空），随即补 `_ext_file_payload`。
**教训**：模型里有的数据，不代表 JSON 里有；「数据在」和「数据可交付」是两件事。

**D2（有意偏差）** R77 §6.2 计划的 `func.asm_refs` / `func.comment_ref` **没做**。
理由：那要给每个函数 dict 加键，而函数 dict 是既有多处测试/门禁直接比对的形状；
本轮先把数据落在 file 级（`asm[].func` 已能反查所属函数），**不动函数 dict 的形状**。
这是一次显式取舍，不是遗漏。

**D3（浅层前端的边界，已实测）** `.S` 分类器按行首 token 归类，因此：
* 数字局部标签（`1:`）不被认作 label，却会进 `insn_hist`（如 `1: 1964`）；
* `lock; addl $1, %eax` 这种**分号连写**会把 `lock;` 当成一个助记符；
* `.byte` / 数据表行也会进 `insn_hist`（如 `|` 5709）；
* 统计键 `directives` 指的是 **`#` 行**（含 `#define`），**不含** `.globl` / `.weak` 这类
  **点指令** —— 后者被计入**符号**（冒烟实测：`.globl`+`.weak` ⇒ `symbols 2`、`directives 1`）。
  名字容易误读 ⇒ 下一轮要么改名、要么把点指令也计入。

这些都是「浅层」的应有之义（`.S` 不做宏展开与条件汇编求值，见 §8），但它们**污染了
指令直方图** —— 下一轮应先做「数据段 / 文本段」粗分段，再统计（C28-2）。

**D4（不做语义验证）** 我们报告「这行读了哪些约束、绑了哪个 C 表达式、声明了哪些
clobber」，**不判断 clobber 是否充分**。后者需要约束求解器；`inline-asm-fact-extraction`
技能 §7 的实测结论是：编译器对「漏 clobber」**全程沉默**，而本仓是零依赖 + Python 3.6.5，
用不了 libclang ≥21。这条边界写在 R77 §8，本轮没有越界，也没有假装越界。

**D5（命名撞车，坑的是验证脚本）** 仓里另有一个**旧编号族**的
`test_r78_shell_contract`（`tests/test_matlabc.py:10763`），它在永久红登记册
（`tools/check_known_red.py`）里。远端/克隆验证若用裸 `-k r78`，会把它一起选上 ——
于是「跑红」**不再说明是我弄坏的**。选择器必须写成 `r78 and not shell_contract`。
**判据自己也要先问「量具错还是对象错」。**

---

## 6 两向验证（不动真树）

变异体全部注入在**仓库副本** `_r78/mut_r78/`；真树 `git status` 全程只有本轮的 7 个文件。

| 编号 | 变异 | 目标测试 | 注入 | 还原 |
|---|---|---|---|---|
| M1 | 内联汇编改用 `_c_lex` 的 token 流 | 注释/汇编模型测试 | rc=1 | rc=0 |
| M2 | `+` ⇒ `inout` 映射失效 | 同上 | rc=1 | rc=0 |
| M3 | `_parse_c_source` 不返回新键 | 同上 | rc=1 | rc=0 |
| M4 | `_run_ext_only` 回到「只挑通用字段」 | `.S` 前端测试 | rc=1 | rc=0 |
| M5 | `_c_comments` 不为块注释内换行计数 | 行号口径测试 | rc=1 | rc=0 |
| NEGCTRL | 无害改写（加行尾注释） | 必须绿 | rc=0 | rc=0 |

**5/5 + NEGCTRL = 6/6**（`_r78/mutate_r78.py`）。
M1 是本轮最要紧的证人：它证明「宏体内 asm」这条判据**真的在防一个具体的退化**，
而不是事后补的空断言。

### 6.1 全量回归：FAILED 集合对照（两套基线）

`tests/test_matlabc.py` 有一大批**永久红**（`tools/check_known_red.py` 两向登记在册），
所以判据**不是通过数**，而是 **FAILED 集合的差**：新增失败 = 我弄红的。

第一遍用了 `git archive HEAD` 作基线 —— 它**没有 `.git`**。这本身是个量具风险：
依赖 git 的测试在副本里会**额外**红，而那种红在真仓里不会出现，于是
`new = cur - base` 有可能**掩盖**「既因副本缺 `.git` 而红、又因我的改动而红」的测试。
先用它跑了一遍，结果确实报出 3 个「消失的失败」全是那类伪红
（`test_r30_static_guards_all_clean` / `test_r33_check_all_guard_count_floor` /
`test_r62_gate_row_signatures_two_way`）⇒ **基线的错被看见了**。

于是换 `git clone`（**带 `.git`**，钉在 `fae0a13`）重做基线，并把「同步另外 2 处断言」
之后的当前态再跑一遍：

| 基线来源 | 基线 FAILED | 当前 FAILED | **新增失败** | 消失的失败 |
|---|---|---|---|---|
| `git archive HEAD`（无 `.git`，**修复前**） | 126 | 125 | **2**（即 §7 那两处漏同步） | 3（全是伪红） |
| `git clone HEAD`（有 `.git`，**修复后**） | 123 | 123 | **0** | **0** |

克隆基线的 **123 = 126 − 3**（那 3 个伪红消失），并且**消失的失败 = 0** ⇒ 基线与当前态
**集合完全相同**，判据零噪声。那 3 个伪红在真仓里确实**通过**，已单独复跑确认
（`-k "static_guards_all_clean or guard_count_floor or gate_row_signatures_two_way"`
⇒ `3 passed in 150.40s`）—— 也就是说「基线错」这一次**没有**掩盖任何东西，但**差一点**会。

⇒ 定位到根因、同步断言之后，**新增失败 0**。
两套基线都跑，是因为**先问量具错还是对象错**：`git archive` 副本的 3 个伪红
证明「对照基线必须带 `.git`」，否则判据会在极端情况下失去分辨力。

> 补充一个**我自己的量具错**（同一个教训的第二次）：我先用
> `ls -la a.txt b.txt 2>/dev/null && … || echo 未完成` 判进度 —— 两个路径里只要缺一个，
> `ls` 就返回非零、stderr 又被吞掉，于是**已存在的文件被我判成「未完成」**，
> 白白多等了十几分钟。**一条把 stderr 吞掉又用退出码分支的探针，会把「没找到」说成「没有」。**

---

## 7 门禁与落地

* `tools/check_all.py` **rc=0**（17 道门全绿）。
* **`check_help_contract.py` 曾红**：`--help` 因新增 `asm` 取值与说明而**合法增长**
  （本体 50,676 → **50,792**；规范形 42,223 → **42,284**）。按该门自己的契约
  「在同一提交里更新快照、不许放宽 `HELP_DRIFT_BYTES`」，本提交同步更新了
  `HELP_BYTES_SNAPSHOT` / `HELP_CANON_SNAPSHOT`。
* **`check_ir_attribution.py` 曾红**：I6 要求每个已注册前端**点名**它的 unresolved
  产出点。汇编**刻意不做调用图** ⇒ 新增 `frontends/ir.py::unresolved_none`
  （显式空产出点）并登记 `"asm"`；语言登记 4 → **5**。
* **「语言 4 → 5」是一次级联，共 3 处手写断言**（都在 `tests/test_matlabc.py`）：
  `test_r44_frontends_ir_is_the_only_decision_point`（语言集合）、
  `test_r44_gate_is_registered_and_can_say_no`（写死 `"语言登记 4 个"`）、
  `test_r44_language_registry_is_two_way_and_typed`（语言集合）。
  ⚠ **第一遍只同步了 1 处**（此时 `check_all.py` 17 门全绿、`check_ir_attribution`
  也全绿）—— 是**全量 FAILED 集合对照**把另外 2 处揪出来的（见 §6.1）。
  这就是「**门禁绿 ≠ 没弄红**」的现场：写死数字的断言只有跑整套才会现形。
* 结果：`check_ir_attribution` 报「语言登记 **5** 个…双向一致」。

---

## 8 诚实边界

1. **汇编是结构提取，不是语义验证**（同 R77 §8 第 1 条，本轮未变）。
2. **`.S` 只做浅层**：符号 / 标签 / 指令直方图 / 注释；**宏展开与条件汇编不展开**。
3. **`.S` 不参与 C 的 8 类规则**（`build_edges` / `collect_checks` 显式返回空 —— 是设计）。
4. **注释来自 `#if 0` 清洗后的文本**：被 `_scrub_c_if0` 清空的行里的注释**不出现** ——
   与函数/告警同一口径（死代码不参与分析）。
5. **JSON 体积**：`security` 6.23 MB → 8.13 MB（+30.5%），`lib` 11.32 MB → 22.16 MB
   （+95.7%）。注释正文是主要成本；**整树 JSON 若要产出需先评估**（C28-1）。
6. **「一次看穿全树」不存在**：仍然是「单文件全文 + 树级索引」。

---

## 9 下一轮建设性的意见

| 编号 | 优先级 | 内容 |
|---|---|---|
| **C28-1** | 最高 | 给注释/汇编明细加**开关**（如 `--no-annotations`），并给出「整树 JSON 体积」的实测外推；当前 +96% 的体积增长在整树上未评估 |
| **C28-2** | 最高 | `.S` 直方图**分段**：先粗分文本段/数据段，再统计助记符，修掉 `1:` / `lock;` / `|` 污染（D3） |
| **C28-3** | 高 | C-2 源码视图（`renderers/sview.py`）：全文 + 行内徽章 + 锚点 + 分块；数据层已就绪 |
| **C28-4** | 高 | C-3 译文层（术语词典 + 内容寻址缓存 + 可插拔后端）；`comment_stats` 已给出「要不要翻译」的量化依据 |
| **C28-5** | 中 | `asm` 的**具名操作数**回填：`[name]` 已解析出 `name`，但模板里的 `%[name]` → `%N` 映射还没做（C-1 原本把它列为 `_asm_bind` 的一部分） |
| **C28-6** | 中 | `_asm_file_model` 的 `rel` 仍是 basename（`_rel_of` 按 cwd 算）⇒ 与 C-2 站点同一隐患（C26-2）；⚠ **R90 已修**（asm 前端走 `_build_ext_model`，同一根参数） |
| C26-1 | 高 | 旧单页 `c_report.html` 降为可选（最大 457 MB，浏览器打不开） |
| C25-1 | 高 | 修 B4：`if(foo())` 误判 cast ⇒ 丢调用边 |

---

## 10 拒绝 / 不做（有理由，不是遗漏）

| 项 | 理由 |
|---|---|
| 用 libclang 做 asm 事实抽取 | 本仓**零依赖 + Python 3.6.5**（`check_py36_clean` 守着）；libclang ≥21 是硬前提 |
| 递归展开 `.S` 的宏与条件汇编 | 那是写一个汇编预处理器，超出「浅层」的承诺范围 |
| 给函数 dict 加 `asm_refs` | 见 D2：会动既有形状 |
| 把 `_c_comments` 合进 `_c_lex` | 会动 8 类规则的行号/偏移 —— 本轮所有「逐位不变」的保证都建立在「不动它」之上 |

---

## 附录 A 复现路径

```
# 旧键回归对照（需先有基线副本）
git archive HEAD | tar -x -C _r78/base_repo
python _r78/pair_r78.py            # lib + include/asm-generic 配对回归
python _r78/regress_r78.py <base.json> <after.json> <0|1>

# 两向验证
python _r78/mutate_r78.py          # 5 变异 + NEGCTRL

# 内联汇编规模探针
python _r78/probe_asm_scope.py

# 整树汇编前端
python malabc/matlabc.py <kernel> --lang asm --json out.json
```
