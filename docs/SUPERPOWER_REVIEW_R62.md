# R62 —— 质量门表的**内容** ⇄ 那道门（P5 / R61 §8 C12-1）

> R61 的 **P4** 把「质量门表」的对手方从**另一侧文件**换成了**事实**（`tools/check_*.py`
> 的真实清单）。它补上了一个真缺陷（R56 把一行整行覆盖掉，两侧同时少一行 ⇒ 对等门
> 看不见），但它只证「14 行都在」，**不证那一行说的是不是那道门**。
> 把一行**整段**换到另一行上 —— 行的**集合**没变，P4 一声不响。
> 一句话：**P4 管「在不在」，不管「对不对」。**
>
> 本轮（R62）给这个空档接上 **P5**：每道护栏在自己源码里声明一个 `ROW_SIGNATURE`
> （本门自己的判据族，或只有它在用的机制名），并把它打进**自己的成功行**；
> 两侧 README 的对应表行必须**逐字**含它。三处（门源码 / 门成功行 / 两侧 README）
> 从此互为对手方。**零产品行为变更**（`--help` 字节不变，`VERSION` 不动）。

## §1 白帽：事实（全部来自仓库外独立装置，不是门自己说的）

装置：`E:\matlabc\_r62\` 三支，**不 `import` 任何 `tools/check_*`、也不 `import matlabc`**，
只读文件 + 跑公开 CLI 子进程：

| 探针 | 量什么 |
| --- | --- |
| `probe_content_parity.py` | ① 每道门成功行的**末行**；② 两侧 README 质量门表行；③ 「表行是否字字含成功行的稳定标识」 |
| `probe_shared_tokens.py` | 成功行 ⇄ 表行今天**已经**共享哪些 token（词元级交集） |
| `probe_signature_impact.py` | 拟采用签名的四轴现状：**是否已声明 / 锚点是否在源码 / 两侧表行是否已含 / 成功行是否已含** |

### 1.1 修前读数（这才是「为什么需要这一轮」）

| 读数 | 修前 |
| --- | --- |
| C12-1 的字面形式（「从成功行里抽一个稳定标识」）可行吗？ | **不可行**：14 道门里 **9 道**成功行没有任何**编号族**；**6 道**与自己的表行 token 交集为**空**（`check_doc_flags` / `check_help_contract` / `check_ir_attribution` / `check_operator_impl` / `check_patch_ops` / `check_py36_clean`） |
| 已声明 `ROW_SIGNATURE` 的门 | **0 / 14** |
| 签名的锚点在其源码里出现 | 13 / 14（缺的是 `check_readme_parity.py`：`P5` 还不存在） |
| 两侧 README 的表现已含签名 | **3 / 14**（`C1–C9`、`V1–V5`、`D1–D12`） |
| 成功行已含签名 | **4 / 14**（外加 `F1–F6`、`G1–G7`） |

⇒ 结论：**照字面抄 C12-1 会得到一道对 9 道门恒真的门**。要把判据做实，就得让
「签名」成为**每道门自己的一件东西**（源码里的常量 + 成功行里的输出），而不是
从输出里「抽」出来的巧合。

### 1.2 表行的内容今天**没有**对手方（这就是真缺陷）

`P4` 的两向是「表 ↔ 真实清单」，**行内容不参与任何比对**。因此下面这种改动
在修前是**完全静默**的：

```
| `check_alpha.py` | <beta 的描述…> |      ← 整段换成另一行的
| `check_beta.py`  | <beta 的描述…> |
```

行的首列没变、行数没变、两侧同时改也一样 —— `check_all` rc 仍是 0。

## §2 黑帽：本轮抓到的问题（全部是**跑出来**的）

| # | 失效 | 现场 | 处置 |
| --- | --- | --- | --- |
| 2.1 | **判据恒真**（最有价值的一次） | S3 首版把「签名的锚点必须在该门源码里出现」写成对**整份源码**搜索 —— 而签名本身就写在源码里（`F1` 是 `"F1–F6"` 的子串）⇒ 这条判据**永远为真**。真树上跑**发现不了**（真树本来就绿） | `--selftest` 的 `P5 anchor` 坏样本**本该红却放行**，把它顶出来了；修法：`gate_row_signature()` 返回源码时把**声明那一行的字面量抹掉**（`ROW_SIGNATURE =`），锚点只能由**别处**满足 |
| 2.2 | **`%s` 的参数位置写错** | 补丁把签名塞进参数元组**开头**，而 `%s` 在格式串**末尾/中间** ⇒ 三道门 `TypeError: %d format: a real number is required, not str`（`check_c_frontend_shapes` / `check_flow_diagrams` / `check_operator_impl`） | 由独立装置 `probe_signature_impact.py`（它跑每道门并读成功行）与 `check_all` 同时抓出；`patch_r62_fix.py` 三处改正 |
| 2.3 | **写盘时 str/bytes 混用** | `patch_r62_gates.py` 首版 `io.open(p,"wb").write(str)` ⇒ 第一个文件被**截断成 0 字节**（`check_baseline.py`） | 立即 `git checkout --` 恢复（34837 B），改成先 `.encode("utf-8")`，并把 `bare_lf` 自检也算在 **bytes** 上 |
| 2.4 | **常量夹在 import 之前** | 首版把 `ROW_SIGNATURE` 插在模块 docstring 之后、`import` 之前 | `patch_r62_relocate.py` 迁移到 **import 块之后**（`ast` 定位最后一个模块级 import），全 14 个文件迁移；迁移后断言 `import` 位置 < 常量位置 |
| 2.5 | **幂等守卫写错一次** | `patch_r62_readme.py` 首版把「该行已含签名」当**失败**，于是 3 道本来就含签名的门（`C1–C9`/`V1–V5`/`D1–D12`）把整体写盘挡下 | 判据改成「**统一前缀**是否已存在」：已存在 ⇒ 跳过（真幂等）；行里本来有没有签名**不算数** |

## §3 落地物

### 3.1 14 道门：声明 + 自报（**追加式**，不改写既有文案）

每道门在 import 之后新增（同一段注释 + 一行常量）：

```python
# R62/P5：「质量门表」里本门那一行的**签名**（本门自己的判据族，
# 或本门独有的机制名）。它必须逐字出现在两处：
#   ① 本门的成功行（下面 main() 打印的那一行）；
#   ② README.md / README_CN.md 里本门那一行。
# 对手方 = tools/check_readme_parity.py 的 P5（表行内容 ⇄ 门）。
ROW_SIGNATURE = "F1–F6"
```

并在成功行里用 `%s` 把 `ROW_SIGNATURE` **打出来**（已有文案一字不改，只在尾部追加）；
`V1–V5` / `F1–F6` / `D1–D12` / `G1–G7` 四处原本就写着字面量，改成引用常量 —— 输出**逐字不变**。

| 门 | 签名 | 语义 |
| --- | --- | --- |
| `check_baseline.py` | `P1–P4` | 四条前置条件 |
| `check_binfmt_fixtures.py` | `C1–C9` | 契约 C1–C9 |
| `check_boundary_reverse.py` | `V1–V5` | 「诚实的边界」五条反向判据 |
| `check_c_frontend_shapes.py` | `F1–F6` | C 前端六条形态判据 |
| `check_doc_flags.py` | `NO_HELP_SCRIPTS` | 它独有的登记表（按设计无 CLI 选项的脚本） |
| `check_flow_diagrams.py` | `D1–D12` | 图集十二条判据 |
| `check_help_contract.py` | `B0–B5` | 边界承诺 ⇄ 帮助正文的六条登记判据 |
| `check_import_graph.py` | `G1–G7` | import 图七条判据 |
| `check_ir_attribution.py` | `I0–I7` | 归因八条判据 |
| `check_operator_impl.py` | `_UNIMPLEMENTED_KINDS` | 它独有的登记表（「不做」的算子） |
| `check_patch_ops.py` | `G0–G3` | 补丁算子四条判据 |
| `check_py36_clean.py` | `--check-py36` | 它实际驱动的那个开关 |
| `check_readme_parity.py` | `P1/P2/P4/P5` | 本门自己的判据族 |
| `check_subprocess_hygiene.py` | `S1–S5` | 子进程卫生五条判据 |

> 选签名的口径：**能用判据编号族就用编号族**（它本来就是这门在用的判据名）；
> 只有三道门（`check_doc_flags` / `check_operator_impl` / `check_py36_clean`）
> 的判据从来没编号 —— 对它们取「只有它们在用的**机制名**」，而不是为了凑格式
> 硬造编号（那会变成 R61 §9-1 点名拒绝的「拆判据凑覆盖面」）。

### 3.2 `tools/check_readme_parity.py`：新增 **P5**（S1–S5）

| 子判据 | 对手方（什么会红） |
| --- | --- |
| S1 覆盖 | 某道真实护栏**没有**声明 `ROW_SIGNATURE` ⇒ 它那一行没有对手方 |
| S2 非退化 | 签名 <3 字符，或不含数字/下划线 ⇒ 该登记**不生效**（与 `LAZY_CYCLES` 的「理由 <8 字符不生效」同源） |
| S3 锚点真实 | 签名的锚点（`F1`、`F6`…；机制名则取整串）必须在**抹掉声明行之后**的源码里出现 |
| S4 唯一 | 两道门共用同一个签名 ⇒ 「换行」同样看不出来 |
| S5 表行 | 两侧 README 的**对应表行**不含本门签名 ⇒「表说 A、门做 B」 |

外加一条**缺输入**判据：`tools/` 下一个 `check_*.py` 都没有 ⇒ 红（与
`check_ir_attribution` 的「空表是真红」同源，而不是「没有可检查对象 ⇒ 放行」）。

两半**故意分开**：

* **静态半**在门里（读源码，**不 import 门、也不 spawn 门** —— 否则本门会把
  全套护栏再跑一遍，且会与 `check_readme_parity` 自己递归）；
* **行为半**（门真的把签名打进了成功行）在 `tests/test_matlabc.py::test_r62_*`，
  用 14 个子进程真跑每道门。

### 3.3 两侧 README 的质量门表

每行前缀统一成 `| \`check_x.py\` | \`签名\` — 原描述…`（**只改行内容**，
不改行数与结构 ⇒ P2 的逐节计数不变）；`check_readme_parity.py` 那一行尾部补上
P5 的说明。改动量：`README.md` **+578 B**、`README_CN.md` **+587 B**。

### 3.4 登记表与文档

| 文件 | 改动 |
| --- | --- |
| `tools/check_help_contract.py` | `GUARD_CONTRACT["tools/check_readme_parity.py"]` 的 0/1 描述补 P5（**退出码集合未动**，G1/G2 仍逐码一致） |
| `CONTRIBUTING.md` | 新增「质量门表的**内容** ⇄ 那道门（R62 / P5）」一节（含 S1–S5 表 + 那条恒真自伤） |
| `tests/test_matlabc.py` | `test_r62_gate_row_signatures_two_way`（静态半 + 行为半 + 反向）、`test_r62_parity_gate_p5_end_to_end` |
| `docs/SUPERPOWER_REVIEW_R62.md` | 本文件 |

## §4 判据与验证矩阵（数字全部取自**定稿之后**的最后一次回归）

| 判据 | 装置 | 读数 |
| --- | --- | --- |
| P5 主路径 | `tools/check_readme_parity.py` | **rc=0**，打印 `表行签名 P1/P2/P4/P5，14 道门的表行内容与那道门逐字对上` |
| P5 自证 | 同上 `--selftest` | **rc=0 / `SELFTEST COUNTS {"bad": 16, "good": 5}`**（P4 时是 9/4；+7 反例 +1 正例） |
| 14 道门各自自证 | `tools/check_all.py` | **rc=0（14 个护栏，全部通过且各自自证；门数下限 14）** |
| 退出码契约 | `tools/check_help_contract.py` | **rc=0**（6 入口 + **15** 护栏脚本；4 份文档数字与事实一致） |
| 帮助体积 | `matlabc.py --help` | **50451 B 未变**（本轮**没动** `matlabc.py`） |
| 家族回归 | pytest | `-k "r31 or r37 or r44 or r50 or r51 or r52 or r53 or r54 or r55 or r56 or r61 or r62 or renderers_import_smoke"` → **30 passed** |
| R62 单族 | pytest | `-k "r62"` → **2 passed**（含 14 个子进程真跑每道门） |
| **反向判据 A（门）** | 干净树 `654e22e` + 只注入新门 | **rc=1 / 15 项**：13 道门 `没有声明 ROW_SIGNATURE` + 本门两侧 README 行缺 `P1/P2/P4/P5`（`check_readme_parity.py` 自己的常量是随新门一起注入的） |
| **反向判据 B（测试）** | 干净树 `654e22e` + 只注入新门 + 新测试 | **2 failed / 3.03s**：端到端那条死在 `returncode == 0`（门在干净树上 rc=1），静态那半死在 `没有声明 ROW_SIGNATURE` |
| **反向判据 C（P4 看不见）** | 本树：把一行整段换成另一行 | P5 **红**且点名那一道门；同一份文本上 **P4 仍绿** ⇒ P5 不是装饰 |

## §5 轮次账本（R62 内）

| # | 动作 | 结果 |
| --- | --- | --- |
| 1 | 三支仓库外装置量影响面 | 9/14 无编号族、6/14 token 交集为空 ⇒ **字面版 C12-1 会恒真** |
| 2 | 补丁 1：14 道门加常量 + 成功行自报 | 首次写盘 str/bytes 混用 ⇒ 1 个文件被截断，立即 `git checkout --` 复原；改后 14/14 写盘 |
| 3 | 复测 | 3 道门 `TypeError`（`%s` 参数位置）⇒ 补丁 2 修正 |
| 4 | 补丁 3：常量块迁到 import 之后 | 14/14 |
| 5 | 实现 P5（S1–S5 + 缺输入） | 门 rc=0；自证 8 个 P5 样本 —— **`P5 anchor` 放行 ⇒ 抓到恒真自伤**，修完 16/5 PASSED |
| 6 | 补丁 4：两侧 README 14 行加签名前缀 | 各 +227 B；幂等守卫写错一次（§2.5）当场挡住 |
| 7 | 补丁 5：`check_readme_parity.py` 行尾补 P5 说明 | README +351 B / README_CN +360 B |
| 8 | 补丁 6：两条 R62 测试 | 2 passed |
| 9 | 文档（`CONTRIBUTING.md` 一节 + 本文件） | — |
| 10 | `check_all` / 家族 / 反向判据 A–C | 全部按预期 |

## §6 探针清单（仓库外 `E:\matlabc\_r62\`，**不进 git**）

| 文件 | 作用 |
| --- | --- |
| `probe_content_parity.py` | 成功行 / 表行 / 「字面版 C12-1」的可行性体检 |
| `probe_shared_tokens.py` | 成功行 ⇄ 表行的词元交集（量「今天已经共享什么」） |
| `probe_signature_impact.py` | 14 道门 × 四轴（声明/锚点/表行/成功行）的影响面，改动前后各跑一次 |
| `patch_r62_gates.py` | 14 道门：常量 + 成功行自报（锚点各 1 次、全或无、`ast.parse` + `bare_lf` 自检） |
| `patch_r62_fix.py` | 三处 `%s` 参数位置修正 |
| `patch_r62_relocate.py` | 常量块迁到 import 之后（`ast` 定位） |
| `patch_r62_readme.py` | 两侧 README 的 14 行加签名前缀（真幂等：统一前缀） |
| `patch_r62_readme_p5.py` | `check_readme_parity.py` 行尾补 P5 说明 |
| `patch_r62_tests.py` | 两条 R62 测试 |
| `normalize_doc.py` | 新文档归一 CRLF + `bare_lf == 0` 自检 |
| `*.txt` | 每次运行的原始读数（`check_all` / `pytest` / 门自证 / 反向） |

## §7 已知盲区（不藏）

1. **S3 只证「锚点在那份源码里出现过」**，不证「那条判据真的在做这件事」——
   与 R56 C11-2（豁免 `where` 缺少「判据名」第二维）**同源**。落点见 C13-2。
2. **签名是常量，不是算出来的**：它锚在源码里的别处（S3），但一次「把常量改成一个
   同样在源码里出现的字符串」仍能混过去（S4 只挡两道门共用）。下一轮候选见 C13-1。
3. **行为半在 `tests/`，不 `check_all`**：`check_all` 跑不到「门真的打出来了」这一条
   （除非本门真跑全套护栏 —— 那是它**刻意不做**的）。这是**刻意的分工**，不是遗漏：
   静态门快、行为判据重，本仓既有纪律就是「重门禁放 `tests/`」。
4. **`tests/` 本就有永久红**（`fe_audit` / `trend` / `r78` / `readme_doc_sync` 等），
   与本轮无关；判「是不是我引入的」用 `git worktree` 干净树对照。

## §8 下一次建设性意见（接在 R61 §8 之后；**C12-1 本轮完成**）

**C13-0（沿用 R49–R62，仍最高优先）`fe_audit.py` / `frontend-gate.yml` 的「不做」登记。**
R53 量出的真实规模是**单个 `-k` 过滤式 25 条红**。R54/R55/R56/R61/R62 已连出五种
可复用模板（按**产物**登记 + 两向核对；**承诺 ⇄ 判据**；**口径 ⇄ 覆盖数**；
**表 ⇄ 真实清单**；**表行内容 ⇄ 那道门**）。

**C13-1（R62 新洞见，优先级高）把签名从「常量」升级为「**算出来的**」。**
现在 S3 只证「锚点在那份源码里出现过」（可能是注释、可能只是一处引用）。
落点：要求签名里每个判据编号在该门源码里以**判据标签**的形式出现（如
`"F1 "` 这种「编号 + 分隔符」的字符串字面量，或 `CRITERIA_IDS` 元组成员），
这样「新增一条判据却忘了改签名」才有人守。**对手方**：把某条判据的编号从
源码里改掉而签名不动 ⇒ 必须红。

**C13-2（沿用 R56 C11-2 / R61 C12-4）给登记表的 `where` 加第二维：判据名。**
`Mach-O：` 的豁免写成 `where = ("tools/check_binfmt_fixtures.py", "verified=False")`
—— 只证了「这个 token 在那份文件里出现」，**没有证**「那条判据真的在做这件事」。
与 §7-1 是同一个病。

**C13-3（沿用 R61 C12-2）`_c_lex` 的 token 行号恒等式也进仓库**（现在只活在 `_r49/`）。
落点：`matlabc.py::_scan_c_definitions_selftest()` 里加一段「每个 token 的行号 ==
其偏移所在行」的自洽断言，`check_c_frontend_shapes.py` 的 F5 用公开 CLI 行号作第二次作证。
**对手方**：删掉字符串续行的 `line += 1` ⇒ 自证必须红。

**C13-4（R62 顺手量出的新事实）「成功行 ⇄ 表行」的 token 交集只有 8/14 非空**，
且其中 3 个是 `full` / `stdin` / `mermaid` 这类**弱 token**。也就是说：如果哪天
有人想再加一道「文档 ⇄ 输出」的判据，**先量交集，别假设它存在**。

**C13-5（沿用 R61 C12-5）「豁免的理由」也需要反向判据**：要求理由里逐字出现
`where` 那个文件名的**基名**。

**C13-6（沿用 R61 C12-6）** `git archive` 导出树没有 `.git` 的**可断言实测**；
`BORROWED` 的文档侧对手方。

## §9 明确拒绝做的事（避免下一轮走回头路）

1. **不为「格式统一」给三道没编号的门硬造判据编号**（`W1–W4` 之类）：那会让
   「每条判据各有独立证人」变成装饰。取「只有它在用的机制名」是等价强度的门。
2. **不把 P5 做成「任何一行提到 `check_*.py` 就比对」**：P4 已限定在**质量门表的
   连续表块**内，P5 沿用同一个定位器；历史文档（`docs/SUPERPOWER_REVIEW_R*.md`）
   里的数字在写下的那一刻都是真的。
3. **不在 `tools/check_readme_parity.py` 里 spawn 那 14 道门**：会自跑递归、会把
   门禁从 30s 级拖到分钟级。行为判据放 `tests/`。
4. **不改 `HELP_BYTES_SNAPSHOT`、不放宽 `HELP_DRIFT_MAX`**（本轮 `matlabc.py` 一字未动）。
5. **不动 `flow/diagrams`、不动 `VERSION`**（用户明确指示：本轮不修图）。
6. **不把「签名」做成双份事实源**（门里一份、登记表里一份）：那会回到
   「两处要人记得同步」的老问题。签名**只有一处事实源** = 门自己的常量。
