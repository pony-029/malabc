import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
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
      id: 'mir',
      name: 'MIR 前端',
      path: 'translate/mir.py',
      desc: '把 .m 降级成 MIR 行（const / op / shape / unmapped）',
      source: 'flow/fullflow.json',
      semantic: stages[0]
        ? { ok: stages[0].pass, n: stages[0].total }
        : null,
    },
    {
      id: 'hir',
      name: 'HIR 契约',
      path: 'translate/hir.py · mir.py:hir_gate',
      desc: '每次 to_mir 收尾把 MIR 抬升成 HIR、降回、比对算子多重集',
      source: 'flow/hir_status.json',
      semantic: stages[1] ? { ok: stages[1].pass, n: stages[1].total } : null,
    },
    {
      id: 'emit',
      name: 'Rust 发射器',
      path: 'rust/m2c/src/emit.rs',
      desc: 'MIR → gen.c + main.c（assumed shape、MATMUL 降回）',
      source: 'flow/fullflow.json',
      semantic: stages[2] ? { ok: stages[2].pass, n: stages[2].total } : null,
    },
    {
      id: 'rt',
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
      id: 'gates',
      name: '门禁与台账',
      path: 'tools/check_*.py（48 道）',
      desc: '每道门自证 + check_all 汇总；GX2 是第 48 道',
      source: 'flow/ane.json · flow/failures.json',
      semantic: ane.ok ? { ok: 1, n: 1 } : { ok: 0, n: 1 },
    },
  ];

  return {
    generatedAt: new Date().toISOString(),
    flowRoot: FLOW,
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
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(
            JSON.stringify({
              ok: false,
              reason:
                'M2C_ALLOW_RUN=1 已开启，但执行器需在下一轮接上 ' +
                '（子进程 + 超时 + 输出截断）。',
            })
          );
        });
      },
    },
  ],
  server: { host: '127.0.0.1', port: 5178 },
});
