# 二进制文件分析 × malabc 融合方案（含 CUDA / AMD GPU 算子）

- 日期：2026-10-08
- 方法：六顶思考帽（白→红→黑→黄→绿→蓝）+ 隔离探针实测
- 探针位置：`E:\matlabc\_r31\`（仓库外，不污染 git 工作区）
- 语料：本机真实 GPU 二进制（Ollama 发行包），非构造样本

---

## 0. 结论先行

**要做的不是「给 matlabc 加一个 `--binary` dump 工具」，而是把二进制变成「未解析调用的归属证据」。**

本项目已有的核心概念是「未解析调用」（`renderers/unresolved.py`）与「算子目录」（`_CROSS_LANG_KIND_META`）。
源码侧看到一个调用却找不到定义时，今天只能说「未解析」——它把三件完全不同的事混成了一个桶：

| 今天的桶 | 实际可能是什么 | 二进制分析能否分开 |
| --- | --- | --- |
| 未解析调用 | 来自外部动态库（`cublasSgemm` ← `cublas64_12.dll`） | ✅ 能 |
| 未解析调用 | 来自 GPU kernel（`ggml_cuda_mul_mat_q4_0` ← fatbin 里的 PTX entry） | ✅ 能 |
| 未解析调用 | 真的漏了（既无源码也无库） | ✅ 能（排除法） |

**所以本轮的接入点是「归属」（attribution），不是「反汇编」。**

### 一个必须先澄清的术语冲突

| 词 | 本项目现有含义 | GPU 语境含义 |
| --- | --- | --- |
| **算子 / operator** | 「跨语言检测规则」的 kind（`py_eval_usage`、`c_double_free`…），登记在 `_CROSS_LANG_KIND_META` | GPU **kernel**（`conv2d`、`softmax` 的 device 实现） |

这两个含义完全不同，混淆会污染现有算子目录。**本方案在代码与文档中一律用 `kernel` 指 GPU 算子，保留 `kind` / `check` 指检测规则。**
用户所说的「CUDA 和 AMD 的算子」= CUDA kernel 与 AMD (ROCm/HIP) kernel，本报告统称 **GPU kernel**。

---

## 1. 【白帽】事实与数据

白帽纪律：只写实测得到的、可复现的数字。**不写文档里抄来的魔数。**

### 1.1 探针方法

在真实文件上跑 `struct` 级解析，**只 seek 读头部**，不整文件加载（最大文件 692 MB）。
两个探针：`probe_r1_facts.py`（段表 + 内容命中计数）、`probe_r2_semantics.py`（语义精确解析）。

### 1.2 真实语料清单

| 厂商 | 文件 | 大小 | 容器 |
| --- | --- | --- | --- |
| NVIDIA CUDA 12 | `cuda_v12\ggml-cuda.dll` | 349.7 MB | PE (AMD64) |
| NVIDIA CUDA 12 | `cuda_v12\cublas64_12.dll` | 113.7 MB | PE |
| NVIDIA CUDA 12 | `cuda_v12\cublasLt64_12.dll` | 692.4 MB | PE |
| NVIDIA CUDA 13 | `cuda_v13\ggml-cuda.dll` | 132.4 MB | PE |
| AMD ROCm 7.1 | `rocm_v7_1\ggml-hip.dll` | 504.8 MB | PE |
| AMD ROCm 7.1 | `rocm_v7_1\rocblas.dll` | 41.1 MB | PE |
| Khronos | `vulkan\ggml-vulkan.dll` | 41.7 MB | PE |

### 1.3 事实 F1：PE 段名被 8 字节硬截断，且三家厂商各不相同

PE 的 `IMAGE_SECTION_HEADER.Name` 只有 **8 字节**。厂商想用的长名字全部被截断，
而截断方式**不是简单的前 8 字符**：

| 厂商 | 想用的名字 | 实际落盘段名 | 段大小 |
| --- | --- | --- | --- |
| CUDA | `.nv_fatbin` | **`.nv_fatb`** | 334,921,016 B |
| CUDA | `.nvFatBin` | **`.nvFatBi`** | 3,432 B |
| AMD HIP | `.hip_fatbin` | **`.hip_fat`** | 491,254,728 B |
| AMD HIP | `.hipFatBin` | **`.hipFatB`** | 3,288 B |
| Vulkan | — | **无专用段**（躲在 `.rdata`） | 40,605,094 B |

> **黑帽预警**：如果按文档直觉写 `.nv_fatbin`，在所有 Windows PE 上**永久失配且静默返回 0**。
> 这条只有跑真实文件才能发现。

### 1.4 事实 F2：fatbin wrapper 魔数 = `0xba55ed50`

`.nv_fatb` 段起始 32 字节（ggml-cuda.dll）：

```
50 ed 55 ba | 01 00 10 00 | e8 1c 03 00 | 00 00 00 00
0xba55ed50  | ver 0x00100001 | hdrSize=204008 | 0
```

### 1.5 事实 F3：`.nvFatBi` 是 24 字节定长条目表，条目魔数 `0x466243b1`

```
b1 43 62 46 | 01 00 00 00 | 00 30 e3 80 01 00 00 00 | 00 00 00 00 00 00 00 00
0x466243b1  | type=1      | VA=0x180e33000           | flags=0
```

`0x180e33000` 是 PE ImageBase(0x180000000) + RVA，即 **条目指向的 cubin 的虚拟地址**。
条目按 24 字节等距排列（`.nvFatBi` 3584 B ≈ 149 条；cublas64 4800 B = 200 条整）。

### 1.6 事实 F4（重要）：CUDA cubin **不是标准 ELF**，不能当 ELF 解析

同一个 `\x7fELF` 起点，按标准 ELF64 偏移解析得到：

```
e_type    = 0x8000        ← 不是 ET_NONE/REL/EXEC/DYN/CORE 任一个
e_machine = 0x0100 (256)  ← 不是 EM_CUDA(190)，也不是任何已分配值
e_shoff   = 0xCAFE...     ← 哨兵值，不是偏移
e_ident[7] = 0x33 = 51 = ELFOSABI_CUDA   ← 这个是真的
e_ident[8] = 7   = ABI version           ← 这个是真的
```

> **结论**：「在 `.nv_fatb` 里 `find(\x7fELF)` 计数」得到的 **1219 / 5500 不是可信的 cubin 计数**，
> 只能作为「疑似候选」。可信判据必须包含 `e_ident[7] == 0x33`。
> 这与本项目一直在修的「能力目录撒谎」是同一类错误 —— 用便宜的判据冒充精确结论。

### 1.7 事实 F5：PTX 是明文，且 kernel 名可直接提取

cuBLASLt-12 的 `.nv_fatb` 内实测：

```
@232860399 = ".version 8.7\n.target sm_120\n.address_size 64\n"
```

| 探针 | cuBLAS-12 | cuBLASLt-12 | ggml-cuda-12 |
| --- | --- | --- | --- |
| `.version`（PTX 块数） | 13 | 63 | **0** |
| `.target sm_` | 13 | 63 | **0** |
| `\x7fELF`（疑似 cubin） | 1219 | 5500 | **0** |
| `.visible .entry`（kernel 声明） | 0 | **348** | **0** |
| `.nv.info`（CUBIN 段） | 1214 | 2938 | **0** |

PTX kernel 名形态（实测）：

```
.visible .entry sm89_37...        ← 直接是标识符
.entry _ZN15cask__5x_cublas20nop  ← Itanium mangled
```

> **探针修正了我自己的一个设计错误**：我原本打算「先定位 PTX 块首，再解析块内 `.entry`」。
> 实测读块首 4096 字节时 `.entry` 命中 **0**（PTX 头部是 `.version`/`.target`/`.address_size`，
> kernel 声明在更后面）。正确做法是**整段扫 `.visible .entry <ident>`**，不依赖块首。

### 1.8 事实 F6：SPIR-V 是二进制，`OpEntryPoint` 文本搜索无效

Vulkan 的 `.rdata` 里 SPIR-V 魔数 `03 02 23 07` 命中 **1477 次**（真实模块数），
但文本 `OpEntryPoint` 命中 **0 次**（因为它是 opcode 15，不是字符串）。

头部实测：`magic=0x07230203, version=0x00010500 (1.5), generator=0x000d000b, bound=669`
`OpEntryPoint` 的 `ExecutionModel = 5 (GLCompute)`，名字是 null-terminated 字符串。

> 这条决定了必须写一个**指令流解析器**，不能靠字符串搜。

### 1.9 事实 F7：存在「段很大但内容不可解析」的情形

ggml-cuda.dll 的 `.nv_fatb` **334.9 MB**，但 7 类探针**全部 0 命中**。
同目录的 cuBLAS 命中上千。→ 同一厂商、同一段名，内容布局可以完全不同（压缩/异构 wrapper）。

> **这是本轮最重要的设计约束**：`parseable=False` 必须是一个**一等公民状态**，
> 带 `reason`，并在报告里显式出现。否则用户看到「0 个 kernel」会以为是「这个库没有 kernel」。

### 1.10 事实 F8：本机工具链与独立验证手段

| 工具 | 可用性 |
| --- | --- |
| `readelf` / `objdump` / `nm` | ❌ 无 |
| `nvcc` / `cuobjdump` / `nvdisasm` | ❌ 无 |
| `hipcc` / `rocm-smi` | ❌ 无 |
| WSL | ⛔ **被安全策略黑名单禁用**（不可绕过） |
| `pyelftools` / `capstone` | ❌ 未安装（可装入隔离 venv） |

> **对验证方法的约束**：无法用系统 binutils 交叉验证。
> 唯一正当的独立验证是**差分测试**：同一输入上，我的解析器 vs `pyelftools` 结果必须一致。
> 这是标准做法（differential testing），不是伪造。

### 1.11 白帽缺口（不知道的事）

| 缺口 | 影响 |
| --- | --- |
| fatbin 内部完整结构（`__cudaFatCudaBinary2` 字段语义） | 只做「识别 + 计数 + 提取 PTX」，不做完整反序列化 |
| `.nv_fatb` 为何在 ggml-cuda 上不可解析（压缩？） | 只能标记 `parseable=False`，不猜测 |
| ELF `.dynsym`/`.gnu.hash` 真实样本 | 本机无真实 ELF 可测（见 1.10）→ 需自造 + pyelftools 差分 |
| AMD `.hip_fat` 内部（探针被输出截断，未取到语义） | 待补测 |

---

## 2. 【红帽】直觉与情绪

- **兴奋**：语料是真实的、免费的、就在本机 —— 349 MB 的真实 CUDA fatbin 不是能造出来的东西。这比读文档可靠一个数量级。
- **警惕**：这个方向**极易变成「写一个 `file` 命令的劣化版」**。dump 段表谁都会，价值为零。真正的价值只在「归属」那一层。
- **不安**：`.nv_fatb` 334 MB 却 0 命中那一刻，我的第一反应是「我的代码有 bug」。**实际上不是** —— 是真实世界就是这么脏。
  如果我没有先跑真实文件，我会在报告里写「ggml-cuda.dll 含 0 个 cubin」，一个彻头彻尾的错误结论。
- **克制**：绝不能宣称「支持 CUDA/AMD 二进制分析」却不做 `parseable=False`。那就是又一次「能力目录撒谎」。

---

## 3. 【黑帽】风险与缺陷

| 编号 | 风险 | 严重度 | 缓解 |
| --- | --- | --- | --- |
| **K1** | 性能：692 MB 文件全段扫描会让 CLI 卡住 | 高 | 流式分块 + `--binfmt-scan-cap` 硬上限 + 默认只扫段名前 N MB |
| **K2** | 段名硬编码：「厂商又改段名了」就静默 0 | 高 | 段名优先 + **magic 扫描兜底**；两者都空时输出 `parseable=False, reason="no gpu section and magic scan empty"` |
| **K3** | 用便宜判据冒充精确结论（`\x7fELF` 计数） | 高 | 严格判据：`e_ident[7]==0x33`；不满足的记为 `suspect`，不混入 kernel 列表 |
| **K4** | mangled 名（`_ZN15cask__5x_cublas20nop...`）直接输出，人不可读 | 中 | 提供 `demangle` 尽力而为 + 保留原始名（**不丢信息**） |
| **K5** | 把「二进制符号」与「源码符号」混进同一个命名空间 → 假匹配 | 中 | 符号带 `origin`（容器路径）与 `source ∈ {binary, source}`，匹配时要求显式跨域 |
| **K6** | 引入 pyelftools 作为运行时依赖，违背项目零依赖风格 | 中 | **仅测试/护栏**使用，缺失则跳过并打印 `SKIP`（不假装通过） |
| **K7** | 差分测试的夹具是自造的 → 只证明「我和 pyelftools 对同一自造文件一致」 | 中 | 承认其局限：差分测试验证**解析正确性**，真实语料验证**鲁棒性**，两者都不证明「覆盖了所有格式」 |
| **K8** | 大文件被 read 进内存 → OOM | 中 | 全部 `seek`+定长 `read`，单次读 ≤ 8 MB |
| **K9** | 误报：把 `.rdata` 里巧合的 4 字节当 SPIR-V | 中 | 校验 version 字段合法 + bound 合理 + OpEntryPoint 可解析；不合法即丢弃 |
| **K10** | 范围膨胀：想做反汇编/反编译 | 高 | **明确拒绝**（见 §6 拒绝清单） |

---

## 4. 【黄帽】价值与收益

| 编号 | 收益 | 可验证形式 |
| --- | --- | --- |
| **Y1** | 「未解析调用」从 1 个桶变成 3 类归因 | 报告新增字段 `attributed_to ∈ {source, library:<name>, gpu_kernel:<name>, missing}` |
| **Y2** | 建立**真实** GPU kernel 目录（不靠文档） | cuBLASLt 实测可提取 ≥348 个 kernel 名 |
| **Y3** | 动态依赖图（谁能提供这个符号） | 新增 `dependency` 边，含 `DT_NEEDED` / Import Directory |
| **Y4** | 「库存在但内容不可解析」变成可观测状态 | `parseable=False` + 原因，防静默 |
| **Y5** | 为 C'5（构建系统感知）提供落点 | `-l<lib>` → 库名 → 二进制符号表，形成闭环 |
| **Y6** | 三家 GPU 后端（CUDA/ROCm/Vulkan）用**同一套**抽象 | 统一 `GpuBlob` 模型，新增后端只需加一个探测函数 |

---

## 5. 【绿帽】替代方案与改进

| 方案 | 描述 | 评价 |
| --- | --- | --- |
| **A. 外部工具包装** | 调用 `readelf`/`cuobjdump`/`llvm-objdump` | ❌ 本机全无（F8），且引入外部依赖 |
| **B. 引入 pyelftools + LIEF 作运行时依赖** | 成熟库 | ❌ 违背零依赖；且 LIEF 装不上（网络）；且覆盖不了 fatbin/SPIR-V |
| **C. 纯 stdlib 自研容器解析 + GPU 段探测** | 本项目风格 | ✅ **采用** |
| **D. 只做「识别」（是不是 GPU 二进制）** | 最省事 | ❌ 价值太低，等于 `file` 的劣化版 |
| **E. 反汇编 kernel 指令** | 最彻底 | ❌ 明确拒绝：需要 SASS/amdgcn 解码器，成本极高，且与「归属」目标无关 |

**绿帽对 C 的三点改进**：
1. **不要先定位块首再解析**（F5 教训）→ 直接扫语义标记（`.visible .entry`）。
2. **「不可解析」是一等状态**（F7 教训）→ 不是异常，是正常返回值的一种。
3. **便宜判据与精确判据分开命名**（F4 教训）→ `suspect_cubin_count` vs `kernels`，报告里分两行显示。

---

## 6. 明确拒绝的事（写下来，避免下一轮反复讨论）

1. ❌ **反汇编 / 反编译** GPU 或 CPU 指令（C 方案已够，E 方案成本不可控）。
2. ❌ **把 pyelftools/LIEF/capstone 变成运行时依赖**（只在护栏里做差分验证）。
3. ❌ **完整反序列化 fatbin**（`__cudaFatCudaBinary2` 字段语义未实测，猜测即撒谎）。
4. ❌ **把 GPU kernel 塞进 `_CROSS_LANG_KIND_META`**（术语冲突，见 §0）。
5. ❌ **宣称「支持 CUDA/AMD 二进制」而不标 `parseable`**。
6. ❌ **自动下载厂商二进制**（语料用本机已有的；不联网拉 692 MB）。

---

## 7. 【蓝帽】综合结论与架构

### 7.1 三层架构

```
┌─ L1 容器层  binfmt/container.py
│    识别 PE / ELF / Mach-O（+fat），解析 头/段表/节表
│    产出统一 Container：arch, bits, endian, sections[], imports[], exports[], deps[]
│
├─ L2 GPU 段定位层  binfmt/gpu.py
│    段名优先：.nv_fatb .nvFatBi .hip_fat .hipFatB
│    magic 兜底：0xba55ed50 / SPIR-V 0x07230203（因 Vulkan 无专用段）
│    两路都空 → GpuBlob(parseable=False, reason=...)
│
└─ L3 内容提取层  binfmt/gpu.py
     CUDA: PTX（.visible .entry 扫描）+ 疑似 cubin 计数（严格判据 e_ident[7]==0x33）
     AMD : .hip_fat 内 ELF code object（EM_AMDGPU=224 判据待实测确认）
     SPIRV: 指令流解析 OpEntryPoint(op=15) → ExecutionModel + name
```

### 7.2 统一数据模型（关键字段）

```python
Symbol(name, kind∈{export,import,dynamic,gpu_kernel}, address, origin, source∈{binary})
Dependency(name, kind∈{needed,import_module,rpath,link_flag}, resolved_path)
GpuBlob(backend∈{cuda,hip,vulkan,spirv}, section, offset, size,
        parseable: bool, reason: str,
        kernels: list[str], targets: list[str], ptx_version: str|None,
        suspect_code_objects: int)          # ← 便宜判据单独命名，不混入 kernels
BinaryReport(path, kind, arch, bits, endian, sections, symbols, deps, gpu_blobs)
```

### 7.3 接入点

| 接入点 | 改什么 | 产出 |
| --- | --- | --- |
| `renderers/unresolved.py` | 未解析条目增加 `attributed_to` | 「未解析」三分 |
| 构建系统 | 新增 `Makefile`/`CMakeLists` 的 `-l` 提取 | `link_flag` 依赖边 |
| CLI | 新增 `--binary <path>`、`--binary-json`、`--binfmt-scan-cap`、`--binary-symbols` | 可独立使用，也可被其他模式调用 |

### 7.4 30 轮实施计划（C1–C10）

| 编号 | 建议 | 轮次 | 验收判据 |
| --- | --- | --- | --- |
| **C1** | 事实采集探针（真实语料） | R1–R3 | 两个探针输出全部事实，含 F1–F8 |
| **C2** | 容器层：PE + ELF + Mach-O 流式解析 | R5–R11 | 三种格式各解析真实文件成功；`seek` 读取，单次 ≤8 MB |
| **C3** | GPU 段定位：段名 + magic 兜底 | R12–R13 | 真实 CUDA/AMD 文件都能定位到段 |
| **C4** | CUDA：fatbin 识别 + PTX kernel 提取 | R14–R15 | cuBLASLt 提取 ≥348 个 kernel 名；ggml-cuda 报 `parseable=False` |
| **C5** | AMD：`.hip_fat` code object 识别 | R16 | 真实 ggml-hip.dll 上给出 backend=hip |
| **C6** | SPIR-V：OpEntryPoint 指令流解析 | R17 | Vulkan 上提取 GLCompute kernel 名，与 magic 计数一致 |
| **C7** | 不可解析诚实报告 | R19 | 报告含 `parseable/reason` 字段；有负对照测试 |
| **C8** | 接入未解析调用归因 + 构建系统 | R20–R22 | 未解析条目带 `attributed_to`；`-l` 提取闭环 |
| **C9** | 护栏 + 差分测试 | R23–R25 | `check_binfmt_fixtures.py` 两向自证；pyelftools 差分一致 |
| **C10** | 回归 + 公平基线 + 归档入库 | R26–R30 | 既有测试 0 转红；对象级验证通过 |

### 7.5 一句话

**二进制分析在本项目的定位不是「多一个输入格式」，而是「给未解析调用提供归属证据」；
而它的实现纪律不是「支持尽可能多的格式」，而是「每一个结论都必须有真实文件支撑，且不可解析时必须说出来」。**

---

## 附录 A：探针 1 关键输出

```
CUDA-12  ggml-cuda.dll (349.7 MB)
   .nv_fatb  vsize=334921016 raw_off=14785536
   .nvFatBi  vsize=3432      raw_off=349706752
   --- 内容扫描 .nv_fatb ---
       .target sm_  count=0   ELF(cubin) count=0   .nv.info count=0

cuBLAS-12  cublas64_12.dll (113.7 MB)
   .nv_fatb  vsize=108743072 raw_off=4952064
       .target sm_  count=13   ELF(cubin) count=1219   .nv.info count=1214

cuBLASLt-12  cublasLt64_12.dll (692.4 MB)
   .nv_fatb  vsize=286559048 raw_off=232526848
       .target sm_  count=63   ELF(cubin) count=5500
       .visible .entry count=348   .entry count=375   .nv.constant0 count=19

VULKAN  ggml-vulkan.dll (41.7 MB)  — 无专用 GPU 段
   .rdata  vsize=40605094
       SPIR-V magic count=1477   OpEntryPoint(string) count=0

AMD-ROCm  ggml-hip.dll (504.8 MB)
   .text .rdata .data .pdata .hipFatB(3288) .hip_fat(491254728) .tls .rsrc .reloc
```

## 附录 B：探针 2 关键输出

```
## Q1 CUDA cubin 头
   cubin 候选 @4952145 type=32768 machine=256 osabi=51 abiver=7 shnum=98 shoff=0xCAFE...
## Q2 PTX kernel 名
   @232860399 version=['8.7'] target=['sm_120'] addr=['64']
       （读块首 4096 B 时 .entry 数=0 → 窗口假设错误，改为全段扫）
## Q3 SPIR-V OpEntryPoint
   @1063888 version=0x00010500 generator=0x000d000b bound=669
       OpEntryPoint model=GLCompute name=main（提取有 bug，见 K4/绿帽改进 2）
```

## 附录 C：探针抓出的我自己的 3 个错误

1. **窗口假设错误**：先定位 PTX 块首再解析 `.entry` → 块首 4096 B 内 `.entry` 命中 0。改为全段扫语义标记。
2. **便宜判据冒充精确结论**：`\x7fELF` 计数被当作 cubin 计数，但 cubin 的 `e_type/e_machine/e_shoff` 全非标准。改为严格判据 + 单独命名。
3. **SPIR-V 名字提取循环 bug**：内层遇 `\0` 未跳出外层，读出 `main3???` 垃圾。
