# 下一代能力方案：从「能看见」到「能判断」

> 目标：**在 MATLAB 官方 IDE 做不到的地方做到极致**，而不是在它能做的地方做得更差。
> 约束：每一项都必须能用**现有数据**算出来，且官方没有等价物。

---

## §0 现状：数据已经够了，缺的是「面向决策的产出」

YALMIP 那次分析产出的 27 个顶层键里，**已经埋着三个能力的全部原料**：

| 已有数据 | 规模（YALMIP） | 目前只用来… | **本可以** |
| --- | --- | --- | --- |
| `edges` | **20225 条**（跨文件 17369） | 画图 / 数边 | **反查影响面** |
| `call_graph.ambiguous` | 每个调用的候选数 | 记在 JSON 里 | **提示「这个调用可能调错」** |
| `type_flow` / `shape_mismatch` | — | 报错 | **调用契约验证** |
| `dup_code` | **765 处** | 列出来 | **合并建议 + 影响面交叉** |
| `taint` | 133 条 | 列出来 | **追到危险入口的完整路径** |

**关键认识**：`edges` 是**有向图**，「影响面」就是它的**反向可达集**。**这个计算今天就能做，只是没人做。**

---

## §1 方向 A：影响面分析 `--impact <func>`（最高优先级）

### 1.1 官方为什么做不到

MATLAB 官方 IDE 的 F12 是**正向**的（从调用找定义）。**反向**（从定义找所有调用者）只能靠「在文件夹里搜索函数名」，而：

- 搜到的是**文本**，不是**调用关系**（注释、字符串里的同名也会命中）
- **跨文件重名**无法区分（`@sdpvar/get.m` 与 `@sdpvar/subsasgn.m` 里都有 `get`）
- **多态派发**（`@class/method.m`）搜不出来

**而 `edges` 里已经有 `caller → callee` 的确定关系，以及 `ambiguous` 的候选数。**

### 1.2 规格

```powershell
python matlabc.py <root> --impact "modules/global/compileQuadratic.m:compileQuadratic"
```

输出：

```
影响面：compileQuadratic
  直接调用者（1 层）        12 个
  间接调用者（2 层）        47 个
  间接调用者（3 层）        103 个
  可达入口（无调用者）       4 个
  涉及文件                  21 个

  交叉提示
    其中 3 个文件在 --git-diff 里改过   ⇒ 本次改动可能影响它们
    其中 2 个函数与它有 dup_code 重复   ⇒ 改一处要同步改另一处
```

### 1.3 判据（四条，全部可验证）

| # | 判据 | 为什么 |
| --- | --- | --- |
| I1 | 反向可达集**必含** `edges` 里已知的调用者（人工核对一条） | 正向数据对，反向必须自洽 |
| I2 | **层数可复现**：同一份 JSON 跑两次层数相同 | 防遍历顺序影响结果 |
| I3 | **递归/循环不得让层数无限增长**（`r→r`、`a↔b`） | 用 `tests/sample_m` 的循环测 |
| I4 | **入口集合** ⊆ 全体函数里「无 caller」的集合 | 定义一致性 |

### 1.4 成本

**约 80 行**：反向邻接表 + BFS 分层 + 与 `dup_code`/`git-diff` 交叉。
**没有新分析**，只消费已有数据 ⇒ 风险极低。

---

## §2 方向 B：AI 上下文 `--ai-context <func>`（最具突破性）

### 2.1 官方为什么做不到

**MATLAB 官方没有任何「把代码理解压缩成 LLM 可吃形式」的能力。**

真实痛点很具体：

- 27 MB JSON **塞不进任何上下文窗口**
- 但「解释 `compileQuadratic` 做什么」**只需要它自己 + 12 个调用者 + 3 个被调用者**
- **压缩比可达 1000:1**

### 2.2 规格

```powershell
python matlabc.py <root> --ai-context "modules/global/compileQuadratic.m:compileQuadratic"
```

输出（约 4 KB）：

```markdown
# compileQuadratic

签名：function [model] = compileQuadratic(model, ...)
描述：<头部注释>
复杂度：7

## 它调用谁（3 个，直接）
- ... — <一行描述>

## 谁调用它（12 个，直接）
- ... — <一行描述>

## 它身上的诊断（2 条）
- m_missing_doc 第 1 行
- dup_code 与 addInequality 相似度 0.86

## 改动它要注意
- 影响 21 个文件 / 103 个间接调用者
- 其中 2 个在本次 --git-diff 里
```

### 2.3 为什么这是突破性的

| 对比 | 现在 | 之后 |
| --- | --- | --- |
| 把项目交给 AI 理解 | **27 MB，不可行** | **4 KB，一次对话放得下** |
| AI 回答「改这个安全吗」 | 只能读正文，**看不到调用关系** | **影响面 + 重复 + 诊断全在里面** |
| 跨文件推理 | 人工喂多个文件 | **一次给全** |

**它把「结构化分析」变成「AI 的输入」** —— 闭源 GUI **结构上做不到**。

### 2.4 判据

| # | 判据 |
| --- | --- |
| A1 | 输出体积 **< 8 KB**（对 YALMIP 实测） |
| A2 | 必含该函数**所有直接调用者**（与 `edges` 核对） |
| A3 | 必含 `dup_code` 里与它相关的条目 |
| A4 | **不得出现** `edges`/诊断里没有的函数名（防编造） |

**A4 最关键：它只能转述已有数据，不能“推理”出不存在的调用关系。**

---

## §3 方向 C：跨语言调用图（MEX 边界）

### 3.1 官方为什么做不到

**官方只认 MATLAB。** `mexFunction` 在 C 里，官方 IDE 不知道 MATLAB 侧谁在调它。
而真实项目的边界就在这里：MATLAB → MEX(C) → BLAS，MATLAB → Python。

### 3.2 规格

`--mixed` 已能同时分析 MATLAB 与 C，**缺的是把它们连起来**：

```
C 侧：mexFunction(nlhs, plhs, nrhs, prhs)
MATLAB 侧：foo(...)  调用
⇒ 生成一条 cross_language 边：matlab:foo -> c:foo.c:mexFunction
```

### 3.3 判据

| # | 判据 |
| --- | --- |
| X1 | `--mixed` 的 `edges` 里出现带 `lang` 字段的跨语言边 |
| X2 | 该边的 callee **必须真的在 C 侧存在** |
| X3 | **没有跨语言边的项目必须返回 0，而不是报错** |

### 3.4 成本

**约 200 行**（C 侧识别 `mexFunction` 签名 + MATLAB 侧按文件名匹配）。
**这是三个方向里唯一有真风险的**（文件名匹配可能误连），所以要 X3 那条兜底。

---

## §4 方向 D：静态性能热点（次要）

**官方 Profiler 是运行时**（要跑起来、要数据）。**静态版**：

```
从 call_graph + 每个函数的循环嵌套深度 + 被调用次数
⇒ 预测「哪个函数最可能是热点」
```

**判据**：对已知热点（如 `_detect_dup_code`）必须在 Top 10 里。

**成本约 60 行**，但**准确率无法严格验证**（没有 ground truth），**优先级最低**。

---

## §5 优先级与路线

| 序 | 方向 | 收益 | 成本 | 风险 | 官方有没有 |
| --- | --- | --- | --- | --- | --- |
| **1** | **A 影响面** | ⭐⭐⭐ | 80 行 | 低 | ❌ |
| **2** | **B AI 上下文** | ⭐⭐⭐ | 120 行 | 低 | ❌ |
| 3 | C 跨语言边 | ⭐⭐ | 200 行 | **中** | ❌ |
| 4 | D 静态热点 | ⭐ | 60 行 | 中 | 部分（运行时） |

**推荐顺序：A → B → C → D**。

**A 和 B 共用同一套「邻接表 + 压缩」逻辑**，一起做只花 150 行。

---

## §6 第一步的精确规格（可直接实现）

```python
def _impact(result, target, depth=3):
    """target 形如 "a.m:b"。返回反向可达集的分层结果。"""
    rev = {}                       # callee -> [caller...]
    for e in (result.edges or []):
        rev.setdefault(e["callee"], []).append(e["caller"])

    seen = {target}
    layer = [target]
    levels = []
    for _ in range(depth):
        nxt = []
        for node in layer:
            for c in rev.get(node, []):
                if c not in seen:      # ← I3：seen 同时防自环与重复
                    seen.add(c)
                    nxt.append(c)
        if not nxt:
            break
        levels.append(nxt)
        layer = nxt
    return levels
```

**`seen` 那一个集合同时满足 I1（不漏）、I2（顺序无关）、I3（防环）** —— 三条判据一个实现。

**`_ai_context` 直接复用 `levels` + `files` 的 `header`/`complexity` + 诊断索引**。

---

## §7 一句话

**官方 IDE 回答「这个函数是什么」；这三个方向回答「改它会发生什么」「AI 能不能理解它」「它跨语言连到哪」。**

**前两个今天就能做，且只花 150 行 —— 因为它们要的数据（`edges` / `type_flow` / `dup_code`）已经在 27 MB 的 JSON 里了。**
