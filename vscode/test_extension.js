// test_extension.js —— 用**模拟的 vscode 宿主**验证 activate() 真的注册了能力。
//
//   node vscode/test_extension.js
//
// 它覆盖 `node --check` 覆盖不到的东西：activate 会不会抛、有没有注册
// definitionProvider / referenceProvider、deactivate 会不会崩。
//
// 明确不覆盖：VSCode 是否真的激活扩展、波浪线是否真的画出来 —— 那些要真宿主。

'use strict';

const path = require('path');
const Module = require('module');

const ROOT = path.resolve(__dirname, '..');
const CORPUS = path.join(ROOT, 'tests', 'sample_m');

let bad = 0;
let good = 0;

function chk(cond, msg) {
  if (cond) {
    good += 1;
  } else {
    bad += 1;
    console.log('  [FAIL] ' + msg);
  }
}

const registered = [];
const disposed = [];

// 兜底桩：未显式实现的 vscode API（枚举 / 新注册函数 / 未来新增）都不该让
// activate 抛 TypeError。真实宿主里这些永远存在，mock 只需「存在且不炸」。
function _permissive(name) {
  const target = function () { return _permissive(name + '()'); };
  return new Proxy(target, {
    get(t, prop) {
      if (prop === 'dispose') return () => {};
      // `.then` 必须存在（有些代码链式 .then），但别让 await 误判成真 Promise。
      if (prop === 'then') return () => _permissive(name + '.then');
      if (prop === Symbol.toPrimitive) return () => 0;
      if (prop === 'toString') return () => name;
      return _permissive(name + '.' + String(prop));
    },
    construct() { return _permissive(name + '{}'); },
    apply() { return _permissive(name + '()'); },
  });
}

const _base = {
  workspace: {
    workspaceFolders: [{ uri: { fsPath: CORPUS } }],
    textDocuments: [],
    getConfiguration: () => ({ get: (k, d) => d, update: () => Promise.resolve() }),
    onDidOpenTextDocument: () => ({ dispose: () => disposed.push('onDidOpen') }),
    onDidSaveTextDocument: () => ({ dispose: () => {} }),
    onDidChangeTextDocument: () => ({ dispose: () => {} }),
    onDidChangeConfiguration: () => ({ dispose: () => {} }),
    findFiles: () => Promise.resolve([]),
    openTextDocument: () => Promise.resolve({ getText: () => '' }),
  },
  languages: {
    createDiagnosticCollection: () => ({
      set: () => {},
      dispose: () => disposed.push('collection'),
    }),
    registerDefinitionProvider: () => {
      registered.push('definition');
      return { dispose: () => disposed.push('definition') };
    },
    registerReferenceProvider: () => {
      registered.push('references');
      return { dispose: () => disposed.push('references') };
    },
    registerHoverProvider: () => {
      registered.push('hover');
      return { dispose: () => disposed.push('hover') };
    },
    registerDocumentSymbolProvider: () => {
      registered.push('symbol');
      return { dispose: () => disposed.push('symbol') };
    },
    registerCodeLensProvider: () => ({ dispose: () => disposed.push('codeLens') }),
    registerDocumentHighlightProvider: () => ({ dispose: () => disposed.push('highlight') }),
    registerDocumentSemanticTokensProvider: () => ({ dispose: () => disposed.push('tokens') }),
  },
  commands: {
    registerCommand: (name) => {
      registered.push('cmd:' + name);
      return { dispose: () => {} };
    },
    executeCommand: () => Promise.resolve(),
  },
  env: {
    clipboard: { writeText: () => Promise.resolve() },
    openExternal: () => Promise.resolve(),
  },
  Uri: {
    parse: (s) => ({ toString: () => s, fsPath: s, scheme: 'file' }),
    file: (s) => ({ toString: () => 'file:///' + s, fsPath: s, scheme: 'file' }),
  },
  Range: class {
    constructor(sl, sc, el, ec) {
      this.start = { line: sl, character: sc };
      this.end = { line: el, character: ec };
    }
    union(o) {
      return new this.constructor(this.start.line, this.start.character,
                                 o.end.line, o.end.character);
    }
    isBefore(o) {
      return this.end.line < o.start.line ||
             (this.end.line === o.start.line && this.end.character < o.start.character);
    }
    isAfter(o) {
      return this.start.line > o.end.line ||
             (this.start.line === o.end.line && this.start.character > o.end.character);
    }
    contains(o) {
      return !this.isBefore(o) && !this.isAfter(o);
    }
  },
  Location: class {
    constructor(uri, range) { this.uri = uri; this.range = range; }
  },
  Diagnostic: class {
    constructor(range, message, severity) {
      this.range = range;
      this.message = message;
      this.severity = severity;
    }
  },
  MarkdownString: class {
    constructor(v) { this.value = v; }
  },
  Hover: class {
    constructor(c) { this.contents = c; }
  },
  SymbolKind: { File: 0, Module: 2, Class: 5, Function: 12, Variable: 13 },
  DocumentSymbol: class {
    constructor(name, detail, kind, range, selectionRange) {
      this.name = name;
      this.detail = detail;
      this.kind = kind;
      this.range = range;
      this.selectionRange = selectionRange;
    }
  },
  DiagnosticSeverity: { Error: 0, Warning: 1, Information: 2, Hint: 3 },
  ViewColumn: { One: 1, Two: 2, Three: 3, Beside: -2, Active: -1 },
  ProgressLocation: { SourceControl: 1, Window: 10, Notification: 15 },
  StatusBarAlignment: { Left: 1, Right: 2 },
  TreeItemCollapsibleState: { None: 0, Collapsed: 1, Expanded: 2 },
  TextEditorRevealType: { InCenter: 1 },
  ConfigurationTarget: { Global: 1, Workspace: 2 },
  DocumentHighlightKind: { Text: 1 },
  EventEmitter: class {
    constructor() { this.event = () => ({ dispose: () => {} }); }
    fire() {}
    dispose() {}
  },
  ThemeIcon: class { constructor(id) { this.id = id; } },
  TreeItem: class {
    constructor(label, state) { this.label = label; this.collapsibleState = state; }
  },
  CodeLens: class { constructor(range) { this.range = range; } },
  Position: class { constructor(line, character) { this.line = line; this.character = character; } },
  Selection: class {
    constructor(sl, sc, el, ec) {
      this.start = { line: sl, character: sc };
      this.end = { line: el, character: ec };
      this.anchor = this.start;
      this.active = this.end;
    }
  },
  SemanticTokens: class { constructor(data) { this.data = data; } },
  SemanticTokensLegend: class {
    constructor(types, modifiers) { this.tokenTypes = types; this.tokenModifiers = modifiers; }
  },
  DocumentHighlight: class { constructor(range, kind) { this.range = range; this.kind = kind; } },
  window: {
    activeTextEditor: undefined,
    showErrorMessage: () => Promise.resolve(undefined),
    showWarningMessage: () => Promise.resolve(undefined),
    showInformationMessage: () => Promise.resolve(undefined),
    showQuickPick: () => Promise.resolve(undefined),
    showInputBox: () => Promise.resolve(undefined),
    showOpenDialog: () => Promise.resolve(undefined),
    showSaveDialog: () => Promise.resolve(undefined),
    showTextDocument: () => Promise.resolve(undefined),
    withProgress: (opts, fn) => Promise.resolve(typeof fn === 'function' ? fn() : undefined),
    createOutputChannel: () => ({ appendLine() {}, append() {}, show() {}, dispose() {} }),
    createStatusBarItem: () => ({
      show() {}, hide() {}, dispose() {}, text: '', tooltip: '', command: '',
    }),
    createTreeView: () => ({
      dispose() {}, reveal() {}, message: '',
      onDidChangeSelection: () => ({ dispose: () => {} }),
      onDidChangeVisibility: () => ({ dispose: () => {} }),
    }),
    createWebviewPanel: () => ({
      webview: {
        html: '', cspSource: '',
        asWebviewUri: (u) => u,
        onDidReceiveMessage: () => ({ dispose: () => {} }),
      },
      onDidDispose: () => ({ dispose: () => {} }),
      reveal() {}, dispose() {},
    }),
    onDidChangeActiveTextEditor: () => ({ dispose: () => {} }),
    onDidChangeTextEditorSelection: () => ({ dispose: () => {} }),
    setStatusBarMessage: () => ({ dispose: () => {} }),
  },
};

const fakeVscode = new Proxy(_base, {
  get(t, k) {
    if (k in t) return t[k];
    return _permissive(String(k));
  },
});

const origLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') return fakeVscode;
  return origLoad.call(this, request, parent, isMain);
};

const ext = require('./extension.js');

// 真实宿主一定提供 extensionPath / extensionUri；mock 缺了它，
// activate 里 `path.join(context.extensionPath, ...)` 会直接抛 TypeError，
// 测试就永远测不到后面注册了哪些 provider。
const ctx = { subscriptions: [], extensionPath: ROOT,
              extensionUri: { fsPath: ROOT } };

try {
  ext.activate(ctx);
  chk(true, 'activate 未抛异常');
} catch (e) {
  chk(false, 'activate 抛出：' + e.message);
}

// 三个请求都已由 LSP 实现 ⇒ 三个 provider 都应注册。
chk(registered.indexOf('definition') >= 0, '应注册 definitionProvider');
chk(registered.indexOf('references') >= 0, '应注册 referenceProvider');
chk(registered.indexOf('hover') >= 0, '应注册 hoverProvider');
chk(registered.indexOf('symbol') >= 0, '应注册 documentSymbolProvider');
// R432：site 级 HTML 文档生成（--browse）必须真的注册进插件。
chk(registered.indexOf('cmd:matlabc.generateSite') >= 0,
  '应注册 site 级 HTML 文档命令（matlabc.generateSite）');
chk(registered.indexOf('cmd:matlabc.openCounterpart') >= 0,
  '应注册 C/MATLAB 对照命令（matlabc.openCounterpart）');
chk(registered.indexOf('cmd:matlabc.toggleCounterpartSync') >= 0,
  '应注册对照同步开关（matlabc.toggleCounterpartSync）');
chk(registered.indexOf('cmd:matlabc.reopenCounterpart') >= 0,
  '应注册恢复对照命令（matlabc.reopenCounterpart）');

// C/MATLAB 对照的纯函数：不启动 LSP 也要能定位「光标属于哪个函数」。
const t = ext._test || {};
const mkDoc = (text) => ({
  getText: () => text,
  offsetAt: (p) => {
    const lines = text.split(/\r?\n/);
    let n = 0;
    for (let i = 0; i < p.line; i++) n += lines[i].length + 1;
    return n + p.character;
  },
});
const mtext = ['function y = foo(x)', 'y = x;', 'end',
               'function z = bar()', 'z = 1;', 'end'].join('\n');
const ctext = ['#include "mlc.h"', 'mlc_status m2c_foo(const mlc_array *x)',
               '{', '    return MLC_OK;', '}', 'void bar(void)', '{', '}'].join('\n');
chk(t.matlabFunctionAt && t.matlabFunctionAt(mkDoc(mtext),
  { line: 1, character: 0 }).name === 'foo', 'MATLAB 函数定位 foo');
chk(t.matlabFunctionAt && t.matlabFunctionAt(mkDoc(mtext),
  { line: 4, character: 0 }).name === 'bar', 'MATLAB 函数定位 bar');
chk(t.cFunctionAt && t.cFunctionAt(mkDoc(ctext),
  { line: 2, character: 0 }).name === 'm2c_foo', 'C 函数定位 m2c_foo');
chk(t.cFunctionAt && t.cFunctionAt(mkDoc(ctext),
  { line: 6, character: 0 }).name === 'bar', 'C 函数定位 bar');
chk(t.matlabFunctionLine && t.matlabFunctionLine(mtext, 'bar') === 4,
  'MATLAB 函数行号');
chk(t.cFunctionLine && t.cFunctionLine(ctext, 'm2c_foo') === 2,
  'C 函数行号');
chk(t.matlabFunctionRange && t.matlabFunctionRange(mtext, 'foo').end === 3,
  'MATLAB 函数范围到下一个 function 前');
chk(t.cFunctionRange && t.cFunctionRange(ctext, 'm2c_foo').end === 5,
  'C 函数范围到匹配的右花括号');
chk(t.mapLine && t.mapLine(2, 1, 3, 10, 12) === 11,
  '行级映射取函数体内相对位置');
chk(t.mapLine && t.mapLine(99, 1, 3, 10, 12) === 12,
  '行级映射越界时钳到目标函数末尾');

// source map 注释：MATLAB 行号写在 C 语句前
const cmapText = [
  'void f(void) {',
  '    /* @m2c src:12 */',
  '    a = b;',
  '    /* @m2c src:20 */',
  '    c = d;',
  '}',
].join('\n');
const cmap = t.parseSourceMap ? t.parseSourceMap(cmapText) : [];
chk(cmap.length === 2 && cmap[0].cLine === 2 && cmap[0].src === 12,
  'source map 能解析 C 行 -> MATLAB 行');
chk(t.srcToCLine && t.srcToCLine(cmap, 13) === 4,
  'MATLAB 行 13 映射到下一个 C 语句');
chk(t.cToSrc && t.cToSrc(cmap, 5) === 20,
  'C 行 5 映射回 MATLAB 行 20');
const shash = 'a'.repeat(64);
chk(t.parseSourceHash &&
  t.parseSourceHash('/* @m2c source_sha256:' + shash + ' */') === shash,
  'source hash 能从 C 注释解析');
chk(t.parseSourceHash && t.parseSourceHash('no hash') === '',
  '没有 source hash 时返回空，不用假值');
const goodHash = require('crypto').createHash('sha256')
  .update('abc', 'utf8').digest('hex');
chk(t.isStale && t.isStale('abc',
  '/* @m2c source_sha256:' + goodHash + ' */', '', '') === false,
  '内容哈希一致时不算陈旧');
chk(t.isStale && t.isStale('abcd',
  '/* @m2c source_sha256:' + goodHash + ' */', '', '') === true,
  '内容哈希不一致时判陈旧');
const h2 = 'b'.repeat(64);
const twoHash = '/* @m2c source_sha256:' + goodHash + ' */\n' +
  'void a(void) {}\n/* @m2c source_sha256:' + h2 + ' */\nvoid b(void) {}\n';
chk(t.parseSourceHashAt && t.parseSourceHashAt(twoHash, 2) === goodHash,
  '多文件哈希：取当前 C 行之前最近的一份');
chk(t.parseSourceHashAt && t.parseSourceHashAt(twoHash, 4) === h2,
  '多文件哈希：跨过函数边界后切换');
chk(ctx.subscriptions.length >= 5,
  'subscriptions 应至少 5 项（definition + references + hover + symbol + 诊断集合），实际 '
  + ctx.subscriptions.length);

try {
  ext.deactivate();
  chk(true, 'deactivate 未抛异常');
} catch (e) {
  chk(false, 'deactivate 抛出：' + e.message);
}

Module._load = origLoad;

// 让 activate 里起的 python 子进程有时间退出，避免脚本挂住
setTimeout(() => {
  console.log('LSP EXTENSION {"bad": ' + bad + ', "good": ' + good + '}');
  process.exit(bad === 0 ? 0 : 1);
}, 500);
