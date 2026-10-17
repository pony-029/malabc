# 2026-10-17 · LSP 性能实测：瓶颈不在解析，在 `_collect_checks`

> 上一轮的建议是「给 `api.analyze` 接 `Index`，只重解析变化的文件，
> 把首次打开从 1,093 秒降到可用区间」。本轮实测**推翻了这个方向**。

---

## §0 一句话结论

1300 个 `.m` 文件的 profile：

| 函数 | 累计 | 占比 |
| --- | --- | --- |
| `run_pipeline` | 3.93s | 97% |
| **`_collect_checks`** | **2.56s** | **63%** |
| └ `_detect_dup_code` | 1.80s | **44%** |
| └ `_apply_dup_idiom_suppression` | 1.06s | 26% |
| `build_analysis_model` | 0.44s | 11% |
| **`parse_file`（1300 次）** | **0.36s** | **9%** |

**解析只占 9%**。所以「增量缓存」最多省 9% —— 实测确也只省了 31%
（3.20s → 2.20s，含 `analyze_calls` 等派生），**远达不到「5%」的期望**。

---

## §1 增量缓存的实测（1300 文件）

| 模式 | 耗时 | 备注 |
| --- | --- | --- |
| 全量 | 3.20s | 基线 |
| 增量冷 | 2.21s | 首次写缓存 |
| **增量热** | **2.20s** | `cache_hits: 1300` / `hit_rate: 1.0` |

**热/全量 = 0.686**，结果一致（`RESULT_SAME True`）。

⇒ **缓存生效了，但省不到关键路径上。** 与 R146 在小语料上看到的
「反优化」（0.066s → 0.653s）是同一件事的两端：**缓存的是 `parse_file`，
而它不是瓶颈**。

---

## §2 LSP 真正用不上的是那 63%

`--json` 的 `heuristics`（5 条）**只从 `model.doc_todos` 派生**
（`matlabc.py` 里那句 `for _t in (doc_todos or {}).get("todos")`）。

而 `run_pipeline` 是**无条件**跑 `_collect_checks` 的：

```python
checks_for_sarif = _collect_checks(files, _parse_checks_arg(args.checks),
                                   dup_opts=_dup_opts)
```

`_collect_checks` 产出的是 `uninitialized / dead_code / type_mismatch /
dup_code / shape_mismatch` —— **LSP 第一版一条都不用**。

**实测**：传 `checks=""` 并不会关掉它（`_parse_checks_arg("")` 解释为全部，
耗时 2.03s → 2.05s 无变化，`checks` 仍 6 条）。

⇒ 要真正省这 63%，必须给 `run_pipeline` 一个**显式的跳过开关**，
而不是靠传空值。

---

## §3 三条真结论

| 结论 | 证据 |
| --- | --- |
| **接 Index 不是 LSP 的关键路径** | 解析只占 9% |
| **跳过 `_collect_checks` 才是** | 占 63%，且 LSP 不用 |
| **`_detect_dup_code` 是 O(n²)** | 24750 次 `_dup_idiom_score` / 59800 次 `_tokenize_matlab` |

第三条是**独立的性能问题**：62,704 个文件的整树探针要 1,000+ 秒，
而其中约 44% 花在重复代码检测上 —— 它对 C 语料的收益是否值得这个代价，
应该单独评估。

---

## §4 正确的下一步（按收益排序）

| # | 动作 | 预期收益 | 风险 |
| --- | --- | --- | --- |
| 1 | `run_pipeline` 加 `skip_checks`（或 `--no-checks`） | **−63%** | 低（判据：`heuristics` 不变） |
| 2 | LSP 改用**单文件**分析入口（不跑 root 级 `--json`） | −95%+ | 高（要新写 `analyze_file`） |
| 3 | 接 `Index` 做增量解析 | −9% | 低 |
| 4 | 优化 `_detect_dup_code`（O(n²) → 索引） | 影响整树探针 | 高 |

**第 1 条是最便宜的**：一个布尔参数 + 一条判据（`heuristics` 逐条相同）。
它把 LSP 首次打开从 1,093 秒降到约 **400 秒** —— 仍然慢，但方向对了。

第 2 条才是 LSP 的正解，但它要 `run_pipeline` 支持"只分析一个文件 + 它的 1 跳邻居"，
那是 P3（分析外迁）之后才能做的事。

---

## §5 判据

**第 1 条的判据**（可以现在就写，改完即可跑）：

```
analyze(root, skip_checks=True) 的 --json heuristics
  == analyze(root) 的 --json heuristics   （逐条相等）
且耗时 ≤ 全量的 50%
```

**第二条比第一条重要**：快但少了一条告警，是负收益。

---

## §6 状态

```
check_all      24/24
matlabc.py     未改动（本轮只做测量，所以 W2 保持绿）
LSP            第一版可用（10 条判据通过），但首次打开慢
```
