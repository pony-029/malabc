// test_client.js —— 用**真实的** matlabc_lsp.py 验证 JS 客户端的三件事。
//
//   node vscode/test_client.js
//
// 判据：initialize / 2 条诊断 / definition -> L5 / references -> 1 个。
// 这条测试不改 Python 侧、也不装 npm 包 —— 它验证的是"协议在 JS 侧也通"。

'use strict';

const path = require('path');
const { LspClient } = require('./lspClient');

const ROOT = path.resolve(__dirname, '..');
const CORPUS = path.join(ROOT, 'tests', 'sample_m');
const LSP = path.join(ROOT, 'matlabc_lsp.py');
const PYTHON = process.env.PYTHON || 'python';

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

function uri(p) {
  return 'file:///' + p.replace(/\\/g, '/').replace(/^\//, '');
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

(async function main() {
  const c = new LspClient({ python: PYTHON, script: LSP, cwd: ROOT });
  try {
    const init = await c.initialize(CORPUS);
    const caps = (init.result || {}).capabilities || {};
    chk(caps.textDocumentSync === 1, 'textDocumentSync 应为 1');

    let diags = null;
    c.onNotification((m) => {
      if (m.method === 'textDocument/publishDiagnostics') diags = m.params;
    });

    const cls = path.join(CORPUS, 'MyCls.m');
    c.notify('textDocument/didOpen', {
      textDocument: { uri: uri(cls), languageId: 'matlab', version: 1, text: 'x=1;\n' },
    });
    await sleep(2000);
    chk(diags !== null, 'didOpen 后应收到 publishDiagnostics');
    chk(diags && diags.diagnostics.length === 2,
      'MyCls.m 应 2 条诊断，实际 ' + (diags ? diags.diagnostics.length : 'null'));

    const aM = path.join(CORPUS, 'a.m');
    c.notify('textDocument/didOpen', {
      textDocument: { uri: uri(aM), languageId: 'matlab', version: 1, text: 'x=1;\n' },
    });
    await sleep(500);

    // **反向断言**：`matlabc_lsp.py` 目前只实现诊断，definition / references
    // 一律回空。曾经扩展侧注册了这两个 provider，导致 F12 静默失败；现在两侧
    // 都明确「没有」。哪天 LSP 实现了它们，这两条会变红 —— 那是正确的信号。
    const def = await c.request('textDocument/definition', {
      textDocument: { uri: uri(aM) },
      position: { line: 2, character: 5 },
    });
    chk((def.result || []).length === 0,
      'definition 未实现 ⇒ 应回空数组，实际 ' + JSON.stringify(def.result));

    const ref = await c.request('textDocument/references', {
      textDocument: { uri: uri(aM) },
      position: { line: 5, character: 14 },
      context: { includeDeclaration: false },
    });
    chk((ref.result || []).length === 0,
      'references 未实现 ⇒ 应回空数组，实际 ' + JSON.stringify(ref.result));

    const notFound = await c.request('textDocument/definition', {
      textDocument: { uri: uri(aM) },
      position: { line: 1, character: 5 },
    });
    chk((notFound.result || []).length === 0, '注释上 definition 应为 []');
  } catch (e) {
    bad += 1;
    console.log('  [FAIL] ' + e.message);
  } finally {
    c.dispose();
  }

  console.log('LSP CLIENT {"bad": ' + bad + ', "good": ' + good + '}');
  process.exit(bad === 0 ? 0 : 1);
})();
