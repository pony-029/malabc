# R160 复盘：`--checks default` 不存在，我的建议是编的

> 连续两轮我都建议「测一次 `--checks default`，如果产物与 `all` 字节相同，
> 以后内核读数用 default 跑，把 21 分钟压到 3 分钟」。
> 本轮查了 `--help` 与 `add_argument`：**没有这个值**。

---

## §0 一句话结论

```python
ap.add_argument("--checks", default=cfg.get("checks", "all"), ...)
```

`--checks` 的默认值**就是 `all`**；它只接受「逗号分隔的检查名」或 `all`。
**不存在 `default` 这个哨兵值**——那是我凭印象编的。

⇒ 上一轮那条「省时间」建议**作废**，不要执行。

---

## §1 实测

```
$ matlabc.py --help | grep checks
  --checks CHECKS   启用的静态检查（逗号分隔：uninitialized,dead_code,
                     type_mismatch,shape_mismatch,c_unused_static,
                     c_missing_guard,c_too_many_params,c_missing_doc,
                     c_uninit_pointer,c_array_oob,c_use_after_free,
                     ...
```

**枚举里没有 `default`。**

---

## §2 那 21 分钟到底能不能省

| 思路 | 可行性 |
| --- | --- |
| `--checks default` | **不存在** |
| `--checks <子集>` | 产物**必然不同**（少了检查项），不能用来做读数对照 |
| 减少文件数 | 改变了分母，读数不可比 |
| **优化 `--checks all` 的实现** | 唯一真正的方向 |
| **接受它是一次性成本** | 现实选项 |

**六次读数**：541 → 623 → 775 → 1000 → 1233 → 1269.9 秒。
**单调上升**，与 `matlabc.py` 从 31,889 涨到 34,000 行同向。
所以更可能是「代码变多、检查变多」，而不是某一次退化。

---

## §3 这条教训的形状

这已经是**第三次**「凭印象编一个不存在的东西」：

| 次 | 编了什么 | 怎么被否证的 |
| --- | --- | --- |
| 1 | 「`model.uninit` 是死字段」 | 运行时 `'uninit' in __dict__` 为 True |
| 2 | 「`_collect_checks` 没有 `shape_mismatch`」 | `sorted(checks)` 里有 |
| 3 | **「`--checks default` 可以加速」** | `--help` 枚举里没有 |

**共同点**：都是「用一个听起来合理的名字代替实际查一次」。
**成本**：前两次各写错一段文档，第三次差点让下一轮白跑一次对照实验。

⇒ **凡是引用 CLI 取值、字段名、函数名，先 grep 或 `--help`，再写建议。**

---

## §4 状态

```
check_all      23/24（W2，探针 PID 17476 已 15+ 分钟）
matlabc.py     已搬走 3 个叶子（94 行），P2 第二批 474 行的脚本已 dry-run 通过
```

---

## §5 下一步

1. 探针收口。
2. P2 第二批执行（6 个 / 474 行，四条判据含 `--mermaid` / `--dot`）。
3. 若要加速内核读数，方向是**优化 `--checks all` 本身**，不是换参数。
