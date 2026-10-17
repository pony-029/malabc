# malabc MATLAB LSP（VSCode 扩展）

**零 npm 依赖**：不装 `vscode-languageclient`，手写协议客户端（`lspClient.js`，约 70 行）。
符合本仓"离线、零依赖、内网可用"的设定。

## 现在能做什么

| 能力 | 来源 | 状态 |
| --- | --- | --- |
| 诊断 | `publishDiagnostics` | **`m_missing_doc`（函数缺头部描述）** |
| 转到定义 | — | **未实现**：LSP 侧没有 `textDocument/definition` |
| 查找引用 | — | **未实现**：LSP 侧没有 `textDocument/references` |

> **曾经注册过这两个 provider**，而 LSP 并不实现对应请求——服务端回
> `{"result": null}`，扩展拿到空数组，**F12 与 Shift+F12 静默失败**
> （不跳转也不报错）。现在两侧一致：扩展不注册、LSP 不支持，
> `test_extension.js` 与 `test_client.js` 各有一条**反向断言**守着。

## 明确不做的事

- **不做 hover / CodeLens / 语义高亮**：它们要的类型/复杂度还在 `model` 深处，判据比现在弱。
- **不自己解析 `.m`**：所有分析走 `matlabc_lsp.py` → `analyzer.api.analyze`。一旦自己解析，
  就是第二事实源。
- **诊断只有一类**：`--json` 的 `heuristics` 当前只含 `m_missing_doc`
  （`matlabc.py:14279` 的注释明说其余类别未并入）。**这不是缺陷，是口径一致**——
  要发更多，先改 facts 层。

## 将来要加 F12 时，先补什么

`analyze` 的 `edges` 是 `(caller, callee, ambiguous)` 三元组，**不带行号**——
所以即使实现 `references`，也只能给「哪个函数调用了它」，落点是调用者的
**定义行**，不是调用发生的那一行。要行级引用，得先让 `edges` 带 `line`。

而 `definition` 需要「光标处标识符 → 定义位置」：`analyzer.api` 已能给出
`files[].functions[]` 的 `(name, line)`，这条路是通的，**但必须先写判据**
（光标放在 `a.m:3` 的 `b` 上 → 跳到 `a.m:6`），再来注册 provider。
行级引用要等 facts 层给 `edges` 加 `line`。

## 安装与运行

1. 需要 Python 3.8+ 在 PATH（或设置 `matlabc.pythonPath`）。
2. 把本目录**软链接/复制**到 VSCode 扩展目录：

```powershell
# Windows
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.vscode\extensions\malabc.matlabc-lsp-0.1.0" -Target "E:\matlabc\malabc\vscode"
```

3. 打开一个含 `.m` 的目录，VSCode 会自动激活（`activationEvents: onLanguage:matlab`）。

## 判据（不装 VSCode 也能跑）

```powershell
# 用真实的 matlabc_lsp.py 验证 JS 客户端
$env:PYTHON="C:\Program Files\Python310\python.exe"
node vscode\test_client.js
# 期望：LSP CLIENT {"bad": 0, "good": 6}

# 验证 Python 侧
python tools\lsp_selftest.py
# 期望：LSP SELFTEST {"bad": 0, "good": 10}
```

`test_client.js` 不 `require('vscode')`，所以能在纯 Node 下跑；`extension.js` 必须
在 VSCode 宿主里跑，只做语法检查（`node --check`）。
