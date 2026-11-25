import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AppShell } from '@astryxdesign/core/AppShell';
import { Card } from '@astryxdesign/core/Card';
import { Badge } from '@astryxdesign/core/Badge';
import { Button } from '@astryxdesign/core/Button';

// ────────────────────────────────────────────────────────────────
// 设计说明（Astryx 规范：语义令牌、不硬编码色值、主从结构、受控组件）
//  · 颜色只用 var(--color-*) / 文本语义类
//  · 布局：AppShell(root) → 顶部摘要 → 主从两栏（左：流程阶段；右：详情面板）
//  · 数据：全部来自 /api/state（后端现算），不写死任何数字
//  · 联动：每个阶段卡片上的「实跑 N 次」POST /api/run，真的执行该模块
// ────────────────────────────────────────────────────────────────

const fmt = (n) => (n === null || n === undefined ? '—' : Number(n).toLocaleString('en-US'));
const pct = (a, b) => (b ? ((100 * a) / b).toFixed(1) + '%' : '—');

function Kpi({ label, value, hint, variant }) {
  return (
    <Card padding={1.5} variant={variant || 'default'}>
      <div style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>{hint}</div>
    </Card>
  );
}

/**
 * 全流程 7 步（R1239）。
 *
 * 数据来自 `/api/state` 的 `pipeline.steps`：流程骨架由后端给出，
 * 数字全部来自仓库 `flow/*.json` —— 所以"后续只更新测试数据"就能自动反映。
 *
 * 交互：点一行展开 input / output / detail / source；再次点击收起。
 */
function PipelineSteps({ pipeline }) {
  const [openId, setOpenId] = useState(null);
  const steps = (pipeline && pipeline.steps) || [];
  if (!steps.length) return null;

  return (
    <Card padding={2} style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10,
                    marginBottom: 10, flexWrap: 'wrap' }}>
        <strong style={{ fontSize: 14 }}>全流程 7 步</strong>
        <Badge
          label={`通过 ${pipeline.okCount} / 失败 ${pipeline.failCount} / 共 ${pipeline.total}`}
          variant={pipeline.failCount ? 'yellow' : 'green'}
        />
        <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
          点任意一步展开：它吃什么、产出什么、数字来自哪个文件
        </span>
      </div>

      {steps.map((st) => {
        const open = openId === st.id;
        return (
          <div key={st.id}
               style={{ borderTop: '1px solid var(--color-border)', padding: '8px 0' }}>
            <div
              role="button"
              tabIndex={0}
              onClick={() => setOpenId(open ? null : st.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ')
                  setOpenId(open ? null : st.id);
              }}
              style={{ display: 'flex', alignItems: 'center', gap: 10,
                       cursor: 'pointer' }}
            >
              <span style={{ fontFamily: 'var(--font-family-code)', fontSize: 11,
                             width: 20, color: 'var(--color-text-secondary)' }}>
                {st.seq}
              </span>
              <span style={{ width: 8, height: 8, borderRadius: '50%',
                background: st.ok === true ? 'var(--color-text-success)'
                  : st.ok === false ? 'var(--color-text-error)'
                  : 'var(--color-text-secondary)' }} />
              <strong style={{ fontSize: 13 }}>{st.name}</strong>
              <span style={{ fontFamily: 'var(--font-family-code)', fontSize: 11,
                             color: 'var(--color-text-secondary)' }}>
                {st.module}
              </span>
              <span style={{ flex: 1 }} />
              <span style={{ fontFamily: 'var(--font-family-code)', fontSize: 12,
                             fontWeight: 600 }}>{st.metric}</span>
              <Badge label={open ? '收起' : '展开'} variant="default" />
            </div>

            {open ? (
              <div style={{ marginTop: 8, marginLeft: 30, fontSize: 12,
                            lineHeight: 1.75,
                            color: 'var(--color-text-secondary)' }}>
                <div><b>输入</b>：{st.input}</div>
                <div><b>产出</b>：{st.output}</div>
                {(st.detail || []).map((d, i) => <div key={i}>· {d}</div>)}
                <div style={{ fontFamily: 'var(--font-family-code)', fontSize: 10.5,
                              marginTop: 4, opacity: 0.8 }}>
                  来源：{st.source}
                </div>
              </div>
            ) : null}
          </div>
        );
      })}
    </Card>
  );
}

function StageCard({ s, active, onSelect }) {
  const sem = s.semantic;
  const semPct = sem && sem.n ? (100 * sem.ok) / sem.n : null;
  return (
    <Card
      padding={1.5}
      variant={active ? 'blue' : 'default'}
      elevation={active ? 'low' : 'none'}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => onSelect(s)}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(s)}
        style={{ cursor: 'pointer' }}
      >
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <strong style={{ fontSize: 14 }}>{s.stage}</strong>
          {s.parallel ? <Badge label={`并行 ${s.parallel}`} variant="info" /> : null}
          {s.errors ? <Badge label={`错误 ${s.errors}`} variant="error" /> : <Badge label="0 错误" variant="success" />}
          {semPct !== null ? (
            <Badge
              label={`语义 ${semPct.toFixed(1)}%`}
              variant={semPct >= 99 ? 'success' : 'warning'}
            />
          ) : null}
        </div>
        <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 2 }}>
          {s.entry}
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 1fr',
            gap: 6,
            marginTop: 8,
            fontVariantNumeric: 'tabular-nums',
            fontSize: 12,
          }}
        >
          <div>实跑<br /><strong>{fmt(s.done)}</strong></div>
          <div>吞吐<br /><strong>{fmt(s.ops_per_s)}/s</strong></div>
          <div>耗时<br /><strong>{s.elapsed_s}s</strong></div>
        </div>
      </div>
    </Card>
  );
}

function Detail({ s, onRun, running, result }) {
  if (!s) {
    return (
      <Card padding={2} variant="muted">
        <div style={{ fontSize: 13 }}>左侧选择一个阶段，这里显示它的真实入口、边界命中与<b>现场实跑</b>结果。</div>
      </Card>
    );
  }
  const sem = s.semantic;
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <Card padding={2}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>{s.stage}</div>
            <div style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>{s.entry}</div>
          </div>
          <Button
            label={running ? '执行中…' : '实跑 500 次'}
            variant="primary"
            isLoading={running}
            onClick={() => onRun(s, 500)}
          />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, marginTop: 12, fontSize: 12 }}>
          <div>配额<br /><strong>{fmt(s.quota)}</strong></div>
          <div>实跑<br /><strong>{fmt(s.done)}</strong></div>
          <div>吞吐<br /><strong>{fmt(s.ops_per_s)}/s</strong></div>
          <div>耗时<br /><strong>{s.elapsed_s}s</strong></div>
        </div>
        {sem ? (
          <div style={{ marginTop: 8, fontSize: 12 }}>
            语义成功 <strong>{fmt(sem.ok)}/{fmt(sem.n)}</strong>（{pct(sem.ok, sem.n)}）
          </div>
        ) : (
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--color-text-secondary)' }}>
            该阶段没有语义计数（只有“未抛异常”）。
          </div>
        )}
      </Card>

      <Card padding={2}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>边界命中（闭式精确计数）</div>
        {Object.keys(s.boundary || {}).length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>本次运行未记录边界命中。</div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
            {Object.entries(s.boundary).map(([k, v]) => (
              <li key={k}>
                {k}: <strong>{fmt(v)}</strong>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {result ? (
        <Card padding={2} variant={result.errors ? 'red' : 'green'}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
            现场实跑结果（刚刚真的调用了这个模块）
          </div>
          <div style={{ fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>
            执行 {fmt(result.n)} 次 · 成功 {fmt(result.ok)} · 错误 {fmt(result.errors)} ·{' '}
            {result.elapsed_ms} ms · {fmt(result.ops_per_s)}/s
          </div>
          {result.first_error ? (
            <div style={{ fontSize: 11, marginTop: 6, color: 'var(--color-text-danger)' }}>{result.first_error}</div>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}

export default function App() {
  const [state, setState] = useState(null);
  const [err, setErr] = useState('');
  const [sel, setSel] = useState(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch('/api/state', { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      setState(j);
      setErr('');
      setSel((cur) => cur || (j.stages && j.stages[0]) || null);
    } catch (e) {
      setErr('拿不到 /api/state：' + e.message + '（先启动 python scripts/dash_api.py）');
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const onRun = useCallback(async (s, n) => {
    setRunning(true);
    setResult(null);
    try {
      const r = await fetch(`/api/run?stage=${encodeURIComponent(s.stage)}&n=${n}`, { method: 'POST' });
      setResult(await r.json());
    } catch (e) {
      setResult({ errors: 1, ok: 0, n, elapsed_ms: 0, ops_per_s: 0, first_error: e.message });
    } finally {
      setRunning(false);
    }
  }, []);

  const run = state?.run || {};
  const modules = state?.modules || {};
  const head = useMemo(
    () => (
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, padding: '10px 16px', flexWrap: 'wrap' }}>
        <strong style={{ fontSize: 15 }}>Aethera 全流程控制台</strong>
        <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
          Astryx · Neutral 主题 · 数据每 15s 从 /api/state 现算
        </span>
        {state?.generated_at ? (
          <span style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>读数时间 {state.generated_at}</span>
        ) : null}
        <span style={{ flex: 1 }} />
        <Button label="刷新" variant="secondary" size="sm" onClick={load} />
      </div>
    ),
    [state, load],
  );

  return (
    <AppShell topNav={head} contentPadding={2} height="auto" variant="elevated">
      {err ? (
        <Card padding={2} variant="red" style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 13 }}>{err}</div>
        </Card>
      ) : null}

      <PipelineSteps pipeline={state?.pipeline} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 10, marginBottom: 16 }}>
        <Kpi label="实跑总量" value={fmt(run.executed)} hint={`目标 ${fmt(run.target)}`} />
        <Kpi label="墙钟" value={`${run.wall_s || '—'}s`} hint={state?.run?.parts ? `每阶段 ${run.parts} 片` : '分片/单机'} />
        <Kpi
          label="阶段参与"
          value={`${run.stages_participated || 0}/${run.stages_total || 0}`}
          hint="有真实入口且真跑"
          variant={run.stages_participated === run.stages_total ? 'green' : 'red'}
        />
        <Kpi label="错误 / 失配" value={`${fmt(run.errors)} / ${fmt(run.mismatches)}`} hint="抛异常 / 完整性" />
        <Kpi
          label="模块参与"
          value={`${fmt(modules.loaded)}/${fmt(modules.total)}`}
          hint="sys.modules 实测，非“全部模块”"
          variant="yellow"
        />
        <Kpi
          label="指令真实发射"
          value={`${run.instruction_coverage_pct ?? '—'}%`}
          hint="分子分母仅 UIR→UC 发射"
          variant="orange"
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.15fr) minmax(0,1fr)', gap: 16 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, margin: '4px 0 8px' }}>
            全流程阶段（点击查看详情 · 详情里可现场实跑）
          </div>
          <div style={{ display: 'grid', gap: 8 }}>
            {(state?.stages || []).map((s) => (
              <StageCard key={s.stage} s={s} active={sel?.stage === s.stage} onSelect={setSel} />
            ))}
            {!state?.stages?.length ? (
              <Card padding={2} variant="muted">
                <div style={{ fontSize: 12 }}>还没有读数：先跑一次全流程，或启动 scripts/dash_api.py。</div>
              </Card>
            ) : null}
          </div>
        </div>
        <Detail s={sel} onRun={onRun} running={running} result={result} />
      </div>

      <Card padding={2} variant="muted" style={{ marginTop: 16 }}>
        <div style={{ fontSize: 12, lineHeight: 1.8, color: 'var(--color-text-secondary)' }}>
          <b>口径</b>：这里的每个数字都来自 <code>.brain/*.json</code>（不是前端常量）；
          「实跑 500 次」会真的在 Python 侧 new 出对应模块并调用其入口函数，返回耗时与错误数。
          「模块参与」是运行期 <code>sys.modules</code> 实测，分母为 <code>src/**/*.py</code>。
        </div>
      </Card>
    </AppShell>
  );
}
