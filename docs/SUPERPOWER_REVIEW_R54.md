# R54 —— 判「是不是 git 仓库」必须接受 `git worktree` 形态

> 本轮是**修测量工具自己**，不是修被测对象。上一轮（R53）在用 `git worktree add`
> 起对照组时发现：**对照组里 `check_all` 跑不完**，于是对照组只能跑 pytest、证不了门禁。
> 本轮把那道闸门本身修好。

## §1 白帽：事实（全部来自仓库外独立装置实测）

| # | 事实 | 证据 |
| --- | --- | --- |
| 1 | 旧判据 `os.path.isdir(root/.git)` 出现在**两处** | `agent_loop.py::_is_git_repo`（服务 git 回退）、`tools/check_baseline.py::check_prerequisites` 的 **P1** |
| 2 | `git worktree add _r54/wt_head 082bf03` 后，`.git` 是**文件**（50 B） | 内容逐字：`gitdir: E:/matlabc/malabc/.git/worktrees/wt_head1` |
| 3 | 修前：worktree 自带的**旧**脚本 + worktree root ⇒ **rc=2** | `P1 …\_r54\wt_head 不是 git 仓库：无法导出 HEAD（基线的前提）` |
| 4 | 修后：主树的**新**脚本 + 同一个 worktree root ⇒ **rc=0** | `check_baseline: OK（前置条件 4 项 + 判定逻辑两向自证 {"bad": 11, "good": 13}…）` |
| 5 | 真 payoff：把修后的 `check_baseline.py` 叠进 worktree，**在 worktree 里**跑 `check_all.py` ⇒ **rc=0** | `check_all: OK（12 个护栏，全部通过且各自自证；门数下限 12）` |
| 6 | `tools/` 全仓**不 import** 产品模块 | `grep -rn "^import matlabc\|^from matlabc" tools/*.py` 为空 ⇒ 只能写**两份同义实现** |

**缺陷性质**：这是**测量工具自己的** bug。它不改变被测对象，却**限制了对照组能证的东西**
——而对照组正是本仓所有「是不是我引入的」结论的唯一来源。

## §2 黑帽：本轮要防的三类静默失效

1. **把「像仓」当成仓。** 只要看到 `gitdir:` 字样就放行，会把**损坏的**工作树
   （`gitdir:` 指向不存在或已删除的目录）也算成仓。判据会从「是不是仓」退化成「像不像仓」。
2. **放宽过头 = 洗白。** 若顺手把「根本没有 `.git`」也放行，P1 就永远不红，
   基线门的前置条件体检**变成装饰**。所以「真·非仓库目录」必须**照旧红**。
3. **顺手放行 `git archive` 导出树会立刻破坏一条既有登记。**
   `check_baseline.py::KNOWN_BASELINE_NOISE` 的依据是「导出树不是 git 仓库 ⇒ P1 必红一次，
   那是环境差异不是回归」。若我把「没有 `.git`」也放行，这条登记**当场过期**（B3 会把它顶出来），
   或者更糟：让它变成一条**假解释**。

## §3 落地物

### 3.1 两份**独立同义**实现

| 文件 | 函数 | 用途 |
| --- | --- | --- |
| `agent_loop.py` | `_is_git_repo(directory)` | 决定回退走 `git apply` 还是进程内快照 |
| `tools/check_baseline.py` | `_is_git_repo(root)` | 默认模式前置条件 **P1** |

**为什么是两份而不是一份**：`tools/` 下**没有任何脚本** import 产品模块（这是本仓的既有
分层纪律，`grep` 为证）。所以这里**不用硬 import**，改用**一致性判据**代替单一实现：

> `tests/test_matlabc.py::test_r54_git_repo_detection_accepts_worktree_form`
> 在 **7 个样本**上要求两份实现**逐例相同**，且都等于期望值。

判据语义（两处逐字相同）：

```text
① `.git` 是目录                                  -> 是仓（普通仓库 / 子模块）
② `.git` 是文件 & 首行 `gitdir:` 指向存在目录     -> 是仓（git worktree）
③ `.git` 是文件 & `gitdir:` 指向不存在目录        -> 不是仓（损坏的工作树）
④ `.git` 是文件 & 无 `gitdir:` 前缀 / 冒号后为空  -> 不是仓
⑤ 没有 `.git`                                    -> 不是仓
```

`gitdir:` 的相对路径按**工作树根**解析（`os.path.join(root, target)`），绝对路径直接用 ——
本机 git 实测写的是**绝对路径 + 正斜杠**（`E:/…`），`os.path.isabs` 认得，两条分支都覆盖。

### 3.2 门自身的两向自证：7 例新增

`tools/check_baseline.py --selftest` 由 **3 反 3 好**扩到 **7 反 7 好**（下界 `>= 7/9` → `>= 11/12`）：

| 类型 | 样本 |
| --- | --- |
| 好 | `.git` 是目录 |
| 好 | `.git` 文件 + `gitdir:` **相对**指向存在目录 |
| 好 | `.git` 文件 + `gitdir:` **绝对**指向存在目录 |
| 坏 | 没有 `.git` |
| 坏 | `gitdir:` 指向**不存在**目录（不许把「像仓」当仓） |
| 坏 | `.git` 文件无 `gitdir:` 前缀 |
| 坏 | `gitdir:` 后为空 |

## §4 判据与验证矩阵（改完 → 终局回归 → 数字）

| 判据 | 装置 | 读数 |
| --- | --- | --- |
| **A 修前必红** | worktree 自带旧脚本 + worktree root | **rc=2**，`P1 … 不是 git 仓库` |
| **B 修后必绿** | 主树新脚本 + 同一 worktree root | **rc=0**，无 P1 |
| **C 没修歪** | 新脚本 + 真·非仓库目录 | **rc=2**，P1 点名「既不是目录，也不是首行 `gitdir:` 指向存在目录的文件」 |
| **D 登记仍成立** | 新脚本 + `git archive HEAD` 导出树（`os.path.exists(.git)` = **False**） | **rc=2**，P1 红 ⇒ `KNOWN_BASELINE_NOISE` **不过期** |
| **E 真 payoff** | 修后脚本叠进 worktree，**worktree 内**跑 `tools/check_all.py` | **rc=0**，`check_all: OK（12 个护栏）` |
| 自证 | `check_baseline.py --selftest` | `SELFTEST COUNTS {"bad": 11, "good": 13}`（R43 时 7/10） |
| 反向判据（绿） | 本树 | `pytest -k "r54 or r53 or r52 or r51 or r50 or r37 or r43 or static_guards or renderers_import_smoke"` → **13 passed** |
| agent_loop 整文件 | `tests/test_agent_loop.py` | **15 passed**（其中一条 monkeypatch `_is_git_repo`，名字未变 ⇒ 不受影响） |
| 总门禁 | `tools/check_all.py` | **rc=0（12 道护栏，各自自证）** |
| 双语结构 | `check_readme_parity.py` | 15 小节逐节对等（两侧均在**同一行内**追加文字） |

**探针整体结论**：`R54 PROBE PASSED（四方对照全部符合预期）`，数字
`{"a_old_rc": 2, "b_new_rc": 0, "c_plain_rc": 2, "d_archive_rc": 2, "e_wt_checkall_rc": 0}`。

## §5 轮次账本

| # | 动作 | 结果 |
| --- | --- | --- |
| 1 | 影响面量化：全仓 `isdir(.git)` | **两处**（`agent_loop.py` + `check_baseline.py`）；其余 `.git` 命中都是 `SKIP_DIRS` 常量，不同义 |
| 2 | 确认 `tools/` 不 import 产品 | `grep` 为空 ⇒ 走「两份同义 + 一致性判据」 |
| 3 | 确认改 `tools/` 文档不触门 | `HELP_BYTES_SNAPSHOT` 只覆盖 5 个入口脚本；`check_doc_flags.SCRIPTS` 只含入口脚本 |
| 4 | 全或无补丁（3 文件 / 7 处） | 锚点各 1 次；`ast.parse` 全过；`bare_lf=0` |
| 5 | 自证 | `{"bad": 11, "good": 13}` |
| 6 | 新测试 | `1 passed` |
| 7 | 四方对照探针（真 `git worktree`） | `PROBE PASSED` |
| 8 | `check_all` | **rc=0（12 道）** |
| 9 | 家族 13 条 + `test_agent_loop.py` 15 条 | 全绿 |

### 本机踩坑（本轮的）

1. **shell 的反引号会吃掉 `python -c "…"` 里的代码块。** 往 `MEMORY.md` 头部写
   `` `MEMORY.md` `` 时，双引号内的反引号被 bash 当**命令替换**执行，写进去的是空串
   （报 `MEMORY.md: command not found`，却被 python 的 rc=0 掩盖）。**写含反引号的文本
   一律用 `Write`/`Edit` 工具，不要内联进 shell。**
2. **`git worktree` 的 `.git` 文件写的是绝对路径**（`gitdir: E:/…`），不是相对路径 ——
   所以「相对路径解析」这条分支本机**测不到真值**，只能靠**合成样本**覆盖
   （已用 `../store_rel` 造了合成样本）。
3. **`check_all` 在 worktree 里原本跑不完**，所以本轮最硬的那条证据（E）**必须**在
   worktree 里叠入修后文件才能拿到 —— 这也顺带证明了「对照组能跑门禁」这件事**确实被解锁**。

## §6 探针清单（仓库外，**不进 git**）

| 文件 | 用途 |
| --- | --- |
| `_r54/patch_r54.py` | 3 文件 / 7 处全或无补丁（锚点各 1 次 + `ast.parse` + `bare_lf` 自检） |
| `_r54/probe_p1.py` | 四方对照 A–E（真 `git worktree` + `git archive` 导出树），输出 `R54 PROBE …` |
| `_r54/wt_head/` | `git worktree add --detach 082bf03` 起的真工作树（对照组本体） |
| `_r54/*.pre.py` | 改前三个文件的副本（回退用） |

## §8 下一次建设性意见（接在 R53 §8 之后；**R53 C0–C4 中 C1 已在 R54 完成**）

**C9-0（沿用 R49–R53，仍最高优先）`fe_audit.py` / `frontend-gate.yml` 的「不做」登记。**
R53 已量出真实规模（单个 `-k` 过滤式就有 **25 条红**，不是历史文档写的 7 条）。
本轮**顺带给出了可复用的模板**：把缺口按**产物**登记，并且**两向**核对 ——
登记了却其实已存在 → 红；存在却仍被登记为缺失 → 也红。

**C9-1（本轮新发现，优先级高）把「`git archive` 导出树没有 `.git`」变成可断言的实测。**
R54 的 D 项证明：`KNOWN_BASELINE_NOISE`（「导出树不是仓 ⇒ P1 必红一次」）**在修后仍然成立**。
但这条登记的依据是**环境行为**，而**没有任何门钉住它**。哪天导出方式一改
（例如改用 `git worktree` 导出以获得 `.git`），P1 不再红，`B3 陈旧登记` 会红 ——
但那时的报错**指向登记表**，不指向真正变了的导出方式。落点：一条测试，
显式断言「`git archive HEAD` 的产物里不存在 `.git`」。

**C9-2（本轮副产品）给「同义多实现」建登记。** R54 用**一条测试**保证两份 `_is_git_repo`
逐例一致。但若以后有人再加**第三份**（例如某个门里又写一次），没有任何东西会提醒他
「这里已有一份同义的」。落点：`tools/check_import_graph.py` 或新门里加一张
`SYNONYMIC_HELPERS` 登记表 + 两向核对（未登记的同义实现 → 红；登记的已消失 → 也红）。

**C9-3（沿用 R53 C2）`BORROWED` 的**文档侧对手方**。** 现在它只有代码侧对手方（G7）；
`CONTRIBUTING.md` 那张表是**手写**的，删掉一行没有任何东西发现。

**C9-4（沿用 R53 C3）真正**移走**那 22 个被借用的符号**（= 消灭借用，而非推迟）。
第一步仍是 R52 点名的四个**纯路径辅助**搬进 `renderers/_shared.py`；搬完 `BORROWED` 必须缩水。

**C9-5（沿用 R53 C4）给 `check_import_graph.py` 的「判据条数」加棘轮。**
现在判据 7 条、自证样本 19 条，但**没有一条断言**阻止以后有人删掉 G7 而不改数字。

**C9-6（本轮新洞见，待量）`agent_loop` 的 git 回退在 worktree 里的**行为**没人量过。**
本轮只修了「判据认不认 worktree」。但 `agent_loop.py` 的纪律写着「工作副本必须干净，
否则回退会带走你的未提交改动」—— 在 worktree 里这条**是不是成立**（worktree 的
`git status` 语义、`git apply` 的路径基准）**尚未实测**。落点：一次带真实 patch 的
worktree 回退实验，并把它固化成测试。

## §9 明确拒绝做的事（避免下一轮走回头路）

1. **不为过门而放宽判据**：`.git` 缺失仍然红（C 项为证）—— P1 不是装饰。
2. **不用「像仓」代替「是仓」**：`gitdir:` 指向的目标**必须存在且是目录**。
3. **不改 rc 语义**：`GUARD_CONTRACT["tools/check_baseline.py"]` 的 `{0,1,2}` 一字未动
   （P1 仍走「缺输入 ⇒ 2」那条路）。
4. **不让 `tools/` import 产品模块**：宁可写两份同义实现 + 一致性判据。
5. **不动 `flow/diagrams`、不动 `VERSION`、不动 `HELP_BYTES_SNAPSHOT`**（本轮零产品行为变更；
   `--help` 正文只多了一句对 P1 判据的说明，`check_all` 已证 6 个入口脚本的契约仍双向一致）。
