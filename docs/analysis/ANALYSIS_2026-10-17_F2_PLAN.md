# 2026-10-17 · F2 方案：三类告警并入 facts，先看清它们现在在哪

> 上一轮的建议是「F2 之前先确认 `uninitialized` / `dead_code` / `shape_mismatch`
> 的数据在 `model` 上叫什么，如果没挂在 `model` 上，F2 会变大」。本轮实测完了，
> 结论比预想的更糟：**它们根本不在 `model` 上，只在 `render_json` 里现算**。

---

## §0 一句话结论

`dead_code` 与 `shape_mismatch` **没有挂在 `model` 上**；`uninitialized` 虽然挂在
`model.uninit`，但 `render_json` **并没有用它**——而是重新遍历 `files` 调
`_detect_uninitialized(mf)`。于是同一批检测在渲染路径上被**至少执行 2 次**。

---

## §1 实测：model 上有什么，没什么

```
model attrs: c_bridge, c_model, callers_of, calls_of, doc_todos, edges,
             edges_objects, empty_dirs, files, fn_to_file, index, ranked,
             rel, root, stats, taint, uninit, varflow, variables
```

| 名字 | 在 model 上？ | 实测条数（`tests/sample_m`） |
| --- | --- | --- |
| `uninit` | **是**（L19863–19868 真有赋值） | 0（该语料确实无此告警） |
| `dead_code` | **否** | — |
| `shape_mismatch` | **否** | — |

**`model.uninit` 有数据**：`build_analysis_model` 在 `return SimpleNamespace(...,
uninit=uninit)` 里填入，值来自 L19855 的 `_detect_uninitialized(mf)` 循环。

> ⚠ 本文件初稿曾把 `model.uninit` 写成「死字段」，理由是 `grep "model.uninit ="`
> 只找到两处**读**。那是个错误结论——赋值走的是 `SimpleNamespace(uninit=...)`
> 这条 kwargs 路径，而我的 grep 模式根本没覆盖它。**「grep 没找到」不等于
> 「不存在」**，这条已记进本节。

**真正的问题不是「没数据」，而是「算了两遍」**：`render_json`（L14295）
没有用 `model.uninit`，而是重新遍历 `files` 再调一次 `_detect_uninitialized(mf)`。

---

## §2 同一个检测被调了不止一次

`grep` 出六个调用点：

| 行 | 所在函数 | 做什么 |
| --- | --- | --- |
| L14295 | `render_json` | `"uninitialized": [... for mf in files for r in _detect_uninitialized(mf)]` |
| L14300 | `render_json` | `"dead_code": [...]` |
| L14310 | `render_json` | `"shape_mismatch": _detect_shape_mismatch(files)` |
| L19855 | 另一处渲染 | `for r in _detect_uninitialized(mf)` |
| L25846 | 另一处渲染 | `for r in _detect_uninitialized(mf)` |
| L25854 / L25864 | 同上 | `_detect_dead_code(mf)` / `_detect_shape_mismatch(files)` |

**这意味着**：`--json` 与站点页各算一遍；一旦两处过滤条件不同（比如一处按
`min_confidence` 过滤），就会出现「同一批告警，报表与站点数量不同」——本仓最贵的病。

---

## §3 F2 的最小改动（四处，都是加法）

### 3.0 精确行号（实测，2026-10-17 19:40；§3.1 的发现让表从 4 行缩到 3 行）

| # | 改动 | 行号 |
| --- | --- | --- |
| ① | `render_json` 加 `checks=None`，`uninitialized` / `dead_code` 优先读它 | **L14229**（定义）、**L14295 / L14300**（两个键） |
| ② | `render_xml` 加 `checks=None` + 透传 | **L19701**（定义）、**L19706**（内部调 `render_json`） |
| ③ | `emit_outputs` 传 `checks_for_sarif=checks_for_sarif` | **L33248** |
| — | `run_pipeline` | **不用改**（`checks_for_sarif` 早就有了） |
| — | `shape_mismatch` | 仍由 `render_json` 自己算（唯一无上游缓存者） |

**并且发现第三处统计点**：L25879–25880 另有 `return {"uninitialized": ...,
"dead_code": ..., "shape_mismatch": ..., "dup_code": ..., ...}` —— 那是
`_collect_checks` 的返回，也就是 `checks_for_sarif` 本身。

### 3.1 **先别急着加计算 —— `checks_for_sarif` 里已经有了**

实测 L25835：

```python
def _collect_checks(files, enabled=None, dup_opts=None):
    """C3：综合静态检查（未初始化 / 死代码 / 类型不一致），带 file 字段。
    返回 {"uninitialized": [...], "dead_code": [...],
          "type_mismatch": [...], "dup_code": [...]}。"""
```

而 `run_pipeline` 早就调了它（L33039）：

```python
checks_for_sarif = _collect_checks(files, _parse_checks_arg(args.checks),
                                   dup_opts=_dup_opts)
```

⇒ **`uninitialized` 与 `dead_code` 已经算好了，就在 `result.checks_for_sarif` 里。**
`render_json` 只是**没有用它**，而是重新遍历 `files` 再算一遍。

**所以 ① 步不是「新增计算」，是「把已有的结果传进去」**：

| 键 | `_collect_checks` | `render_json` | 能否直接复用 |
| --- | --- | --- | --- |
| `uninitialized` | ✅ | ✅ | **能**（键名相同） |
| `dead_code` | ✅ | ✅ | **能** |
| `type_mismatch` | ✅ | ❌ | — |
| `dup_code` | ✅ | ❌ | — |
| `shape_mismatch` | ❌ | ✅ | **不能**（`render_json` 独有） |

**结论：改动从 4 处降到 3 处，且完全不碰 `run_pipeline`。**
`shape_mismatch` 仍由 `render_json` 自己算（它是唯一没有上游缓存的那个）。

### 3.2 `render_json` 改为优先读 `model`

```python
def render_json(files, edges, stats, root, ..., model=None):
    ...
    "uninitialized": (getattr(model, "uninit", None)
                      if model is not None else
                      [r for mf in files for r in _detect_uninitialized(mf)]),
```

**默认 `None` 时保留旧路径** —— 这样 `--from-json`、测试、其它调用点都不会断。

### 3.3 `emit_outputs` 把 `model` 传下去

```python
render_json(..., model=model)
```

`emit_outputs` 里已经有 `model`（解包来的），传下去是一行。

### 3.4 `render_xml` 也要透传（这是第 4 处，初版漏了）

`render_json` 共 **7 处调用**：

| 行 | 位置 | 需要传 model？ |
| --- | --- | --- |
| L14229 | 定义 | — |
| **L19706** | **`render_xml` 内部** | **要**（否则 XML 又算一遍） |
| L33248 | `emit_outputs` | **要** |
| 4 处 | `tests/test_matlabc.py`（空 `files=[]`） | 不用（默认 None 走旧路径） |

所以 `render_xml(files, edges, stats, root, ..., model=None)` 也要加同款参数，
并把它透传给内部的 `render_json(...)`。

**判据追加一条**：`--xml` 与 `--json` 同时比较（XML 是从 JSON 转的，
如果 JSON 变了 XML 必变；反之若只 XML 变，说明透传漏了）。

**⚠ XML 也被时间戳污染**（实测 `--xml` 输出 65,093 字节，第 3 行就是
`<generated_at>2026-10-17T19:38:28</generated_at>`）。所以 XML 的判据**不能**是
「逐字节」——要么用 `sed` 去掉该行后比，要么给 `json_diff` 加一个 xml 模式。
这一点是本轮实测发现的，与 F1 时 JSON 的情形完全同源。

---

## §4 判据（三层，都能红）

| # | 判据 | 命令 / 期望 |
| --- | --- | --- |
| 1 | 除 `heuristics` 外一个字都不许变 | `json_diff before.json after.json --ignore generated_at --ignore heuristics` → **rc=0** |
| 2 | `heuristics` 只增不减 | 条数 **≥ 5**（旧值） |
| 3 | `facts` 与 `heuristics` 同量 | `len(result.facts) == len(heuristics)` |

第 1 条是本轮新增的工具直接支撑的（`tools/json_diff.py`，R147）。
第 2 条的「只增不减」比「等于某个数」更重要——后者会把「少了一条告警」当成通过。

**反向验**：把 `_detect_dead_code` 的过滤条件改一行（比如 `min_confidence` 调高），
第 1 条必须红（因为 `dead_code` 键变了）。

---

## §5 为什么这一步值得付一次整树重跑

| 收益 | 可测吗 |
| --- | --- |
| 消除 2–3 次重复遍历 | 是：`--json` 的 `stats` 里有耗时/计数；也可用 `_detect_dead_code` 调用计数 |
| facts 覆盖三类 ⇒ LSP 能发三类诊断 | 是：`facts` 条数、`m_dead_code` / `m_shape_mismatch` 的 rule_id |
| 三处口径统一 | 是：第 1 条判据 |

**代价**：改 `matlabc.py` ⇒ 一次整树重跑（实测 541–1233 秒）。

---

## §6 下一步

1. 探针收口（当前 `14dd32ea` 的这次跑完 → 改 `KERNEL_RUN.md` 一行 → 24/24）。
2. **F2 一次做完**：三处改动 + 三条判据 + 一次探针。
3. F3：LSP / SARIF 改从 `facts` 派生，四方条数相等。
