# 下一代能力（二）：从「能用」到「比官方顺手」

> 前提：0.3.3 已经能跳转、悬停、大纲、结构体成员、保存即刷新、后台预热。
> 本方案只做**官方 IDE 结构上做不到**的事，且**优先做用户每天都碰的**。

---

## §0 现在的短板（按用户可感知排序）

| # | 短板 | 用户的感受 |
| --- | --- | --- |
| 1 | **首次 35 秒** | 打开大仓库要等 |
| 2 | **重启就重来** | 每次开 VSCode 都等 |
| 3 | **保存后全量重算** | 改一行要等 35 秒 |
| 4 | **不知道哪里重要** | 1665 个文件里，哪个是热点？ |
| 5 | **注释之外没有语义** | 变量/全局/字段/内置都是同一个颜色 |

**四条待办全部有现成数据**：`edges`、`functions`、`builtin_calls`、`field_access`。

---

## §1 分层预热（把 35 秒拆成 10 + 25）

### 1.1 为什么要拆

`analyze(root)` 里两段代价差 3 倍：

| 数据 | 谁需要 | YALMIP 耗时 |
| --- | --- | --- |
| `files` / `functions` / `edges` | **F12 / 引用 / 悬停 / 大纲** | 约 10s |
| `facts`（`_collect_checks`） | 只有 diagnostics | 另 25s |

**F12 在等一份它根本不需要的数据。**

### 1.2 规格

```
initialize
  ├─ ① 结构层：analyze(no_checks=True) → _STATE["result"] 就绪
  │     ⇒ F12 / references / hover / symbols 全部可用
  └─ ② 诊断层：analyze() → _STATE["payload"] 就绪
        ⇒ publishDiagnostics 补发
```

**`_definition` 等 ①（不是 ②）**，`_diagnostics_for` 等 ②。

### 1.3 判据

| # | 判据 |
| --- | --- |
| S1 | `initialize` 后 12 秒内 `documentSymbol` 能返回（结构层就绪） |
| S2 | 此时 `publishDiagnostics` **还没发**（诊断层未完） |
| S3 | 再过 30 秒，`publishDiagnostics` 到达且条数 > 0 |
| S4 | 两层都完成后，行为与现在**完全一致**（19 条不退化） |

---

## §2 磁盘缓存（第二次 0.2 秒）

### 2.1 规格

```
<root>/.matlabc_lsp_cache.json
{"v": 1, "stamp": <所有 .m 的最大 mtime>, "files": [...], "edges": [...], "payload": {...}}
```

**校验**：`stamp` 不一致 → 作废重算。

### 2.2 三个必须

| 必须 | 为什么 |
| --- | --- |
| **`{"v": 1}`** | 代码改结构后，旧缓存会喂出**错误的形状**（14 次判据错的来源） |
| **进 `.gitignore`** | 否则一开项目 `git status` 就脏 |
| **`stamp` 用 `max(mtime)` 不是文件数** | 文件数不变但内容改了是最常见的情况 |

### 2.3 判据

| # | 判据 |
| --- | --- |
| C1 | 第一次跑：无缓存文件，预热后**生成**它 |
| C2 | 第二次跑（不改文件）：`initialize` 后 **< 1 秒**可用 |
| C3 | 改一个 `.m` 再跑：`stamp` 变 → **重新分析**（不能误用旧缓存） |
| C4 | 缓存写坏（截断 JSON）：**忽略并重算**，不崩 |
| C5 | `{"v": 99}`：忽略并重算 |

---

## §3 增量重算（保存从 35 秒到 0.3 秒）

### 3.1 为什么能做

`didSave` 现在是**全量** `_run_json(root)`。而 `edges` 是**有向图**：

```
改动的文件 → 反向可达集（谁依赖它）→ 只重算这些
```

实测（YALMIP）：改 `callPOP.m`，反向可达 47 个函数 / 12 个文件，
**占比 0.7%** —— 重算它们约 **0.3 秒**。

### 3.2 规格

```python
changed = {rel}                       # 保存的文件
affected = reverse_reachable(changed)  # 用 edges 反查
payload = _run_json(root, only=affected | changed)
```

**`analyze` 目前不支持 `only=`** —— 这是唯一需要动 `analyzer/api.py` 的地方：
传一个 `files_filter`，`run_pipeline` 只解析这些文件，其余复用上次的 `MatlabFile`。

### 3.3 风险与判据

**风险**：增量结果与全量不一致（**最危险的一类 bug**）。

| # | 判据 |
| --- | --- |
| I1 | 改一个文件后，增量结果的 `edges` **⊆** 全量结果的 `edges` |
| I2 | 增量跑 N 次再全量跑一次，两者**逐字节相同**（规范化后） |
| I3 | 新增文件（不在缓存里）：必须触发**全量**，不是增量 |
| I4 | 删文件：反向可达集里的引用必须消失 |

**I2 是关键**：它把"增量是否正确"变成一个**可自动验证**的命题。

---

## §4 CodeLens：让「哪里重要」浮在函数头上

### 4.1 官方做不到

MATLAB 的 CodeLens 只在**有 git 信息**时显示"作者/提交"。**它不显示调用关系**。

### 4.2 规格

```matlab
function [output] = callPOP(interfacedata)
                                                   ← 上方显示：
   ↑ 3 个调用者 · ↓ 12 个被调用 · 复杂度 11
```

**点击** → 执行 `--impact`（或直接打开 `--ai-context` 的输出）。

**数据全部现成**：`edges` + `complexity`。

### 4.3 判据

| # | 判据 |
| --- | --- |
| CL1 | 每个 `function` 上方**恰好一条** CodeLens |
| CL2 | 数字与 `--impact` / `--tree` 的读数**一致** |
| CL3 | 没有调用者的函数显示 **"0 个调用者"**（不是不显示） |

---

## §5 语义高亮（Semantic Tokens）

### 5.1 官方做不到

官方的 TextMate 语法是**正则**，它无法区分：

```matlab
x = 1;          % 局部变量
global G;       % 全局变量
s.field = 1;    % 结构体字段
sin(x);         % 内置函数
myfunc(x);      % 用户函数
```

**这五类在官方高亮里是同一个颜色。**

### 5.2 规格

`textDocument/semanticTokens/full` 返回 `(line, char, len, type, modifiers)`：

| 类型 | 来源 |
| --- | --- |
| `variable`（局部） | `functions[].locals` |
| `variable.global` | `files[].globals` |
| `property`（字段） | `field_access` |
| `function.builtin` | `builtin_calls` |
| `function.user` | `files[].functions` |

### 5.3 判据

| # | 判据 |
| --- | --- |
| T1 | `x = 1` 的 `x` 标记为 `variable` |
| T2 | `sin` 标记为 `function.builtin`，`myfunc` 标记为 `function.user` |
| T3 | `s.field` 的 `field` 标记为 `property` |
| T4 | **没有 types 信息的标识符不标记**（宁可不标，不可标错） |

---

## §6 优先级

| 序 | 功能 | 收益 | 成本 | 风险 | 官方 |
| --- | --- | --- | --- | --- | --- |
| **1** | **分层预热** | ⭐⭐⭐ 10s 可用 | 60 行 | 低 | ❌ |
| **2** | **磁盘缓存** | ⭐⭐⭐ 0.2s 重开 | 120 行 | 低 | ❌ |
| **3** | **CodeLens** | ⭐⭐⭐ 一眼看权重 | 50 行 | 低 | ❌ |
| 4 | **语义高亮** | ⭐⭐ 五类区分 | 150 行 | 中 | ❌ |
| 5 | 增量重算 | ⭐⭐ 保存 0.3s | 200 行 | **高** | ❌ |

**1 → 2 → 3 是连续的三轮，都是低风险**。

**5（增量重算）放最后**：它收益高但**一旦算错就是"结果对不上"**，必须先把 I2 那条判据做出来。

---

## §7 一句话

**官方 IDE 的强项是"实时反馈"（输入即分析），弱项是"全局视野"（不知道整个项目的结构）。**

**1、2 让它追上实时性；3、4、5 把"全局视野"塞进编辑器。**

**而这三件事需要的 `edges` / `complexity` / `builtin_calls` / `field_access`，在 27 MB 的 JSON 里早就有了。**
