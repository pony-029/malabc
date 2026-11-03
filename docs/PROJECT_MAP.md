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
| **T3** | `reentrant: false` 的函数不得被**两个不同周期**的任务共用 |
| **T4** | 与 **R2** 同义（`max_ops_per_entry`）—— 只保留一个实现，不各写一份 |

### T3 / T4 / M4 各管一件事（此前三者混作一团）

| 规则 | 看什么 | 触发条件 | 后果 |
|---|---|---|---|
| **M4** | 同一份 `.m` 被**两个模块**引用 | 未写 `shared:` | 生成两份 C（符号冲突 / 代码膨胀） |
| **T3** | 非可重入函数被**不同周期**任务共用 | `reentrant: false` 且周期不同 | 数据竞争（一次调用打断另一次） |
| **T4 = R2** | 入口函数的算子数 | 超过 `max_ops_per_entry` | 截止期可能不保（WCET） |

**最容易混的一对是 M4 与 T3**：M4 **与周期无关**（两个同周期任务也要求 `shared:`，
它管的是代码重复）；T3 **只在周期不同且不可重入时**才成立（管的是并发安全）。
判据 `test_t3_*` 与 `test_m4_still_fires_without_shared` 把这条边界钉住 ——
同一份配置里，只该有一个命中。

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

## 九、数据格式与定标（MATLAB 的 double 不是板子上的 double）

同一份 MATLAB 代码，PC 上跑 `double`，板子上跑 `Q15` —— 数值结果、饱和行为、
舍入方向**全都不同**。所以它不是实现细节，是**接口约定**，必须写进配置并被校验。

```json
"dtypes": {
  "default": "f64",
  "map": { "double": "f64", "single": "f32", "int16": "int16" },
  "fixed_point": { "format": "Q15", "frac_bits": 15,
                   "round": "nearest", "overflow": "saturate" }
}
```

| 编号 | 规则 | 违反的后果 |
|---|---|---|
| **DS1** | `default` / `map` 的值必须是已知 C dtype | 生成器拿到不认识的类型名 |
| **DS2** | `frac_bits` 必须小于该 Q 格式位宽；`round`/`overflow` 只能取白名单 | Q15 写了 16 位小数 = 溢出且不可表示 |
| **DS3** | `target.dtype` 必须是已知 dtype | 目标 ABI 未定义 |
| **DS4** | **动静对账**：默认 dtype 与**源码实测 dtype** 不同时，必须显式声明转换（`fixed_point` 或 `map`）；否则报错 | 你以为在跑 f32，其实源码是 f64 —— 或者反之 |

`round` 白名单：`nearest | floor | ceil | trunc`；`overflow` 白名单：`saturate | wrap`。
两者都必须**显式**给出，因为"默认行为"在定点里是一个陷阱。

## 十、只允许一个配置文件

仓库与工程里**只能有一个** `m2c.project.json`：

* 版本靠文件内的 `version` 字段区分，**不靠文件名**（`m2c.project.v2.json` 这种会被判据拒绝）；
* 多个文件名会让"当前生效的是哪一份"变成猜谜；
* 判据 `test_single_project_config_file` 守着这一条。

## 十一、构建参数由配置推导（不手抄）

配置里写的是 `pool_bytes: 65536`，而 `m2c build` 要的是 `--static-pool 65536` ——
中间那次**人肉抄写**是最容易错的一环（抄成 `6553` 也能编过，只是池小了一点，且毫无提示）。

```bash
python translate/project_map.py m2c.project.json --emit-cflags
# → --name numeric_demo --static-pool 65536 --pool-align 8

python translate/project_map.py m2c.project.json --build
# → 真的跑 mir.py + m2c build（out 取自 c.root）
```

* `--target <名字>`：多个 target 都可选时指定用哪一个的 `memory`；
* 配置里没有 `strategy: static_pool` 时，**不会**产生任何池参数
  （否则会静默改变内存行为）。

### 定标的取值范围（一个必须先说清的事实）

**Q15 只能表示 `[-1, 1)`**：`1.0 × 2^15 = 32768` 已经越界，必须饱和到 `32767`。

所以定标只对**已归一化到 [-1,1) 的信号**有意义。这也解释了两件事：

* 语料里 `1..4` 这种值**进不了 Q15**（会全部饱和成 0.99997）——
  因此示例配置**不得**声明 `fixed_point`（有判据守着）；
* 边界转换必须**显式**，否则同一份代码在 PC 与板子上给出不同数值，且**都不报错**。

约定（写死，可被差分验证）：

| 转向 | 公式 |
|---|---|
| 外部 f64 → Q15 | `sat(round_half_away(x * 2^15))` |
| Q15 → 外部 f64 | `q / 2^15` |

实现为 `mlc_op_q15_from_f64` / `mlc_op_q15_to_f64`。
**`1.0` 必须落到 `32767` 而不是环绕成 `-32768`** —— 这是用 `double` 判边界、而不是整数转换的原因。

## 十二、产物样例（真实生成，非手写）

源文件（`acc.m`）：

```matlab
function y = acc(x)
% @m2c shape x 4
% @m2c shape y 1
y = sum(x);
end
```

配置：`matlab.root=m`、`c.root=gen`、`mcu.memory = static_pool/4096/align 8`、
模块 `accum` 由 `acc` 单独拼成、`period=1ms deadline=0.8ms entry=isr`。

### 1) 内存池（`gen/src/gen.c` 开头）

```c
#include "mlc.h"
/* 静态内存池：4096 字节，8 字节对齐（由 m2c.project.json 的 memory 段生成） */
static double m2c_pool_buf[(4096 + 8 - 1) / 8];
void m2c_pool_boot(void)
{
    (void)mlc_pool_configure(m2c_pool_buf, 4096, 8);
}
```

`src/main.c` 的 `main()` **第一句**就是 `m2c_pool_boot();` —— 池必须先于任何分配配置。

### 2) 函数体：f64 路径

```c
mlc_status m2c_acc(mlc_array x, mlc_array *y) {
    mlc_status st = MLC_OK;
    if (mlc_array_init(y, MLC_F64, 1, (int64_t[]){1}) != MLC_OK) { return MLC_ERR; }
    st = mlc_op_sum(&x, y);
    if (st != MLC_OK) { return st; }
    return st;
}
```

### 3) 同一份源码 + `--fixed-point q15`

```c
mlc_status m2c_acc(mlc_array x, mlc_array *y) {
    mlc_status st = MLC_OK;
    if (mlc_array_init(y, MLC_F64, 1, (int64_t[]){1}) != MLC_OK) { return MLC_ERR; }
    if (mlc_op_q15_from_f64(&x, &x) != MLC_OK) { return MLC_ERR; }
    st = mlc_op_q15_sum(&x, y);
    if (st != MLC_OK) { return st; }
    if (mlc_op_q15_to_f64(y, y) != MLC_OK) { st = MLC_ERR; }
    return st;
}
```

**差别正好三行**：入口转换、归约换成定点版、出口转换。
这就是"同一条 MATLAB 语句在两种目标上数值可比、且转换点显式可见"的样子。

### 4) `--emit-manifest` 的产物

```c
#define M2C_PROJECT "demo"
#define M2C_MODULE_COUNT 1

#define M2C_ACCUM_SOURCES 1
#define M2C_ACCUM_PERIOD_MS 1
#define M2C_ACCUM_DEADLINE_MS 0.8
#define M2C_ACCUM_ENTRY_KIND "isr"
#define M2C_ACCUM_SRC0 "acc"

#define M2C_MEM_STRATEGY "static_pool"
#define M2C_MEM_POOL_BYTES 4096
#define M2C_MEM_ALIGNMENT 8

#define M2C_USES_OP_SUM 1
```

嵌入式侧只要 `#include` 它，就能在编译期看到"这个模块由哪些 MATLAB 功能拼成、
跑在什么时序下、内存池多大"。

> 这些片段由 `tests/test_doc_samples.py` 守护：它会**重新生成**一遍并断言
> 文档里的关键行确实出现在产物中 —— 文档与代码不一致时立刻红。
