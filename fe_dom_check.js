/**
 * fe_dom_check.js —— 真实 DOM 交互验证（jsdom），fe_audit 的可选检查项 S11。
 *
 * 为什么需要它：fe_audit 的 S5 用的是**手写 DOM stub**，只能捕获「脚本一跑就抛异常」。
 * 真实交互（主题切换是否持久化、命令面板能否打开并产出可跳转结果、#L 深链是否真的
 * 高亮、skip-link 是否指向存在的元素）stub 一律测不出来 —— 本轮补的正是这一层。
 *
 * 用法： node fe_dom_check.js <dir-with-html> [more dirs...]
 * 输出： JSON { issues: [{level, check, file, msg}] }
 * 依赖： jsdom（缺失时输出空 issues 并由调用方降级为 WARN）
 */
'use strict';

const fs = require('fs');
const path = require('path');

// R94：参数解析必须**早于** jsdom 探测。jsdom 缺失时（见下方 catch）会立即早退；
// 若把解析留在文件末尾，`--out=FILE` 就被忽略 —— 结果只写 stdout，调用方
// （fe_audit）读不到文件，判成「未产出结果」WARN ⇒ --strict 下 rc=1。
// 这正是「缺 jsdom 的环境把整个 S11 硬门禁拖红」的真因。
const argv = process.argv.slice(2);
let outFile = null;
let limit = 0;              // 0 = 不限制（全量）
const roots = [];
for (const a of argv) {
  if (a.startsWith('--out=')) outFile = a.slice(6);
  else if (a.startsWith('--limit=')) limit = parseInt(a.slice(8), 10) || 0;
  else roots.push(a);
}

let JSDOM, requestInterceptor;
try {
  const jsdom = require('jsdom');
  JSDOM = jsdom.JSDOM;
  // 注意：jsdom v27 起不再导出 ResourceLoader，改用 requestInterceptor
  requestInterceptor = jsdom.requestInterceptor;
} catch (e) {
  // 缺 jsdom 属**环境**，不是站点缺陷；但结果仍须按 --out 落盘 ——
  // 否则调用方只看到「未产出结果」，分不清「环境缺 jsdom」与「脚本真崩了」。
  // R94：empty 必须**真探过**再报，不能无条件写 true —— 那是在说谎（目录里明明
  // 有页面也报 empty），而下游 check_real_dom 会据此回一条 ERROR。
  // 且「roots 下没有 .html」**不需要 jsdom** 就能查明，恰恰是缺 jsdom 的环境里
  // 「静默假绿」风险最高，那时更必须出信号。
  // 注意：此处不能调用 add() —— issues 用 const 声明在下方，落在这个时刻的
  // 暂时性死区里；直接构造数组写回即可。
  var _found = [];
  try { _found = collectHtml(roots); } catch (e2) { _found = []; }
  var _iss = [];
  if (_found.length === 0) {
    _iss.push({ level: 'WARN', check: 'S11', file: '-',
                msg: '未找到任何 HTML 页面（roots 下无 .html）—— 真实 DOM 检查将假绿' });
  }
  writeResult({ skipped: true, empty: _found.length === 0, issues: _iss,
                sampled: 0, total: _found.length }, outFile);
  process.exit(0);
}

const issues = [];

function add(level, check, file, msg) {
  issues.push({ level, check, file, msg });
}

/** 收集目录下所有 html（含子目录） */
function collectHtml(roots) {
  const out = [];
  for (const root of roots) {
    const st = fs.statSync(root);
    if (st.isFile()) {
      if (root.toLowerCase().endsWith('.html')) out.push(root);
      continue;
    }
    const walk = (d) => {
      for (const name of fs.readdirSync(d)) {
        const p = path.join(d, name);
        const s = fs.statSync(p);
        if (s.isDirectory()) walk(p);
        else if (name.toLowerCase().endsWith('.html')) out.push(p);
      }
    };
    walk(root);
  }
  return out;
}

/* S11 采样：jsdom 加载一页约 1 秒级开销，200+ 页站点全量跑会到分钟级。
   但交互缺陷通常**按页型聚集**（同一模板生成的页面行为一致），因此按
   「页型」去重采样即可在几乎不损失检出率的前提下把耗时压到常数级。
   优先保留：各类关键页面 + 每种目录各取一页（覆盖 src/、dirs/ 等子层级）。 */
const KEY_PAGES = [
  'index.html', 'report.html', 'gs.html', 'global_state.html',
  'func_detail.html', 'unified.html', 'dup.html', 'metrics.html',
  'complexity.html', 'unresolved.html', 'var_taint.html', 'folder_impact.html'
];

function samplePages(files, limit) {
  if (!limit || limit <= 0 || files.length <= limit) return files;
  const picked = [];
  const seen = new Set();
  const take = (f) => {
    const abs = path.resolve(f);
    if (seen.has(abs) || picked.length >= limit) return;
    seen.add(abs); picked.push(f);
  };
  // ① 关键页面优先
  for (const k of KEY_PAGES) {
    for (const f of files) if (path.basename(f).toLowerCase() === k) take(f);
  }
  // ② 每个目录各取一页（覆盖 src/、dirs/ 等子层级的不同模板）
  const byDir = new Map();
  for (const f of files) {
    const d = path.dirname(path.resolve(f));
    if (!byDir.has(d)) byDir.set(d, f);
  }
  for (const f of byDir.values()) take(f);
  // ③ 仍有余量则顺序补齐，保证结果稳定可复现
  for (const f of files) take(f);
  return picked;
}

/**
 * 只加载本地（file://）资源的 ResourceLoader。
 *
 * 必要性：report.html 会动态注入 mermaid 的 CDN 脚本。若允许联网加载，
 * 第三方脚本一旦用到 jsdom 未实现的 API（如 structuredClone），报错会算到
 * 我们头上（误报）。外部 CDN 本身已由 fe_audit 的 S3 单独告警，这里只验证自有代码。
 * 顺带让本检查完全离线、结果可复现。
 */
/* jsdom 未实现的浏览器 API。第三方脚本（如 mermaid CDN）用到它们时报错，
   在真实浏览器里并不存在，必须过滤，否则会误判为产品缺陷。
   外部 CDN 的使用情况由 fe_audit 的 S3 单独告警。 */
const JSDOM_UNSUPPORTED = [
  'structuredClone', 'IntersectionObserver', 'ResizeObserver',
  'matchMedia', 'requestIdleCallback', 'AbortController',
  'requestAnimationFrame', 'cancelAnimationFrame'
];

function isJsdomLimitation(msg) {
  const s = String(msg || '');
  return JSDOM_UNSUPPORTED.some((api) => s.includes(api + ' is not defined'));
}

/**
 * 用 jsdom 加载页面（执行脚本），返回 Promise<{dom, window, errors}>。
 *
 * 两个关键细节（踩过的坑）：
 *  1) url 必须是**绝对** file:// 路径。用相对路径会拼成 `file:///_fe_out/...`
 *     （缺盘符），导致所有外部脚本（src/_search.js 等）加载失败，页面脚本根本没跑，
 *     检查项会全部误报。
 *  2) 必须等 load（或超时）再检查。构造完立刻检查时，外部脚本尚未执行，
 *     命令面板/行深链的初始化都还没发生。
 */
function load(file) {
  const errors = [];
  // jsdom 内置的 cssom 解析器较老，对 min()/max()/:not(a,b) 等现代 CSS 会报
  // 「Could not parse CSS stylesheet」。这类是解析器能力问题而非产品缺陷
  // （真实浏览器可正常解析，且生成的 CSS 里已确认无转义残留），故单独记为 WARN。
  const cssNotes = [];
  const absFile = path.resolve(file);
  const url = 'file:///' + absFile.replace(/\\/g, '/').replace(/^\//, '');
  const vc = new (require('jsdom').VirtualConsole)()
  .on('jsdomError', (e) => {
    const msg = String((e && e.message) || e);
    // 资源加载失败（如缺 mermaid CDN）不算页面缺陷，忽略
    if (/Could not load|not implemented/i.test(msg)) return;
    // jsdom 未实现的浏览器 API（第三方脚本触发）不算产品缺陷
    if (isJsdomLimitation(msg)) return;
    if (/Could not parse CSS stylesheet/i.test(msg)) { cssNotes.push(msg); return; }
    errors.push(msg);
    })
    .on('error', (m) => errors.push(String(m)));
  const dom = new JSDOM(fs.readFileSync(file, 'utf8'), {
    url, runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
    resources: 'usable',
    // jsdom 把 file:// 视为 opaque origin，访问 localStorage 会直接抛异常，
    // 页面脚本随即中断（表现为「主题切换无效」等假缺陷）。这里在脚本执行前
    // 注入内存版 localStorage：既保留 file:// 的相对资源加载，又能验证
    // 「读 key / 写 key 是否一致」这类真实持久化缺陷。
    beforeParse(win) {
      try {
        const mem = {};
        const store = {
          getItem: (k) => (Object.prototype.hasOwnProperty.call(mem, k) ? mem[k] : null),
          setItem: (k, v) => { mem[k] = String(v); },
          removeItem: (k) => { delete mem[k]; },
          clear: () => { for (const k in mem) delete mem[k]; },
          key: (i) => Object.keys(mem)[i] || null,
          get length() { return Object.keys(mem).length; }
        };
        Object.defineProperty(win, 'localStorage', {
          value: store, configurable: true, writable: true
        });
      } catch (e) { /* 注入失败则沿用 jsdom 默认行为 */ }
    }
  });
  return new Promise((resolve) => {
    const win = dom.window;
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      resolve({ dom, window: win, errors, cssNotes });
    };
    // 关键：等 **DOMContentLoaded** 而不是 load。
    // 页面可能动态注入外网 CDN 脚本（如 mermaid），无网络时该请求会长时间挂起，
    // load 事件迟迟不触发，导致检查在脚本尚未执行时就开始（全局函数都还是 undefined）。
    // DOMContentLoaded 时页内脚本与本地外部脚本均已执行完毕，正是我们需要的时机。
    if (win.document.readyState === 'interactive' ||
        win.document.readyState === 'complete') {
      setTimeout(finish, 50);
    } else {
      win.addEventListener('DOMContentLoaded', () => setTimeout(finish, 50));
    }
    setTimeout(finish, 8000);      // 兜底超时，避免外部资源缺失时永久挂起
  });
}

function key(win, k, opts) {
  const ev = new win.KeyboardEvent('keydown', Object.assign({
    key: k, bubbles: true, cancelable: true
  }, opts || {}));
  win.document.dispatchEvent(ev);
  win.dispatchEvent(ev);
}

/* ---------- 检查 1：主题切换必须真的改变 data-theme 且持久化 ---------- */
function checkTheme(file, win) {
  const t = win.maToggleTheme;
  if (typeof t !== 'function') return;      // 页面未提供主题能力，跳过
  const root = win.document.documentElement;
  const before = root.getAttribute('data-theme');
  try {
    t();
  } catch (e) {
    add('ERROR', 'S11', file, 'maToggleTheme() 抛异常：' + e.message);
    return;
  }
  const after = root.getAttribute('data-theme');
  if (before === after) {
    add('ERROR', 'S11', file, '调用 maToggleTheme() 后 data-theme 未变化（切换无效）');
    return;
  }
  // 注意：亮色是「移除 data-theme 属性」表示的，故计算实际生效主题时要把 null 视为 light
  const effective = after || 'light';
  // P271 R1 修复的真实缺陷：读 gs-theme / 写 ma-theme 不对称 → 刷新丢失。
  // 因此「gs-theme 未被写入」与「写入值不一致」都必须报错。
  const stored = win.localStorage.getItem('gs-theme');
  if (stored === null) {
    add('ERROR', 'S11', file,
      '主题切换后未持久化到 gs-theme（刷新会丢失；P271 R1 修复过的 key 不对称缺陷）');
  } else if (stored !== effective) {
    add('ERROR', 'S11', file,
      '主题持久化不一致：当前=' + effective + ' 但 gs-theme=' + stored +
      '（刷新后会跳回，P271 R1 修复过的缺陷）');
  }
}

/* ---------- 检查 2：skip-link 必须指向真实存在的元素 ---------- */
function checkSkipLink(file, win) {
  const a = win.document.querySelector('a.skip-link');
  if (!a) return;                            // S9 已按静态文本报缺失
  const href = a.getAttribute('href') || '';
  if (!href.startsWith('#')) {
    add('ERROR', 'S11', file, 'skip-link 的 href 不是页内锚点：' + href);
    return;
  }
  const target = win.document.getElementById(href.slice(1));
  if (!target) {
    add('ERROR', 'S11', file, 'skip-link 目标不存在：' + href + '（跳了等于没跳）');
  } else if (!target.matches('main') && !target.closest('main')) {
    add('WARN', 'S11', file,
      'skip-link 目标 ' + href + ' 不在 <main> 内（建议指向主内容地标）');
  }
}

/* ---------- 检查 3：命令面板（Ctrl+K）可打开并产出可跳转结果 ---------- */
/**
 * 调用图节点的键盘可达性（P271 R4）。
 *
 * 统一代码结构图（UNIFIED_GRAPH_JS）的节点此前既无 tabindex 也无键盘处理，
 * 只有鼠标 click/dblclick —— 键盘与读屏用户**完全无法使用**该图。
 * 这里在真实 DOM 里校验节点确实可聚焦、有语义与可读标签。
 */
function checkGraphA11y(file, win) {
  const doc = win.document;
  let nodes;
  try {
    nodes = doc.querySelectorAll('.cg-node-g');
  } catch (e) { return; }
  if (!nodes || nodes.length === 0) return;   // 本页没有调用图，跳过

  let noFocus = 0, noRole = 0, noLabel = 0;
  let sample = '';
  for (const n of nodes) {
    // SVG 元素用 getAttribute 判断（.tabIndex 在 SVG 上不可靠）
    if (n.getAttribute('tabindex') === null) {
      noFocus++;
      if (!sample) sample = '缺少 tabindex';
    }
    if (!n.getAttribute('role')) noRole++;
    const al = n.getAttribute('aria-label');
    if (!al || !String(al).trim()) noLabel++;
  }
  if (noFocus) {
    add('ERROR', 'S11', file,
      `调用图有 ${nodes.length} 个节点，其中 ${noFocus} 个不可聚焦（缺 tabindex）`
      + `—— 键盘用户无法使用调用图（${sample}）`);
  }
  if (noRole) {
    add('WARN', 'S11', file,
      `调用图节点中 ${noRole} 个缺少 role 语义（读屏无法识别为可操作元素）`);
  }
  if (noLabel) {
    add('WARN', 'S11', file,
      `调用图节点中 ${noLabel} 个缺少 aria-label（读屏无法播报节点名称）`);
  }
}

function checkPalette(file, win) {
  const doc = win.document;
  const openFn = win.__GS_OPEN__ || win.__gs_open__;
  if (typeof openFn !== 'function') return;  // 该页未挂命令面板，跳过
  let opened = false;
  try {
    opened = openFn() !== false;
  } catch (e) {
    add('ERROR', 'S11', file, '打开命令面板抛异常：' + e.message);
    return;
  }
  if (!opened) return;
  const input = doc.getElementById('gsearch-input');
  if (!input) {
    add('ERROR', 'S11', file, '命令面板已声明打开，但 #gsearch-input 不存在');
    return;
  }
  // 输入一个极可能命中的字符（函数名首字母），验证结果渲染
  const box = doc.getElementById('gsearch-results');
  if (!box) {
    add('ERROR', 'S11', file, '命令面板缺少 #gsearch-results 容器');
    return;
  }
  let tested = false;
  for (const q of ['a', 'e', '_', '1']) {
    input.value = q;
    input.dispatchEvent(new win.Event('input', { bubbles: true }));
    const links = box.querySelectorAll('a[href]');
    if (links.length) { tested = true; break; }
  }
  if (!tested) {
    // 没有索引数据（如 report.html 无 __CG__）时不算缺陷，仅提示
    add('WARN', 'S11', file, '命令面板未产出任何结果（可能本页缺少索引数据）');
    return;
  }
  // 结果链接必须是「相对本页可解析」的（不能是写死的 func_detail.html）
  const links = box.querySelectorAll('a[href]');
  let bad = 0;
  let sample = '';
  for (const a of links) {
    const h = a.getAttribute('href');
    if (!h || h.startsWith('#')) continue;
    // 关键：模拟浏览器解析，确认目标文件真实存在（死链会让「点了没反应」）
    const target = path.resolve(path.dirname(file), h.split('#')[0].split('?')[0]);
    if (!fs.existsSync(target)) {
      bad++;
      if (!sample) sample = h + ' -> ' + target;
    }
  }
  if (bad) {
    add('ERROR', 'S11', file,
      '命令面板结果含 ' + bad + ' 条死链（点击无反应），例：' + sample);
  }
}

/* ---------- 检查 4：源码行深链 #Lx 必须真的高亮 ---------- */
function checkLineDeeplink(file, win) {
  const rows = win.document.querySelectorAll('tr.code-row[id^="L"]');
  if (!rows.length) return;                  // 非源码页
  const first = rows[0];
  const n = (first.getAttribute('id') || 'L1').slice(1);
  try {
    win.location.hash = '#L' + n;
    win.dispatchEvent(new win.Event('hashchange'));
  } catch (e) { /* jsdom 导航受限，忽略 */ }
  // 有些实现监听 hashchange、有些在 DOMContentLoaded 读一次；这里直接再触发一次
  const el = win.document.getElementById('L' + n);
  if (el && !el.classList.contains('ln-hl')) {
    add('WARN', 'S11', file,
      '源码行深链 #L' + n + ' 未加 ln-hl 高亮（可能未监听 hashchange）');
  }
  // 行号单元格应可点击复制（data-ln）
  const lnCell = el && el.querySelector('td.ln');
  if (lnCell && !lnCell.hasAttribute('data-ln')) {
    add('WARN', 'S11', file, '行号单元格缺少 data-ln（无法点击复制本行链接）');
  }
}

async function run(roots, outFile, limit) {
  const all = collectHtml(roots);
  const files = samplePages(all, limit);
  // 采样覆盖度透传给调用方（fe_audit / CI）：仅作信息提示，不计入告警——
  // 否则 S11 在 --strict 下永远无法变绿（采样只是覆盖度提示，并非缺陷）。
  const sampled = files.length;
  const total = all.length;
  // 空 roots（目录下无任何 .html）：jsdom 会静默返回空 issues/sampled=0，
  // 让上层审计假绿。显式给信号（R(收尾)6），由 check_real_dom 升级为 ERROR。
  if (all.length === 0) {
    add('WARN', 'S11', '-', '未找到任何 HTML 页面（roots 下无 .html）—— 真实 DOM 检查将假绿');
  }
  for (const file of files) {
    // 超大页保护：jsdom 解析数十 MB 页面极易 OOM / 超时，单页拖垮整轮 S11 检查。
    // 超过阈值直接跳过并记 WARN（R(收尾)5），建议拆分或分页而非硬扛。
    let size = 0;
    try { size = fs.statSync(file).size; } catch (e) { size = 0; }
    if (size > 8 * 1024 * 1024) {
      add('WARN', 'S11', file,
          '页面过大（' + Math.round(size / 1024 / 1024) +
          'MB）已跳过 DOM 校验，建议拆分或分页');
      continue;
    }
    let ctx;
    try {
      ctx = await load(file);
    } catch (e) {
      add('WARN', 'S11', file, 'jsdom 加载失败：' + e.message);
      continue;
    }
    const { window: win, errors, cssNotes } = ctx;
    for (const e of errors.slice(0, 3)) {
      add('ERROR', 'S11', file, '真实 DOM 中运行期异常：' + e);
    }
    for (const e of cssNotes.slice(0, 1)) {
      add('WARN', 'S11', file,
        'CSS 无法被 jsdom 解析（多为 min()/:not(a,b) 等现代语法的老解析器限制，'
        + '真实浏览器通常正常；若确为语法错误需人工确认）：' + e);
    }
    try {
      checkTheme(file, win);
      checkSkipLink(file, win);
      checkPalette(file, win);
      checkGraphA11y(file, win);
      checkLineDeeplink(file, win);
    } catch (e) {
      add('WARN', 'S11', file, 'DOM 检查自身异常：' + e.message);
    }
    try { win.close(); } catch (e) { /* ignore */ }
  }
  writeResult({ skipped: false, empty: all.length === 0, issues, sampled, total }, outFile);
}

function writeResult(obj, outFile) {
  const payload = JSON.stringify(obj);
  if (outFile) {
    // 写文件而不是 stdout：PowerShell 的重定向会产出 UTF-16，Python 端解不出来
    fs.writeFileSync(outFile, payload, 'utf8');
  } else {
    process.stdout.write(payload);
  }
}

// 采样在收集文件后、逐个检查前完成（见 run 内）
run(roots, outFile, limit).catch((e) => {
  writeResult({
    skipped: true,
    issues: [{ level: 'WARN', check: 'S11', file: '-',
               msg: 'DOM 检查执行失败：' + e.message }]
  }, outFile);
});
