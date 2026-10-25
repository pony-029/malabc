# 能做什么 / 不能做什么（按语料核对）

> 每一行都有**证据文件**（`translate/examples/…`）与**验证方式**。
> 全部语料 27 个函数，逐个与 Octave 真值比对（`tools/check_translate_port.py --require-c`）。
> 想看某一行是否真的成立：直接打开那个文件，跑一次转换与对拍。

## 一、支持（有语料 + 有真值）

| 特性 | 证据 | 备注 |
|---|---|---|
| 标量算术与赋值 | `numeric/above.m` | `y = x(x > 2)` 之前的标量路径 |
| 数组逐元素运算 + 标量广播 | `numeric/dynshape.m`、`numeric/sumsq.m` | `x + x`、`x.*x` |
| 归约 `sum` / `max` / `mean` | `numeric/col2sum.m`、`pickmax.m`、`colmean.m` | 1-D 与按列 |
| 点乘与矩阵乘 | `numeric/dotp.m`、`mmul.m` | 矩阵乘走 4×4 微内核 |
| 2-D 索引 `A(i,j)` | `numeric/colmax_loop.m` | 含循环变量下标 |
| 列切片 `A(:,j)` | `numeric/col2sum.m` | |
| 行切片 `A(i,:)` | `numeric/row1.m` | 新算子 `OP-ROW` |
| 线性区间索引 `x(1:2)` | `numeric/head2.m` | |
| 展平 `A(:)` | `numeric/flatit.m` | |
| 转置 `A'` | `numeric/transit.m` | 2-D |
| 逻辑掩码 `x(x>2)` / `find` | `numeric/above.m`、`relu.m`、`wheregt.m` | 动态长度输出 |
| `for` 循环 | `numeric/for_acc.m`、`cumsum_loop.m` | 含循环内写入 |
| `while` 循环（**条件每轮重算**） | `numeric/while_acc.m`、`while2d.m` | 含 `break` |
| `if` / `elseif` / `else` / 裸条件 / `~` 取反 | `numeric/firstel.m`、`notempty.m`、`colmax_loop.m` | |
| 多返回值调用 `[a,b] = f(x)` | `examples/multi/` | 生成 `call2:` |
| 无返回值函数（"过程"） | （YALMIP `scope_demo` 等） | 生成 `mlc_status f(args)` |
| 空数组 `A = []` | `numeric/emptychk.m` | `fill:A:0:0` |
| `isempty` / `numel` / `length` / `size(x,d)` | `emptychk.m`、`countel.m`、`ncols.m` | 均为 1×1 结果 |
| **返回值不写形状注解** | `numeric/dynshape.m`、`dynsum.m` | 由算子按结果形状运行时分配 |
| 零注解调用（含入参） | `examples/nouns/scale2x.m` | 驱动按默认形状 `[4]` |

## 二、不支持（明确拒绝，不静默）

| 特性 | 行为 | 为什么 |
|---|---|---|
| `struct` / `fieldname` | 整函数 `reject:struct` | C 无对应物；要支持需类型系统 |
| `cell` / `{...}` | `reject:cell` | 异构容器 |
| `varargin` / `varargout` | `reject:varargin` | C 签名无法表达 |
| `@类` 目录下的方法 | `reject:method` | 语义是分派 |
| `global` 变量 | 语句 `unmapped`，函数成桩 | **忽略会读到局部 0 → 静默算错** |
| 数组别名 `y = x` | `unmapped` | `const:` 只接数字，不猜 |
| 字符串参与运算 | `unmapped`（`# why:strlit`） | |
| 拼接 `[a b]` / `[a; b]` | `unmapped` | 需形状与动态长度，未做 |
| `A(:, j:k)` 两维切片 | `unmapped`（`# why:slice2d`） | 已有一维变体 |
| 变量的赋值在 `if/else` 两支 | 形状推不出 → 函数成桩 | **信息不在源码里**，需注解 |

## 三、怎么自己验证

```bash
# 1) 全量对拍：27 个函数逐个与 Octave 比数值
python tools/check_translate_port.py --require-c

# 2) 端到端：转换→生成→编译→跑→按类计数
python tools/runnable_report.py translate/examples/numeric

# 3) 生成物能编译（4 个示例工程）
python tools/check_generated_compiles.py
```

## 四、一句话定位

**它转换「带形状注解的数值型 MATLAB 子集」，逐函数对应到 C99，并用 Octave 真值逐例核对。**
它不试图覆盖任意 MATLAB —— 见 `KNOWN_LIMITS.md` 里的数量与理由。
