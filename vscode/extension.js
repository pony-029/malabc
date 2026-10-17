// extension.js —— VSCode 扩展入口。**薄壳**：只做协议 ↔ VSCode 对象的翻译。
//
// 分析全部在 `matlabc_lsp.py` 里（Python），这里不允许出现任何"再算一遍"的逻辑
// —— 否则就是第二事实源，而本仓最贵的历史教训就是"两本账"。

'use strict';

const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { LspClient } = require('./lspClient');

let client = null;
let collection = null;
let out = null;

// **同时写文件**：`%TEMP%\matlabc-ext.log`。
// 只看「输出」面板不够 —— 用户找不到那个频道时，日志就等于不存在。
// 写文件让排查者可以直接读，不需要用户做任何操作。
const _fs = require('fs');
const _os = require('os');
const LOGFILE = path.join(_os.tmpdir(), 'matlabc-ext.log');

function log(msg) {
  const line = '[' + new Date().toTimeString().slice(0, 8) + '] ' + msg;
  try { _fs.appendFileSync(LOGFILE, line + '\n'); } catch (e) { /* ignore */ }
  try {
    if (!out) out = vscode.window.createOutputChannel('malabc');
    out.appendLine(line);
  } catch (e) { /* 日志本身不能把扩展带崩 */ }
}

function severityOf(n) {
  // LSP: 1=Error 2=Warning 3=Information 4=Hint
  switch (n) {
    case 1: return vscode.DiagnosticSeverity.Error;
    case 2: return vscode.DiagnosticSeverity.Warning;
    case 3: return vscode.DiagnosticSeverity.Information;
    default: return vscode.DiagnosticSeverity.Hint;
  }
}

function toRange(r) {
  return new vscode.Range(r.start.line, r.start.character,
                          r.end.line, r.end.character);
}

function toLocation(loc) {
  return new vscode.Location(vscode.Uri.parse(loc.uri), toRange(loc.range));
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
  log('activate() 进入，扩展已加载');
  const cfg = vscode.workspace.getConfiguration('matlabc');
  if (!cfg.get('enabled', true)) {
    log('matlabc.enabled = false，跳过');
    return;
  }

  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    log('没有打开任何文件夹 —— 扩展不启动。请「文件 → 打开文件夹」');
    return;
  }

  const root = folders[0].uri.fsPath;

  // **第一候选是扩展自带的**（R204 起 .vsix 里打包了 matlabc_lsp.py +
  // matlabc.py + analyzer/）。用户装的扩展自带分析器，**零配置**。
  // 之后才是工作区里的那三种位置（开发者在本仓里调代码时用得上）。
  //
  // 实测教训：用户打开 C:\temp\yalmip 时，前三个工作区候选都不命中，
  // 扩展弹「找不到 matlabc_lsp.py」——而那条错误只有开发者看得懂。
  const bundled = path.join(context.extensionPath, 'matlabc_lsp.py');
  const candidates = [
    bundled,
    path.join(root, 'matlabc_lsp.py'),
    path.join(root, 'malabc', 'matlabc_lsp.py'),
    path.join(root, '..', 'matlabc_lsp.py'),
  ];
  let lspPath = cfg.get('lspPath');
  if (!lspPath) {
    for (const c of candidates) {
      if (fs.existsSync(c)) { lspPath = c; break; }
    }
    if (!lspPath) lspPath = candidates[0];
  }
  const python = cfg.get('pythonPath', 'python');

  log('工作区   : ' + root);
  log('python   : ' + python);
  log('lspPath  : ' + lspPath);

  if (!fs.existsSync(lspPath)) {
    const m = 'malabc: 找不到 matlabc_lsp.py。已试过：' +
              candidates.join(' / ') +
              '。若都用不了，请在设置里填 matlabc.lspPath。';
    log(m);
    vscode.window.showErrorMessage(m);
    return;
  }

  client = new LspClient({
    python: python,
    script: lspPath,
    cwd: path.dirname(lspPath),
    // 说明语言：`both`（中文在前 + 英文）/ `zh` / `en`。
    // 通过环境变量传，因为 LSP 是子进程，读不到 VSCode 的设置。
    env: Object.assign({}, process.env, {
      MATLABC_DOC_LANG: cfg.get('docLang', 'both'),
    }),
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

  client.initialize(root).then(() => {
    log('initialize 成功');
  }).catch((e) => {
    log('initialize 失败：' + e.message + '   stderr尾部=' +
        (client.stderrTail || []).join('').slice(-400));
    vscode.window.showErrorMessage('malabc LSP 启动失败：' + e.message);
  });

  // 打开时推一次全文；已打开的文档补推一遍
  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((d) => {
      log('文档打开 ' + path.basename(d.uri.fsPath) +
          '  languageId=' + d.languageId);
      sendOpen(d);
    })
  );
  vscode.workspace.textDocuments.forEach((d) => {
    if (d.languageId === 'matlab') log('已打开文档补推 ' + path.basename(d.uri.fsPath));
    sendOpen(d);
  });

  // 两个 provider 都已由 LSP 实现，判据各自通过：
  //   definition：`a.m:3` 的 `b` → `a.m:6`、`a.m:13` 的 `d` → `d.m:1`、注释 → `[]`
  //   references：`a.m:6` 的 `b` → 调用者 `a` 在 `a.m:1`，含定义 2 个、注释 → `[]`
  // 「注册一个 provider 就是承诺一个能力」——两条现在都兑现了。

  context.subscriptions.push(
    vscode.languages.registerDefinitionProvider({ language: 'matlab' }, {
      provideDefinition: async (doc, pos) => {
        log('F12 请求 ' + path.basename(doc.uri.fsPath) + ' ' +
            (pos.line + 1) + ':' + pos.character);
        try {
          const r = await client.request('textDocument/definition', {
            textDocument: { uri: doc.uri.toString() },
            position: { line: pos.line, character: pos.character },
          });
          const arr = r.result || [];
          log('F12 返回 ' + arr.length + ' 个位置 ' +
              JSON.stringify(arr).slice(0, 240));
          return arr.map(toLocation);
        } catch (e) {
          // **必须 catch**：R205 之前这里没有，超时的 Promise rejection
          // 会一直往上抛，VSCode 只显示「未找到定义」，日志里连「F12 返回」
          // 都没有 —— 用户看到的就是「点了什么反应都没有」。
          log('F12 失败：' + (e && e.message));
          vscode.window.setStatusBarMessage(
            'malabc: 跳转失败（' + (e && e.message) + '）', 6000);
          return [];
        }
      },
    })
  );

  context.subscriptions.push(
    vscode.languages.registerReferenceProvider({ language: 'matlab' }, {
      provideReferences: async (doc, pos, ctx) => {
        try {
          const r = await client.request('textDocument/references', {
            textDocument: { uri: doc.uri.toString() },
            position: { line: pos.line, character: pos.character },
            context: { includeDeclaration: ctx.includeDeclaration },
          });
          return (r.result || []).map(toLocation);
        } catch (e) {
          log('Shift+F12 失败：' + (e && e.message));
          return [];
        }
      },
    })
  );

  context.subscriptions.push(
    vscode.languages.registerHoverProvider({ language: 'matlab' }, {
      provideHover: async (doc, pos) => {
        try {
          const r = await client.request('textDocument/hover', {
            textDocument: { uri: doc.uri.toString() },
            position: { line: pos.line, character: pos.character },
          });
          const c = r.result && r.result.contents;
          if (!c || !c.value) return undefined;
          const md = new vscode.MarkdownString(c.value);
          return new vscode.Hover(md);
        } catch (e) {
          log('hover 失败：' + (e && e.message));
          return undefined;
        }
      },
    })
  );

  // ---- CodeLens：`↑3 调用者 · ↓12 被调用 · 复杂度 11`（R215）--------
  // 官方 CodeLens 只放 git 作者，**不显示调用关系**。这三组数字全在
  // `edges` 里，由 LSP 侧 `_code_lens` 直接给。
  context.subscriptions.push(
    vscode.languages.registerCodeLensProvider({ language: 'matlab' }, {
      provideCodeLenses: async (doc) => {
        try {
          const r = await client.request('textDocument/codeLens', {
            textDocument: { uri: doc.uri.toString() },
          });
          return (r.result || []).map((l) => {
            const d = l.data || {};
            return new vscode.CodeLens(toRange(l.range), {
              title: '↑' + (d.callers || 0) + ' 调用者 · ↓' +
                     (d.callees || 0) + ' 被调用 · 复杂度 ' + (d.complexity || 0),
              command: 'malabc.showImpact',
              arguments: [d.name, doc.uri.toString()],
            });
          });
        } catch (e) {
          log('codeLens 失败：' + (e && e.message));
          return [];
        }
      },
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('malabc.showImpact', async (name, uriStr) => {
      // 点击 CodeLens 时用 `--impact` 的 LSP 版（当前先给可操作提示：
      // 真正的影响面面板留给下一轮，避免这一轮引入未验证的协议方法）。
      out.show();
      log('CodeLens 点击：' + name);
      vscode.window.showInformationMessage(
        'malabc: ' + name + ' —— 用 Shift+F12 查看所有调用者', '好');
    })
  );

  context.subscriptions.push(
    vscode.languages.registerDocumentSymbolProvider({ language: 'matlab' }, {
      provideDocumentSymbols: async (doc) => {
        try {
          const r = await client.request('textDocument/documentSymbol', {
            textDocument: { uri: doc.uri.toString() },
          });
          return (r.result || []).map((s) => {
            const kind = s.kind === 12
              ? vscode.SymbolKind.Function
              : vscode.SymbolKind.Class;
            const range = toRange(s.range);
            const sel = toRange(s.selectionRange);
            return new vscode.DocumentSymbol(s.name, '', kind, range, sel);
          });
        } catch (e) {
          log('大纲失败：' + (e && e.message));
          return [];
        }
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
