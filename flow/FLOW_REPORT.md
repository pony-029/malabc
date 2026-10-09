# FLOW_REPORT —— malabc 全部流程图的逐张详解

> 生成方式：**archify**（`D:\project\archify`，skill 3.0.1）把 21 个 mermaid 块重绘为**可交互的独立
> HTML**；方法论用 **superpower 六顶思考帽 + 隔离探针**（见 `E:\matlabc\_r45\`）。
> 本文只写**定稿之后实测到的数字**——所有计数都取自实际文件，不抄旧文档。

## 0. 这一轮到底做了什么

| 步骤 | 做法 | 实测结果 |
| --- | --- | --- |
| 普查 | 全仓扫 `.md/.mmd/.mermaid` 里的 ```` ```mermaid ```` 块 | **21** 个块 → `FLOW_CENSUS.json` |
| 导出 | 逐字节导出（**含 CRLF 行尾也一致**，21/21 已断言通过） | 21 个 `source/*.mmd` + `source/INDEX.md` |
| 去重 | 8 对是 EN/CN 镜像（同构、标签语言不同） | **13** 张不同的图 |
| 重绘 | 每张图选一个 archify 图型，写 `candidate.json` | 13 个 candidate |
| 渲染 | `archify render <type> … --quality showcase` | 13 张图 × 中英两版 = **26** 个 HTML，rc 全 0；英文合计 **9,854,186** 字节、中文合计 **9,845,424** 字节（F12 修正数字后重渲染的最终值） |
| 中文版 | 复制英文候选、只换字符串，再断言「清空所有字符串后结构逐键逐序相同」 | 13 个 `candidate.zh-CN.json`，**450** 条译文 |
| 映射 | 源图 ↔ archify 图，双向往返都要能对上 | `FLOW_INDEX.json` / `INDEX.md`（由脚本断言生成） |

**13 张图的分工**

| 图型 | 张数 | 图号 |
| --- | --- | --- |
| `architecture` | **5** | F01 F02 F04 F05 F12 |
| `workflow` | **6** | F03 F06 F07 F08 F10 F11 |
| `lifecycle` | **2** | F09 F13 |
| `dataflow` | 0 | 试过，见 §0.1 |

> 精确的逐图节点/连线计数见 `INDEX.md`。上表按**最终选定的图型**分：
> F02 由源图型 `flowchart` 改判为 `architecture`，理由写在 §0.1。

### 0.1 为什么有两张图「换了图型」

源文档用 `flowchart` 画了一切，但 `flowchart` 只是画法，不是语义。archify 的图型带着各自的
**布局契约与校验器**，换型等于换一套自动检查：

- **F01**（`mindmap` → `architecture`）：思维导图没有方向、没有连线语义；能力地图需要「一个内核 + 七块能力」的归属关系。
- **F02**（`flowchart LR` → `architecture`）：这是一张**数据/证据流**图。先试了 `dataflow`（图型语义最贴），
  但 `dataflow` 的 `stage/row` 网格把「源侧证据」与「容器里抽出来的证据」放在同一列时，
  `s1 → at` 这条**跨级长边**必然穿过同排节点；校验器三次都报 `edge-through-node` 与
  `label-overlaps-node`。改判为 `architecture` 后，坐标由作者掌握，一次通过。
  **这是「用测量决定画法」，不是「为了过校验而改图」。**
- **F04 / F05 / F12**（`flowchart TB/LR` → `architecture`）：分层、扇入、扇出，都是静态结构。
- **F09 / F13**（`flowchart` → `lifecycle`）：两者本质是**状态机**（有返回边、有终态、有 tier）。
  `lifecycle` 的契约会强制「可恢复的失败必须有一条真的返回边」——恰好是这两张图要讲的事。
- **F10 / F11**（`graph/flowchart` → `workflow`）：有泳道（谁在做）、有阶段、有判定边。

---

## 1. F01 —— 能力地图（`architecture`）

- **源**：`README.md` L55–97 `mindmap`（`README_CN.md` L49–91 镜像）
- **产物**：[`f01-capabilities.html`](archify/architecture-malabc-capabilities-20261009-2215/f01-capabilities.html)
- **问题**：*这个工具由哪几块能力组成？*

**节点（8）**：`core`（matlabc · single-file analyzer kernel）+ 7 块能力
`Structure Mapping` / `Interactive Site` / `Static Checks` / `Metrics & Governance` /
`Fix Loop` / `CI Gate` / `Binary & GPU`。

**连线（7）**：全部是 `core → 能力`，`fromSide: right → toSide: left`，**没有标签**。
无标签是刻意的：`from` 是内核、`to` 是能力块，方向与归属已被两端说尽；加标签只会挤占走廊。

**说明卡（7）**：一张卡对应一块能力，逐条列出源码里的具体项（如 Static Checks 列出
uninitialized / type / dead code / shape / cross-file taint）。

**这张图证明**：能力是**并列**的七块，共同挂在一个内核上；不证明它们之间有调用关系——
源 `mindmap` 本来也没有。

**做这张图时的一个真实教训**：第一版按「组 + 叶子」画了 39 个节点，被校验器当面否掉——
9 条 `Label "…" is wider than component`、大量 `clean-flow/edge-through-node`（2px 净空）
与 `composition/ambiguous-corridor`。**是测量把设计退回来的**，不是审美偏好。

---

## 2. F02 —— 三态归因（`architecture`）

- **源**：`README.md` L117–138 `flowchart LR`（CN L110–131）
- **产物**：[`f02-binary-attribution.html`](archify/architecture-binary-attribution-20261009-2340/f02-binary-attribution.html)
- **问题**：*一个名字为什么被判成 unresolved？三态各由什么证据支持？*

**节点（9）**

| 节点 | 角色 | 事实来源 |
| --- | --- | --- |
| `unresolved call sites` | 源侧输入 | `matlabc myproj --json out.json` 的输出键 |
| `library file` | 容器入口 | PE / ELF / Mach-O 三类容器 |
| `dynamic dependencies` | 抽出的证据 1 | DT_NEEDED / import table |
| `export symbols` | 抽出的证据 2 | dynsym / export directory |
| `embedded GPU content` | 抽出的证据 3 | CUDA fatbin · AMD HSA · Vulkan SPIR-V |
| `attribution engine` | 判定点 | `binfmt/attribute.py` |
| `library:` / `gpu_kernel:` / `missing:` | 三态结论 | 归因结果的三个前缀 |

**连线（10）**：`s1→at`（源侧）；`b1→b2→b3→b4`（容器内逐层抽取，垂直链）；
`b2/b3/b4→at`（三路证据汇入判定点）；`at→r1/r2/r3`（判定点扇出三个结论）。

**关键取舍**：`b1→b2→b3→b4` 画成**垂直链**。源图画的是 `B1-->B2 & B3 & B4`（扇出），
但扇出到同一列的三行会被校验器判为「贴着容器边框走」或「共享走廊」。改成链之前，
先把事实确认清楚：`attribute.py` 确实是先读容器、再读依赖表、再读符号表、最后扫 GPU 段。
**链是执行顺序，不是依赖关系**——这一点写进说明卡，避免读者误读。

**这张图证明**：三态是**穷尽且互斥**的；`missing` 是一个**结论**，不是「还没做」。
**不证明**：没在命令行给出的二进制会被「猜到」——恰恰相反，说明卡写死了
「没给的保持 missing，假阳性比不归因更糟」。

---

## 3. F03 —— 一条命令代替两条（`workflow`）

- **源**：`README.md` L195–206（CN L184–195）
- **产物**：[`f03-binary-attach.html`](archify/workflow-binary-attach-20261009-2310/f03-binary-attach.html)
- **问题**：*`--binary-attach` 到底省了什么？*

两条泳道：`--binary + --binary-symbols · two steps`（`t1 → t2 → t3`，中间落一个 `out.json`）
与 `--binary-attach · one step`（`o1 → o2`）。5 节点 3 连线。

**这张图证明**：省掉的是**中间快照文件与第二次命令**，不是省掉了归因本身。
说明卡同时钉住两条「不会变」：两条路写的是同一个 JSON 键 `unresolved_attribution`；
`--binary`（短路）与 `--binary-attach`（不短路）**永远是两个开关，不许合并**。

---

## 4. F04 —— 单文件五层内核（`architecture`）

- **源**：`README.md` L261–295（CN L247–281）
- **产物**：[`f04-layers.html`](archify/architecture-malabc-layers-20261009-2340/f04-layers.html)
- **问题**：*单文件内核内部分了哪几层？输入与输出各是什么？*

**节点（10）**：入口层（`matlabc_boot.py` 路由 CLI/ask/flow/GUI）、两个输入
（工程目录 / `analyzer_config.json` 或 `--from-json` 快照）、内核五层
`Lexical → Parser → Data → Analysis → Render`、输出层（五族产物）、CI 门（exit 0/1）。

**连线（9）**：`entry→b1`、`in_src→b1`、`in_cfg→b4`（**配置直插分析层，不经过词法/解析**——
这正是 `--from-json` 的语义）、`b1→b2→b3→b4→b5`、`b5→out`、`out→ci`。

**做这张图时踩到的真实坑**：最初给五层加了一个 `region`（区域框，标签「single-file layered
kernel」）。校验器立刻报 `composition/container-border-run`：`in_src → b1` 这条边
**沿着区域上边框走了 543px**。我先把行距拉大一倍——**仍然贴着边框**（它取的是 `border − 4`）。
结论：这不是间距问题，是「源与目标的水平投影不重叠」这一事实的必然结果。
于是**去掉区域框**，把「单文件」这件事交给标题、副标题与说明卡。**去掉的是装饰，不是事实。**

**说明卡**说清了三件内核事实：五层各自的代表函数；为什么是单文件（零第三方依赖、
只用标准库、3.6.5 就能跑）；五族产物各自是什么。

---

## 5. F05 —— 唯一判定点（`architecture`）

- **源**：`README.md` L338–348（CN L324–334）
- **产物**：[`f05-decision-point.html`](archify/architecture-single-decision-point-20261009-2340/f05-decision-point.html)
- **问题**：*「解析不到的调用」究竟在哪里被判定？*

**节点（9）**：C / Py / JS / MATLAB 四个前端；判定点 `frontends/ir.py · resolve_calls()`；
输出 `edges → call graph` 与 `unresolved`；下游「possibly missed 页」与 `--binary-attach`。

**连线（8）**：`cf/pf/jf → rc`（三路汇入）；**`mf → u`（MATLAB 直连 unresolved，绕过 rc）**；
`rc→e`、`rc→u`、`u→rp`、`u→at`。

**这张图证明**：收拢之后，**「哪个调用解析不到」只有一个判定点**；
同时诚实地画出**那个例外**——`frontends/matlab.py::unresolved_tuples()` 仍是独立模块。

**说明卡**交代了三条硬约束：① 收拢前同一规则被抄了**五遍**；② `build_ir` 是 `unresolved`
的**唯一写入点**；③ MATLAB 那条路**必须保持旧插入顺序**，否则 `Counter.most_common()`
的并列次序会静默改变。

---

## 6. F06 —— 修复闭环（`workflow`）

- **源**：`README.md` L400–407（CN L385–392）
- **产物**：[`f06-fix-loop.html`](archify/workflow-fix-loop-20261009-2310/f06-fix-loop.html)
- **问题**：*五步是什么？失败回哪一步？*

`review → fix → apply → verify → report`，外加一条 `verify ⤏ fix` 的**虚线错误边**（`role: error`）。

**这张图证明**：**verify 是回退点**，不是终点。说明卡写明 apply 走
「`git apply` 或严格进程内校验」，verify 的标准是「重扫之后没有任何规则报得更多」——
也就是**没有新告警**，而不是「补丁长得对」。

---

## 7. F07 —— CI 退出码门（`workflow`）

- **源**：`README.md` L447–454（CN L431–438）
- **产物**：[`f07-ci-gate.html`](archify/workflow-ci-gate-20261009-2310/f07-ci-gate.html)
- **问题**：*退出码怎么算出来的？*

三泳道（Repository / matlabc in the CI job / Gate outcome）。节点
`push → diff → sarif → decide`，判定后分叉到 `exit 1`（**新告警增加**）与 `exit 0`（**没有增加**）。

**做这张图时的机械修**：`exit 1` 与 `exit 0` 初版同列同泳道，校验器报
`workflow/node-overlap`「相距不到 8px」，并直接给出可用列号。按它给的列号改，一次通过。
**校验器的报错本身就带修法**——这是这个工具值得用的原因之一。

**说明卡**钉住：退出码是**公开接口**（0 通过 / 1 失败）；基线是自动持久化的，
所以一次 PR 不需要人再传参数。

---

## 8. F08 —— 基线门比集合（`workflow`）

- **源**：`README.md` L560–568（CN L543–551）
- **产物**：[`f08-baseline-nodeids.html`](archify/workflow-baseline-nodeids-20261009-2310/f08-baseline-nodeids.html)
- **问题**：*为什么比集合而不是比个数？*

`HEAD tree → pytest -q` 与 `working tree → pytest -q` 两路，汇入 `nodeid set difference`，
再分流为 `regressions → RED` 与 `fixed / renamed → informational`。

**这张图证明**：单纯比个数会**藏住一次改名**——走一个、来一个，总数不变。
说明卡给出了这条判据的来源（R37 定的契约），并注明**成本被刻意分离**：
默认模式是秒级（前置条件 + 门自身的两向自证），`--full` 才真跑两棵树（约 11 分钟），
**绝不进 `check_all` 的默认路径**。

---

## 9. F09 —— 方法论闭环（`lifecycle`）

- **源**：`docs/SUPERPOWER_REVIEW_R30.md` L24–36
- **产物**：[`f09-superpower-loop.html`](archify/lifecycle-superpower-loop-20261009-2340/f09-superpower-loop.html)
- **问题**：*一轮怎么走？探针不通过时回哪一步？*

两泳道（`main` 主路径 / `rework` 返回通道）。5 个主状态：
`六顶思考帽 → C1–C10 真落地 → 隔离探针 → 登记制护栏 → 全量回归 + 下一轮`；
外加一个 `rework` 状态承接「探针不通过」。

**连线（7）**：`a→b→c→d→e`；`c→d` 标 `both pass`；`c→rw` 标 `one way fails`（security）；
`rw→b` 标 `rework`（dashed，**真的返回边**）；`e→a` 标 `next round`（走顶部通道）。

**这张图证明**：**探针在护栏之前**。说明卡写明原因——「凭猜测写的护栏会把猜测冻住」，
以及本轮反复验证过的那条：「测量工具自身的 bug 会伪造出被测对象的 bug」。

---

## 10. F10 —— 登记制护栏（`workflow`）

- **源**：`docs/SUPERPOWER_REVIEW_R30.md` L176–189
- **产物**：[`f10-guard-registry.html`](archify/workflow-guard-registry-20261009-2340/f10-guard-registry.html)
- **问题**：*护栏怎么被「登记」进测试与 CI？*

四泳道（runner / guards / collect / ci）。`check_all.py` → 三道具名护栏
（`check_patch_ops.py` / `check_doc_flags.py` / `check_operator_impl.py`）→ `test_matlabc.py` → CI。

**这张图刻意改过画法**：源图是 `G4 → G1 & G2 & G3` 的扇出，但 archify 的官方示例里，
凡是「一个源扇出到同泳道多个目标」的边，都会被校验器判为 `ambiguous-corridor`
与 `proper-crossing`。实测确认后，改成**同泳道相邻列的链**，
并把事实写进第一句标签：**`runs each guard in order`**（`check_all` 确实是**按序执行**的）。
**改的是画法，不是事实**——三个护栏依旧是并列的兄弟，只是用「按序执行」来表达。

**说明卡**给出三条判据：护栏表就在每个 `check_*.py` 顶部；测试断言的是**道数**
（加文件不算数，必须登记）；**陈旧登记也红**（登记了却不存在，与漏登记一样是红的）。

**本轮实测到的当前值**：`tools/` 下 `check_*.py` 共 **11** 个；
`check_all.py` 里 `MIN_GUARDS == 10`（`check_all` 自己不算一道门）。

---

## 11. F11 —— 唯一判定点 + 六条变异判据（`workflow`）

- **源**：`docs/SUPERPOWER_REVIEW_R44.md` L182–200
- **产物**：[`f11-ir-attribution.html`](archify/workflow-ir-attribution-20261009-2340/f11-ir-attribution.html)
- **问题**：*收拢之后，用什么挡住它再次扩散？*

三泳道。6 节点 5 连线：`rc`（the ONE decision point）→ `edges → call graph` / `unresolved`；
`frontends/matlab.py` **虚线**汇入 `unresolved`；`unresolved → possibly missed 页` / `--binary-attach`。

**这张图证明**：收拢后的拓扑（含那个例外），以及 `build_ir 写它，且只写一次`。
说明卡把**六条变异 → 各自必须命中的判据**逐条列出（I1 / I5 / I4 / I1b / I6 前向 / I6 反向），
并专门解释**为什么需要 I1b**：只看「写点集合」时，一种「保留共享调用、又顺手内联 append」
的改法会隐形；而第一次红路探针里这条变异被 I5 抓住而不是 I1b，
说明 **I1b 当时没有独立证人**——于是补了第四条变异。这是本轮最值钱的一条方法论。

---

## 12. F12 —— 仓库真实分层（`architecture`）

- **源**：`docs/analysis/ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT.md` L72–107
- **产物**：[`f12-audit-layers.html`](archify/architecture-audit-layers-20261009-2340/f12-audit-layers.html)
- **问题**：*仓库的真实分层是什么？那条循环依赖在哪？*

**16 节点 20 连线**，是本批最大的一张图：

| 层 | 节点 |
| --- | --- |
| 入口/分发 | `matlabc_boot.py`、`matlabc_mcp.py` |
| 四个入口 | `matlabc.py · CLI`、`matlabc_ask.py`、`matlabc_flow.py`、`gui.py · tkinter` |
| AI / Agent | `ai_cli.py · agent_loop.py · analyzer_memory.py`、`working copy` |
| 内核五层 | `Lexical → Parser → Data → Analysis → Render` |
| 渲染层 | `assets.py`、`snapshot / report`、`sarif / metrics` |

**连线**：`boot→四个入口`；**`mcp → CLI/ask/flow` 三条虚线**（stdio 子进程）；
四个入口→内核；内核五层链；`Render → 三个渲染模块`（虚线，且**另有一条 `matlabc.py ← renderers/` 的回边事实写在卡里**）；
`flow → AI/Agent`（security 色）；`AI/Agent → working copy`。

### 12.1 本轮在这里抓到一个**真缺陷：陈旧数字**

源审计文档写于 2026-10-08，它给出的规模数字**今天已经不对**。逐项实测：

| 审计文档（2026-10-08） | 今天实测（2026-10-09） | 结论 |
| --- | --- | --- |
| `matlabc.py` 29,637 行 | **30,875** 行 | 已增长 |
| `main()` 906 语句 / 518 函数 | **923** 语句 / 文件内 **635** 函数 | 已增长 |
| `gui.py` 1,090 行 | **1,200** 行 | 已增长 |
| `renderers/` 26 文件 7,510 行 | **11** 个 `.py` / **5,918** 行 | **口径不同且已变化** |
| `agent_loop.py` 620 行 | **671** 行 | 已增长 |
| `renderers/assets.py` 3,826 行 | **3,825** 行 | ≈ 未变（差 1 是口径差） |

> **计数口径必须先定，再比数**：本节一律用**换行符个数**（等价于 `wc -l`）。
> 本轮初版在这里犯过一次**系统性 +1** 的错：当时用 `text.split("\n")` 计数，末尾换行被当成额外一行，
> 于是 `matlabc.py`/`gui.py`/`agent_loop.py`/`renderers/` 全都被多算。复测时两种口径
> （数 `\n` / `readlines()`）对四个文件**完全一致**，且四个文件都以换行结尾 ——
> 所以那个 +1 只可能是口径错，不可能是内容差。**数字错一次不要紧；口径不说清才致命。**

**处理方式**：把 F12 的 candidate 里三处陈旧数字改成实测值并**重渲染**，
审计文档本身**不动**（它是历史快照），但在本文里留下对照表。
这正是「报告里的数字必须来自定稿之后的最后一次测量」这条纪律的又一次兑现。

另外**两个都带区域框的尝试也被测量否掉**：`renderers/ · 26 files, 7,510 lines` 这个
区域框让 `b5→r2` 沿着它的上边框走了 558px。**去掉区域框**——顺带把那句已经过时的
「26 files, 7,510 lines」也从图里清掉了。

---

## 13. F13 —— `agent_loop.py` 状态机（`lifecycle`）

- **源**：`docs/analysis/ANALYSIS_2026-10-08_MALABC_DEEP_AUDIT.md` L189–208
- **产物**：[`f13-agent-loop.html`](archify/lifecycle-agent-loop-20261009-2340/f13-agent-loop.html)
- **问题**：*怎么保证不留下「改了一半的树」？*

**14 个状态、4 条泳道**（`main` / `apply gate` / `rollback + feedback` / `exits`）、**14 条转移**。

主路径：`Baseline analysis → total == 0? → Attempt loop → fix_source() → Rescan and verify`。
门与回退：`git apply --check`（apply 泳道）；`feedback: apply_rejected` 与 `Rollback`
（recovery 泳道）各自**真的返回** `Attempt loop`。
出口：`already_clean` / `max_turns exhausted` / `no_strategy` / `accept` / `review_gate`。

**这张图证明**三件事：① **每个补丁过两道独立闸**（前 `git apply --check`、后重扫验证）；
② **循环有界**（`max_turns` 耗尽是一个**正常上报的结论** tier 2，还会出检查点与可选 Draft PR）；
③ **不留半成品**（验证失败用 `git apply -R` 或进程内快照还原；`review_gate` 会回退后
以 `exit 3` 出审查产物）。

**做这张图时的机械约束**：`lifecycle` 的 `lanes` **上限是 4**、`col` **上限是 4**。
第一版排了 5 条泳道，schema 直接拒收（`/lanes must NOT have more than 4 items`）；
把 `mem` 融进 `accept` 的副标题后降到 4 条。**是 schema 在管人，不是人在猜 schema。**

---

## 14. 这批图之外，本轮还测出来的三件事

这三条都属于「**工具/环境的事实**」，会影响后续任何一次重绘，必须记下来。

### 14.1 本机 archify 的 `finalize` 用不了，`render` 可以

`archify finalize` = 校验 → 交付 → 检查 → **浏览器检查**。它需要
`spawnSync` 起子进程（渲染器进程、浏览器）。本机 Node **无法 spawn 任何子进程**——
`probe_spawn.mjs` 连 `node -v`（Node 自己 spawn 自己）都返回 `EBUSY`。所以：

- `finalize` / `browser-check` / `visual-check`：**本机不可用**（不是配置错，是环境限制）；
- `render`：**可用**，它做的是**进程内**布局校验 + 落盘，本文 13 张图全部由它产出，rc 全 0。

### 14.2 本机「删除」是**回收站语义**，会打破 archify 的 `nlink` 不变量

实测（`fsutil hardlink list`）：`os.remove` / `fs.unlinkSync` / 先改名再删，**一律被改成移动到
`E:\$RECYCLE.BIN`**，inode 保留。于是 archify 那条「硬链接 + 删原名」的原子写，
会留下 `nlink=2` 的产物，触发 `[output/target-hardlinked]`。

**处理方式（必须如实披露）**：在**仓库外的临时副本** `_r45\archify-probe\` 上做了最小
host-compat 补丁——把发布步骤从「硬链接」换成**同卷 `renameSync`**，
并把「恰好 1 个链接名」放宽为「至少 1 个」。**只放宽上界，不放宽下界**；
`demo` / `render` 均 rc=0 且产物 `nlink=1`。
**原仓库 `D:\project\archify` 一个字节都没有改。**

### 14.3 源图的 8 对镜像必须一起改

`README.md` 与 `README_CN.md` 的 8 张图是同构镜像。`check_readme_parity.py` 的 P2
**逐节比对表行数 / 代码块数 / mermaid 数**，所以任何一侧的增删都必须成对发生。
本文新增的小节因此在两侧**同位置、同结构**插入。

### 14.4 中文版：同一份骨架，两套文字

archify 的 `SUPPORTED_LOCALES` 是 **`['en', 'zh-CN']`**，所以中文版的 locale 标签是 **`zh-CN`**。
写 `zh` **不会报错**，但会被**静默回退**成英文外壳 —— 这正是 `i18n/locale-fallback` 那条警告在提醒的事，
所以「标签写对」本身就是一个必须实测的点。

`meta.locale` 只管**查看器外壳**（`<html lang>`、图例默认词、工具栏、底部说明）；**作者侧的文字必须自己译**。
于是 13 张图各有两份候选：

| | 文件 | locale | 产物 |
| --- | --- | --- | --- |
| 英文 | `candidate.json` | `en` | `f*.html` |
| 中文 | `candidate.zh-CN.json` | `zh-CN` | `f*.zh-CN.html` |

中文候选**不是手写的**：`_r45/make_zh_candidates.py` 复制英文候选、只替换字符串，然后断言
**「把两份文件里所有字符串都清空后，剩下的结构必须逐键逐序完全相同」**（`skeleton(en) == skeleton(zh)`）。
这一条同时锁住了：节点 id 与顺序、坐标与尺寸、`variant` / `role` / `fromSide`、说明卡数量与条目数。
机器换不出来的只有译文本身（450 条），其余一律不许动 —— **译文可以错，结构不许漂**。

中文标签更短（`结构映射` 对 `Structure Mapping`），而 archify 的测宽把 CJK 按 **2 倍进宽**计
（`utils.mjs` 的 `FULLWIDTH_RE`），所以不存在「中文塞不下」的问题：实测 13 张图 `render` 全 rc=0，
**没有一张需要调列号或改宽度**。

**行尾的另一半**：中文候选是手写物 → CRLF；中文 HTML 是生成物 → 保留渲染器原始字节（LF）。
`_r45/render_zh.py` 对每张中文图**连渲两次并逐字节比对**（13/13 相同），并断言产物里有
`<html lang="zh-CN"`、有汉字、且**不含 CRLF**。

---

## 15. 怎么重新生成

```bash
# 1) 普查 + 导出（仓库外脚本，只读仓库）
python E:/matlabc/_r45/census_flow.py
python E:/matlabc/_r45/scaffold_flow.py

# 2) 生成索引（会断言：每个导出都必须能对上一张图，缺一即失败）
python E:/matlabc/_r45/gen_flow_index.py

# 3) 重绘任意一张（以 F01 为例）
cd /e/matlabc/malabc/flow
node E:/matlabc/_r45/archify-probe/bin/archify.mjs render architecture \
  archify/architecture-malabc-capabilities-20261009-2215/candidate.json \
  archify/architecture-malabc-capabilities-20261009-2215/f01-capabilities.html \
  --quality showcase

# 4) 中文版：先由英文候选生成中文候选，再渲染
python E:/matlabc/_r45/make_zh_candidates.py    # 结构不变式在这里断言
python E:/matlabc/_r45/render_zh.py             # 26 张图一起跑，含逐字节可重复性断言
```

**纪律一**：改图只能改 `candidate.json` 再重渲染，**不要手改 HTML**；
改源文档的 mermaid 之后必须**重新导出** `source/*.mmd`，否则两边会静默分叉。

**纪律二（行尾分两类）**：

- `.html` 是**生成物**，仓库里保存的就是渲染器**原始输出**的字节（LF）。
  这样「重跑一次 `render` == 仓库里的文件」才是一个**可验证的等式**：
  `_r45/rerender_flow.py` 对 13 张图各渲染两次并逐字节比对，13/13 相同。
  若把 HTML 改成 CRLF，这个等式就只剩「差一轮行尾归一」，是更弱的说法。
- `.md` / `.json` / `.mmd` 是**手写物**，遵守仓库约定（blob 全 CRLF、`core.autocrlf=false`）；
  `_r45/normalize_flow_eol.py` 断言它们的 `bare_lf` 全为 0。

---

## 16. 下一步（建设性意见）

1. **把「图」纳入 CI 一致性检查**：现在 `source/*.mmd` 与源文档是**人工同步**的。
   建议加一道 `tools/check_flow_sync.py`：重新跑一次普查，与 `FLOW_CENSUS.json` 逐字节比对，
   不一致就红。判据要**两向**：源文档有块而 census 没有 → 红；census 有块而源文档没有 → 也红。
2. **F02 的 `dataflow` 版本值得再试一次**：失败原因是跨级长边。若先测出
   `dataflow` 求解器对 `stage/row` 的坐标公式（`validate --layout-json` 能打印），
   就能用 `channelY` 精确指定那条走廊，而不是换图型规避。**这是把「规避」升级为「掌握」。**
3. **`docs/analysis/ANALYSIS_2026-10-08_*` 需要一个「数字有效期」标记**。§12.1 的对照表说明：
   一份带着大量精确数字的历史文档，半年后会静默变成错误信息源。
   建议在文档头加 `<!-- numbers-measured: 2026-10-08 -->`，并由
   `check_doc_flags` 之类的一致性门在数字被引用时提示「对不上当前值」。
4. **`renderers/` 的循环依赖**（`matlabc.py ↔ renderers/`，靠模块尾部 import 规避）是 F12
   上唯一标红的结构性债务，也是「已达不可维护线」的那一处。打断它应该是下一轮的主攻方向。
5. **26 张 HTML 合计 19.70 MB**（英文 13 张 9,854,186 字节 + 中文 13 张 9,845,424 字节），
   其中约 **750 KB × 26** 是**同一份 viewer 运行时**的重复。若这个目录要长期增长，
   应该抽出共享运行时或改为按需生成，而不是让仓库无限变胖。
6. **给「图里的数字」也上一道门**：§12.1 那次系统性 +1 说明，**图里的数字和文档里的数字一样会腐坏**。
   建议把 `FLOW_REPORT.md` / `INDEX.md` / 两张 README 里出现的**文件行数**统一到一个由脚本测量的来源
   （例如 `flow/FLOW_METRICS.json`，且必须带**计数口径**字段），再在 `tools/check_*.py` 里比对。
   判据要两向：**数字不符 → 红；声明了却不存在的指标 → 也红**。
