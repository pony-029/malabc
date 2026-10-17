# 2026-10-17 · 单文件分析不等价：`analyze_file` 这条路走不通

> 上一轮的建议是「LSP 的下一步是 `analyze_file(path)` 单文件入口」。
> 本轮实测**否掉了它**：至少对 `doc_todos`，单文件与全量不等价。

---

## §0 一句话结论

| 文件 | 类型 | 全量 todos | 单文件 todos | 一致？ |
| --- | --- | --- | --- | --- |
| `a.m` | 普通函数 | 3 | 3 | **是** |
| `MyCls.m` | `classdef` | **2**（含 `description`） | **0** | **否** |

`a.m` 看着没问题，`MyCls.m` 直接少了全部两条。

**⇒ `doc_todos` 依赖跨文件上下文，单文件分析不可用。**

---

## §1 实测

```python
r_full = run_pipeline(ns, ROOT, collect_files(ROOT))      # 13 文件 / 18 todos
r_one  = run_pipeline(ns, ROOT, [Path(ROOT)/"MyCls.m"])   #  1 文件 /  3 todos
```

`MyCls.m` 的对比：

```
full  MyCls.m  [('MyCls.m', 7,  ('description','author','version')),
                ('MyCls.m', 14, ('description','author','version'))]
one   MyCls.m  []
```

**全量给出两条「缺 description」，单文件一条都不给。**

`a.m` 的对比（对照组）：

```
full  a.m  [('a.m',1,('author','version')), ('a.m',6,...), ('a.m',11,...)]
one   a.m  [('a.m',1,('author','version')), ('a.m',6,...), ('a.m',11,...)]
A_M_SAME True
```

**对照组通过了**——所以不是"单文件分析完全不行"，而是**某些文件类型需要跨文件上下文**。

---

## §2 为什么 `MyCls.m` 特殊

`_collect_doc_todos(files, model.callers_of, tainted_funcs=...)` 的第二个参数是
`callers_of`，它来自 `edges`。单文件分析时 `edges` 为空（没有其它文件可调用），
所以任何依赖"被谁调用"的判断都会退化。

`MyCls.m` 是 `classdef`，它的方法头描述判定很可能走的是与类成员/调用关系相关
的分支——具体是哪一行需要再查，但**结论已经够用**：**不能假设单文件等价**。

---

## §3 对 LSP 的直接影响

上一轮 README 里写的是「下一步是单文件入口，把 370 秒降下来」。**这条必须撤回**。

LSP 的可行路径只剩两条：

| 路径 | 可行性 |
| --- | --- |
| **全量 + `--no-checks`**（现状） | 可行，约 370 秒 / 62,704 文件 |
| **增量索引 + 只重算变化文件** | 需要 `run_pipeline` 支持"部分文件 + 全部上下文"，改动大 |

第二条是真正的解法，但它**不是"单文件分析"**，而是「**全量上下文 + 只重解析变化的文件**」——
`Index` 已经能回答"哪些变了"，缺的是 `run_pipeline` 接受"复用其余文件的解析结果"。

---

## §4 一个更诚实的说法

LSP 现在的真实性能：**首次打开 = 一次全量分析（`--no-checks` 之后约 370 秒）**。

这在 13 个文件的玩具项目里是 0.07 秒，在 62,704 个文件的真实项目里是 6 分钟。
**在后者上它不是"慢"，是"不可用"**。所以：

- 短期：README 如实写「首次打开需要一次全量分析」；
- 中期：`Index` + 「复用未变化文件的解析结果」（P3 的核心工作）；
- 长期：`doc_todos` 若能改成"不依赖跨文件"，才可能走单文件。

---

## §5 判据（给将来的 `analyze_file`）

如果要重试这条路，判据必须是：

```
对**每一个** .m 文件：
    analyze_file(f) 的 doc_todos（该文件的条目）
  == analyze(ROOT) 的 doc_todos（该文件的条目）
```

**`a.m` 通过、`MyCls.m` 不通过，就说明不能用它**。本轮正是靠这条判据否掉了一个
看起来合理的优化。
