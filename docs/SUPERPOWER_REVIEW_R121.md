# R121 复盘：S2a —— 纯语言分发先独立，因为整段 S2 会同时改 6 处 return

> R119 完成了 S1（`cli_entry`）。本轮本该做 S2（`run_pipeline`），
> 但读代码后发现：**分析段里散布着 6 处提前 `return`**，其中三处直接调用产物函数
> （`_run_c_only` / `_run_ext_only`）。整段切会让"纯流水线"和"独立任务"混在一起。
> 所以先做其中唯一干净的一块：**纯语言分发**。

---

## §0 一句话结论

**S2a 完成**：`run_lang_path(args, root) -> int | None` 抽出 30 行，
`main` 从 **1,361 → 1,334 行**，diff **45 增 / 30 删**。
**判据三条全过**：`--lang c` 冒烟 rc=0；`sample_m` 的五类计数与 `stats` 全等；
`--help` 规范形逐字节不变（R5c）。
**未完成**：W2 等整树重跑（PID 7588）。

---

## §1 为什么 S2 不能整体切

分析段（原 L32985–L33206）里有这些提前退出：

| 位置 | 代码 | 性质 |
| --- | --- | --- |
| `root.is_dir()` 失败 | `return 1` | 前置校验 |
| `--git-diff` 空集 | `return _run_incremental_empty(...)` | 独立任务 |
| `--lang asm` 无文件 | `return 1` | 纯语言路径 |
| `--lang asm` 有文件 | `return _run_ext_only(...)` | **直接产产物** |
| `--lang c` | `return _run_c_only(...)` | **直接产产物** |
| `--lang py/js` 无文件 | `return 1` | 纯语言路径 |
| `--lang py/js` 有文件 | `return _run_ext_only(...)` | **直接产产物** |

`_run_c_only` / `_run_ext_only` 是"分析 + 渲染 + 落盘"三合一，**不是纯分析**。
把它们塞进 `run_pipeline` 会让"流水线"这个概念立刻失真：流水线不该写盘。

⇒ S2 必须分两步：
- **S2a（本轮）**：纯语言分发独立成函数 —— 它们的语义恰好是"返回退出码"。
- **S2b（下一轮）**：`run_pipeline` 只包"收集 → 解析 → 建模"，返回 `PipelineResult`。

---

## §2 S2a 的做法：`return` 变返回值，缩进不变

```python
def run_lang_path(args, root):
    """纯语言模式（--lang c|py|js|asm）的分发。

    返回 None 表示「不是纯语言模式，继续主流水线」；
    返回整数表示「这条路已经走完，把它作为进程退出码」。
    """
    if args.lang in ("c", "py", "js", "asm"):
        ...
        return _run_ext_only(...)
```

`main` 里只剩三行：

```python
    _rc = run_lang_path(args, root)
    if _rc is not None:
        return _rc
```

**为什么 diff 只有 45/30**：被搬的 30 行在原位置就是 4 空格缩进（`if args.lang in (...)`），
搬进函数后仍是 4 空格 —— 又是"原地换主"，中间一行没动。

---

## §3 三条判据

| 判据 | 读数 |
| --- | --- |
| `--lang c` 冒烟 | `C 文件 1 / C 函数 2 / 调用边 0 / 未解析 1 / include 1`，启发式 3 条，rc=0 |
| `sample_m` 读数 | `files 13/13`、`edges 9/9`、`heuristics 5/5`、`unresolved 2/2`，`stats` 相等 |
| `--help` 规范形 | 与快照 **50,094 B** 一致（R5c 通过） |

**为什么 `--lang c` 冒烟是必须的**：S2a 改的正是这条路径的归属。
如果只测 MATLAB 路径，`run_lang_path` 的四个分支里三个没被走过 —— 那等于没改。

---

## §4 当前状态

```
main                 1,334 行（原 2,020）
cli_entry             663 行
run_lang_path          41 行
check_help_contract  OK（R5c 逐字节）
check_all            23/24（W2 等 PID 7588）
```

---

## §5 下一步：S2b

`run_pipeline(args, root) -> PipelineResult`，只包 L33031（`files = []`）到 L33221（`checks_for_sarif`）。

`PipelineResult` 先定，字段从既有赋值反推：

```
files / index / edges / stats / model / c_model / checks_for_sarif
```

**六个提前 return 里只剩两个**（`root.is_dir` 失败、`--git-diff` 空集），
它们留在 `main`，因为一个是前置校验、一个是独立任务。

判据：`--json` 的 `--fingerprint` 不变 + `--mixed` 路径仍产出 `c_model`。
