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


// 选 Python 解释器（R386）。
// 设置里那一项是纯字符串：用户不知道填什么，填错了也只表现为"启动失败"。
// 这个命令让他直接挑文件，**当场验证能不能启动**，再写进设置。

// Python 起不来时给**可操作**的提示（R392）。
// 原来的提示只有一句 `matlabc LSP 启动失败：timeout` —— 用户既不知道原因，
// 也不知道下一步该做什么。而这件事九成是"PATH 里没有 python"，
// 解决方法是"去设置里指一个"，所以提示里就直接给那个按钮。
function showPythonHelp(detail) {
  const msg = 'matlabc: 启动失败 —— 找不到可用的 Python。\n' +
              (detail ? ('原因：' + detail + '\n') : '') +
              '请在设置里指定 Python 路径（命令面板 → matlabc: 选择 Python 解释器），' +
              '或按 Ctrl+, 搜索 matlabc.pythonPath 填绝对路径。';
  vscode.window.showErrorMessage(msg, '选择 Python 解释器', '打开使用说明')
    .then((pick) => {
      if (pick === '选择 Python 解释器') {
        vscode.commands.executeCommand('matlabc.selectPython');
      } else if (pick === '打开使用说明') {
        vscode.commands.executeCommand('matlabc.openGuide');
      }
    });
}

async function pickPython() {
  const picked = await vscode.window.showOpenDialog({
    canSelectMany: false,
    canSelectFiles: true,
    openLabel: '使用这个 Python',
    filters: process.platform === 'win32' ? { 'Python': ['exe'] } : undefined,
  });
  if (!picked || !picked.length) return;
  const py = picked[0].fsPath;

  const ok = await new Promise((resolve) => {
    const { spawn } = require('child_process');
    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        try { child.kill(); } catch (e) { /* 已经退了 */ }
        resolve(false);
      }
    }, 8000);
    const child = spawn(py, ['-c', 'print(1)'], { windowsHide: true });
    child.on('error', () => {
      if (!settled) { settled = true; clearTimeout(timer); resolve(false); }
    });
    child.on('exit', (code) => {
      if (!settled) { settled = true; clearTimeout(timer); resolve(code === 0); }
    });
  });

  if (!ok) {
    vscode.window.showErrorMessage(
      'matlabc: 这个路径启动不了 Python：' + py +
      '。换一个试试（例如 C:\\Python310\\python.exe）。');
    return;
  }
  await vscode.workspace.getConfiguration('matlabc')
    .update('pythonPath', py, vscode.ConfigurationTarget.Global);
  const act = await vscode.window.showInformationMessage(
    'matlabc: Python 已指向 ' + py, '重新加载窗口');
  if (act) {
    await vscode.commands.executeCommand('workbench.action.reloadWindow');
  }
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
    // **起不来的时候，正是最需要自救的时候**：这三个命令原本注册在这行
    // return 之后，于是"服务器起不来"时连「打开使用说明」都不存在。
    context.subscriptions.push(
      vscode.commands.registerCommand('matlabc.selectPython', pickPython)
    );
    context.subscriptions.push(
      vscode.commands.registerCommand('matlabc.openGuide', async () => {
        const p = path.join(context.extensionPath, 'USER_GUIDE.md');
        if (fs.existsSync(p)) {
          await vscode.commands.executeCommand(
            'markdown.showPreview', vscode.Uri.file(p));
        } else {
          vscode.window.showErrorMessage('matlabc: 找不到使用说明');
        }
      })
    );
    context.subscriptions.push(
      vscode.commands.registerCommand('matlabc.openGuidePdf', async () => {
        const p = path.join(context.extensionPath, 'USER_GUIDE.pdf');
        if (fs.existsSync(p)) { vscode.env.openExternal(vscode.Uri.file(p)); }
        else { vscode.window.showErrorMessage('matlabc: 找不到使用说明 PDF'); }
      })
    );
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

  // spawn 失败（PATH 里没有 python）走这里：比 initialize 超时快得多。
  client.onSpawnError = (err) => {
    log('spawn 失败：' + (err && (err.code || err.message)));
    showPythonHelp((err && (err.code || err.message)) || '');
  };

  client.initialize(root, {
    // 跨语言（C 源 / mex / DLL 导出表）分析开关，见设置 `matlabc.crossLanguage`
    crossLanguage: cfg.get('crossLanguage') !== false,
  }).then(() => {
    log('initialize 成功');
    // **装好之后说一句**：只在这个版本第一次成功启动时出现一次。
    // 否则用户装完只看到侧边栏多了一个图标，不知道下一步做什么。
    const ver = (context.extension && context.extension.packageJSON &&
                 context.extension.packageJSON.version) || '';
    const seen = context.globalState.get('matlabc.welcomed', '');
    if (seen !== ver) {
      vscode.window
        .showInformationMessage('matlabc 已就绪（' + ver + '）：跳转、关系面板、诊断已启用。',
                                '打开使用说明', '看导览')
        .then((pick) => {
          if (pick === '打开使用说明') {
            vscode.commands.executeCommand('matlabc.openGuide');
          } else if (pick === '看导览') {
            vscode.commands.executeCommand('matlabc.openTour');
          }
        });
      context.globalState.update('matlabc.welcomed', ver);
    }
  }).catch((e) => {
    log('initialize 失败：' + e.message + '   stderr尾部=' +
        (client.stderrTail || []).join('').slice(-400));
    showPythonHelp(e.message);
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

  // ---- 打开使用导览（R350）--------------------------------------------
  // 导览的**源文件只有一份**，在 `releases/demo/matlabc-tour.html`；
  // 打包时映射进包内 `media/tour.html`。两个位置都试：
  //   装好的扩展 → 包内 media/tour.html
  //   直接跑仓库 → releases/demo/matlabc-tour.html
  // 只认一个位置的话，会出现「装了能打开、改源码时反而打不开」。
  context.subscriptions.push(
    vscode.commands.registerCommand('matlabc.openTour', async () => {
      const cands = [
        path.join(context.extensionPath, 'media', 'tour.html'),
        path.join(path.dirname(lspPath), '..', 'releases', 'docs',
                  'matlabc-tour.html'),
      ];
      let hit = '';
      for (const p of cands) {
        try {
          if (fs.existsSync(p)) { hit = p; break; }
        } catch (e) { /* 权限问题就跳过这个候选 */ }
      }
      if (!hit) {
        vscode.window.showErrorMessage(
          'matlabc: 找不到使用导览（生成它：python tools/make_tour_html.py）');
        return;
      }
      log('打开导览 ' + hit);
      vscode.env.openExternal(vscode.Uri.file(hit));
    })
  );

  // ---- 打开使用说明（R373）--------------------------------------------
  // 手册只讲「装完怎么用」，随包分发；这里用 VS Code 自带的 Markdown 预览打开。
  // 两个候选：装好的扩展 → 包根 USER_GUIDE.md；直接跑仓库 → releases/docs/USER_GUIDE.md。
  context.subscriptions.push(
    vscode.commands.registerCommand('matlabc.openGuide', async () => {
      const cands = [
        path.join(context.extensionPath, 'USER_GUIDE.md'),
        path.join(path.dirname(lspPath), '..', 'releases', 'docs',
                  'USER_GUIDE.md'),
      ];
      let hit = '';
      for (const p of cands) {
        try {
          if (fs.existsSync(p)) { hit = p; break; }
        } catch (e) { /* 权限问题就跳过这个候选 */ }
      }
      if (!hit) {
        vscode.window.showErrorMessage('matlabc: 找不到使用说明文件');
        return;
      }
      log('打开使用说明 ' + hit);
      await vscode.commands.executeCommand(
        'markdown.showPreview', vscode.Uri.file(hit));
    })
  );

  // ---- 打开使用说明的 PDF 版（R382）-----------------------------------
  // Markdown 预览要先点一次"打开预览"，而且换台机器不一定有预览器；
  // PDF 打开就是最终排版，四张示意图直接落在页面上，也方便转发给同事。
  context.subscriptions.push(
    vscode.commands.registerCommand('matlabc.openGuidePdf', async () => {
      const cands = [
        path.join(context.extensionPath, 'USER_GUIDE.pdf'),
        path.join(path.dirname(lspPath), '..', 'releases', 'docs',
                  'matlabc-guide.pdf'),
      ];
      let hit = '';
      for (const p of cands) {
        try {
          if (fs.existsSync(p)) { hit = p; break; }
        } catch (e) { /* 权限问题就跳过 */ }
      }
      if (!hit) {
        vscode.window.showErrorMessage(
          'matlabc: 找不到使用说明 PDF（生成它：python tools/make_guide_pdf.py）');
        return;
      }
      log('打开 PDF 说明 ' + hit);
      vscode.env.openExternal(vscode.Uri.file(hit));
    })
  );

  // ---- 选择 Python 解释器（R386）------------------------------------
  context.subscriptions.push(
    vscode.commands.registerCommand('matlabc.selectPython', pickPython)
  );

  // ---- 生成 HTML 分析报告（R327）-------------------------------------
  // 分析器本来就能出这份报告（`--html`），只是编辑器里拿不到。
  // 报告落在工作区的 `.matlabc/` 下，不污染源码目录，也不用用户记命令。
  context.subscriptions.push(
    vscode.commands.registerCommand('matlabc.generateReport', async () => {
      if (!root) {
        vscode.window.showWarningMessage('matlabc: 请先打开一个工作区');
        return;
      }
      const _cp = require('child_process');
      // **必须读 pythonPath**：原来写的是 `cfg.get('python')` —— 那个键
      // 根本不存在，所以用户在设置里填了绝对路径，生成出来的配置里仍是
      // `python`。而这份配置是在**别的客户端**里跑的，PATH 与编辑器不同，
      // 报错只会说「启动失败」，没人会想到是配置生成器读错了键。
      const py = cfg.get('pythonPath', 'python');
      const mpy = path.join(path.dirname(lspPath), 'matlabc.py');
      if (!fs.existsSync(mpy)) {
        vscode.window.showErrorMessage('matlabc: 找不到 matlabc.py');
        return;
      }
      const outDir = path.join(root, '.matlabc');
      const outFile = path.join(outDir, 'report.html');
      try {
        fs.mkdirSync(outDir, { recursive: true });
      } catch (e) { /* 已存在 */ }

      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification,
          title: 'matlabc: 正在生成分析报告' },
        () => new Promise((resolve, reject) => {
          _cp.execFile(py, [mpy, root, '--html', outFile],
                       { cwd: root, maxBuffer: 32 * 1024 * 1024 },
                       (err, stdout, stderr) => {
                         if (err) {
                           log('报告失败：' + (stderr || err.message));
                           reject(new Error(stderr || err.message));
                           return;
                         }
                         log('报告已生成 ' + outFile);
                         resolve(stdout);
                       });
        })
      ).then(() => {
        vscode.window.showInformationMessage(
          'matlabc: 报告已生成（.matlabc/report.html）');
        vscode.env.openExternal(vscode.Uri.file(outFile));
      }).catch((e) => {
        vscode.window.showErrorMessage(
          'matlabc: 生成报告失败 —— ' + (e && e.message));
      });
    })
  );

  // ---- 生成 MCP 配置（R327）-------------------------------------------
  // 用户要在别的 AI 客户端里用这套能力，就得手写一段 JSON；
  // 而 python 路径、脚本路径、工程根三个值都容易填错。
  // 这里直接生成好，两个格式都给：VS Code 内置 MCP 与通用 mcpServers。
  context.subscriptions.push(
    vscode.commands.registerCommand('matlabc.generateMcpConfig', async () => {
      const py = cfg.get('python') || 'python';
      const mcp = path.join(path.dirname(lspPath), 'matlabc_mcp.py')
        .replace(/\\/g, '/');
      const ws = (root || '${workspaceFolder}').replace(/\\/g, '/');
      // VS Code 的 mcp.json 用 `servers`，每项带 `type: stdio` 最稳
      // （缺省也是 stdio，但显式写出来省得读者去查）。
      const vs = {
        servers: {
          matlabc: { type: 'stdio', command: py, args: [mcp, '--root', ws] },
        },
      };
      const generic = {
        mcpServers: { matlabc: { command: py, args: [mcp, '--root', ws] } },
      };
      const pick = await vscode.window.showQuickPick([
        { label: '$(file-code) 写入 .vscode/mcp.json',
          description: 'VS Code 内置 MCP（1.102+）',
          fmt: 'vs', data: vs },
        { label: '$(clippy) 复制通用配置',
          description: 'Claude Desktop / Cursor 等使用的 mcpServers 格式',
          fmt: 'generic', data: generic },
        { label: '$(output) 只复制 VS Code 格式',
          description: '自己贴到别处',
          fmt: 'vs', data: vs },
      ], { placeHolder: 'MCP 配置：选择目标' });
      if (!pick) return;

      const text = JSON.stringify(pick.data, null, 2);
      if (pick.fmt === 'generic') {
        await vscode.env.clipboard.writeText(text);
        vscode.window.showInformationMessage(
          'matlabc: 已复制 mcpServers 配置到剪贴板');
        return;
      }
      if (pick.label.indexOf('写入') >= 0 && root) {
        const dir = path.join(root, '.vscode');
        try { fs.mkdirSync(dir, { recursive: true }); } catch (e) { /* */ }
        fs.writeFileSync(path.join(dir, 'mcp.json'), text + '\n', 'utf8');
        log('已写入 .vscode/mcp.json');
        vscode.window.showInformationMessage(
          'matlabc: 已写入 .vscode/mcp.json，重载窗口后生效');
      } else {
        await vscode.env.clipboard.writeText(text);
        vscode.window.showInformationMessage('matlabc: 已复制到剪贴板');
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

    // **记住展开状态**（R357）。面板每次光标一动就整体重建，而重建出来的
    // 分组默认是收起的 —— 读者刚点开的「上游」，下一次移动光标就没了。
    // 这不会报错，只是让人反复做同一件事。
    //
    // 键用 label：调用点有几十处，要求每处都传 id 既啰嗦又容易漏；
    // 代价是 label 里带计数（`上游（3）`），计数一变这一项的展开态就丢 ——
    // 可接受（那种情况下内容本来就变了）。
    const relExpanded = new Set(
      context.workspaceState.get('matlabc.relExpanded') || []);
    const relKey = (el) => String((el && el.label) || '');
    const saveExpanded = () => {
      try {
        context.workspaceState.update('matlabc.relExpanded',
                                      Array.from(relExpanded).slice(-80));
      } catch (e) { /* 存不下不影响本次会话 */ }
    };
    relView.onDidExpandElement((e) => {
      relExpanded.add(relKey(e.element));
      saveExpanded();
    });
    relView.onDidCollapseElement((e) => {
      relExpanded.delete(relKey(e.element));
      saveExpanded();
    });

    const mkItem = (label, o) => {
      o = o || {};
      const it = new vscode.TreeItem(label, o.children
        ? (relExpanded.has(String(label))
          ? vscode.TreeItemCollapsibleState.Expanded
          : vscode.TreeItemCollapsibleState.Collapsed)
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
      // **请求序号**（R320）：两次 refreshRel 可能并发（快速移动光标），
      // 先发的那个若后返回，就会把新结果覆盖成旧内容 —— 用户看到的是
      // 「点了全局变量，界面还停在刚才的局部变量上」。
      const epoch = (relState.epoch = (relState.epoch || 0) + 1);
      const stale = () => epoch !== relState.epoch;
      // **注释里的词不算**（R315）：`getWordRangeAtPosition` 不区分代码与注释，
      // 光标停在注释里某个词上（日志里出现过 declare / function）就会拿它
      // 去查关系，白跑一趟还可能显示一堆无关内容。
      if (pos) {
        const _ln = doc.lineAt(pos.line).text;
        const _pct = _ln.indexOf('%');
        if (_pct >= 0 && pos.character >= _pct) {
          log('关系跳过：光标在注释里');
          return;
        }
      }
      let word = forced || '';
      let line = -1;
      // **请求一律用标识符的起始列**（R318）。用户的 cursor 可能落在行首
      // （整行选中、或点行号区），那时服务端 `_ident_at` 取到的是 `global`
      // 这种关键字，references/definition 就永远返回 0 —— 日志里
      // 「references 不足（0 < 本文 2）」重复几十次正是这个原因。
      let wordPos = null;
      if (!word) {
        if (!pos) return;
        const wr = doc.getWordRangeAtPosition(pos, /[A-Za-z]\w*/);
        if (!wr) return;
        word = doc.getText(wr);
        line = wr.start.line;
        wordPos = wr.start;
      } else {
        // 钉住某个名字时没有光标位置：用它在本文件里的第一次出现。
        const _r = doc.getWordRangeAtPosition(new vscode.Position(0, 0),
                                              /[A-Za-z]\w*/);
        wordPos = _r ? _r.start : null;
        if (!wordPos) {
          const _t = doc.getText();
          const _i = _t.indexOf(word);
          wordPos = _i >= 0 ? doc.positionAt(_i) : null;
        }
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

      let pendingFlag = false;
      if (info && info.pending) {
        // **不要在这里 return**（R315）：`pending` 只说明「全库索引还没建好」，
        // 而变量/字段的「本文声明 + 本文出现」完全由客户端算得出来。
        // 之前直接 return，侧栏只剩一句「分析进行中」，什么都不给。
        log('关系 ' + word + ' -> 服务端仍在分析（本地信息先给，3 秒后重试）');
        // 把服务端 stderr 的尾巴带出来（它写着「预热开始 / 结构层就绪 /
        // 预热完成」）——否则只知道「还在算」，不知道算到哪一步（R316）。
        try {
          const tail = (client && client.stderrTail) || [];
          if (tail.length) {
            log('  服务端: ' + tail.slice(-3).join(' | ').slice(0, 300));
          }
        } catch (e) { /* 日志不能带崩 */ }
        pendingFlag = true;
        if (!relState.retryTimer) {
          relState.retryTimer = setTimeout(() => {
            relState.retryTimer = null;
            relState.key = '';           // 清掉去重键，强制重算
            refreshRel(doc, null, word);
          }, 3000);
        }
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
        // **跨语言（C/MEX）**（R342）：MATLAB 里解析不到的调用，若工程内的
        // C 源里有同名定义，就把链路接过去 —— 否则链在 mex 边界断掉，
        // 下游全部丢失，而界面上只表现为「未解析 N 处」。
        try {
          const br = await withTimeout(
            client.request('matlabc/cbridge', { name: word }), 4000);
          const b = br && br.result;
          if (b && b.available && (b.items || []).length) {
            groups.push(mkItem('⇢  跨语言（C 源）(' + b.items.length + ')', {
              desc: 'MATLAB 侧解析不到，但 C 源里有定义',
              children: b.items.slice(0, 15).map((it) => {
                // C 内部的下一跳（R346）：只到 C 入口就停，等于把「链断了」
                // 往后挪一层。这里把 C 的 callee 也挂上，可继续往下看。
                // 多层用前缀箭头表示深度（树项本身只有一级缩进，
                // 把「第几层」写进标签比靠缩进更可靠）。
                const kids = (it.c_down || []).map((d) => {
                  const dep = d.depth || 1;
                  return mkItem('↳ '.repeat(dep - 1) + d.name, {
                    desc: '第 ' + dep + ' 层 · line ' + (d.line || 0),
                    rel: it.c_rel, line: d.line || it.c_line,
                  });
                });
                return mkItem(it.c_name, {
                  desc: String(it.c_rel || '').split('/').pop() +
                        ' · line ' + it.c_line +
                        (kids.length ? ' · 内部 ' + kids.length + ' 处' : ''),
                  rel: it.c_rel, line: it.c_line,
                  children: kids.length ? kids : undefined,
                });
              }),
            }));
          }
          if (b && b.available && (b.binaries || []).length) {
            groups.push(mkItem('⇢  二进制（mex / 库）(' +
                               b.binaries.length + ')', {
              desc: '入口名写在文件名上',
              children: b.binaries.slice(0, 10).map((it) =>
                mkItem(it.callee, {
                  desc: String(it.rel || '').split('/').pop() + ' · ' +
                        it.kind + ' 入口 · 文件名匹配',
                  rel: it.rel, line: 1,
                })),
            }));
          }
          if (b && b.available && (b.calllib || []).length) {
            const cl = b.calllib;
            groups.push(mkItem('⇢  calllib 调用（' + cl.length + '）', {
              desc: '已核对库的导出表',
              children: cl.slice(0, 10).map((c) => mkItem(c.fn, {
                desc: c.exported === true
                  ? '✓ 在 ' + String(c.rel || '').split('/').pop() + ' 中导出'
                  : (c.exported === false
                    ? '✗ 该库没有导出 ' + c.fn
                    : '库未找到：' + c.lib),
                rel: c.rel || null, line: 1,
              })),
            }));
          }
          if (b && b.available && (b.unresolved || []).length) {
            // C 里也没有 —— 如实说「这些进了二进制/工具箱」，
            // 不要用一个空组让人以为链路是完整的。
            groups.push(mkItem('⇢  仍连不上（' + b.unresolved.length + '）', {
              desc: 'C 源与工程内二进制都没有',
              children: b.unresolved.slice(0, 10).map((n) =>
                mkItem(n, { desc: '外部（工具箱 / 动态调用 / 系统库）' })),
            }));
          }
        } catch (e) { /* 桥接失败不影响主视图 */ }
        // 横向视图放最后：它是补充，不该占第一行。
        groups.push(mkItem('⇥  横向查看（箭头关系）', {
          desc: '在右侧打开',
          cmd: { command: 'matlabc.previewGraph', title: '横向',
                 arguments: [word, true] },
        }));
        // 已经被更新的请求取代了，就别覆盖界面。
        if (stale()) {
          log('关系 ' + word + ' -> 结果已过期，丢弃');
          return;
        }
        // **顶层就是这个名字本身** —— 树的第一行必须回答「这是谁的关系」。
        relView.title = '关系：' + word;
        // `info.target` 是**名字字符串**，位置在 `info.definitions` 里
        // （R322）。顶层直接取 `info.line` 永远是 undefined，
        // 所以这里一直显示 `line 1`。
        const _tg = (info.definitions || [{}])[0] || {};
        relState.roots = [mkItem(word, {
          // 顶层也**只写行号**：同一屏里出现两遍完整路径就是噪音。
          desc: 'line ' + (_tg.line || 1),
          rel: _tg.rel || rel, line: _tg.line || 1,
          children: groups,
        })];
        relEmitter.fire();
        return;
      } else {
        // **先问一句：这个名字是结构体字段吗**（R339）。
        // 字段和变量是两种问题：字段要回答「谁在写、谁在读、挂在哪些基名上」，
        // 变量要回答「本文哪里出现过」。混在一起就会出现截图里的情形 ——
        // `options.coneprog` 被写成「本文无声明（变量）」，而它明明是个字段。
        if (wordPos && client) {
          try {
            const fr = await withTimeout(
              client.request('matlabc/field', { name: word }), 3000);
            const f = fr && fr.result;
            if (f && (f.writes.length || f.reads.length)) {
              const mk = (row, kind) => {
                const r = row && row.rel ? row.rel : '';
                return mkItem(kind + '　' + path.basename(r) + ':' + row.line, {
                  desc: row.base + '.' + word + '　' + (row.func || ''),
                  rel: r, line: row.line,
                });
              };
              if (f.writes.length) {
                groups.push(mkItem('写入（' + f.writes.length + '）', {
                  children: f.writes.slice(0, 20).map((x) => mk(x, '写')),
                }));
              }
              if (f.reads.length) {
                groups.push(mkItem('读取（' + f.reads.length + '）', {
                  children: f.reads.slice(0, 20).map((x) => mk(x, '读')),
                }));
              }
              log('关系 ' + word + ' -> 字段：' + f.writes.length + ' 写 / ' +
                  f.reads.length + ' 读 / ' + f.bases.length + ' 个基名');
              relView.title = '关系：' + word;
              relState.roots = [mkItem(word, {
                desc: '字段 · ' + f.bases.length + ' 个基名',
                children: groups,
              })];
              relEmitter.fire();
              return;
            }
          } catch (e) { /* 查不到就按变量处理 */ }
        }

        // 变量：本文里的声明与出现
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

        // **函数归属**（R341）。放在这里（而不是「本文出现」之前）是因为
        // 「声明」也要用它：同一个 .m 文件里主函数与局部函数各自独立，
        // **全文件第一个赋值可能落在别的函数里** —— 那不是当前这个变量的
        // 声明。之前直接把 `decl` 当成「首次赋值」，于是给了一个错误答案。
        let ownerOf = () => '';
        try {
          const uriStr = doc.uri.toString();
          const symKey = uriStr + '@' + doc.version;
          if (!relState.syms || relState.syms.key !== symKey) {
            const sr = await withTimeout(client.request(
              'textDocument/documentSymbol',
              { textDocument: { uri: uriStr } }), 2000);
            relState.syms = { key: symKey, list: (sr && sr.result) || [] };
          }
          const syms = relState.syms.list || [];
          ownerOf = (ln) => {
            let best = null;
            syms.forEach((s) => {
              const a = s.range.start.line;
              const b = s.range.end.line;
              if (ln >= a && ln <= b) {
                if (!best || (b - a) < (best.range.end.line -
                                        best.range.start.line)) best = s;
              }
            });
            return best ? best.name : '';
          };
        } catch (e) { /* 拿不到函数范围就整体显示 */ }

        // 光标落在哪个函数里 —— 决定「声明」该在哪找
        const curFn = ownerOf(wordPos ? wordPos.line : hits[0]);
        // 当前函数内的首次赋值才是「这个变量」的声明；
        // 拿不到函数范围时退回文件级（与旧行为一致）。
        let declHere = -1;
        if (!curFn) {
          declHere = decl;
        } else {
          for (let k = 0; k < hits.length; k += 1) {
            const i2 = hits[k];
            if (ownerOf(i2) === curFn &&
                declRe.test(lines[i2].replace(/%.*$/, ''))) {
              declHere = i2;
              break;
            }
          }
        }
        // **本文没有声明时，问一次服务端**（R308）：结构体字段的产地常在
        // 别的文件（`cfg.lb` 在 cfg_build.m 里赋值）。definition 早就支持
        // 跨文件按基名解析，侧栏只是没去问。
        // **先问一次「全库出现」**（R310）：全局变量的价值就在跨文件，
        // 把它排在「本文出现」之后，等于把重点埋在下面。
        let grefs = [];
        if (wordPos) {
          try {
            // **超时必须长于服务端自己的等待**（R317）：`_references` 里
            // `_wait_result(timeout=2.0)` 起步就要 2 秒，而这里原来只给
            // 1.5 秒 —— 请求必然超时，`grefs` 恒为空，于是**全局变量被
            // 当成局部变量**（截图里 `line 13（变量）`）。
            // 位置用 `wordPos`（标识符起始列），不是光标列（R318）。
            const rr = await withTimeout(client.request(
              'textDocument/references',
              { textDocument: { uri: doc.uri.toString() },
                position: { line: wordPos.line,
                            character: wordPos.character },
                context: { includeDeclaration: true } }), 5000);
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
        // **references 不可信时不许下结论**（R317）：服务端在分析未完成时
        // 会返回空数组（实测 2.07s -> 0 个位置），而空数组也意味着「确实
        // 没有引用」。两者无法区分时，**至少它必须覆盖本文的出现**：
        // 同一个名字在同一文件里至少出现 hits 次，返回少于这个数就是没拿到。
        // **只有全局变量才期待全库引用**（R320）。局部变量本来就不会有
        // 跨文件引用，references 只会返回「当前函数的声明」一条 ——
        // 以前一律按「不足」判成「分析中」，于是局部变量也挂着一个
        // 「全库关系 · 待分析完成」，永远等不到。
        const hasGlobalDecl = new RegExp('^\\s*global\\b[^\\n]*\\b' +
                                        escRe + '\\b', 'm')
          .test(doc.getText());
        const refsTrusted = hasGlobalDecl ? (grefs.length >= hits.length)
                                          : true;
        if (!refsTrusted) {
          pendingFlag = true;      // 借同一个标记：界面会写「分析中…」
          log('关系 ' + word + ' -> references 不足（' + grefs.length +
              ' < 本文 ' + hits.length + '），不判定为局部变量');
          // 同样要**自动重试**，否则它会一直停在「分析中…」上。
          if (!relState.retryTimer) {
            relState.retryTimer = setTimeout(() => {
              relState.retryTimer = null;
              relState.key = '';
              refreshRel(doc, null, word);
            }, 3000);
          }
        }

        let extLoc = null;
        if (decl < 0 && wordPos) {
          try {
            // 同上：`_definition` 也有 2 秒等待，1.2 秒必然先超时。
            const dr = await withTimeout(client.request(
              'textDocument/definition',
              { textDocument: { uri: doc.uri.toString() },
                position: { line: wordPos.line,
                            character: wordPos.character } }), 5000);
            extLoc = (dr && dr.result && dr.result[0]) || null;
          } catch (e) { /* 查不到就照旧说「本文没有」 */ }
        }
        let declChild;
        if (declHere >= 0) {
          declChild = mkItem('第 ' + (declHere + 1) + ' 行',
                             { desc: (lines[declHere] || '').trim().slice(0, 40)
                                     + (curFn ? '　@' + curFn : ''),
                               rel: rel, line: declHere + 1 });
        } else if (decl >= 0) {
          // 全文件第一个赋值在**别的函数**里：它是另一个变量，
          // 不能当成这个变量的声明（R341）。
          declChild = mkItem(
            '本函数内没有赋值（另一个函数有同名变量）',
            { desc: (ownerOf(decl) || '另一个函数') + ' 第 ' + (decl + 1) +
                    ' 行：' + (lines[decl] || '').trim().slice(0, 30),
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
        groups.push(mkItem(declHere >= 0 ? '声明（首次赋值）' : '声明',
                           { children: [declChild] }));
        // **按函数分组**（R340）：`ownerOf` 已在前面算好（R341），
        // 这里直接用它把命中行归类。

        const byFn = {};
        hits.forEach((i) => {
          const o = ownerOf(i);
          (byFn[o] = byFn[o] || []).push(i);
        });
        const fnNames = Object.keys(byFn).filter((k) => k);
        if (fnNames.length > 1) {
          groups.push(mkItem(
            '本文出现（' + hits.length + ' · 跨 ' + fnNames.length + ' 个函数）',
            { desc: '同名但不同变量',
              children: fnNames.map((fn) => mkItem(fn, {
                desc: byFn[fn].map((i) => 'line ' + (i + 1)).join('、')
                  .slice(0, 56),
                children: byFn[fn].slice(0, 40).map((i) =>
                  mkItem('第 ' + (i + 1) + ' 行',
                         { desc: (lines[i] || '').trim().slice(0, 40),
                           rel: rel, line: i + 1 })),
              })) }));
        } else {
          groups.push(mkItem('本文出现（' + hits.length + '）', {
            children: hits.slice(0, 80).map((i) =>
              mkItem('第 ' + (i + 1) + ' 行',
                     { desc: (lines[i] || '').trim().slice(0, 40),
                       rel: rel, line: i + 1 })),
          }));
        }

        // 全局变量：单列一组「全库出现」，按文件分组、每项可点。
        // 服务端还没算完时，**明确写一行「待分析完成」** ——
        // 静默缺失会让人以为「它就是没有全库引用」（R316）。
        if (pendingFlag && !isGlobal) {
          groups.push(mkItem('全库关系', {
            desc: '待分析完成',
            children: [mkItem('服务端仍在建索引，完成后自动补上')],
          }));
        }
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
      if (stale()) {
        log('关系 ' + word + ' -> 结果已过期，丢弃');
        return;
      }
      relView.title = '关系：' + word;
      relState.roots = [mkItem(word, {
        // 跨文件出现的变量就是**全局变量**，标题直接写清这一点，
        // 而不是和局部变量一样只写「（变量）」。
        desc: (pendingFlag ? '分析中…　' : '') + (isGlobal
          ? ('全局变量 · ' + gfiles.length + ' 个文件')
          : ((decl >= 0 ? 'line ' + (decl + 1) : '本文内无声明') + '　（变量）')),
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
    // **切换文件也要刷新**（R314）。只监听「选择变化」是不够的：
    // 打开一个文件时光标本来就停在某处（VS Code 还会恢复上次位置），
    // 没有 selection 事件 —— 于是侧栏一直空着，而用户以为它坏了。
    context.subscriptions.push(
      vscode.window.onDidChangeActiveTextEditor((ed) => {
        if (!ed || ed.document.languageId !== 'matlab') return;
        relState.key = '';
        refreshRel(ed.document, ed.selection.active);
      })
    );
    // 激活时若已有打开的文件，立刻算一次（否则要等用户动一下光标）。
    if (vscode.window.activeTextEditor
        && vscode.window.activeTextEditor.document.languageId === 'matlab') {
      refreshRel(vscode.window.activeTextEditor.document,
                 vscode.window.activeTextEditor.selection.active);
    }
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
              client.request('matlabc/impact', { name: word }), 3000);
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
          const hitLines = [];
          for (let i = 0; i < lines.length; i += 1) {
            const code = lines[i].replace(/%.*$/, '');
            if (!hitRe.test(code)) continue;
            n += 1;
            hitLines.push(i);
            if (decl < 0 && declRe.test(code)) decl = i;
          }
          if (!n) return null;        // 本文里没出现，就不弹

          // **函数归属**（R341）：与侧栏同一套规则。否则会出现
          // 「悬停说声明在第 3 行、侧栏说本函数内没有赋值」的自相矛盾 ——
          // 而两者说的是同一个变量。
          let fnOf = () => '';
          try {
            const symKey = doc.uri.toString() + '@' + doc.version;
            if (!relState.syms || relState.syms.key !== symKey) {
              const sr = await withTimeout(client.request(
                'textDocument/documentSymbol',
                { textDocument: { uri: doc.uri.toString() } }), 2000);
              relState.syms = { key: symKey, list: (sr && sr.result) || [] };
            }
            const syms2 = relState.syms.list || [];
            fnOf = (ln) => {
              let best = null;
              syms2.forEach((s) => {
                const a = s.range.start.line;
                const b = s.range.end.line;
                if (ln >= a && ln <= b) {
                  if (!best || (b - a) < (best.range.end.line -
                                          best.range.start.line)) best = s;
                }
              });
              return best ? best.name : '';
            };
          } catch (e) { /* 拿不到函数范围就按文件级 */ }

          const curFn2 = fnOf(pos.line);
          let declHere = decl;
          if (curFn2) {
            declHere = -1;
            for (let k = 0; k < hitLines.length; k += 1) {
              const i2 = hitLines[k];
              if (fnOf(i2) === curFn2 &&
                  declRe.test(lines[i2].replace(/%.*$/, ''))) {
                declHere = i2;
                break;
              }
            }
          }

          md.appendMarkdown('**' + word + '** · 本文出现 ' + n + ' 处\n\n');
          if (declHere >= 0) {
            md.appendMarkdown('声明（首次赋值）：第 ' + (declHere + 1) + ' 行\n');
          } else if (decl >= 0) {
            md.appendMarkdown('本函数内没有赋值（同名变量在 `' +
                              (fnOf(decl) || '另一个函数') + '` 第 ' +
                              (decl + 1) + ' 行）\n');
          } else {
            md.appendMarkdown('本文没有赋值 —— 可能是入参、全局变量，或只被读取\n');
          }
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
