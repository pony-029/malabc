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

// 侧栏「关系」视图的“钉住某个名字”入口（R298）。
// 定义在 activate 内部（那里才有 TreeDataProvider），这里先留一个引用，
// 让前面注册的 CodeLens 命令能调用它 —— **不再打开任何标签页**。
let pinRelationsTo = null;

// 给任何请求加一个上限（R307）。服务端在首次全库分析期间不处理请求，
// 没有上限的话 provider / 侧栏会无限挂着 —— 界面上就是「正在加载…」。
const withTimeout = (p, ms) => {
  let tid = null;
  const t = new Promise((_res, rej) => {
    tid = setTimeout(() => rej(new Error(ms + 'ms 超时')), ms);
  });
  return Promise.race([p, t]).then(
    (v) => { if (tid) clearTimeout(tid); return v; },
    (e) => { if (tid) clearTimeout(tid); throw e; });
};
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
    if (!out) out = vscode.window.createOutputChannel('matlabc');
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
    const m = 'matlabc: 找不到 matlabc_lsp.py。已试过：' +
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
    vscode.window.showErrorMessage('matlabc LSP 启动失败：' + e.message);
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
            'matlabc: 跳转失败（' + (e && e.message) + '）', 6000);
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

  // ---- 语义高亮（R218）---------------------------------------------
  // 官方 TextMate 是正则，分不清「局部变量 / 全局变量 / 结构体字段 /
  // 内置函数 / 用户函数」；这五类只有解析器能分。
  //
  // **legend 必须与 LSP 侧 `_SEMANTIC_TYPES` / `_SEMANTIC_MODS` 完全同序**：
  // 协议里 tokenType 就是个下标，顺序错一位颜色就整体错乱，而且不报错。
  const semLegend = new vscode.SemanticTokensLegend(
    ['variable', 'function', 'property', 'parameter'],
    ['declaration', 'defaultLibrary', 'static']);
  context.subscriptions.push(
    vscode.languages.registerDocumentSemanticTokensProvider(
      { language: 'matlab' },
      {
        provideDocumentSemanticTokens: async (doc) => {
          try {
            const r = await client.request(
              'textDocument/semanticTokens/full',
              { textDocument: { uri: doc.uri.toString() } });
            const data = (r.result || {}).data || [];
            if (!data.length) {
              return null;   // 没识别出任何 token ⇒ 保留 TextMate 的原色
            }
            return new vscode.SemanticTokens(new Uint32Array(data));
          } catch (e) {
            log('semanticTokens 失败：' + (e && e.message));
            return null;
          }
        },
      },
      semLegend)
  );

  // ---- 调用关系图预览窗口（R229）-------------------------------------
  // CodeLens 的 QuickPick 适合"选一个就跳"，但看**整体形状**时它不够：
  // 一个 QuickPick 列表看不出「这条链有三层」。
  // 这里用一个旁开的 webview 画缩进树 —— 只读、静态，不需要脚本权限。
  const renderGraph = (name, info, horizontal) => {
    const esc = (s) => String(s).replace(/[&<>"]/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

    // 参数摘要：`step(a)` 里的 `(a)`。服务端给前 4 个名字 + 总数，
    // 多了就写 `, …` —— 截断必须可见（和前两个列表同一个原则）。
    const sigText = (d) => {
      const p = d.params || [];
      if (!p.length) return '';
      const t = d.param_types || [];
      // 类型只在**有时**才渲染：签名回退那条路径没有类型，
      // 显示成 `a:` 或者 `a:?` 都是在编。
      const shown = p.map((n, i) => (t[i] ? n + ':' + t[i] : n));
      const more = (d.params_total || p.length) > p.length;
      return '<span class="params">(' + esc(shown.join(', ')) +
             (more ? ', …' : '') + ')</span>';
    };

    // 服务端只给前 5 个名字；`total` 是**不同名字**的总数。
    // 截断必须说出来，否则「lb、ub、dim、solver、nonlins」会被读成全部。
    const fmtUnres = (list, total) => {
      const a = list || [];
      if (!a.length) return '';
      const shown = a.join('、');
      const t = total || a.length;
      return t > a.length ? shown + ' 等 ' + t + ' 个' : shown;
    };
    // 一个节点 = 函数名 + 定义行 + 被哪几行调用。
    // 定义行与每个调用行都是**可点击的**（`command:` URI 不需要脚本权限）。
    const link = (rel, line, text) =>
      '<a href="command:matlabc.openAt?' +
      encodeURIComponent(JSON.stringify([rel, line])) + '">' + esc(text) + '</a>';

    // 上游节点：名字 + 定义行 + **被哪几行调用**。
    // 每个节点最多列 6 个调用点，剩下的说「另 N 处」。
    // 9 个 `rel:line` 连排会把整行撑开，而**截断不报就是撒谎** ——
    // 这一轮和上一轮（未解析名字）是同一个毛病。
    const MAX_CALLS = 6;
    const upNode = (d, prefix) => {
      // 每个调用点带**自己所在的文件**：跨文件时 `d.rel` 是错的，
      // 点过去会打开一个毫无关系的行（R256 修的就是这个）。
      const sites = (d.call_sites || []).filter((s) => s && s.line > 0);
      const shown = sites.slice(0, MAX_CALLS);
      const rest = sites.length - shown.length;
      // **入口以服务端为准**（R261）。以前这里靠 `sites.length === 0` 推断，
      // 而 `sites` 滤掉了行号 0 的条目 —— 由 `edges` 补进来、没有行号的
      // 调用者会被当成“不存在”，**一个有调用者的函数就被标成入口**。
      const isEntry = (typeof d.is_entry === 'boolean') ? d.is_entry
                                                        : !sites.length;
      const callHtml = isEntry
        ? '<span class="badge">入口</span>' +
          '<span class="calls entry">无调用者</span>'
        : (sites.length
          ? '<span class="calls">调用自 ' +
            shown.map((s) => link(s.rel, s.line, s.rel + ':' + s.line))
              .join(' ') +
            (rest > 0 ? ' … 另 ' + rest + ' 处' : '') + '</span>'
          : '<span class="calls">有调用者（行号未记录）</span>');
      return '<div class="node' + (isEntry ? ' entry' : '') + '">' +
        prefix + esc(d.name) + sigText(d) +
        '<span class="where">' + link(d.rel, d.line, d.rel + ':' + d.line) +
        '</span>' + callHtml + '</div>';
    };

    // 下游节点：名字 + 定义行 + 复杂度。
    // 这里**不显示「调用自」** —— 那是上游的语义。下游关心的是
    // 「它有多复杂、跳过去看什么」，多给一份上游信息只会让人分不清方向。
    const downNode = (d, prefix) => {
      // 它自己也可能有跳不动的调用 —— 标出来，否则用户点进去才发现。
      // 只给数量等于给了一个没有内容的数字；名字才让人知道去查什么。
      const un = d.unresolved || 0;
      const names = fmtUnres(d.unresolved_names, d.unresolved_names_total);
      const unHtml = un
        ? '<span class="calls">另 ' + un + ' 未解析' +
          (names ? '：' + esc(names) : '') + '</span>' : '';
      return '<div class="node">' + prefix + esc(d.name) + sigText(d) +
        '<span class="where">' + link(d.rel, d.line, d.rel + ':' + d.line) +
        '</span><span class="calls">复杂度 ' + (d.complexity || 0) + '</span>' +
        unHtml + '</div>';
    };

    const rows = [];
    // 根节点也带参数摘要 —— 它和目标函数是同一个东西，
    // 只有在子节点显示签名、根节点不显示，会让人以为根是另一类东西。
    rows.push('<div class="node root">' + esc(name) +
              sigText({ params: info.params,
                        param_types: info.param_types,
                        params_total: info.params_total }) +
              (info.is_entry ? '<span class="badge">源头</span>' : '') +
              '</div>');

    const direct = info.direct || [];
    const others = info.others || [];
    const down = info.down || [];

    // **每层最多画 20 个**。YALMIP 这类项目里一个函数的下游三层
    // 可能有上百个节点，全画出来是一页文字墙 —— 而前 20 个已经足够
    // 判断"这是不是一个热点"。截断了就明说还剩多少，不假装是全部。
    const PER_LEVEL = 20;
    const byLevel = (arr) => {
      const m = {};
      arr.forEach((d) => { (m[d.level] = m[d.level] || []).push(d); });
      return m;
    };

    // ---- 调用链（R287）----
    // Source Insight 那种读法：**一条链一行**，从入口一路读到目标。
    // 分层的树适合看层级，但「这个函数是怎么被调到的」用一句话更省事。
    const chains = info.chains || [];
    if (chains.length) {
      rows.push('<div class="section">链（入口 → 目标）</div>');
      chains.slice(0, 12).forEach((ch) => {
        rows.push('<div class="node chain">' +
          (ch || []).map((n) => link(n.rel, n.line, n.name)).join(' → ') +
          '</div>');
      });
      if (chains.length > 12) {
        rows.push('<div class="empty">… 共 ' + chains.length +
                  ' 条路径，仅显示前 12 条</div>');
      }
    }

    // ---- 横向视图（R291）：目标在左，调用方向右展开 ----
    // 纵向看「有几层」，横向看「一条路怎么走」。两种读法对应两类问题：
    // 「谁还会受影响」用纵向， 「它是怎么被调到的」用横向。
    if (horizontal) {
      rows.push('<div class="section">◀ 上游（目标 ← 谁，逐层向左）</div>');
      if (!chains.length) {
        rows.push('<div class="empty">没有调用者 —— 它是入口。</div>');
      } else {
        const seen = {};
        chains.slice(0, 12).forEach((ch) => {
          const rev = (ch || []).slice().reverse()
            .map((n) => link(n.rel, n.line, n.name)).join(' ← ');
          if (!seen[rev]) {
            seen[rev] = 1;
            rows.push('<div class="node chain">' + esc(name) + ' ← ' +
                      rev + '</div>');
          }
        });
      }
      rows.push('<div class="section">▶ 下游（它 → 谁，逐层向右）</div>');
      if (!down.length) {
        rows.push('<div class="empty">' + (info.unresolved
          ? '没有可跳转的调用；另有 ' + info.unresolved + ' 处无法定位'
          : '不调用其他函数 —— 叶子。') + '</div>');
      } else {
        const dn = byLevel(down);
        Object.keys(dn).map(Number).sort((a, b) => a - b).forEach((lv) => {
          const list = dn[lv];
          rows.push('<div class="node chain"><span class="levelbar">第 ' + lv +
            ' 层</span>　' + list.slice(0, 12)
              .map((d) => link(d.rel, d.line, d.name)).join('　→　') +
            (list.length > 12 ? ' … 另 ' + (list.length - 12) + ' 个' : '') +
            '</div>');
        });
      }
    } else {

    // ---- 上游 ----
    rows.push('<div class="section">▲ 上游（谁调用它）</div>');
    if (!direct.length && !others.length) {
      rows.push('<div class="empty">没有调用者 —— 它是入口。</div>');
    } else {
      const up = byLevel(direct.map((d) => Object.assign({ level: 1 }, d))
        .concat(others));
      Object.keys(up).map(Number).sort((a, b) => a - b).forEach((lv) => {
        if (lv > 1) {
          rows.push('<div class="levelbar">第 ' + lv + ' 层</div>');
        }
        const list = up[lv];
        list.slice(0, PER_LEVEL).forEach((d) => {
          rows.push(upNode(d, '│  '.repeat(lv - 1) + '└─ '));
        });
        if (list.length > PER_LEVEL) {
          rows.push('<div class="empty">… 本层还有 ' +
                    (list.length - PER_LEVEL) + ' 个</div>');
        }
      });
    }

    // ---- 下游 ----
    rows.push('<div class="section">▼ 下游（它调用谁）</div>');
    if (!down.length) {
      // `down` 只含**能跳到定义**的调用。目标可能还有一堆 `foo(...)`
      // 解析不到 —— 那时说「叶子」就是在撒谎（R243）。
      const nm = fmtUnres(info.unresolved_names, info.unresolved_names_total);
      rows.push('<div class="empty">' + (info.unresolved
        ? '没有可跳转的调用；另有 ' + info.unresolved + ' 处调用无法定位' +
          (nm ? '：' + esc(nm) : '') + '（字段取值 / toolbox / 函数句柄）'
        : '不调用其他函数 —— 叶子。') + '</div>');
    } else {
      const dn = byLevel(down);
      Object.keys(dn).map(Number).sort((a, b) => a - b).forEach((lv) => {
        if (lv > 1) {
          rows.push('<div class="levelbar">第 ' + lv + ' 层</div>');
        }
        const list = dn[lv];
        list.slice(0, PER_LEVEL).forEach((d) => {
          rows.push(downNode(d, '│  '.repeat(lv - 1) + '└─ '));
        });
        if (list.length > PER_LEVEL) {
          rows.push('<div class="empty">… 本层还有 ' +
                    (list.length - PER_LEVEL) + ' 个</div>');
        }
      });
      if (info.down_truncated) {
        rows.push('<div class="empty">… 还有更深层，已按 3 层截断' +
                  '（完整树见 CLI：--tree）</div>');
      }
    }

    }

    return '<!DOCTYPE html><html><body>' +
      '<h2>' + esc(name) + '</h2>' +
      '<p class="sum">↑ ' + direct.length + ' 直接 · ' +
      others.length + ' 间接 · ' + (info.entries || 0) + ' 入口' +
      '　｜　↓ ' + (info.down_total || 0) + ' 个被调用' +
      (info.unresolved ? '　｜　' + info.unresolved + ' 处调用无法定位' : '') +
      (info.ambiguous ? '　｜　' + info.ambiguous + ' 处同名定义' : '') + '</p>' +
      rows.join('') +
      '<p class="note">' + (horizontal
        ? '<a href="command:matlabc.previewGraph?' + encodeURIComponent(name) +
          '">切换为纵向（按层）</a>'
        : '<a href="command:matlabc.previewGraphH?' + encodeURIComponent(name) +
          '">切换为横向（按链）</a>') + '　｜　' +
      '静态快照（打开时分析结果）。点击任意文件名或行号可跳转。' +
      '「调用自 5 8 9」里的数字是**语句**：一行里写两次调用只算一处。</p>' +
      '</body></html>';
  };

  // 关系图里每个 `rel:line` 与每个调用行号都指向这个命令。
  context.subscriptions.push(
    vscode.commands.registerCommand('matlabc.openAt', async (rel, line) => {
      try {
        const target = vscode.Uri.file(path.join(root, rel));
        const doc = await vscode.workspace.openTextDocument(target);
        const ed = await vscode.window.showTextDocument(doc);
        const pos = new vscode.Position(Math.max(0, (line || 1) - 1), 0);
        ed.selection = new vscode.Selection(pos, pos);
        ed.revealRange(new vscode.Range(pos, pos),
                       vscode.TextEditorRevealType.InCenter);
      } catch (e) {
        log('openAt 失败：' + (e && e.message));
      }
    })
  );

  // 热点排行（R282/R283）：从「先看哪几个函数」这个问题出发。
  // 复杂度高说明难读，调用者多说明波及面大，两者相乘才是值得先看的地方。
  // R283：可按目录过滤，并可把结果复制成 Markdown，便于贴进评审文档。
  // 横向视图单独一个命令：图里有 `command:` 链接可以来回切。
  context.subscriptions.push(
    vscode.commands.registerCommand('matlabc.previewGraphH', async (name) => {
      if (!name) {
        vscode.window.showWarningMessage('matlabc: 请先从 CodeLens 点一个函数');
        return;
      }
      await vscode.commands.executeCommand('matlabc.previewGraph', name, true);
    })
  );

  const mkHeatMd = (rows) => {
    const head = ['| # | 函数 | 位置 | 复杂度 | 调用者 | 得分 |',
                  '| --- | --- | --- | --- | --- | --- |'];
    const body = rows.map((h, i) => '| ' + (i + 1) + ' | `' + h.name +
      '` | `' + h.rel + ':' + h.line + '` | ' + h.complexity + ' | ' +
      h.callers + ' | ' + h.score + ' |');
    return head.concat(body).join('\n');
  };

  const showHeat = async (dir) => {
    try {
      const params = { limit: 20 };
      if (dir) params.dir = dir;
      const r = await client.request('matlabc/heat', params);
      const rows = r.result || [];
      if (!rows.length) {
        vscode.window.showInformationMessage(dir
          ? ('matlabc: ' + dir + ' 下没有可排行的函数')
          : 'matlabc: 当前工作区没有可排行的函数（分析可能尚未完成）');
        return;
      }
      const items = rows.map((h, i) => ({
        label: (i + 1) + '.\t' + h.name,
        description: '复杂度 ' + h.complexity + ' · 调用者 ' + h.callers +
                     ' · 得分 ' + h.score,
        detail: h.rel + ':' + h.line,
        rel: h.rel,
        line: h.line,
      }));
      items.push({
        label: '$(clippy) 复制为 Markdown',
        description: rows.length + ' 行 · 可直接贴进评审文档',
        copy: true,
      });
      const pick = await vscode.window.showQuickPick(items, {
        placeHolder: (dir ? dir + ' · ' : '') +
                     '热点排行：复杂度 × (1 + 调用者数)',
        matchOnDescription: true,
        matchOnDetail: true,
      });
      if (!pick) return;
      if (pick.copy) {
        await vscode.env.clipboard.writeText(mkHeatMd(rows));
        vscode.window.showInformationMessage(
          'matlabc: 已复制 ' + rows.length + ' 行到剪贴板');
        return;
      }
      await vscode.commands.executeCommand('matlabc.openAt', pick.rel,
                                           pick.line);
    } catch (e) {
      log('showHeat 失败：' + (e && e.message));
      vscode.window.showErrorMessage('matlabc: ' + (e && e.message));
    }
  };

  context.subscriptions.push(
    vscode.commands.registerCommand('matlabc.showHeat', () => showHeat(null))
  );

  // 当前文件所在目录的热点：跨模块的分数没有可比性，同一目录内才有意义。
  context.subscriptions.push(
    vscode.commands.registerCommand('matlabc.showHeatHere', async () => {
      const ed = vscode.window.activeTextEditor;
      if (!ed || !root) return showHeat(null);
      const relp = path.relative(root, ed.document.uri.fsPath)
        .replace(/\\/g, '/');
      const cut = relp.lastIndexOf('/');
      return showHeat(cut >= 0 ? relp.slice(0, cut + 1) : null);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('matlabc.previewGraph', async (name, horizontal) => {
      if (!name) {
        vscode.window.showWarningMessage('matlabc: 请先从 CodeLens 点一个函数');
        return;
      }
      // 点函数 → **只更新侧栏**，不打开标签页（R298）。
      // 标签页会抢走编辑器焦点，大纲随即转到那个 webview 上 —— 用户看到的
      // 就是「大纲不见了」。横向视图是显式命令，仍然保留标签页。
      if (!horizontal && pinRelationsTo) {
        pinRelationsTo(name);
        return;
      }
      try {
        const r = await withTimeout(
          client.request('matlabc/impact', { name: name }), 2500);
        const info = r.result;
        if (info && info.pending) {
          vscode.window.showInformationMessage(
            'matlabc: 正在建全库索引，请稍后再点（首次打开大工程约需 1 分钟）');
          return;
        }
        if (!info) {
          vscode.window.showWarningMessage('matlabc: 找不到 ' + name);
          return;
        }
        // 同样**不抢焦点**：横向面板是「另开一眼」，不该把编辑器的
        // 大纲赶走（R301，与 showRelations 的修法一致）。
        const panel = vscode.window.createWebviewPanel(
          'matlabcGraph', '调用关系：' + name,
          { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
          // `enableCommandUris` 是点击链接的前提；`enableScripts` 仍然关着
          // —— 命令 URI 由宿主执行，页面本身不需要脚本权限。
          { enableScripts: false, enableCommandUris: true });
        const css = [
          'body{font-family:var(--vscode-editor-font-family,monospace);',
          'padding:14px;color:var(--vscode-editor-foreground);',
          'background:var(--vscode-editor-background);}',
          'h2{margin:0 0 4px;font-size:15px;}',
          '.sum{margin:0 0 14px;opacity:.65;font-size:12px;}',
          '.node{line-height:1.7;font-size:13px;}',
          '.node.root{font-weight:600;color:var(--vscode-textLink-foreground);}',
          '.where{opacity:.55;margin-left:10px;font-size:11px;}',
          '.where a{color:var(--vscode-textLink-foreground);text-decoration:none;}',
          '.calls{opacity:.45;margin-left:12px;font-size:11px;}',
          '.calls a{color:var(--vscode-textLink-foreground);text-decoration:none;}',
          '.calls.entry{opacity:.35;font-style:italic;}',
          '.params{opacity:.6;font-size:12px;}',
          '.badge{margin-left:8px;font-size:10px;padding:1px 6px;',
          'border-radius:9px;background:var(--vscode-badge-background);',
          'color:var(--vscode-badge-foreground);vertical-align:1px;}',
          '.node.entry{font-weight:600;}',
          '.node.chain{font-size:12.5px;line-height:1.9;}',
          '.node.chain a{color:var(--vscode-textLink-foreground);',
          'text-decoration:none;}',
          '.section{margin:16px 0 6px;opacity:.75;font-size:12px;',
          'border-bottom:1px solid var(--vscode-editorWidget-border);',
          'padding-bottom:4px;}',
          '.empty{opacity:.4;font-size:12px;font-style:italic;margin:4px 0 4px 8px;}',
          '.levelbar{opacity:.4;font-size:11px;margin:10px 0 2px;',
          'border-top:1px solid var(--vscode-editorWidget-border);padding-top:6px;}',
          '.note{opacity:.4;font-size:11px;margin-top:18px;}',
        ].join('');
        const html = renderGraph(name, info, !!horizontal).replace(
          '</body>', '<style>' + css + '</style></body>');
        panel.webview.html = html;
        log('previewGraph ' + name + ' -> total=' + info.total);
      } catch (e) {
        log('previewGraph 失败：' + (e && e.message));
        vscode.window.showErrorMessage('matlabc: ' + (e && e.message));
      }
    })
  );

  // ---- 光标处名字的关系（R295）---------------------------------------
  // Source Insight 的 Relation 窗口：**同一个入口，两种身份**。
  //   是函数 → 上下游 + 调用链（与 CodeLens 点开的是同一张图）
  //   是变量/字段 → 声明（首次赋值）在哪、本文里还出现在哪些行
  context.subscriptions.push(
    vscode.commands.registerCommand('matlabc.showRelations', async (wordArg) => {
      const ed = vscode.window.activeTextEditor;
      if (!ed) {
        vscode.window.showInformationMessage('matlabc: 请先打开一个 .m 文件');
        return;
      }
      // 悬停里的链接会带上名字；命令面板/右键则用光标处的名字。
      let word = (typeof wordArg === 'string' && wordArg) ? wordArg : '';
      if (!word) {
        const wr = ed.document.getWordRangeAtPosition(
          ed.selection.active, /[A-Za-z]\w*/);
        if (!wr) {
          vscode.window.showInformationMessage('matlabc: 光标处没有标识符');
          return;
        }
        word = ed.document.getText(wr);
      }
      const rel = path.relative(root || '', ed.document.uri.fsPath)
        .replace(/\\/g, '/');
      // 右键与命令面板也走侧栏：**全程不再打开标签页**（R298）。
      // 标签页会抢焦点 → 大纲跟着跑 → 用户看到「大纲不见了」。
      if (pinRelationsTo) {
        pinRelationsTo(word);
        return;
      }
      const esc = (s) => String(s).replace(/[&<>"]/g, (c) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
      const mkLink = (r, ln, txt) => '<a href="command:matlabc.openAt?' +
        encodeURIComponent(JSON.stringify([r, ln])) + '">' + esc(txt) + '</a>';

      let info = null;
      try {
        const r = await client.request('matlabc/impact', { name: word });
        info = (r && r.result) || null;
      } catch (e) {
        log('showRelations：impact 失败 ' + (e && e.message));
      }

      // **preserveFocus**：面板打开但不抢焦点。否则编辑器失去激活，
      // 大纲会转去显示这个 webview —— 而它没有符号，于是「大纲不见了」。
      const panel = vscode.window.createWebviewPanel(
        'matlabcRel', '关系：' + word,
        { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
        { enableScripts: false, enableCommandUris: true });
      const css = [
        'body{font-family:var(--vscode-editor-font-family,monospace);',
        'padding:14px;color:var(--vscode-editor-foreground);',
        'background:var(--vscode-editor-background);}',
        'h2{margin:0 0 4px;font-size:15px;}',
        '.sum{margin:0 0 12px;opacity:.65;font-size:12px;}',
        '.section{margin:14px 0 6px;opacity:.75;font-size:12px;',
        'border-bottom:1px solid var(--vscode-editorWidget-border);',
        'padding-bottom:4px;}',
        '.node{line-height:1.7;font-size:13px;}',
        'a{color:var(--vscode-textLink-foreground);text-decoration:none;}',
        '.code{opacity:.5;font-size:11px;margin-left:8px;}',
        '.note{opacity:.4;font-size:11px;margin-top:16px;}',
      ].join('');

      // ① 是函数：直接给上下游（与 CodeLens 那张图同源）
      if (info && typeof info.total === 'number') {
        panel.webview.html = renderGraph(word, info, false)
          .replace('</body>', '<style>' + css + '</style></body>');
        log('showRelations ' + word + ' -> 函数');
        return;
      }

      // ② 不是函数：本文的声明与出现
      const lines = ed.document.getText().split(/\r?\n/);
      const escRe = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const wordRe = new RegExp('\\b' + escRe + '\\b');
      const declRe = new RegExp('^\\s*(?:\\[[^\\]]*\\]\\s*=\\s*)?' + escRe +
                                '\\s*(?:\\([^)]*\\))?\\s*=');
      const hits = [];
      let decl = -1;
      for (let i = 0; i < lines.length; i += 1) {
        const code = lines[i].replace(/%.*$/, '');
        if (!wordRe.test(code)) continue;
        if (decl < 0 && declRe.test(code)) decl = i;
        hits.push(i);
      }
      const rows = ['<h2>' + esc(word) + '</h2>',
        '<p class="sum">变量 / 标识符　｜　本文出现 ' + hits.length + ' 处</p>',
        '<div class="section">声明（首次赋值）</div>'];
      rows.push(decl >= 0
        ? '<div class="node">' + mkLink(rel, decl + 1, rel + ':' + (decl + 1)) +
          '<span class="code">' +
          esc((lines[decl] || '').trim().slice(0, 80)) + '</span></div>'
        : '<div class="node" style="opacity:.5">本文里没有赋值语句 —— ' +
          '它可能是入参、全局变量，或只被读取</div>');
      rows.push('<div class="section">本文出现</div>');
      hits.slice(0, 200).forEach((i) => {
        rows.push('<div class="node">' +
          mkLink(rel, i + 1, ':' + (i + 1)) + '<span class="code">' +
          esc((lines[i] || '').trim().slice(0, 90)) + '</span></div>');
      });
      if (hits.length > 200) {
        rows.push('<div class="node" style="opacity:.5">… 还有 ' +
                  (hits.length - 200) + ' 处</div>');
      }
      panel.webview.html = '<!DOCTYPE html><html><body>' + rows.join('') +
        '<p class="note">光标停在任意标识符上，执行「matlabc: 查看名字的关系」' +
        '即可；函数会给上下游，变量给声明与出现位置。</p>' +
        '<style>' + css + '</style></body></html>';
      log('showRelations ' + word + ' -> 变量，' + hits.length +
          ' 处，声明行=' + (decl + 1));
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
            // `↓N` 只数库内、可跳的调用；`unresolved` 是那些解析不到的
            // （字段取值、toolbox、函数句柄）。**两者必须一起出现**，
            // 否则用户会拿 N 当分母，然后在那 M 个上按 F12 得到「未找到」。
            const un = d.unresolved || 0;
            const title = '↑' + (d.callers || 0) + ' 调用者 · ↓' +
                          (d.callees || 0) + ' 被调用' +
                          (un ? '（另 ' + un + ' 未解析）' : '') +
                          ' · 复杂度 ' + (d.complexity || 0);
            return new vscode.CodeLens(toRange(l.range), {
              title: title,
              command: 'matlabc.showImpact',
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
    vscode.commands.registerCommand('matlabc.showImpact', async (name, uriStr) => {
      // 点击 CodeLens：拉反向可达集，列出**直接调用者**，选中即跳过去。
      // 这就是 CLI 的 `--impact`，只是在编辑器里可点。
      try {
        const r = await client.request('matlabc/impact', { name: name });
        const info = r.result;
        if (!info) {
          vscode.window.showWarningMessage(
            'matlabc: 找不到 ' + name + ' 的定义');
          return;
        }
        log('impact ' + name + ' -> total=' + info.total +
            ' levels=' + info.levels + ' entries=' + info.entries);
        const direct = info.direct || [];
        if (!direct.length && !(info.others || []).length) {
          // 没有上游时仍然让用户能打开关系图 —— 图上会是一个孤零零的
          // 节点，那本身就是信息（「它是入口，没人调它」）。
          const pick0 = await vscode.window.showQuickPick([
            { label: '$(graph) 预览调用关系图',
              description: '旁侧窗口 · 当前没有上游', preview: true },
          ], { placeHolder: name + ' 没有调用者' +
                          (info.entries ? '（它是入口）' : '') });
          if (pick0 && pick0.preview) {
            await vscode.commands.executeCommand('matlabc.previewGraph', name);
          }
          return;
        }
        // 直接调用者 + 间接（按层标注）。分隔条目不可选，
        // 用 `$(blank)` 之类的空图标会失败，所以用一个可以渲染成空白的标签。
        const items = direct.map((d) => ({
          label: '$(symbol-function) ' + d.name,
          description: '第 1 层 · ' + d.rel + ':' + d.line,
          detail: '直接调用者',
          rel: d.rel,
          line: d.line,
          pickable: true,
        }));
        (info.others || []).forEach((d) => {
          items.push({
            label: '$(symbol-function) ' + d.name,
            description: '第 ' + d.level + ' 层 · ' + d.rel + ':' + d.line,
            detail: '间接调用者',
            rel: d.rel,
            line: d.line,
            pickable: true,
          });
        });
        items.push({
          label: '$(graph) 预览调用关系图',
          description: '旁侧窗口 · 分层展开',
          preview: true,
        });
        const pick = await vscode.window.showQuickPick(items, {
          placeHolder: name + ' 的上游：' + direct.length + ' 个直接 · ' +
                       ((info.others || []).length) + ' 个间接' +
                       (info.entries ? ' · ' + info.entries + ' 个入口' : ''),
          matchOnDescription: true,
        });
        if (pick && pick.preview) {
          await vscode.commands.executeCommand('matlabc.previewGraph', name);
          return;
        }
        if (!pick) {
          return;
        }
        const target = vscode.Uri.file(path.join(root, pick.rel));
        const doc = await vscode.workspace.openTextDocument(target);
        const ed = await vscode.window.showTextDocument(doc);
        const pos = new vscode.Position(Math.max(0, (pick.line || 1) - 1), 0);
        ed.selection = new vscode.Selection(pos, pos);
        ed.revealRange(new vscode.Range(pos, pos),
                       vscode.TextEditorRevealType.InCenter);
      } catch (e) {
        log('impact 失败：' + (e && e.message));
        vscode.window.showErrorMessage('matlabc: ' + (e && e.message));
      }
    })
  );

  // ---- 同一文件内的所有出现位置（R289）--------------------------------
  // Source Insight 的读法：点一个名字，立刻看见它在**本文**里还出现在哪。
  // 纯客户端正则，**不依赖分析结果** —— 服务端没就绪、或这个文件不在分析
  // 范围里，它照样工作。上限 500 处，避免超长文件卡住渲染。
  // **每一步注册都各自兜底**（R293）。激活是自上而下执行的：中间任何一句
  // 抛错，**后面所有注册都不会发生**，而前面的（CodeLens）照常工作 ——
  // 症状看起来就像「只有大纲坏了」。这里不让高亮这一步连累后面。
  try {
  context.subscriptions.push(
    vscode.languages.registerDocumentHighlightProvider({ language: 'matlab' }, {
      provideDocumentHighlights: (doc, pos) => {
        const range = doc.getWordRangeAtPosition(pos, /[A-Za-z_]\w*/);
        if (!range) return [];
        const word = doc.getText(range);
        if (!word) return [];
        const text = doc.getText();
        const esc = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const re = new RegExp('\\b' + esc + '\\b', 'g');
        const out = [];
        let m;
        while ((m = re.exec(text)) !== null && out.length < 500) {
          const s = doc.positionAt(m.index);
          const e = doc.positionAt(m.index + word.length);
          out.push(new vscode.DocumentHighlight(
            new vscode.Range(s, e), vscode.DocumentHighlightKind.Text));
        }
        return out;
      },
    })
  );
  } catch (e) {
    log('注册「出现位置高亮」失败（不影响其它功能）：' + (e && e.message));
  }

  // ---- 侧栏「关系」视图（R297）---------------------------------------
  // Source Insight 的关系窗口是**停靠在侧边**的，不是文档标签页 —— 这一点
  // 决定了三件事：
  //   1. 它不抢编辑器焦点，所以**大纲不会消失**（webview 标签页会抢）；
  //   2. 它**跟着光标自动更新**，不需要先点“查看完整关系”；
  //   3. 它常驻，看一眼就知道，不打断当前编辑。
  try {
    const relState = { roots: [], key: '' };
    const relEmitter = new vscode.EventEmitter();
    const relProvider = {
      onDidChangeTreeData: relEmitter.event,
      getTreeItem: (el) => el,
      getChildren: (el) => (el && el.children ? el.children : relState.roots),
    };
    // 用 createTreeView 而不是 registerTreeDataProvider：**要拿到视图句柄**，
    // 才能把标题改成「关系：xos1」—— 标题写死的话，读者不知道在看谁（R299）。
    const relView = vscode.window.createTreeView('matlabcRelations', {
      treeDataProvider: relProvider,
    });
    context.subscriptions.push(relView);

    const mkItem = (label, o) => {
      o = o || {};
      const it = new vscode.TreeItem(label, o.children
        ? vscode.TreeItemCollapsibleState.Collapsed
        : vscode.TreeItemCollapsibleState.None);
      if (o.desc) it.description = o.desc;
      // **不再用 ThemeIcon**（R302）。codicon 在部分主题/字体环境下会渲染成
      // 乱码（用户看到的就是函数名前的 `@*`），而这里表达的信息用文字符号
      // 就够：`←` `→` `⌗` `⇥`。可读性不该依赖字体是否齐备。
      if (o.cmd) it.command = o.cmd;
      if (o.rel) {
        it.command = { command: 'matlabc.openAt', title: '打开',
                       arguments: [o.rel, o.line] };
        it.tooltip = o.rel + ':' + o.line;
      }
      if (o.children) it.children = o.children;
      return it;
    };

    const refreshRel = async (doc, pos, forced) => {
      // **整段兜底 + 打点**（R312）。侧栏空白的几种可能（未触发 / 抛异常 /
      // 组为空）在界面上完全一样，只能靠日志区分。
      try {
      log('关系触发 forced=' + (forced || '') +
          ' doc=' + (doc ? doc.languageId : 'null') +
          ' pos=' + (pos ? pos.line : 'null'));
      if (!doc || doc.languageId !== 'matlab') {
        log('关系跳过：doc 无效');
        return;
      }
      // 记住最后一次有效的 matlab 文档（R313）：点 CodeLens 时焦点可能
      // 已经在侧栏上，`activeTextEditor` 会是 null —— 那时不能算不出东西。
      relState.lastDoc = doc;
      let word = forced || '';
      let line = -1;
      if (!word) {
        if (!pos) return;
        const wr = doc.getWordRangeAtPosition(pos, /[A-Za-z]\w*/);
        if (!wr) return;
        word = doc.getText(wr);
        line = wr.start.line;
      }
      if (!word) {
        log('关系跳过：光标处没有标识符');
        return;
      }
      if (!forced && relState.key === word + '@' + line) {
        log('关系跳过：同一位置去重 ' + word);
        return;
      }
      relState.key = word + '@' + line;
      const rel = path.relative(root || '', doc.uri.fsPath).replace(/\\/g, '/');

      let info = null;
      try {
        // 服务端在分析未完成时 **2 秒内**返回 `{pending:true}`，这里等 2.5 秒
        // 就能拿到它，而不是干等 70 秒（R307）。
        const r = await withTimeout(
          client.request('matlabc/impact', { name: word }), 2500);
        info = (r && r.result) || null;
      } catch (e) { /* 超时或失败：走变量分支，不空着 */ }

      if (info && info.pending) {
        // **明确说「在算」，并自己重试** —— 空着会让人以为工具坏了。
        relView.title = '关系：' + word;
        relState.roots = [mkItem(word, {
          desc: '分析进行中…',
          children: [mkItem('正在建全库索引，几秒后自动刷新'),
                     mkItem('（首次打开大工程约需 1 分钟）')],
        })];
        relEmitter.fire();
        if (!relState.retryTimer) {
          relState.retryTimer = setTimeout(() => {
            relState.retryTimer = null;
            relState.key = '';           // 清掉去重键，强制重算
            refreshRel(doc, null, word);
          }, 3000);
        }
        return;
      }

      const groups = [];
      // `decl` 在变量分支里赋值、在顶层节点里使用 —— 必须声明在外层，
      // 否则 `let` 的块级作用域会让顶层读到 undefined（R300 的坑）。
      let decl = -1;
      // 这两个也必须在外层：变量分支里赋值，顶层节点（`relState.roots`）
      // 还要读。上一版写成分支内的 `const`，整个侧栏抛 ReferenceError
      // 变成空白 —— 和 R300 的 `decl` 是同一个坑，我又踩了一次（R311）。
      let gfiles = [];
      let isGlobal = false;
      if (info && typeof info.total === 'number') {
        // 箭头就是调用方向：`←` 谁调我，`→` 我调谁。
        // **链与调用者合并**（R300）：一条链本身就是“谁调我”的完整路径，
        // 再单列一份扁平的调用者只是同一信息的碎片版。有链就只给链；
        // 没有链（说明它是入口）才退回到调用者列表。
        // 每条链 = 一条**从入口到我**的完整来路；展开后逐跳是函数名，
        // 而不是一条挤在一起点的长字符串（R301）。
        // 每条链 = 一条**从入口到我**的完整来路（R302）。
        // 结构照 Source Insight 的 Relation 窗口：
        //   顶层符号 → 每条来路 → 逐跳（编号 + 函数名 + 位置）
        // 函数行**不带图标**：TreeItem 的图标在某些主题/字体下会渲染成乱码，
        // 而读者要的是名字本身（用户明确要求「干净的显示一个函数」）。
        // ---- 照 Source Insight 的 Relation 窗口（R303）------------------
        // 三条约束，都来自实际使用：
        //   ① 只写「函数名 + 行号」，**不铺绝对路径**（一屏全是目录没法读）；
        //   ② **近的在上**：紧邻的调用者排最前，逐层向上到入口；
        //   ③ 层数尽量少，别为了"完整"把一屏塞满。
        const curBase = String(rel || '').split('/').pop();
        const shortDesc = (n) => {
          const base = String(n.rel || '').split('/').pop();
          // **优先调用点**（R304）：SI 的 `1. line 286` 指的是「引用发生在
          // 第几行」，不是「函数定义在第几行」。服务端给了 `call_line` 就用它；
          // 最后一跳（就是我）没有出边，退回定义行。
          const ln = n.call_line || n.line;
          // 同文件只写行号；跨文件才带文件名（仍然只到文件名这一级）。
          return (base && base !== curBase ? base + ' · ' : '') +
                 'line ' + (ln || 1);
        };
        const toItem = (nd) => {
          const kids = [];
          nd.children.forEach((v) => kids.push(toItem(v)));
          return mkItem(nd.node.name, {
            desc: shortDesc(nd.node),
            rel: nd.node.rel, line: nd.node.line,
            children: kids.length ? kids : undefined,
          });
        };
        // 用 chains 建一棵**共享前缀**的树：把每条链逆序（直接调用者 → 入口），
        // 同一入口的不同路径自然合流，不会重复列出。
        const rootNode = { node: null, children: new Map() };
        (info.chains || []).forEach((ch) => {
          const ups = (ch || []).slice(0, -1).reverse();
          let cur = rootNode;
          ups.forEach((n) => {
            const key = n.rel + ':' + n.name;
            if (!cur.children.has(key)) {
              cur.children.set(key, { node: n, children: new Map() });
            }
            cur = cur.children.get(key);
          });
        });
        const upItems = [];
        rootNode.children.forEach((v) => upItems.push(toItem(v)));
        groups.push(upItems.length
          ? mkItem('←  调用者（' + info.total + '）', {
              desc: '近 → 远', children: upItems,
            })
          : mkItem('←  无调用者（它是入口）'));

        // 被调用：只展开一层，够判断"它还依赖谁"即可。
        const dns = (info.down || []).slice(0, 20).map((d) =>
          mkItem(d.name, {
            desc: shortDesc(d), rel: d.rel, line: d.line,
          }));
        groups.push(mkItem('→  被调用（' + (info.down_total || 0) + '）',
                           { desc: '我 → 谁',
                             children: dns.length ? dns : [mkItem('（叶子）')] }));
        // 横向视图放最后：它是补充，不该占第一行。
        groups.push(mkItem('⇥  横向查看（箭头关系）', {
          desc: '在右侧打开',
          cmd: { command: 'matlabc.previewGraph', title: '横向',
                 arguments: [word, true] },
        }));
        // **顶层就是这个名字本身** —— 树的第一行必须回答「这是谁的关系」。
        relView.title = '关系：' + word;
        relState.roots = [mkItem(word, {
          // 顶层也**只写行号**：同一屏里出现两遍完整路径就是噪音。
          desc: 'line ' + (info.line || 1),
          rel: info.rel || rel, line: info.line || 1,
          children: groups,
        })];
        relEmitter.fire();
        return;
      } else {
        // 变量 / 字段：本文里的声明与出现
        const lines = doc.getText().split(/\r?\n/);
        const escRe = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const hitRe = new RegExp('\\b' + escRe + '\\b');
        const declRe = new RegExp('^\\s*(?:\\[[^\\]]*\\]\\s*=\\s*)?' + escRe +
                                  '\\s*(?:\\([^)]*\\))?\\s*=');
        const hits = [];
        for (let i = 0; i < lines.length; i += 1) {
          const code = lines[i].replace(/%.*$/, '');
          if (!hitRe.test(code)) continue;
          if (decl < 0 && declRe.test(code)) decl = i;
          hits.push(i);
        }
        if (!hits.length) {
          log('关系跳过：本文没有出现 ' + word);
          return;
        }
        // **本文没有声明时，问一次服务端**（R308）：结构体字段的产地常在
        // 别的文件（`cfg.lb` 在 cfg_build.m 里赋值）。definition 早就支持
        // 跨文件按基名解析，侧栏只是没去问。
        // **先问一次「全库出现」**（R310）：全局变量的价值就在跨文件，
        // 把它排在「本文出现」之后，等于把重点埋在下面。
        let grefs = [];
        if (pos) {
          try {
            const rr = await withTimeout(client.request(
              'textDocument/references',
              { textDocument: { uri: doc.uri.toString() },
                position: { line: pos.line, character: pos.character },
                context: { includeDeclaration: true } }), 1500);
            grefs = (rr && rr.result) || [];
          } catch (e) { /* 拿不到就只给本文结果 */ }
        }
        const byFile = {};
        grefs.forEach((g) => {
          if (!g || !g.uri) return;
          const p2 = vscode.Uri.parse(g.uri).fsPath;
          const r2 = path.relative(root || '', p2).replace(/\\/g, '/');
          (byFile[r2] = byFile[r2] || []).push(g.range.start.line + 1);
        });
        gfiles = Object.keys(byFile).sort();
        // 跨文件 ⇒ 它是全局变量（普通变量活不过函数边界）
        isGlobal = gfiles.length > 1;

        let extLoc = null;
        if (decl < 0 && pos) {
          try {
            const dr = await withTimeout(client.request(
              'textDocument/definition',
              { textDocument: { uri: doc.uri.toString() },
                position: { line: pos.line, character: pos.character } }), 1200);
            extLoc = (dr && dr.result && dr.result[0]) || null;
          } catch (e) { /* 查不到就照旧说「本文没有」 */ }
        }
        let declChild;
        if (decl >= 0) {
          declChild = mkItem('第 ' + (decl + 1) + ' 行',
                             { desc: (lines[decl] || '').trim().slice(0, 40),
                               rel: rel, line: decl + 1 });
        } else if (extLoc && extLoc.uri) {
          const ep = vscode.Uri.parse(extLoc.uri).fsPath;
          const erel = path.relative(root || '', ep).replace(/\\/g, '/');
          const eline = extLoc.range.start.line + 1;
          declChild = mkItem('在其他文件：' + path.basename(ep) + ' 第 ' + eline + ' 行',
                             { desc: erel, rel: erel, line: eline });
        } else {
          declChild = mkItem('本文没有赋值（入参 / 全局 / 只读）');
        }
        groups.push(mkItem(decl >= 0 ? '声明（首次赋值）' : '声明',
                           { children: [declChild] }));
        groups.push(mkItem('本文出现（' + hits.length + '）', {
          children: hits.slice(0, 80).map((i) =>
            mkItem('第 ' + (i + 1) + ' 行',
                   { desc: (lines[i] || '').trim().slice(0, 40),
                     rel: rel, line: i + 1 })),
        }));

        // 全局变量：单列一组「全库出现」，按文件分组、每项可点。
        if (isGlobal) {
          // **分成定义 / 声明 / 使用**（R311）：全局变量只有一个真正的
          // 定义（赋值），多个文件里的 `global X` 只是声明，其余是读取。
          // 混成一片会让人以为它被定义了好几次。
          const toItem = (g) => {
            const p2 = vscode.Uri.parse(g.uri).fsPath;
            const r2 = path.relative(root || '', p2).replace(/\\/g, '/');
            return mkItem(path.basename(p2) + ' 第 ' +
                          (g.range.start.line + 1) + ' 行',
                          { desc: r2, rel: r2, line: g.range.start.line + 1 });
          };
          const defs = grefs.filter((g) => g.kind === 'define');
          const decls = grefs.filter((g) => g.kind === 'declare');
          const uses = grefs.filter((g) => !g.kind || g.kind === 'use');
          if (defs.length) {
            groups.push(mkItem('定义（' + defs.length + ' 处）',
                               { desc: '赋值处', children: defs.slice(0, 10).map(toItem) }));
          }
          if (decls.length) {
            groups.push(mkItem('声明（' + decls.length + ' 个文件）',
                               { desc: 'global 声明', children: decls.slice(0, 20).map(toItem) }));
          }
          if (uses.length) {
            groups.push(mkItem('使用（' + uses.length + ' 处）',
                               { desc: '读取', children: uses.slice(0, 30).map(toItem) }));
          }
        }
      }
      // 变量也一样：顶层是这个变量名，标题写清在看谁。
      // **顶层的行号必须是“声明行”，不是光标行**（R300）。
      // 之前这里用的是光标所在行，于是 `x @sdpvar/xos1.m:14` 指向的是
      // 你正在看的那一行，而不是 `x` 成立的地方 —— 行号对不上代码。
      relView.title = '关系：' + word;
      relState.roots = [mkItem(word, {
        // 跨文件出现的变量就是**全局变量**，标题直接写清这一点，
        // 而不是和局部变量一样只写「（变量）」。
        desc: isGlobal
          ? ('全局变量 · ' + gfiles.length + ' 个文件')
          : ((decl >= 0 ? 'line ' + (decl + 1) : '本文内无声明') + '　（变量）'),
        rel: decl >= 0 ? rel : null,
        line: decl >= 0 ? decl + 1 : 0,
        children: groups,
      })];
      relEmitter.fire();
      log('关系 ' + word + ' -> 组=' + groups.length + ' 全局=' + isGlobal +
          ' refs=' + grefs.length + ' files=' + gfiles.length);
      } catch (e) {
        log('关系 ' + word + ' 失败：' + (e && e.message) + ' @ ' +
            String((e && e.stack) || '').split('\n')[1]);
      }
    };

    // 点 CodeLens / 右键命中的名字：**钉住**它并显示侧栏，不打开标签页。
    pinRelationsTo = async (name) => {
      try {
        const ed = vscode.window.activeTextEditor;
        // 焦点在侧栏时 `activeTextEditor` 为空 —— 回退到最后一次有效文档。
        const doc2 = (ed && ed.document) || relState.lastDoc;
        log('pin ' + name + ' doc=' + (doc2 ? doc2.languageId : 'null'));
        await refreshRel(doc2, null, name);
        await vscode.commands.executeCommand('matlabcRelations.focus');
      } catch (e) {
        log('pinRelationsTo 失败：' + (e && e.message));
      }
    };

    let relTimer = null;
    context.subscriptions.push(
      vscode.window.onDidChangeTextEditorSelection((e) => {
        // 光标一动就解除「钉住」，恢复跟随。
        relState.pinned = null;
        if (relTimer) clearTimeout(relTimer);
        const doc = e.textEditor.document;
        const pos = e.selections[0] && e.selections[0].active;
        relTimer = setTimeout(() => { refreshRel(doc, pos); }, 180);
      })
    );
  } catch (e) {
    log('注册「关系」侧栏失败：' + (e && e.message));
  }

  // ---- 悬停即见关系（R296）-------------------------------------------
  // Source Insight 的读法：**鼠标停在哪，关系就在哪**，不用先右键。
  // 这里是「摘要」：函数给调用者数量与前三个调用点；变量给声明行与出现次数。
  // 想看全的，点悬停里的链接打开右侧面板。
  try {
  context.subscriptions.push(
    vscode.languages.registerHoverProvider({ language: 'matlab' }, {
      provideHover: async (doc, pos) => {
        try {
          const wr = doc.getWordRangeAtPosition(pos, /[A-Za-z]\w*/);
          if (!wr) return null;
          const word = doc.getText(wr);
          if (!word || word.length < 2) return null;

          const md = new vscode.MarkdownString();
          md.isTrusted = true;        // `command:` 链接需要它
          const linkTo = (w) => '[查看完整关系](command:matlabc.showRelations?' +
            encodeURIComponent(w) + ')';

          let info = null;
          try {
            const r = await withTimeout(
              client.request('matlabc/impact', { name: word }), 1200);
            info = (r && r.result) || null;
          } catch (e) { /* 超时就只给变量视图，不卡住悬停 */ }

          if (info && typeof info.total === 'number') {
            md.appendMarkdown('**' + word + '** · ↑' + info.total +
              ' 调用者 · ↓' + (info.down_total || 0) + ' 被调用\n\n');
            (info.direct || []).slice(0, 3).forEach((d) => {
              md.appendMarkdown('· `' + d.name + '`　' +
                                d.rel + ':' + d.line + '  \n');
            });
            md.appendMarkdown('\n' + linkTo(word));
            return new vscode.Hover(md, wr);
          }

          // 变量 / 字段：本文里的声明与出现次数
          const lines = doc.getText().split(/\r?\n/);
          const escRe = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          const hitRe = new RegExp('\\b' + escRe + '\\b');
          const declRe = new RegExp('^\\s*(?:\\[[^\\]]*\\]\\s*=\\s*)?' +
                                    escRe + '\\s*(?:\\([^)]*\\))?\\s*=');
          let decl = -1;
          let n = 0;
          for (let i = 0; i < lines.length; i += 1) {
            const code = lines[i].replace(/%.*$/, '');
            if (!hitRe.test(code)) continue;
            n += 1;
            if (decl < 0 && declRe.test(code)) decl = i;
          }
          if (!n) return null;        // 本文里没出现，就不弹
          md.appendMarkdown('**' + word + '** · 本文出现 ' + n + ' 处\n\n');
          md.appendMarkdown(decl >= 0
            ? '声明（首次赋值）：第 ' + (decl + 1) + ' 行\n'
            : '本文没有赋值 —— 可能是入参、全局变量，或只被读取\n');
          md.appendMarkdown('\n' + linkTo(word));
          return new vscode.Hover(md, wr);
        } catch (e) {
          return null;
        }
      },
    })
  );
  } catch (e) {
    log('注册「悬停关系」失败：' + (e && e.message));
  }

  try {
  context.subscriptions.push(
    vscode.languages.registerDocumentSymbolProvider({ language: 'matlab' }, {
      provideDocumentSymbols: async (doc) => {
        try {
          // **只问一次，立刻回来**（R292）。
          //
          // R287 曾经在这里做 6 次带 sleep 的重试（累计最长 5.25 秒）。
          // 编辑器对 provider 是有超时的：**provider 迟迟不 resolve，
          // 它就把这次结果当成空**，之后再也不会重新请求 ——
          // 也就是说「重试」本身把它拖成了永久空白。
          // 实测（C:\Temp\yalmip\@sdpvar\toeplitz.m，真实子进程）：
          // 服务端毫秒级返回 1 个符号，根本不需要等。
          let raw = [];
          try {
            if (client) {
              // **800ms 超时**（R307）：首次打开工作区时，服务端正在做全库
              // 分析，所有请求都在排队 —— provider 会一直挂着，编辑器就
              // 显示「正在加载…」永远不动，而我的本地兜底在 await 之后，
              // 根本走不到。
              // 服务端就绪时这是毫秒级操作；没就绪就立刻自己扫，不干等。
              const rr = await withTimeout(
                client.request('textDocument/documentSymbol', {
                  textDocument: { uri: doc.uri.toString() },
                }), 800);
              raw = (rr && rr.result) || [];
            }
          } catch (e) {
            log('大纲请求失败/超时：' + (e && e.message));
          }
          log('大纲 ' + path.basename(doc.uri.fsPath) + ' -> ' + raw.length + ' 个符号');

          // **兜底：服务端给不出符号时，就在当前文档上自己扫一遍**（R288）。
          // 连续几轮远程排查都没能让它出符号（服务端本地验过是对的），
          // 而大纲空着对使用者来说是硬伤 —— 与其继续猜链路，
          // 不如让它在最坏情况下也有内容。
          // 这是**兜底**，不是第二事实源：只在服务端返回 0 个符号时启用。
          if (!raw.length) {
            const lines = doc.getText().split(/\r?\n/);
            const found = [];
            for (let i = 0; i < lines.length; i += 1) {
              const code = lines[i].replace(/%.*$/, '');   // 去掉行内注释
              const m = /^\s*function\b\s*(?:\[[^\]]*\]|[A-Za-z_][\w.]*)?\s*=?\s*([A-Za-z]\w*)\s*\(/.exec(code);
              if (m) found.push({ name: m[1], line: i });
            }
            log('大纲 ' + path.basename(doc.uri.fsPath) +
                ' 服务端为空，本地扫描得到 ' + found.length + ' 个');
            // 连本地扫描都找不到函数时，**不许留空白** —— 空大纲无法与
            // 「工具坏了」区分。放一行说明，并写明该把什么发回来。
            if (!found.length) {
              const msg = '未识别到 function（本地扫描 0 个）';
              return [new vscode.DocumentSymbol(
                msg, '请把输出频道 matlabc 的内容发回来',
                vscode.SymbolKind.Function,
                new vscode.Range(0, 0, 0, msg.length),
                new vscode.Range(0, 0, 0, msg.length))];
            }
            return found.map((f, i) => {
              const endLine = (i + 1 < found.length)
                ? found[i + 1].line - 1 : lines.length - 1;
              const range = new vscode.Range(f.line, 0,
                                             Math.max(f.line, endLine), 0);
              const sel = new vscode.Range(f.line, 0, f.line, f.name.length);
              return new vscode.DocumentSymbol(f.name, '',
                                               vscode.SymbolKind.Function,
                                               range, sel);
            });
          }

          return raw.map((s) => {
            const kind = s.kind === 12
              ? vscode.SymbolKind.Function
              : vscode.SymbolKind.Class;
            let range = toRange(s.range);
            const sel = toRange(s.selectionRange);
            // **`selectionRange` 必须落在 `range` 内**，否则 VSCode 抛
            // `selectionRange must be contained in fullRange`，**整批符号被拒**，
            // 大纲一片空白（R294 就是这么空了好几轮）。
            // 服务端已修根因；这里再兜一层：包不住就扩，绝不让一个符号
            // 不合法而丢掉全部。
            if (range.start.isAfter(sel.start) || range.end.isBefore(sel.end)) {
              range = range.union(sel);
            }
            return new vscode.DocumentSymbol(s.name, '', kind, range, sel);
          });
        } catch (e) {
          log('大纲失败：' + (e && e.message));
          return [];
        }
      },
    })
  );
  } catch (e) {
    log('注册「大纲」provider 失败：' + (e && e.message));
  }

  context.subscriptions.push(collection);
  log('activate 完成：diagnostics / definition / references / hover / ' +
      'codeLens / 语义高亮 / 大纲 / 出现位置 均已注册');
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
