import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { DataTable, MetricCard, PageHeader, SectionCard, StatusBadge } from '../components/common';

function percent(value) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function price(value) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return Number(value).toFixed(2);
}

function qualityTone(contract) {
  if (contract?.data_quality === 'mock' || contract?.fallback_used) return 'warning';
  if (contract?.data_quality === 'primary') return 'success';
  return 'info';
}

function coverageTone(value) {
  if (value >= 0.8) return 'success';
  if (value >= 0.4) return 'warning';
  return 'danger';
}

function mergeCandidates(topMovers, activeSymbols) {
  const map = new Map();
  topMovers.forEach((item) => {
    map.set(item.symbol, { ...item, candidate_sources: ['强势异动'] });
  });
  activeSymbols.forEach((item) => {
    const current = map.get(item.symbol);
    map.set(item.symbol, {
      ...(current || item),
      ...item,
      candidate_sources: [...new Set([...(current?.candidate_sources || []), '成交活跃'])],
    });
  });
  return Array.from(map.values());
}

export function MarketDiscoveryPage({ onNavigate }) {
  const [params, setParams] = useState({ sample_size: 8, lookback_days: 45 });
  const [state, setState] = useState({ loading: true, error: '', data: null });

  function load(nextParams = params) {
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    api.marketDiscovery(nextParams)
      .then((data) => setState({ loading: false, error: '', data }))
      .catch((error) => setState((prev) => ({ ...prev, loading: false, error: error.message })));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const data = state.data || {};
  const breadth = data.breadth || {};
  const contract = data.data_contract || {};
  const notes = data.opportunity_notes || [];
  const requestedSample = Number(data.sample_size ?? params.sample_size ?? 0);
  const sampled = Number(breadth.sampled || 0);
  const coverageRatio = requestedSample ? sampled / requestedSample : 0;
  const providerErrors = contract.errors || [];
  const health = data.health || {};
  const candidates = useMemo(() => mergeCandidates(data.top_movers || [], data.active_symbols || []), [data.top_movers, data.active_symbols]);
  const candidateGroups = useMemo(() => [
    {
      title: '强势突破',
      hint: '日内强势或阶段强势标签',
      items: candidates.filter((item) => (item.signal_tags || []).some((tag) => ['日内强势', '阶段强势'].includes(tag))),
    },
    {
      title: '趋势确认',
      hint: '最新价站上 MA20',
      items: candidates.filter((item) => item.above_ma20),
    },
    {
      title: '成交活跃',
      hint: '活跃度排序靠前',
      items: candidates.filter((item) => (item.candidate_sources || []).includes('成交活跃')),
    },
    {
      title: '待观察',
      hint: '暂无强势标签但仍在本次样本内',
      items: candidates.filter((item) => !(item.signal_tags || []).some((tag) => ['日内强势', '阶段强势'].includes(tag)) && !item.above_ma20),
    },
  ], [candidates]);

  return (
    <main className="page">
      <PageHeader
        eyebrow="Discovery"
        title="市场发现"
        description="用现有行情源先建立市场宽度、强势样本和活跃标的入口，作为扫描前的机会发现层。"
        badges={(
          <>
            <StatusBadge tone={qualityTone(contract)}>{contract.data_quality || 'unknown'}</StatusBadge>
            {contract.fallback_used ? <StatusBadge tone="warning">fallback</StatusBadge> : null}
          </>
        )}
      />

      {state.error ? <div className="alert">{state.error}</div> : null}
      {contract.data_quality === 'mock' || contract.fallback_used ? (
        <div className="alert warning">
          当前市场发现使用 {contract.data_quality || 'unknown'} 数据{contract.fallback_used ? '，且行情源已降级' : ''}，只能作为扫描前线索。
        </div>
      ) : null}
      {state.loading ? <div className="card loading-card">正在计算市场发现数据...</div> : null}

      <form className="toolbar" onSubmit={(event) => { event.preventDefault(); load(params); }}>
        <label>
          样本数量
          <input
            type="number"
            min="1"
            max="20"
            value={params.sample_size}
            onChange={(event) => setParams((prev) => ({ ...prev, sample_size: event.target.value }))}
          />
        </label>
        <label>
          回看天数
          <input
            type="number"
            min="10"
            max="180"
            value={params.lookback_days}
            onChange={(event) => setParams((prev) => ({ ...prev, lookback_days: event.target.value }))}
          />
        </label>
        <button type="submit" disabled={state.loading}>刷新发现</button>
      </form>

      <section className="grid">
        <MetricCard label="样本数" value={breadth.sampled ?? 0} hint={`截至 ${data.as_of || '-'}`} />
        <MetricCard label="请求覆盖率" value={percent(coverageRatio)} hint={`本次请求 ${requestedSample || '-'} / 完成 ${sampled}`} danger={coverageRatio < 0.8} />
        <MetricCard label="上涨占比" value={percent(breadth.advance_ratio)} hint={`${breadth.advancers ?? 0} 涨 / ${breadth.decliners ?? 0} 跌`} />
        <MetricCard label="站上 MA20" value={percent(breadth.above_ma20_ratio)} hint={`${breadth.above_ma20 ?? 0} 个样本`} />
        <MetricCard label="平均换手率" value={breadth.avg_turnover_rate == null ? '-' : `${Number(breadth.avg_turnover_rate).toFixed(2)}%`} />
        <MetricCard label="行情源" value={contract.provider || '-'} hint={(contract.provider_chain || []).join(' -> ') || '-'} danger={contract.fallback_used || contract.data_quality === 'mock'} />
      </section>

      <SectionCard title="覆盖率与数据质量" subtitle="覆盖率是本次请求样本覆盖，不代表全市场覆盖；发现结论必须结合行情源质量使用。">
        <div className="quality-grid">
          <div className="quality-tile">
            <span>样本覆盖</span>
            <strong>{sampled} / {requestedSample || '-'}</strong>
            <StatusBadge tone={coverageTone(coverageRatio)}>{percent(coverageRatio)}</StatusBadge>
          </div>
          <div className="quality-tile">
            <span>行情健康</span>
            <strong>{health.ok ? '可用' : '异常'}</strong>
            <small>{health.message || contract.provider || '-'}</small>
          </div>
          <div className="quality-tile">
            <span>数据质量</span>
            <strong>{contract.data_quality || 'unknown'}</strong>
            <small>{contract.fallback_used ? '已发生 fallback' : '未报告 fallback'}</small>
          </div>
          <div className="quality-tile">
            <span>采集错误</span>
            <strong>{providerErrors.length}</strong>
            <small>{providerErrors.slice(0, 2).join('；') || '暂无错误'}</small>
          </div>
        </div>
      </SectionCard>

      {notes.length ? (
        <SectionCard title="发现结论" className="section-gap">
          <div className="quick-actions">
            {notes.map((note) => (
              <div className="quick-action" key={note}><strong>提示</strong><span>{note}</span></div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      <SectionCard title="候选分组" subtitle="分组只基于当前样本的标签、MA20 和活跃度派生，用于扫描前分流。">
        <div className="candidate-group-grid">
          {candidateGroups.map((group) => (
            <div className="candidate-group" key={group.title}>
              <div className="section-title-row">
                <div>
                  <strong>{group.title}</strong>
                  <p className="muted">{group.hint}</p>
                </div>
                <StatusBadge tone={group.items.length ? 'info' : 'warning'}>{group.items.length}</StatusBadge>
              </div>
              <div className="candidate-chip-list">
                {group.items.slice(0, 6).map((item) => (
                  <button type="button" className="candidate-chip" key={`${group.title}-${item.symbol}`} onClick={() => onNavigate?.('kline', { symbol: item.symbol })}>
                    <strong>{item.symbol}</strong>
                    <span>{item.name || '-'}</span>
                    <small>{percent(item.change_pct)} / {item.above_ma20 ? 'MA20 上方' : 'MA20 下方'}</small>
                  </button>
                ))}
                {!group.items.length ? <div className="empty compact-empty">暂无候选。</div> : null}
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <section className="dashboard-layout section-gap">
        <SectionCard title="强势与异动样本">
          <DataTable
            className="active-discovery-table"
            columns={[
              { label: '股票', render: (item) => <strong>{item.symbol} {item.name}</strong> },
              { label: '最新价', render: (item) => price(item.last_close) },
              { label: '日涨跌', render: (item) => percent(item.change_pct) },
              { label: '阶段收益', render: (item) => percent(item.lookback_return_pct) },
              { label: '标签', render: (item) => (item.signal_tags || []).map((tag) => <StatusBadge key={tag} tone="info" className="compact-badge">{tag}</StatusBadge>) },
              { label: '操作', render: (item) => <button type="button" className="btn-secondary" onClick={() => onNavigate?.('kline', { symbol: item.symbol })}>K 线</button> },
            ]}
            rows={data.top_movers || []}
            getKey={(item) => item.symbol}
            emptyText="暂无市场发现样本。"
          />
        </SectionCard>

        <SectionCard title="成交活跃样本">
          <DataTable
            className="discovery-table"
            columns={[
              { label: '股票', render: (item) => <strong>{item.symbol} {item.name}</strong> },
              { label: '换手率', render: (item) => item.turnover_rate == null ? '-' : `${Number(item.turnover_rate).toFixed(2)}%` },
              { label: '成交额', render: (item) => item.amount == null ? '-' : `${(Number(item.amount) / 100000000).toFixed(2)} 亿` },
              { label: 'MA20', render: (item) => item.above_ma20 ? <StatusBadge tone="success">站上</StatusBadge> : <StatusBadge tone="warning">未站上</StatusBadge> },
              { label: '操作', render: (item) => <button type="button" className="btn-secondary" onClick={() => onNavigate?.('kline', { symbol: item.symbol })}>看 K 线</button> },
            ]}
            rows={data.active_symbols || []}
            getKey={(item) => item.symbol}
            emptyText="暂无活跃样本。"
          />
        </SectionCard>
      </section>
    </main>
  );
}
