import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { DataTable, MetricCard, SectionCard, StatusBadge } from '../components/common';

const BAR_INTERVAL_OPTIONS = [
  ['1d', '日线'],
  ['15m', '15分钟'],
  ['30m', '30分钟'],
  ['5m', '5分钟'],
  ['1h', '60分钟'],
];

const BAR_INTERVAL_LABELS = Object.fromEntries(BAR_INTERVAL_OPTIONS);
const SECURITY_TYPE_LABELS = {
  stock: '股票',
  etf: 'ETF',
  index: '指数/板块',
  convertible_bond: '可转债',
  bond: '债券',
  fund: '基金',
  b_share: 'B股',
};
const ADJUST_LABELS = {
  qfq: '前复权',
  hfq: '后复权',
  none: '不复权',
};

function uniqueValues(values) {
  return [...new Set((values || []).map((value) => String(value || '').trim()).filter(Boolean))];
}

function joinValues(values, fallback = '-') {
  const list = uniqueValues(values);
  return list.length ? list.join(', ') : fallback;
}

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

function movingAveragePoints(items, field, size, minPrice, priceSpan) {
  if (items.length < size) return '';
  return items
    .map((item, index) => {
      if (index < size - 1) return null;
      const slice = items.slice(index - size + 1, index + 1);
      const average = slice.reduce((total, current) => total + toNumber(current[field]), 0) / size;
      const x = items.length <= 1 ? 0 : (index / (items.length - 1)) * 100;
      const y = 100 - ((average - minPrice) / priceSpan) * 100;
      return `${x},${Math.max(0, Math.min(100, y))}`;
    })
    .filter(Boolean)
    .join(' ');
}

function paperOrderDate(item) {
  return String(item?.created_at || item?.updated_at || '').slice(0, 10);
}

function formatPrice(value) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return Number(value).toFixed(2);
}

function formatVolume(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '-';
  if (Math.abs(numeric) >= 100000000) return `${(numeric / 100000000).toFixed(2)} 亿`;
  if (Math.abs(numeric) >= 10000) return `${(numeric / 10000).toFixed(2)} 万`;
  return numeric.toLocaleString('zh-CN');
}

function barDate(item) {
  return item?.trade_time || item?.trade_date || item?.date || item?.datetime || '-';
}

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== '');
}

function priceLineY(value, maxPrice, priceSpan) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  return Math.max(0, Math.min(100, ((maxPrice - numeric) / priceSpan) * 100));
}

function dateLineX(date, bars) {
  if (!date || !bars.length) return null;
  const normalized = String(date).slice(0, 10);
  const index = bars.findIndex((item) => String(barDate(item)).slice(0, 10) === normalized);
  if (index < 0) return null;
  return bars.length <= 1 ? 50 : (index / (bars.length - 1)) * 100;
}

function normalizeLimitUpReturnOverlays(data, context) {
  const sources = [
    data?.overlays?.limit_up_return,
    data?.overlays?.LIMIT_UP_RETURN,
    data?.indicators?.limit_up_return,
    data?.indicators?.LIMIT_UP_RETURN,
    context?.latest_pick?.indicators?.limit_up_return,
    context?.latest_pick?.indicators?.LIMIT_UP_RETURN,
    context?.latest_pick?.limit_up_return,
  ].filter(Boolean);
  const source = Object.assign({}, ...sources);
  return {
    anchorDate: firstValue(source.anchor_date, source.anchor_day),
    supportPrice: firstValue(source.support_price, source.support_level),
    triggerPrice: firstValue(source.trigger_price, source.breakout_price),
    stopLossPrice: firstValue(source.stop_loss_price, source.stop_price),
    signalSubtype: firstValue(source.signal_subtype, source.state),
  };
}

function hasLimitUpReturnOverlay(overlay) {
  return Object.values(overlay).some((value) => value !== undefined && value !== null && value !== '');
}

function barChangePct(items, index) {
  const close = toNumber(items[index]?.close);
  const previousClose = toNumber(items[index - 1]?.close);
  if (!previousClose) return null;
  return ((close - previousClose) / previousClose) * 100;
}

function stockSyncStatus(data, bars, loading) {
  if (loading) return '加载中';
  if (!bars.length) return '暂无数据';
  return data?.provider === 'local' ? '本地已同步' : '已拉取缓存';
}

export function StockKlinePage({ initialSymbol = '000001', pagePayload = {}, onNavigate }) {
  const initialInterval = pagePayload.interval || '1d';
  const [symbol, setSymbol] = useState(initialSymbol || '000001');
  const [range, setRange] = useState({ start_date: '', end_date: '' });
  const [queryOptions, setQueryOptions] = useState({ interval: initialInterval, adjust: initialInterval === '1d' ? 'qfq' : 'none' });
  const [barWindow, setBarWindow] = useState('120');
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const [state, setState] = useState({ loading: false, error: '', data: null, context: null, stockMeta: null });

  async function loadKline(nextSymbol = symbol, nextRange = range, nextOptions = queryOptions) {
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    try {
      const adjust = nextOptions.interval === '1d' ? nextOptions.adjust : 'none';
      const [data, context, stockList] = await Promise.all([
        api.stockKline(nextSymbol, { ...nextRange, interval: nextOptions.interval, adjust }),
        api.stockContext(nextSymbol, { limit: 20 }).catch(() => ({ history: [], total: 0 })),
        api.stocks({ keyword: nextSymbol, limit: 20 }).catch(() => ({ items: [] })),
      ]);
      const stockMeta = (stockList.items || []).find((item) => item.symbol === nextSymbol) || stockList.items?.[0] || null;
      setState({ loading: false, error: '', data, context, stockMeta });
    } catch (error) {
      setState({ loading: false, error: error.message, data: null, context: null, stockMeta: null });
    }
  }

  useEffect(() => {
    const nextSymbol = initialSymbol || '000001';
    const nextInterval = pagePayload.interval || queryOptions.interval;
    const nextOptions = { interval: nextInterval, adjust: nextInterval === '1d' ? queryOptions.adjust : 'none' };
    setSymbol(nextSymbol);
    setQueryOptions(nextOptions);
    loadKline(nextSymbol, range, nextOptions);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSymbol, pagePayload.interval]);

  const rawBars = useMemo(() => state.data?.items || [], [state.data]);
  const chartBars = useMemo(() => {
    if (barWindow === 'all') return rawBars;
    return rawBars.slice(-Number(barWindow || 120));
  }, [rawBars, barWindow]);
  const latest = chartBars[chartBars.length - 1] || {};
  const previous = chartBars[chartBars.length - 2] || {};
  const latestClose = toNumber(latest.close);
  const previousClose = toNumber(previous.close);
  const changePct = previousClose ? ((latestClose - previousClose) / previousClose) * 100 : 0;
  const ma5 = movingAverage(chartBars, 'close', 5);
  const ma20 = movingAverage(chartBars, 'close', 20);
  const ma25 = movingAverage(chartBars, 'close', 25);
  const ma60 = movingAverage(chartBars, 'close', 60);
  const maxPrice = Math.max(...chartBars.flatMap((item) => [toNumber(item.high), toNumber(item.close)]), 1);
  const minPrice = Math.min(...chartBars.flatMap((item) => [toNumber(item.low), toNumber(item.close)]), maxPrice);
  const priceSpan = Math.max(maxPrice - minPrice, 1);
  const maxVolume = Math.max(...chartBars.map((item) => toNumber(item.volume)), 1);
  const ma5Points = movingAveragePoints(chartBars, 'close', 5, minPrice, priceSpan);
  const ma20Points = movingAveragePoints(chartBars, 'close', 20, minPrice, priceSpan);
  const ma25Points = movingAveragePoints(chartBars, 'close', 25, minPrice, priceSpan);
  const ma60Points = movingAveragePoints(chartBars, 'close', 60, minPrice, priceSpan);
  const mavol5Points = movingAveragePoints(chartBars, 'volume', 5, 0, maxVolume);
  const mavol60Points = movingAveragePoints(chartBars, 'volume', 60, 0, maxVolume);
  const context = state.context || {};
  const latestPick = context.latest_pick;
  const markerDates = new Set((context.history || []).map((item) => item.trade_date).filter(Boolean));
  const limitUpReturnOverlay = normalizeLimitUpReturnOverlays(state.data, context);
  const hasLimitUpReturnData = hasLimitUpReturnOverlay(limitUpReturnOverlay);
  const limitUpReturnLines = [
    { key: 'support', label: '支撑线', value: limitUpReturnOverlay.supportPrice },
    { key: 'trigger', label: '触发线', value: limitUpReturnOverlay.triggerPrice },
    { key: 'stop', label: '止损线', value: limitUpReturnOverlay.stopLossPrice },
  ]
    .map((line) => ({ ...line, y: priceLineY(line.value, maxPrice, priceSpan) }))
    .filter((line) => line.y != null);
  const limitUpReturnAnchorX = dateLineX(limitUpReturnOverlay.anchorDate, chartBars);
  const paperOrdersByDate = (context.paper_orders || []).reduce((acc, item) => {
    const key = paperOrderDate(item);
    if (!key) return acc;
    acc[key] = [...(acc[key] || []), item];
    return acc;
  }, {});
  const activeIndex = hoveredIndex == null ? chartBars.length - 1 : hoveredIndex;
  const activeBar = chartBars[activeIndex] || latest;
  const activeChangePct = activeIndex >= 0 ? barChangePct(chartBars, activeIndex) : null;
  const tooltipLeft = chartBars.length <= 1 ? 50 : Math.max(8, Math.min(92, (activeIndex / (chartBars.length - 1)) * 100));
  const visibleStartDate = chartBars.length ? barDate(chartBars[0]) : '-';
  const visibleEndDate = chartBars.length ? barDate(chartBars[chartBars.length - 1]) : '-';
  const stockMeta = state.stockMeta || (pagePayload.security_type ? { security_type: pagePayload.security_type } : {});
  const securityType = stockMeta.security_type || '-';
  const interval = state.data?.interval || queryOptions.interval;
  const adjust = state.data?.adjust || queryOptions.adjust;
  const latestTradeTime = latest.trade_time || latest.trade_date || '-';
  const barSources = uniqueValues(rawBars.map((item) => item.source));
  const barAdjusts = uniqueValues(rawBars.map((item) => item.adjust));
  const syncStatus = stockSyncStatus(state.data, rawBars, state.loading);

  return (
    <main className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Market</p>
          <h1>股票 K 线</h1>
          <p className="muted">结合价格走势、入池状态、复盘标记和历史候选记录复核单个标的。</p>
        </div>
      </div>

      <section className="toolbar" aria-label="K 线查询">
        <label>
          股票代码
          <input value={symbol} onChange={(event) => setSymbol(event.target.value.trim())} placeholder="000001" />
        </label>
        <label>
          K线周期
          <div className="segmented-control" aria-label="K线周期">
            {BAR_INTERVAL_OPTIONS.map(([value, label]) => (
              <button
                type="button"
                className={queryOptions.interval === value ? 'active' : ''}
                key={value}
                onClick={() => setQueryOptions((prev) => ({ ...prev, interval: value, adjust: value === '1d' ? prev.adjust : 'none' }))}
              >
                {label}
              </button>
            ))}
          </div>
        </label>
        <label>
          复权
          <select
            value={queryOptions.adjust}
            disabled={queryOptions.interval !== '1d'}
            onChange={(event) => setQueryOptions((prev) => ({ ...prev, adjust: event.target.value }))}
          >
            <option value="qfq">前复权</option>
            <option value="hfq">后复权</option>
            <option value="none">不复权</option>
          </select>
        </label>
        <label>
          开始日期
          <input type="date" value={range.start_date} onChange={(event) => setRange((prev) => ({ ...prev, start_date: event.target.value }))} />
        </label>
        <label>
          结束日期
          <input type="date" value={range.end_date} onChange={(event) => setRange((prev) => ({ ...prev, end_date: event.target.value }))} />
        </label>
        <label>
          缩放区间
          <div className="segmented-control" aria-label="K 线显示窗口">
            {[
              ['30', '30 根'],
              ['60', '60 根'],
              ['120', '120 根'],
              ['all', '全部'],
            ].map(([value, label]) => (
              <button
                type="button"
                className={barWindow === value ? 'active' : ''}
                key={value}
                onClick={() => setBarWindow(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </label>
        <button type="button" onClick={() => loadKline(symbol, range, queryOptions)} disabled={state.loading}>刷新</button>
      </section>

      {state.error ? <div className="alert">{state.error}</div> : null}

      <section className="grid">
        <MetricCard label="最新收盘" value={latestClose ? formatPrice(latestClose) : '-'} badge={<span className={changePct >= 0 ? 'data-badge danger small-text' : 'data-badge success small-text'}>{changePct.toFixed(2)}%</span>} />
        <MetricCard label="成交量" value={formatVolume(latest.volume)} />
        <MetricCard label="MA5 / MA20" value={`${ma5 ? ma5.toFixed(2) : '-'} / ${ma20 ? ma20.toFixed(2) : '-'}`} />
        <MetricCard label="MA25 / MA60" value={`${ma25 ? ma25.toFixed(2) : '-'} / ${ma60 ? ma60.toFixed(2) : '-'}`} />
        <MetricCard label="证券类型" value={SECURITY_TYPE_LABELS[securityType] || securityType} hint={`${stockMeta.exchange || '-'} / ${stockMeta.market || '-'}`} />
        <MetricCard label="周期/复权" value={`${BAR_INTERVAL_LABELS[interval] || interval} / ${ADJUST_LABELS[adjust] || adjust}`} hint={`明细复权 ${joinValues(barAdjusts, ADJUST_LABELS[adjust] || adjust)}`} />
        <MetricCard label="最新交易时间" value={latestTradeTime} hint={`覆盖 ${state.data?.start_date || '-'} 至 ${state.data?.end_date || '-'}`} />
        <MetricCard label="行情源" value={state.data?.market_data_source || state.data?.provider || '-'} hint={`更新 ${state.data?.updated_at || '-'}`} />
        <MetricCard label="同步状态" value={syncStatus} hint={`${rawBars.length} 根 / 来源 ${joinValues(barSources, state.data?.market_data_source || state.data?.provider || '-')}`} />
        <MetricCard label="入池状态" value={context.in_pool ? '已入池' : '未入池'} badge={latestPick ? <StatusBadge status={latestPick.status}>{latestPick.status}</StatusBadge> : null} />
      </section>

      <section className="card chart-card section-gap">
        <div className="chart-meta">
          <strong>{state.data?.symbol || symbol}</strong>
          <span>{SECURITY_TYPE_LABELS[securityType] || securityType}</span>
          <span>{BAR_INTERVAL_LABELS[interval] || interval}</span>
          <span>复权 {ADJUST_LABELS[adjust] || adjust}</span>
          <span>{state.data?.start_date || '-'} 至 {state.data?.end_date || '-'}</span>
          <span>最新 {latestTradeTime}</span>
          <span>来源 {joinValues(barSources, state.data?.market_data_source || state.data?.provider || '-')}</span>
          <span>显示 {chartBars.length} / {rawBars.length} 根 K 线</span>
          <span>窗口 {visibleStartDate} 至 {visibleEndDate}</span>
          <span>数据质量：{state.data?.data_quality || 'unknown'}</span>
        </div>
        <div className="mini-kline" role="img" aria-label={`${symbol} ${state.data?.interval || queryOptions.interval} K 线图`} onMouseLeave={() => setHoveredIndex(null)}>
          <div className="price-axis" aria-hidden="true">
            <span>{maxPrice.toFixed(2)}</span>
            <span>{((maxPrice + minPrice) / 2).toFixed(2)}</span>
            <span>{minPrice.toFixed(2)}</span>
          </div>
          <svg className="kline-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {ma20Points ? <polyline points={ma20Points} className="ma-line ma20-line" /> : null}
            {ma25Points ? <polyline points={ma25Points} className="ma-line ma25-line" /> : null}
            {ma60Points ? <polyline points={ma60Points} className="ma-line ma60-line" /> : null}
            {ma5Points ? <polyline points={ma5Points} className="ma-line ma5-line" /> : null}
            {limitUpReturnAnchorX != null ? <line x1={limitUpReturnAnchorX} x2={limitUpReturnAnchorX} y1="0" y2="100" className="limit-up-overlay-line anchor" /> : null}
            {limitUpReturnLines.map((line) => (
              <line key={line.key} x1="0" x2="100" y1={line.y} y2={line.y} className={`limit-up-overlay-line ${line.key}`} />
            ))}
          </svg>
          {chartBars.map((item, index) => {
            const open = toNumber(item.open);
            const close = toNumber(item.close);
            const high = toNumber(item.high);
            const low = toNumber(item.low);
            const top = ((maxPrice - high) / priceSpan) * 100;
            const bottom = ((low - minPrice) / priceSpan) * 100;
            const bodyTop = ((maxPrice - Math.max(open, close)) / priceSpan) * 100;
            const bodyHeight = Math.max((Math.abs(close - open) / priceSpan) * 100, 2);
            const up = close >= open;
            const marked = markerDates.has(item.trade_date);
            const paperOrders = paperOrdersByDate[String(item.trade_date || item.trade_time || '').slice(0, 10)] || [];
            const hasPaperBuy = paperOrders.some((order) => String(order.side || '').toUpperCase() === 'BUY');
            const hasPaperSell = paperOrders.some((order) => String(order.side || '').toUpperCase() === 'SELL');
            return (
              <div
                className={hoveredIndex === index ? 'candle active' : 'candle'}
                key={barDate(item)}
                tabIndex={0}
                title={`${barDate(item)} ${item.interval || interval}/${item.adjust || adjust} ${item.source || '-'} O:${formatPrice(open)} H:${formatPrice(high)} L:${formatPrice(low)} C:${formatPrice(close)} V:${formatVolume(item.volume)}`}
                onFocus={() => setHoveredIndex(index)}
                onMouseEnter={() => setHoveredIndex(index)}
              >
                <span className="wick" style={{ top: `${top}%`, bottom: `${bottom}%` }} />
                <span className={up ? 'body up' : 'body down'} style={{ top: `${bodyTop}%`, height: `${bodyHeight}%` }} />
                {marked ? <span className="pick-marker" /> : null}
                {hasPaperBuy ? <span className="paper-trade-marker buy" /> : null}
                {hasPaperSell ? <span className="paper-trade-marker sell" /> : null}
              </div>
            );
          })}
          {activeBar && chartBars.length ? (
            <div className="kline-tooltip" style={{ left: `${tooltipLeft}%` }}>
              <strong>{barDate(activeBar)}</strong>
              <span>{activeBar.interval || interval} / {ADJUST_LABELS[activeBar.adjust || adjust] || activeBar.adjust || adjust} / {activeBar.source || '-'}</span>
              <span>开 {formatPrice(activeBar.open)} / 高 {formatPrice(activeBar.high)}</span>
              <span>低 {formatPrice(activeBar.low)} / 收 {formatPrice(activeBar.close)}</span>
              <span>量 {formatVolume(activeBar.volume)} / 涨跌 {activeChangePct == null ? '-' : `${activeChangePct.toFixed(2)}%`}</span>
            </div>
          ) : null}
          {!chartBars.length ? <div className="empty chart-empty">当前区间暂无 K 线数据，请调整日期或同步行情。</div> : null}
        </div>
        <div className="kline-volume-panel" role="img" aria-label={`${symbol} 成交量柱状图`}>
          <div className="volume-axis" aria-hidden="true">
            <span>{formatVolume(maxVolume)}</span>
            <span>0</span>
          </div>
          <svg className="volume-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {mavol5Points ? <polyline points={mavol5Points} className="ma-line mavol5-line" /> : null}
            {mavol60Points ? <polyline points={mavol60Points} className="ma-line mavol60-line" /> : null}
          </svg>
          <div className="volume-bars">
            {chartBars.map((item, index) => {
              const volume = toNumber(item.volume);
              const open = toNumber(item.open);
              const close = toNumber(item.close);
              const up = close >= open;
              return (
                <span
                  className={up ? 'volume-bar up' : 'volume-bar down'}
                  key={`${barDate(item)}-volume`}
                  style={{ height: `${Math.max(4, (volume / maxVolume) * 100)}%` }}
                  title={`${barDate(item)} 成交量 ${formatVolume(volume)}`}
                  onMouseEnter={() => setHoveredIndex(index)}
                />
              );
            })}
          </div>
        </div>
        <div className="chart-legend">
          <span><i className="legend-candle up" /> 阳线</span>
          <span><i className="legend-candle down" /> 阴线</span>
          <span><i className="legend-line ma5" /> MA5</span>
          <span><i className="legend-line ma20" /> MA20</span>
          <span><i className="legend-line ma25" /> MA25</span>
          <span><i className="legend-line ma60" /> MA60</span>
          <span><i className="legend-line mavol5" /> MAVOL5</span>
          <span><i className="legend-line mavol60" /> MAVOL60</span>
          <span><i className="legend-volume" /> 成交量</span>
          <span><i className="legend-dot" /> 入池记录</span>
          <span><i className="legend-dot buy" /> Paper BUY</span>
          <span><i className="legend-dot sell" /> Paper SELL</span>
          {hasLimitUpReturnData ? (
            <>
              <span><i className="legend-line limit-up-anchor" /> 涨停锚点</span>
              <span><i className="legend-line limit-up-support" /> 支撑线</span>
              <span><i className="legend-line limit-up-trigger" /> 触发线</span>
              <span><i className="legend-line limit-up-stop" /> 止损线</span>
            </>
          ) : null}
        </div>
        <div className="limit-up-overlay-summary">
          <strong>涨停回马枪 / LIMIT_UP_RETURN</strong>
          {hasLimitUpReturnData ? (
            <span>
              锚点 {limitUpReturnOverlay.anchorDate || '-'} · 支撑 {formatPrice(limitUpReturnOverlay.supportPrice)} · 触发 {formatPrice(limitUpReturnOverlay.triggerPrice)} · 止损 {formatPrice(limitUpReturnOverlay.stopLossPrice)} · {limitUpReturnOverlay.signalSubtype || '-'}
            </span>
          ) : (
            <span className="muted">接口未返回 indicators/overlays 中的策略线数据。</span>
          )}
        </div>
      </section>

      <SectionCard title="入池与复盘上下文">
        {latestPick ? (
          <div className="scan-summary">
            <div className="summary-row"><span>最近入池</span><strong>{latestPick.trade_date} / {latestPick.source}</strong></div>
            <div className="summary-row"><span>策略</span><strong>{latestPick.strategy_code || '-'}</strong></div>
            <div className="summary-row"><span>复盘</span><strong>{latestPick.review_comment || '-'}</strong></div>
            <div className="summary-row"><span>成交</span><strong>{latestPick.deal_status || '-'}</strong></div>
            <div className="summary-row"><span>收益</span><strong>{latestPick.return_pct ?? '-'}</strong></div>
          </div>
        ) : (
          <div className="empty">当前标的暂无有效入池记录。</div>
        )}
      </SectionCard>

      <SectionCard title="历史入池记录" actions={<button type="button" className="btn-secondary" onClick={() => onNavigate?.('picks', { symbol })}>打开选股池</button>}>
        <DataTable
          className="compact-table"
          columns={[
            { label: '日期', render: (item) => item.trade_date || '-' },
            { label: '来源', render: (item) => item.source || '-' },
            { label: '策略', render: (item) => item.strategy_code || '-' },
            { label: '状态', render: (item) => <StatusBadge status={item.status}>{item.status}</StatusBadge> },
            { label: '成交', render: (item) => item.deal_status || '-' },
            { label: '收益', render: (item) => item.return_pct ?? '-' },
          ]}
          rows={context.history || []}
          getKey={(item) => item.id}
          emptyText="暂无历史入池记录。"
        />
      </SectionCard>
    </main>
  );
}
