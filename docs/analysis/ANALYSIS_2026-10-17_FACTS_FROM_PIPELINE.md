# 2026-10-17 · 让 `run_pipeline` 直接产事实（facts 前置化）

> 为什么现在必须做：LSP 只能发 `m_missing_doc` 一类诊断，因为 `--json` 的
> `heuristics` 只包含这一类（`matlabc.py:14272-14286` 的注释自己写着"其余
> 检查类别未并入"）。要让 LSP 发 `uninitialized` / `shape_mismatch` /
> `dead_code`，不是"再加几个 if"，而是**让分析与出口之间有事实层**。

---

## §0 一句话结论

现在的事实层是**后置**的：`facts.py` 从 `--json` 载荷反推事实（R110 做的），
它只能看到报表里**已经有**的东西。要做的是**前置**：`run_pipeline` 在算完
模型后直接产 `Fact[]`，报表与 LSP 都从它派生。

**区别一句话**：

| 形态 | 位置 | 能看到什么 |
| --- | --- | --- |
| 后置（现状） | `facts.facts_from_payload(--json)` | 只有报表里已聚合的 5 类 |
| 前置（目标） | `run_pipeline` 末尾 | 每个文件、每个函数、每条告警的位置级事实 |

---

## §1 现状的三处口径分叉（都指向同一件事）

| 数据 | 在哪 | 谁在看 |
| --- | --- | --- |
| `heuristics`（5 条，`m_missing_doc`） | `--json` 顶层 | 站点、SARIF、LSP |
| `uninitialized` / `dead_code` / `shape_mismatch` | `--json` 各自键 | 站点（各自页） |
| `checks_for_sarif`（6 条） | `PipelineResult` | SARIF |

**三处都不是同一个集合。** `checks_for_sarif` 6 条、`heuristics` 5 条、
`uninitialized` 0 条（`sample_m` 实测）——**没有一处是"全部告警"**。

这就是 LSP 只能发一类的根因：**它没有"全部告警"这个集合可读**。

---

## §2 目标形态

```python
# run_pipeline 末尾
return PipelineResult(
    files=..., index=..., edges=..., stats=..., model=..., c_model=...,
    checks_for_sarif=...,
    facts=facts,            # ← 新增：Fact[]
)
```

`Fact` 沿用 `facts.py` 已定义的最小形状（不新造）：

```python
{"kind": "issue",                    # def / ref / call / issue / unresolved / unimplemented
 "loc": {"file": "a.m", "line": 12, "col": 5},
 "subject": "a.m:foo",
 "payload": {"rule_id": "m_missing_doc", "level": "note", "msg": "..."},
 "evidence": "ast"}                  # text < decl < ast < exec
```

---

## §3 三处派生（单向，不许回写）

```
                    ┌──→ --json 的 heuristics（按 rule_id 过滤）
run_pipeline ──facts├──→ SARIF（rule_id → ruleId）
                    └──→ LSP 诊断（loc.line - 1）
```

**判据（这条能红）**：

```
facts 里 rule_id == "m_missing_doc" 的条数
  == `--json` 的 heuristics 条数（5）
```

删一条 fact ⇒ 报表少一条 ⇒ 判据红。

**反向不许**：报表不能反推 facts（那就退化成现状的后置形态）。

---

## §4 分三步（每步都能独立提交）

| 步 | 内容 | 判据 |
| --- | --- | --- |
| **F1** | `run_pipeline` 产 `facts`，但**先只覆盖 `m_missing_doc`**（与现状等价） | `facts` 里该规则的条数 == `--json` 的 heuristics 条数；`--json` 逐字节不变 |
| **F2** | 把 `uninitialized` / `dead_code` / `shape_mismatch` 也产成 facts，同时**扩 `heuristics` 通道** | `heuristics` 条数从 5 → 全部告警数；`--json` 的**其它键不变**（只新增，不改旧） |
| **F3** | LSP 与 SARIF 都改从 `facts` 派生 | 三方条数相等（facts == JSON == SARIF == LSP） |

**F1 是关键**：它不改变任何输出（`--json` 逐字节不变），只是**建立通道**。
通道建成后，F2 才是"加数据"，而不是"改结构"。

---

## §5 为什么不直接扩 `heuristics` 列表

有人会问：既然只是多几类，为什么不直接在 `render_json` 里多写几个 `for`？

答案是**会重复计算**：

- `uninitialized` 已经在 `_detect_uninitialized(files)` 里算过，结果进了 `model.uninit`；
- `dead_code` 在 `_detect_dead_code(files)` 里算过；
- 如果在 `render_json` 里再循环一遍 `model.uninit` 造 `heuristics`，那是**第二次遍历**，
  而且一旦两处过滤条件不同（比如一处按 `min_confidence` 过滤），就出现"同一批告警，
  报表与 LSP 数量不同"——这正是本仓最贵的病。

**事实层的作用就是让"遍历一次、多处派生"成为结构上的默认。**

---

## §6 与已完成的 P1 的关系

P1 已经把 `run_pipeline` 抽成 183 行、零跨界变量的纯函数（R124/R125）。
**这正是 facts 前置能做的前提**：只要在它的 `return` 之前插一段产事实的代码，
不需要动 `main`、不需要动 `emit_outputs`。

⇒ F1 的改动面：`run_pipeline` 末尾 +10 行、`PipelineResult` 加一个字段、
`emit_outputs` 解包多一行。**三处，都是加法。**

---

## §7 下一步

1. **F1**：`run_pipeline` 产 facts（只覆盖 `m_missing_doc`），`--json` 逐字节不变。
2. **F2**：扩三类告警进 facts，同时扩 `heuristics`（只新增键，不改旧键）。
3. **F3**：LSP / SARIF 改从 facts 派生，三方条数相等的判据。

**F1 做完之前，不要动 LSP 的诊断范围** —— 否则 LSP 会自己扫 `model.uninit`，
那就是第三处口径。
