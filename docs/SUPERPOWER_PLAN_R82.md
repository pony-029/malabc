# SUPERPOWER 方案 R82 —— 全链路贯通：调用图 → 异步 → 二进制 → 算子 → 互转 → 自治演进

> **定位**：把 matlabc 从「能分析单语言、单形态、单跳归因」升级为**能贯通整条链路**——
> 源码调用关系（含异步）→ 动态库/ELF/PE/CUDA 算子 → 双向代码互转 → 不间断自治演进。
>
> **方法**：`superpowers`（六顶思考帽）× `superpower-probe-loop`（隔离探针 + 登记制护栏）×
> `loop-engineer`（闭环迭代与退出条件）。联动 skill 清单见 §9。
>
> **定稿基线**：`aa65a29`（`VERSION = "1.16.72"`）· 80 提交 · `ls-tree -r -z` 266 条目 · 59 个受控 `.py` · `matlabc.py` 32,690 行
>
> **本文档的性质**：方案与验收判据的定义文件。**不承诺进度**，只承诺「每一步的判据长什么样、
> 以及它怎样才能红」。状态列全部从 ⬜ 起步，逐轮回填。

---

## 0. 一图看懂

```
                         ┌─────────────────────────── 已有底座（R44–R81）───────────────────────────┐
                         │  frontends/   matlab · c/cpp · py · js · asm      17 道门禁 + 登记制护栏      │
                         │  renderers/   csite · callgraph · hotspot · sarif · snapshot · unresolved    │
                         │  binfmt/      elf · pe · macho · gpu(CUDA/HIP/SPIR-V) · attribute · buildsys│
                         │  agent_loop · matlabc_flow · matlabc_ask · ai_cli · analyzer_memory · mcp  │
                         └────────────────────────────────────┬──────────────────────────────────────┘
                                                              │
   ┌──────────────────── 本方案要补的五条贯通线（互相咬合，不是五个独立功能）────────────────────┐
   │                                                                                            │
   │  T1 异步调用链          T2 二进制并入调用图        T3 源侧算子评估        T4 C↔MATLAB 互转    │
   │  ┌──────────────┐      ┌──────────────┐         ┌──────────────┐      ┌──────────────┐   │
   │  │ 边三态：      │      │ 多跳链：      │         │ __global__   │      │ 规则表(可版本)│   │
   │  │ direct/async/ │──▶  │ 源码→符号→库  │◀───────▶│ <<<g,b,s,st>>>│──▶  │ 确定性段+AI段 │   │
   │  │ unknown       │      │ →库依赖       │         │ ptxas 报告    │      │ 双语对照执行  │   │
   │  └──────────────┘      └──────────────┘         └──────────────┘      └──────────────┘   │
   │         │                      │                        │                     │           │
   │         └──────────────────────┴────────────┬───────────┴─────────────────────┘           │
   │                                             ▼                                              │
   │                              T5 自治演进闭环（目标注册表 → 判据 → 落地 → 记账 → 回退）        │
   │                              目标四类：静态告警 · 文档漂移 · 翻译保真失败 · 覆盖差集          │
   └────────────────────────────────────────────────────────────────────────────────────────────┘
```

**为什么是「五条线」而不是「五个功能」**：它们共用同一张**统一图**（unified graph）。
`MATLAB 的 parfeval 回调`（T1）→ `MEX 入口 mexFunction`（T2）→ `C 里 launch 的 CUDA kernel`（T3）
→ `同一个算子出现在 .mexw64 的 fatbin 里`（T2 又一次）→ `这一跳的翻译要么有规则要么标注未验证`（T4）
→ `差集与未验证项就是 T5 下一轮的目标`。任何一条线单独做，都会在边界上留下「静默缺失」。

---

## 1. 【蓝帽】分析对象、目标与产出格式

### 1.1 需求原文拆成可判定的条目

| # | 需求原文（你的话） | 判定形式（可红/可绿） |
|---|---|---|
| N1 | 「解析任何一个 C 工程或者 matlab 代码库的时候，把各个函数的调用关系都需要弄清楚」 | 调用图覆盖率：`已建边 / 提取到的调用站点`，且**未建边的站点必须分类**（不是静默丢） |
| N2 | 「直到最后的异步」 | **异步边被单独建模**：`async` 边数 > 0，且与 `direct` 边**不混**（混了就会得出错误的顺序结论） |
| N3 | 「不管是代码中依赖的动态链接库还是 elf 或者 pe 也都要解析出来」 | 二进制解析**已有**；缺的是**把符号图并入调用图**（多跳链），判据=链长分布 + 每跳有产它的装置 |
| N4 | 「把和 cuda 等涉及的算子准确的评估出来」 | 源侧算子评估：`__global__` 定义数 / 启动点数 / 启动配置可解析率 / 与二进制 kernel 名的对齐差集 |
| N5 | 「借用 ai agent 的力量可以把 c 代码或者 matlab 代码相互转换，按照我规定的规则」 | 规则表命中率；**每条翻译可追溯**（规则 ID 或 `ai_ad_hoc`）；**保真度**：双语执行对照通过率 |
| N6 | 「不间断持续的演进，直到满足具体的需求」 | 自治循环：每轮产出 `(目标, 变化量, 判据, 接受/拒绝)`；**退出的判据是「无红之目标」而非「AI 说好了」** |
| N7 | 「整个项目的文档维护以及 bug 分析等，也就是从头到尾都有」 | 文档漂移 = 0（已有 `doc_metric` 概念）；bug 分析**能消费 T1/T2 的新边**（而不是继续只看同步调用） |

### 1.2 产出格式

- 每轮一份 `docs/SUPERPOWER_REVIEW_Rnn.md`（复盘，含真缺陷与判据）
- 方案本身的**验收判据**先于实现落地（Phase 0），并**当场证明它会红**（本仓纪律：先装闸门，看它当场红）
- 一切读数必须**带分母与口径**（本仓纪律：报「全覆盖」必须同时报分母）

---

## 2. 【白帽】事实与数据（全部本机实测，2026-10-11）

> 白帽纪律：**只写查过源码或跑过命令的事实**。下文每条都标了证据（文件/行号/命令）。

### 2.1 已落地的底座（这一节决定方案从哪里起步）

| 类别 | 已有能力 | 证据（实测） |
|---|---|---|
| 多语言前端 | `--lang` 允许值 = `matlab`（默认）/ `c` / `cpp` / `py` / `js` / `asm` | `matlabc.py:30901-30909` |
| 调用图 | `renderers/callgraph.py`（静态 SVG，左→右分层，`max_nodes` 降采样） | 10,779 B / 254 行 |
| 交互站点 | `--browse`，含函数页/调用跳转/规则页/类继承图 | `renderers/csite.py` 32,498 B |
| Doxygen 兼容 | `--export-doxygen-xml OUTDIR`（`index.xml` + 每文件 `compounddef`） | `matlabc.py:30883-30885` |
| 二进制解析 | `binfmt/`：ELF（含 CUDA cubin 伪装识别 `e_ident[7]==0x33`）/ PE（含段名 8 字节截断真相）/ Mach-O | `elf.py` 15,050 B · `pe.py` 11,592 B · `macho.py` 29,028 B |
| GPU 内容提取 | CUDA fatbin / PTX / AMD HSACO / Vulkan SPIR-V；实测 `cublas64_12 → 171 个 kernel 名` | `binfmt/gpu.py` 26,063 B / 639 行 |
| 三态归因 | `--binary-attach`：源码未解析调用 → ① 来自动态库 ② 来自 GPU 算子 ③ 真漏 | `matlabc.py:30605-30611` |
| 二进制独立解析 | `--binary` / `--binary-symbols` / `--binary-json` / `--binfmt-scan-cap` | `matlabc.py:16506`、30956、30968 |
| 跨语言桥接 | `--mixed`：MATLAB 外部调用命中 C 函数时建 MEX 桥 | `matlabc.py:31490`、`31660-31662` |
| 静态检查 | `--checks` 含 9 kind + C 侧 8 类规则（`c_unused_static` / `c_missing_guard` / `c_array_oob` / `c_use_after_free` …） | `matlabc.py:30886+` |
| 问答底座 | `matlabc_ask.py`：零依赖 BM25 + 意图识别（谁调用 X / 风险热点 / 解释 X） | 20,549 B / 457 行 |
| 修复闭环 | `matlabc_flow.py` 五站点 `review→fix→apply→verify→report`；`agent_loop.py` 门控+回退+终止 | 31,896 B / 630 行 · 31,277 B / 706 行 |
| 跨运行记忆 | `analyzer_memory.py`：`suppressions` + `learned_fixes`（限长 200，`.codebuddy/analyzer/memory.json`） | 5,041 B / 131 行 |
| MCP 暴露 | `matlabc_mcp.py`：5 工具 `analyze` / `check` / `ask` / `gen_patch` / `version` | 19,032 B / 450 行 |
| AI 多供应商 | `ai_cli.py`：`offline`/`openai`/`anthropic`/`ernie`/`iflytek` + 国产别名 | 34,089 B / 692 行 |
| 工程闭环 | `--debt` `--trend` `--gate` `--sarif(-diff/base)` `--dup-*` `--gen-pr` `--gen-apply-patch` `--gen-tests(-risk)` `--gen-ci` | 参数清单实测 |
| 门禁 | `tools/check_all.py` 聚合 **17** 道 `check_*.py`，`MIN_GUARDS=17` | 目录实测 |
| 整树实证 | 内核 62,704 C 文件 / 36,155,901 行 / **743,518 函数** / 7,065,831 调用边 / 2,293,841 注释；站点 62,920 页 | R81 读数（`aa65a29`） |

### 2.2 需求 → 现状对照（三态）

图例：✅ 已落地 · 🟡 浅层/半截 · ❌ 缺失

| 需求 | 现状 | 说明（实测） |
|---|---|---|
| N1 调用关系弄清 | ✅ | 调用图 + 站点 + Doxygen XML；OOP 四路径已补（类名限定/构造赋值/类内互调/跨文件消歧） |
| **N2 直到异步** | ❌ | **`async` 只出现在词法层**：`_RE_PY_DEF_HEAD`（`9421`）、JS 函数定义（`9740`）只把 `async` 当**关键字跳过**。`pthread` = 0 命中、`coroutine` = 0、`parfeval` = 0。**没有任何异步边** |
| N3 动态库/ELF/PE | 🟡 | 解析与**三态归因**已有；但**不建边**——`--binary-attach` 只回答「这个名字来自哪个库」，不回答「这条调用链往下走到哪个库的哪个符号、那个库又依赖谁」 |
| **N4 CUDA 算子准确评估** | 🟡 | 只做**清点**（从容器提取 kernel 名）。**源码侧零评估**：无 `__global__` 识别、无 `<<<>>>` 启动配置解析、无资源用量。⚠ 另有**术语冲突**（见 2.4） |
| **N5 C↔MATLAB 互转** | ❌ | `matlab2c`/`c2matlab`/`mexFunction` 全 0 命中；`转换` 30 处**全是 MATLAB 类型转换函数**（`cast`/`int8`…），`translate` 4 处**全是 SVG transform**。**没有任何代码翻译能力** |
| N6 不间断演进 | 🟡 | `agent_loop.py` 有门控/回退/终止，但**只处理静态告警计数**（判据=「各规则告警数不得增加 + 总量下降」）；`analyzer_memory` 只记 `learned_fixes`。**没有「目标注册表」，也没有「文档/翻译/覆盖」三类目标** |
| N7 文档维护 + bug 分析 | ✅ | `--debt`/`--trend`/`--sarif`/`--dup-*`/`--gen-pr` 齐全；缺的是**消费新边**（异步边不存在的今天，异步回调里的 bug 不可达） |
| N8 端到端链路 | ❌ | 上面每一条线各自都有产物，但**没有一张贯穿图**把 `MATLAB 调用点 → MEX 入口 → C 实现 → .so → CUDA kernel` 连起来 |

### 2.3 四个真缺口（每个都带量化依据）

| 缺口 | 量化依据（本机测得） |
|---|---|
| **G1 异步边缺失** | 词法命中 `async` 仅 9 处且**全是关键字跳过**；`pthread`/`coroutine`/`parfeval`/`mexFunction` 命中 **0**。整树内核 1,369 个 `.S` 与 62,704 个 C 文件里的并发原语，今天**一条边都没建** |
| **G2 二进制不进图** | `binfmt` 44 处接线里，产出的是 `BinaryReport`（sections/symbols/dependencies/gpu）与**归因表**；`renderers/` 里**没有任何消费者**把 `symbols` 变成调用图的边 |
| **G3 源侧算子零评估** | `binfmt/gpu.py` 只认**二进制里**的 kernel 名；源码侧 `__global__`/`<<<>>>` 无识别。整树 `.S` 的 `insn_top` 里已实测混入 `short` 1,870 + `long` 1,658 = **3,528** 条 m68k 省略点号数据指令（R79/R80 已登记 C30-1），说明 asm/算子侧的**分类本身**还不够 |
| **G4 无互转与无保真判据** | 无任何翻译器；有 `ai_cli.py`（能调模型）与 `matlabc_flow.py`（能自证补丁），**但没有把两者接成「翻译 → 执行对照 → 保真」的链路** |

### 2.4 一个必须先修的术语冲突（白帽事实）

`--operator-impact-out/threshold/baseline/compare/gate/scan-cap` 这一族参数里，
**「算子」指「静态检查类别」**，不是 CUDA 算子。原文（`matlabc.py:30857-30858`）：

> `把「检测算子工程影响分析」单独写入 FILE；算子按命中数×严重度×波及系数排名，定位对整个工程影响最大的检测类别。`

而本方案的 **T3 要谈的是真正的 GPU 算子**。同一个词两个意思，且**已经在 CLI 表面固化**。

> **处理原则**：**不改旧语义**（会破坏向后兼容与已有基线），而是**给新语义起新名**
> （GPU 侧统一叫 `kernel` / `gpu-kernel`），并在 help 与文档里**显式声明这个区分**。
> 这是本仓「同一个名字能同时用在两个含义里 ⇒ 必须为每个含义写下它覆盖的范围」（skill §4b-2）的直接应用。

### 2.5 硬约束（不可协商）

1. **零第三方依赖**：`binfmt/model.py` 的手写类（而非 `@dataclass`）就是为了**严格兼容 Python 3.6.5**；
   `check_py36_clean.py` 在门禁里。任何新模块必须过它。
2. **`_c_lex` 不可轻动**：R78 证明它是**多处共用的唯一词法器**；新增语言/方言必须**另写词法**（汇编前端就是这么做的）。
3. **旧键逐位不变**：R79/R80 的兼容性基线要求「老键的值与老版本全等，新增只能是新键」。
4. **行尾**：仓库 blob 全 CRLF（`core.autocrlf=false` + `* -text`），新文件自查 `bare_lf == 0`。
5. **门禁扩张成本**：动 `IR_LANG_OWNERS` 级联 3 处、改 `matlabc.py` docstring 须同步**两处**体积快照、门数变更**级联七处**。
6. **没有可执行对照的能力一律标注 `unverified`**（沿用 `macho.py` 的 `verified` / `fixture_verified` 双字段先例）。

---

## 3. 【红帽】直觉与情绪

- **最兴奋的一点**：链路真的能打通。今天缺的每一环都**已经有一个真装置**（binfmt 能读 `.so`，
  `--mixed` 能认 MEX 名字，`agent_loop` 能自证改动，`ai_cli` 能调模型）——缺的是**把它们接成一条链**，
  而不是从零造。这意味着 80% 的工作是**接线 + 判据**，不是新算法。
- **最不安的一点**：**N5（互转）最容易被做成「看起来能跑」的演示**。让模型把一段 MATLAB 翻成 C，
  编译过、跑出个结果，就能演示；而**语义等价**才是真需求。若不先把「保真度判据」立起来，
  这个功能会变成一个高级玩具，且**它的失败是静默的**（编译通过、结果不同）。
- **第二不安**：**异步**。把 `std::thread` 之后的调用当同步边，会得出「A 在 B 之后执行」这种
  **恰好错误**的结论；而它读起来完全正常。宁可报 `unknown` 也不能猜。

---

## 4. 【黑帽】风险与批评（这一节最该认真读）

| # | 风险 | 最坏情况 | 缓解（写进方案的约束） |
|---|---|---|---|
| K1 | **互转做成玩具** | 演示很漂亮，实际不可用；用户按它改了生产代码 | **保真度判据先行**（D 段）：无双语执行对照的结果一律 `unverified`；工具**默认只输出对照报告，不改代码** |
| K2 | **异步边「猜」出来** | 误连出假边 ⇒ 调用图从此不可信（比没有更坏） | **三态**：`direct` / `async` / `unknown`。只有**有明确 spawn 语法**的才是 `async`；其余进 `unknown` 并计数 |
| K3 | **多跳链变成「编故事」** | 链上某一跳其实是猜的，报告却写得很确定 | **每跳必须挂一个产它的装置**（`hop.via_device = "elf.dynsym" / "pe.import" / "fatbin.section_name"`）；无装置即不建边 |
| K4 | **算子评估过度承诺** | 报出一个 occupancy 数字，用户拿去调优，实为估算 | 只报**可得的量**（启动配置、ptxas 报告里的寄存器/共享内存）；occupancy 一律标注 `estimated` 并给出**反推它的约束**（本仓 skill §4b-2「两个资源的拐点」纪律） |
| K5 | **门禁被撑爆** | 每条线各加一批门 ⇒ `check_all` 从秒级变分钟级（本仓已有此教训：`check_*` 通配会把慢工具吸进门禁） | 慢检查**不叫 `check_*.py`**（本仓已有先例：`probe_cases.py` 刻意不叫 `check_cases.py`）；真跑放 `tests/` |
| K6 | **翻译规则表变成「没人维护的常量」** | 规则表与实现漂移，命中率悄悄下降 | 规则表**有版本 + 有命中/未命中读数**；「声明了规则但从未命中」必须是一条**可红**的判据（本仓 skill §4k-2：一个从未被触发的分支不是判据） |
| K7 | **自治循环「多做了事」** | `--evolve` 顺手改了用户没看的文件（本仓 skill §4r-5） | 默认 `--auto-apply=false`；输出**逐条给出精确目标**（文件+规则 ID），宽口径命令必须**预告实际范围** |
| K8 | **Python 3.6.5 兼容被破坏** | 用了 `dataclass`/`f-string` 之外的 3.7+ 特性 ⇒ `check_py36_clean` 红 | 新模块一律**先跑 `--check-py36`**；探针与正式代码同一标准 |
| K9 | **工时误判** | 把 5 条线当 1 轮做 | 本方案**明确拒绝**一次性交付；Phase 0→E 逐段验收（见 §8） |
| K10 | **`--mixed` 已有行为被改坏** | T2 要升级 MEX 桥，可能改坏已有的「名字命中」基线 | 新增为**新键**（如 `c_bridge_v2`），旧的 `c_bridge` 保持**逐位不变**（硬约束 3） |

---

## 5. 【黄帽】价值与收益

| 收益 | 为什么值 |
|---|---|
| **一句话结论可辩护** | 「这个 MATLAB 函数的真实耗时在内核里」——今天无法说，因为链路断在 MEX。打通后它是一条**有 5 跳证据**的话 |
| **大语料可用** | R80 已把整树 JSON 从 ~2.2 GB 压到 **10.83 MB**（`summary` 档）。链路打通后，**整树级别的端到端查询**才可能（而不是抽样子集） |
| **翻译从「能跑」到「可信」** | 双语执行对照把「AI 说它等价」变成「**两侧输出在容差内相等**」。这一条就能把 T4 从玩具变成工具 |
| **自治循环有真正的目标** | 今天 `agent_loop` 的目标只有「告警数下降」。新增三类目标后，**文档漂移 / 翻译保真 / 覆盖差集**都能被同一个循环吃掉，且都能自证 |
| **零新依赖** | 全部能力都建在标准库 + 已有模块上；`binfmt` 已经证明这条路可行（手写类也要坚持 3.6.5） |
| **失败也是资产** | 每条线的**差集**（未识别的并发原语 / 无装置支持的跳 / 未验证的翻译）本身就是**下一轮的目标清单**——这正是 N6「不间断演进」的燃料 |

---

## 6. 【绿帽】替代方案与改进点

| 方案 | 描述 | 判定 |
|---|---|---|
| **A 最小可用** | 只做 T2（二进制并入图），因为 `binfmt` 已就绪 | 否——单线会让异步与互转继续缺失，而它们恰好是你点名的两条 |
| **B 只做 T4** | 直接上互转（最显眼） | 否——**没有 T1/T2，翻译的上下文不完整**（翻一段调用了 `.so` 与开线程的代码，等价性根本无法判） |
| **C 五线并行** | 同时推 5 条线 | 否——违反 K9；且 5 条线共用统一图，模型层的改动会互相打架 |
| **D 分层接续（选定）** | **Phase 0 护栏 → A(T1) → B(T2) → C(T3) → D(T4) → E(T5)**，统一图数据结构在 Phase 0 一次定稿 | ✅ 选定。理由：T1 给图加**边的种类**，T2 给图加**跨形态的 hop**，T3 复用 T2 的 hop 概念，T4 复用 T1/T2 的图做上下文，T5 消费前面所有线的**差集** |
| 改进点 1 | **把「差集」当一等产物** | 不只报「识别了什么」，**同等重要地报「没识别什么、为什么」**（本仓 skill §4s-1：过滤发生得太早 ⇒ 判据够不着它要判的东西） |
| 改进点 2 | **术语先行** | Phase 0 先修 `operator` 歧义（2.4），否则 T3 的文档与 CLI 会持续互相误导 |
| 改进点 3 | **MCP 工具扩展与 CLI 同步** | 每新增一个能力，同步扩 `matlabc_mcp.py`（否则 Agent 摸不到 = 等于没实现；本仓 skill「能力清单不能撒谎」有可执行对手方） |

---

## 7. 【蓝帽】选定架构：五条贯通线

### 7.1 分层（每层只有一个职责，层间单向依赖）

```
第 4 层  消费面   ├── 站点/报告（renderers）  ├── MCP 工具（matlabc_mcp）  ├── 问答（matlabc_ask）
                  └── 自治循环（agent_loop / matlabc_flow / --evolve）
                          ▲
第 3 层  图模型    └── **UnifiedGraph**（本方案新增，唯一事实源）
                      节点：File / Function / Binary / Kernel / Rule
                      边：  direct | async | callback | indirect | dynamic | **binhop**
                          ▲
第 2 层  解析器    ├── frontends/  (matlab · c · py · js · asm)   ← 已有，只加「边种类」输出
                  └── binfmt/     (elf · pe · macho · gpu)        ← 已有，只加「符号→节点」导出
                          ▲
第 1 层  词法/字节  └── 已有词法器 + 新增：并发原语表 · CUDA 启动语法 · MEX 入口签名 · 翻译规则表
```

**关键纪律**：第 2 层**不产生边**，只产生**节点与站点**；边的构造**只发生在第 3 层一处**。
（同一规则只实现一次——本仓招牌纪律。）

### 7.2 T1 异步调用链

**要回答的问题**：`foo()` 里的调用，是**同步等它返回**，还是**派出去就不管了**？

| 语言 | 识别目标 | 三态归属 |
|---|---|---|
| C/C++ | `pthread_create`、`std::thread`、`std::async`、`std::future`、`fork`、`signal`、`epoll`/`io_uring` 注册、`__attribute__((constructor))` | 有明确 spawn 语法 ⇒ `async`；其余（函数指针表、vtable）⇒ `indirect` 或 `unknown` |
| Python | `async def` + `await`、`asyncio.create_task`、`run_in_executor`、`Thread`/`Process`、`atexit` | `await` 是**汇合点**（汇合到 direct 语义），`create_task` 是 `async` |
| JS | `Promise.then`、`async/await`、`setTimeout`、`addEventListener`、`queueMicrotask` | 回调注册 ⇒ `callback`；`await` ⇒ 汇合 |
| MATLAB | `parfor`、`parfeval`/`Future`、`batch`、`spmd`、`timer`、`uicontrol` 回调 | `parfor` 体 ⇒ `async`（工作项）；`timer`/回调 ⇒ `callback` |
| asm | `call`/`bl`/`jal` 之外的**间接跳转**（跳转表、`br x0`） | ⇒ `unknown`（不猜目标） |

**数据模型（精确到字段）**

```
AsyncSite = {
  site_id:      str,        # 稳定 ID：rel:line:col
  kind:         "thread" | "task" | "promise" | "parfor" | "timer" | "signal" | "callback" | "stream",
  spawn_line:   int,
  target_name:  str | None, # 能静态解析出的目标名；解析不出为 None（**不猜**）
  target_ref:   str | None, # 解析出的 Function.node_id
  barrier:      "join" | "await" | "yield" | "none",   # 汇合点在哪
  evidence:     str,        # 产它的装置：如 "c:pthread_create" / "matlab:parfeval"
}
Edge = { src, dst, kind, evidence, site_id }
# kind ∈ {direct, async, callback, indirect, dynamic, binhop}
```

**判据（可红/可绿）**

1. **边数守恒（恒等式，不是阈值）**：
   `Σ(各 kind 的边) + Σ(unknown 站点) == 解析器报出的调用站点总数`。
   漏一条边或漏一个 unknown 站点，恒等式当场破。（本仓 skill：护栏用恒等式，不用阈值。）
2. **不混**：任何 `async` 边**不得**同时以 `direct` 出现（同一 `site_id` 只能有一种 kind）。
3. **`unknown` 必须可见**：站点/报告上有一列「未识别的并发站点」，且**分母是扫描过的并发关键字节点数**。
4. **两向变异**：注入一个 `pthread_create` 调用点 ⇒ 多一条 `async` 边（红→绿方向）；
   把 `pthread_create` 从并发原语表里删掉 ⇒ 该站点必须掉进 `unknown`（**不是静默消失**）。

### 7.3 T2 二进制符号图并入调用图（多跳链）

**要回答的问题**：`foo()` 解析不到定义——它来自哪个库？那个库自己又依赖谁？它里面有没有 GPU 算子？

**多跳链（这是「像 doxygen」之外真正多出来的一层）**

```
MATLAB foo.m
   │  (1) direct 边（同语言）
   ▼
MEX 入口 mexFunction          ← 桥锚点：C 侧的**已知入口形状**
   │  (2) binhop：经 .mexw64/.mexa64 的**导出符号**（ELF .dynsym / PE export）
   ▼
C 实现 foo_impl()
   │  (3) direct 边 + (4) async 边（若它开了线程）
   ▼
libfoo.so 的导出符号           ← ELF .dynsym / PE import
   │  (5) binhop：库依赖（DT_NEEDED / import table）
   ▼
libbase.so → 里面的 CUDA fatbin 段 `.nv_fatb` → kernel `_Z6kernelPf`
```

**数据结构**

```
Hop = {
  via_device: str,     # **必须**是产这一跳的装置名："elf.dynsym" | "pe.import" |
                       #   "pe.export" | "fatbin.section" | "magic.scan" | "buildsys.flag"
  from_node:  str,
  to_node:    str,
  symbol:     str,
  container:  str,     # 承载它的文件
}
Resolution = {
  name: str,                       # 源码侧未解析的名字
  kind: "source" | "dynlib" | "gpu_kernel" | "mixed" | "unresolved",
  chain: [Hop, ...],               # 空链 = 真漏（**这才是缺陷**）
  verified: bool,                  # 该链是否在真实二进制上验证过（沿用 macho 双字段先例）
}
```

**判据**

1. **每跳有装置**：`Hop.via_device` 非空且属于**登记表** `HOP_DEVICES`；不在表里 ⇒ 红。
2. **链的忠实性**：`chain` 里每一跳的 `to_node` 必须是**上一跳装置真的读出来的东西**
   （不是同一份报告里另找的）—— 用「同名不同源」的夹具两向验证。
3. **差集分类**：`kind="unresolved"` 的集合必须**分类报告**（`symbol_not_exported` / `dynamic_only_no_name` /
   `mangled_unparsed` / `genuinely_missing`），每类都要有分母。**「真漏」才叫缺陷。**
4. **`--mixed` 升级不改旧键**：新增 `c_bridge_v2`（含 hop），旧 `c_bridge` 逐位不变（K10）。
5. **MEX 锚点是**形状**而不是名字**：识别 `mexFunction(int nlhs, mxArray *plhs[], int nrhs, const mxArray *prhs[])`
   —— 名字可能被宏包装，形状更稳。

### 7.4 T3 源侧算子评估（GPU kernel）

**要回答的问题**：这个工程里有哪些 CUDA 算子？它们怎么被启动的？资源用量多少？和二进制里那些名字对得上吗？

| 项 | 数据来源 | 确定性 |
|---|---|---|
| `__global__` 定义 | C 词法（**新词法**，不动 `_c_lex`） | 确定 |
| 启动点 `<<<g,b,s,st>>>` | C 词法 + 括号配平（`dim3(a,b)`、变量、表达式） | 确定；**解析不出记 `unevaluated`** |
| 启动配置数值 | 若 grid/block 是**字面量**或**const 宏** ⇒ 直接得数 | 确定；否则 `unevaluated` |
| 寄存器/共享内存 | `ptxas -v` 输出**解析**（用户显式提供该文件时才跑） | 确定（来自 ptxas） |
| occupancy | 由上面反推 | **`estimated`**，且必须给出**反推它的约束**（哪个资源是瓶颈） |
| 与二进制对齐 | T2 的 `fatbin` kernel 名集合 | 确定（集合运算） |

**判据**

1. **三处对齐**：源码 `__global__` 名集合 `S`、启动点目标名集合 `L`、二进制 kernel 名集合 `B`。
   `L - S` 与 `S - B` 都必须**分类报告**（未在本工程定义 / 未在给定二进制里找到），
   不得只报交集。（本仓 skill §4x-1：**超集关系必须写成断言**。）
2. **`unevaluated` 有分母**：`可解析启动配置 / 启动点总数`，且分母是**扫描到的启动点数**。
3. **`estimated` 可识别**：任何估算值必须带 `estimated=True` 与 `bound_by`（瓶颈资源名）；
   报告里估算与确定**分列**，不得混排。
4. **术语**：GPU 侧一律用 `kernel`；`--operator-impact-*` 的旧语义**加一段 help 声明**这个区分。
5. **R79 遗留一并处理**：m68k 点号省略指令（`short`/`long`，整树实测 3,528 条）归数据段，不再污染 `insn_top`。

### 7.5 T4 规则驱动的 C ↔ MATLAB 互转

**这是全方案风险最高的一条**，因此设计上**把「不可信」变成默认**。

```
                    ┌──────────────── 你规定的规则（可版本化，唯一事实源）────────────────┐
                    │  translate_rules.json                                          │
                    │    { "version": "1.0", "rules": [                              │
                    │        {"id": "IDX-1",  "from": "matlab:1-based",              │
                    │         "to": "c:0-based", "note": "索引基准",                  │
                    │         "verified_by": "tests/translate/idx1"} ] }              │
                    └────────────────────────────┬───────────────────────────────────┘
                                                 │
   源码 ──▶ ① 确定性段（零 AI） ──▶ 每个函数：{mapped | unmapped} + 差异报告
              │  覆盖：标量循环 / 数组运算 / 索引基准 / 基本 I-O / 作用域
              │
              └─▶ ② AI 段（ai_cli）──▶ 只吃「unmapped」+ 反例 + 上下文 ──▶ 补丁
                                                                    │
                                              ③ 回流 matlabc_flow（apply → verify）
                                                                    │
                                              ④ **双语对照执行器**（保真度的唯一裁判）
                                                 · 同一组输入，两侧真跑：MATLAB 侧 octave/matlab -batch；C 侧编译运行
                                                 · 比对：数值（容差）/ 字符串 / 错误行为 / 边界
                                                 · 输出：verified | unverified（**默认就是 unverified**）
```

**数据结构**

```
Translation = {
  unit: str,                 # 函数/脚本单元
  direction: "m2c" | "c2m",
  rules_hit: [rule_id, ...],
  unmapped: [{node, reason, ad_hoc: bool}],
  patch: str | None,
  fidelity: {
    status: "verified" | "unverified" | "failed",
    cases: [{in, out_a, out_b, equal, tol}],
    runner: "octave" | "matlab" | "cc" | "gcc" | None,   # None ⇒ 无法执行 ⇒ unverified
  },
}
```

**判据**

1. **可追溯**：每条翻译必须**引用至少一条规则 ID**或标注 `ad_hoc=True`；`ad_hoc` 一律进 `unverified`。
2. **保真度是唯一裁判**：`verified` 只能由**双语真执行**给出；**没有 runner 就是 `unverified`**（不是「大概对」）。
3. **规则表的两个对手方**：① 声明了却**从未命中**的规则 ⇒ 可红；② 命中了**未登记**的规则 ID ⇒ 红。
4. **默认不改代码**：只产出对照报告与补丁草稿；`--apply` 才落盘，且落盘后**必须重跑对照**。
5. **语料**：先用 MATLAB 自带的可执行样例（无需商业 license 也能跑的 octave 子集），
   并在报告里**声明用了哪个 runner**（口径）。

### 7.6 T5 自治演进闭环（不间断持续演进 + 文档维护 + bug 分析）

```
   ┌─ 目标注册表 EVOLVE_TARGETS（可版本化）────────────────────────────────────┐
   │  T-STATIC   静态告警       判据：各规则告警数不增 且 总量下降（已有）        │
   │  T-DOC      文档漂移       判据：doc 数字 == 真值（已有 doc_metric 概念）   │
   │  T-TRANS    翻译保真       判据：unverified 集合变小 且 verified 不减少     │
   │  T-COVER    覆盖差集       判据：分类差集的总量下降（T1/T2/T3 的差集）      │
   └────────────────────────────┬────────────────────────────────────────────┘
                                ▼
   扫描 ──▶ 分类 ──▶ 选一个**可自证**的目标 ──▶ 生成改动 ──▶ 用**不变量**验证
     ▲                                                            │
     │                                          ┌─────────────────┴──────────────┐
     │                                       通过 │                         不通过 │
     │                                    进下一轮 │                    回退到基线 │
     └────────────────── 记账：(目标, 变化量, 判据, 接受/拒绝) ◀──────────────┘
```

**判据**

1. **接受必须伴随判据由红转绿**（不能只凭「变化量 > 0」）。
2. **回退必须可证**：拒绝后工作区与基线**逐文件 sha256 相等**（本仓纪律：`git diff` 不是工具）。
3. **记账可重算**：每轮 `(目标, 变化量, 判据, 结论)`；**变化量必须能被独立重算**（不是自报）。
4. **`--evolve` 默认不落盘**，且**逐条列出精确目标**（文件 + 规则 ID）；宽口径动作必须**预告范围**（K7）。
5. **退出条件**：`所有注册目标的判据皆为绿` ⇒ 停机并**交出「最后一道门的名字」**（不是日期——
   本仓 skill：日期不可重算）。

### 7.7 新增文件与唯一事实源清单

| 新文件 | 职责 | 唯一事实源 |
|---|---|---|
| `unified_graph.py` | 图模型（节点/边/hop）+ 序列化 | **边的构造只在这里** |
| `concurrency.py` | 五语言并发原语表 + 站点提取 | 并发原语表只在这里 |
| `binhops.py` | `Hop` 构造与装置登记（`HOP_DEVICES`） | 跳的构造只在这里 |
| `gpu_kernels.py` | `__global__` / `<<<>>>` / ptxas 解析 | 启动语法只在这里 |
| `translate/` | `rules.py` + `m2c.py` + `c2m.py` + `fidelity.py` | 保真判据只在这里 |
| `evolve.py` | 目标注册表 + 循环 + 记账 | 目标判据只在这里 |
| `tools/check_unified_graph.py` | 边数守恒 / hop 装置登记 / 术语 | 护栏（静态、秒级） |
| `tools/check_translate_rules.py` | 规则表两向对手方 | 护栏 |
| `tests/test_translate_fidelity.py` | 双语真执行（**真跑，放 tests/ 而非 tools/**） | — |

---

## 8. 分阶段实施计划（原子任务 + 验收判据）

> 每一条都是**原子任务**：一个文件的主要改动 + 一条验收判据。
> **不许跳步**，每条做完必须**当场证明判据能红**（两向变异）。

### Phase 0 · 护栏与模型先行（不写功能，先把「能红」立起来）

| ID | 任务 | 文件 | 验收判据 |
|---|---|---|---|
| R82-0-1 | 术语修复：GPU 侧统一 `kernel`，`--operator-impact-*` 加 help 声明 | `matlabc.py`（help 文案） | `check_doc_flags` + `check_help_contract` 绿；新旧术语在 help 里**同时出现且区分明确** |
| R82-0-2 | `unified_graph.py` 建模型（节点/边/hop/序列化） | 新文件 | `--check-py36` 绿；**空实现的边数守恒恒等式能红**（注入一条边即破） |
| R82-0-3 | `check_unified_graph.py` 护栏（含 `--selftest` + `SELFTEST COUNTS` 行） | 新文件 | **先装闸门，看它当场红**；登记进 `check_all.py`（门数 **17→18**，级联七处） |
| R82-0-4 | 变体目录登记：`HOP_DEVICES` / 并发原语表 / 规则表骨架 | 新文件 | 空白登记表下，引用它的判据必须红（不是静默空转） |
| R82-0-5 | 基线快照（供 E 段回退对照） | 记录 | 记录 `HEAD` + `tree` + 受控文件 sha256 清单 |

**Phase 0 出口判据**：`check_all` 门数从 17 → 18 且**全绿**；两道新护栏 `--selftest` 的两向变异记录可见。

### Phase A · T1 异步调用链

| ID | 任务 | 验收判据 |
|---|---|---|
| R82-A1 | `concurrency.py`：五语言并发原语表 + `AsyncSite` 提取（**新词法，不动 `_c_lex`**） | 表里**每一条**原语都有一个夹具命中；删除任一条 ⇒ 对应站点掉进 `unknown`（**不是消失**） |
| R82-A2 | C/C++ 后端：`pthread_create` / `std::thread` / `std::async` / `fork` / `signal` | 探针：真实 C 夹具（含 5 种原语）逐个命中，`evidence` 字段齐 |
| R82-A3 | Py/JS 后端：`await`（汇合）/ `create_task`（async）/ `Promise.then`（callback）/ 事件注册 | `await` 必须**不产生 async 边**（它是汇合）；反向夹具必须能红 |
| R82-A4 | MATLAB 后端：`parfor` / `parfeval` / `batch` / `timer` / 回调注册 | 整树式语料上 `parfor` 体识别率有分母报告 |
| R82-A5 | asm 间接跳转 ⇒ `unknown`（**不猜**） | 跳转表夹具：产出 `unknown` 而非假边 |
| R82-A6 | 站点/报告新增「异步」列 + 「未识别并发站点」计数 | 站点 HTML 里 async 边**视觉可区分**；计数分母 = 扫描到的并发关键字节点数 |

**Phase A 出口判据**：边数守恒恒等式在**整树内核语料**上成立；`async` 边数 > 0；
两向变异 5/5。

### Phase B · T2 二进制符号图并入调用图

| ID | 任务 | 验收判据 |
|---|---|---|
| R82-B1 | `binhops.py`：`Hop` 构造 + `HOP_DEVICES` 登记 | 未登记的 `via_device` ⇒ 红 |
| R82-B2 | ELF/PE/Mach-O **符号 → 图节点** 导出 | 真实 `.so`/`.dll` 上：导出符号数 == 二进制里 `symbols` 数（逐位对账） |
| R82-B3 | MEX 桥升级：`mexFunction` **形状**锚点（新键 `c_bridge_v2`） | 旧 `c_bridge` **逐位不变**（兼容基线）；`c_bridge_v2` 含 hop |
| R82-B4 | 多跳链构造 + 差集分类（4 类） | `kind="unresolved"` 每类有分母；`chain` 每跳有装置 |
| R82-B5 | 站点/报告新增「二进制链路」视图 | 5 跳链在真实 `.mexw64` 或合成 ELF 上可走通并渲染 |

**Phase B 出口判据**：`unresolved` 的四类分母齐；「每跳有装置」两向变异；旧键逐位不变。

### Phase C · T3 源侧算子评估

| ID | 任务 | 验收判据 |
|---|---|---|
| R82-C1 | `gpu_kernels.py`：`__global__` 定义提取（新词法） | 含宏包装的夹具能识别；宏展开不了的 ⇒ `unevaluated` + 分母 |
| R82-C2 | `<<<g,b,s,st>>>` 启动配置解析（括号配平 + `dim3`） | `<<<dim3(a,b), dim3(c,d), smem, stream>>>` 必须支持；解析不出 ⇒ `unevaluated` |
| R82-C3 | ptxas 报告解析（用户显式提供时才跑） | 夹具报告解析出寄存器/共享内存；**缺该文件 ⇒ 不产出任何数字**（不是 0） |
| R82-C4 | 三处对齐（源码 `S` / 启动 `L` / 二进制 `B`） | `L-S` 与 `S-B` **分类报告**；`loose >= strict` 写成断言 |
| R82-C5 | `estimated` 标注 + `bound_by` 瓶颈资源 | 估算与确定**分列**；删掉 `bound_by` ⇒ 红 |
| R82-C6 | R79 遗留：m68k 点号省略指令归数据段（整树 3,528 条） | 整树 `insn_top` 里 `short`/`long` **不再出现**；数据段计数上升 3,528 |

**Phase C 出口判据**：三处对齐有差集分母；`estimated` 可识别；整树回归里 `insn_top` 干净。

### Phase D · T4 规则驱动的 C ↔ MATLAB 互转

| ID | 任务 | 验收判据 |
|---|---|---|
| R82-D1 | `translate/rules.py`：规则表 schema + 版本 + 加载 | 未命中规则可红；命中未登记 ID ⇒ 红 |
| R82-D2 | C → MATLAB 确定性段（标量循环/数组/索引基准/基本 I-O） | 每个已实现规则**有一个夹具 + 一个反例** |
| R82-D3 | MATLAB → C 确定性段 | 同上（方向对称） |
| R82-D4 | AI 段接入 `ai_cli` + 回流 `matlabc_flow` | `--dry-run` 默认；AI 失败 ⇒ 降级为「只出 unmapped 报告」而**不崩** |
| R82-D5 | `fidelity.py` **双语对照执行器** | 无 runner ⇒ `unverified`（**默认姿态**）；有 runner ⇒ 容差内相等才是 `verified` |
| R82-D6 | `tests/test_translate_fidelity.py`（真跑，进 `tests/`） | 至少 3 组样例两侧真执行并比对；**造一个故意不等的翻译 ⇒ 必须 `failed`** |
| R82-D7 | 报告：`verified/unverified/failed` 三分列 + runner 口径 | 缺 runner 名 ⇒ 红 |

**Phase D 出口判据**：三分列齐全；「造一个不等 ⇒ 必须 failed」这条**独立**验证通过（这是全方案最关键的判据）。

### Phase E · T5 自治演进闭环

| ID | 任务 | 验收判据 |
|---|---|---|
| R82-E1 | `evolve.py`：`EVOLVE_TARGETS` 注册表（4 类） | 未登记目标 ⇒ 红；**从未被触发的目标** ⇒ 红（§4k-2） |
| R82-E2 | 目标 T-STATIC 接线（复用 `agent_loop`） | 告警数下降才接受（已有判据） |
| R82-E3 | 目标 T-DOC 接线（doc 数字 vs 真值） | 造一个文档漂移 ⇒ 目标变红并可被收敛 |
| R82-E4 | 目标 T-TRANS 接线（T4 的 `unverified` 集合） | `unverified` 变小**且** `verified` 不减少才接受 |
| R82-E5 | 目标 T-COVER 接线（T1/T2/T3 差集） | 差集总量下降才接受；每类差集有分母 |
| R82-E6 | `--evolve` CLI + 记账 + 回退 + MCP 工具扩展 | 拒绝后工作区与基线 **sha256 逐文件相等**；MCP 工具清单与真实 CLI **两向对账** |

**Phase E 出口判据**：`--evolve` 在无人干预下完成「分诊→改动→自证→记账」，且**所有拒绝都真正回退**。

### 进度台账

| ID | 状态 | 判据两向变异 | 备注 |
|---|---|---|---|
| _（全部从 ⬜ 起）_ | | | |

---

## 9. skill 联动矩阵

| skill | 在哪一段用 | 具体作用 |
|---|---|---|
| `superpowers` | §1–§7（本文档） | 六顶思考帽：把「需求 → 现状 → 缺口 → 方案」拆成互不干扰的六个视角 |
| `superpower-probe-loop` | Phase 0–E **每一轮** | 隔离探针先跑真实 API → 断言落在真实结果上 → 登记制护栏锁死 → 下一轮。**本方案的验收判据全部按它的形态写**（恒等式而非阈值、分母必报、两向变异、先装闸门看它当场红） |
| `loop-engineer` | Phase E | 闭环迭代与**退出条件**：达标即停、遇不可自证转人工 |
| `isa-decode-lift-matrix` | Phase B/C | ELF/PE/PTX/SASS 的**解析组件与许可证判据**；「支持所有架构」的选型不靠猜 |
| `inline-asm-fact-extraction` | Phase A（asm 侧）/ C（kernel 侧） | 内联汇编的操作数约束、clobber、屏障缺失——**异步/内存序缺陷常在这里** |
| `external-doc-integration-audit` | Phase C/D | 把 ptxas 报告格式、CUDA occupancy 文档、MEX API 文档**搬进项目时的取经纪律**（认装置不认叙述） |
| `deep-research` | Phase D 前置 | MATLAB 与 C 的语义差异（索引基准、列主序、隐式扩展、整数溢出语义）需**多源交叉验证**后写进规则表 |
| `systematic-debug` | Phase E（T-STATIC） | bug 分析的四阶段根因：复现 → 隔离 → 定位 → 验证 |
| `self-improving` | 每轮收尾 | 复盘沉淀：新纪律回写 skill，避免下一轮重踩 |
| `fireworks-tech-graph` | 本文档与后续 | 架构图/DFG/CFG 生成（本项目 `flow/` 图册的既有工具链） |

---

## 10. 诚实边界（写在方案里，防止过度承诺）

1. **不做真正的 occupancy 计算**：需要 SASS + 目标架构 + 延迟表；本方案只报**可得的量**
   （启动配置、ptxas 的寄存器/共享内存），occupancy 一律 `estimated` + `bound_by`。
2. **不做反汇编/反编译**：`binfmt` 明确「不做反汇编、不做重定位」，本方案**不放开这条**。
   T2 的 hop 全部来自**符号表与依赖表**，不是代码理解。
3. **不保证任意 C ↔ MATLAB 互转**：只覆盖**有规则**的子集；没规则的进 `unmapped`/`unverified`。
   **工具的诚实输出 = 差异报告**，不是「翻译好了」。
4. **不自动改用户的代码**：`--evolve` 与互转**默认不落盘**。
5. **不承诺一次性交付**：5 条线分 6 个阶段，每阶段独立验收（K9）。
6. **Windows 优先但不断言跨平台**：`octave`/`matlab`/`cc` 的可用性按本机实测声明口径。
7. **`unknown` / `unevaluated` / `unverified` 是**一等状态**，不是错误**：它们**必须可见且有分母**，
   这才是「准确评估」的真实含义。

---

## 11. 下一步建议

1. **立刻做 Phase 0**（护栏与模型先行）——它是唯一「不做就白做」的一步：
   统一图模型若晚定稿，T1–T4 会各自长出一套边表示，之后要拆两遍。
2. **Phase 0 之后做 T1（异步）**，因为它给图加的是**边的种类**——T2/T3/T4 都要用它。
3. **术语修复（R82-0-1）与 Phase 0 同批**，成本最低、收益立现。
4. **把「差集」当一等产物**贯穿始终：每条线都要回答「我没识别什么、为什么、分母多少」。
5. **MCP 工具与 CLI 同步扩张**：每完成一条线就扩 `matlabc_mcp.py`，并用
   「工具清单 ↔ 真实 argparse 开关」**两向对账**（本仓已有可执行先例）。
