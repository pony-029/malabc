# SUPERPOWER_REVIEW_R43 —— 9 道护栏 · 两条验证轴 · 按集合比基线 · 散文数字 · 历史引用 · 「门自己的自伤」

> 覆盖范围：**R34 → R43**（C''1–C''9 的执行批 + 两道新门 + 一次自我抓错）
> 证据口径：所有数字都来自**真实文件/真实进程**（命令与输出见 §7 / §8）。凡是没有实测
> 支撑的地方，本文一律写「未测」，不写估计。

---

## §0 结论先行

这一段把「宣称」与「装置」逐条对上。**括号里是它的可执行对手方**，没有对手方的都标了 ⚠。

| 这一批新增的装置 | 它拦住的真问题 | 对手方（能红的东西） |
| --- | --- | --- |
| `frontends` 无关（未做）⚠ | — | — |
| `#if 0` 预处理感知（R34） | 死代码里的检出被当成真检出（**那个文件 100% 的检出都来自死代码**） | 4 个探针用例（dead/nested 全静；live_control/else 照报） |
| `binfmt/buildsys.py` 接入默认路径（R35） | 构建脚本里的链接意图此前只被提取、没被使用 | `--binary-attach` 的三态归因多一路来源 |
| **K9 修复**（R36） | thin Mach-O 头部**从文件偏移 4096 读** —— 不报错，只是安静地给出错误答案 | >4096 B 的合成夹具 + 落在 4096 的诱饵头 |
| 两条**独立**验证轴（R36） | 「未验证」被当成一句话，掩盖了「连夹具都没过」与「有夹具、无真实语料」的区别 | C9 断言 `verified is False and fixture_verified is True` + 报告措辞必须同时含两个词 |
| `check_baseline.py`（R37） | 「124 failed 改成 123 failed」分不清「修好一个」还是「修好两个又弄坏一个」 | 按 **nodeid 集合**比；同数异集必须红 |
| 帮助体积**相对棘轮**（R38） | 绝对界对辅助入口形同虚设（919 B vs 16 KiB 上界），对旗舰入口又太紧 | `HELP_BYTES_SNAPSHOT` 漂移 ±30% 且 512 B 宽容 |
| `ci-examples/` 退出码契约（R39） | 会被**复制进别人的 CI** 的脚本，退出码语义没人守 | `CI_PY_EXIT_CONTRACT` / `CI_SH_EXIT_CONTRACT` / `CI_RELIES_ON_NONZERO` 三表两向核对 |
| 未实现算子必须进帮助正文（R40） | 「源码里有理由、用户看不到」= 用沉默冒充能力 | `check_operator_impl.py` 第三判据 + 点名替代工具 |
| 散文数字自动核实（R41） | `--help` 写「7 道护栏」而实际 9 道，四份文档各写错一处 | 4 份文档的 `N 道…护栏` / `N gates` 实测比对 |
| **历史引用显式豁免**（R42） | R41 的门**上线即抓住我自己**：解释这条规则的散文里引用了旧值 | `<!-- guard-count:historical … -->` + N3/N4 两条反向约束 |
| 基线门**自己跑通了**（R43） | 它此前在本机**完全不可用**；且它的清理失败会被 `ignore_errors=True` **吞掉** | `_unique_dir` + `_prepare_dir` 三态 + `KNOWN_BASELINE_NOISE` 双向核对 |

一句话：**这一批的主题不是「加了几个功能」，而是「把一批宣称接到了能红的对手方上」**；
而两次最有价值的发现都不是靠读代码，是**靠把门打开跑一遍**（K9、R43 三缺口）。

---

## §1 白帽：事实清单（全部实测）

### 1.1 护栏从 8 道变成 9 道（R36 起）

`tools/` 下被 `check_all.py` 聚合的 `check_*.py`（不含 runner 自己）实测 **9 道**：

| # | 脚本 | 拦什么 |
| --- | --- | --- |
| 1 | `check_baseline.py` | 改动有没有让测试变差（**比集合**不比个数，`--full` 才真跑） |
| 2 | `check_binfmt_fixtures.py` | PE/ELF/Mach-O 解析 + GPU 段识别 + 契约 C1…**C9** |
| 3 | `check_doc_flags.py` | 文档/帮助里写的 CLI 开关必须真的存在（含 6 个入口的 module docstring） |
| 4 | `check_help_contract.py` | 退出码在代码↔帮助双向一致；示例能真跑；体积棘轮；**散文数字**（含 R42 豁免标记） |
| 5 | `check_operator_impl.py` | 算子元表里不得有「只声明不产出」的幻影；未实现必须写进帮助正文 |
| 6 | `check_patch_ops.py` | 补丁编辑算子唯一事实源（禁止覆盖式赋值） |
| 7 | `check_py36_clean.py` | 本仓 46 个 `.py` 全部通过本仓自己的 3.6.5 门 |
| 8 | `check_readme_parity.py` | 中英 README 14 个小节逐节结构对等 |
| 9 | `check_subprocess_hygiene.py` | 子进程必须切 stdin 且不会永久挂住 |

两条**棘轮**（少一个都红）：
* `MIN_GUARDS = 9`，且 `check_all` 的自证里有一条断言 **「`MIN_GUARDS` == `tools/` 里真实护栏数」**
  —— 删一道、加一道不同步，都会红。
* `check_help_contract.py` 的 `GUARD_CONTRACT` 覆盖 **10** 道（含 `check_all.py` 自己），
  它审计「护栏脚本自己声明的退出码」与源码是否有依据。

### 1.2 帮助体积实测（`--help` 真实字节数）

| 入口 | 现测字节 | 已批准快照（R38） | 漂移 | 绝对界 |
| --- | --- | --- | --- | --- |
| `matlabc.py` | **49615** | 48593 | **+1022（+2.1%）** | 400 B ～ 64 KiB |
| `matlabc_flow.py` | 2075 | 2075 | 0 | 400 B ～ 16 KiB |
| `matlabc_ask.py` | 919 | 919 | 0 | 400 B ～ 16 KiB |
| `matlabc_mcp.py` | **0** | 0 | 0 | `(0,0)` = 显式不设界（stdio server） |
| `gui.py` | 2651 | 2651 | 0 | 400 B ～ 16 KiB |

`matlabc.py` 的 +2.1% 是**合法增长**（R40 往「诚实的边界」里加了一条 `py_undefined_name`
的说明），落在 ±30% 内所以放行 —— 这正好证明相对臂的设计意图成立：**绝对界对旗舰入口
太紧（加三个功能就可能顶到 64 KiB），相对臂才是真正起作用的那一条。**

### 1.3 `ci-examples/` 的退出码此前没有任何契约

`ci-examples/` 下的脚本是给用户**复制进他们自己的 CI** 用的，退出码因此是**公开接口**。
R39 之前没有人守。现在三张登记表：

* `CI_PY_EXIT_CONTRACT`（`merge_sarif.py`：0 / 1 / 2 各有依据）
* `CI_SH_EXIT_CONTRACT`（`pre-commit`：shell 侧 `\bexit\s+(\d+)\b`）
* `CI_RELIES_ON_NONZERO`（两份流水线模板依赖「非零退出」⇒ 必须挂到一个**真实存在**的非零码上）

### 1.4 散文数字：4 处陈旧（R41 上线即抓）

| 文件 | 原文 | 真值 |
| --- | --- | --- |
| `matlabc.py` | 「7 道登记制护栏」 | 9 |
| `README.md` | 「8 gates」 | 9 |
| `README_CN.md` | 「8 道门」 | 9 |
| `CONTRIBUTING.md` | 「登记制护栏（8 道，…）」 | 9 |

第 4 处是 **R41 首版判据完全漏掉**的：数字在「护栏」**之后**（括注形态），四条正则都够不着；
是把量词放宽再扫一遍才发现的。教训：**判据要按真实写法枚举，不能只写「最常见的那种」。**

### 1.5 本轮新增的两条本机环境事实

1. **`cmd | tail` 读到的是 `tail` 的 rc。** 我因此把 `check_help_contract.py --selftest` 的
   `rc=1` 看成了 `rc=0`，直到 `check_all` 报红才发现。**验证必须看被测进程自己的 rc。**
2. **`safe-delete` 守卫在对 >50 项的目录做批量删除时直接终止进程**（不是抛异常，
   `try/except` **兜不住**）。一棵 `git archive` 导出树有 200+ 项 ⇒ 任何「先删再建固定目录」
   的实现，在这台机器上必然死。

---

## §2 黑帽：真缺陷分级

### 2.1 K9 —— thin Mach-O 头部从错偏移读（严重度：**高**，静默错答案）

`binfmt/macho.py` 的 `parse()` 先 `f.read(4096)`，然后 `_parse_thin(f, rep, endian)` 又自己
`f.read(32)` —— 于是头部是**从文件偏移 4096** 读出来的。

它**不报错**，只是安静地给出错误答案。实测（>4096 B 的结构合法夹具）：

```
arch = unknown(0x0)      bits = 32      flavour = ft=0      sections = 0
```

为什么一直没被发现：旧的 28 字节夹具**只走到 `struct.error` 分支**，那个分支会留一条 note，
看起来像「夹具不完整」，而不是「读错了位置」。

**修复**：`head` 由调用方从**文件开头**读入并传下去，`_parse_thin` 绝不再自己 `f.read()`。
**回归锚点**：夹具刻意 pad 到 >4096 B，并在 4096 处**埋一个诱饵头**（大端 `ppc` magic +
`ncmds=0x01000000`），这样一旦退化，报错是「解析出了 ppc 头」而不是含糊的「0 sections」。

### 2.2 K10 —— 公平基线门的清理失败被吞掉（严重度：**中高**：门在本机不可用）

`export_head` 写的是 `shutil.rmtree(dest, ignore_errors=True)`。实测 `--full` 的画面是：

```
[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED] {"count":211,"threshold":50,…}
[1/4] git archive HEAD -> E:\matlabc\_baseline_cb\head
（进程结束，rc=1）
```

三层缺陷叠在一起：

1. **`ignore_errors=True` 把失败吞掉**，紧接着 `os.makedirs` 撞 `FileExistsError`
   —— 报错离真因很远。
2. 修法 v1「删不掉就改名归档 + 兜住 `OSError`」**也兜不住**：守卫是**直接终止进程**。
3. 最终解：**让这道门根本不需要删除动作** —— `_unique_dir()` 每次开
   `<work>/head-<时间戳>-<pid>`，从不删旧目录；`_prepare_dir()` 只服务小目录（`tests/`），
   契约是「删不掉 → 改名归档 → 还不行就**抛**」，**绝不带着脏目录继续**。

为什么第 3 条比前两条重要：这道门存在的**唯一理由**就是「两侧比对不能静默失真」，
而它的清理恰好是静默失真的入口。一个自己会静默失真的门，比没有门更糟。

### 2.3 K11 —— 噪声混进 `fixed` 读数（严重度：**中**，会掩盖真实修复）

修好 K10 后真跑通，得到：

```
BASELINE COUNTS {"regressions": 0, "fixed": 1, "common": 124}
  不再失败 1 个（前 125 -> 后 124）：tests/test_matlabc.py::test_r30_static_guards_all_clean
```

`regressions: 0` 是真的。但那条 `fixed` 揭示了一个**方法论漏洞**：`git archive HEAD` 的
导出树**不是 git 仓库**，而 `test_r30_static_guards_all_clean` 会在树内跑 `tools/check_all.py`
（其中 `check_baseline.py` 默认模式的前置条件 P1 需要 `.git`）⇒ before 侧**必然**多红一次。

它是**环境差异**，不是回归；可它和「真的修好了一个」**长得一模一样**，会掩盖同一 nodeid 上
真实的修复。按本仓一贯的**登记制**处理，并**双向核对**：

* 已登记 + 出现 → 放行（打印原因）
* 未登记 + 出现 → **红（B2）**：新噪声必须解释
* 已登记 + 没出现 → **红（B3）**：陈旧登记（例如有人把 P1 改成「只在 `--full` 下设」，
  这条解释就立刻作废 —— B3 会逼着维护者删掉它）

### 2.4 K12 —— 未实现算子只有源码里有理由（严重度：**中**）

`py_undefined_name` 登记在 `_UNIMPLEMENTED_KINDS` 里，理由（需要真实作用域链，正则近似会
成片假阳性）写在源码注释里 —— **用户看不到**。R40 把它写进 `--help` 正文，并**点名替代工具**
（`python -m pyflakes your.py` / `ruff check --select F821`）。

### 2.5 我自己在这一批里的**五次**自伤（全部被装置抓出，逐条记下）

| # | 自伤 | 抓到它的东西 |
| --- | --- | --- |
| 1 | `check_baseline` 自证里写 `r["common"] == 2` —— `common` 是**列表**，表达式恒真，断言永远不红 | 它自己的自证 |
| 2 | R5 缩水样本参数写错（drift −500 落在 512 B 宽容内），期望值与判据相反 | 它自己的自证 |
| 3 | R42 两个「陈旧标记」样本用了 4 字符理由，先触发 N4、**N3 根本没机会跑** | 它自己的自证 |
| 4 | R43 三个样本把 `want_problem` 写反（这是这个套路第 4 次） | 它自己的自证 |
| 5 | 用 `cmd \| tail` 读退出码，把 `--selftest` 的 `rc=1` 看成 `rc=0` | `check_all` 报红 |

**结论：两向自证不是形式主义 —— 它抓到的「我的 bug」比它抓到的「代码的 bug」还多。**
这正是「测量工具自身的 bug 会伪造出被测对象的 bug」那条纪律的经验依据。

---

## §3 黄帽 / 绿帽：C''1–C''9 落地表

| 建议 | 状态 | 落点 | 可证伪的对手方 |
| --- | --- | --- | --- |
| C''1 前端外挂化 + 统一 IR | ❌ **未做** | — | 见 §9 C'''1 |
| C''2 预处理器感知 | ✅ R34 | `_scrub_c_if0` / `_c_lines_effective` | 4 用例探针（死代码全静、活代码照报） |
| C''3 `binfmt/buildsys.py` 接入 | ✅ R35 | `--binary-attach` 的链接意图来源 | 三态归因多一路来源 |
| C''4 动态库边界 | ❌ **未做** | — | 见 §9 C'''2 |
| C''5 `py_undefined_name` | ✅ R40 | 帮助正文 + 第三判据 + 替代工具 | 删掉帮助那段必须红（已实测） |
| C''6 Mach-O 从「未验证」推进一格 | ✅ R36 | C9 合成夹具 + 两条验证轴 + 修 K9 | 夹具 + 诱饵头 + 措辞断言 |
| C''7 公平基线做成一道门 | ✅ R37（**R43 才真正跑通**） | `check_baseline.py` | 两侧集合比对 + 登记制噪声 |
| C''8 体积棘轮改相对棘轮 | ✅ R38 | `HELP_BYTES_SNAPSHOT` + `_r5_verdict` | 8 条纯函数断言 + 真实仓库两向 |
| C''9 退出码契约扩展到 `ci-examples/` | ✅ R39 | 三张登记表 + `audit_ci_examples` | shell `exit N` 未登记必须红 |
| C''10 打断 `renderers` ↔ `matlabc` 循环依赖 | ❌ **未做** | — | 见 §9 C'''3 |

（R40 顺带补上 C''5；R41/R42/R43 是**计划外**的三轮，由 R41 上线后立刻暴露的问题驱动。）

---

## §4 蓝帽：这一批建立的不变量

1. **护栏数有下限，且下限必须等于事实。** `MIN_GUARDS = 9` + 「`MIN_GUARDS` == 真实数」断言。
2. **两条验证轴不得合并。** `verified`（真实语料）/ `fixture_verified`（合成夹具）是两个布尔值；
   报告措辞必须区分「既无真实语料也无合成夹具」与「有合成夹具、无真实语料」。
3. **比集合，不比个数。** `after − before = regressions`；个数相等而集合不同**同样是回归**。
4. **`fixed` 也要分类。** 「修好了」与「环境不同」必须能分开，否则噪声会掩盖修复。
5. **豁免必须显式、必须带理由、必须能被反向抓。** 豁免标记：理由 < 8 字符 → 红且视为不存在；
   陈旧标记（本来就不违规）→ 红；`min_claims` 只数**未被豁免**的命中。
6. **清理失败不许吞。** 删不掉 → 改名归档 → 还不行就抛；**绝不带着脏目录继续**。
7. **测量工具的默认值会改写被测对象。** 唯一目录 > 固定目录；`stdin=DEVNULL` > 继承 stdin。
8. **验证要看被测进程自己的 rc**，不能看管道末端的 rc。

---

## §5 轮次账本（R34 → R43）

| 轮 | 主题 | commit | VERSION |
| --- | --- | --- | --- |
| R34 | C 前端字面量 `#if 0` 感知 | `2e905cd` | — |
| R35 | `binfmt/buildsys.py` 接进 `--binary-attach` | `298a17e` | — |
| R36 | 修 K9 + C9 合成夹具 + 两条验证轴 | `1af5998` | 1.16.69 |
| R37 | 公平基线做成一道门 `check_baseline.py` | `0549f88` | 1.16.69 |
| R38 | 帮助体积棘轮两臂取严 | `ede9ed6` | 1.16.69 |
| R39 | `ci-examples/` 退出码契约 | `03e5da9` | 1.16.69 |
| R40 | 未实现算子必须写进帮助正文 | `6d34d6a` | 1.16.69 |
| R41 | 散文数字自动化核实 | `11e4a62` | 1.16.69 |
| R42 | 历史引用豁免标记（门抓住我自己） | `ee0ecd9` | 1.16.70 |
| R43 | 基线门跑通 + 三缺口 + 登记制噪声 | 见 §7 | 1.16.71 |

---

## §6 质量门结束态

```
tools/check_all.py → rc=0
check_all: OK（9 个护栏，全部通过且各自自证；门数下限 9）
check_py36_clean: OK（本仓 46 个 .py 文件全部通过 3.6.5 语法兼容门）
check_readme_parity: OK（README.md 与 README_CN.md 的 14 个小节逐节对等）
check_help_contract --selftest: SELFTEST COUNTS {"bad": 29, "good": 32}
check_baseline --selftest:      SELFTEST COUNTS {"bad": 7,  "good": 10}
check_operator_impl --selftest: SELFTEST COUNTS {"bad": 0,  "good": 8}
check_binfmt_fixtures --selftest: SELFTEST COUNTS {"bad": 5,  "good": 5}
全仓文本文件 bare_LF = 0（纯 CRLF）
```

---

## §7 公平基线对照（R43 实测，真的跑了两侧全量）

```
[1/4] git archive HEAD -> E:\matlabc\_baseline_cb\head-*（唯一目录，不删旧目录）
      -> E:\matlabc\_baseline_cb\head-20261009-210107-26404
[2/4] 把当前 tests\test_matlabc.py 复制进导出树（同测试集）
      测试函数数：HEAD 树 437 / 当前树 437
[3/4] 跑 HEAD 树（-k 'not r33'）…
[4/4] 跑当前树（-k 'not r33'）…
BASELINE COUNTS {"regressions": 0, "fixed": 1, "common": 124}
  [已登记的环境噪声] tests/test_matlabc.py::test_r30_static_guards_all_clean
      导出树不是 git 仓库 ⇒ 树内 check_baseline.py 的前置条件 P1（需要 .git）
      必然红一次；只出现在 before 侧，属环境差异而非回归
check_baseline: OK（--full：按 nodeid 集合比对两侧，无回归）
```

**怎么读这张表**：
* `regressions = 0` → 这一批（R34–R43）**没有引入任何回归**。
* `fixed = 1` 且**已被登记解释** → 不是"修好了一个"，是导出树缺 `.git` 造成的环境差异。
* 「测试函数数 437 / 437」→ **同测试集**这个前提成立，所以两侧差异只可能来自源码改动。
* 两侧各有 124 个共同失败 → 那是**历史状态**，本批未处理（见 §10）。

---

## §8 探针与验证脚本清单（仓库外，不进 git）

`E:\matlabc\_r33\`：`normalize_eol.py` · `verify_push.py`（对象级推送验证，R43 起改为
**改名归档**而非删除 clone）
`E:\matlabc\_r36\`：`probe_macho.py` · `probe_twoway_k9.py`
`E:\matlabc\_r37\`：`probe_baseline_red.py`
`E:\matlabc\_r38\`：`probe_help_ratio.py` · `probe_help_drift_red.py`
`E:\matlabc\_r40\`：`probe_undoc_red.py`
`E:\matlabc\_r42\`：`apply_markers.py` · `append_r42_test.py` · `patch_verify_push.py` · `bump_version.py`
`E:\matlabc\_r43\`：`patch_baseline.py` · `patch_baseline2.py` · `patch_baseline3.py` ·
`append_r43_test.py` · `bump_version.py`

**推送验证（R42 实测）**：从远端 `--depth 1` clone 回来，比 `HEAD` + `HEAD^{tree}` +
`ls-tree -r` 全量清单（**116** 条）+ **逐文件 blob sha256**，并在 clone 内跑 `check_all` 与
`pytest -k`。结果：**HARD 失败数 = 0**。

---

## §9 C'''1–C'''10：下一次建设性意见

排序原则与上一批相同：**优先「已有装置但没接上线」和「已有承诺但没装置」**，
并且每一条都必须先能说清「**什么会红**」。

**C'''1（最高优先）前端外挂化 + 统一 IR，并把归因接到 IR 的 `unresolved` 节点。**
这是唯一还没动的 C 系地基项，也是本仓最大的结构性缺口：`collect_c_files` / `CFrontend` /
MATLAB / Py / JS 四条前端各自为政，`--binary-attach` 的三态归因**走的是另一条独立路径**。
落点：`frontends/<lang>.py` 统一产出 IR（`{path, funcs[], calls[], unresolved[]}`）。
**对手方**：新门 `check_ir_attribution.py`，断言
`IR.unresolved 的符号集合 == unresolved_attribution.rows 的符号集合`（**比集合，不比个数** ——
与 R37 同一条纪律）。现在两者只是"碰巧一致"，没有任何东西守着。

**C'''2 动态库的**运行期绑定**必须显式化（C''4 未做，两条都行但不能都不做）。**
全仓至今无 `dlopen` / `LoadLibrary` / `dlsym` / `LD_PRELOAD` 处理。
建议**先做可证伪的那一半**：在 `--help` 的「诚实的边界」+ 报告里明确写
「不跟踪运行期绑定」，并点名替代工具（`ltrace` / `strace -e openat` / `LD_DEBUG=bindings`）。
理由：写清楚边界是**可以证的**（文档里必须出现这些字），而启发式近似会引入新的假阳性。

**C'''3 打断 `renderers` ↔ `matlabc` 的循环依赖（C''10 未做）。**
现在靠「模块尾部 import」规避，属于**能用但不可维护**。落点：显式注册表 + 新门
`check_import_graph.py`（用 `ast` 建模块级 import 图，断言无环），并把**允许的例外**
登记在 `--help` / `CONTRIBUTING` 里。对手方：人为加一条回边必须红。

**C'''4 两条验证轴推广到 PE / ELF。**
目前只有 Mach-O 带 `fixture_verified`；PE/ELF 用的是本机真实二进制，应当显式写
`verified=True, fixture_verified=True`，让三档（真实 / 仅夹具 / 都没有）在**所有容器**上可读。
对手方：断言「三档的值两两不等价」都有真实样本覆盖，且报告措辞三者互不相同。

**C'''5 让豁免标记的**理由**也受审计。**
现在理由字段是自由文本，没人查它是否还成立。落点：把豁免条数纳入 `check_help_contract`
的成功行（已做），再加一条 —— 理由里若出现 `R数字`/日期，则该轮次/文件必须真的存在。
对手方：写一个不存在的轮次号必须红。

**C'''6 让「本轮无回归」成为**产物**。**
现在 `--full` 只在终端打印 `BASELINE COUNTS`。落点：落一份 `baseline_report.json`
（两侧 nodeid 集合的对称差 + 解释 + 时间戳），并把「已关闭家族」逐步纳入默认过滤
（现在默认 `not r33`）。对手方：报告缺失或 `regressions` 非空 → 红。

**C'''7 `check_baseline` 的工作目录改用 `tempfile.mkdtemp` 或补 `--gc`。**
现在用「唯一目录」，结论干净，但 `E:\matlabc\_baseline_cb\` 会攒下历次导出树
（实测已有 2 棵 230+ 项的树）。对手方：`--gc` 必须能在**守卫拦删的情况下**至少报告
「哪些目录可以删、共多少项」，而不是静默失败。

**C'''8 C 前端从「行锚定正则」升级到「括号配平 + 跨行签名」。**
`_RE_C_FUNC` 要求 `) {` 与函数名同行，跨行签名的函数**会被漏掉一整条**。
**先量影响**：拿本机 Linux 内核语料扫一遍，统计漏掉的函数占比 —— 如果 < 1%，
就只修这一条（跨行签名），不做完整 AST。

**C'''9 `binfmt` 的 GPU 判据加「节名 vs 节内容」一致性。**
现在靠节名 / `.text._Z` 表。加一条：**声称有 GPU 但节大小为 0** → 降级为 `missing` 并存 note。
对手方：造一个「名字像但内容空」的夹具，必须不报 GPU。

**C'''10 给 `check_all.py` 加**墙钟预算**。**
现在 9 道门各自 < 2s，但没有总预算断言。加一条「总耗时 > N 秒 → 警告」。
理由与 R37 的「把分钟级东西塞进默认路径 ⇒ 所有人开始绕开它 ⇒ 实际覆盖率 0」同源：
**守护慢到没人愿意跑，就等于没有守护。**

---

## §10 明确拒绝做的事（避免下一轮走回头路）

1. **不为绕开数字审计而把正则改松。** 那是"碰巧不命中"：判据会连带失去对真实违规的
   检测力，而且**没人会注意到**。历史引用必须用显式豁免标记。
2. **不把豁免标记做成"任何行都能加"。** 理由 < 8 字符 → 红；陈旧标记 → 红；
   `min_claims` 只数未被豁免的命中。
3. **不把 `--full` 塞进 `check_all` 的默认路径。** 它两侧各一次全量（本机实测 ≈ 11 分钟）。
   进默认路径的结果是所有人开始绕开 `check_all`，那时实际覆盖率是 **0**。
4. **不用「比个数」判断回归。** 个数相等而集合不同同样是回归。
5. **不为了消灭 124 个历史失败而放宽断言。** 它们是**历史状态**；处理它们要单独一轮，
   且必须逐条判定「断言错」还是「代码错」，不能批量 skip。
6. **不做「注释式」的前端外挂化。** C'''1 必须真的产出统一 IR 并被归因路径消费，
   否则就是给四条各自为政的前端加了个目录名。
7. **不引入新依赖。** 本仓坚持「离线、零依赖、3.6.5 兼容」；C'''8 的自研与
   §9 全部建议都不得打破这条。
