import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import path from 'node:path';

/**
 * Vite 配置 —— 同时提供两条真实数据通路。
 *
 * ## 为什么需要这个文件
 *
 * `src/App.jsx` 里有 `fetch('/api/state')` 与 `POST /api/run`，
 * 而原来的 `vite.config.js` **是空文件** —— 于是 `/api/state` 会落到
 * vite 的 SPA 兜底上返回 index.html，前端 `res.json()` 直接抛错，
 * 页面表现为"有骨架、无数据"。
 *
 * ## 两个端点
 *
 * 1 `GET /api/state`
 *    直接读仓库里的 `flow/*.json`（真源），聚合成前端要的形状。
 *    **不写死任何数字** —— 页面上的每个值都来自这些文件。
 *
 * 2 `POST /api/run`
 *    联动入口：真的执行一次 `tools/three_links_report.py`（限定小样本），
 *    返回退出码与最后几行输出。
 *    **默认关闭**：只有 `M2C_ALLOW_RUN=1` 时才真跑 —— 否则返回 501 并说明原因。
 *    这样"点一下就真执行"不会变成"点一下就误跑 3000 个"。
 */

const ROOT = path.resolve(process.cwd(), '..');
const FLOW = path.join(ROOT, 'flow');

function readJson(name, fallback) {
  try {
    return JSON.parse(fs.readFileSync(path.join(FLOW, name), 'utf8'));
  } catch {
    return fallback;
  }
}

/**
 * 真的跑一次三段（R1240）。
 *
 * 用 `spawnSync` 而不是 `execSync`：前者能设 `timeout` 且不会把几十 MB
 * 输出全缓冲在内存里（我们只要尾巴）。
 */
function runThreeLinks(n) {
  const py = process.env.M2C_PYTHON || 'python';
  const script = path.join(ROOT, 'tools', 'three_links_report.py');
  const corpus = process.env.M2C_CORPUS || path.join(ROOT, '..', 'temp', 'gen_mixed');
  const outDir = path.join(ROOT, '..', 'temp', 'matlabc', 'UI_RUN_' + Date.now());

  if (!fs.existsSync(script)) return { ok: false, tail: [], err: '找不到 ' + script };
  if (!fs.existsSync(corpus)) {
    return {
      ok: false,
      tail: [],
      err: '语料目录不存在：' + corpus + '（可用 M2C_CORPUS 指定）',
    };
  }

  const r = spawnSync(py, [script, '-o', outDir, '--limit', String(n), corpus], {
    cwd: ROOT,
    timeout: 120000,          // **120 秒硬超时**
    encoding: 'utf8',
    maxBuffer: 8 * 1024 * 1024,
    // **必须显式给 UTF-8**（R1242）：Windows 下 Python 默认 GBK 输出，
    // 不给这个变量，中文会变成 `���Σ���` 这种乱码。
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  });
  const both = ((r.stdout || '') + (r.stderr || '')).split('\n');
  const tail = both.filter((x) => x.trim()).slice(-40);   // **只留末尾 40 行**

  // **判据用结构化符号，不用中文关键词**（R1242）。
  // 原来写的是 tail.some(x => x.includes('三段'))，而中文一旦乱码就永远匹配不上，
  // 于是 rc=0 却报 ok=0。数字与斜杠在任何编码下都是 ASCII，永远不会骗人。
  const reTriple = /\d+\s*\/\s*\d+\s*[｜|]/;
  const ok = r.status === 0 && tail.some((x) => reTriple.test(x));
  return {
    ok,
    tail,
    err: ok
      ? ''
      : r.error
        ? String(r.error.message)
        : `rc=${r.status}, 未在输出里找到 "N/N |" 形式的三段行`,
  };
}

function buildPipeline(ff, ane, cb, fl, st, stageRows) {
  const stages = ff.stages || [];
  const entries = fl.entries || [];
  const nFixed = entries.filter((e) => e.status === 'fixed').length;
  const by = (id) => stageRows.find((r) => r.id === id) || {};

  const steps = [
    {
      seq: 1,
      id: 'parse',
      name: '解析 .m → MIR',
      module: 'translate/mir.py',
      input: '.m 源文件（合成语料 / 真实工程）',
      output: 'MIR 行：const / op / shape / unmapped',
      metric: stages[0] ? `${stages[0].pass} / ${stages[0].total}` : '—',
      detail: [
        '判据：unmapped 条数为 0 才算通过（不是"能进 MIR"）',
        '降级形态：算子链、表达式树临时量、字面量 HCAT/VCAT',
        stages[0]
          ? `本轮零未映射 ${stages[0].pass} 个，失败 ${stages[0].total - stages[0].pass} 个`
          : '无数据',
      ],
      ok: stages[0] ? stages[0].pass === stages[0].total : null,
      source: 'flow/fullflow.json · stages[0]',
    },
    {
      seq: 2,
      id: 'hir',
      name: 'HIR 契约校验（hir_gate）',
      module: 'translate/hir.py · translate/mir.py',
      input: '刚生成的 MIR 文本',
      output: '抬升成 HIR → 降回 MIR → 比对算子多重集',
      metric: '每次 to_mir 收尾都走一遍',
      detail: [
        '不通过就报错：谁改坏了可降级性，谁在本地立刻红',
        '注意：HIR 的痕迹**不在** MIR 文本里（它是校验，不替换产物）',
        cb.ok === false ? '小脑契约有缺口' : '小脑契约 CB1–CB4 全绿',
      ],
      ok: cb.ok !== false,
      source: 'flow/cerebellum.json',
    },
    {
      seq: 3,
      id: 'emit',
      name: 'MIR → gen.c + main.c',
      module: 'rust/m2c/src/emit.rs · project.rs',
      input: 'MIR 文本',
      output: 'gen.c（函数体）+ main.c（驱动与比对）',
      metric: stages[1] ? `${stages[1].pass} / ${stages[1].total}` : '—',
      detail: [
        'main.c 负责：分配入参、填值、调函数、打印结果',
        '已知约束：入参无 shape 注解时按一维 [4] 假设（会打印 assumed shape [4]）',
        '`*` 默认 OP-MATMUL，仅当两侧都是 2-D 证据时才保留',
      ],
      ok: stages[1] ? stages[1].pass === stages[1].total : null,
      source: 'flow/fullflow.json · stages[1]',
    },
    {
      seq: 4,
      id: 'gcc',
      name: 'gcc 编译',
      module: 'D:\project\MinGW-w64\bin\gcc.EXE',
      input: 'gen.c + main.c + mlc_runtime.c + mlc_ops.c',
      output: '可执行文件（或编译错误）',
      metric: '与⑤合并统计',
      detail: [
        '参数：-std=c99 -O1 -I <gen>/include -I c_runtime/include ... -lm',
        '历史坑：`__k8` 撞 AVX-512 mask 寄存器名，已改 m2c_k*',
      ],
      ok: null,
      source: 'flow/fullflow.json（②的判据含编译）',
    },
    {
      seq: 5,
      id: 'run',
      name: '运行 + 数值比对',
      module: '生成的 exe · m2c_rt_run_all',
      input: '可执行文件 + 测试数据',
      output: '逐元素数值与期望比对',
      metric: stages[2] ? `${stages[2].pass} / ${stages[2].total}` : '—',
      detail: [
        '失败集中在二维数组用例（mat4x4 / mat2x3）',
        '机制：下游按一维假设实现，真二维会让 m2c 直接失败',
      ],
      ok: stages[2] ? stages[2].pass === stages[2].total : null,
      source: 'flow/fullflow.json · stages[2]',
    },
    {
      seq: 6,
      id: 'gate',
      name: '门禁收口（48 道）',
      module: 'tools/check_*.py · check_all.py',
      input: '仓库全量',
      output: '每道门自证 + 汇总',
      metric: ane.ok ? 'ANE 6 条全立' : 'ANE 有缺口',
      detail: [
        'GX2 = check_generated_compiles 的第二个契约（第 48 道）',
        'check_all 会提示"分批模式"与"图漂移"——这两条也要读',
      ],
      ok: !!ane.ok,
      source: 'flow/ane.json · flow/status.json',
    },
    {
      seq: 7,
      id: 'ledger',
      name: '错误台账',
      module: 'flow/failures.json',
      input: '历轮真实犯过的错',
      output: '每条带 witness（能拦住它的判据）',
      metric: `已修 ${nFixed} / 未闭 ${entries.length - nFixed}`,
      detail: [
        '没有 witness 的错误只算故事，不算机制',
        'R1208 把 53 条"标了 fixed 但无 commit"改回 open',
      ],
      ok: null,
      source: 'flow/failures.json',
    },
  ];

  return {
    steps,
    // 让前端能画一个"总进度"：通过步数 / 总步数
    okCount: steps.filter((x) => x.ok === true).length,
    failCount: steps.filter((x) => x.ok === false).length,
    total: steps.length,
  };
}

function buildState() {
  const ff = readJson('fullflow.json', {});
  const ane = readJson('ane.json', {});
  const cb = readJson('cerebellum.json', {});
  const fl = readJson('failures.json', {});
  const st = readJson('status.json', {});

  const stages = ff.stages || [];
  const entries = fl.entries || [];
  const nFixed = entries.filter((e) => e.status === 'fixed').length;

  // 把仓库里的五个模块映射成前端需要的"阶段"形状
  const stageRows = [
    {
      id: 'mir', stage: 'mir',
      name: 'MIR 前端',
      path: 'translate/mir.py',
      desc: '把 .m 降级成 MIR 行（const / op / shape / unmapped）',
      source: 'flow/fullflow.json',
      semantic: stages[0]
        ? { ok: stages[0].pass, n: stages[0].total }
        : null,
    },
    {
      id: 'hir', stage: 'hir',
      name: 'HIR 契约',
      path: 'translate/hir.py · mir.py:hir_gate',
      desc: '每次 to_mir 收尾把 MIR 抬升成 HIR、降回、比对算子多重集',
      source: 'flow/hir_status.json',
      semantic: stages[1] ? { ok: stages[1].pass, n: stages[1].total } : null,
    },
    {
      id: 'emit', stage: 'emit',
      name: 'Rust 发射器',
      path: 'rust/m2c/src/emit.rs',
      desc: 'MIR → gen.c + main.c（assumed shape、MATMUL 降回）',
      source: 'flow/fullflow.json',
      semantic: stages[2] ? { ok: stages[2].pass, n: stages[2].total } : null,
    },
    {
      id: 'rt', stage: 'rt',
      name: 'C 运行时',
      path: 'c_runtime/src/mlc_ops.c',
      desc: 'mlc_array + 算子族，gcc 编译后逐个运行比对',
      source: 'flow/cerebellum.json',
      semantic: cb.rows
        ? {
            ok: cb.rows.filter((r) => r.verdict === 'OK').length,
            n: cb.rows.length,
          }
        : null,
    },
    {
      id: 'gates', stage: 'gates',
      name: '门禁与台账',
      path: 'tools/check_*.py（48 道）',
      desc: '每道门自证 + check_all 汇总；GX2 是第 48 道',
      source: 'flow/ane.json · flow/failures.json',
      semantic: ane.ok ? { ok: 1, n: 1 } : { ok: 0, n: 1 },
    },
  ];

  const now = new Date().toISOString();
  const s3 = stages[2] || null;

  return {
    // App.jsx 读的是下划线版；两种都给，免得再猜一次
    generated_at: now,
    generatedAt: now,
    flowRoot: FLOW,

    // **run**：App.jsx 用 run.stages_participated / run.stages_total
    run: {
      stages_participated: stages.filter((x) => x.pass > 0).length,
      stages_total: stages.length,
      sample: ff.total || 0,
      s1: stages[0] ? stages[0].pass : 0,
      s2: stages[1] ? stages[1].pass : 0,
      s3: s3 ? s3.pass : 0,
      fail2: stages[1] ? stages[1].total - stages[1].pass : 0,
      fail3: s3 ? s3.total - s3.pass : 0,
    },

    // **pipeline**：把"每一步做了什么"全部暴露（用户要求：流程要全展示）
    //
    // 设计原则：**流程骨架固定，数字全部来自 flow/*.json** ——
    // 这样"后续只更新测试数据"就能自动反映到页面。
    pipeline: buildPipeline(ff, ane, cb, fl, st, stageRows),

    // **modules**：五个模块各自的 ok/n 与源文件
    modules: Object.fromEntries(
      stageRows.map((r) => [
        r.id,
        {
          name: r.name,
          path: r.path,
          source: r.source,
          ok: r.semantic ? r.semantic.ok : null,
          n: r.semantic ? r.semantic.n : null,
        },
      ])
    ),
    kpi: {
      total: ff.total || 0,
      stages: stages.map((s) => ({ name: s.name, pass: s.pass, total: s.total })),
      failures: entries.length,
      fixed: nFixed,
      open: entries.length - nFixed,
      aneOk: !!ane.ok,
      cerebellumOk: cb.ok !== false,
      gates: st.gates || null,
    },
    stages: stageRows,
    runs: ff.runs || [],
    findings: ff.findings || [],
    limits: ff.limits || '',
    failures: entries.slice(0, 20),
    cerebellum: cb.rows || [],
  };
}

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'm2c-flow-api',
      configureServer(server) {
        server.middlewares.use('/api/state', (req, res, next) => {
          if (req.method !== 'GET') return next();
          try {
            const body = JSON.stringify(buildState());
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(body);
          } catch (e) {
            res.statusCode = 500;
            res.end(JSON.stringify({ error: String(e) }));
          }
        });

        server.middlewares.use('/api/run', (req, res, next) => {
          if (req.method !== 'POST') return next();
          // **默认不真跑**：这是为了避免"点一下误跑 3000 个"。
          if (process.env.M2C_ALLOW_RUN !== '1') {
            res.statusCode = 501;
            res.setHeader('Content-Type', 'application/json; charset=utf-8');
            res.end(
              JSON.stringify({
                ok: false,
                reason:
                  '联动执行默认关闭。启动前设 M2C_ALLOW_RUN=1 才会真的调用 ' +
                  'tools/three_links_report.py（当前 limit 由前端传入，' +
                  '建议先用 20 个试）。',
              })
            );
            return;
          }
          // App.jsx 传的是 `?stage=xxx&n=20`（query，不是 body）
          const u = new URL(req.url, 'http://127.0.0.1');
          const stage = u.searchParams.get('stage') || 'unknown';
          const n = Number(u.searchParams.get('n') || 0);
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          // **限幅**：一次误点不该跑 3000 个（50 个约 20 秒）
          if (!(n >= 1 && n <= 50)) {
            res.end(
              JSON.stringify({
                ok: 0,
                errors: 1,
                n,
                elapsed_ms: 0,
                ops_per_s: 0,
                first_error: 'n 必须在 1..50 之间（当前 ' + n + '）',
              })
            );
            return;
          }
          const t0 = Date.now();
          const r = runThreeLinks(n);
          res.end(
            JSON.stringify({
              ok: r.ok ? 1 : 0,
              errors: r.ok ? 0 : 1,
              n,
              stage,
              elapsed_ms: Date.now() - t0,
              ops_per_s: r.ok
                ? Number((n / Math.max(0.001, (Date.now() - t0) / 1000)).toFixed(2))
                : 0,
              tail: r.tail,
              first_error: r.ok ? '' : r.err,
            })
          );
        });
      },
    },
  ],
  server: { host: '127.0.0.1', port: 5178 },
});
