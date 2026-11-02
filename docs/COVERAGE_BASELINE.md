# C 运行时覆盖率基准（gcov）

> 第二个第三方仪器。`cppcheck` 只能静态看代码，**不知道哪些分支从未被执行**；
> gcov 度量的是"执行过什么"，不是"我以为执行过什么"。

## 一、怎么复现

```bash
# 1) 转 MIR + 生成 C（语料 40 例）
python translate/mir.py translate/examples/numeric -o /tmp/n.mir
rust/m2c/target/release/m2c build --mir /tmp/n.mir --out /tmp/gen --name numeric
# 2) 在**同一个目录**里带 --coverage 编译（.gcno/.gcda 要与源码同目录）
cp c_runtime/src/mlc_runtime.c c_runtime/src/mlc_ops.c /tmp/
cd /tmp && gcc -std=c99 -O0 --coverage \
    -I gen/include -I <repo>/c_runtime/include \
    gen/src/gen.c gen/src/main.c mlc_runtime.c mlc_ops.c -o num.exe -lm
./num.exe
# 3) gcov 要用**对象名**（`-o num.exe` 时文件叫 num-mlc_ops.gcno）
gcov -b -c num-mlc_ops.gcno
gcov -b -c num-mlc_runtime.gcno
```

> 踩坑记录：`gcov -b -c mlc_ops.c` 会报 `cannot open notes file` ——
> 因为对象名前缀是 `num-`。用对象名（`num-mlc_ops.gcno`）才行。
> 另：`--coverage` 编译时若工作目录在仓库根，`.gcno/.gcda` 会落在根目录 —— 必须在临时目录里编译。

## 二、基准数字（2026-10-28，语料 40/40 全过）

| 文件 | 行覆盖 | 分支已执行 | 分支至少走一次 |
|---|---|---|---|
| `mlc_ops.c` | **56.98%**（688 行） | 84.01%（663 个） | **48.42%** |
| `mlc_runtime.c` | **51.09%**（92 行） | 79.71%（69 个） | **46.38%** |

## 二·补：接入负向测试后（`tests/test_op_error_paths.py`，12 条错误路径）

| 场景 | `mlc_ops.c` 行覆盖 | 分支至少走一次 | `mlc_runtime.c` 行覆盖 |
|---|---|---|---|
| A 仅语料 40 例 | 56.98% | 48.42% | 51.09% |
| **B 语料 + 负向** | **59.45%** | **51.28%** | **54.35%** |
| 增量 | **+2.47pp** | **+2.86pp** | **+3.26pp** |

量法：用 `-c` 编出 `mlc_ops.o` / `mlc_runtime.o`（都带 `--coverage`），
再分别链出 `num.exe`（语料驱动）与 `err.exe`（错误路径），**两个程序写同一份 `.gcda`** ——
计数会累加，于是得到并集。

## 三、未覆盖的是什么（这一节比数字重要）


未执行的行**绝大多数是错误分支**，例如：

```
#####:   73:        return MLC_ERR;      /* 空指针 */
#####:   79:        return MLC_ERR;      /* 不可广播：不猜 */
#####:   85:        return MLC_ERR;      /* 就地分配失败 */
#####:   90:        return MLC_ERR;      /* 形状与广播结论不一致 */
#####:  108:        return MLC_ERR;      /* data 为 NULL */
```

**含义**：语料只喂合法输入，所以约 43% 的行（几乎都是 `return MLC_ERR` 及其卫语句）
**一次都没跑过**。而这正是泄漏最容易发生的地方 —— 早期 `return` 会跳过后面的 `free`。

也就是说：**当前"零内存问题"的结论，只覆盖了 happy path。**

## 四、下一步（按依赖排序）

| 序 | 事项 | 为什么是它 |
|---|---|---|
| ~~1~~ | ~~造负向测试点亮错误路径~~ **已完成**：12 条错误路径全被拒，行覆盖 +2.47pp | 剩余未覆盖仍是错误分支，需继续补 |
| **2** | 把 RS1–RS2 扩成 **RS1–RS3**（行覆盖 + 分支至少走一次设阈值，例如 60% / 55%） | 数字进门槛才有约束力；阈值必须在**点亮负路径之后**再定 |
| **3** | MSVC `cl /fsanitize=address` 跑同一批（含负向） | 本机唯一真正的内存检查；错误路径正是泄漏高发区 |
| **4** | `docs/MIR_SEMANTICS.md`（42 opcode × 6 字段） | 语义层；`depth >= 3` 魔数一并规范掉 |

## 五、这份文档的定位

它记录的是**基准**，不是成就：56.98% 行覆盖说明"我们测的是半个运行时"。
把它写下来，是为了让下一次改动有个可比的起点 —— 而不是为了说明现在有多好。

## 关于 Q15 定点算子的覆盖率（R608）

`mlc_op_q15_add` / `mlc_op_q15_mul` **不在语料的执行路径上**（语料走 f64 路径），
所以加入它们会让 RS3 的行/分支覆盖**如实回落**（62.62% → 59.42%）。

它们的正确性由**另一条判据**守住：`tests/test_q15_ops.py`
—— 用独立的 Python 参考实现做差分（200 组随机 + 10 组边界，add/mul 逐元素一致）。

⇒ RS3 的阈值随之下调到实测值（59.3 / 49.2），并在本文件记录原因，
而不是为了让数字好看去删代码或加无意义的语料。

## RS3 的口径（R613 起）

RS3 只衡量 **f64 主路径**（语料走的那条）。`mlc_ops.c` 里的 **Q15 定点段**
用 `@m2c coverage-exclude begin/end` 标出并排除，理由是它有**自己的判据**：

* `tests/test_q15_ops.py` —— 与独立 Python 参考实现差分（算术 + 边界缩放）
* `tests/test_q15_end_to_end.py` —— 走生成器 + 夹具，验证饱和（`20000+20000 → 32767`）

**为什么要改**：此前用同一个百分比衡量两条路径，于是每加一批定点算子指标就掉一截
（62.6 → 59.4 → 58.7 → 56.5），每次都有"合理理由"，加起来是一个正在失效的指标。

**为什么排除是安全的**：`tests/test_rs3_exclusion.py` 四向守住 ——
标记必须成对且唯一、排除区内**只许有定点实现**（不许藏 f64 算子）、
关键符号确实落在排除区、以及 `_gcov_stats` 真的会跳过被排除行。
