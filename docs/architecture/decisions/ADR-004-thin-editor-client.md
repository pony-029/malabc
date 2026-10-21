# ADR-004: 编辑器客户端保持轻薄，分析在服务端

- Status: Accepted
- Date: 2026-10-21
- Diagrams: 06-lsp, 07-ai-mcp, 13-sequence

## Context

VS Code 扩展如果自己解析 MATLAB，就要复制一套分析逻辑；
而扩展生态又要求零 npm 依赖、离线可用、启动快。

## Decision

扩展只做 LSP 客户端：`vscode/extension.js` 负责注册 provider、转发请求、800ms 超时；
真正的分析在 `matlabc_lsp.py` 服务端，复用单文件内核。
超时后客户端做本地兜底（脚本按 `%%` 分节，无分节用文件名），绝不返回空白大纲。

## Consequences

- 扩展零 npm、离线可用；服务端升级即全量生效。
- 客户端需要处理超时与降级，不能假设服务端永远在线。
- 诊断/大纲/跳转共享服务端同一份模型。

## Evidence

- `vscode/extension.js`
- `vscode/lspClient.js`
- `matlabc_lsp.py`
- `tools/lsp_selftest.py`
