# malabc-rt

M 语义参考实现的**最小骨架**。零外部依赖（纯 `std`），release 单二进制约 1.2 MB。

> 起因：R111–R131 的方案里，「Rust MATLAB Runtime」一直只是纸面设计。
> 本目录是它的**第一块砖**——能编译、能跑、能测，而不是又一份计划。

## 现在能做什么

```powershell
malabc-rt eval "1+2*3"   # 7
malabc-rt eval "(1+2)*3" # 9
malabc-rt eval "1/0"     # Inf
malabc-rt eval "0/0"     # NaN
malabc-rt eval "a+1"     # 报错，退出码 1
```

只支持**标量 `double`** 的四则（`+ - * /`）、括号、一元正负号。
显示按 MATLAB `format short` 的近似：整数不带小数点，小数 4 位且末尾零省略。

## 边界（写死，不许漂移）

| 输入 | 行为 |
| --- | --- |
| 只含数字与 `+ - * / ( )` | 求值，rc=0 |
| 含标识符 / 其它字符 | **rc=1**，并指出是哪个 token |
| 子命令不是 `eval` / `--version` / `--help` | **rc=2**（unimplemented） |

**绝不返回一个“看起来对”的值**——这是与 `matlabc.py` 同一套纪律：
`unimplemented` 与 `error` 必须分开，否则“跑不了”和“算错了”长得一样。

## 判据

```powershell
cargo test
```

五组：运算符优先级、一元与括号、除零边界（`Inf` / `-Inf` / `NaN`）、拒绝垃圾输入、格式化。
当前读数：**5 passed; 0 failed**（编译 0.65s，运行 0.00s）。

## 与主项目的关系（尚未接线）

现在它**独立**运行，不参与 `matlabc.py` 的任何路径。规划中的接线有三条：

1. `--dims-exec`：让 `dimensions` 从“静态推断”变成“实测”（`_make_dims_probe_script` 已有生成器，但零调用）
2. `--patch-verify`：确定性补丁在应用前后各跑一次，判 `fixed` / `regressed` / `changed`
3. `--calibrate`：给静态规则算**假阳性率**（第一次有分母）

三条都依赖同一个前置：**M AST**。现在这个骨架只有表达式求值，没有语句、函数、数组。
