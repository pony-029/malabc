// extension.js —— VSCode 扩展入口。**薄壳**：只做协议 ↔ VSCode 对象的翻译。
//
// 分析全部在 `matlabc_lsp.py` 里（Python），这里不允许出现任何"再算一遍"的逻辑
// —— 否则就是第二事实源，而本仓最贵的历史教训就是"两本账"。

'use strict';

const path = require('path');
const vscode = require('vscode');
const { LspClient } = require('./lspClient');

let client = null;
let collection = null;

function severityOf(n) {
  // LSP: 1=Error 2=Warning 3=Information 4=Hint
  switch (n) {
    case 1: return vscode.DiagnosticSeverity.Error;
    case 2: return vscode.DiagnosticSeverity.Warning;
    case 3: return vscode.DiagnosticSeverity.Information;
    default: return vscode.DiagnosticSeverity.Hint;
  }
}

function toLocation(loc) {
  const uri = vscode.Uri.parse(loc.uri);
  const r = new vscode.Range(loc.range.start.line, loc.range.start.character,
                             loc.range.end.line, loc.range.end.character);
  return new vscode.Location(uri, r);
}

function sendOpen(doc) {
  if (!client) return;
  if (doc.languageId !== 'matlab') return;
  client.notify('textDocument/didOpen', {
    textDocument: {
      uri: doc.uri.toString(),
      languageId: doc.languageId,
      version: doc.version,
      text: doc.getText(),
    },
  });
}

function activate(context) {
  const cfg = vscode.workspace.getConfiguration('matlabc');
  if (!cfg.get('enabled', true)) return;

  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) return;

  const root = folders[0].uri.fsPath;
  const lspPath = cfg.get('lspPath') || path.join(root, '..', 'matlabc_lsp.py');
  const python = cfg.get('pythonPath', 'python');

  client = new LspClient({
    python: python,
    script: lspPath,
    cwd: path.dirname(lspPath),
  });

  collection = vscode.languages.createDiagnosticCollection('matlabc');

  client.onNotification((msg) => {
    if (msg.method !== 'textDocument/publishDiagnostics') return;
    const params = msg.params || {};
    const uri = vscode.Uri.parse(params.uri);
    const items = (params.diagnostics || []).map((d) => {
      const r = new vscode.Range(d.range.start.line, d.range.start.character,
                                 d.range.end.line, d.range.end.character);
      const item = new vscode.Diagnostic(r, d.message, severityOf(d.severity));
      item.code = d.code;
      item.source = d.source || 'matlabc';
      return item;
    });
    collection.set(uri, items);
  });

  client.initialize(root).catch((e) => {
    vscode.window.showErrorMessage('malabc LSP 启动失败：' + e.message);
  });

  // 打开时推一次全文；已打开的文档补推一遍
  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument(sendOpen)
  );
  vscode.workspace.textDocuments.forEach(sendOpen);

  // **只注册 definition**。`matlabc_lsp.py` 已实现 `textDocument/definition`，
  // 判据是 `a.m:3` 的 `b` → `a.m:6`、`a.m:13` 的 `d` → `d.m:1`、注释上 → `[]`。
  //
  // **不注册 referenceProvider**：LSP 侧没有 `textDocument/references`，
  // 注册了会让 Shift+F12 静默失败（服务端回 null，扩展映射成空数组）。
  // 「注册一个 provider 就是承诺一个能力」——没实现就别注册。

  context.subscriptions.push(
    vscode.languages.registerDefinitionProvider({ language: 'matlab' }, {
      provideDefinition: async (doc, pos) => {
        const r = await client.request('textDocument/definition', {
          textDocument: { uri: doc.uri.toString() },
          position: { line: pos.line, character: pos.character },
        });
        return (r.result || []).map(toLocation);
      },
    })
  );

  context.subscriptions.push(collection);
}

function deactivate() {
  if (client) {
    client.dispose();
    client = null;
  }
  if (collection) {
    collection.dispose();
    collection = null;
  }
}

module.exports = { activate, deactivate };
