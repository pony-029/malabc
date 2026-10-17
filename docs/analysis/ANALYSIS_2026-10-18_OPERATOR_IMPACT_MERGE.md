# 2026-10-18 · 合并 `operator_impact` 的两处重写

> R169 加 `--json-compact` 时踩到一件事：`--json` 的输出**被写了两次**，
> 第二次用硬编码 `indent=2`，把第一次的紧凑输出整个覆盖。
> 修完之后遗留一个**结构性浪费**：每次 `--json` 都序列化两遍。

---

## §0 一句话结论

`_operator_impact` 的计算只依赖 `checks_for_sarif` 与三个 `args` 参数，
而 `checks_for_sarif` 在 `render_json` **之前**就有了。

⇒ **把计算前移，`render_json` 多接一个 `operator_impact=None`，
两处「回读 + 重写」全部删掉。**

---

## §1 现状：写两次

| 步 | 位置 | 动作 |
| --- | --- | --- |
| ① | L32757 | `render_json(...)` 序列化一次 → 写文件 |
| ② | L32972 | `_compute_operator_impact(...)` |
| ③ | **L33054** | **回读文件 → 加键 → 用 `indent=2` 重写** |
| — | L17153 | 另一处同样的回读重写（不走 `--json` 主路径） |

**代价**：

- 23.6 MB 的 JSON 被**解析一次、序列化两次**
- 格式开关必须在**两处**同步（R169 就是在这里改错了一次）

**旧注释已经过时**：

> R62：把算子影响分析并入既有产物……这些产物在 `checks_for_sarif` 构建前
> 已落盘，故此处回读后追加/注入。

**现在 `checks_for_sarif` 由 `run_pipeline` 产出，早于 `render_json`。**
「必须回读」这个前提已经不成立。

---

## §2 依赖实测（L32970-32975）

```python
_threshold = float(getattr(args, "operator_impact_threshold", 0) or 0)
_scan_cap  = getattr(args, "operator_impact_scan_cap", None)
_operator_impact = _compute_operator_impact(checks_for_sarif,
                                            enabled_checks=_enabled,
                                            threshold=_threshold,
                                            scan_cap=_scan_cap)
```

**只依赖 `checks_for_sarif` + 三个 `args` 字段** —— 两者在 `render_json` 之前都可用。

---

## §3 改动（四处，都是加法或删除）

| # | 改动 |
| --- | --- |
| ① | 把 `_enabled` / `_threshold` / `_scan_cap` / `_compute_operator_impact` **移到 `render_json` 调用之前** |
| ② | `render_json` 加 `operator_impact=None`：非 None 时 `data["operator_impact"] = operator_impact` |
| ③ | `emit_outputs` 的 `render_json(...)` 传 `operator_impact=_operator_impact` |
| ④ | 删掉 L33054 与 L17153 两处「回读 + 重写」 |

**`_print_operator_impact` 保持在原处**（它是 stdout 副作用，与文件无关）。

---

## §4 判据（三条）

| # | 判据 | 期望 |
| --- | --- | --- |
| 1 | `--json` 输出 | 与改动前 **`IDENTICAL`**（含 `operator_impact` 键） |
| 2 | `--json-compact` | 体积仍约 **56%**，内容 `IDENTICAL` |
| 3 | 写文件次数 | **1 次**（`grep 'io.open(args.json, "w"'` 只剩 L26290 一处，那是别的功能） |

**第 3 条是这次改动的意义所在** —— 前两条只证明「没弄坏」，第三条才证明「真的省了一次」。

**怎么量第 3 条**：在 `_write_output` 与两处 `io.open(..., "w")` 各加一个计数器？
太侵入。**更简单：用 `strace`/`Process Monitor` 看写次数，或者比较改动前后的 CLI 耗时。**

**最实用**：`--json` 在 1300 文件上的总耗时从 ~17.2s 降到 ~15s（省掉一次 0.47s 序列化 + 0.5s 解析）。

---

## §5 风险

| 风险 | 说明 |
| --- | --- |
| `_print_operator_impact` 顺序变化 | 它是 stdout，移到前面会改变输出顺序 → **判据里要加 `--json` 的 stdout 比对**（或保持它在原位） |
| `operator_impact` 为空时 | `_compute_operator_impact` 恒返回 dict（可能为空），所以要区分「None（未计算）」与「空 dict（算了但没内容）」 |
| 两处重写点删哪个 | L33054 是 `--json` 主路径必删；L17153 是另一条路径，要确认它是否还活着 |

**第三个风险要先查**：L17153 在哪个函数里、什么时候被调用。**如果它是死代码，只删 L33054 就够；如果它是活路径，两处都要改成「不再重写」。**

---

## §6 状态

```
R169  --json-compact                          ✅ 87498ec
R171  合并两处 operator_impact 重写            ⬜ 本方案
```
