# 2026-10-18 · `run_pipeline` 的 `reuse` 接口（LSP 的正解）

> 单文件分析已被实测否掉（`MyCls.m` 全量 2 条 / 单文件 0 条）。
> 剩下的唯一路径是**全量上下文 + 复用未变化文件的解析结果**。
> 本文只定接口与判据，不改代码。

---

## §0 一句话结论

`run_pipeline` 目前每次都 `parse_file` 全部文件。要让它接受一份
「上次的 `files` 列表」，**只对变化文件重新解析**，其余直接复用
——**上下文仍覆盖全部文件**，所以 `doc_todos` 的跨文件依赖不会退化。

### §0.1 ⚠ 先纠正：`--incremental` 已经存在，但它不是这个

`run_pipeline` 里已有 `args.incremental` 分支（L32360-32378），用
`.matlabc_cache.pkl` 缓存 `MatlabFile`。**它是跨进程的**。

| | `--incremental`（已有） | **`reuse`（本文）** |
| --- | --- | --- |
| 载体 | **pickle 文件** | **进程内 list** |
| 序列化开销 | 有（反序列化每个 `MatlabFile`） | **无** |
| 适用 | CLI 多次调用 | **LSP 常驻进程** |
| 实测（13 文件） | **0.066s → 0.653s（慢 10 倍）** | 未测，预期无额外开销 |
| 实测（1300 文件） | 3.20s → 2.20s（快 31%） | 未测 |

**⇒ 小项目上 `--incremental` 是负优化**（pickle 反序列化 13 个对象 >
直接解析 13 个小文件），这条已在 R136b 实测记录。

**LSP 要的是"进程内复用"**：它常驻，`MatlabFile` 本来就在内存里，
**根本不需要序列化**。所以 `reuse` 不是 `--incremental` 的别名，
而是它的"无序列化版本"。

---

## §1 为什么不是 `analyze_file`

| 方案 | 上下文 | `MyCls.m` 的 `doc_todos` |
| --- | --- | --- |
| `analyze_file(MyCls.m)` | 只有 1 个文件 | **0 条**（`callers_of` 为空） |
| **`reuse` 全量 + 增量解析** | **全部文件** | **2 条**（与全量一致） |

**区别不在"解析多少"，而在"上下文有多少"。**

---

## §2 接口形状

```python
def run_pipeline(args, root, paths, prev=None, changed=None):
    """
    prev    : 上次的 `files`（`List[MatlabFile]`），None 表示全量
    changed : 变化文件的 rel 集合；`prev` 非空时必须给
    """
```

**语义**：

1. `prev is None` → 现有行为（全量 `parse_file`），**逐字节不变**
2. `prev is not None` → 对 `paths` 里 `rel` 不在 `changed` 的文件，直接取 `prev` 中同名项；
   其余 `parse_file`

**关键：`files` 的顺序必须与全量一致** —— 否则 `edges` 的构建顺序、去重与 `--json` 的输出顺序都会变。

---

## §3 判据（四条，缺一不可）

| # | 判据 | 期望 |
| --- | --- | --- |
| 1 | `--json` | `json_diff --ignore generated_at` → **rc=0** |
| 2 | `--browse` | `tree_diff --ignore-line ... --ignore-file manifest\.json` → **same** |
| 3 | `--mermaid` / `--dot` | 与全量**逐字节相等** |
| 4 | **`rel` 顺序** | `[f.rel for f in files]` 与全量**完全相同**（前三条可能漏掉顺序差异） |

**第 4 条是这次特有的**：前三条比的是"内容"，而 `reuse` 最可能出错的地方是**顺序**
——`sorted()` 与"按 `prev` 顺序拼接"会给出不同结果，而内容可能恰好相同。

---

## §4 改动点（三处）

| # | 位置 | 改动 |
| --- | --- | --- |
| ① | `run_pipeline` 开头 | 接受 `prev` / `changed`，构造 `files` |
| ② | 同上 | `prev` 非空且 `changed` 为空时**直接复用整个 `files`**（零解析） |
| ③ | `__main__` / LSP | 保存上次结果并传入 |

**第 ② 条是 LSP 的日常路径**：用户只是滚动、不编辑时，`changed` 为空，**解析耗时 0**。

---

## §5 风险与对策

| 风险 | 对策 |
| --- | --- |
| `prev` 里的 `MatlabFile` 被下游**修改**（污染缓存） | 判据：跑两次 `reuse`，第二次结果与第一次**相同** |
| `paths` 与 `prev` 的 `rel` 不匹配（大小写、分隔符） | 统一用 posix rel 做 key |
| `changed` 里给了不存在的文件 | 忽略（它本来就不在 `prev` 里） |
| 内存（持有 62,704 个 `MatlabFile`） | 已知：LSP 常驻进程，可接受；CLI 一次性，不启用 |

---

## §6 预期收益

以 1300 个 `.m` 实测的 profile 为基准：

| 成分 | 全量 | `reuse`（无变化） |
| --- | --- | --- |
| `parse_file` | 1.65s（31%） | **0** |
| `build_analysis_model` | 0.44s（11%） | 0.44s |
| `_collect_checks` | 已由 `--no-checks` 关闭 | 0 |
| **合计** | 2.18s | **约 0.5s** |

**4 倍左右**，且随文件数线性放大。

**但注意**：`build_analysis_model` 仍要跑全量（它依赖 `id(f)` 与 `edges`）。
**如果那个也成为瓶颈，下一步是让 `model` 也支持增量**——那是 P3 的事。

---

## §7 状态

```
R143  单文件分析被否掉                       ✅
R144  README 撤回该建议                       ✅
R145  reuse 接口设计与判据                    ⬜ 本文
R146  reuse 实施（三处 + 四条判据 + 一次探针）  ⬜ 待续
```
