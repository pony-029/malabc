# R158 复盘：验证脚本用副本，等待探针用纪律

> 这两轮（R158 / R159）没有产品代码产出。它们做的是两件**防止返工**的事。

---

## §0 一句话结论

| 做法 | 省掉什么 |
| --- | --- |
| 改大文件的脚本**先在副本上跑** | 一次「插错位置 → 回滚 → 重跑 20 分钟探针」 |
| 探针运行期间**什么都别跑** | 一次「9 分钟被拖成 18 分钟 / 被终止」 |

---

## §1 副本验证覆盖了什么

`f3_facts.py` 要往 `matlabc.py` 插 943 字节。探针正在用那份文件，所以复制一份到
`C:\temp\mc_copy.py`，把路径替换掉，真执行：

```
anchor matches: 1
applied at offset 1355319
syntax OK
L32533  for _ck, _rule, _lvl in (("uninitialized", "c_uninit_read", "warning"),
L32534                        ("dead_code", "m_dead_code", "note")):
```

| 失败模式 | dry-run | 副本执行 |
| --- | --- | --- |
| 锚点找不到 | ✅ | ✅ |
| 缩进错了 | ❌ | ✅（`ast.parse`） |
| 插到了块外面 | ❌ | ✅（看行号） |
| 转义写坏 | ❌ | ✅ |

**dry-run 只能证明「找不到会报错」，副本执行能证明「找到了、插对了、文件还是好的」。**

成本 10 秒，覆盖后三种。

---

## §2 「等待」也是一条判据

探针跑在 9–23 分钟的区间里。这两轮它已经跑了 9+ 分钟仍未落盘——**这是正常的**。

前两次异常（18.5 分钟、6 分钟被终止）的根因都指向同一个：**我在它跑的时候做了别的事**。

所以这两轮我做的事只有：
- `Get-Content`（只读日志）
- `Test-Path`（只读存在性）
- `git status`（只读）
- 写文档（不占 CPU/IO）

**`_detect_dup_code` 的 profile 我想做，但没做** —— 它会跑 Python，会抢 IO。
**忍住不做，是这一轮唯一有价值的决定。**

---

## §3 一个反直觉的点：`alive=False` 不等于「跑完了」

| 状态 | `alive` | `done` 行 | `json` | stderr |
| --- | --- | --- | --- | --- |
| **正常完成** | False | **有** | 有 | 空 |
| **超时** | False | 有（`rc=124`） | 无 | 空 |
| **被终止** | False | **无** | 无 | **空** |

**三者 `alive` 都是 False。** 区分它们靠的是 `done` 行与 `json` 是否存在。

这条已经写进 `CONTRIBUTING` 第 6.5 条（R156）。

---

## §4 状态

```
F1  facts（5 条 m_missing_doc）              ✅ 5724aaf
F2  render_json/xml 复用 checks              ✅ f9747a7
F3  ② LSP 读 facts                           ✅ 4eb8321
F3  ① facts 扩两类                           ⬜ 脚本副本验证通过，等探针结束后执行
F3  ③ --uninit 从红转绿                       ⬜ 等 ①
```

探针：`PID 30428`，23:49:32 启动，**9+ 分钟，正常区间内**。

---

## §5 下一步（四步，全部已就绪）

```
① python C:\temp\f3_facts.py --apply           # 副本上已验证
② json_diff before after --ignore generated_at  # 必须 IDENTICAL
③ python tools/lsp_selftest.py --uninit         # 必须从红转绿
④ python tools/lsp_selftest.py                  # 必须仍 19/19
```
