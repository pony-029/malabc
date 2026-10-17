# malabc MATLAB LSP（VSCode 扩展）

**零 npm 依赖**：不装 `vscode-languageclient`，手写协议客户端（`lspClient.js`，约 70 行）。
符合本仓"离线、零依赖、内网可用"的设定。

## 现在能做什么

| 能力 | 来源 | 状态 |
| --- | --- | --- |
| 诊断 | `publishDiagnostics` | **`m_missing_doc`（函数缺头部描述）** |
| 转到定义 | `textDocument/definition` | **同文件 + 跨文件**（判据 7 条） |
| 查找引用 | `textDocument/references` | **函数级**（不是行级，见下；判据 6 条） |

> 这两个 provider 曾经在扩展侧注册、LSP 侧却没实现——服务端回
> `{"result": null}`，扩展拿到空数组，**F12 与 Shift+F12 静默失败**
> （不跳转也不报错）。现在的顺序反过来了：**先在 LSP 侧实现并写判据，
> 判据变绿后再注册 provider**。`test_extension.js` 与 `test_client.js`
> 里的断言也跟着翻面。

## 明确不做的事

- **不做 hover / CodeLens / 语义高亮**：它们要的类型/复杂度还在 `model` 深处，判据比现在弱。
- **不自己解析 `.m`**：所有分析走 `matlabc_lsp.py` → `analyzer.api.analyze`。一旦自己解析，
  就是第二事实源。
- **诊断只有一类**：`--json` 的 `heuristics` 当前只含 `m_missing_doc`
  （`matlabc.py:14279` 的注释明说其余类别未并入）。**这不是缺陷，是口径一致**——
  要发更多，先改 facts 层。

## 引用为什么是"函数级"

`analyze` 的 `edges` 是 `(caller, callee, ambiguous)` 三元组，**不带行号**。
所以 `references` 给的是「哪个函数调用了它」，落点是调用者的**定义行**，
不是调用发生的那一行。**要行级引用，得先让 `edges` 带 `line`**——那会改
`--json` 里 `edges` 的结构，属于 `matlabc.py` 的改动，要付一次整树重跑。
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
