# 2026-10-17 · F3：facts 扩三类，LSP 改读 facts

> F2 让 `render_json` / `render_xml` **不再重算** `uninitialized` / `dead_code`
> （复用 `checks_for_sarif`），判据是 `--json` / `--xml` 双 `IDENTICAL`。
> F3 要往前走一步：**让 LSP 能发的不止 `m_missing_doc`**。

---

## §0 一句话结论

F3 **只扩 `facts`，不扩 `--json` 的 `heuristics`** —— 这样 `--json` 保持
零变化（判据仍是 `IDENTICAL`），而 LSP 从"1 类诊断"变成"4 类"。

代价是：**LSP 的硬判据必须改**，从「诊断 == `--json` 的 heuristics」
变成「诊断 ⊇ heuristics，且每条都能在 facts 里找到」。

---

## §1 为什么不能顺手把 `heuristics` 也扩了

`--json` 的 `heuristics` 现在只有 `m_missing_doc`（5 条），源码里明说
「其余检查类别仍留在各自键里、**未并入**这条通道」。

如果 F3 顺手扩它：

| 后果 | 说明 |
| --- | --- |
| `--json` 字节变了 | 所有拿它做快照/基线的下游全部要重跑 |
| LSP 判据失去对手方 | 「诊断 == heuristics」两边同时变，等于没判据 |
| SARIF 口径被牵连 | SARIF 也在读同一批 checks，三处可能再分叉 |

**所以 F3 的边界是：`facts` 扩，`heuristics` 不动。**

---

## §2 F3 的改动（三处）

| # | 改动 | 位置 |
| --- | --- | --- |
| ① | `run_pipeline` 里 `facts` 追加三类 | `facts = []` 那段之后 |
| ② | `matlabc_lsp.py` 的诊断改读 `result.facts` | `_heuristics_from_result` 改成 `_facts_from_result` |
| ③ | `model.doc_todos` 那条仍保留（facts 已含它，二选一） | — |

### 2.1 facts 追加的字段形状（与 F1 一致）

```python
{"kind": "issue",
 "loc": {"file": ..., "line": ...},
 "subject": ...,
 "payload": {"rule_id": "c_uninit_read" / "m_dead_code" / "m_shape_mismatch",
             "level": "warning" / "note",
             "msg": ...},
 "evidence": "check"}     # ← F1 的是 "ast"，这里区分来源
```

**`evidence` 必须区分**：F1 的 `m_missing_doc` 来自 AST 扫描，这三类来自
`_collect_checks`。**同一个 facts 数组里混两种来源，`evidence` 是唯一的辨别依据。**

### 2.2 严重级别映射

| rule_id | level |
| --- | --- |
| `m_missing_doc` | `note`（缺文档是提示） |
| `c_uninit_read` | **`warning`**（可能读未初始化 = 潜在崩溃） |
| `m_dead_code` | `note` |
| `m_shape_mismatch` | **`warning`** |

**LSP severity 映射沿用 `matlabc_lsp.py` 那张表**（`warning` → 2）。

---

## §3 判据演进（这是 F3 最需要想清楚的部分）

### 3.1 现在这条判据会失效

```
LSP 诊断 == `--json` 的 heuristics
```

F3 之后 LSP 发 4 类，而 `heuristics` 只有 1 类 —— **这条判据会红，而且是应该红**。

### 3.2 新判据（三条，都能红）

| # | 判据 | 期望 |
| --- | --- | --- |
| 1 | **超集**：`heuristics` 的每一条都能在 LSP 诊断里找到 | 逐条命中 |
| 2 | **同源**：LSP 每条诊断的 `(file, line-1, code)` 都能在 `facts` 里找到 | 逐条命中 |
| 3 | **反例**：`switch_case.m`（只缺 author/version）仍是 **0 条** | 不许误报 |

**第 1 条保的是「没有丢」**，第 2 条保的是「没有编」，第 3 条保的是「没有滥」。

**三条合起来，比原来那条「==」更强**：原来只证明两个来源数量一致，
现在证明「一个包含另一个，且包含的那部分有出处」。

### 3.3 还要一条：`--json` 不许变

F3 改的是 `run_pipeline`（`facts` 追加），**理论上不碰 `--json`**。所以：

```
json_diff before after --ignore generated_at  →  rc=0
```

**这条如果红了，说明 facts 的追加意外影响了别的键** —— 那是必须当场查的。

---

## §4 F3 之后，LSP 的诊断变成什么样

| 文件 | 现在 | F3 之后 |
| --- | --- | --- |
| `MyCls.m` | 2 条（缺 description） | 2 条（不变） |
| `a.m` | 0 条 | 0 条（该语料无 uninit/dead_code） |
| `switch_case.m` | 0 条 | **0 条**（反例保持不变） |

**注意：`tests/sample_m` 里 `uninitialized` 是 0 条**（实测），所以 F3 在
这个语料上**看不出差别**。

⇒ **F3 必须另造一个反例语料**（比如一个真的读未初始化变量的 `.m`），
否则"扩了四类"这件事没有任何判据能证明。

**这是 F3 最大的风险**：改完之后所有判据都绿，但没人知道新能力是否真的工作。

---

## §5 执行手册（R157 起，四步 + 排查）

| 步 | 命令 | 期望 | 失败时查什么 |
| --- | --- | --- | --- |
| ① | `python C:\temp\f3_facts.py --apply` | 943 字节、锚点 1 处 | 锚点被 F2 改动过 ⇒ 重新测（行号会漂） |
| ② | `json_diff before after --ignore generated_at` | `IDENTICAL` | facts 追加意外影响 `--json` ⇒ 查是否碰了 `heuristics` |
| ③ | `python tools/lsp_selftest.py --uninit` | 从红转绿 | **先查 `loc["line"]` 是不是 1-based** |
| ④ | `python tools/lsp_selftest.py` | 仍 19/19 | 换源有副作用 ⇒ 查 `_facts_from_result` 的六字段映射 |

**②③④ 的顺序不能变**：先证明「没弄坏输出」，再证明「有新能力」，最后证明「旧能力没退化」。

**第 ③ 步最常见的错**：**已实测确认** `checks_for_sarif["uninitialized"][0]["line"] == 3`，
而源文件第 3 行正是 `y = a + b;` —— 所以 `line` 是 **1-based**。
LSP 诊断要 **0-based**，`_diagnostics_for` 里已经 `- 1`，`_facts_from_result` 只做透传。
⇒ **`loc["line"]` 必须保持 1-based**，转成 0-based 只在一处（`_diagnostics_for`）。
如果 `--uninit` 红且行号差 1，就是有人在这条链上加/减了两次。

同一测还确认：`tests/sample_uninit` 的 `facts` 是 **0 条**（`x.m` 有 description），
所以 F3 第 ③ 步转绿**只可能来自 checks 那两条**，不可能巧合地被 `m_missing_doc` 蒙对。

**第 ① 步的锚点脆弱性**：`f3_facts.py` 用 `"evidence": "ast",\r\n        })\r\n`
作为锚点。**F2 已经改过这一段附近**，所以执行前必须先 dry-run 看 `anchor matches: 1`。
锚点漂了不要硬改，重新用 `ast` 定位那段 `facts = []` 的位置。

---

## §6 状态

```
F1  facts（5 条 m_missing_doc）          ✅ 5724aaf
F2  render_json/xml 复用 checks          ✅ f9747a7
F3  facts 扩三类 + LSP 读 facts          ⬜ 本方案
```
