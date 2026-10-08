# SUPERPOWER_REVIEW_R33 —— `--binary-attach` · 可执行的帮助示例 · 双语对等门 · 测量工具的自伤

> 方法：六顶思考帽（白→红→黑→黄→绿→蓝）→ 把上一轮的「下一步建议」C'1–C'10 **逐条落成真装置**
> → **先在真实文件上做隔离探针**（探针不进仓库）→ 用**登记制护栏**把结论锁死（含两向自证）
> → 收尾给出 C''1–C''10。
>
> 本轮的一条新纪律是全文的主线：**测量工具自身的 bug 会伪造出被测对象的 bug** ——
> 所以「两向自证先跑通」必须先于「宣布真实仓库 0 违规」。本轮真的踩了两次（§2.1、§2.2）。

---

## §0 结论先行

1. **`--binary-attach`（C'3）已实装并端到端实测。** 它是**不短路**开关：先照常做源码分析，
   再把源码侧刚发现的未解析调用拿去**显式给出**的二进制里三态对账，一条命令完成。
   实测：`cublasSgemm → library`、`totally_missing_fn_xyz → missing`，
   JSON `unresolved_attribution.summary == {"library": 1, "missing": 1}`；
   **未给该开关时该键不存在**（不留空壳）。
2. **帮助里的示例命令现在会被真的跑一遍（C'1/R4）。** 要求 `rc == 0`，且命令必须**逐字**
   出现在帮助正文里 —— 「复制就能用」从此是断言，不是形容词。
3. **两道新护栏落地：** `check_readme_parity.py`（C'2，中英 README 结构对等）与
   `GUARD_CONTRACT`（C'7，护栏自身的退出码契约）。护栏总数 **7 → 8**，并加了**道数下限**（C'9）。
4. **本轮抓到并修掉了一个「测量工具自伤」级别真 bug：** 退出码依据匹配器 `\breturn\s+0\b`
   会在 `return 0.0` 上命中，于是一个**返回浮点数**的函数被当成「退出码 0 的依据」，
   把一条**陈旧的登记条目洗白成有效**。修法：尾部加 `(?![.\d])`。
5. **本轮还踩了一个「工具默认值改变被测对象」的坑：** 追加测试块时用 `io.open(p, "r")` 读文件，
   那是 universal-newlines 模式，CRLF 被静默翻成 LF ⇒ 整份文件被以 LF 重写，
   `git diff` 显示 16068 行「全改」而真实新增只有 316 行。已归一 CRLF 并全仓自查 `bare_LF == 0`。
6. **质量门终态：8 道全绿**（各自 `--selftest` 也绿），3.6.5 语法门绿（45 个 `.py`），
   R30–R33 家族回归 **33 passed**，R33 家族 **9 passed**。

---

## §1 白帽：事实清单（全部来自真实文件实测）

### 1.1 `--binary-attach` 的实测形态

探针 `_r33/probe_binattach_c.py`（仓库外）造一个 C 源，里面调两个名字：一个在显式给出的
fixture DLL 里有导出、一个哪儿都没有。实测输出：

```
C 未解析调用的二进制归因（待归因 2 个名字；只依据你显式给出的二进制）
name                               attribution            origins / detail
cublasSgemm                        library                libprobe.dll
totally_missing_fn_xyz             missing                在已提供的 1 个二进制里均未找到
attribution summary: library=1  missing=1
```

JSON 侧：`unresolved_attribution = {"summary": {"library": 1, "missing": 1}, "rows": [...]}`。
不给开关时 JSON 的键集合为
`['edges', 'files', 'heuristics', 'include_edges', 'lang', 'operator_impact', 'unresolved', 'version']`
—— **没有** `unresolved_attribution`。

反面探针 `_r33/probe_binattach_missing.py`：指向不存在的文件 → `rc=1` 且消息里点名
`--binary-attach`。

### 1.2 「帮助示例写了但没跑过」是真实缺口

R31/R32 已经把「`--help` 立即返回且非空」装置化，`check_help_contract.py` 也已经核对
*退出码*。但**示例命令本身**从来没有被执行过：一句 `python matlabc.py myproj/ --bogus`
只要语法上像，就能一直躺在帮助里。这是「图文并茂」变成「图文并**骗**」的入口。

### 1.3 中英 README 此前靠人手对齐

`README.md` 与 `README_CN.md` 是 1:1 对应的两份文档（`##` 小节都 13 个）。
此前「保持同步」全靠自觉；一旦某一侧加了一行表格而另一侧忘了，没人会发现。
实测基线：14 个比对块（13 个小节 + 前言），逐节 `(表行, 代码块, mermaid)` 完全相等。

### 1.4 护栏脚本自己的退出码没有契约

`check_help_contract.py` 一直在管**入口脚本**的退出码，但**护栏脚本自身**的
「0=干净 1=违规 2=缺输入」只写在各自的 usage 注释里。实测扫描：9 道护栏里有 5 道
（`check_all` / `check_doc_flags` / `check_patch_ops` / `check_py36_clean` /
`check_subprocess_hygiene`）**没有可解析的「退出码」段** —— 也就是说这句话是 prose，
CI 读不到。

### 1.5 「门少了」这件事没有下限

`check_all.py` 的发现逻辑是「列 `tools/check_*.py`，逐个跑」。所以**把一道护栏删掉**，
`check_all` 依然 rc=0（它只是少跑了一道）—— 「门少了」和「全绿」在信号上无法区分。
这与 `POPEN_STREAMING` / `UNVERIFIABLE` / `EXIT_CONTRACT` 是**同一类**问题：
登记表只增不减、或者集合只少不多，都会让护栏失去意义。

### 1.6 本机环境事实（本轮再次确认）

- pytest 只在 `C:\Program Files\Python310\python.exe`（3.10.10）可用；
- 仓库 blob **全是 CRLF**、`bare_LF == 0`，`core.autocrlf=false`；
- Bash 工具的 PATH 会间歇性抽风（`ls`/`tail` 有时可用有时不可用）⇒ 探测一律用**绝对路径 python**；
- `git diff --stat` 对**行尾**是敏感的 —— 它正是本轮发现行尾事故的工具（§2.2）。

---

## §2 黑帽：真缺陷分级

### 2.1 K1 —— 测量工具把自己的 bug 变成了被测对象的 bug（严重度：高）

`check_help_contract.py` 的 R1b 判据是「登记在 `NO_EVIDENCE` 里的退出码，源码里是否已经
**有依据**了；若有，则这条登记**陈旧**、必须红」。依据匹配器四选一，其中一条是：

```python
r"\breturn\s+%d" % code      #  ← 修前
```

`matlabc_ask.py` 里有一个**返回浮点数**的函数写了 `return 0.0`。`0` 与 `.` 之间就是词边界，
于是 `\breturn\s+0\b` 命中 —— 这条判据认为「源码里有退出码 0 的依据」，
于是一条本应被判为**陈旧**的登记被**洗白成有效**。

**修法：** 尾缀 `(?![.\d])`，把 `return 0.0` / `sys.exit(20)` 这类「看起来像」的写法挡在门外。

**为什么这是本轮最重要的一条：** 它验证了「两向自证必须先跑通，再宣布真实仓库 0 违规」
不是口号。如果先跑真实仓库、看到「0 违规」就收工，这个 bug 会一直躺在那，
并且**方向是危险的**：它只让护栏变松，不会让它变紧。

### 2.2 K2 —— 工具默认值静默改写了被测对象（严重度：中高）

追加 R33 测试块的脚本里：

```python
cur = read(TARGET)                     # io.open(p, "r") → universal newlines！
nl = "\r\n" if "\r\n" in cur else "\n" # cur 里已经没有 "\r\n" 了
```

`io.open(path, "r")` 默认 `newline=None`，会把 CRLF **翻译成 LF**。于是 `"\r\n" in cur`
恒为假 ⇒ 判据认定「这文件是 LF」，整份 16226 行被以 **LF 重写**。
`git diff --stat` 显示 `316` → `32136` 行（16068 增 + 16068 删），而真实新增只有 316 行。

**复核方式（也是本轮的工具）：** 拿 HEAD 的 blob 数 `CRLF` 与 `bare_LF`：`CRLF=15910, bare_LF=0`。
**修法：** `_r33/normalize_eol.py`（文本后缀白名单 + 归一 CRLF + 复核 `bare_LF == 0`）。
归一后 `git diff --stat` 回到 **316 insertions, 0 deletions**。

**注意这与 §2.1 是同一根因的两副面孔：** 都是「工具的默认行为悄悄改变了你以为你在测量的东西」。

### 2.3 K3 —— 重演了本仓 CONTRIBUTING 规则 2 的坑（严重度：中）

第一次尝试追加测试块用的是 **shell 内联** `python -c "...正则/引号/括号..."`，直接失败：

```
bash.exe: eval: line 22: syntax error near unexpected token `('
```

而本仓 `CONTRIBUTING.md` 的硬规则 2 恰恰写着「**不要**用 shell 内联传递含反引号/转义序列的
代码块」。**修法：** 把代码块写成纯文本文件 `_r33/r33_block.py` → `ast.parse` 自检 →
追加脚本再对整份合并文件 `ast.parse` → 通过才落盘。**纪律的价值在于它救的是未来的自己。**

### 2.4 K4 —— 帮助示例不可执行（严重度：中）

见 §1.2。修法是 R4（登记 + 真跑 + 逐字可复制性）。这条的价值不是「多一道门」，
而是把**形容词**（「可直接复制」）变成**可证伪的断言**。

### 2.5 K5/K6/K7 —— 同根因的其余落点（严重度：中）

- **K5：** 双语 README 无门 ⇒ 「同步」是形容词 ⇒ 新增 `check_readme_parity.py`。
  一个刻意的**负设计**：**不比对行数**。中文比英文紧凑，行数相等是错误目标 ——
  把它写进判据会逼人为了凑数而灌水。
- **K6：** 护栏自身退出码无契约 ⇒ 新增 `GUARD_CONTRACT` + 补 5 段「退出码」。
- **K7：** 门数无下限 ⇒ 新增 `MIN_GUARDS = 8` + `_guard_count_problem`，
  **且只在 `tools_dir` 就是本仓时施下限**（复用场景不误伤）。

### 2.6 我自己在本轮的另一次自伤（写下来，避免下一轮重犯）

`matlabc.py` 接线时一度写成 `print(binfmt_text := _render_binary_attribution_text(rows))` ——
海象运算符是 **3.8+**，撞本仓 3.6.5 承诺。当场改成普通调用。
为了让它**不可能再发生**，R33 补了一条**独立复核**测试
（`test_r33_entry_scripts_are_36_syntax_clean_independent_recheck`）：
用护栏之外的代码直接遍历 AST，查 `ast.NamedExpr` 与 `ast.arguments.posonlyargs`。
「护栏 + 独立复核」两套实现看同一件事 —— 护栏自己被改错时仍能发现。

---

## §3 黄帽 / 绿帽：新能力（C'1–C'10 落地表）

| 建议 | 落地物 | 可证伪的断言 | 实测 |
| --- | --- | --- | --- |
| C'1 | `check_help_contract.py` R4：`RUNNABLE` + `_run_safe_example` + `_r4_verdict` | 示例 `rc == 0`；stdio server 则 `rc=0 且零输出`；命令**逐字**出现在帮助里 | 5 条示例命令真跑，全绿 |
| C'2 | `tools/check_readme_parity.py`（新） | 小节数相等 + 逐节 `(表行, 代码块, mermaid)` 相等；**不比对行数** | `14 个小节逐节对等`；自证 `{"bad":4,"good":3}` |
| C'3 | `--binary-attach`（`matlabc.py` + `binfmt/attribute`） | 三态归因只在**显式给出**的二进制上做；未给开关则 JSON 无该键 | `{"library":1,"missing":1}` |
| C'4 | `check_binfmt_fixtures.py` **C7** | PTX `.entry <名>(` 必须后随左括号（1 真 3 假） | 只提出真的那一个 |
| C'5 | `check_binfmt_fixtures.py` **C8** + `binfmt/{model,macho,report}.py` | Mach-O 的 `verified=False` 必须传到报告（`to_text()` 出现「未验证」），且 PE 不被误标 | 自证 `{"bad":4,"good":4}` |
| C'6 | `_code_has_evidence` 尾缀 `(?![.\d])` + `_is_stale_no_evidence` 纯函数 | `return 0.0` 不是依据；`return 0` 是 | §2.1 |
| C'7 | `GUARD_CONTRACT` / `GUARD_SCRIPTS` / `audit_guards`（9 道护栏 × {0,1,2}） | 护栏的退出码也进双向核对 | 补 5 段后全绿 |
| C'8 | `HELP_BYTES` 体积棘轮（下界 400 B / 上界 64 KiB·16 KiB / stdio 记 (0,0)） | 缩水与臃肿都红 | `matlabc.py --help` = 47776 B ∈ [400, 65536] |
| C'9 | `MIN_GUARDS = 8` + `_guard_count_problem` | 删一道护栏 → 红；复用 `--tools-dir` 不误伤 | 双向自证 |
| C'10 | `CONTRIBUTING.md`：验证 5 步→**8 道门**；落盘硬规则 3 条→**4 条** | 新增第 4 条 = §2.1 的教训 | 文档同步 |

---

## §4 蓝帽：本轮建立的不变量

1. **「不短路」与「短路」是两个不同的开关，不该合并。**
   `--binary` 短路（看完二进制就退），`--binary-attach` 不短路（正常分析 + 额外对账）。
   把它们合并会强迫用户二选一 —— 而真实需求是「我既想分析，又想知道这些未解析调用是什么」。
2. **「没给的东西一律 `missing`」优于「猜一个最像的」。**
   一个假阳性会把真缺陷洗白成「来自某个库」，比不归因更糟。归因只依赖**显式输入**。
3. **「键不存在」优于「键存在但为空」。**
   `unresolved_attribution` 只在给了开关时出现。否则下游无法区分
   「没做归因」与「归因了但一个都没命中」。
4. **登记表必须两向核对。** 有而未登记 → 抓；登记了而代码里没有（陈旧）→ **也**抓。
   本轮把这条推广到护栏的退出码（`GUARD_CONTRACT`）与护栏的道数（`MIN_GUARDS`）。
5. **「实例集合只少不多」与「登记表只增不减」是同一类病。** 都需要一条下限或一条上限。
6. **不变量（本次新增）：** *任何测量工具在对自己跑通两向自证之前，不得对被测对象下结论。*

---

## §5 轮次账本（R33 内）

| # | 动作 | 结果 |
| --- | --- | --- |
| 1–3 | 三顶帽子走查 + 探针（`probe_binary_attach` / `probe_readme_parity` / `probe_examples` / `probe_safe_flags`） | 拿到 C'1–C'10 的可实现边界 |
| 4–6 | C'1 R4（示例真跑）、C'8 体积棘轮、C'7 退出码契约 | 三处都在真实仓库上抓到缺口并补齐 |
| 7–9 | C'3 `--binary-attach` 实装 + 接线主流程与 `_run_c_only`（双分支） | 端到端探针通过 |
| 10–12 | C'2 新增 `check_readme_parity.py`；C'4/C'5 夹具 C7/C8；C'6 自伤修复 | 全部两向自证 |
| 13–15 | C'9 门数下限；C'10 贡献指南；R4 可复制性回归 | 8 道护栏全绿 |
| 16–18 | 追加 9 项 R33 回归测试（**先写纯文本文件再 ast 自检**） | `9 passed`；家族 `33 passed` |
| 19–21 | 行尾事故发现与归一；双语 README 图文更新；版本 1.16.67 → 1.16.68 | `bare_LF == 0`；parity 绿 |
| 22 | 公平基线对照 + 对象级校验 + 推送 | 见 §7 |

> 说明：本轮的「60 轮 / 240 分钟」目标是在 R30→R33 的连续迭代里推进的；
> R33 这一轮实际交付的是 C'1–C'10 的**全部十条**，而不是只做一部分。

---

## §6 质量门清单（本轮结束态）

```
$ python tools/check_all.py
[OK  ] check_binfmt_fixtures.py   ... 契约 C1/C2/C3/C4/C5/C6 + R33 新增 C7/C8
[OK  ] check_doc_flags.py         ... 9 份文档/帮助正文的开关全部存在
[OK  ] check_help_contract.py     ... 6 入口 + 9 护栏的退出码双向一致；5 条示例已真跑且 rc=0
[OK  ] check_operator_impl.py     ... 元表 9 kind 全有产出点；未实现 1 个显式登记；交集为空
[OK  ] check_patch_ops.py         ... 算子集合 ⊆ ['del','ins_before']
[OK  ] check_py36_clean.py        ... 本仓 45 个 .py 全部通过 3.6.5 语法门
[OK  ] check_readme_parity.py     ... README.md 与 README_CN.md 的 14 个小节逐节对等
[OK  ] check_subprocess_hygiene.py ... 捕获点 16 全部切断 stdin；run 类全部带 timeout
check_all: OK（8 个护栏，全部通过且各自自证；门数下限 8）      rc=0
```

---

## §7 公平基线对照

方法：`git archive HEAD` 把**未改动树**导出到仓库外，把**当前测试集**复制进去
（同一解释器 + 同一测试集 ⇒ 只隔离「源码改动」这一个变量），两侧都跑
`pytest tests/test_matlabc.py -q -k "not r33"`。

| | pytest 结论 | 耗时 | 失败集合 |
| --- | --- | --- | --- |
| HEAD 源码（基线） | `124 failed, 283 passed, 9 skipped` | 1162 s | — |
| 当前工作树 | `124 failed, 283 passed, 9 skipped` | 1196 s | — |
| 交集比对 | — | — | `only in head = []`、`only in work = []` ⇒ **逐 nodeid 完全相同** |

**读法（很重要）：**

1. **基线自己本来就不绿**（124 failed）—— 这是本仓的历史状态，**不是**本轮引入的。
   所以本轮的结论**不能**建立在「失败数」上，只能建立在**集合相等**上。
2. 失败集合逐 `nodeid` 完全一致 ⇒ 本轮改动**没有**让任何一条既有测试变红。
3. `-k "not r33"` 是把 R33 新增的 9 条单独排除 —— 它们依赖本轮的**新装置**
   （`check_readme_parity.py` / `HELP_BYTES` / `GUARD_CONTRACT`），在 HEAD 里根本不存在，
   放进基线只会得到「必然失败」，反而掩盖真信号。
4. R33 新增的 9 条在**当前树**上单独跑：**`9 passed`**；R30–R33 家族：**`33 passed`**。
5. **为什么不做「失败个数」比较：** 个数相等可以是巧合（一条旧失败修好、一条新失败出现，
   数目抵消）。必须比对**集合**，才能区分「旧失败修好了」与「新失败出现了」。

原始输出留在仓库外：`E:\matlabc\_baseline_r33\{head_out,work_out}.txt`。

---

## §8 探针清单（仓库外，不进 git）

| 探针 | 回答的问题 |
| --- | --- |
| `_r33/probe_binattach_c.py` | C 模式 `--binary-attach` 端到端：三态、JSON 键、无开关时无键 |
| `_r33/probe_binattach_missing.py` | 缺文件时是否红、是否点名开关 |
| `_r33/probe_dispatch.py` | 入口分发与早退路径 |
| `_r33/probe_examples.py` | 帮助示例的可执行性与可复制性 |
| `_r33/probe_safe_flags.py` | 哪些开关是「无副作用」的（R4 登记表的依据） |
| `_r33/probe_readme_parity.py` | 双语结构指标的原始测量 |
| `_r33/show_parity.py` | 逐节 `(表行, 代码块, mermaid)` 打印（规划双语编辑） |
| `_r33/normalize_eol.py` | 行尾归一 + `bare_LF == 0` 全仓自查（§2.2 的工具） |
| `_r33/append_r33_tests.py` | 以「纯文本文件 + ast 自检」方式安全追加测试块（§2.3 的工具） |

---

## §9 C''1–C''10：下一次建设性意见

> 全部落在**已有装置但没接上线**、或**已有承诺但没装置**的地方 —— 避开「再造一个名词」。

1. **C''1 前端外挂化（路线图 B 阶段的第一步）。** 现在 C/Py/JS 前端是**行锚定正则**，
   不是 AST。把 `frontends/` + 统一 IR 立起来，并把 `--binary-attach` 的归因**接到 IR 的
   `unresolved` 节点**上（而不是像现在这样在 `matlabc.py` 里现取现用）。验收：同一份
   JSON 的 `unresolved` 与 `unresolved_attribution.rows` 的 `name` 集合**必须相等**（可写成一道门）。
2. **C''2 预处理器感知。** `#if 0` 里的代码现在照样被分析（本仓已披露，但没有装置）。
   先造探针在**真实**内核风格文件上量出「有多少告警来自被 `#if 0` 屏蔽的代码」，
   再决定：实现最小 `#if/#ifdef` 求值，还是把它升级为**显式登记 + 报告里标注**。
   禁止停在「帮助里写了」。
3. **C''3 把 `binfmt/buildsys.py` 接进默认流水线（有装置没接线）。** 它已能提取
   `Makefile`/`CMakeLists.txt` 的字面量链接意图，却没接进主分析默认路径。
   「有装置没接线」比没有更危险 —— 会让人以为有覆盖。接线后 `--binary-attach` 可自动
   建议「该把哪些库传进来」。
4. **C''4 动态库运行期绑定的**显式边界**。** `dlopen/dlsym/LD_PRELOAD` 目前零覆盖。
   建议做「字面量字符串常量 → 候选库名」的静态近似并**明确标注为启发式**，
   或把「不在范围」写进 `--help` 与报告（二选一，别留空白）。
5. **C''5 `py_undefined_name`：实现或明确拒绝。** 它现在在 `_UNIMPLEMENTED_KINDS` 里。
   要么实现（需要作用域链），要么把「为什么不做、替代方案是什么」写进帮助正文 ——
   让它受 `check_help_contract` 的 R2 管。
6. **C''6 用合成夹具把 Mach-O 从「未验证」推进一格。** `check_binfmt_fixtures.py` 已有
   `_make_pe`/`_make_elf`，加一个 `_make_macho` 即可让 `verified=False` 变成「**有夹具验证**」。
   纪律：合成夹具验证 ≠ 真实样本验证，报告里的措辞必须区分两者（本轮 C8 已经把
   `verified` 做成显式字段，正好承接）。
7. **C''7 把公平基线做成一道门：`tools/check_baseline.py`。** 现在基线是手工跑的。
   自动化：`git archive HEAD` → 仓库外 → 复制当前测试集 → 跑 → **比对失败集合**
   （不是比对失败**个数**：要按 `nodeid` 集合比较，才能区分「旧失败修好了」与「新失败出现了」）。
8. **C''8 把体积棘轮从常数改成相对棘轮。** `HELP_BYTES` 现在是硬编码常数，
   会被随手改大。改成「与上一 tag 相比漂移不得超过 ±N%」+ 常数作为绝对上界（两者取严）。
9. **C''9 退出码契约扩展到 `ci-examples/`。** `GUARD_CONTRACT` 覆盖了 9 道护栏 + 6 个入口；
   `ci-examples/` 的模板脚本还没有契约。CI 模板一旦退出码说谎，用户会照着信。
10. **C''10 打断 `renderers` ↔ `matlabc` 的循环依赖。** 现在靠「模块尾部 import」规避，
    结构脆弱。可引入 `renderers/registry.py` 做显式注册（参照 `binfmt` 的
    `_load_binfmt()` 惰性加载），并加一道门禁止新的循环 import。

---

## §10 明确拒绝做的事（避免下一轮走回头路）

- **拒绝**把 `--binary` 与 `--binary-attach` 合并成一个开关（§4.1）。
- **拒绝**为了「归因好看」而在没给出库时猜一个最像的（§4.2）。
- **拒绝**在 README 右侧补行数来实现「双语一致」（中文更紧凑，行数相等是错误目标）。
- **拒绝**把 `check_readme_parity.py` 也做成「跑 `--selftest` 才算过」的重量级门 ——
  它只需结构判据，重复跑示例命令是浪费（与 `check_help_contract` 的 R3/R4 职责不重复）。
- **拒绝**用手工基线数字当结论：基线必须能在仓库外**重跑**（C''7 要把它自动化）。
- **拒绝**用 shell 内联传递代码块（§2.3）；一律纯文本文件 + `ast.parse` 自检。
- **拒绝**用 `io.open(p, "r")` 读源码文件后原样写回（§2.2）；要么 `newline=""`，要么按字节处理。
