# 什么时候可以发布：判据、现状、路线

> 本文只写**能被测量**的条件。每个数字都有对应命令，读者可自行复现。
> 更新于 2.2.3。

## 一、先回答：现在能不能发？

**能，但只能作为 `v1.0.0-preview`（预览版），不能作为 v1.0.0。**

区别不是修辞：预览版承诺「**可复现的演示 + 明确的适用范围 + 已知限制清单**」，
而 v1.0.0 承诺「用户拿自己的代码来，多数情况能转」。

当前满足前者的全部条件（见第二节），后者还差三件事（见第四节）。

## 二、发布判据（六条，逐条打分）

| # | 判据 | 命令 | 现状 | 结论 |
|---|---|---|---|---|
| R1 | 闸门全绿且可复现 | `python tools/check_all.py` | 17 道门全绿，约 30 s | ✅ |
| R2 | 数值正确性有真值参照 | `python tools/check_translate_port.py --require-c` | 语料 **26/26** 与 Octave 逐一相等 | ✅ |
| R3 | 生成物能编译 | `python tools/check_generated_compiles.py` | 4 个示例工程 `-fsyntax-only` 通过 | ✅ |
| R4 | 端到端可执行 | `python tools/runnable_report.py translate/examples/numeric` | **26/26 产出数值** | ✅ |
| R5 | 性能有可信数字（含短板） | `python tools/bench.py <case> --reps 10` | 循环类 ~90×；矩阵乘 **慢 ~4.5×** | ⚠️ 有数字，含明确短板 |
| R6 | 真实工程可量化 | `python tools/runnable_report.py <工程> --recursive` | YALMIP：numeric **3** / unimplemented 37 / shape 121 / reject 1043 | ❌ 见第四节 |

**R1–R4 全绿 → 预览版可发。R6 是 v1.0 的硬门槛。**

## 三、预览版发布包（一周内可完成，约 3 轮）

1. **README 首屏三句话**（已在做）：
   - 它做什么：把**带形状注解**的 `.m` 转成 C99，逐函数对应。
   - 它保证什么：语料 26/26 与 Octave 相等；生成物能编译、能跑。
   - 它不保证什么：无注解代码的自动形状推断；struct/cell/varargin（占 YALMIP 87%）。
2. **一条命令的演示**：`python tools/runnable_report.py translate/examples/numeric --top 5`
3. **`KNOWN_LIMITS.md`**：把 `reject` 的 5 类原因、`TODO` 的 8 类、性能短板逐条列出，
   每条给出"为什么不做/怎么做"。
4. **可复现的环境**：Python 3.10、gcc、Octave 11（版本写进文档，`bench.py` 已依赖）。

> 预览版的意义：让外部的人**在 10 分钟内复现我们的数字**，而不是相信我们的结论。

## 四、v1.0.0 的三个硬条件

### C1｜真实工程里"能算"的函数 ≥ 30%（当前 3/1204 ≈ 0.2%）

现状分解（`runnable_report`，账已平）：

```
numeric 3 ｜ unimplemented 37 ｜ skipped_shape 121 ｜ skipped_reject 1043 = 1204
```

三条独立的增长路径，缺一不可：

| 群体 | 数量 | 卡点 | 需要的能力 |
|---|---|---|---|
| `unimplemented` | 37 | 函数体是桩 | 补齐 `shape`(12)/`ret`(9)/`call`(9)/`set`(8) 四类 |
| `skipped_shape` | 121 | 返回值形状未知 | 更多算子的「空输出→运行时分配」 |
| `skipped_reject` | 1043 | struct/cell/varargin | **结构性**：需要类型系统，不是补算子 |

> **1043 是天花板**：不引入 struct 支持，30% 永远到不了（可做上限是 161/1204 ≈ 13%）。
> 所以 C1 的准确表述应是：**在"非 struct/cell"的子集里 ≥ 50%（当前 3/161 ≈ 2%）**。

### C2｜生成物与 MATLAB（不是 Octave）对拍

现在全部真值来自 Octave。MATLAB 的 JIT、`sum` 累加顺序、整型饱和、`end` 语义
都可能不同。v1.0 至少要有一份「MATLAB 跑出的真值」样本（`bench/matlab_baseline.m` 已备）。

### C3｜一次真实用户的落地

拿一个**别人写的**、几十行的 MATLAB 脚本，从 `.m` 到可运行的 C，全程无人工改 MIR。
现在的全部验证都是我们自己的语料 + YALMIP（只跑，不求结果）。

## 五、路线（以轮为单位，每轮 ≈ 60 分钟）

| 阶段 | 轮次 | 目标 | 验收 |
|---|---|---|---|
| P0 预览版 | 3 轮 | README 三句话 + `KNOWN_LIMITS.md` + 一条命令演示 | 外人 10 分钟复现全部数字 |
| P1 补齐桩 | 6–8 轮 | `unimplemented` 37 → ≤ 10 | `numeric` ≥ 20/1204 |
| P2 放宽形状 | 6–8 轮 | `skipped_shape` 121 → ≤ 40 | `numeric` ≥ 40 |
| P3 真实落地 | 4 轮 | C3：外部脚本一次转通 | 无人工改 MIR |

**粗略估计：v1.0.0 还需 20–25 轮，且 C1 的分母要改成"非 struct 子集"。**

## 七、10 分钟复现（预览版的门槛）

前提：Python 3.10+、`gcc`、Octave（`octave-cli` 在 PATH 或标准安装位置）；
`rust/m2c` 已 `cargo build --release`。

```bash
# 1) 闸门（期望：17 道门全绿，约 30 s）
python tools/check_all.py

# 2) 数值正确性（期望：26 个函数与 Octave 真值一致；PA3 = 0）
python tools/check_translate_port.py --require-c

# 3) 端到端可执行（期望：26 个全部 numeric，其余为 0）
python tools/runnable_report.py translate/examples/numeric

# 4) 生成物可编译（期望：GX1–GX2 全绿）
python tools/check_generated_compiles.py
```

第 3 条的关键输出（应当逐字一致）：

```
用例 translate/examples/numeric ｜ 可驱动函数 26
  numeric（真能算） : 26
  unimplemented     : 0
  error             : 0
  empty             : 0
  skipped_reject    : 0
  skipped_shape     : 0
```

**如果这一条不是 26/26，就不要相信本文其他任何数字。**

外部工程（可选，需要工程路径）：

```bash
python tools/runnable_report.py <工程目录> --recursive
# 期望形态：numeric + unimplemented + empty + skipped_shape + skipped_reject == 函数总数
```

> 最后那条等式是**唯一防止"账不平"的检查**：分类表是人写的，
> 而"各行之合 == 总数"与写表的人知道多少类无关。

## 六、不建议做的事（写下来防止反复摇摆）

- **不建议**为了数字好看去支持 `struct`：它是类型系统级改动，等于重写半个前端。
- **不建议**把 `reject` 计数的下降当成进展：那 1043 个里有 87% 是结构性不可转。
- **不建议**在没有 MATLAB 真值前宣称"与 MATLAB 一致"：现在只能宣称"与 Octave 一致"。
