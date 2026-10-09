# SUPERPOWER_REVIEW R52 —— 打断 `renderers` ↔ `matlabc` 的 **import 期回边**

> 本轮落地用户优先清单里的 **C''''3 `tools/check_import_graph.py`：打断 `renderers` ↔ `matlabc`
> 循环依赖**（= R44 §8 C''''3 / R49 §8 C'''''8 / R50 §8 C''''''3 / R51 §8 C''''''3）。
> 方法沿用本仓既有纪律：先用**仓库外的独立装置**量影响面，再改代码，再加**反向判据**
> （真红 → 真绿），再跑总门禁与相关家族，最后**从远端 clone 回来**做对象级验证。

---

## §0 结论先行

| 口径（独立装置实测） | R52 前 | R52 后 |
| --- | --- | --- |
| **模块级（import 期）环数** | 1（`matlabc` + 6 个 renderer 一共 7 个模块的 SCC） | **0** |
| 全图（含嵌套惰性边）环数 | 2 | 1（`agent_loop` ↔ `matlabc_flow`，**已登记**） |
| `renderers.*` 里的模块级 `from matlabc import` 语句 | **6** | **0** |
| 被借用符号的使用点（裸名） | 44 处 | 44 处改写成 `_mL.名字` |
| 指向本仓模块的**动态** import | 0（此前**没有**任何装置看得见它） | **2**（`_late`→`matlabc`、测试→`frontends`，登记 + 双向核对） |
| 全仓「模块级 import 图」装置 | **0** | 1 道（`tools/check_import_graph.py`，判据 G1–G6） |
| 护栏道数 | 11 | **12** |

修法两半，缺一都不算落地：

1. **真修**：新增 `renderers/_late.py`（**不在 import 期触碰 matlabc** 的惰性通道），
   把 6 个 renderer 模块底部的 `from matlabc import (...)` 换成
   `from renderers/_late import late as _mL`，并把 44 处裸名使用点改成 `_mL.名字`。
2. **补装置**：`tools/check_import_graph.py` —— 把「**模块级 import 必须无环**」钉成判据，
   并让「剩余的惰性环」与「指向本仓模块的动态 import」只能走**登记 + 两向核对**。

---

## §1 白帽：事实清单（全部实测，可复现）

1. **装置 1**：`E:\matlabc\_r52\probe_import_graph.py`（仓库外、LF、零依赖）。
   用 `ast` 建模块图，Tarjan 求 SCC。修前读数：`NODES=51`、`SCC_MULTI=2`：

   * `matlabc <-> renderers.callgraph <-> renderers.hotspot <-> renderers.report
     <-> renderers.sarif <-> renderers.snapshot <-> renderers.unresolved`
   * `agent_loop <-> matlabc_flow`

2. **装置 1 的自伤（当场被抓）**：它用「`node.lineno` 落在某个顶层语句的行范围内」
   判「模块级」—— 而**嵌套节点的行号天然落在其中**，于是把 `agent_loop ↔ matlabc_flow`
   （两条边都写在函数体里）误判成**模块级**环。装置 3（`_r52/probe_cycle_kind.py`）
   改成**只看 `tree.body` 的直接子节点**后，这条环如实变成 `nested`。
   ⇒ 又一次实证：**测量工具自身的 bug 会伪造出被测对象的 bug**。

3. **修前的隐性代价**：`renderers/report.py:270` 之类的 `from matlabc import (...)` 与
   `matlabc.py:31310` 的 `from renderers.report import (...)` 互为**回边**。它能跑，
   靠的是一份**隐式时序契约** ——「matlabc 被部分初始化时，被借用的名字必须已经定义在
   再导出点之前」。装置 2（`_r52/probe_partial_init.py`）量出：6 个 renderer 共借用
   **20 个符号**，全部落在再导出点之前 —— 契约今天**成立**，但它**没有任何对手方**。

4. **反向安全性也成立**（`import renderers.X` 先执行时）：matlabc 从 renderer 借用的每个名字，
   都定义在该 renderer 回边行之前（`_r52/probe_partial_init.py` 的 C 段全 OK）。
   这条性质 R52 之后**不再需要** —— 因为回边已经不存在。

5. **44 处使用点全部在函数体内、且全是 `Load` 上下文**（装置实测）：
   `callgraph 3 / hotspot 3 / report 5 / sarif 7 / snapshot 21 / unresolved 5`。
   ⇒ 惰性代理在**调用期**取符号，行为上与原写法等价。

6. **不能整行正则改写**：`renderers/sarif.py` 的 docstring 第 2 行、`renderers/snapshot.py`
   第 483 行的**字符串字面量**里都出现过这些名字。补丁因此走 **`ast` 的字节列偏移**，
   而不是正则（`_r52/patch_r52_late.py`）。

---

## §2 黑帽：本轮抓到的问题（含诚实声明）

### 2.1 真缺陷：import 期的环靠一份**没人钉住**的时序契约活着

`renderers/` 的存在意义就是把页面生成从 31 k 行的 `matlabc.py` 里拆出来，
所以「renderer 需要 matlabc 的分析函数」是**设计如此**。问题不在借用本身，
而在**借用的时机**：写在模块底部，等于宣布「我在 import 期就要这些名字」，
于是两个模块在 import 期互相需要对方**已经初始化到某个位置**。

这一类缺陷的特征是：**它现在不报错**。它只在有人把某个被借用的名字挪到再导出点之后、
或者把某个 renderer 的底部 import 提前时，才会以「AttributeError / ImportError」的
形态在**运行时**炸开 —— 而 `git status`、`git diff`、以及当时全部 474 个测试都看不见。

修法是把它变成**不可能**：惰性通道 + 「模块级 import 图无环」的判据。

### 2.2 真缺口：全仓「import 图」没有装置

R49–R51 连续三轮都在处理同一类病（**声明与装置分叉**）：R50 是 `.exts` 声明，
R51 是「诚实的边界」承诺。R52 在**结构层**遇到第三次：`CONTRIBUTING.md` 早就写着
「避免与 `matlabc.py` 反向 `import` 形成环形依赖」，**但没有任何东西能证明它没被违反**。

### 2.3 诚实声明（本轮不假装）

- **借用关系没有被消灭，只是被推迟。** `renderers` 仍然在**运行期**依赖 `matlabc`
  （`renderers/_late.py` 里的 `importlib.import_module("matlabc")`）。
  R52 消灭的是 **import 期**的环 —— 也就是「部分初始化的对方」这一整类故障。
  把它彻底消除（把 20 个符号搬出 `matlabc.py`，或倒置依赖）是 §8 的
  C'''''''6，本轮**没做**。
- **G1 只保证「模块级 import 图无环」，不保证架构变好。** 一个把 20 个函数抄一遍
  的仓库同样无环。
- **登记的惰性环仍在**（`agent_loop` ↔ `matlabc_flow`）。它不是本轮引入的，也不是缺陷 ——
  两条边都写在函数体里，且两处注释都写明了理由；登记它只是让「谁把它改成模块级边」
  立刻变红。
- **「2 个 nodeid 显示为 fixed」不是本轮修好的**：那是**环境产物**。
  `git worktree` 建出来的树里 `.git` 是**文件**而不是目录，`check_baseline.py` 的
  前置条件 P1 断言「必须是 git 仓库」就会误判（实测输出：`不是 git 仓库：无法导出 HEAD`），
  于是 worktree 侧的 `check_all` 必红，连带 2 条聚合测试变红。真实读数见 §6。

### 2.4 自伤三处（都被装置/纪律当场挡住）

1. **装置 1 的顶层判定用行号范围**（§1 第 2 条）—— 制造了一个**不存在**的模块级环。
2. **shell 内联改写脚本被引号污染**：同一段 `rep(old, new)` 在 `python -c "..."` 里
   把 `\\n` 提前解释成真换行，锚点命中 0 次。改用 `Edit` 工具逐条精确改写。
   本仓纪律里已有这一条（探针一律落 `.py`），本轮再次证实。
3. **`'''…'''` 模板里出现连续四个单引号**（写轮次标记 `C''''3`）会**提前终止字符串**；
   改成占位符 `__C4__`，写盘前替换。

---

## §3 黄帽 / 绿帽：收益与边界

**收益**

1. **一整类故障消失**：`import` 期不再有环 ⇒ 「部分初始化的对方」这个状态不可达。
   `import matlabc` 与 `import renderers.X` 两个方向都变成普通的单向加载。
2. **声明终于有装置**：`CONTRIBUTING.md` 那句「避免反向 import 形成环形依赖」
   从散文变成 G1；而「例外」必须写进同一份文档（G6 双向）。
3. **三条判据各自独立作证**（自证强制「坏样本必须红在**指定**判据上」）：
   模块级回边 → 只 G1；未登记的嵌套环 → 只 G2；未登记的动态 import → 只 G3。
4. **行为保持是可证伪的等式，不是「跑过一次」**：`--reproducible` 下
   **110 个产物文件 + 7 条命令 stdout** 在改前/改后**逐字节一致**，
   且改前侧连跑 **3 次**自证可重复（墙钟耗时按 `MASK` 显式遮蔽，不静默放过）。

**边界**

- G6 只保证「登记表 ↔ `CONTRIBUTING.md` 标记互为对手方」，**不保证**理由的内容为真。
- G3 只看得见**字面量**目标的动态 import；`import_module(some_var)` 抓不到
  （本仓现存 1 处，在测试里）。这是**已知盲区**，写在登记理由里。
- **没有引入任何新依赖 / 新门种**：判据仍是静态 AST，秒级。

---

## §4 蓝帽：本轮建立的不变量

1. **模块级 import 图无环**（G1）。自环不可登记（G4）。
2. **回边只能走登记过的惰性通道**：`renderers/` 在模块级不得出现 matlabc 引用；
   借用一律 `_mL.名字`。
3. **动态取本仓模块必须登记**（G3），且这条登记**两向核对**。
4. **惰性环必须登记**（G2），两向核对；纯模块级环**不许**用登记绕过（由 G1 直接判红）。
5. **理由不变量**：每条登记的说理 ≥ 8 字符，否则该登记**不生效**。
6. **文档同源不变量**（G6）：登记项 ↔ `CONTRIBUTING.md` 标记，两向。
7. **借用名字必须真实存在**：每个 `_mL.X` 的 `X` 必须能在 `matlabc` 上取到
   （由 `tests/test_matlabc.py::test_renderers_import_smoke` 自动派生校验）。

---

## §5 轮次账本（R52 内）

| # | 动作 | 判据 / 产物 | 结果 |
| --- | --- | --- | --- |
| 1 | 读记忆 + R43/R44/R49/R50/R51 §8 | 选定 C''''3（import 图） | — |
| 2 | 独立装置量影响面 | `_r52/probe_import_graph.py` | 51 模块 / 85 边 / **2 个环** |
| 3 | 环分型 + 部分初始化边界 | `_r52/probe_cycle_kind.py` | renderers 环 = 全模块级；agent_loop 环 = 全嵌套；G5 正向 True |
| 4 | 修正装置 1 的自伤 | `is_top` 改看 `tree.body` | 误判的「模块级环」消失 |
| 5 | 体量语料 + 3 次可重复 | `_r52/capture_behavior.py` | 110 文件 + 7 命令，三向一致 |
| 6 | 改代码（7 文件，44 处使用点） | `_r52/patch_r52_late.py`（全或无 + ast + bare_lf） | 一次通过 |
| 7 | 加反向判据 | `tests/test_matlabc.py` 两条 `test_r52_*` + 升级 `test_renderers_import_smoke` | HEAD 树 3 failed → 本树 3 passed |
| 8 | 装置自证 | `check_import_graph.py --selftest` | `SELFTEST COUNTS {"bad": 0, "good": 14}` |
| 9 | 总门禁 | `tools/check_all.py` | **rc=0**，12 道护栏全部通过并各自自证 |
| 10 | 相关家族 | `pytest -k "r52 or r44 or r50 or r51 or r31 or r37 or renderers_import_smoke"` | **21 passed** |
| 11 | 全量回归（按 nodeid 集合） | 干净 `HEAD` worktree vs 本树 | **regressions = 0** |
| 12 | 文档同步 | README×2 / CONTRIBUTING / matlabc.py / 2 个 tools | parity 15 节对等；帮助体积不变 |
| 13 | 提交 + 远端对象级验证 | （见 §6） | — |

---

## §6 验证矩阵

| 面 | 装置 | 判据 | 读数 |
| --- | --- | --- | --- |
| 结构（模块级环） | `_r52/probe_cycle_kind.py` | SCC 大小 > 1 | **2 → 0**（含 agent_loop 那条惰性环：全图 2 → 1） |
| 结构（回边语句） | 同装置 | `renderers/*.py` 模块级 `from matlabc import` 计数 | 6 → **0** |
| 使用点改写 | `_r52/patch_r52_late.py` | 精确计数 | 44 处，锚点各命中 1 次 |
| 行为保持（产物） | `_r52/capture_behavior.py` | 逐字节 sha256 | **110/110 相同**（改前侧三向可重复） |
| 行为保持（stdout） | 同装置 | 归一化路径 + 遮蔽墙钟后逐字节 | **7/7 相同** |
| 反向判据（红） | `git archive HEAD` 树注入新门/新测试 | 三条必须红 | **3 failed**（G1 点名 7 模块环） |
| 反向判据（绿） | 本树 | 三条必须绿 | **3 passed** |
| 门自证 | `check_import_graph.py --selftest` | 坏样本必红在**指定**判据、好样本必过 | `{"bad": 0, "good": 14}` |
| 门主路径 | `check_import_graph.py` | rc=0 且打印计数 | rc=0（53 模块 / 模块级仓库内边 61 / 全图 88；环 0） |
| 总门禁 | `tools/check_all.py` | rc=0 且 12 道各自自证 | **rc=0** |
| 家族 | `pytest -k "r52 or r44 or r50 or r51 or r31 or r37 or renderers_import_smoke"` | 全绿 | **21 passed** |
| 全量回归 | 干净 `HEAD` worktree（`6b96ed7`）vs 本树 | nodeid 集合差 | **regressions = 0**；126 → 124 failed |
| 双语结构 | `check_readme_parity.py` | 15 小节逐节对等 | OK |
| 帮助体积 | `check_help_contract.py` | 棘轮两臂 | `--help` 仍 **50230** 字节（「11 道」→「12 道」等长） |
| 远端 | 从 GitHub clone 回来 | 对象级 sha256 比对 | 见 §5 第 13 项 |

---

## §7 探针清单（仓库外，**不进 git**）

| 文件 | 用途 |
| --- | --- |
| `_r52/probe_import_graph.py` | 装置 1：全图 SCC + 逐边清单（**首版 `is_top` 判据有 bug**，保留作教训） |
| `_r52/probe_partial_init.py` | 装置 2：借用符号的**部分初始化边界**（正向 + 反向） |
| `_r52/probe_cycle_kind.py` | 装置 3：**正确的**模块级/嵌套判定 + 环分型（修正装置 1） |
| `_r52/capture_behavior.py` | 行为保持装置：固定命令集 × 110 产物 sha256 + 3 次可重复 |
| `_r52/patch_r52_late.py` | 7 文件补丁（全或无 + ast 字节列改写 + bare_lf） |
| `_r52/patch_r52_docs.py` | 12 处文档/接线锚点补丁（全或无） |
| `_r52/patch_r52_tests.py` | 测试补丁（升级冒烟 + 两条 R52 判据） |
| `_r52/head_tree/`、`before1..3/`、`after1/` | 对照组与语料（仓库外暂存，未清理） |

---

## §8 下一次建设性意见（接在 R51 §8 之后；**C‌''''''3 已在 R52 完成**）

排序原则不变：**优先「已有装置但没接上线」与「已有承诺但没装置」**，
每条先说清「**什么会红**」。

**C'''''''0（阻塞项，沿用 R49–R51）补 `fe_audit.py` 与 `.github/workflows/frontend-gate.yml`，
或把 7 条测试显式登记为「不做」。**
「守护永远是红的」与「守护没人跑」是同一种病。**对手方**：登记了却其实已存在 → 红；
存在却仍登记为缺失 → 也红。

**C'''''''1（本轮新发现，小而易修）`check_baseline.py` 的 P1 把「有 `.git` **目录**」当成
「是 git 仓库」的唯一形态 ⇒ 在 `git worktree` 里**恒判红**。**
本轮实测：干净 `HEAD` 的 linked worktree 里 `check_baseline` 报
`P1 … 不是 git 仓库：无法导出 HEAD`，于是 worktree 里 `check_all` 必红，
连带两个聚合 nodeid **假**显示为「本轮修好」。落点：改成
`git rev-parse --git-dir` 探测（`.git` 是文件也算）。**对手方**：造一个 `.git` 是文件的
目录 → 修前红、修后绿；而真·非仓库目录仍必须红。

**C'''''''2 给「借用清单」加一份**静态单一事实源**。**
现在 `_mL.X` 的 `X` 由使用点定义，门与测试只能验「X 存在于 matlabc」；
拿掉一个使用点、或新加一个借用，**没有一张表要求同步**。
落点：`renderers/_late.py` 里登记 `BORROWED = {"renderers.snapshot": (...), ...}`，
门断言「使用点集合 == 登记表」（两向）。**对手方**：删一个使用点 → 陈旧登记红。

**C'''''''3 真正**移走**那 20 个被借用的符号（= 把借用关系消灭，而非推迟）。**
最有价值的第一步：`_page_rel` / `_dir_page_name` / `_src_href_from_rel` / `_up_to_index`
四个**纯路径辅助**（合计 794 字节、无其它模块级依赖）搬进 `renderers/_shared.py`，
`matlabc.py` 反向 `from renderers._shared import ...` 保住内部名字。
读数目标：`renderers → matlabc` 的借用从 **6 个模块 / 20 个符号**降到 **4 个模块 / 16 个**，
`renderers/_late.py` 的登记项随之缩小。**对手方**：搬完之后
`tools/check_import_graph.py` 的借用清单必须同步缩水（陈旧 → 红）。

**C'''''''4 让「判据条数」进棘轮（R44 C''''7 / 未做）。**
`check_import_graph.py` 现有 G1–G6 六条判据、14 条自证样本，但**没有一条断言**
阻止以后有人删掉 G3 而不改数字。落点：把「静态判据条数」与 `SELFTEST COUNTS`
的**下界**一起做成只许增的快照。**对手方**：删掉 G3 → 红。

**C'''''''5 把 G1 从「模块级」推广到「符号级」。**
`from matlabc import X` 里的 `X` 是否真的存在，目前只在
`tests/test_matlabc.py::test_renderers_import_smoke` 里查（要 import 产品）。
落点：静态门直接拿 `ast` 比对「被导入的名字」与「目标模块的顶层定义」，秒级。
**对手方**：`from matlabc import 不存在的名字` → 红。

**C'''''''6 把 R52 的行为保持装置固化进仓库。**
`_r52/capture_behavior.py`（110 产物 + 7 命令 × 3 次可重复）目前只活在仓库外。
落点：`tools/check_behavior_identity.py`，固定语料（`git ls-files` 的 `tests/sample_m`）
+ 固定命令集 + 遮蔽墙钟，秒级。**对手方**：改一行渲染逻辑 → 产物哈希变化 → 红
（**故意**比测试集更敏感）。

**C'''''''7（沿用 R51 C‌''''''7 / C‌''''''8）把 B5 文档同源表推广到 `CONTRIBUTING.md`
与 `docs/matlabc_USAGE.md`；并给「诚实的边界」加内容侧对手方。**

---

## §9 明确拒绝做的事（避免下一轮走回头路）

1. **不为过门而放宽判据。** 冒烟测试的断言从「renderers 模块有这些属性」改成
   「`_mL.` 借用的每个名字都存在于 matlabc」是**接口变更后的等价升级**
   （自动派生、覆盖面更大），不是放宽；本轮的 `HELP_BYTES_SNAPSHOT` 也**没有**动
   （「11 道」→「12 道」等长）。
2. **不用 PEP 562 的模块级 `__getattr__`** —— 那是 3.7+，本仓承诺 3.6.5。
3. **不用 `sys.modules` 魔法 / 不用 import hook**：`_late.py` 里的
   `importlib.import_module` 是**唯一**一处动态导入，且被 G3 登记。
4. **不整行正则改写代码**：`sarif.py` 的 docstring 与 `snapshot.py` 的字符串里
   都有这些名字；改写走 `ast` 字节列偏移。
5. **不动 `VERSION`**：它仍是 `matlabc.py` 的源码常量，本轮只把**读取时机**推迟。
6. **不做「注释式」单一事实源**：登记表必须两向核对，写错就红。
7. **本轮不碰 `flow/diagrams`**（R45–R48 已完成、暂不推进）。
