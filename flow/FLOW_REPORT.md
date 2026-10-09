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

### 0.2 R47 加的一步：把图从产物里「取出来」，直接嵌进 README

上面 13 张图原本只以**可交互 HTML** 存在 —— README 里只有「点得开的链接」，
读者要看到图必须先打开一个约 750 KB 的页面。R47 把图**取出来**做成独立 SVG，
直接嵌进两份 README（方法、三个量测陷阱、以及那 58 处具名差异见 §14.5，图册见 §14.6）。
多出来的是一条**可重跑的四步链路**，每一步都有实测数字：

| 步骤 | 做法 | 实测结果 |
| --- | --- | --- |
| 提取 | 调 archify **自己的** `serializeSvg()`（不是截图、也不是重画一遍） | 26 个 `flow/diagrams/*.svg`，合计 **3,997,289** 字节 |
| 校验 | 同文档三臂比对（REF / shadow / lightDOM），29 个计算属性 × 2,910 个元素 | **84,390** 次比对，0 处解释不了的差异、0 处 bbox 差、0 处文本长度差 |
| 嵌入 | 两份 README 各嵌 13 张，位置与结构对称，点图打开同语种的交互产物 | 两侧 **15** 个小节仍逐节对等（`check_readme_parity` 的 P1/P2 全绿） |
| 守门 | `tools/check_flow_diagrams.py`，**D1–D9，每一对都双向** | 22 个反例全抓 / 真实仓库 **0** 项不对齐 |

顺带：`flow/INDEX.md` 与 `FLOW_INDEX.json` 也登记了这 26 个 SVG 的路径与字节数，
而**索引自己也被 D9 钉住** —— 漏登记、体积漂移、登记了磁盘上没有的文件，三种都红。

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

## 14. 这批图之外，本轮还做出来的装置与实测到的事实

下面这些都属于「**工具 / 环境 / 装置的事实**」，会影响后续任何一次重绘，必须记下来。这三条都属于「**工具/环境的事实**」，会影响后续任何一次重绘，必须记下来。

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

### 14.5 独立 SVG：把产物里那张图「取出来」，而不是「截出来」

README 里要直接看得见图，就得有**静态图**。栅格截图（PNG）会丢掉矢量、体积大、且和源脱钩；
而**图本身就是 SVG** —— 每张的标记只有 2 万字符左右。所以做法是**取** SVG，不是截。

`archify` 自己就有这个装置：`viewer/export.js` 的 `serializeSvg(scale, opts)` ——
克隆 `.diagram-container svg`、只保留 SVG 相关 CSS 规则、把主题变量**解析成真值**、
内联字体字节、补一张背景 rect。但它**在闭包里，没有暴露**；CLI 也没有 svg 子命令
（`archify --help` 只有 render/compare/deliver/finalize/preview/validate/migrate/inspect/check/…），
而 `browser-check` / `visual-check` / `finalize` 在本机**不可用**（Node 无法 spawn，见 14.1）。

于是 `_r47/extract_svg.py` 绕了一圈，但**没有重写它**：把产物复制到仓库外临时目录 →
在**同一闭包作用域内**插一行 `window.__archifySerialize = serializeSvg;`
（函数声明会提升，插在定义之前也取得到，**原声明一个字不动**）→ 在 `</body>` 前追加 harness，
调它、把结果 **base64** 回传 → 无头浏览器 `--dump-dom` 取回。
用 base64 有两个好处：dump 出来的 DOM 里**不含 `<`**（不会被 HTML 解析器改写），
且取回来的字节可以逐字节校验。
**仓库里的 `.html` 与 `D:\project\archify` 都是零改动。**

两个开关是**按失败模式选的**，不是按好不好看：

| 开关 | 取值 | 为什么是它 |
| --- | --- | --- |
| `autoTheme` | `true` | 双主题（深色为底，浅色走 `prefers-color-scheme`）。万一番主不认这个媒体查询，它会退回**深色底 + 自带背景**，最坏是「浅色页面上多一块深色卡片」；若锁成浅色，最坏是「深色页面上深色文字 = 看不见」。**前者可用，后者不可用** —— 按最坏情况选，不按最优情况选。 |
| `figure` | `true` | 让导出把 `.diagram-container > svg` 那批规则**改写到 `svg` 上**。不开会实测丢两样：`[data-edge-from]` 的 round 线帽/拐角，以及 `[data-node-id] > rect` 的 drop-shadow（节点「浮起来」的那层投影）。f01 实测 8 处 `filter` + 7 处 `linecap/linejoin` 不一致。 |

背景**不受** `figure` 影响：`autoTheme` 分支注入的 `rect.c-bg-rect { fill: var(--bg); }`
是一条 **CSS 规则**，优先级高于 `figure` 那句 `setAttribute('fill','none')` ——
实测背景仍是 `rgb(244,245,247)`（浅色 `--bg`），不是透明。

#### 怎么证明「取出来的 == 产物里那张」（`_r47/verify_svg.py`）

把**产物自己的渲染路径**和**独立 SVG 的渲染路径**放进**同一个文档**里逐元素比：

- **REF 支**：产物原样的 `<svg>` 放回 `.diagram-container`，页面照搬产物的两张 `<style>`
  与 `<html>` / 容器的属性 —— 这就是产物自己的渲染路径；
- **CAND 支**：独立 SVG 放进 **shadow root**（宿主的 CSS 一条也匹配不进来），
  所以它看到的只有自己身上那份 —— 这正是它被单独打开时的渲染路径；
- 比 **29 个计算属性 × 2910 个元素**，外加 `getBBox()` 与 `getComputedTextLength()`。

##### 三处**测量装置自己的坑**（都是先红了才修好的，记下来免得重踩）

1. **主题必须先对齐。** 产物的 `<html data-theme="dark">` 是**钉死的**，而 `autoTheme` 的独立 SVG
   跟随浏览器偏好 —— 无头 Chromium 报的是 **light**。首轮没对齐，f01 直接 139 处不一致，
   全是 `fill`/`stroke`/`color`（深色值 vs 浅色值），看上去像「CSS 过滤漏了规则」，
   其实是**两边在比两个主题**。
2. **缩放比必须先钉到 1:1。** 产物里的 `<svg>` 没有 `width`/`height`，尺寸全由查看器布局 CSS 给；
   独立 SVG 的 `width`/`height` 就是 viewBox。两者缩放比不同时，Chromium 会在**设备像素**上
   对字形取整，于是同一段文字在用户坐标里量出的前进宽度会差千分之几
   （首轮 23 条 `getComputedTextLength` 里有 8 条差 0.09~0.17px）。把参考支的宽高钉成 viewBox 后归零。
3. **`@font-face` 的等待不能只看 `document.fonts`。** 本机 `document.fonts.check()` 对
   JetBrains Mono 返回 **false**（`fonts.size=12`，但两棵树都一样地退回后备字体），
   所以又加了一路**光 DOM 副本**（CAND2）做对照 —— 实测 `cand2 vs cand` 全 0，
   证明 shadow root 不是差异来源，把「**环境差异**」和「**SVG 自己的差异**」分开了。

##### 结果

`_r47/verify_all2.txt`：**26/26 全绿** —— 84,390 项属性比对 **0 项不明差异**，
`getBBox` 0 项、`getComputedTextLength` 0 项、结构（元素序列）26/26 完全相同。

另有 **58 项「已披露的差别」**，全部落在 f09（各 11 处）与 f13（各 18 处）的 `opacity` 上：

> 产物初始态是 `data-detail-level="read"`，那条
> `.diagram-container[data-detail-level="read"] svg [data-detail="fine"] { opacity: 0 }`
> 会把**细粒度标注藏起来**（放大才出现）。导出按设计把它们显出来 ——
> 静态图要的正是「完整」，而不是「复刻当前的缩放级别」。

这 58 项**不是从判据里删掉的**：验证器把它**点名并单独计数**（只有 `opacity` 在 `{0,1}` 之间跳、
且元素确实带 `data-detail`，才算这一类）。所以下一轮若出现**新的**差异，它仍然会红 ——
「把一条差异命名并计数」和「把一条差异豁免掉」是两件事。

### 14.6 图册：README 里直接看得见的那 26 张

`flow/diagrams/` 下正好 26 个文件，由 `_r47/extract_svg.py` 从 26 个交互产物里一一取出，
中英成对、骨架同构。两份 README 各嵌 13 张（英文版 / 中文版），点图即可打开对应的交互产物。

| 图 | 英文独立 SVG | 中文独立 SVG | 交互产物 |
| --- | --- | --- | --- |
| `F01` | `f01-capabilities.svg` | `f01-capabilities.zh-CN.svg` | `architecture-malabc-capabilities-20261009-2215/f01-capabilities.html` |
| `F02` | `f02-binary-attribution.svg` | `f02-binary-attribution.zh-CN.svg` | `architecture-binary-attribution-20261009-2340/f02-binary-attribution.html` |
| `F03` | `f03-binary-attach.svg` | `f03-binary-attach.zh-CN.svg` | `workflow-binary-attach-20261009-2310/f03-binary-attach.html` |
| `F04` | `f04-layers.svg` | `f04-layers.zh-CN.svg` | `architecture-malabc-layers-20261009-2340/f04-layers.html` |
| `F05` | `f05-decision-point.svg` | `f05-decision-point.zh-CN.svg` | `architecture-single-decision-point-20261009-2340/f05-decision-point.html` |
| `F06` | `f06-fix-loop.svg` | `f06-fix-loop.zh-CN.svg` | `workflow-fix-loop-20261009-2310/f06-fix-loop.html` |
| `F07` | `f07-ci-gate.svg` | `f07-ci-gate.zh-CN.svg` | `workflow-ci-gate-20261009-2310/f07-ci-gate.html` |
| `F08` | `f08-baseline-nodeids.svg` | `f08-baseline-nodeids.zh-CN.svg` | `workflow-baseline-nodeids-20261009-2310/f08-baseline-nodeids.html` |
| `F09` | `f09-superpower-loop.svg` | `f09-superpower-loop.zh-CN.svg` | `lifecycle-superpower-loop-20261009-2340/f09-superpower-loop.html` |
| `F10` | `f10-guard-registry.svg` | `f10-guard-registry.zh-CN.svg` | `workflow-guard-registry-20261009-2340/f10-guard-registry.html` |
| `F11` | `f11-ir-attribution.svg` | `f11-ir-attribution.zh-CN.svg` | `workflow-ir-attribution-20261009-2340/f11-ir-attribution.html` |
| `F12` | `f12-audit-layers.svg` | `f12-audit-layers.zh-CN.svg` | `architecture-audit-layers-20261009-2340/f12-audit-layers.html` |
| `F13` | `f13-agent-loop.svg` | `f13-agent-loop.zh-CN.svg` | `lifecycle-agent-loop-20261009-2340/f13-agent-loop.html` |
| | **合计 26 个 SVG，3,997,289 字节** | | **26 个交互 HTML，19,699,610 字节** |

对比一下量级：26 个独立 SVG **3.82 MB**，占 26 个交互 HTML（19.70 MB）的 **五分之一不到**，
而它带来的差别是「打开 README 就看得见图」。两者都在仓库里，各自有各自的用途：
SVG 用来看，HTML 用来**放大、查找、沿着关系走**。

`flow/INDEX.md` 与 `flow/FLOW_INDEX.json` 也一并登记了这 26 个 SVG 的**路径与字节数**
（由 `_r45/gen_flow_index.py` 从磁盘**实测**生成，不是手写）。索引既然叫索引，它自己
也得被钉住 —— `tools/check_flow_diagrams.py` 的 **D9** 判据就是干这个的：索引漏登记、
登记了磁盘上不存在的文件、或声明的体积与 `os.path.getsize` 对不上，一律变红。
**一条会过期的索引比没有索引更糟**，因为它看起来是对的。

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

# 5) 从 26 个产物里各取一份独立 SVG（仓库外脚本，只动临时副本；
#    `window.__archifySerialize = serializeSvg;` 只插在临时副本上）
python E:/matlabc/_r47/extract_svg.py

# 6) 验证取出来的图 == 产物里那张图（同文档、同主题、1:1、逐元素比计算样式）
python E:/matlabc/_r47/verify_svg.py --ref-theme light

# 7) 把独立 SVG 嵌进两份 README（锚点唯一性 + 中英逐节对等，本步自检）
python E:/matlabc/_r47/embed_docs.py
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

> **R47 落地情况**：下面第 1 条里「**图与文档对不上**」的那一半已经落地 ——
> 新增的 `tools/check_flow_diagrams.py` 把 **README 里的引用 ↔ `flow/diagrams/` 里的文件 ↔
> `candidate*.json` 里的声明 ↔ `flow/archify/` 里的交互产物 ↔ `flow/FLOW_INDEX.json` 的索引登记**
> 钉成了 **D1–D9 九条判据，且**每一对都双向**（引用悬空 → 红；文件没人引用 → 也红；
> 索引漏登记 → 红；索引登记了不存在的东西、或声明的体积与磁盘对不上 → 也红）。
> **仍然没做的**是「`source/*.mmd` 与源文档对不上」那一半（它要重跑普查），见下面第 1 条。

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
7. **给独立 SVG 补一条「尺寸判据」**：D5 现在只查静态形态。可以再加一条 —— SVG 的
   `viewBox` 必须等于 `candidate.json` 里声明的宽高（`extract_svg.py` 已经把
   `width`/`height` 带回来了），否则「图被重渲染成另一个尺寸」不会有人发现。
8. **给「取图」也做一次逐字节可重复**：`extract_svg.py` 每次都要起一次无头浏览器。
   应加一条断言：同一份产物**连取两次，SVG 必须逐字节相同**（像 `render_zh.py`
   对 HTML 做的那样）。这样「取图」也从「跑过一次」升级成「可重复的等式」。
9. **那 88 KB 的内联字体值不值得背？** 26 个 SVG 合计 3.82 MB，其中 **57%**（每张 ~88 KB）
   是同一份 JetBrains Mono WOFF2 子集。而 GitHub 侧用 `<img>` 加载 SVG 时，`@font-face`
   到底会不会生效，各浏览器并不一致；中文又本来就不在这个子集里。
   值得实测一次（去掉字体块再比一次像素），再决定是否保留 —— **先测，再选**，
   和本轮选 `autoTheme` / `figure` 是同一套方法。
