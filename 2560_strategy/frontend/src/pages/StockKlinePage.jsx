import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { DataTable, MetricCard, SectionCard, StatusBadge } from '../components/common';

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function movingAverage(items, field, size) {
  if (items.length < size) return null;
  const slice = items.slice(-size);
  const sum = slice.reduce((total, item) => total + toNumber(item[field]), 0);
  return sum / size;
}

export function StockKlinePage({ initialSymbol = '000001', onNavigate }) {
  const [symbol, setSymbol] = useState(initialSymbol || '000001');
  const [range, setRange] = useState({ start_date: '', end_date: '' });
  const [state, setState] = useState({ loading: false, error: '', data: null, context: null });

  async function loadKline(nextSymbol = symbol, nextRange = range) {
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    try {
      const [data, context] = await Promise.all([
        api.stockKline(nextSymbol, nextRange),
        api.stockContext(nextSymbol, { limit: 20 }).catch(() => ({ history: [], total: 0 })),
      ]);
      setState({ loading: false, error: '', data, context });
    } catch (error) {
      setState({ loading: false, error: error.message, data: null, context: null });
    }
  }

  useEffect(() => {
    const nextSymbol = initialSymbol || '000001';
    setSymbol(nextSymbol);
    loadKline(nextSymbol);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSymbol]);

  const chartBars = useMemo(() => state.data?.items || [], [state.data]);
  const latest = chartBars[chartBars.length - 1] || {};
  const previous = chartBars[chartBars.length - 2] || {};
  const latestClose = toNumber(latest.close);
  const previousClose = toNumber(previous.close);
  const changePct = previousClose ? ((latestClose - previousClose) / previousClose) * 100 : 0;
  const ma5 = movingAverage(chartBars, 'close', 5);
  const ma20 = movingAverage(chartBars, 'close', 20);
  const ma25 = movingAverage(chartBars, 'close', 25);
  const maxPrice = Math.max(...chartBars.flatMap((item) => [toNumber(item.high), toNumber(item.close)]), 1);
  const minPrice = Math.min(...chartBars.flatMap((item) => [toNumber(item.low), toNumber(item.close)]), maxPrice);
  const priceSpan = Math.max(maxPrice - minPrice, 1);
  const context = state.context || {};
  const latestPick = context.latest_pick;

  return (
    <main className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Market</p>
          <h1>Stock K-line</h1>
          <p className="muted">Inspect price action together with pool status, review markers, and historical pick records.</p>
        </div>
      </div>

      <section className="toolbar" aria-label="K-line query">
        <label>
          Symbol
          <input value={symbol} onChange={(event) => setSymbol(event.target.value.trim())} placeholder="000001" />
        </label>
        <label>
          Start
          <input type="date" value={range.start_date} onChange={(event) => setRange((prev) => ({ ...prev, start_date: event.target.value }))} />
        </label>
        <label>
          End
          <input type="date" value={range.end_date} onChange={(event) => setRange((prev) => ({ ...prev, end_date: event.target.value }))} />
        </label>
        <button type="button" onClick={() => loadKline(symbol)} disabled={state.loading}>Refresh</button>
      </section>

      {state.error ? <div className="alert">{state.error}</div> : null}

      <section className="grid">
        <MetricCard label="Latest close" value={latestClose || '-'} badge={<span className={changePct >= 0 ? 'data-badge danger small-text' : 'data-badge success small-text'}>{changePct.toFixed(2)}%</span>} />
        <MetricCard label="Volume" value={latest.volume || '-'} />
        <MetricCard label="MA5 / MA20" value={`${ma5 ? ma5.toFixed(2) : '-'} / ${ma20 ? ma20.toFixed(2) : '-'}`} />
        <MetricCard label="MA25" value={ma25 ? ma25.toFixed(2) : '-'} />
        <MetricCard label="Data source" value={state.data?.market_data_source || state.data?.provider || '-'} hint={`Updated ${state.data?.updated_at || '-'}`} />
        <MetricCard label="Pool marker" value={context.in_pool ? 'In pool' : 'Not in pool'} badge={latestPick ? <StatusBadge status={latestPick.status}>{latestPick.status}</StatusBadge> : null} />
      </section>

      <section className="card chart-card section-gap">
        <div className="chart-meta">
          <strong>{state.data?.symbol || symbol}</strong>
          <span>{state.data?.start_date || '-'} to {state.data?.end_date || '-'}</span>
          <span>{chartBars.length} bars</span>
          <span>quality: {state.data?.data_quality || 'unknown'}</span>
        </div>
        <div className="mini-kline" role="img" aria-label={`${symbol} daily K-line chart`}>
          {chartBars.map((item) => {
            const open = toNumber(item.open);
            const close = toNumber(item.close);
            const high = toNumber(item.high);
            const low = toNumber(item.low);
            const top = ((maxPrice - high) / priceSpan) * 100;
            const bottom = ((low - minPrice) / priceSpan) * 100;
            const bodyTop = ((maxPrice - Math.max(open, close)) / priceSpan) * 100;
            const bodyHeight = Math.max((Math.abs(close - open) / priceSpan) * 100, 2);
            const up = close >= open;
            return (
              <div className="candle" key={item.trade_date} title={`${item.trade_date} O:${open} H:${high} L:${low} C:${close}`}>
                <span className="wick" style={{ top: `${top}%`, bottom: `${bottom}%` }} />
                <span className={up ? 'body up' : 'body down'} style={{ top: `${bodyTop}%`, height: `${bodyHeight}%` }} />
              </div>
            );
          })}
        </div>
      </section>

      <SectionCard title="Pool and review context">
        {latestPick ? (
          <div className="scan-summary">
            <div className="summary-row"><span>Latest pick</span><strong>{latestPick.trade_date} / {latestPick.source}</strong></div>
            <div className="summary-row"><span>Strategy</span><strong>{latestPick.strategy_code || '-'}</strong></div>
            <div className="summary-row"><span>Review</span><strong>{latestPick.review_comment || '-'}</strong></div>
            <div className="summary-row"><span>Deal</span><strong>{latestPick.deal_status || '-'}</strong></div>
            <div className="summary-row"><span>Return</span><strong>{latestPick.return_pct ?? '-'}</strong></div>
          </div>
        ) : (
          <div className="empty">No active pool record for this symbol.</div>
        )}
      </SectionCard>

      <SectionCard title="Historical pool records" actions={<button type="button" className="btn-secondary" onClick={() => onNavigate?.('picks', { symbol })}>Open pool</button>}>
        <DataTable
          className="compact-table"
          columns={[
            { label: 'Date', render: (item) => item.trade_date || '-' },
            { label: 'Source', render: (item) => item.source || '-' },
            { label: 'Strategy', render: (item) => item.strategy_code || '-' },
            { label: 'Status', render: (item) => <StatusBadge status={item.status}>{item.status}</StatusBadge> },
            { label: 'Deal', render: (item) => item.deal_status || '-' },
            { label: 'Return', render: (item) => item.return_pct ?? '-' },
          ]}
          rows={context.history || []}
          getKey={(item) => item.id}
          emptyText="No historical pick records."
        />
      </SectionCard>
    </main>
  );
}
