# 加一个算子要改**五处**（实测清单）

> 这份清单是两次失败换来的：第一次只改了四处，`size(A,2)` 直接编译不过；
> 而漏掉第 4 处时**不会报错**，它会静默按输入形状执行 —— 那比编译失败更糟。

## 五处

| # | 位置 | 内容 | 漏了会怎样 |
|---|---|---|---|
| 1 | `c_runtime/include/mlc_ops.h` | 函数声明 | 隐式声明警告 / 链接失败 |
| 2 | `c_runtime/src/mlc_ops.c` | 实现 | 同上 |
| 3 | `translate/operators.py` | 条目 + 识别正则 + `C_IMPLEMENTED` | 语句识别不出来，落 `unmapped` |
| 4 | `rust/m2c/src/emit.rs` 的 `C_IMPLEMENTED` | 白名单 | `OP-XXX: 未知算子` |
| 5 | `rust/m2c/src/emit.rs` 的 `out_shape` | 输出形状 | **静默**：按输入形状执行，产出错值 |

## 如果算子带**字面量参数**（如 `size(A,2)` 的 `2`）

还要加第 6 处：发射器里的**专用分支**。

通用的一参路径会把 `2` 当成变量名，生成 `mlc_op_size(&x, _2, y)` → `_2 undeclared`。
照抄 `OP-INDEX` 的写法：

```rust
} else if op.id == "OP-SIZE" && op.args.len() == 2 {
    let dim = &op.args[1];
    if dim.parse::<i64>().is_err() { /* TODO + return */ }
    out.push(format!("{}st = mlc_op_size_dim({}, (int64_t){}, {});", pad, arg0, dim, dst));
}
```

## 顺序建议

先改 3（Python 侧识别）→ 用 `operators.parse_line` 单测确认 → 再改 1/2 → 5 → 4/6 →
最后跑 `python tools/check_all.py`（它会同时校验 Python 与 Rust 两份 `C_IMPLEMENTED` 是否对齐）。
