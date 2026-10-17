# R149 复盘：三个结论，两个被实测修正，一个被扩大

> 本轮没改产品代码（探针在跑），只做 F2 的前置调查。
> 但调查过程里，我自己写下的三个判断有两个是错的。

---

## §0 一句话结论

| 判断 | 状态 |
| --- | --- |
| `model.uninit` 是死字段 | **错**（赋值走 `SimpleNamespace(uninit=...)`） |
| `dead_code` / `shape_mismatch` 不在 `model` 上 | **对** |
| F2 要改 3 处 | **少算了**（`render_xml` 也要透传 ⇒ 4 处） |

---

## §1 错的那个：`model.uninit` 不是死字段

第一版文档写：

> **`model.uninit` 是一个死字段**：全仓 grep 只找到两处读它，没有任何一处给它赋值。

依据是 `grep "model\.uninit|\.uninit\s*="` 只命中 2 处（都是注释/docstring）。

后来补分母时跑了一次运行时验证：

```python
print('has uninit in dict', 'uninit' in getattr(m, '__dict__', {}))
# has uninit in dict True
```

再查 `uninit=`：

```
19863:    return SimpleNamespace(
...
19868:        variables=variables, varflow=varflow, uninit=uninit)
```

**赋值走的是 kwargs 路径**，grep 模式根本没覆盖。

**教训**：任何「某某字段没人赋值」的结论，必须用运行时验证
（`'key' in obj.__dict__`）兜底，不能只靠静态 grep。**grep 模式要覆盖
`x.attr =` / `f(attr=...)` / `setattr(x, "attr", ...)` / 解包赋值 四条路径。**

---

## §2 对的那个：三处口径分裂

| 名字 | 在 `model` 上 |
| --- | --- |
| `uninit` | 是（L19863–19868） |
| `dead_code` | **否** |
| `shape_mismatch` | **否** |

三类检测的调用点：

```
L14295/14300/14310   render_json        算 3 次
L19855               build_analysis_model（uninit）
L25846/25854/25864   另一处渲染         再算 3 次
```

⇒ **同一批检测被算 2–3 次**。这才是 F2 真正要治的病（不是"没数据"）。

---

## §3 被扩大的：F2 是 4 处改动，不是 3 处

`render_json` 共 **7 处调用**：

| 行 | 位置 | 要传 `model`？ |
| --- | --- | --- |
| L14229 | 定义 | — |
| **L19706** | **`render_xml` 内部** | **要** |
| L33248 | `emit_outputs` | **要** |
| 4 处 | `tests/test_matlabc.py`（空 `files=[]`） | 不用 |

所以 `render_xml` 也要加 `model=None` 并透传。**初版漏了它**——如果只改
`emit_outputs`，`--xml` 仍会自己算一遍，F2 的收益减半。

---

## §4 新实测：`--xml` 也带时间戳

```
xml_bytes = 65093
<?xml version="1.0" encoding="UTF-8"?>
<matlabc version="1.16.72">
  <version>1.16.72</version>
  <generated_at>2026-10-17T19:38:28</generated_at>
```

所以 XML 判据**也不能逐字节**。已在 `tools/json_diff.py` 加 `--xml` 模式：

```powershell
python tools/json_diff.py a.xml b.xml --xml --ignore generated_at
# IDENTICAL {"mode": "xml", "ignored": ["generated_at"], "canon_bytes": 62765}
```

自证从 6 条扩到 **9 条**（3 条 XML：只差时间戳 / 未忽略必须红 / 内容变了必须红）。

---

## §5 F2 的完整清单（下次一次性做完）

| # | 改动 | 判据 |
| --- | --- | --- |
| ① | `run_pipeline` 把 `dead_code` / `shape_mismatch` 存到 `model` | `model.dead_code` 非空（若有告警） |
| ② | `render_json` 加 `model=None` + 优先读 | `json_diff --ignore generated_at --ignore heuristics` → 0 |
| ③ | `render_xml` 加 `model=None` + 透传 | `json_diff --xml --ignore generated_at` → 0 |
| ④ | `emit_outputs` 两处都传 `model` | 同上 |
| ⑤ | facts 扩三类 | `facts` 条数 == `heuristics` 条数，且 `heuristics` ≥ 5 |

---

## §6 状态

```
check_eol_convention  OK（323 个文本文件）
check_py36_clean      OK（94 个 .py）
check_help_contract   OK（25 个护栏脚本）
tools/json_diff.py    自证 9 条；JSON 与 XML 两种模式都实测通过
check_all             23/24（W2，探针 19:33:59 启动）
```

---

## §7 下一步

1. 探针收口（连续第三轮挂着）。
2. F2 五条一次性做完 + 一次探针。
3. F3：LSP / SARIF 从 facts 派生。
