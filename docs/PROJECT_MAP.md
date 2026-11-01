# MATLAB 工程 ↔ C 工程 的映射关系（v2）

> 这份文档定义**一个 C 工程如何由多个 MATLAB 功能拼装而成**，以及反过来
> （一个 MATLAB 功能如何落到多个 C 目标上）。它同时约束**算子替换**与
> **嵌入式时序**，并要求配置与实测**对账**（动静结合）。

## 一、为什么 1:1 文件映射不够

真实工程里，关系是**多对多**的：

| 现实 | 1:1 映射的表达力 |
|---|---|
| 一个 C 模块 = 3 个 MATLAB 函数拼装（`init`/`step`/`reset`） | 表达不了 |
| 一个 MATLAB 函数要同时生成 **PC 版**和**定点/嵌入式版** | 表达不了 |
| `sum` 在目标板上要换成厂商 DSP 原语 | 表达不了 |
| 这个模块跑在 **1 kHz 中断**里，不许动态分配 | 表达不了 |

所以模型不是"文件表"，而是**两层图**：

```
MATLAB 侧（功能）                 C 侧（模块/目标）
  m:filter.step  ──┐
  m:filter.reset ──┼──►  cmod:dsp_filter  ──►  target:pc | target:mcu
  m:filter.init  ──┘              │
                                  ├─ timing: period=1ms, entry=isr, heap=no
                                  └─ operators: sum -> vendor_sum_q15
```

## 二、配置格式（JSON，`m2c.project.json`）

```json
{
  "version": 2,
  "matlab": { "root": "matlab", "recursive": true,
              "exclude": ["**/test/**", "**/+*/**"] },
  "c":      { "root": "gen", "project": "dsp", "prefix": "m2c_",
              "runtime": "c_runtime" },

  "targets": {
    "pc":  { "abi": "host",  "allow_heap": true,  "dtype": "f64" },
    "mcu": { "abi": "arm",   "allow_heap": false, "dtype": "f32",
             "max_stack_bytes": 2048 }
  },

  "modules": [
    { "id": "dsp_filter",
      "targets": ["pc", "mcu"],
      "sources": ["filter_init", "filter_step", "filter_reset"],
      "entry": "filter_step",
      "timing": { "period_ms": 1, "deadline_ms": 0.8,
                  "entry_kind": "isr", "reentrant": false },
      "operators": { "sum": "vendor_sum_f32", "OP-MUL": "vendor_mul_f32" } }
  ],

  "operators": { "max": "vendor_max_f32" },

  "constraints": { "forbid_heap": ["mcu"], "max_ops_per_entry": 200 }
}
```

字段语义（**每条都有判据**，见第五节）：

| 字段 | 含义 |
|---|---|
| `modules[].sources` | **多个 MATLAB 函数拼成一个 C 模块**（组合关系）；名字可带 `文件.函数` |
| `modules[].entry` | 模块入口（其它 sources 作为内部步骤） |
| `modules[].targets` | 同一模块可**同时**产出多个目标（PC / MCU） |
| `modules[].timing` | 嵌入式时序：周期、截止期、入口类型（`isr`/`task`）、是否可重入 |
| `operators` | **算子替换**：MATLAB 算子名或 `OP-*` id → C 符号 |
| `constraints.forbid_heap` | 目标级禁令：该目标下不许动态分配 |

## 三、动静结合（本设计的核心）

**静态** = 配置文件声明的那些关系；
**动态** = 从**真实 MATLAB 源码**里扫出来的事实。

二者**必须对账**，四条规则：

| 编号 | 规则 | 违反时的含义 |
|---|---|---|
| **M1** | 配置里出现的 MATLAB 函数必须**真实存在** | 配置与工程脱节（改名/删了） |
| **M2** | 配置里替换的算子必须**真的被用到** | 多余配置 = 你以为优化了，其实没生效 |
| **M3** | 源码里用到的算子**必须被覆盖**（内置实现 ∪ 配置替换） | 目标板上没有这个算子 |
| **M4** | 同一 MATLAB 函数被**两个模块**引用且未声明共享 | 会生成两份，符号冲突或代码膨胀 |

`M2`/`M3` 就是"动"的那一半 —— 它们由 `mir.py` 扫出的算子集合驱动，
**配置改了但源码没变，或源码变了但配置没跟，都会被报出来**。

## 四、时序约束

| 编号 | 规则 |
|---|---|
| **T1** | `deadline_ms <= period_ms`（否则这个任务永远完不成） |
| **T2** | `entry_kind == "isr"` 时该模块**不得**依赖堆分配（`allow_heap` 必须为 false） |
| **T3** | `reentrant: false` 的模块不得同时出现在**两个不同周期**的任务里 |
| **T4** | `max_ops_per_entry` 限制入口函数的算子数（估算最坏执行时间） |

## 五、怎么被守住

`translate/project_map.py`（v2）实现上述 M1–M4／T1–T4，`tests/test_project_map.py` 锁定；
`--emit-manifest` 会输出一份 `m2c_manifest.h`（`#define` 表），
让**嵌入式侧**在编译期就能看到"这个模块由哪些 MATLAB 功能拼成、跑在什么时序下"。

## 六、与 v1 的关系

`version: 1` 的配置（`matlab.root` + `mapping` 目录映射）仍然可用，语义不变；
`version: 2` 在它之上加了 `targets/modules/operators/constraints`。两版共存，不迁移。

## 七、内存模型（嵌入式：没有充足的堆）

MATLAB 里 `zeros(1e6)` 随手就写；目标板上不行。所以内存必须**声明式**：

```json
"targets": {
  "mcu": {
    "allow_heap": false, "dtype": "f32",
    "memory": {
      "strategy": "static_pool",        // static_pool | heap | stack
      "pool_bytes": 65536,
      "alignment": 8,
      "max_array_bytes": 8192,
      "arrays": [ { "name": "accum_buf", "elements": 256, "dtype": "f32" } ]
    }
  }
}
```

| 编号 | 规则 | 违反的后果 |
|---|---|---|
| **MM1** | `static_pool` ⇒ 目标必须 `allow_heap: false` | 你以为没有堆，实际还在 malloc |
| **MM2** | `pool_bytes` 必须是 `alignment` 的整数倍 | 末段永远用不满，且不同对齐下容量错位 |
| **MM3** | 单个数组字节数 ≤ `max_array_bytes` | 一次分配就把池打穿 |
| **MM4** | 池容量 ≥ 所有声明数组之和 | 链接期/运行期溢出 |
| **MM5** | 声明数组的 `elements` 必须与**源码实测形状**一致 | 配置与实际脱节（动静对账） |

## 八、其他嵌入式约束（R1 / R2）

| 编号 | 规则 | 为什么 |
|---|---|---|
| **R1** | `constraints.no_recursion` 为真时，源码不得有自调用 | 递归 = 栈深不可静态界定，中断里尤其危险 |
| **R2** | `constraints.max_ops_per_entry` 限制入口函数算子数 | WCET 的粗估上限 |

这两条同样靠 `mir.py` 扫出的**事实**判定（自调用、每函数算子数），不是靠配置自述。
