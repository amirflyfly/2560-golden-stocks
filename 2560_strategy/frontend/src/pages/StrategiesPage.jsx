import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { canWrite, writeDisabledReason } from '../auth/permissions';
import { DataTable, MetricCard, PageHeader, SectionCard, StatusBadge } from '../components/common';

function percent(value) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function benchmarkQualityLabel(benchmark) {
  if (!benchmark) return '-';
  const source = benchmark.source || benchmark.code || '-';
  const quality = benchmark.data_quality || 'unknown';
  return benchmark.fallback_used ? `${quality} / ${source} / fallback` : `${quality} / ${source}`;
}

function todayMinus(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

export function StrategiesPage({ authz, pagePayload = {} }) {
  const [items, setItems] = useState([]);
  const [selectedCode, setSelectedCode] = useState(pagePayload.strategy_code || '2560');
  const [form, setForm] = useState({
    start_date: todayMinus(90),
    end_date: new Date().toISOString().slice(0, 10),
    holding_days: 5,
    max_positions_per_day: 3,
    trade_limit: 20,
    fee_bps: 0,
    slippage_bps: 0,
    limit_up_down_guard: true,
    benchmark_code: '000300',
    benchmark_return_pct: 0,
  });
  const [backtest, setBacktest] = useState(null);
  const [historyDetail, setHistoryDetail] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const mayWrite = canWrite(authz);
  const disabledReason = writeDisabledReason(authz);

  useEffect(() => {
    api.strategies({ page: 1, page_size: 20 })
      .then((data) => {
        setItems(data.items || []);
        if (pagePayload.strategy_code && data.items?.some((item) => item.code === pagePayload.strategy_code)) {
          setSelectedCode(pagePayload.strategy_code);
        } else if (data.items?.[0]?.code) {
          setSelectedCode(data.items[0].code);
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [pagePayload.strategy_code]);

  useEffect(() => {
    if (!pagePayload.strategy_code) return;
    setSelectedCode(pagePayload.strategy_code);
  }, [pagePayload.strategy_code]);

  useEffect(() => {
    if (!selectedCode) return;
    api.strategyBacktests(selectedCode, { page: 1, page_size: 5 })
      .then((data) => {
        setHistory(data.items || []);
        setHistoryDetail(null);
      })
      .catch(() => {
        setHistory([]);
        setHistoryDetail(null);
      });
  }, [selectedCode]);

  function buildBacktestPayload(extra = {}) {
    return {
      start_date: form.start_date,
      end_date: form.end_date,
      holding_days: Number(form.holding_days),
      max_positions_per_day: Number(form.max_positions_per_day),
      trade_limit: Number(form.trade_limit),
      fee_bps: Number(form.fee_bps),
      slippage_bps: Number(form.slippage_bps),
      limit_up_down_guard: Boolean(form.limit_up_down_guard),
      benchmark_code: form.benchmark_code,
      benchmark_return_pct: Number(form.benchmark_return_pct),
      include_trades: true,
      ...extra,
    };
  }

  async function runBacktest(event) {
    event.preventDefault();
    if (!mayWrite) {
      setError(disabledReason);
      return;
    }
    setError('');
    setMessage('');
    setRunning(true);
    try {
      const data = await api.strategyBacktest(selectedCode, buildBacktestPayload());
      setBacktest(data);
      setMessage('回测已完成，建议结合行情源质量、样本数量和成本假设复核结论。');
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  async function runParameterComparison() {
    if (!mayWrite) {
      setError(disabledReason);
      return;
    }
    setError('');
    setMessage('');
    setRunning(true);
    try {
      const baseHoldingDays = Number(form.holding_days);
      const data = await api.strategyBacktest(selectedCode, buildBacktestPayload({
        param_groups: [
          { label: '短持有', holding_days: Math.max(1, baseHoldingDays - 2), max_positions_per_day: Number(form.max_positions_per_day) },
          { label: '当前参数', holding_days: baseHoldingDays, max_positions_per_day: Number(form.max_positions_per_day) },
          { label: '长持有', holding_days: Math.min(60, baseHoldingDays + 5), max_positions_per_day: Number(form.max_positions_per_day) },
        ],
      }));
      setBacktest(data);
      setMessage('参数组对比已完成。');
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  async function viewBacktestDetail(item) {
    if (!item?.id) return;
    setError('');
    try {
      const data = await api.strategyBacktestDetail(selectedCode, item.id);
      setHistoryDetail(data);
    } catch (err) {
      setError(err.message);
    }
  }

  const selectedStrategy = useMemo(() => items.find((item) => item.code === selectedCode) || items[0], [items, selectedCode]);
  const summary = backtest?.summary || {};
  const explanation = backtest?.explanation || {};
  const trades = summary.trade_page?.items || [];
  const curve = summary.equity_curve || [];
  const benchmarkCurve = summary.benchmark?.curve || [];
  const parameterComparison = backtest?.parameter_comparison || [];
  const executionConstraints = summary.execution_constraints || {};

  return (
    <main className="page">
      <PageHeader
        eyebrow="Strategy"
        title="策略管理"
        description="策略页不只列清单，还要能直接运行回测、查看风险解释，并把验证结果带回日常扫描。"
        badges={selectedStrategy ? (
          <>
            <StatusBadge tone={selectedStrategy.enabled ? 'success' : 'warning'}>{selectedStrategy.enabled ? '已启用' : '未启用'}</StatusBadge>
            <StatusBadge tone="info">{selectedStrategy.code}</StatusBadge>
          </>
        ) : null}
      />

      {error ? <div className="alert">{error}</div> : null}
      {message ? <div className="alert success">{message}</div> : null}
      {!mayWrite ? <div className="alert warning">{disabledReason}</div> : null}
      {loading ? <div className="card loading-card">正在加载策略...</div> : null}

      <section className="strategy-grid">
        {items.map((item) => (
          <button
            type="button"
            className={item.code === selectedCode ? 'strategy-card active' : 'strategy-card'}
            key={item.code}
            onClick={() => setSelectedCode(item.code)}
          >
            <div className="section-title-row">
              <strong>{item.name}</strong>
              <StatusBadge tone={item.enabled ? 'success' : 'warning'}>{item.enabled ? '启用' : '停用'}</StatusBadge>
            </div>
            <span>{item.code}</span>
            <p className="muted">{item.description || item.category}</p>
          </button>
        ))}
      </section>

      <section className="dashboard-layout section-gap">
        <article className="panel-card">
          <h2>运行回测</h2>
          <form className="backtest-form" onSubmit={runBacktest}>
            <label className="form-field">
              策略
              <select className="scan-select" value={selectedCode} onChange={(event) => setSelectedCode(event.target.value)}>
                {items.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}
              </select>
            </label>
            <label className="form-field">
              开始日期
              <input className="scan-input" type="date" value={form.start_date} onChange={(event) => setForm((prev) => ({ ...prev, start_date: event.target.value }))} />
            </label>
            <label className="form-field">
              结束日期
              <input className="scan-input" type="date" value={form.end_date} onChange={(event) => setForm((prev) => ({ ...prev, end_date: event.target.value }))} />
            </label>
            <label className="form-field">
              持有天数
              <input className="scan-input" type="number" min="1" max="60" value={form.holding_days} onChange={(event) => setForm((prev) => ({ ...prev, holding_days: event.target.value }))} />
            </label>
            <label className="form-field">
              每日最大持仓
              <input className="scan-input" type="number" min="1" max="20" value={form.max_positions_per_day} onChange={(event) => setForm((prev) => ({ ...prev, max_positions_per_day: event.target.value }))} />
            </label>
            <label className="form-field">
              交易明细上限
              <input className="scan-input" type="number" min="1" max="500" value={form.trade_limit} onChange={(event) => setForm((prev) => ({ ...prev, trade_limit: event.target.value }))} />
            </label>
            <label className="form-field">
              手续费 bps
              <input className="scan-input" type="number" min="0" max="200" step="0.1" value={form.fee_bps} onChange={(event) => setForm((prev) => ({ ...prev, fee_bps: event.target.value }))} />
            </label>
            <label className="form-field">
              滑点 bps
              <input className="scan-input" type="number" min="0" max="500" step="0.1" value={form.slippage_bps} onChange={(event) => setForm((prev) => ({ ...prev, slippage_bps: event.target.value }))} />
            </label>
            <label className="form-field">
              基准代码
              <input className="scan-input" value={form.benchmark_code} onChange={(event) => setForm((prev) => ({ ...prev, benchmark_code: event.target.value }))} />
            </label>
            <label className="form-field">
              基准收益
              <input className="scan-input" type="number" min="-1" max="1" step="0.01" value={form.benchmark_return_pct} onChange={(event) => setForm((prev) => ({ ...prev, benchmark_return_pct: event.target.value }))} />
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={form.limit_up_down_guard} onChange={(event) => setForm((prev) => ({ ...prev, limit_up_down_guard: event.target.checked }))} />
              涨跌停约束提示
            </label>
            <button type="submit" disabled={running || !selectedCode || !mayWrite} title={disabledReason}>{running ? '回测中...' : '运行回测'}</button>
            <button type="button" className="btn-secondary" onClick={runParameterComparison} disabled={running || !selectedCode || !mayWrite} title={disabledReason}>参数组对比</button>
          </form>
        </article>

        <article className="panel-card">
          <h2>解释结论</h2>
          {backtest ? (
            <div className="scan-summary">
              <div className="summary-row"><span>结论</span><StatusBadge status={explanation.verdict}>{explanation.verdict}</StatusBadge></div>
              <div className="summary-row"><span>风险等级</span><StatusBadge status={summary.risk_level}>{summary.risk_level}</StatusBadge></div>
              <div className="summary-row"><span>解释分</span><strong>{explanation.score ?? '-'}</strong></div>
              <div className="summary-row"><span>置信度</span><strong>{explanation.confidence ?? '-'}</strong></div>
              <div className="summary-row"><span>行动建议</span><strong>{explanation.action_suggestion || '-'}</strong></div>
            </div>
          ) : (
            <div className="empty">选择日期区间后运行一次回测，系统会返回收益、回撤、胜率和解释建议。</div>
          )}
        </article>
      </section>

      {backtest ? (
        <>
          <section className="grid section-gap">
            <MetricCard label="交易次数" value={summary.total_trades} hint="样本量越小，置信度越低" />
            <MetricCard
              label="约束剔除"
              value={executionConstraints.excluded_count ?? 0}
              hint={executionConstraints.enabled ? '已启用涨跌停/停牌约束' : '仅剔除显式无效价格'}
              danger={Number(executionConstraints.excluded_count || 0) > 0}
            />
            <MetricCard label="胜率" value={percent(summary.win_rate)} />
            <MetricCard label="累计收益" value={percent(summary.total_return)} />
            <MetricCard label="估算净收益" value={percent(summary.net_total_return)} />
            <MetricCard label="基准收益" value={percent(summary.benchmark?.total_return)} />
            <MetricCard
              label="基准数据"
              value={benchmarkQualityLabel(summary.benchmark)}
              danger={summary.benchmark?.fallback_used || summary.benchmark?.data_quality === 'mock'}
            />
            <MetricCard label="超额收益" value={percent(summary.benchmark?.excess_return)} danger={Number(summary.benchmark?.excess_return || 0) < 0} />
            <MetricCard label="最大回撤" value={percent(summary.max_drawdown)} danger={Number(summary.max_drawdown) >= 0.12} />
            <MetricCard label="夏普比率" value={summary.sharpe_ratio ?? '-'} />
            <MetricCard label="盈亏比" value={summary.profit_factor ?? '-'} />
          </section>

          {parameterComparison.length ? (
            <SectionCard title="参数组对比">
              <DataTable
                className="backtest-history-table"
                columns={[
                  { label: '参数组', render: (item) => <strong>{item.label}</strong> },
                  { label: '持有', render: (item) => item.params?.holding_days ?? '-' },
                  { label: '胜率', render: (item) => percent(item.summary?.win_rate) },
                  { label: '净收益', render: (item) => percent(item.summary?.net_total_return) },
                  { label: '超额', render: (item) => percent(item.summary?.excess_return) },
                ]}
                rows={parameterComparison}
                getKey={(item) => item.label}
                emptyText="暂无参数组对比。"
              />
            </SectionCard>
          ) : null}

          <SectionCard title="收益曲线">
            <div className="equity-curve" role="img" aria-label="回测收益曲线">
              {curve.map((point, index) => {
                const top = Math.max(0, Math.min(100, 100 - (Number(point.equity || 1) * 50)));
                return (
                  <span
                    className="equity-point"
                    key={`${point.step}-${index}`}
                    style={{ left: `${curve.length <= 1 ? 0 : (index / (curve.length - 1)) * 100}%`, top: `${top}%` }}
                    title={`step ${point.step}: ${Number(point.return_pct || 0).toFixed(4)}`}
                  />
                );
              })}
              {benchmarkCurve.map((point, index) => {
                const top = Math.max(0, Math.min(100, 100 - (Number(point.equity || 1) * 50)));
                return (
                  <span
                    className="equity-point benchmark-point"
                    key={`benchmark-${point.step}-${index}`}
                    style={{ left: `${benchmarkCurve.length <= 1 ? 0 : (index / (benchmarkCurve.length - 1)) * 100}%`, top: `${top}%` }}
                    title={`benchmark ${point.step}: ${Number(point.return_pct || 0).toFixed(4)}`}
                  />
                );
              })}
              {!curve.length ? <div className="empty">本次回测未返回收益曲线。</div> : null}
            </div>
          </SectionCard>

          <SectionCard title="交易样本">
            <DataTable
              className="backtest-table"
              columns={[
                { label: '股票', render: (trade) => <strong>{trade.code} {trade.name}</strong> },
                { label: '信号', render: (trade) => trade.signal || '-' },
                { label: '入场', render: (trade) => trade.entry_date || '-' },
                { label: '出场', render: (trade) => trade.exit_date || '-' },
                { label: '收益', render: (trade) => percent(trade.return_pct) },
                { label: '风险分', render: (trade) => trade.risk_score ?? '-' },
              ]}
              rows={trades}
              getKey={(trade, index) => `${trade.code}-${index}`}
              emptyText="本次回测未返回交易明细。"
            />
          </SectionCard>
        </>
      ) : null}

      <SectionCard title="历史回测">
        <DataTable
          className="backtest-history-table"
          columns={[
            { label: '区间', render: (item) => `${item.start_date || '-'} 至 ${item.end_date || '-'}` },
            { label: '交易', render: (item) => item.summary?.total_trades ?? item.total_trades ?? '-' },
            { label: '胜率', render: (item) => percent(item.summary?.win_rate ?? item.win_rate) },
            { label: '收益', render: (item) => percent(item.summary?.total_return ?? item.total_return) },
            { label: '回撤', render: (item) => percent(item.summary?.max_drawdown ?? item.max_drawdown) },
            { label: '详情', render: (item) => <button type="button" className="btn-secondary" onClick={() => viewBacktestDetail(item)}>查看</button> },
          ]}
          rows={history}
          getKey={(item, index) => item.id || index}
          emptyText="暂无历史回测记录。"
        />
      </SectionCard>

      {historyDetail ? (
        <SectionCard title="历史回测详情">
          <div className="scan-summary">
            <div className="summary-row"><span>区间</span><strong>{historyDetail.item?.start_date || '-'} 至 {historyDetail.item?.end_date || '-'}</strong></div>
            <div className="summary-row"><span>交易次数</span><strong>{historyDetail.item?.summary?.total_trades ?? '-'}</strong></div>
            <div className="summary-row"><span>胜率</span><strong>{percent(historyDetail.item?.summary?.win_rate)}</strong></div>
            <div className="summary-row"><span>收益</span><strong>{percent(historyDetail.item?.summary?.total_return)}</strong></div>
            <div className="summary-row"><span>风险等级</span><StatusBadge status={historyDetail.item?.explanation?.risk_level}>{historyDetail.item?.explanation?.risk_level || '-'}</StatusBadge></div>
            <div className="summary-row"><span>审计记录</span><strong>{historyDetail.audit_trail?.length || 0}</strong></div>
          </div>
        </SectionCard>
      ) : null}
    </main>
  );
}
