# R106 复盘 —— 内核整树读数**逐字节复现** + R105 §8 六项落地

> 一句话：用户要的「验证 Linux 内核的分析代码」本轮给了**可复算的裁决**——
> 被测物从 `f9d3b15c`(1,698,165 B) 改到 `cd9f84ce`(1,709,745 B) 之后，
> **整树 C 读数一个字节都没动**（三份在册产物 sha256 逐位相同）；
> 同时把 R105 §8 的六项**逐条落地或推进**，其中项 2（追捕装置入库）在**落盘前**
> 就查出它**不是零级联**，把一次可预见的返工提前消掉。

---

## §0 本轮读数一览（全部实测，无一处是声明）

| 面 | 读数 | 出处 |
| --- | --- | --- |
| 内核 C 臂（第二遍） | `rc=0` / **3027.6 s** / peak **11094.4 MB** / 文件 62704 / 函数 743509 / json **11355506 B** | `_r106/kernel_rerun2_r106.log` |
| 内核 asm 臂 | `rc=0` / 3.2 s / peak 154.5 MB / json 486229 B | 同上 |
| 在册产物 `kernel_c_summary.json` | 11355506 B / sha `9a6bd04cfd6c7341` ⇒ **SAME** | `_r106/verify_kernel_rerun_r106.py`（EXIT=0） |
| 在册产物 `kernel_asm_summary.json` | 486229 B / sha `dff8383318922938` ⇒ **SAME** | 同上 |
| 在册产物 `kernel_callgraph.json` | 4358990 B / sha `c426096624900f81` ⇒ **SAME** | 同上 |
| 派生摘要 `AGG_r84.json` | 3765 B / 逐字段差异 **8 处，全部是归属/时钟**；读数叶子一处未变 | `_r106/diff_agg_r106.py`（EXIT=0） |
| 登记表 `docs/KERNEL_RUN.md` | 重新生成 23543 B / CRLF / `bare_lf=0` | `_r82/gen_kernel_run_doc.py` |
| 内核快照门 | `check_kernel_snapshot: OK` / RC=0 | `tools/check_kernel_snapshot.py` |
| 记分牌（对等表） | **49 yes · 7 no · 8 na**（R105 末为 47/9/8） | `docs/PARITY_MATLAB_C_PY.md` + 两份 README |
| 第 20 道门 | `check_parity_registry: OK`（能力 16 格 × 语言 4；在册探针 56 格） | `tools/check_all.py` |
| 余量侧信道 | 源内调用点 **3 → 15**；实跑记录 **22 条（预算 20 / 宽限 2）** | `_r106/check_all_with_tests_r106.log` |
| 追捕装置入库 | `harness/` 6 个文件，全 CRLF；`check_subprocess_hygiene: OK`（Popen 登记点 **5 → 7**） | 同上门禁输出 |
| Py3.6 兼容门 | `check_py36_clean: OK`（本仓 **77 → 82** 个 `.py`） | 同上 |
| 整套门禁（不含测试） | **21 个护栏全部通过** / EXIT=0 | `_r106/check_all_r106.log` |
| 整套测试（第一 / 二 / 三次） | ① `(1, 538, 4)` 红=`test_r72_…`（已按 `_R72_EXTRA_NS` 登记）② `(0, 539, 4)` ③ `(1, 539, 4)` 红=`test_p161_watch_gate`（**既有 flaky，已修** —— 见 §8bis） | `_r106/check_all_with_tests_r106{,b,d}.log` |
| **整套门禁 + 整套测试（第四次，最终）** | **`(0, 541, 4)` + 21 门全绿 + 「测试基线一致」+ EXIT=0** | `_r106/check_all_with_tests_r106e.log` |
| 第 7 项（护栏超时带证据） | `_run` 超时分支：`kill()` → 再 `communicate()` → 贴**最后 6 行**；实测 `.output` 在 3.10/3.13 上**都是 `None`** | `_r106/probe_timeout_evidence.py`；新用例 1 passed |
| 第二支 flaky（`test_p161_watch_gate`） | 竞态修复后**本树连跑 10 次全绿**（而 HEAD 树 5 次里 1 红） | 见 §8bis |

---

## §1 内核验证：改被测物之后，整树读数一个字节都没动

### §1.1 命令与 provenance（规范命令，不许走默认）

```
python _r82/probe_kernel_r84.py --arms c asm \
    --extra-c "--callgraph E:/matlabc/_kernel/r84/kernel_callgraph.json"
```

⚠ 这一步**必须**显式带 `--callgraph`：默认 `--arms c asm` **不刷新调用图**，
于是调用图会**登记在新 provenance 下但内容是旧的**，而 `rc` 依然是 0 ——
**rc 看不出这件事**（这是本轮重跑前就钉住的纪律）。

第二遍跑出来的 provenance：

```
[00:56:57] provenance: matlabc=cd9f84ce3ac8b1b0 (1709745 B) HEAD=0b4fbe13bb75e077…
```

`cd9f84ce3ac8b1b0` 与**盘上现算**一致（`tools/check_kernel_snapshot.py` 的 W2 正是
拿这两个字段与盘上比），`HEAD` 是本次跑那一刻的树顶（R105）。

### §1.2 三份在册产物逐字节复现（**这是本轮的核心裁决**）

对照的是**第二轮起跑前**的底账 `_r106/ledger_post_c_entity.json`
（也就是「4 个补丁已落盘、`matlabc.py` 已改」之后、重跑之前的状态）：

| 产物 | 字节 | sha256[:16] | 判定 |
| --- | --- | --- | --- |
| `kernel_c_summary.json` | 11355506 | `9a6bd04cfd6c7341` | **SAME** |
| `kernel_asm_summary.json` | 486229 | `dff8383318922938` | **SAME** |
| `kernel_callgraph.json` | 4358990 | `c426096624900f81` | **SAME** |

**为什么它该是 SAME（机制，不是巧合）**：C 载荷有**两档 JSON 口径**，
`--json-level summary` 的 `summary` 档**只留签名**，**不带**实体明细；
而本轮对 `matlabc.py` 的改动（`_scan_c_entities` 等 6 函数 + `_c_file_payload`
只在 **full** 档加 4 个键）**只影响 full 档** ⇒ 整树 summary 读数**必然**不动。
预言与实际一致 ⇒ 这是一次**有先验的复现**，不是「跑完看看一样」。
（若它变了，那就是**真发现**，不许解释成噪声。）

### §1.3 派生摘要：从「推断」升级为「逐字段实测」

`AGG_r84.json` 由 probe 从两份产物 + R81 基线**现算**，且它**不在**门的在册名单里
（门自己打印「产物现算核对：**3** 份」，AGG 不在其中）。第一遍重跑时，
底账**只记了 sha/bytes、没留副本** ⇒ 旧内容**无法逐字节重构**，只能给「差异类别」——
那是**当时记录在案的量具缺口**。

本轮把它堵上：`_r106/make_ledger_r106.py` 记底账的同时，把旧产物
**`shutil.copy2` 到 `_r106/stale_r106/`**（并校验副本 sha 与源一致）。于是
`_r106/diff_agg_r106.py` 能真比：

```
provenance.matlabc_bytes      1698165 -> 1709745
provenance.matlabc_sha256     f9d3b15c… -> cd9f84ce…
results[0].matlabc_sha256     f9d3b15c… -> cd9f84ce…
results[0].peak_mb            153.7 -> 154.5
results[0].seconds            3.1 -> 3.2
results[1].matlabc_sha256     f9d3b15c… -> cd9f84ce…
results[1].peak_mb            10628.6 -> 11094.4
results[1].seconds            1991.3 -> 3027.6
```

判据三条（**互补**，都写在脚本里）：① 差异集合**必须非空**（空集 ⇒ 「无差异」是恒真）；
② 每条差异的**叶子名**必须是归属/时钟；
③ 差异里**不许出现任何「读数类叶子」**（`std_funcs`/`json_bytes`/`files`/`funcs`…）——
命中即红，那才是「读数变了」。

⚠ **修过一次自己的量具错**：③ 与 ② 的第一版按**路径前缀**写白名单，
漏了嵌套的 `results[i].*` ⇒ 实测报 6 处「不在白名单」，而它们**全都是**归属/时钟。
改成按**叶子名**判 + 补上黑名单 ③，强度是**升**的（只放宽白名单，同时收紧黑名单）。

**⚠ 又一条「推断 ≠ 实测」**：先前在 `verify_kernel_rerun_r106.py` 的输出里**推断**
差异含 `git_head ×3`；实测是 **`matlabc_sha256` ×3** —— 本轮两次跑的 HEAD 都是
`0b4fbe13bb75`，`git_head` **根本没变**。**推断说得再顺也不许当结论**，
这条错误**躺在已跑过的脚本输出里**，是逐字段实测把它抓出来的。

### §1.4 墙钟：1.52× 的差**不许**归因版本

C 臂 `3027.6 s`（本轮）vs `1991.3 s`（第一遍）= **1.52×**；peak `11094.4` vs `10628.6` MB。
既有的墙钟纪律是「同臂相邻两次**可差 3 倍**」⇒ 1.52× 在范围内，
**不得**读成「改代码变慢了」。要归因墙钟必须**交替轮次取最小**，而本轮两遍是
**同一版本的先后两遍**，不构成对照。

### §1.5 W 门

`tools/check_kernel_snapshot.py` = **OK / RC=0**，W1–W7 全过，其中：
* 「产物现算核对：**3** 份（`kernel_asm_summary.json`, `kernel_c_summary.json`,
  `kernel_callgraph.json`）」；
* 「流程读数：13 站（其中仓外 12 个 —— 存在性**刻意不裁决**，新克隆里没有 `_kernel/`）」；
* 「当前驱动 `E:\matlabc\_r82\probe_kernel_r84.py`」。

---

## §2 项 4 / 项 5：C 实体层 + MATLAB 调用图（记分牌 47/9/8 → **49/7/8**）

这两项在压缩前已落地，本轮复述其**判据链**（因为它们是「真正实现」的样板）：

* `matlabc.py`：新增 `_c_match_brace` / `_c_declarators` / `_c_struct_fields` /
  `_c_enum_items` / `_c_typedef_alias` / `_scan_c_entities` 六个函数；
  `_parse_c_source` 多返回 4 个键；`_c_file_payload` **只改 full 档**；
  MATLAB 主流程补 `_emit_call_relations(_ml_callgraph_model(edges), args, label="MATLAB")`。
* `entity_model.py`：新增 `_txt` / `_line_of` / `c_entities(files)`，并把
  `LANG_SUPPORT["c"]` 从 `no` 改成 `yes`（`reason=""`）。
* **级联是被门按设计报出来的**：第 20 道门当场报两条 **E2b「实现了却没登记」**
  （`entities/c` 与 `callgraph_projection/matlab`）⇒ 同步对等表 14 处 + 两份 README 记分牌
  ⇒ 门转 **OK / RC=0**。实测矩阵 `entities = yes yes yes no`、
  `callgraph_projection = yes yes yes yes`。
* 记分牌 **47 / 9 / 8 → 49 / 7 / 8**（比 R105 §8 预告的 48/8/8 **多翻一格**：
  因为 C 实体与 MATLAB 调用图是**两格**，且都在同一轮落地）。
* **适配器接真产物**由独立用例钉住（C7，`tests/test_entity_contract.py`）：真跑公开 CLI
  读 `--json-level full` 真载荷，夹具里放一行 **注释** `/* struct Ghost { int x; }; */`
  断言它**不**变实体 ⇒ `9 passed`。★ **独立变异对照**（`_r106/negctrl_c7_mutant.py`，
  **不动真树**）：副本基绿 → 注入（把 `for _k in ("structs","unions","enums","typedefs")`
  改成 `for _k in ()`）**即红**，且红在 `assert [s["name"] …] == ["Pair"]` 那一行
  → 还原**即绿** → **真树 `matlabc.py` sha256 未动**（`cd9f84ce…` → `cd9f84ce…`）。

---

## §3 项 1：余量读数接齐（源内调用点 **3 → 15**，实跑记录 **22 条**）

问题（R103 ㉜）：**通过时什么都不打印 = 余量可以悄悄翻面**。此前
`_emit_perf_margin` 只有 3 个调用点（`p77` ×2、`c28` ×1），而高档候选里还有 8 条
**有阈值的**用例一条读数都没有。

本轮补 **12 个调用点**（`c22`/`c25`/`p210`/`r31`×2/`r32`×2/`r33`/`p150`/`p161`×3）。
**唯一的接线纪律**是 R104 ㉝ 那条真事故：**比值的两个操作数必须同量纲** ——
`measured` 必须是**断言真正测的那个量**，`limit` 必须是**那条断言的上界**。
所以每一条都先读出断言行再决定量什么，其中：

* `p210` 量与断言**同一条**（引擎自报的 `elapsed_sec`），不另量墙钟；
* `r32`/`r33` 的循环里逐次计时（`_r31_run([name,"--help"], timeout=60)` 的墙钟），
  并**单独**记 `.../check_all` 那一次（它最接近上界）；
* `p150` **如实记 `kind="tolerance"`**：`--watch` 本来就不退出，`timeout=6` 是
  **限时终止的轮询上界**（比值本来就该 ≈1.0）。记成 `budget` 等于宣称
  「余量 1.0× 的性能门」—— 那是把一个**设计上的等待**读成**性能回归**（㉝ 的反面教材）。

跑完后的表（`check_all: 实测 / 上限 / 余量`，按余量升序）：

| 节点 | 实测 | 上限 | 余量 | 类 |
| --- | --- | --- | --- | --- |
| `p150_watch_and_incrjson_and_taint_svg` | 6.008 s | 6.000 s | 1.00× | 宽限断言 |
| `p77_incremental_perf_benchmark/inc` | 67.970 s | 75.238 s | 1.11× | 宽限断言 |
| `p77_incremental_perf_benchmark` | 68.399 s | 182.325 s | 2.67× | 预算 |
| `p161_watch_gate/phase2` | 4.304 s | 20.000 s | 4.65× | 预算 |
| `c25_large_project` | 34.864 s | 180.000 s | 5.16× | 预算 |
| `p210_benchmark` | 26.036 s | 180.000 s | 6.91× | 预算 |
| `p161_watch_gate/phase3` | 2.855 s | 20.000 s | 7.00× | 预算 |
| `c22_stress_test` | 5.638 s | 60.000 s | 10.64× | 预算 |
| `r31_doc_flags_guard_returns_promptly` | 1.675 s | 60.000 s | 35.82× | 预算 |
| …（余下 13 条 48.48× – 377.38×） | | | | 预算 |

（上表是**第四次** `--with-tests` 的读数；前三次的实测在同一量级内浮动
—— 例如 `p77` 预算项在 68.4 s – 87.1 s 之间，这正是 R103 ㉜ 要「表先于变红出现」的原因。）

**余量记录 22 条（预算 20 / 宽限 2）/ 源内调用点 15 处** —— 表**先于变红出现**
（门把表打在两条判据之前），这就是本项要的效果。

⚠ **本项判据的已知弱点（下一轮的候选）**：门只要求「调用点 > 0 + 有记录 +
至少一条 `budget`」，**不要求**每个调用点都有记录 ⇒ 某一条没跑**不会**红。
更强的版本可从**源码字面量推导**出应到的节点名集合再逐个要求（符合 ㉛「候选集要能推导」），
但必须**感知 `skipped`**（本机 node/jsdom 会让 4 条用例时跳时不跳），
否则会把「本机没装 node」读成「余量读数没接上」。

---

## §4 项 2：追捕装置入库 —— **它不是零级联**（预演查出来的一处真级联）

5 个追捕装置（`hunt_flaky_r102.py` / `ensure_crlf.py` / `to_crlf_r105.py` /
`mutate_r103.py` / `derive_candidates.py`）从**仓外**搬进 `harness/`（债务 ④ 的第一刀）。

**为什么另起 `harness/` 而不是放 `tools/`**：`tools/` 里**只有** `check_*.py`，
且**三道门**在管那份清单（`check_all.py` 的 `MIN_GUARDS` 数 `tools/check_*.py`、
`check_help_contract.py` 的 **G0b** 要求 `tools/` 下每个 `check_*.py` 都被登记、
`check_readme_parity.py` 的 **P4/P5** 要求两侧 README 门表 == 真实清单）。
把「不是门」的东西放进去，等于让三条判据在语义上说谎。

### §4.1 落盘**前**用门自己的函数预演，查出必须同时改一处登记表

先逐道查了「哪些门会**递归扫全仓**」，发现
`tools/check_subprocess_hygiene.py` 的 `SCAN_DIRS = (".", "tools", "binfmt", "renderers")`
—— 那个 **`.` 就是递归整个仓库**（只排除 `.git/__pycache__/.workbuddy/docs/tests/node_modules`），
**`harness/` 不在排除表里**。于是写 `_r106/probe_subprocess_gate_r106.py`：
**import 门自己**，对沙箱里的 5 份源码逐份调 `SH.analyze_source(...)`，再按 `scan()`
的同一口径算 `popen_keys`/`blind_keys`，用 `SH.check_registry` 两向核对。实测：

```
[site] harness/hunt_flaky_r102.py:106 subprocess.Popen  最内层 run_one
[site] harness/mutate_r103.py:42     subprocess.Popen  最内层 run_test
S3 Popen: 未登记：harness/hunt_flaky_r102.py|run_one
S3 Popen: 未登记：harness/mutate_r103.py|run_test
结论：落盘前需要改 tools/check_subprocess_hygiene.py 的键数 = 2
```

`analyze_source` 直接报的 **S1/S2 违规 = 0 条**（两处都已 `stdin=DEVNULL`；
S2 只管 `run/call/check_*`，不管 `Popen`）；**S3**（`Popen` 的超时静态证不出来）需要登记。

**⚠ 时序约束（读源码得到的）**：该门 `--selftest` 的最后一段会
`scan(repo_root())` 并**两向**核对两张表 ⇒ 只落登记键而不落文件报「陈旧登记」，
只落文件而不落键报「未登记」，**二选一必红** ⇒ 两者必须**同一次**落盘。
（这正是「判据是两向的」在**操作层面**的后果。）

逐道排除的另外三道（都读过口径）：`check_ir_attribution.py` 的 I1 只认
「receiver 文本含 `unresolved` 的 `.append/.extend/.insert`」⇒ harness 不碰它；
`check_legal_parity.py` L1–L7 只管 5 份许可/README 文件，**没有**「每个 `.py` 都要许可头」；
`check_browse_clean_manifest.py` 只读 `matlabc.py`。

### §4.2 另一条前置防线：Py3.6 门会扫到 harness

`tools/check_py36_clean.py` 的 plain 模式**扫全仓 `.py`** ⇒ `harness/*.py` 落盘即被审。
所以另写 `_r106/precheck_harness_py36.py`：**在沙箱里**预演
`import_harness_r106.py`（**复用同一份变换逻辑**，不是抄一份），再喂**本仓自己的**
`matlabc.py --check-py36 --max-warnings 0`。

⚠ **第一版沙箱形状错（本轮第 27 次量具错）**：垫片把 `REPO` 写成
`dirname(dirname(__file__))`，而沙箱放在 `_r106/py36pre/`（少了 `harness` 这一层）
⇒ `REPO` 解成 `E:\matlabc\_r106`、`TESTFILE` 不存在、`derive_candidates` 当场 rc=1。
**是沙箱的形状错，不是被预演的东西错** —— 改成**镜像仓库布局**
（`SANDBOX/malabc/harness/` + 复制真 `tests/test_matlabc.py`）后：

```
[check] hunt_flaky_r102   REPO=E:\matlabc\_r106\py36pre\malabc  OK
[check] TESTFILE -> …\malabc\tests\test_matlabc.py  OK
[run] derive_candidates rc=0  行数=41
[run] ensure_crlf rc=0
===== Python 3.6 语法兼容门禁（P114）=====
  扫描 5 个 .py 文件
  统计：文件 5 | 问题 0（error 0 / warning 0）| 干净文件 5
  结论：通过      rc=0
```

### §4.3 落盘与当场验证

`_r106/patch_r106_harness_registry.py`（`tools/check_subprocess_hygiene.py`
459 → 463 行、**零删除行**）+ `_r106/import_harness_r106.py`（6 个文件、全 CRLF、
垫片各恰 1 处、`REPO` 解析 OK、`derive_candidates` 实跑 rc=0、`ensure_crlf` 实跑 rc=0）。
当场验证：

* `tools/check_subprocess_hygiene.py --selftest` = **SELFTEST PASSED / RC=0**，
  真实仓库「运行时捕获点 33；Popen **登记点 5 → 7**；盲区登记点 2」两向一致；
* `tools/check_py36_clean.py` = **OK / RC=0**（本仓 **77 → 82** 个 `.py`）。

**两条预言都成立，且都没有变成返工** —— 这就是「落盘前预演」的全部价值。

⚠ **如实记一条缺口**：`harness/README.md` **不在**文档围栏判据的扫描范围内
（`_fence_docs` 的范围是 `docs/*.md` + **仓库根** `*.md`）。它本身围栏是配平的，
但**没有任何门在管它** —— 与 R104b 那条「围栏缺陷不报错」是同一个盲区的边缘。

---

## §5 项 3：债务 ② 收口（计划块闸门 + `tests/` 转调）

* 仓级：`tools/check_all.py` 新增 `plan_block_rows` / `plan_gate_problems` /
  `plan_gate_from_disk` / `md_fence_problems` / `_fence_docs` / `docs_fence_gate`，
  **常开**（不必 `--with-tests`）：`计划块闸门：数据行 42 / 在册动作 9 个 / 违规 0 项`。
* `tests/` 侧：`test_r106_repo_plan_block_gate` **转调** `check_all.plan_gate_problems`
  （同一份判据不许有两份实现 —— 两份必然漂移），带 8 条两向样本与「分母现算 ≥ 40」。
* **两向实证**（`_r106/probe_plan_gate_negctrl.py`，ALL PASS）：真树 0 违规 /
  注射 A（在册 + 理由）红 / 注射 B（不在册 + 无理由）红 / 摘要 `actions` 为空红 /
  **原文 sha256 未动**。
  ⚠ 第一版锚点匹配不到（`"%s | -" % action`，而真行动作格有 7 个空格填充）
  ⇒ 改为按行整行重拼 + 只在计划块区内搜索 + **断言「注射生效了」** ——
  否则「没生效」会被读成「没抓到」。

---

## §6 项 6：文档围栏判据（常开）

`docs_fence_gate` 常开地扫 `docs/*.md` + 仓库根 `*.md`：本轮实测
**扫 74 份文档 / 围栏 522 个 / 违规 0 项**。它管的是 R104b 那条**不报错的产物缺陷**
（装配脚本插占位符 ⇒ 零长度代码块 ⇒ 内容掉到围栏外 / 被下一对围栏吞掉，而
**围栏总数仍是偶数** ⇒ 只看奇偶看不见）—— 所以判据**两条都判**：零长度块 + 奇偶。

---

## §6bis 第 7 项：护栏超时的读数**必须带证据**（修一条归因盲区）

第二次 `--with-tests` 报：

```
[FAIL] check_ir_attribution.py  （--selftest 挂死（超时））
```

而**同一门的主检查在它上面一行刚 `[OK]` 通过**（≈1 s），同一命令**空载单跑
（Python310 与 3.13 各 5 次）全部 rc=0 / **0.818 s** / `{"bad": 0, "good": 24}`
⇒ 从门给出的读数**分不出**「真挂死」与「环境把这 600 s 吃完了」——
与 R102 ㉙「红数没有名字 ⇒ 门自己就是归因盲区」是**同一族**缺陷。

**先问哪一边错**：不是代码错 —— 空载 0.8 s 反证了它不会挂；是**环境/负载**
（本机系统 Temp 积压 13203 条，且当时有并行负载）。

⚠ **实现方式由实测钉死**：`_r106/probe_timeout_evidence.py` 在两个解释器上实测
`subprocess.TimeoutExpired.output` **都是 `None`**（3.10.10 / 3.13.12）⇒ 若按
`.output` 写，消息里**永远**只会是「（一行都没打）」—— 一条**看着实现了、
其实从不工作**的假装置。证据只能靠 **`kill()` 之后再 `communicate()` 一次**取回
（probe 实测拿到 `b'MARKER_PARTIAL\r\n'`）。

改法（外科式）：

* `tools/check_all.py::_run` 的超时分支：`kill()` → `communicate(timeout=30)`
  收剩余 → 把**最后 6 行**贴进消息（空则「（一行都没打）」）。
  `p.wait()` 被删（它的 reap 职责由 `communicate()` 内部承担，且这是 probe
  **唯一实测过**的形状 —— 不引入未实测的分支）。`Popen` 仍留在 `_run` 里
  （`POPEN_STREAMING` 的键按「最内层函数名」定位，挪进新助手会当场变陈旧登记）。
* `tests/test_matlabc.py` 新增 `test_r106_guard_timeout_carries_partial_output`：
  **两向**（会挂的子进程必须带 `R106_PARTIAL_MARKER` / 不挂的原样返回，
  `rc2 == 0`），并把「`.output` 是 `None`」这条实测**钉死在用例里**。

当场验证：新用例 **1 passed**（5.53 s）；`tools/check_subprocess_hygiene.py
--selftest` = **SELFTEST PASSED / RC=0**、`Popen` 登记点仍 **7**（登记未失效）。

⚠ **这个装置证明了什么、没证明什么**（诚实边界）：第四次 `--with-tests` 里该门
**没有**超时（21 门全绿）⇒ 本条超时确实是**偶发**的环境事件，**新装置这次没有机会
被真的触发**。它的价值在于：**它保证**下次偶发时读数会带上「已经打出了什么 + 有多快」，
而不是像第二次那样只有「挂死（超时）」四个字。**装置本身的两向**由那条新用例
（会挂的必须带标记行 / 不挂的原样返回）承担，不依赖「碰巧再超时一次」。

---

## §7 本轮抓到的五条「错」（先问哪一边错）

| # | 类 | 现象 | 处置 |
| --- | --- | --- | --- |
| 1 | **认知错**（不是量具错） | 先前记「臂跑期间不许往仓里加文件，因为 `--checks all` 会跑 21 道门、含 `check_py36_clean` 扫全仓 `.py`」 | **错**：`matlabc.py:32258` 的 `--checks` 是**分析器的静态检查算子集合**（`uninitialized,dead_code,…,c_array_oob,c_buffer_overflow` 共 10 族），与仓库 21 道门**毫无关系**。白守了一轮（无损失），但不能留着当事实 |
| 2 | **量具错**（我自己的） | `diff_agg_r106.py` 第一版按**路径前缀**写白名单，漏了嵌套 `results[i].*` ⇒ 报 6 处「不在白名单」，而它们**全是**归属/时钟 | 改按**叶子名**判 + 补一条**读数叶子黑名单**（强度升，不是降） |
| 3 | **「推断 ≠ 实测」** | 已跑过的 `verify_kernel_rerun_r106.py` 输出里**推断**差异含 `git_head ×3` | 实测是 **`matlabc_sha256` ×3**（本轮两次跑 HEAD 相同，`git_head` 未变）。**推断躺在已跑过的输出里也是错** |
| 4 | **量具错**（第 27 次） | 预演 harness 的沙箱**形状错**（少了 `harness` 这一层）⇒ `REPO` 解析到 `_r106` | 镜像仓库布局；并在脚本里写清「是沙箱错，不是被预演物错」 |
| 5 | **量具错**（第 29 次，**干跑**抓到） | `patch_r106_guard_timeout_evidence.py` 第一版把 `assert ca.plan_gate_problems("这里没有计划块", digest)` 整行当作锚点**替换掉**，而 `NEW_TEST` 里**没把它带回来** ⇒ 那条 R106 刚加的判据会被**静默吃掉**（`ast.parse` 看得见语法、**看不见判据消失**） | 干跑的对账行打出 `-|    assert ca.plan_gate_problems(...)`；在 `NEW_TEST` 开头补回该行 ⇒ 删除行清单**清空**。**这就是「补丁会悄悄吃掉东西」第 3 次实证**（R90 / R96 之后） |

（压缩前另记两条：**第 25 次**——补丁脚本用 `\uXXXX` 转义写中文，**渲染核对**当场抓到错字
与走样的续行；**第 26 次**——补丁字面量漏尾换行 ⇒ 锚点行的 `\n` 被吃掉、两行粘成一行，
**`ast.parse` 看不见**，由门的 `--selftest` 报 `NameError` 抓出。）

⚠ 另有一条**不是「错」而是边界**：第二次 `--with-tests` 里 `check_ir_attribution.py`
的 `--selftest` 报「挂死（超时）」，而**同一门的主检查先 `[OK]` 通过**、同一命令**空载
单跑（Python310 与 3.13 各 5 次）全部 rc=0 / ≈0.8 s** ⇒ 是**环境/负载相关**的非确定
事件，不是代码缺陷。它的价值是**暴露了一条归因盲区**（见 §6bis）。

---

## §8 测试基线：三场「红数变多」与最终基线（541）

`tools/check_all.py --with-tests` 第一次跑：

```
check_all: 实测汇总 (failed, passed, skipped) = (1, 538, 4)
check_all:   FAILED tests/test_matlabc.py::test_r72_cross_namespace_families_are_registered
check_all: 测试红数变多（1 > 基线 0）—— 新红没有任何门在看，先逐条归因（量具错还是对象错），再修或改表
```

**注意门的行为与 R102 那次形状相反**：R102 是「整套测试红了 23 条而**没有任何门看得见**」，
这次是「门把新出现的那 1 条红**当场报了出来并给出名字**」—— 这正是 R102 补这条判据
想要的效果。

**归因（先问哪一边错）**：不是新判据。本轮给 `s_entities` 升格时新写的 docstring
**开头**就是轮次引用「R106 / 槽 42：…」，而 `check_help_contract.py:1460` 的
`_JUDGE_LIT_RE` 按定义**扫字符串字面量**（`observed_judgement_prefixes` 自己就写了
「**取宽**；夹具名也算」）⇒ 把「第几轮」读成了判据码 `R`。断言消息里的
`Left contains 1 more item: {'tools/check_parity_registry.py': {'R'}}` 把它点得很清楚。

**处置**：沿用 `_R72_EXTRA_NS` 的**既有约定**（`check_browse_clean_manifest.py`
在 R102 的同形登记：「这是**检测器已知的宽读**，不是判据缺口；按本表两向规则登记，
并把事实写在这里（不许只加一行不写理由）」）补一行 + 写清理由 ⇒
`test_r72_cross_namespace_families_are_registered` 单跑 **1 passed**。

**基线更新**（`_r106/update_baseline_r106.py`）：`passed` 534 → **538**（实测新增 2 条用例），
`skipped` 仍 4，`failed` 仍必须 0；`non_determinism_seen` **如实记下那次 1 红**
（不许只留 0 —— 那会把「曾经红过一次」这段历史抹掉）。脚本**写盘前先自证**
「`TEST_BASELINE.json` 逐字节等于 canonical 序列化」，否则拒绝改 ——
免得「更新基线」顺手把整个文件的排版也改掉，让真语义改动淹没在 `git diff` 里。

**最终基线**：`passed` **541** / `skipped` 4 / `failed` **0**（`_r106/update_baseline_r106b.py`
按**第四次实测** `(0, 541, 4)` 更新；构成可推算 = 第三次 539 + 修好 `test_p161_watch_gate`
转绿的 1 条 + 新增 `test_r106_poll_status_gate_two_ways` 的 1 条）。
`non_determinism_seen` 里**保留**第一、三次那两个红记录，**不许只留 0** ——
那会把「曾经红过、以及为什么红」这段历史抹掉。**容差仍为 5，未因本轮放宽。**

---

## §8bis 第三次 `--with-tests` 抓到的**第二支 flaky**：`test_p161_watch_gate`（已修）

第三次读数（`_r106/check_all_with_tests_r106d.log`）：

```
check_all: pytest 退出码 1
check_all: 实测汇总 (failed, passed, skipped) = (1, 539, 4)
check_all:   FAILED tests/test_matlabc.py::test_p161_watch_gate - AssertionError: 修复后 w…
check_all: 测试红数变多（1 > 基线 0）—— 新红没有任何门在看，先逐条归因（量具错还是对象错），再修或改表
```

⚠ **三次 `--with-tests` 红的是三处不同位置**（第一次 `test_r72_cross_namespace…`、
第二次 **0 红**、第三次 `test_p161_watch_gate`）⇒ 强提示**非确定**。

**先问哪一边错**（本轮工作量最大的一次归因）：

1. **是既有 flaky，不是本轮引入** —— 用 `git worktree add … HEAD`（`0b4fbe1`，
   **未改动**的树）单独 checkout 后连跑 5 次：**4 绿 1 红**；而本轮对该用例的改动
   只有 3 行 `+ _emit_perf_margin(...)`，**等待逻辑与断言一字未改**。
2. **机理**：断言消息里的实际读到值是中间态
   `{'state': 'analyzing', 'changed': 1, 'files': ['a.m'], …}`（**没有** `gate` 键）。
   用例 phase2/phase3 的 verdict 观测走两条**互不保证顺序**的写
   （`.gate_fail` 标记 与 `watch_status.json` 的 `gate` 字段）：用例**等**前者、
   **断言**后者 ⇒ **竞态**。⇒ **是量具错**（测试的时序同步对象选错），
   **不是实现缺陷**（两次写是合理语义）。
3. **修法**（判据强度**不降**）：新增 `_poll_status_gate(st_path, want, deadline)`，
   轮询**断言的那个字段本身**；超时后**如实返回最后读到的内容**
   （读不到 / 坏 JSON ⇒ `None`），**不抛异常、不跳过** ⇒ 调用方断言照旧执行并报出实际值。
   —— 这是 R104 ㉝「两个操作数必须同量纲」在**时序**上的对应物：
   **等待的对象必须就是断言的对象**。
4. **当场验证**：`test_p161_watch_gate` 连跑 **10 次全绿**（修前 5 次里 1 红）；
   新增 `test_r106_poll_status_gate_two_ways` **1 passed**（覆盖「等到 / 超时且返回最后值 /
   文件不存在 / 坏 JSON」四路，其中后三路都要求**不抛**）。
5. **附带价值**：本条是**第一次**把「同一棵树两次跑差 1 条」那条历史非确定
   **定位到具体用例 + 具体机理**（R101/R102 当时只能模糊记为边界）——
   R102b ㉙ 补的「把失败名单打出来」在这里兑现了。
6. `_emit_perf_margin` 的位置与语义**不动**（仍量「等 marker 出现/消失」的墙钟）
   ⇒ 余量读数与 R105 §8 项 1 的口径保持一致。

---

## §9 门禁与级联

* `tools/check_all.py`（不带 `--with-tests`）= **21 个护栏全部通过 / EXIT=0**，门数下限 21；
  其中与本轮相关的：`check_kernel_snapshot` OK、`check_parity_registry` OK（56 格）、
  `check_import_graph` OK（**82 个模块** / 模块级环 0 / 惰性环 1 已登记 / 动态 import 2 已登记）、
  `check_ir_attribution` OK（扫描 **82** 个 `.py`，写点 3 处未变）、
  `check_subprocess_hygiene` OK（Popen 捕获点 **7** 全部登记）、
  `check_py36_clean` OK（**82** 个 `.py`）。
  ⚠ 本项**每改一次就重跑一次**（不是只跑一次）：`_run` 超时分支改动后、
  `harness/` 落盘后、`_poll_status_gate` 落盘后，各自都 **21/21 全绿 / EXIT=0**。
* `--with-tests`（**第四次，最终**）：**`(0, 541, 4)` + 21 门全绿 + 「测试基线一致」+ EXIT=0**。
* **级联面结论**：本轮改动触及 22 个脚本中的 4 个
  （`check_all` / `check_help_contract` / `check_parity_registry` / `check_subprocess_hygiene`）
  + 6 个新增 `harness/*`；**预判的三处级联全部被提前化解**（subprocess 登记键、
  Py3.6 扫全仓、`.gitignore`/顶层目录枚举），**没有出现任何意外级联**。
  逐一实测排除过的「嫌疑门」：`check_import_graph`（G1 无环；harness 不引入环）、
  `check_ir_attribution`（I1 只认 `unresolved`）、`check_legal_parity`（无「每文件许可头」）、
  `check_browse_clean_manifest`（只读 `matlabc.py`）、`check_known_red`（只扫测试文件）、
  `check_doc_flags`（只扫 README/CONTRIBUTING + 入口 docstring）。
* 变更集合：**15 个已跟踪文件被改 + `harness/` 6 个新文件 + 复盘 1 个新文件**
  （`git diff --stat`：**1174 insertions / 111 deletions**，未计新文件）。

---

## §10 诚实边界（不许省略）

1. **第二遍重跑不是「同条件原样重跑」**：工作树上有**未提交改动**
   （本轮 4 个补丁 + 文档同步 + 6 个新文件）。能证明的是「被测物 sha256 与登记表
   逐位一致的前提下，读数**在当前工作树下**复现」。要拿**干净**证据必须在
   **没有未提交改动**的树上重跑 —— 登记为下一轮的题。
2. **墙钟不构成对照**（见 §1.4）。
3. **`harness/README.md` 没有门在管**（见 §4.3）。
4. **余量判据不要求「每个调用点都有记录」**（见 §3 末）。
5. **`AGG_r84.json` 不在门的在册名单里**：它的旧内容此前无法逐字节重构，
   本轮靠「落盘前 `copy2` 留副本」才做到逐字段实测；**这条能力依赖执行顺序**
   （先留副本、再重跑），不是自动的。
6. **测试集里已知 flaky 的「支」不止一条**：R101/R102 记的「同一棵树两次全量跑
   差 1 条」本轮第一次被**定位**到 `test_p161_watch_gate`（竞态，已修，连跑 10 次全绿）；
   但**不能**由此推断「只剩这一支」—— 第三次那 1 红恰好落在它上面，不等于别的支不存在。
   `failed` **仍为 0 且无容差**：下一支出现时按同一流程（worktree 上两向、先问哪一边错）逐条修。
7. **`--with-tests` 的读数获取方式有工程边界**：本轮实测，用「后台任务 + 跨轮次」
   的方式起它会**被清理**（进程没了、log 0 字节 —— 因为 stdout 重定向到文件是**块缓冲**，
   被 kill 时不 flush）。可靠做法是**加 `-u`**（实时落盘，中途也能看进度）
   且**不跨轮次**地阻塞等到结束（≈43 min）。这条与代码无关，但会让「读数拿不到」
   被误读成「任务失败」—— 记在这里免得下一轮重踩。

---

## §11 下一轮建议（R107）

按依赖已查清的顺序排：

1. **在「无未提交改动」的树上重跑内核并回证**（把 §10.1 的边界消掉）——
   这次要在**提交之后**跑，让 provenance 的 `HEAD` 与登记表逐位一致，
   并把「重跑前后 sha 相同」变成**同条件**结论。
2. **余量判据强度只许升**（§3 末）：节点名从**源码字面量**推导（符合 ㉛），
   逐个要求有记录；**必须感知 `skipped`**（否则本机没装 node 会被读成「没接上」）。
   先装判据并**看它当场红**，再落实现。
3. **把剩下三个追捕装置与台账入库**：`evolve_loop.py`（`REPO`/`LEDGER` 两个硬编码
   常量 L37/L38）+ `gen_plan_ledger_digest.py`（L25 `sys.path.insert`、L28 `REPO`）
   + **台账 `_r82/rounds.jsonl`**。**依赖已在本轮实测查清**（不是照抄计划原文）：
   * `docs/EVOLVE_ROADMAP_360.md` 里提到「台账 / 环路 / 生成器」的行**确实 12 处**
     （L13/51/69/76/78/83/147/182/221/231/234/579 —— 其余命中是**仓外探针**
     `_r82/probe_*.py` 之类，**不**受台账入库影响，别一起改）；
   * **非 docs 侧另有级联，且有一处是判据级**：`tools/check_all.py:421` 的
     「它由 `_r103/gen_plan_ledger_digest.py` 从环路 `ACTIONS` 现算」（**判据正文**）、
     `harness/README.md:32-34`（自述，本轮刚写的）、
     `harness/mutate_r103.py:59` 与 `harness/hunt_flaky_r102.py:51`（提示语/注释）、
     `tests/test_matlabc.py` 多处（L2545/22503/22549/22552/22557/22606/22644/22645
     —— 它们说的是「`tests/` 不去 import 仓外脚本」这条**理由**，入库后**理由会变**）。
   ⇒ **单独一轮、单独验证**，不许塞进别的轮次（`import_graph` 会为新增模块报
   环/动态 import，也在这里一并算清）。
4. **槽 26 `c_entity_layer`**：C 侧 `global` / `typedef` **目标类型**的覆盖面缺口
   （已写进 `c_entities` docstring 的「已知信息损失」）—— 补齐后对等表
   `49/7/8 → 52/4/8` 的路径是 JS 三格 + MATLAB 三格，先做 **C 的目标类型**这一格。
5. **`harness/README.md` 纳入围栏扫描**（或明确登记「不扫」及理由）——
   把 §10.3 的缺口变成有判据或有意豁免。
6. **`matlabc.py` 的 `--callgraph` 缺陷处置**收尾：本轮已给 MATLAB 补了调用图出口；
   剩下的是**文档/帮助**与**对等表**里那一格的口径统一（不许保持现状）。
7. **把「flaky 归因」固化成可复用的流程**（本轮临时做了一次，值得沉淀）：
   判据是 ① 门必须报出**失败名单**（R102b ㉙ 已有）；② 归因时必须先在
   **`git worktree` 的 HEAD 树**上复跑 N 次（证明是既有还是本轮引入 —— 本轮正是这样
   把 `test_p161_watch_gate` 定性的）；③ 修法遵循「**等待的对象必须就是断言的对象**」；
   ④ 修完在**本树连跑 ≥10 次**才算验证（单次绿说明不了什么）。
   ⚠ 别把它做成「放宽容差」—— `failed` 仍必须 0，修的是**竞态**不是判据。

> 债务账（本轮更新）：① 已收（R103 台账摘要入仓）；**② 已收**（本轮，仓级 + `tests/` 双侧）；
> **④ 第一刀已落**（5 个追捕装置入 `harness/`，剩下 `evolve_loop.py` +
> `gen_plan_ledger_digest.py` + `rounds.jsonl` 见建议 3）；③ `_SITE_DESC` 写死 MATLAB 措辞；
> 其余（`set.X`/`get.X`、matlab 边序通道、`resolution.external=0` 哨兵、
> MATLAB `binaries.html`）照旧。
