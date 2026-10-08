# SUPERPOWER_REVIEW_R31 —— 二进制 / GPU 接入 · 子进程卫生 · 会挂死的门

> 方法论：superpower-probe-loop —— **六顶思考帽 → 逐条真落地 → 隔离探针先跑真实文件 →
> 登记制护栏 → 下一轮**。探针一律放仓库外（`E:\matlabc\_r31\`），不污染 git 工作区。
> 本文只记录**有实测证据**的结论；没有证据的推测一律标注为「未验证」。

---

## §0 结论先行

本轮一句话：**把「源码侧说了有个调用解析不出来」补成「这个名字到底归谁」**，
并顺手修掉一个会**让整套质量门永远挂住**的真缺陷。

| # | 事项 | 性质 | 证据 |
| --- | --- | --- | --- |
| K1 | `tools/check_doc_flags.py` 实测耗时 **~181s**（被外层 `timeout 90` 杀掉，表现为「无故卡住」） | **真缺陷** | 探针 `probe_r26b_pipe`（含重跑对照）；修后 **3.4s** |
| K2 | `tools/check_all.py` 的 `subprocess.run` **既没切 stdin 也没 timeout** | **真缺陷** | AST 普查 `probe_r27_subprocess`；一个不退出的护栏会让 CI 永远等 |
| K3 | `matlabc_mcp.py::_run` spawn 的子进程**继承 MCP 的 JSON-RPC stdin** | **真缺陷（正确性，非仅挂死）** | 同源实测：`matlabc_mcp.py --help` 继承 stdin 时 >30s 不返回，切断后 0.5s |
| K4 | 全仓 42 处「捕获输出 + 无 timeout」，其中 14 处在运行时脚本 | **真缺陷（成组）** | `probe_r27_subprocess` 全表；已逐点修 + 立登记制护栏 |
| K5 | 新增二进制 / GPU 分析能力（PE·ELF·Mach-O；CUDA·ROCm·Vulkan） | 新能力 | 真实语料实测，见 §1 |
| K6 | `matlabc.py` 模块 docstring 只讲 MATLAB，与项目实际能力**不一致** | 文档失真 | `--help` 的 epilog 即 `__doc__`；已重写为任务导向 |
| K7 | 我自己在落盘测试时**两次**损坏文件（行尾 + 转义） | 自伤 | `fix_crlf_tests.py` / `fix_rawbyte_tests.py` 留档，见 §2.3 |

---

## §1 白帽：事实清单（全部来自真实文件实测）

### 1.1 全仓对二进制分析原本零覆盖

严格词边界搜索 `\bELF\b` / `dlopen` / `dlsym` / `LoadLibrary` / `cubin` / `fatbin` /
`PTX` / `amdgcn` / `hsaco` / `__global__` / `<<<` / `spirv` —— **全部 0 命中**。
先前看到的「`.so` 117 处、`hip` 62 处」是 `.source` / `.sort` / `.sort_keys` 的**子串误报**。
教训：**子串搜索不是证据**，必须加词边界。

### 1.2 PE 段名 8 字节硬截断（本轮最有价值的实测发现）

| 逻辑名（ELF 里） | 落到 PE 里的名字 | 后果 |
| --- | --- | --- |
| `.nv_fatbin` | **`.nv_fatb`** | 只认完整拼写的匹配器在**每一个 Windows 二进制**上报「零 GPU 内容」 |
| `.nvFatBin` | **`.nvFatBi`** | 同上 |
| `.hip_fatbin` | **`.hip_fat`** | 同上 |
| `.hipFatBin` | **`.hipFatB`** | 同上 |
| （Vulkan） | **无专用段** —— SPIR-V 躲在 `.rdata` | 只能靠裸魔数扫描 |

### 1.3 CUDA cubin 不是标准 ELF

`e_type = 0x8000`、`e_machine = 0x100`、`e_shoff` 落在 `0xCAFE…` 哨兵值。
唯一可信判别：`e_ident[7] == 0x33`（`ELFOSABI_CUDA` = 51）+ `e_ident[8]`。
因此「数 `\x7fELF` 出现次数」只是**便宜**信号，与**严格**信号分开命名：
`suspect_code_objects` vs `confidence_code_objects`。**便宜判据不许冒充精确结论。**

### 1.4 CUDA kernel 名的真实存放处

不在 PTX 里，在 **cubin 的节名表**：形如 `.text._ZN6cublas19splitKreduce_kernelI…`。
扫 `.text._Z` 即可，**不需要反序列化 cubin**。

| 真实库 | `.text._Z` 提出的独立 kernel 名 | 可 demangle |
| --- | --- | --- |
| cuBLAS 12 | **171** | 171/171 |
| cuBLASLt 12 | **59** | — |

样例：`dot_kernel<…>`、`ger_kernel<…>`、`syr_kernel<…>`、`asum_kernel<…>`、
`copy_kernel<…>`、`gbmv_kernel<…>`、`_ZN6cublas19splitKreduce_kernelI…`。

### 1.5 PTX 路径基本是死的

`.visible .entry ` 有 347 个命中，但要求**名字后随左括号**（真 entry 形态）后，
只剩 **1–2 个**；其余全是二进制元数据。结论：**PTX 提不出 CUDA kernel 名**，如实报告。

### 1.6 其余厂商

* **AMD `.hip_fat`**：1096 个可信 HSA code object（`e_ident[7]` = 64）；kernel 名**不猜**。
* **Vulkan**：修掉 `OpEntryPoint` 名字偏移 bug 后，1477 个模块全叫 `main`（GLCompute）
  —— 已去重并把「模块数」单列，不把它伪装成 1477 个不同算子。

### 1.7 本机环境事实（本轮再次确认）

* `readelf` / `nvcc` / `cuobjdump` / `hipcc` / `pyelftools` / `capstone` **全部不可用**；
  WSL 被安全策略黑名单禁用 → 独立验证只能靠**差分测试**与**手工构造夹具**。
* `pytest` 只装在**系统 Python 3.10.10**（9.0.1）；管道的 3.13.12 里没有。

---

## §2 黑帽：真缺陷分级

### 2.1 K1 —— 一道「不会报错、只会卡住」的门（严重度：高）

**现象**：`check_doc_flags.py` 打印 OK 之后看起来不退出，被外层 `timeout 90` 杀掉（rc=124）。

**第一次的误读（必须留档）**：我一度判定为「四个脚本在捕获输出 + 继承 stdin 时全部挂死」。
**重跑对照后推翻**：

| 脚本 | stdin 继承 | `stdin=DEVNULL` |
| --- | --- | --- |
| `matlabc.py --help` | rc=0 **0.8s** | rc=0 0.8s |
| `matlabc_flow.py --help` | rc=0 **0.5s** | rc=0 0.5s |
| `matlabc_ask.py --help` | rc=0 **0.5s** | rc=0 0.5s |
| **`matlabc_mcp.py --help`** | **TIMEOUT >30s** | rc=0 **0.5s** |

**真正的因果链**：旧 `_help_options` 用 `subprocess.run(capture_output=True)`（stdout/stderr=PIPE、
**stdin 继承**）**按 `SCRIPTS` 顺序串行**问 4 个脚本。前 3 个各 0.7s，第 4 个 `matlabc_mcp.py`
是 stdio JSON-RPC server（设计上就读 stdin），在继承来的、永不 EOF 的管道上阻塞到它自己的
**180s 内建超时** ⇒ 护栏实测 ≈ **181s** > 外层 `timeout 90` ⇒ rc=124。
「打印 OK 后挂住」是**顺序错觉**（stdout 缓冲），它其实**并没有**在打印后卡住。

**修法**：`stdin=DEVNULL` + 改写临时文件（不收 PIPE）+ `kill()`/`wait()` 收尸 +
`HELP_TIMEOUT` 180s → 60s。**结果：3.4s。**

### 2.2 K2/K3/K4 —— 同一根因的其余落点

* `check_all.py::run_guards`：`subprocess.run(stdout=PIPE)`，**无 timeout、无 stdin**。
  → 加 `stdin=DEVNULL` + `GUARD_TIMEOUT=600`，**超时判红**。
* `matlabc_mcp.py::_run`：子进程继承 **MCP 的 JSON-RPC stdin**。
  这不仅是挂死风险，更可能**偷走协议字节**（静默协议损坏，比崩溃更难查）→ 必须 `DEVNULL`；
  收尸 `communicate()` 也补 `timeout=30`（否则 Windows 上变成新的挂死点）。
* 全仓 14 处运行时捕获点逐点补齐（`agent_loop._run_git/_run_gh` 尤其重要：
  `gh` 是**交互式**的，未认证时会读 stdin 提问）。

### 2.3 K7 —— 我自己的两次自伤（必须写下来）

1. **行尾**：用 bash 内联 python 追加测试时，`io.open(encoding='utf-8')` 读入按
   universal-newline 把 CRLF 归一成 LF，再以 `newline=''` 写出 ⇒
   **整份 `tests/test_matlabc.py` 15820 行全变裸 LF**。
   用 `fix_crlf_tests.py` 还原；复核 `git diff --numstat` = `146 增 / 0 删`（干净）。
2. **转义**：同一命令里反引号被 shell 当**命令替换**执行 → docstring 里
   `` `--help` ``、`` `matlabc_mcp.py` `` 等被吃掉；`\n` 变成真实换行；`\x90` 变成
   U+0090 的 UTF-8 编码（`C2 90`），使 `ast` 直接拒绝该文件。
   用 `fix_rawbyte_tests.py` 做**字节级**修复，且**修复前先 `ast.parse` 自检**。

**教训（已可复用）**：**落盘代码块必须写纯文本文件 + `ast.parse` 自检后再写**，
禁止经 shell 内联字符串传递含反引号/转义的内容。本仓既有约定里已写过这条，
本轮是**第二次**踩，故升级为硬规则写进复盘。

---

## §3 黄帽 / 绿帽：新能力

* **`binfmt/` 包**（零依赖，10 个模块）：统一 IR + PE/ELF/Mach-O 容器解析 +
  CUDA/ROCm/Vulkan GPU 内容提取 + **归因层** + 构建系统提示 + 文本报告。
* **4 个 CLI 开关**：`--binary` / `--binary-symbols` / `--binary-json` / `--binfmt-scan-cap`，
  与 `--benchmark` 同属「单次任务」型短路分发（分析后即退出）。
* **归因三态**：`library`（由某库导出解释）/ `gpu_kernel`（是 GPU 算子）/ `missing`（真没有来源）。
  实测输出：`attribution summary: library=1  missing=1`。
* **两处「便宜 vs 严格」分字段命名**，从命名上就杜绝混淆。

---

## §4 蓝帽：架构与不变量

```
matlabc.py --binary ──► binfmt.container.sniff/parse
                          ├─ pe.py  elf.py  macho.py      （容器层）
                          ├─ gpu.py                        （GPU 内容层）
                          │    ├─ .nv_fatb/.nvFatBi → fatbin → .text._Z 节名表
                          │    ├─ .hip_fat/.hipFatB → HSA code object
                          │    └─ magic 兜底 → SPIR-V OpEntryPoint
                          ├─ buildsys.py                   （Makefile/CMake 提示）
                          ├─ report.py                     （不隐藏负面状态）
                          └─ attribute.py                  （唯一目的：归因）
                                   ▲
matlabc --json out.json ───────────┘  （unresolved / 纯文本 / c_model 三态容忍）
```

**四条不变量（已由护栏守门）**

1. **「不可解析」是一等状态**：`parseable=False` 必须带非空 `reason`；禁止静默 0 kernel。
2. **元表与未实现表交集为空**：`check_operator_impl.py`。
3. **补丁算子 ⊆ `['del','ins_before']`**：`check_patch_ops.py`（防「覆盖式删源码」）。
4. **捕获输出必须切 stdin + 带超时**：`check_subprocess_hygiene.py`（本轮新增）。

---

## §5 30 轮账本

| 轮 | 内容 | 产出 |
| --- | --- | --- |
| R1–R4 | 全仓零覆盖普查、真实 GPU 语料定位（7 个文件，最大 692 MB）、段名/魔数实测 | `probe_r1_facts` |
| R5–R8 | cubin 头语义、PTX 名形态、SPIR-V OpEntryPoint、严格 vs 便宜判据 | `probe_r2/r5/r6/r7/r8`（抓出我 3 个 bug） |
| R9 | **突破**：`.text._Z` 节名表 → cuBLAS 171 / cuBLASLt 59 个 kernel 名 | `probe_r9_cubin_names` |
| R10–R14 | `binfmt/` 容器层：`model` `pe` `elf` `macho` `container`（含 2 处真 bug 修复） | 10 个模块 |
| R15–R19 | GPU 层 `gpu.py`：fatbin/cubin/HSA/SPIR-V + demangle + 截断标注 | 实测 6 个真实库 |
| R20 | 归因层 `attribute.py` + 构建系统 `buildsys.py` + 报告 `report.py` | 归因三态跑通 |
| R21–R23 | CLI 接入（4 开关 + 短路分发 + JSON `sort_keys`） | 端到端 rc=0/2 契约成立 |
| R24–R25 | `check_binfmt_fixtures.py` 护栏 + 两向自证（`{"bad":3,"good":2}`） | 契约 C1–C6 |
| **R26** | **修 K1**：`check_doc_flags` 挂死；重跑对照推翻我自己的第一版结论 | 181s → **3.4s** |
| **R27** | **K2/K3/K4 全仓普查与修复** + 新护栏 `check_subprocess_hygiene.py` | 自证 `{"bad":7,"good":4}` |
| **R28** | `matlabc.py` docstring 重写为任务导向（`--help` 37769B → **29293B**）+ `--binary` 帮助改人话 | 冒烟 rc=0 |
| **R29** | 6 个 `test_r31_*` 回归 + 行尾/转义两次自伤修复 + 全量回归 + 公平基线 | `413` 个测试 |
| **R30** | README 中英图文并茂更新 · LICENSE 贴近项目 · 归档 · 入库 | 见 §6/§7 |

---

## §6 质量门清单（本轮结束态）

```
$ python tools/check_all.py
[OK  ] check_binfmt_fixtures.py     契约 C1–C6 全部通过
[OK  ] check_doc_flags.py           3 份文档的开关全部存在于 --help
[OK  ] check_operator_impl.py       元表 9 个 kind 全部有产出点；两表交集为空
[OK  ] check_patch_ops.py           算子 ⊆ ['del','ins_before']
[OK  ] check_subprocess_hygiene.py  捕获点 14 全部切 stdin；Popen 2 + 盲区 2 全部登记
check_all: OK（5 个护栏，全部通过且各自自证）
```

| 护栏 | 自证计数（下界断言用） | 新增能力 |
| --- | --- | --- |
| `check_doc_flags.py` | `{"bad":6,"good":7}` | **登记表可证伪**：`NO_HELP_SCRIPTS` 成员必须「rc=0 且输出为空」，否则登记失效 |
| `check_all.py` | `{"bad":0,"good":5}` | **第 ⑤ 项：永不退出的护栏必须被超时判红**（3s 超时造挂死样本） |
| `check_subprocess_hygiene.py` | `{"bad":7,"good":4}` | S1 切 stdin · S2 带 timeout · S3 Popen 登记 · **S4 `**kwargs` 盲区登记** |

**S4 值得单说**：`matlabc_mcp.py::_run` 的 `stdout=PIPE` 藏在 `**kwargs` 字典里，
静态扫描**看不见**它 —— 而它恰好是最关键的一点。如果不管，「看不见」就会被当成「没问题」。
现在这类点必须登记在 `UNVERIFIABLE` 并写明理由，且**两张登记表都做两向核对**
（代码里有而未登记 → 抓；登记了而代码里已没有 → 也抓，防陈旧登记掩盖新增点）。

---

## §7 公平基线对照

**方法**：`git archive HEAD` 把**未改动**的树导出到仓库**外**（`E:\matlabc\_r31\baseline_head`），
用**同一个解释器**（系统 Python 3.10.10 / pytest 9.0.1）+ **同一个测试文件**重跑。
不看绝对值，只看**增量** —— 因为基线自己就不绿。

| 树 | 结果 |
| --- | --- |
| **HEAD 基线（未改动）** | **124 failed, 274 passed, 9 skipped**（947s） |
| **当前工作树** | **124 failed, 280 passed, 9 skipped**（1115s） |

> **为什么必须做这一步**：只看「当前树有多少个失败」无法区分**是我改坏了**还是**本来就红**。
> 实测证明：本仓回归套件在 HEAD 上已有 124 个失败 —— 若不做对照，任何数字都无法解释。

**实测记录（本轮结束时填写）**

```text
基线树来自 HEAD^{tree} = 96b3289725868067b5e20524b03d15a2ee5dbd41
基线导出到 E:\matlabc\_r31\baseline_head（仓库外）
run_fair_baseline.py 用 git archive 导出两棵树，同一解释器、同一测试集各跑一次

[HEAD 基线（未改动）] rc=1  947s   124 failed, 274 passed, 9 skipped
[当前工作树]           rc=1 1115s   124 failed, 280 passed, 9 skipped

失败数  124 -> 124   （增量 0，零新增失败）
通过数  274 -> 280   （增量 +6，恰为新增的 6 个 test_r31_*）
```

**结论（增量口径）**：

| 指标 | HEAD 基线 | 当前工作树 | 增量 | 解释 |
| --- | --- | --- | --- | --- |
| failed | 124 | 124 | **±0** | 本轮**未新增任何失败**；124 个是 HEAD 上就存在的历史失败 |
| passed | 274 | 280 | **+6** | 恰为 `test_r31_*` 六个新测试，全部通过 |
| skipped | 9 | 9 | ±0 | 与改动无关 |

**四条必须同时说的限定语**（否则这个数字会被误读）：

1. **基线自己就不绿**（124 failed）。本仓回归套件在 HEAD 上就有大量
   `ModuleNotFoundError` / `FileNotFoundError` 型失败（多为按目录存在性、
   可选依赖、平台判定而跳过/报错的用例）。所以「124」不是「124 个 bug」，
   而是「124 个在**两棵树里同样发生**的结果」。
2. **只有增量为零才是结论**。`124 -> 124` 能证明「我没改坏」；
   它**不能**证明「那些失败被修好了」—— 本轮没打算修它们。
3. **耗时不可比**（947s vs 1115s）：当前树多跑 6 个测试，且新增护栏本身
   要起子进程；这不是性能退化。真正的性能改善在别处（`check_doc_flags`
   由 181s 降到 3.4s，见 §6）。
4. **公平性来自「两棵树各自导出」**：`git archive HEAD^{tree}` 把未改动树
   导到仓库外，用同一解释器与同一测试集重跑。若在同一工作区用
   `git stash` 之类做法，两侧会被同一套行尾/忽略规则归一化，对照就失效了
   —— 这与「`git diff` 不能作为推送验证工具」是同一条教训。

<!-- BASELINE_RESULT -->

---

## §8 附录 A：探针清单（仓库外，不进 git）

| 探针 | 回答的问题 |
| --- | --- |
| `probe_r1_facts.py` | 段表 + 内容命中计数；首次发现 `.nv_fatb`/`.nvFatBi`/`.hip_fat`/`.hipFatB` |
| `probe_r2_semantics.py` | cubin 头、PTX 名、SPIR-V OpEntryPoint（抓出我 2 个 bug） |
| `probe_r5_selfcheck.py` | 真实文件端到端自检（修复前后对比） |
| `probe_r6_entry_shape.py` | 验证「entry 后随 `(`」/「SPIR-V 名字从 word[3]」 |
| `probe_r7_count_check.py` | 查清 348 vs 5 计数矛盾 —— **是我自己 `limit=5` 未标注截断** |
| `probe_r8_strict.py` | 严格判据下 PTX 只剩 2 个 kernel ⇒ PTX 路径基本死了 |
| `probe_r9_cubin_names.py` | **重大突破**：`.text._Z` → cuBLAS 171 / cuBLASLt 59 |
| `probe_r26_hang.py` / `probe_r26b_pipe.py` | 定位并**重跑推翻**第一版挂死结论 |
| `probe_r27_subprocess.py` | AST 普查 52 个 subprocess 调用点的卫生属性 |
| `probe_r27b_minimal.py` | 决定性最小实验：继承 stdin 是否普适致挂（**否**） |
| `fix_crlf_tests.py` | 还原被我改成 LF 的 15820 行 |
| `fix_rawbyte_tests.py` | 字节级修复 `C2 90`，修复前先 `ast.parse` 自检 |
| `normalize_crlf.py` | 26 个改动文件的行尾统一与复核 |
| `run_fair_baseline.py` | 全量回归 ×2 + 对照表 |

---

## §9 C'1–C'10：下一次建设性意见

> 排序依据：**先补「会被误读为通过」的洞，再补能力**。每条都给出可执行的验证方式。

1. **C'1 把「124 个失败」变成一张账。** 基线不绿意味着**质量门本身没有信用**。
   先跑一次全量、把 124 条失败按「真缺陷 / 环境相关 / 断言的期望已过期」三类归档，
   产出 `docs/analysis/FAILING_TESTS_TRIAGE.md`；再为「环境相关」的加 `skipif` 并写明理由。
   *验证*：`pytest -q` 的 failed 数能被逐条指向一份文档里的条目。
2. **C'2 让 `check_all.py` 覆盖 `tests/` 的卫生。** 现在 30 个 tests 捕获点被显式排除。
   建议给 `tests/` 单独一道**宽判据**：禁止 `capture_output=True` 且不带 timeout
   （pytest 已被外层 harness 管 stdin，但 timeout 仍值得要）。
   *验证*：把某条测试的 `timeout=` 删掉，新护栏必须变红。
3. **C'3 `.text._Z` 之外的 CUDA 名来源。** 目前只扫节名表；`.nv.info` / `.nv.global`
   与 cubin 的 `.symtab` 可能还有未提取的名字。先做**探针**（不改代码）统计增益再决定。
4. **C'4 把 AMD kernel 名提出来。** 现在只给 HSA code object 计数、**不猜名字**。
   下一步应是：定位 HSA code object 的 `.symtab`/`msgpack` 元数据，先写探针证明能提出
   可解释的名字，再实装。**在探针给出正例前不进代码**（避免走过 PTX 那条死路）。
5. **C'5 二进制分析接进 MCP。** 新增一个 `matlabc_binary` 工具，让 agent 能自己
   「先看源码 unresolved → 再去库文件里对账」，形成闭环。
   *验证*：`test_r30_mcp_run_reports_returncode` 同款方式加一条端到端。
6. **C'6 归因接进报告。** 把 `library` / `gpu_kernel` / `missing` 三态写进 `--output`
   的主报告，而不是只在 `--binary-symbols` 时打印 —— 否则「源码侧未解析」这条信息
   在单独跑源码分析时依然是死的。
7. **C'7 Mach-O 必须有真语料才能摘掉 ⚠。** 现在解析器已实现但**未验证**，
   报告里明确标了。下一步要么找到样本、要么把这个模块降级为「实验性」并在
   `--binary` 帮助里点名。**不允许把未验证当已验证。**
8. **C'8 前端外挂化（承 R30 路线 D→B）。** `binfmt/` 已经证明「新能力做成独立包 +
   登记制护栏」这条路可行；把 C/Py/JS 前端按同样方式搬进 `frontends/` + 统一 IR，
   是当前最高杠杆的重构。**先做 `--lang` 的回归基线，再动。**
9. **C'9 把「探针先行」写进 CONTRIBUTING。** 本轮两次自伤（行尾、转义）与一次误读
   （挂死因果）都是**流程缺失**，不是能力问题。把「探针放仓库外 / 落盘先 `ast.parse` /
   测量工具自身的 bug 会伪造被测对象的 bug」三条写进 `CONTRIBUTING.md` 的硬规则。
10. **C'10 GPU 内容与「未解析调用」的双向校验。** 现阶段归因是单向的（源码 → 二进制）。
    反向更有价值：**二进制里有、而源码从没调用过**的导出，可能是死依赖 ——
    这对「裁剪依赖 / 供应链收敛」是直接可用的结论。

---

## §10 明确拒绝做的事（避免下一轮走回头路）

1. 把 `rea` 做成**必需依赖**（只做可选、可缺席、优雅降级）。
2. 移植 rea 的 TS 源码。
3. 自研完整 C++ / Rust 类型系统。
4. 原地正则扩语言（历史路线，已否决）。
5. 为 PTX 路径继续加特例 —— 实测证明它提不出名字，**止损**。
6. 在探针给出正例之前，把「猜出来的」AMD kernel 名写进代码。
