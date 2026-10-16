# R107 复盘 —— 提交后的树上复现内核整树 + 余量判据强度只许升

> 对标 R106 复盘的结构。本轮全部读数**实测**，凡未实测的一律写进 §8 诚实边界。
> 口径：**先问「量具错还是对象错」**；**字节差必须被解释掉**；**读数只认实测**。

## §0 本轮读数一览（全部实测，无一处是声明）

| # | 项 | 读数 | 证据（可复算） |
|---|---|---|---|
| 1 | 内核整树重跑 | `EXIT=0` / **51m20s**；C 臂 `rc=0 2711.9s peak=11094.5MB files=62704 funcs=743509`；asm 臂 `rc=0 3.1s` | `_r107/kernel_rerun_r107.log` |
| 2 | 三份**在册**产物 | sha256 **逐字节全同** R106：`9a6bd04c…` / `dff83833…` / `c4260966…` | 与 `_r107/prerun/` 副本 `open(...,'rb')` 比对 |
| 3 | 派生摘要 `AGG_r84.json` | **7 处差异，全部是归属/时钟**；**零个**与时钟无关的计数器不同 | 逐字段 `walk()` 递归比对 |
| 4 | provenance 的**可比性** | 盘上 `matlabc.py` sha256 `cd9f84ce…` **== HEAD 提交里的字节**（`IDENTICAL`, 1709745 B） | `git show HEAD:matlabc.py` vs 盘上 |
| 5 | 边界消解 | R106 那次 `git_head=0b4fbe13…`（R105 的提交）⇒ R107 `git_head=544a1893…`（**含 `cd9f84ce` 版 `matlabc.py` 的那个提交**） | 两轮 AGG 的 `provenance.git_head` |
| 6 | 项 2 余量判据 | `SELFTEST COUNTS {"bad": 0, "good": 45}`；棘轮 `good >= 37` → **`>= 45`** | `python tools/check_all.py --selftest` |
| 7 | 项 2 判据能力 | AST 推导节点名 **15 个** == 文本口径调用点 **15 个**；`pytest.skip` 宿主 **13 个函数**，与 15 个宿主**零交集** | `_r107/probe_margin_nodes.py` |
| 8 | 项 5 围栏扩面 | 扫描面 **75 份 → 88 份**；围栏 **580 个**；违规 **0 项**；下界 `50 → 85` | 门自身 + 独立探针 `_r107/probe_fence_all.py` **两处一致** |
| 9 | 21 道门 | 全绿；计划块闸门 `42 行 / 9 动作 / 0 违规` | `_r107/check_all_r107a.log` |
| 10 | 完整门禁（`--with-tests`） | **`(0, 542, 4)`**；21 门全绿 + 「测试基线一致」+ `EXIT=0`；余量 **22 条**（预算 20 / 宽限 2）/ 源内调用点 15 / **源码节点覆盖 15/15** | `_r107/check_all_with_tests_r107a.log` |
| 11 | 本轮用例增量 | **+1 条**（`test_r107_perf_margin_nodes_derived_and_skip_aware`）；`514 → 515` 条 | AST 现数 disk vs `git show HEAD:` |
| 12 | 改动面 | `tools/check_all.py` +298/-… · `tests/test_matlabc.py` +82/-… · `docs/KERNEL_RUN.md` 重生成 · `docs/TEST_BASELINE.json` 541→542 · 本文件新增 | `git diff --stat` |
| 13 | 围栏扩面**当场**拦截 | 本复盘自身落盘时被门判「围栏 13 为奇数」⇒ 修复后 **0 违规 / 12 个** | §3.4 |

## §1 项 1：**在提交后的树上**重跑内核，并回证三份产物逐字节不变

### §1.1 为什么这一项必须单列

R106 §10.1 留了一条边界：那次重跑是在**尚未提交**的工作树上做的 ——
`AGG_r84.json` 里记的 `provenance.git_head` 是 `0b4fbe13…`（**R105** 的提交），
而被分析的 `matlabc.py`（`cd9f84ce…`）**不在那个提交里**。
于是「产物由这份 `matlabc.py` 产出」这句话，只能靠 `matlabc_sha256` 一个字段撑着，
**HEAD 那一半是悬空的**。

R106 §11 因此把「提交之后跑」列为 R107 的第 1 项。

### §1.2 命令与 provenance（规范命令，不许走默认）

```text
C:\Program Files\Python310\python.exe -u _r82/probe_kernel_r84.py \
    --arms c asm --extra-c "--callgraph E:/matlabc/_kernel/r84/kernel_callgraph.json"
```

> ⚠ **C 臂必须显式带 `--callgraph`**：默认 `--arms c asm` **不带**它 ——
> 调用图就不会刷新，却仍会被登记在新 provenance 之下（`rc=0` 看不出）。
> 这是 R106 已经踩过并写进记忆的一条。

驱动自己打印的指纹：

```text
[23:05:01] provenance: matlabc=cd9f84ce3ac8b1b0 (1709745 B) HEAD=544a1893cf80997a6ec69f62cd9b92f52b07a405
[23:05:01] baseline:   E:\matlabc\_kernel\r81\AGG_r81.json (1951 B, sha256=c6ba4cab681edd52)
[23:56:07] done kernel_c_summary: rc=0 2711.9s peak=11094.5MB files=62704 funcs=743509 json=11355506B
[23:56:20] done kernel_asm_summary: rc=0 3.1s peak=152.3MB files=None funcs=None json=486229B
[23:56:20] 丢弃陈旧条目 kernel_asm_summary：指纹 cd9f84ce3ac8/0b4fbe13bb75 ≠ 本轮 cd9f84ce3ac8/544a1893cf80 ⇒ 不得冒充本轮读数
[23:56:20] 丢弃陈旧条目 kernel_c_summary：指纹 cd9f84ce3ac8/0b4fbe13bb75 ≠ 本轮 cd9f84ce3ac8/544a1893cf80 ⇒ 不得冒充本轮读数
EXIT=0
```

**驱动自带防伪**：它把上一轮（`git_head=0b4fbe13…`）的条目判为**陈旧**并丢弃 ——
「旧读数不得冒充本轮读数」这条纪律，本轮是由工具自己执行的，不靠我记着。

### §1.3 三份**在册**产物逐字节复现（这是本轮的核心裁决）

| 产物 | R106（`_r107/prerun/` 副本） | R107（重跑后） | 裁决 |
|---|---|---|---|
| `kernel_c_summary.json` | `9a6bd04cfd6c7341…` (11,355,506 B) | `9a6bd04cfd6c7341…` | **IDENTICAL** |
| `kernel_asm_summary.json` | `dff8383318922938…` (486,229 B) | `dff8383318922938…` | **IDENTICAL** |
| `kernel_callgraph.json` | `c426096624900f81…` (4,358,990 B) | `c426096624900f81…` | **IDENTICAL** |

> ⚠ **字节数相同 ≠ 字节相同**。上面四份里有三份的字节数本轮**恰好也相同**，
> 但判据是 sha256 —— 逐字节比对，不是比 `len()`。
> 这正是记忆里「**产物字节数 ≠ 图**」那条的日常形态。

### §1.4 派生摘要：7 处差异**必须**被解释掉

`_kernel/r84/AGG_r84.json` **不同**（`b6f3121b…` → `a0d4ed0b…`）。逐字段递归比对：

| 字段 | R106 | R107 | 类别 |
|---|---|---|---|
| `provenance.git_head` | `0b4fbe13…` | `544a1893…` | **归属** |
| `results[0].git_head` | `0b4fbe13…` | `544a1893…` | **归属** |
| `results[0].seconds` | 3.2 | 3.1 | **时钟** |
| `results[0].peak_mb` | 154.5 | 152.3 | **时钟/资源** |
| `results[1].git_head` | `0b4fbe13…` | `544a1893…` | **归属** |
| `results[1].seconds` | 3027.6 | 2711.9 | **时钟** |
| `results[1].peak_mb` | 11094.4 | 11094.5 | **时钟/资源** |

**结论：零个「与时钟无关的计数器」不同。** 与 R106 §1.3 的形状一致（那次是 8 处，
本轮 7 处 —— 差的那一处是 `json_bytes`：R106 那次它与 R81 不同，本轮 R84⇄R84 相同）。

第 2、3、5 行的 `git_head` 差异不是噪声，**正是本项要的证据**：
它逐字记录了「上一轮跑在 `0b4fbe13`（不含 `cd9f84ce`），这一轮跑在 `544a1893`（含）」。

### §1.5 W 门

`tools/check_kernel_snapshot.py`（判据族 W1–W7）**只把 `provenance.matlabc_sha256`
与 `provenance.matlabc_bytes` 拿去与盘上现算比对**（W2），`git_head` 只要求「在册」、
**不比对**。所以：

* 本轮**没有**改 `matlabc.py` ⇒ `matlabc_sha256` 仍是 `cd9f84ce…` ⇒ **W2 不红**；
* 反过来说，**任何**对 `matlabc.py` 的字节级改动都会让 W2 立刻红 —— 这条约束
  直接决定了 §4（项 6）为什么**必须**延后到下一轮。

## §2 项 2：余量判据强度只许升（节点名从源码推导 + 感知 `skipped`）

### §2.1 改之前它弱在哪

R106 的余量判据只做一件事：把 `$MALABC_PERF_MARGIN_LOG` 里的记录与
**手写在门里的节点名清单**对账。两处弱：

1. **清单是手写的** ⇒ 源码里新增一个 `_emit_perf_margin(...)` 调用点，
   门**不会红**（那条读出「没接上」，但没接上的东西不在清单里，清单自然不报）。
   这违反 ㉛「**候选集要能推导，不能人工挑**」。
2. **不认识 `skipped`** ⇒ 若某个宿主函数在本机被 `pytest.skip`（例如没装 node），
   它的余量记录自然缺失，门会把它读成「**判据没接上**」——**把环境事实误判成缺陷**。

### §2.2 落盘形状（`tools/check_all.py`，+298/-…）

| 块 | 内容 |
|---|---|
| A | `import ast` |
| F | `PERF_MARGIN_CALLEE`、`_SKIP_LINE_RE`、`_ast_str_const(node)`（先 `.value` 后 `.s`，避开 `DeprecationWarning`）、`perf_margin_nodes(src) -> (nodes, spans)`、`parse_skipped_hosts(text, spans) -> (hosts, problems)` |
| F' | `perf_margin_problem(records, problems, callsites, expected=None, skipped=None)` 加**三支**：`expected is None` ⇒ 红（推导失败不许静默放行）／`len(expected) != callsites` ⇒ 红（两口径不一致）／`miss` 扣掉**宿主被跳过**的之后仍非空 ⇒ 红／`stale`（陈旧登记）⇒ 红 |
| G | `format_perf_margin_lines(...)` 增「源码节点覆盖 x/y」—— **绿灯也要报读数**（㉜） |
| H | `_run_tests` 的 pytest 命令加 `-rs`（否则跳过行根本不出现在输出里） |
| I | `tests_gate_problem` 里接 `perf_margin_nodes()` / `parse_skipped_hosts()`，把 `_skprobs` 作为**第三条独立判据** |
| J | `_selftest()` ⑨ 重写 + **8 条新断言** |

`perf_margin_nodes` 的两处细节值得写下来：

* `spans` 起行**含装饰器**（`end_lineno` 兼容 Py3.6）—— 否则 `@pytest.mark.xfail`
  包着的宿主函数，跳过行落不进它的区间；
* `_ast_str_const` 先取 `.value` 再取 `.s` —— 同一份源码要在 3.13 与 **3.6.5** 上
  都解析得出（`check_py36_clean.py` 扫全仓 `.py`）。

### §2.3 自证：`37 → 45`（**实测**，不是手数）

```text
SELFTEST COUNTS {"bad": 0, "good": 45}
```

⚠ 写补丁时我**手数过 34、35 两次**，两次都被实跑当场抓住 —— 所以门里的注释
现在写的是「R107 **实测** 45 条」「**读数只认实测**」，并且下界棘轮
`good >= 37` → **`good >= 45`**（㉖：判据强度只许升）。

自证里最容易做错的一条（我特意写进去了）：**坏样本必须把 `expected` 给对**。
否则新加的 `expected is None ⇒ 红` 那一支会让坏样本「**红了，但红错了理由**」——
一条**因为错理由而红**的自证，验的是别的判据。

### §2.4 在真仓库上量出来的能力边界（**这条比实现更重要**）

用只读探针 `_r107/probe_margin_nodes.py` 在真源上实测：

| 读法 | 结果 |
|---|---|
| AST 推导出的节点名 | **15 个** |
| 文本口径 `count_perf_margin_callsites` 的调用点 | **15 个**（16 处文本匹配里 `def` 行不计） |
| 两个口径 | **一致**（`15 == 15`） |
| 含 `pytest.skip`/`importorskip`/`xfail` 的函数 | **13 个** |
| 上面两个集合的交集 | **∅（零交集）** |

⇒ 「感知 `skipped`」这条能力**在当前真仓库上恒不触发**。
它是**能力**（把环境事实与缺陷分开），**不是**一个修复 —— 本轮**如实**这样记，
不把它说成「修掉了一个 bug」。

## §3 项 5：`harness/README.md` 纳入围栏扫描（并**独立复核**扫描本身）

### §3.1 缺口

R104b 修了「围栏按序号奇偶配对」，但扫描范围是
`docs/*.md` + 仓库根 `*.md` = **75 份 / 538 个围栏**。
全仓 `*.md` 是 **88 份 / 580 个围栏** —— **漏扫 13 份**：
`ci-examples/README.md`、`docs/analysis/*.md`（6 份）、`flow/FLOW_REPORT.md`、
`flow/INDEX.md`、`flow/README.md`、`flow/source/INDEX.md`、**`harness/README.md`**。

先从**不问门的意见**：把这 13 份逐个喂给判据，实测 **0 份脏**。
（⇒ 缺口是「**没在看**」，不是「看漏了脏文件」。这两件事必须分开报。）

### §3.2 落盘

| 改动 | 内容 |
|---|---|
| `FENCE_MIN_DOCS` | `50 → **85**`（88 份实测 ⇒ 留 3 份余量，**不写 88**：下界是「样本被删掉」的对手方，不是当前值快照） |
| `FENCE_SKIP_DIRS` | 新增，`frozenset((".git","__pycache__","node_modules",".workbuddy",".pytest_cache","dist_bin","_build"))` |
| `_fence_docs(root)` | 改 `os.walk` 全仓遍历 + 跳过登记目录 |
| 打印口径 | `（全仓 *.md，跳过 %d 个登记目录；下界 %d 份）` |

实测：

```text
check_all: 文档围栏闸门：扫 88 份文档 / 围栏 580 个 / 违规 0 项（全仓 *.md，跳过 7 个登记目录；下界 85 份）
```

与独立探针 `_r107/probe_fence_all.py` 的两个数**逐字相同**。

### §3.3 同时补上「扫描本身」的对手方（R104b ㊱㊲ 的直接落地）

只把范围调大，就又多了一条**能被静默蒙混**的判据：门漏扫一个目录、而那个目录
**恰好干净**，读数一模一样。所以 R104b 那条回归用例本轮**同步改造**：

* 扫描范围改为**复用门的 `_ca._fence_docs(ROOT)`**（一个量只许有一份实现）；
* **另加独立复核**：用例自己再 `os.walk` 收集一遍 `_seen`，然后
  `assert _got == _seen` ——「门漏扫一个目录」与「那个目录恰好干净」
  **这才分得开**。

### §3.4 扩面**当场**就抓到了一份脏文档 —— 而它正是本复盘自己

落盘 `docs/SUPERPOWER_REVIEW_R107.md` 时，我按惯例用**门自己的**判据
（`check_all.md_fence_problems`）当场核了一遍，得到：

```text
围栏总数 13 为奇数 ⇒ 末尾内容被吞进代码块
```

**我写的这份文档里有 13 个围栏**（§1.4 结尾多出一个孤立的 ` ``` `，没有配对的
开始）。围栏**总数的奇偶**就能发现它 —— 修掉之后复验 **0 违规 / 12 个**。

这条的证据价值在于**时序**：它发生在**扩展扫描面之后**、且对象是**扫描面里新增的
那份文档**。也就是说，项 5 不是「把范围写大了」，而是**当场就产生了一次真实的拦截**。
（若扫描面没扩到全仓，这份文档也会被扫到 —— 它在 `docs/` 下 —— 但
`harness/README.md` 那 13 份**不会**；而本轮恰好先拿它自身验了判据。）

⚠ 同一条纪律的第 39 次复现：**围栏缺陷不报错**。这次是**门**抓住的，
不是我看出来的 —— 那正是把判据做成机器可读的收益。

## §4 项 6：MATLAB `--callgraph` 缺陷的口径统一 —— 裁定为**纯文档**，本轮**故意不动**

按 R106 §11 项 6，这一项要「把文档/帮助与对等表里那一格的口径统一（不许保持现状）」。
本轮逐处查完，结论比预期小：

| 位置 | 现状 | 裁定 |
|---|---|---|
| `docs/PARITY_MATLAB_C_PY.md` 机器块 | `cap.callgraph_projection \| matlab=yes c=yes py=yes js=yes` | **R106 已统一**（实测由 `no` 变 `yes`，根因＝3 元边 vs 4 元契约） |
| 同文件 §3.3 缺口表 / §6 | 已按 R106 口径改写 | **已统一** |
| `docs/matlabc_USAGE.md` 411–416 | 已列 6 个 `--callgraph*` 开关 | **已统一** |
| `docs/matlabc_FEATURES.md` 139–204 | 有详述 | **已统一** |
| `docs/SUPERPOWER_REVIEW_R98.md` 两处 | 说「MATLAB 无 callgraph」 | **历史轮次记录**，不是活跃口径 —— **不改**（㊱的手术式改动纪律） |
| `matlabc.py:32167–32179` 帮助正文 | 写「R86-3：导出**调用关系的有界投影**」，不交代 MATLAB 也产出 | **唯一未统一处** |

**为什么不改它**：`matlabc.py` 是 W2 的被测物。改它的**任何字节**都会让
`provenance.matlabc_sha256` 与盘上现算不符 ⇒ **W2 立刻红** ⇒
本轮刚做完的 51 分钟整树重跑**当场作废**，且必须再跑一次 51 分钟。

⇒ 这不是「忘了改」，是**判据在正确地阻止一次会让整树读数失效的顺手改动**。
已列入 §9 的 R108 第 1 项，并要求**「改帮助 + 重跑」同轮完成**。

## §5 本轮抓到的错（先问「量具错还是对象错」）

### §5.1 第 29 次量具错 —— 只读探针把「有」读成了「无」

写 `_r107/probe_margin_nodes.py` 的第一版时，我把「这行是不是 `pytest.skip`」
判成 `getattr(node.func, "id", None) == "skip"`。而 `pytest.skip(...)` 的
`node.func` 是 **`ast.Attribute`**（`.attr == "skip"`，**没有 `.id`**）
⇒ 该条件**恒假** ⇒ 探针报「**0 个函数含 `pytest.skip`**」，
与 `Grep` 出来的十几处**直接矛盾**。

修法：

```python
isinstance(node.func, ast.Attribute)
and node.func.attr in ("skip", "importorskip", "xfail")
and getattr(node.func.value, "id", None) == "pytest"
```

⇒ 实测 **13 个函数**。**「探针说 0、grep 说十几」这两个数不可能同时为真** ——
矛盾的读数就是量具错的证据。这条已写进探针源码里。

### §5.2 第 30 次量具错 —— **本轮最贵的一次，且我把它写进了结论**

我用 `ps -W 2>/dev/null | awk '$1==3212{found=1} END{exit !found}'`
判断重跑驱动的存活。23:20:19 它返回「不存在」，我据此宣布
「**重跑被跨 turn 清理了**」，并**基于这个错事实调整了本轮的工作顺序**。

**实际**：后台任务 `4kwuWK` **一直活着**，51m20s 后正常 `EXIT=0`，
三份产物逐字节复现。它的状态从一开始就该用 **task 状态**读，不该用 `ps`。

根因不是 `ps` 本身，而是**确认偏误**：我刚刚在记忆里写下
「后台任务跨 turn 会被清理（进程没了、log 0 字节）」这条坑，
于是把一次**间歇性的空输出**读成了**那条坑的又一次复现** ——
而它当时还给了两个「佐证」（`kernel_c_summary.log` 0 字节、log 停在 23:10:55）。

两条佐证其实都有**别的解释**，而且都在同一轮里被证伪了：
* `kernel_c_summary.log` 0 字节 ⇒ 子进程 stdout 被 `run_arm` 重定向到文件、
  块缓冲未 flush **只是因为还没跑完**；跑完后它是 **7317 B**；
* log 停在 23:10:55 ⇒ 因为驱动的下一句 `print` 在**子进程结束后**，
  它本来就该停在那里 45 分钟。

⇒ 教训（新增一条判据）：**判一个后台任务的存活，读它自己的状态/产物/日志的增长，
不要读进程表**；跨 turn 清理这件事要用**受协议管理的 task** 来避免，
而 `run_in_background` 的任务**本来就是**受管理的 —— 本轮 `4kwuWK` 与
`GEtm2v` 都是它启动的，两个都活到了正常结束。

### §5.3 读数陈旧（`tail` 骗了我一次）

同一次误判里，我还据「15 分钟只有 2 行」推断「驱动卡在 `scope()`」，
并算了两遍 I/O 速率。实际是 **`tail` 读到的是陈旧内容** —— 日志早已推进到
`[23:10:55] run kernel_c_summary`，而 `scope()` 只花了 **5m54s**。
⇒ **读数要看 `ls -la --time-style=full-iso` 的 mtime**，不能只看 `tail` 的最后几行。

### §5.4 一次可推算的算错（已用实测纠正）

上一轮我记「本轮新增 2 条用例 ⇒ 预期 `(0, 543, 4)`」。用 AST **现数**
`disk` vs `git show HEAD:` 得 **+1 条**（`514 → 515`）⇒ 预期应为 `(0, 542, 4)`。
实跑给的就是 `(0, 542, 4)`。

⇒ 这次「**可推算的预期**」先把错误暴露了出来，然后被实测钉死 ——
这正是把「新增用例数」写成**可复算的读数**（而不是记忆）的价值。

## §6 测试基线：`(0, 542, 4)`（实测）

```text
check_all: 实测汇总 (failed, passed, skipped) = (0, 542, 4)
check_all:   余量记录 22 条（预算 20 / 宽限 2）/ 源内调用点 15 处；源码节点覆盖 15/15
check_all: 测试基线一致（docs\TEST_BASELINE.json）
check_all: OK（21 个护栏，全部通过且各自自证；门数下限 21）
EXIT=0
```

* `failed = 0` **且不给容差**（照旧）；
* `passed 541 → 542`：**下界上调 = 收紧**（㉖）。构成可推算（§5.4）；
* `skipped = 4` 不变；
* `TEST_BASELINE.json` 由脚本 `_r107/update_baseline_r107.py` 更新（写前断言
  `bare_lf == 0`、写后**再验一遍整行**），`recorded_round = "R107"`。

**余量读数**（㉜：绿灯也报）—— 本机实测，两条宽限断言如设计般≈1.0：

| 节点 | 实测 | 上限 | 余量 |
|---|---|---|---|
| `p150_watch_and_incrjson_and_taint_svg` | 6.012 s | 6.000 s | **1.00×** `[宽限]` |
| `p77_incremental_perf_benchmark/inc` | 94.820 s | 102.807 s | **1.08×** `[宽限]` |
| `p77_incremental_perf_benchmark` | 93.461 s | 182.325 s | 1.95× |
| `p161_watch_gate/phase2` | 5.125 s | 20.000 s | 3.90× |
| `c25_large_project` | 43.116 s | 180.000 s | 4.17× |
| …（其余 17 条 ≥ 5.25×） | | | |

⚠ `p77/inc` 的 1.08× 用的是 **R105 归一口径**（`max(0.8 s, 10%×dt_first)`），
不是那个过期的绝对 `+0.8 s`（那是 38% 的偏差）。

## §7 门禁与级联

| 轮次 | 命令 | 读数 |
|---|---|---|
| `r107a` | `check_all.py`（在改 `tests/` **之前**的树上） | 21 门全绿 / `EXIT=0` |
| `GEtm2v` | `check_all.py --with-tests`（**含** `tests/` 改动） | 21 门全绿 + `(0, 542, 4)` + 基线一致 + `EXIT=0` |

**零级联**：本轮**没有新增 `check_*.py`** ⇒ 不触碰那条「改判据签名 = 7 处 / 8 文件」
的级联链；`MIN_GUARDS` 仍 **21**；README 门表仍 21 行（`check_readme_parity` 绿）。

但**有一处必须单独说明的「假零级联」**：`tests/test_matlabc.py` 的用例数
**+1**，而 `--with-tests` 的 `passed` 下界在 `docs/TEST_BASELINE.json` 里 ⇒
**这是一个真实的级联点**（不同于「不新增护栏脚本 ⇒ 零级联」那种）。
所以本轮把它**显式**处理了（§6），而不是让它悄悄过去。

## §8 诚实边界（不许省略）

1. **本次 `--with-tests`（`GEtm2v`）跑的那棵树 == 提交的树**吗？
   跑的过程中我**没有写任何仓内文件**（只读证据 + 只写 `_r107/` 仓外草稿）。
   跑完之后才落盘 `docs/KERNEL_RUN.md` / `docs/TEST_BASELINE.json` /
   `docs/SUPERPOWER_REVIEW_R107.md` ⇒ 落盘后**另跑一次 `check_all.py`（无 `--with-tests`）**
   确认 21 门仍全绿。**测试读数不再重跑**：本轮新增的是**文档与 JSON**，
   它们不进 `tests/` 的断言面（`test_r104b_*` 会扫 `*.md` 的围栏 —— 那条**在**
   `check_all.py` 的围栏门与测试用例里都会再验一次）。
2. **`_r107/` 里的探针与补丁脚本没有入仓**（`probe_margin_nodes.py`、
   `probe_fence_all.py`、`patch_r107_check_all.py`、`blocks/`、`update_baseline_r107.py`）。
   它们是**一次性工具**；其中「探针说 0 / grep 说 13」这条事故已写进 §5.1 与本轮记忆。
   这与 R102 ㉕「**一次性手工探针 = 下一轮同形状的事故**」是**有张力**的 ——
   本轮的处理是：**把结论固化进门自己的自证**（§2.3 的 8 条断言），
   而不是把探针入仓。⚠ 若下一轮仍需**同一形状**的探针，就应当入仓。
3. **墙钟不许归因版本**：`arm_c.seconds` 3027.6 s（R106）→ 2711.9 s（R107），
   比值 **0.90×**。**这不是「变快了」** —— 记忆里的实测事实是「同臂相邻两次可差 3 倍」。
   `peak_mb` 同理（11094.4 / 11094.5 差异无意义）。§1.4 的表已把这两类明确标为
   「不可裁决」。
4. **项 3（台账入库）/ 项 4（槽 26 `c_entity_layer`）本轮未做** ——
   R106 §11 已把它们排在本轮之后，本轮**未**声称完成。
5. **项 6 未做**（§4，因 W2 会红）。R108 第 1 项。
6. **`docs/SUPERPOWER_REVIEW_R107.md` 自身不在 `GEtm2v` 那次跑过的树里** ——
   它是在门禁之后落盘的。§7 第 3 条已说明用「再跑一次 `check_all.py`」补上。
7. **`_kernel/r84/` 里还有两份历史 log**（`kernel_run_r88.log`、`kernel_run_r88b.log`）
   与 `LINUX_KERNEL_R84.html`（23:41 的 mtime 早于本轮）—— 本轮**未触碰**，
   它们是 R88 的产物，不在 `ARTIFACT_NAMES`（W7 只核三份在册产物）。

## §9 下一轮建议（R108）

按依赖顺序，且**每条都写清「为什么必须在这一轮」**：

1. **`matlabc.py:32167–32179` 帮助正文补上「MATLAB 也产出 `--callgraph`」，
   并**同轮重跑整树**。**
   为什么必须同轮：改 `matlabc.py` 的**任何字节** ⇒ `provenance.matlabc_sha256`
   与盘上现算不符 ⇒ **W2 立刻红** ⇒ 本轮 51 分钟的读数当场作废。
   所以「改帮助」与「重跑内核」**必须是同一轮的两半**，不许拆开。
   （代价 ≈ 51 分钟，故**单独一轮**，不塞进别的工作。）
   同步核：`docs/matlabc_USAGE.md` / `FEATURES.md` 里的措辞与帮助正文**互指**是否仍成立。
2. **`evolve_loop.py` + `gen_plan_ledger_digest.py` + `_r82/rounds.jsonl` 入库**
   —— 依赖 R106 已**实测**查清（不是照抄计划原文）：
   `docs/EVOLVE_ROADMAP_360.md` **12 处**（L13/51/69/76/78/83/147/182/221/231/234/579）、
   `tools/check_all.py:421`（**判据正文**，不是注释）、`harness/README.md:32-34`、
   `harness/{mutate_r103.py:59,hunt_flaky_r102.py:51}`、`tests/test_matlabc.py` **7 处**。
   ⇒ **单独一轮、单独验证**（`import_graph` 会为新增模块报环/动态 import）。
3. **槽 26 `c_entity_layer`**：C 侧 `global` / `typedef` **目标类型**的覆盖面缺口
   （已写进 `c_entities` docstring 的「已知信息损失」）⇒ 目标是对等表
   `49/7/8 → 52/4/8` 的第一格。
4. **把「flaky 归因」固化成流程**（R106 §11 项 7 提出，本轮**仍未**固化）：
   ① 门必须报**失败名单**（R102b ㉙ 已有）；② 归因先在 **`git worktree` 的 HEAD 树**上复跑 N 次；
   ③ 修法遵循「**等待的对象必须就是断言的对象**」；④ 修完**本树连跑 ≥10 次**。
   ⚠ **绝不放宽 `failed` 容差** —— 修的是竞态，不是判据。
5. **`_r107/probe_margin_nodes.py` 的「矛盾读数」模式值得固化成门**：
   「两个独立口径给出**不同**的节点数 ⇒ 红」这条已经在 `perf_margin_problem` 里了
   （`len(expected) != callsites` ⇒ 红）；但 `_selftest` 之外**没有**在真仓库上
   主动交叉核对**第三条口径**（正则 vs AST vs 实跑记录）。可考虑把
   `_r107/probe_margin_nodes.py` 的交叉核对并入 `test_r107_perf_margin_nodes_*`。

**债务账（本轮更新）**：
① 已收（R103）；② 已收（R106）；③ `_SITE_DESC` 写死 MATLAB 措辞（照旧）；
④ `set.X`/`get.X`、matlab 边序通道、`resolution.external=0` 哨兵、
MATLAB `binaries.html`（照旧）；**⑤ 新增：`matlabc.py` 帮助正文（见本 §9 第 1 项）**。
