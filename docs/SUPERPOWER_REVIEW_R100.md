# R100 复盘 —— 四语言**源码级动态库引用提取** + 第 21 道门 + R99 假声明补正

> **一句话**：用户要的「动态链接库务必都实现分析」此前只有**容器级**的一半
> （`binaries.html` 解析 ELF/PE —— 谁里面有什么，且**要有文件递过来**）；
> 本轮补上**源码级**的另一半（代码想用谁，**只需源码**），四语言共用一份记录
> 形状与一套 `kind` 语义、各自一套 API 表；同轮用 `git log -L` 抓到并补正
> **上一轮的假声明**，并新建第 21 道门让「声明改了、diff 里没有」这一类漏改
> 从此有对手方。

---

## §1 用户诉求（逐字）与拆解

> 「每一次都可以使用 superpower skill，联动的必要的 skill 深度思考，按照**下一步建议**
> 实现保证每一次都是**真正的实现**，并且持续规划 360 轮 / 720 分钟不断修复和改进，
> 并且最后完整后给出下一次建设性的意见」

> 「……我要的是**整个系统的代码的完全分析**，**每一个文件，每一个函数 / 甚至每一个变量**
> 都要分析，还有就是**属于三者差异的点也要各自体现出来**，还有就是更一层的代码中
> 涉及的**动态链接库也务必解析出来**」

拆成四条可验收的判据：

| # | 诉求 | 本轮落点 |
|---|---|---|
| (a) | **每次**都用 superpower + 联动 skill 深度思考 | 六顶思考帽：蓝帽定题 → **白帽以查源码与实测为准**（抓到 R99 假声明）→ 红/黑/黄/绿帽 → 蓝帽综合 |
| (b) | 按**下一步建议**（R99 复盘 §9）落地 | ★★★ 两项中的第一项：MATLAB 侧补动态链接库；★★★ 第二项（槽 25/26 变量级）列入下一轮 |
| (c) | **真正的实现**（不是声明、不是只改表） | 新引擎 407 行 / 16,445 B + 站点页 + 新门 204 行 / 8,749 B，四层证据全绿 |
| (d) | 持续 360 轮 / 720 分钟 | 路线图追加槽 39（挂 `t4`），环路预检现算 **0** |

---

## §2 蓝帽：本轮做了什么（一页纸）

| 类别 | 内容 | 体量（现算） |
|---|---|---|
| **新引擎** | `renderers/dynlibs.py`（仓内 CRLF） | 407 行 / 16,445 B |
| **站点呈现** | `renderers/csite.py` 加 `dynlibs.html` **四语言总生成** | 92,658 → **100,449 B**（+129 行） |
| **MATLAB 侧** | `matlabc.py`：`render_browse_site` 加性参数 `binaries` / `attribution` 透传 + `_clean_browse_dir` 两向补正 | 1,689,491 → **1,692,342 B** |
| **新闸门** | `tools/check_browse_clean_manifest.py`（第 21 个护栏脚本，判据族 **M0–M3**） | 204 行 / 8,749 B |
| **门禁聚合** | `tools/check_all.py` 树行 + `MIN_GUARDS` 20 → 21 | 25,213 B |
| **帮助契约** | `tools/check_help_contract.py`：`GUARD_CONTRACT` 新条目 + `HELP_*_SNAPSHOT` + 前缀牌 | 158,214 B |
| **文档** | README.md / README_CN.md（散文门数 **+ 门表行**）/ CONTRIBUTING.md | 92,905 / 86,098 / 51,405 B |
| **计划** | `docs/EVOLVE_ROADMAP_360.md` 追加**槽 39** | 60,824 → 63,548 B（+22 行） |

`git diff --stat`：**8 files changed, 223 insertions(+), 33 deletions(-)**（另 2 个新文件未跟踪）。

---

## §3 白帽（本轮起因）：R99 的**假声明**

### §3.1 铁证

R99 的提交信息 `e1c88d5` 声称 `_clean_browse_dir` 的顶层清理清单「**两向都错**」已修。
白帽纪律是**以查源码与实测为准，不轻信文档声明**，于是：

```
git log -L 30445,30482:matlabc.py
```

结果显示该函数**自首次提交 `425f3e9` 起一字未动**；而 `_r99/patch_r99d.py`
**根本不存在**（目录里没有任何名为 `patch_r99d*` 的文件）。

### §3.2 三方对账（三个来源互相独立）

| 来源 | 内容 |
|---|---|
| ① 白名单（`_clean_browse_dir` 里的字面量） | 27 个顶层项 + 若干子目录 |
| ② 代码生成点（真跑 `--browse` 后落盘的产物） | 33 文件 / 6 子目录 |
| ③ 实测站点目录（`_r99/bs_m2`） | 出现**幽灵** `review.html` + **9 个文件漏列** + **4 个子目录漏列** |

⇒ R99 那句声明是**假的**：清单**从未**被改过。

### §3.3 补正

本轮两向修掉（顶层 33 项 + 6 子目录），并**新建第 21 道门**让这一类漏改
（「声明改了、`diff` 里没有」）**从此有对手方** —— 见 §5。

---

## §4 新能力：`renderers/dynlibs.py`（四语言源码级动态库引用）

### §4.1 为什么需要（与 `binaries.html` **互补**，不可互相替代）

| 事实 | 来源 | 需要什么 | 回答的问题 |
|---|---|---|---|
| **容器级** | `binfmt.parse`（ELF / PE / Mach-O） | 库**文件**要递过来（`--binary` / `--binary-attach` / `--lib-resolve`） | 「**谁里面有什么**」 |
| **源码级**（本轮） | `dynlibs.extract_dynlib_refs` | **只要源码** | 「**代码想用谁**」 |

只有前者，会把「引用了不存在的库」当成正常；只有后者，会漏掉「代码里写了、
但没把文件递过来」的那一批 —— 而这恰恰是**静态分析能回答、运行时工具回答不了**的问题。

### §4.2 设计：「共有」与「特有」的落点

这是用户那句「**共有的都需要适配，特有的需要各自适配**」在本轮的具体落点：

| 维度 | 共有（四语言一致） | 特有（各自一套） |
|---|---|---|
| 记录形状 | `file / line / api / lib / kind / lib_is_arg / text` | — |
| `kind` 语义 | `load` / `use` / `unload` / `probe` / `type` | MATLAB 独有 `calllib` ⇒ `use`（唯一把「加载」与「使用」分两步的语义） |
| 站点页 | `dynlibs.html`（四语言**总生成**同一页） | — |
| API 表 | — | C / py / js / matlab 各一（见 §4.3） |
| 实参写法 | 统一走 `_literal_after`（四语言共用一份词法） | MATLAB `''` 转义 + 转置消歧 |

### §4.3 API 表（「特有」的落点）

| 语言 | API | `kind` | 首实参是库名？ |
|---|---|---|---|
| C | `dlopen` / `LoadLibrary(A/W/ExA/ExW)` | `load` | 是 |
| C | `FreeLibrary` / `dlclose` | `unload` | **否**（收句柄） |
| py | `ctypes.CDLL` / `WinDLL` / `OleDLL` / `PyDLL` / `LoadLibrary` / `ctypeslib.load_library` / `ffi.dlopen` | `load` | 是 |
| py | `find_library` | `probe` | 是 |
| js | `process.dlopen` / `ffi.Library` / `koffi.load` | `load` | 是 |
| matlab | `loadlibrary` | `load` | 是 |
| matlab | `calllib` | **`use`** | 是 |
| matlab | `unloadlibrary` | `unload` | 是 |
| matlab | `libisloaded` | `probe` | 是 |
| matlab | `libpointer` / `libstruct` | **`type`** | **否**（收 FFI 类型名） |

### §4.4 口径分离：`lib_is_arg`（R98b ⑰「混口径比错数字更隐蔽」）

`FreeLibrary(m)` / `dlclose(h)` / `libpointer('doublePtr')` 的**首实参本来就不是库名**
（句柄 / FFI 类型），与「运行期才知道库名」是**两件事**。所以 `lib=None` 分**两个桶**：

* `unknown` —— 有调用点、库名运行期才定（`dlopen(buf)`）；
* `no_lib_arg` —— 这个 API **本就不带**库名。

站点页的「逐条明细」**只列** `lib_is_arg=True` 的行，「不带库名」的调用**单列一节** ——
这是实测抓到的自伤：MATLAB 语料里 `libpointer` 起初被印成「(运行期才知道)」。

### §4.5 边界（与帮助声明**不冲突**，但必须说清）

帮助原文写着「不跟踪运行期绑定（`dlopen` / `LoadLibrary` / `dlsym` / `LD_PRELOAD`）」
—— 新能力**不违反**它：

* **字面量**实参 ⇒ 静态可见，**提取**；
* **变量**实参 ⇒ 记下调用点、库名 `None`（「有调用点但库名未知」≠「根本没有这一行」）；
* `dlsym` 拿到函数指针再调用 ⇒ 目标运行期才定，**不提取**。

---

## §5 第 21 道门：`check_browse_clean_manifest.py`（判据族 M0–M3）

### §5.1 为什么这一轮**该**加闸

记忆里 R85 的定论是「**缺口为 0 时**加闸 = churn」（已累计 6 个反例）。本轮的缺口是
**真实存在**的：R99 的假声明证明「**声明改了、`diff` 里没有**」这一类漏改此前
**没有任何门在看** —— 3 条站点的清单、代码生成点、实测目录，三方各自为政。

### §5.2 判据（全部**从代码现抽**，本文件不写死任何页面名）

| 判据 | 内容 | 空集/边界处理 |
|---|---|---|
| **M0** | **先断言输入非空**（R95 ④ / R99 事故） | 清单或生成点为空 ⇒ 红（空集上「每项都对」恒真） |
| **M1** | 清单 **⊇** 生成点（无遗漏） | 少一项 ⇒ 换语料 / 换 `--lang` 后页面**残留** |
| **M2** | 清单 **⊆** 生成点（无幽灵） | 多一项 ⇒ 每次都在删一个从不生成的文件 |
| **M3** | 子目录清单**两向**一致（含 `src_subdir` 的**实参值**） | 两向 |

抽取器全从源码现抽：`func_body()` / 白名单正则 / `_safe_page(outdir,"…")` /
`outdir / "…"` / csite 的 `_emit` / `src_subdir="…"` 实参。

### §5.3 自证与真检

```
--selftest  ⇒ SELFTEST COUNTS {"bad": 2, "good": 12}（8 个合成样本，含 2 个空集坏样本）
真检        ⇒ 清理清单：33 个顶层文件 / 6 个子目录
              代码生成点：33 / 6
              [OK] 两向一致（M1–M3）
```

退出码：**0** 一致 / **1** 差异 / **2** 缺输入。

---

## §6 证据链（四层，全部本轮**现算**）

| 层 | 装置 | 读数 |
|---|---|---|
| **A 机制自测** | `_r100/selftest_dynlibs.py`（33 条判据、四语言语料含 4 类反例） | `good=33 bad=0` ⇒ `SELFTEST COUNTS {"bad": 0, "good": 33}` |
| **B 变异体** | `_r100/run_mutation_test.py`（在 `_r100/_mut/` 副本上，**不动真树**） | 3 个变异 **全红**（7 / 2 / 5 条坏样本）+ 还原后 **GREEN**（0/33）⇒ `ALL RED AS EXPECTED` |
| **C 端到端** | `_r100/run_e2e_r100.py`（四语言 `--browse` + `--binary-attach`） | `[PASS] c 2842 B` / `py 3059 B` / `js 2919 B` / `matlab 3711 B` / `m+battach 4235 B` ⇒ `ALL PASS` |
| **D 独立交叉** | `_r100/probe_manifest_cross.py`（**独立于门抽取器**，防共模） | 清单 33 文件 / 6 目录 vs 实测 `site_m` 31 文件 / 5 目录 ⇒ `ALL PASS`（含幽灵 `review.html` 已不在清单、`dynlibs.html` 双向在册） |
| **E 补丁形状** | `_r100/verify_patch_shape_r100.py`（`git show HEAD:<f>` ⇄ 工作区**逐行**对账） | 被删 **32** 行全部在新增行里有对应；**抓到 1 处注释误伤**（`check_help_contract.py` 的 R74 历史注释被 `C3 ` → `M3 ` 波及） |

B 层三个变异各自对应一条**真实语法**：去掉字符串区间过滤（`printf("use dlopen()")` 误报）/
去掉 MATLAB 转置防护（`B = A'; loadlibrary(...)` 跨语句误吞）/ `take_arg` 恒 `True`
（把 `FreeLibrary` 的句柄当库名）。

---

## §7 级联七处 —— 以及**门表行**的当场抓出

改「判据签名 / 门数」的级联点（本仓定式，R96 记 7 处 / 8 个文件）：

| # | 落点 | 本轮 |
|---|---|---|
| 1 | 门自身（`ROW_SIGNATURE` + 成功行） | ✅ |
| 2 | `check_all.py` ASCII 树行 | ✅ |
| 3 | `check_all.py` `MIN_GUARDS` 20 → 21 | ✅ |
| 4 | `check_help_contract.py` `GUARD_CONTRACT` | ✅ |
| 5 | `tests/test_matlabc.py` 门数棘轮 | ⚠ **上一轮也没动**（`assert ca.MIN_GUARDS == 20` 是**故意写死**的棘轮，注释原文「谁改了门数，谁就得在这里露面」）；**聚合门禁结构性抓不到它**（`check_all` 不跑 `tests/`）⇒ 靠 grep 全仓写死数字找到，已改 21 + 补 R100 注释 |
| 6 | README 门表行 × 2 | ⚠ **上一轮漏改** |
| 7 | README 散文门数 × 2 + `CONTRIBUTING.md` | ✅ |

**本轮最有价值的一条**：上一轮我把两侧 README 的「**散文门数**」改了，却漏了「**门表行**」。
这不是我发现的，是**聚合门禁当场抓的**：

```
[FAIL] check_readme_parity.py - P4 README_CN.md 质量门表漏了 1 道真实护栏：['check_browse_clean_manifest.py']
[FAIL] check_readme_parity.py （--selftest 缺失或不通过）
```

`check_readme_parity.py::P4`（R61）把对手方从「另一侧文件」换成了**事实**
（`tools/check_*.py` 的真实清单），所以「两侧一起漏」也照样红。第二行 FAIL 也**不是**独立缺陷：
该门 `--selftest` 的末段「真实仓库整体核对」复用了**同一条 P4 判据** ⇒ 补上行后两条一起转绿。

**修法**：`_r100/patch_readme_rows_r100.py` 从门源码**现读** `ROW_SIGNATURE`（不手抄，
逐字节一致由构造保证，不靠人眼比 en-dash `–` U+2013），两侧门表各 +1 行 ⇒ 20 → 21。
复跑：

```
check_readme_parity: OK（… 两侧质量门表各 21 行 == tools/check_*.py 的真实清单；
                      表行签名 P1/P2/P4/P5，21 道门的表行内容与那道门逐字对上）
SELFTEST COUNTS {"bad": 16, "good": 5} / SELFTEST PASSED
```

---

## §8 事故与量具错清单（**先问量具错还是对象错**）

| # | 现象 | 裁决 | 修法 |
|---|---|---|---|
| 1 | 字符串 `printf("use dlopen()")` 被算成调用 | **对象错**（真缺陷） | 记录字符串区间 + `_in_spans()` 二分过滤 |
| 2 | `ctypes.CDLL` 漏报；`libpointer('doublePtr')` 的类型名被当库名 | **对象错**（两处语义错） | 去掉 lookbehind；加 `take_arg` + `lib_is_arg` 口径分离 |
| 3 | 自测期望值 `libmwfoo` 写 3（实为 4） | **量具错**（第 8 次） | 改 4，并加「聚合条数守恒」判据（三口径相加 == 总数） |
| 4 | 变异体两处**没红**：锚点未做 LF 归一（0 命中）；MATLAB 转置防护失效 | **量具错** | `src.replace("\r\n","\n")`；语料改成跨语句（`B = A'; loadlibrary(...)`） |
| 5 | `patch_csite_r100.py` 写出 `SyntaxError`（`u"\n"` 被解释成真换行） | **量具错**（`--dry` 看不出来） | 改 `u"\\n"`；回滚；**给补丁脚本加输出侧 `ast.parse` 自检** |
| 6 | e2e 判据字符串写错（`(不带库名)` vs 实际「不带库名的调用」） | **量具错**（第 9 次） | 改判据 |
| 7 | `(运行期才知道)` 把 `libpointer` 混进去 | **对象错**（混口径） | 明细表只列 `lib_is_arg=True`，「不带库名」单列节 |
| 8 | README **门表行**漏改 | **对象错**（我的疏漏） | 聚合门禁抓出 ⇒ 补两行（§7） |
| 9 | `check_help_contract.py` 里一条 **R74 历史注释**（`C1/C2/C3 … 由 C0–C3 改名`）被改名补丁的 `(u"C3 ", u"M3 ")` 波及，变成语义混乱的 `C1/C2/M3 … 由 C0–M3 改名` | **补丁误伤**（子串包含 ⇒ 误伤注释；**没有任何门抓到**） | 逐行对账抓出 ⇒ 改回 `C1/C2/C3` / `C0–C3`（**等长替换** ⇒ 文件字节数 **158,214 不变**，`check_help_contract` 仍 OK） |
| 10 | `tests/test_matlabc.py` 的**门数棘轮** `assert ca.MIN_GUARDS == 20` 漏改（改了 `MIN_GUARDS` 就会红） | **对象错**（我的疏漏；**聚合门禁抓不到**） | grep 全仓写死门数 ⇒ 改 21 + 补注释；`test_r61_gate_registry_mentions_the_new_guard` **1 passed in 2.96s** |

**计数**：本轮量具错 **4** 次、对象错 **5** 次（其中 **2 处漏改**：README 门表行、tests 门数棘轮）、**补丁误伤 1** 次。全部由**装置**或**grep 全仓对账**抓出，无一是靠人眼看出来的。

---

## §9 未结与下一轮建议（按优先级）

| 优先 | 事项 | 落点 |
|---|---|---|
| ★★★ | **变量级**：用户明确要的「每一个变量都要分析」——C / py 的**数据源不存在**（不是呈现层能补的） | 槽 25 `py_ast_frontend`（Py `ast` 双层 + 降级进 `limitations`；落地时 `LANG_SUPPORT["py"]` 由 `no` 改 `yes` **并删理由**）→ 槽 26 `c_entity_layer` |
| ★★ | MATLAB 的 **4 个 `no`** 如实归因（「通道不同」≠「没实现」） | `docs/PARITY_MATLAB_C_PY.md` |
| ★★ | `--browse` **帮助与实现对齐**（帮助说 `--binary` 也出 binaries 页，实现只认 `--binary-attach`） | `matlabc.py` 帮助正文 |
| ★ | **15 页语言特有页**的「共有化」评估 | `renderers/csite.py` + `render_browse_site` |
| ★ | 生成器入库（含 R91 `build_py_callgraph_doc.py`） | 仓内 |
| ★ | 决定 `_r100/corpus_dynlib/libdemo.dll`（44,824 B 二进制）是否入库 | — |

**债务（承接 R99）**：`set.X` / `get.X` 同名口径、matlab **边序通道**、`resolution.external=0` 哨兵、
契约跨语言同形判据、R92–R99 复盘入库、MATLAB `binaries.html`（本轮已打通 `--binary-attach`）。

---

## §10 数字表（全部**现算**）

| 项 | 值 |
|---|---|
| `renderers/dynlibs.py` | 407 行 / 16,445 B（新） |
| `renderers/csite.py` | 100,449 B（+129 行） |
| `matlabc.py` | 1,692,342 B |
| `tools/check_browse_clean_manifest.py` | 204 行 / 8,749 B（新） |
| `tools/check_all.py` | 25,213 B；`MIN_GUARDS` = **21** |
| `tools/check_help_contract.py` | 158,214 B |
| README.md / README_CN.md / CONTRIBUTING.md | 92,905 / 86,098 / 51,405 B |
| `docs/EVOLVE_ROADMAP_360.md` | 63,548 B（槽 **40** 个，round 0…39） |
| `git diff --stat` | 8 files, 223 insertions(+), 33 deletions(-) |
| 门数 | **20 → 21**（第 22 个 `check_*.py` = 21 道门 + `check_all.py`） |
| 环路预检 `ledger_plan_problems()` | **0**（plan slots = 40；ledger rows = 23，最大 round 36） |
| 内核读数 | 见 §11（改了 `matlabc.py` ⇒ W2 必红 ⇒ 按唯一合法路径重跑） |

---

## §11 内核快照

本轮**改了** `matlabc.py`（`render_browse_site` 加性参数 + `_clean_browse_dir` 两向补正），
所以第 19 道门的 **W2**（出处钉住）**必红**。唯一合法路径是**重跑**，不是只改表：

```
_r82/probe_kernel_r84.py --arms c asm   →   _r82/gen_kernel_run_doc.py   →   --check 一致
```

读数由 `tools/check_kernel_snapshot.py` 的 **W1–W7** 复核；产物表见 `docs/KERNEL_RUN.md`
（由**生成器现算**刷新，**非手改**）。

---

*本复盘由 R100 收尾时写成；所有数字现算于写盘时刻，装置脚本见 `_r100/`（仓外）。*
