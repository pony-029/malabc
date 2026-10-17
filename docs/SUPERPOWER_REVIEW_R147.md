# R147 复盘：判据被自己的产物误判，然后把它变成工具

> 起因：R146 的 F1（`run_pipeline` 直接产 facts）本应「零输出变化」，
> 但按 R 记的判据「`--json` 逐字节不变」实测**当场红**。

---

## §0 一句话结论

`--json` 里内嵌 `generated_at` 时间戳，所以「逐字节不变」这条判据
**在任何干净改动上都必然失败**。本轮把它换成「忽略指定键后的规范化字节」，
并固化成 `tools/json_diff.py`（自证 6 条 + 真实用例 1 条）。

---

## §1 现场：字节数相同、sha 不同

```
before 90eec6620c12484d 62005
after  4f3ee0654cacc830 62005
IDENTICAL False
```

字节数**完全一致**，sha 不同 —— 这是典型的「噪声而非逻辑变化」信号。
定位第一处差异：

```
first diff at 62
-  "generated_at": "2026-10-17T19:32:42",
+  "generated_at": "2026-10-17T19:33:20",
```

**注意：这不是第一次被它坑。** R132 搬 `html_kit` 时，`--browse` 的
`index.html` 与 `manifest.json` 也因时间戳而 DIFF，当时是靠人工读 diff 放行的。
**同一个噪声源，两次误导判据。**

---

## §2 换判据：去掉不可控键，再比规范字节

```python
def canon(path, ignore):
    data = json.load(open(path, encoding="utf-8"))
    for key in ignore:
        data.pop(key, None)
    return json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2)
```

实测 F1 前后：

```
IDENTICAL {"ignored": ["generated_at"], "canon_bytes": 59521}
```

**这才是 F1 的等价证明。** 而原判据（逐字节）从设计上就不可能通过。

---

## §3 固化成工具：`tools/json_diff.py`

| 项 | 内容 |
| --- | --- |
| 用法 | `json_diff a.json b.json --ignore generated_at [--ignore heuristics]` |
| 退出码 | 0=一致 / 1=有差异（打印第一个差异键）/ 2=缺输入 |
| 自证 | 6 条（见下表） |

| 用例 | 期望 |
| --- | --- |
| 完全相同的两份 | 0 |
| 只差时间戳 **且已忽略** | 0 |
| 只差时间戳 **但未忽略** | **1**（必须红，否则工具恒绿） |
| 忽略 `heuristics` 后一致 | 0 |
| 其它键变了（`files`） | **1**（必须红） |
| 缺文件 | 抛异常（不许静默当一致） |

**第三条是关键**：如果没有它，一个「永远返回 0」的实现也能通过前两条。

---

## §4 接进流程：三条冒烟 → 四条

`CONTRIBUTING.md` 的「改 `main` / 分析入口后的冒烟」新增第 4 条：

```powershell
python tools/json_diff.py before.json after.json --ignore generated_at
```

并写明**为什么不能省**：`--json` 与 `--browse` 的 `manifest.json` 都内嵌时间戳，
逐字节判据在干净改动上必然失败；用它才是真的等价证明。

---

## §5 为什么这算 RSI（递归自我改进）

本轮**没有改产品代码**，改的是「判断产品代码对不对」的方法：

| 层 | 改进前 | 改进后 |
| --- | --- | --- |
| 代码 | F1 已完成（R146） | 不变 |
| **判据** | `--json` 逐字节（被时间戳污染） | 忽略时间戳的规范字节 |
| **流程** | 三条冒烟 | 四条冒烟 + 工具化 |

**一个判据如果在「什么都没变」时会红，它就不是判据，是噪声源。**

---

## §6 状态

```
check_eol_convention  OK（321 个文本文件）
check_help_contract   OK（25 个护栏脚本）
check_all             23/24（W2 等整树重跑，探针 19:33:59 启动）
main                  145 行（原 2,020）
facts                 5 条（m_missing_doc），与 --json 的 heuristics 同源同量
```

---

## §7 下一步

1. **F2**：把 `uninitialized` / `dead_code` / `shape_mismatch` 并入 facts 与 `heuristics`。
   判据用本轮的工具：`json_diff --ignore generated_at --ignore heuristics` 必须 0，
   且 `heuristics` 条数 **只增不减**。
2. **F3**：LSP / SARIF 改从 facts 派生，四方条数相等。
3. 每次改 `--json` 相关代码，第 4 条冒烟必跑。
