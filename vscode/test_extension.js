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

const fakeVscode = {
  workspace: {
    workspaceFolders: [{ uri: { fsPath: CORPUS } }],
    textDocuments: [],
    getConfiguration: () => ({ get: (k, d) => d }),
    onDidOpenTextDocument: () => ({ dispose: () => disposed.push('onDidOpen') }),
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
  },
  Uri: {
    parse: (s) => ({ toString: () => s, fsPath: s, scheme: 'file' }),
  },
  Range: class {
    constructor(sl, sc, el, ec) {
      this.start = { line: sl, character: sc };
      this.end = { line: el, character: ec };
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
  DiagnosticSeverity: { Error: 0, Warning: 1, Information: 2, Hint: 3 },
  window: { showErrorMessage: (m) => console.log('  [window] ' + m) },
};

const origLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') return fakeVscode;
  return origLoad.call(this, request, parent, isMain);
};

const ext = require('./extension.js');

const ctx = { subscriptions: [] };

try {
  ext.activate(ctx);
  chk(true, 'activate 未抛异常');
} catch (e) {
  chk(false, 'activate 抛出：' + e.message);
}

// **反向断言**：现在只做诊断，所以不许再注册 definition / reference。
// 它们曾在扩展侧注册过、LSP 侧却没实现，导致 F12 静默失败。
chk(registered.indexOf('definition') < 0,
  '不应注册 definitionProvider（LSP 未实现该请求）');
chk(registered.indexOf('references') < 0,
  '不应注册 referenceProvider（LSP 未实现该请求）');
chk(ctx.subscriptions.length >= 1,
  'subscriptions 应至少 1 项（诊断集合 + onDidOpen），实际 '
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
