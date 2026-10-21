# ADR-009: 移植管线用 Rust，交付物仍是 C

- Status: Accepted
- Date: 2026-10-21
- Diagrams: 00-overall
- Related: ADR-001（单文件内核 / 零第三方依赖）、ADR-005（确定性移植）

## Context

用户提出「主要实现用 Rust」。这句话必须先落到**哪一层**，否则无法判断可行性：

| 层 | 现状 | 规模（实测） |
| --- | --- | --- |
| 分析器 / 工具链（解析、门禁、LSP/MCP、站点） | Python | **133,055 行** |
| 移植管线（算子表、MIR、发射器、台账） | Python 1,029 行；发射器**尚不存在** | 1,029 行 |
| 生成物运行时（`mlc.h` / `mlc_runtime.c` / `mlc_ops.c`） | C | 4 文件，7 个导出函数 |

同时有两条硬约束：
* **ADR-001**：`matlabc.py` 单文件、零第三方依赖、Python 3.6.5 可跑；
* **用户目标**：MATLAB 工程要移植到**C 工程**（交付物是 C 源码，不是 Rust 源码）。

## Decision

**Rust 只用于「把 MATLAB 变成 C」的那台机器**，具体是：

1. `rust/m2c`：MIR 解析 + C 发射器（纯 `std`，**零第三方依赖**，与 ADR-001 同规格）；
2. MIR 的**文本格式**由 Rust 与 Python 共同约定，Python 侧 `translate/mir.py` 只负责
   把 `.m` 切成函数并复用既有算子表（**不翻译**），保证算子目录单一事实源；
3. 生成物**仍是 C**：`.h` + `gen.c` + `CMakeLists.txt` + `main.c` 骨架；
4. 分析器（133k 行 Python）**不重写** —— 收益（分析速度）不存在：1300 文件实测 6s。

明确**不做**：
* 全量重写分析器为 Rust（成本 >> 收益，且要重跑 40 道门与 24.7k 行测试）；
* 用 Rust 生成物替换 C（那会改变交付形态，与用户目标冲突；如需要，另立 ADR）。

## Consequences

- 多一门语言/工具链：CI 需要 `cargo`；缺 cargo 时 TP5 **跳过并说明**，
  `--require-c` 下判红（不允许"跳过即绿"）。
- 发射器是确定性函数：同一 MIR 两次输出必须逐字节一致（门会真跑两遍比对）。
- 与 ADR-001 不冲突：ADR-001 约束的是 `matlabc.py`，本 ADR 约束的是 `rust/m2c` 与
  `translate/`；两者的共同纪律是**零依赖**。
- 生成代码只调用 `mlc.h` 里已有的契约，不新增 ABI。

## Evidence

- `rust/m2c/` —— `m2c --selftest` 14/14；`cargo build --release` 约 0.8s
- `translate/mir.py` + `translate/examples/demo_port.m` —— 4 函数 / 3 算子 / 1 未映射
- `tools/check_translate_port.py` **TP5**：
  `OK（TP1–TP5 全绿；… MIR 函数 4 / 算子 3 / 未映射 1 / 编译 通过）`
- 生成物实测：`gcc -std=c99 -fsyntax-only` rc=0；两次发射 `gen.c` 哈希相同
- 两向验证：移走 `rust/m2c/Cargo.toml` 后 `--require-c` 判红（1 项不合规）
