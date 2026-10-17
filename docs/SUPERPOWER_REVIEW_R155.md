# R155 复盘：先换数据源，再扩数据 —— 顺序本身就是判据

> F3 有三步：① facts 扩两类 ② LSP 改读 facts ③ 判据从 `==` 变 `⊇`。
> 常规顺序是 ①→②。本轮**故意倒过来**先做 ②，理由是它能被单独证伪。

---

## §0 一句话结论

**在 facts 还等于 heuristics 的时候先换数据源**，19 条旧判据全绿就等于证明了
「换源没有改变任何行为」。等 facts 扩了再换，红绿混在一起，分不清是谁的问题。

---

## §1 倒序的价值

| 顺序 | 换源时的状态 | 如果红了，说明什么 |
| --- | --- | --- |
| ①→②（常规） | facts 已经比 heuristics 多 | **分不清**是换源错了还是扩容错了 |
| **②→①（本轮）** | facts == heuristics | **只可能是换源错了** |

实测：

```
python tools/lsp_selftest.py            → 19/19 绿    ← 换源后旧能力没退化
python tools/lsp_selftest.py --uninit   → 1 红        ← 信号还在（facts 未扩）
```

**这两个读数同时成立，才是「换源正确且扩容未做」的完整证据。**
少任何一个都说不清当前状态。

---

## §2 `_facts_from_result` 的形状映射

facts 的字段：

```python
{"kind": "issue",
 "loc": {"file": "x.m", "line": 3},
 "subject": "x.m:x",
 "payload": {"rule_id": "c_uninit_read", "level": "warning", "msg": "..."},
 "evidence": "check"}
```

LSP 诊断需要的是 `{file, line, func, kind, msg, level}`：

```python
"file":  loc["file"]
"line":  loc["line"]
"func":  subject.rsplit(":", 1)[-1]     # "x.m:x" -> "x"
"kind":  payload["rule_id"]
"msg":   payload["msg"]
"level": payload["level"]
```

**六项一一对应，没有一处需要「再算一遍」**。这就是 F1 把 facts 前置化的回报：
LSP 不需要知道 `m_missing_doc` 和 `c_uninit_read` 各自是怎么检测的，它只读 facts。

---

## §3 超集关系为什么不需要「对账」

旧判据是：

```
LSP 诊断 == `--json` 的 heuristics
```

F3 之后要变成：

```
LSP 诊断 ⊇ heuristics，且每条都能溯源到 facts
```

**但注意**：LSP 现在**就是**从 facts 派生的，而 `heuristics` 也是从
`model.doc_todos` 派生的（facts 里那 5 条 `m_missing_doc` 与它同源同量）。

⇒ **「每条都能溯源到 facts」这一条，由构造保证，不需要写断言。**
要写的只有「⊇」——而它也是构造保证的（facts 只增不减）。

**所以 F3 的判据里真正需要写死的只有两条**：

| # | 判据 | 为什么它不能靠构造保证 |
| --- | --- | --- |
| 1 | `--json` 的 `heuristics` 条数不变（仍是 5） | 万一有人顺手改了 `render_json` 的过滤条件 |
| 2 | `--uninit` 组从红转绿 | 万一 facts 扩了但字段形状不对（比如 `line` 差 1） |

**其余的关系是结构性的，写断言反而是重复。**

---

## §4 状态

```
F1  facts（5 条 m_missing_doc）              ✅ 5724aaf
F2  render_json/xml 复用 checks              ✅ f9747a7
F3  ① facts 扩两类                           ⬜ 脚本 ready（943 字节）
F3  ② LSP 改读 facts                         ✅ 4eb8321
F3  ③ --uninit 从红转绿                       ⬜ 等 ①
```

判据现状：

```
tools/lsp_selftest.py           19/19 绿
tools/lsp_selftest.py --uninit  1 红（预期）
```

---

## §5 下一步

1. 探针跑完 → 收口（`KERNEL_RUN.md` 一行 sha）
2. `python C:\temp\f3_facts.py --apply`（943 字节）
3. `json_diff before after --ignore generated_at` → 必须 `IDENTICAL`
4. `python tools/lsp_selftest.py --uninit` → 必须从红转绿
5. `python tools/lsp_selftest.py` → 必须仍 19/19

**第 3 步与第 4 步必须同时成立**：前者证明「扩 facts 没碰输出」，后者证明
「LSP 真的读到了新事实」。只做前者是「没弄坏」，只做后者是「有新能力」——
**两件事都要有证据。**
