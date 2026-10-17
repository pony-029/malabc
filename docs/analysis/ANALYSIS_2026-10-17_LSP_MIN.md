# 2026-10-17 · LSP 最小版：只做三件事，判据比功能重要

> 前置已经就位：`analyzer/api.py`（可 import、0 stdout 泄漏）与
> `analyzer/index.py`（四态增量）。本轮先把「第一版到底做什么」写死，
> 避免又滑成"什么都想做一点"。

---

## §0 一句话结论

第一版只实现 **`initialize` / `didOpen` / `publishDiagnostics`** 三件事。
它不做转到定义、不做 CodeLens、不做语义高亮 —— 因为**这三件事就能验证最贵的三个风险**：

| 风险 | 判据 |
| --- | --- |
| stdout 被 `print` 污染 | 整个会话 stdout 只有 `Content-Length` 分帧的 JSON |
| 全量分析不可用（623 秒） | `didOpen` 后 1 秒内返回首帧诊断 |
| 行号不同源 | 诊断条数与行号 == `--json` 的 `heuristics` |

---

## §1 为什么是这三件，而不是"更完整的 LSP"

LSP 的能力清单有二十多项，但它们的**验证价值极不均匀**：

| 能力 | 它验证什么 | 第一版要不要 |
| --- | --- | --- |
| `initialize` | 协议握手、能力声明 | **要** |
| `didOpen` | 文档内存快照、不落盘 | **要** |
| `publishDiagnostics` | 分析结果 → 协议消息、行号同源 | **要** |
| `textDocument/definition` | 符号索引 | 否（`api` 还没暴露定义查询） |
| `textDocument/references` | 反向依赖 | 否 |
| `textDocument/hover` | 类型/复杂度 | 否 |
| `textDocument/codeAction` | 补丁生成 | 否（`--gen-apply-patch` 还没接） |
| `workspace/symbol` | 全库符号表 | 否 |

**判据**：一个能力的加入，必须让**某条已有判据变得更强**。否则它只是增加了要维护的表面。

---

## §2 三个能力的协议细节（写死，避免实现时漂移）

### 2.1 `initialize`

请求 → 响应：

```json
{"capabilities": {"textDocumentSync": 1},
 "serverInfo": {"name": "matlabc-lsp", "version": "<与 matlabc.py 同源>"}}
```

`textDocumentSync = 1` 表示 **full**（每次发全文）。不做增量同步 —— 因为
`index.py` 已经按「内容 hash」判断变化，增量同步只会多一层协议复杂度。

### 2.2 `didOpen`

- 必须**先返回**（不阻塞协议循环），再异步分析。
- 首次分析用 `analyzer.index.Index` 建表，之后只算 `changed`。
- **不落盘**：文档内容只进内存快照（`didChange` 时替换）。

### 2.3 `publishDiagnostics`

消息形态（LSP 3.17）：

```json
{"uri": "file:///.../a.m",
 "diagnostics": [{"range": {"start": {"line": 11, "character": 4},
                            "end":   {"line": 11, "character": 20}},
                  "severity": 2,
                  "code": "m_uninit",
                  "source": "matlabc",
                  "message": "..."}]}
```

**两个约定**：

1. **行号是 0-based**（LSP 规范），而 `--json` 的 `line` 是 1-based。
   转换只在 `matlabc_lsp.py` 一处做，**别处不许再减一**。
2. **`severity` 映射**写死一张表：`error=1` / `warning=2` / `info=3` / `hint=4`。
   `--json` 的 `level` 只有 `high/mid/low`，映射表放在同一处。

---

## §3 唯一的硬判据（这条能红，其余都能绿）

```
LSP 对 tests/sample_m 的全部诊断
  == `matlabc.py tests/sample_m --json` 的 heuristics 集合
```

逐条比：`(file, line-1, rule_id, level→severity)`。

**为什么它是唯一硬判据**：它同时锁死三件事 ——
① `print` 没有污染 stdout（否则 JSON 解析失败）；
② 行号没有二次偏移（否则 line 对不上）；
③ 诊断不是"另算一遍"（否则 rule_id 集合不同）。

**反向验**：把 `matlabc_lsp.py` 里的 severity 映射表改成手写副本（与
`--json` 的映射不一致），这条必须红。

---

## §4 与已有两块的关系

```
matlabc.py --json  ──(同一条分析路径)──┐
                                       ├─→ 诊断集合必须相等
matlabc_lsp.py ── analyzer/api.analyze ┘
                      │
                      └─ analyzer/index.Index（只重解析变化文件）
```

**不许出现第三条路径**：LSP 不能自己解析 `.m`。一旦自己解析，就变成第二事实源，
而本仓最贵的历史教训就是"两本账"。

---

## §5 下一步（按顺序）

1. `matlabc_lsp.py`：三件 + 一条判据（约 150 行）。
2. `api.analyze(incremental=True)` 接 `Index`：第二次调用 `changed=0` 时解析耗时 ≤ 首轮 5%。
3. VSCode 壳（`package.json` + `vscode-languageclient`）：**最后做**，因为它最便宜也最容易让人误以为"插件完成了"。
