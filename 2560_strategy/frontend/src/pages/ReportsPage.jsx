import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { DataTable, MetricCard, PageHeader, SectionCard } from '../components/common';

function percent(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

function returnPercent(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== '');
}

function limitUpReturnReportFields(item) {
  const source = item.limit_up_return || item.LIMIT_UP_RETURN || item.attribution?.limit_up_return || {};
  return {
    untradable: firstValue(source.untradable_count, source.unfilled_count, item.untradable_count, item.unfilled_count),
    drawdown: firstValue(source.max_drawdown, source.drawdown, item.max_drawdown, item.drawdown),
    attribution: firstValue(source.attribution, source.reason_attribution, item.signal_attribution, item.attribution_summary),
  };
}

function attributionText(value) {
  if (!value) return '-';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map((item) => item.signal_subtype || item.reason || item.type || JSON.stringify(item)).join(' / ');
  if (typeof value === 'object') return Object.entries(value).map(([key, item]) => {
    if (item && typeof item === 'object') return `${key}:${item.count ?? item.trade_count ?? '-'}`;
    return `${key}:${item}`;
  }).join(' / ');
  return String(value);
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function ReportsPage({ onNavigate }) {
  const [period, setPeriod] = useState('week');
  const [summary, setSummary] = useState(null);
  const [reports, setReports] = useState([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState('');

  async function loadReports(nextPeriod = period) {
    setLoading(true);
    setError('');
    try {
      const [summaryData, reportData] = await Promise.all([
        api.reportSummary({ period: nextPeriod }),
        api.reports({ page: 1, page_size: 20 }),
      ]);
      setSummary(summaryData);
      setReports(reportData.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function exportSummary(format) {
    setExporting(format);
    setError('');
    setMessage('');
    try {
      const file = await api.exportReportSummary({ period, format });
      saveBlob(file.blob, file.filename);
      setMessage(`${format.toUpperCase()} 报表已导出。`);
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting('');
    }
  }

  useEffect(() => {
    loadReports(period);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  const totals = summary?.summary || {};
  const quality = totals.data_quality || {};
  const groups = summary?.groups || [];

  return (
    <main className="page">
      <PageHeader
        eyebrow="Reports"
        title="研究报表"
        description="按周/月汇总候选入池、复盘、成交、收益和数据质量，并支持下钻到候选与回测。"
        actions={(
          <div className="row-actions">
            <select className="scan-select" value={period} onChange={(event) => setPeriod(event.target.value)}>
              <option value="week">周报</option>
              <option value="month">月报</option>
            </select>
            <button type="button" className="btn-secondary" onClick={() => exportSummary('csv')} disabled={Boolean(exporting)}>
              {exporting === 'csv' ? '导出中...' : 'CSV'}
            </button>
            <button type="button" className="btn-secondary" onClick={() => exportSummary('json')} disabled={Boolean(exporting)}>
              {exporting === 'json' ? '导出中...' : 'JSON'}
            </button>
          </div>
        )}
      />

      {error ? <div className="alert">{error}</div> : null}
      {message ? <div className="alert success">{message}</div> : null}
      {loading ? <div className="card loading-card">正在加载研究报表...</div> : null}

      <section className="grid">
        <MetricCard label="入池数" value={totals.total_picks ?? 0} />
        <MetricCard label="复盘率" value={percent(totals.review_rate)} />
        <MetricCard label="成交数" value={totals.deal_count ?? 0} />
        <MetricCard label="胜率" value={percent(totals.win_rate)} />
        <MetricCard label="平均收益" value={returnPercent(totals.average_return_pct)} />
        <MetricCard label="高风险占比" value={percent(totals.high_risk_rate)} danger={Number(totals.high_risk_rate || 0) > 0.2} />
        <MetricCard label="真实行情占比" value={percent(quality.primary_rate)} />
        <MetricCard label="Fallback/Mock" value={`${quality.fallback || 0}/${quality.mock || 0}`} danger={(quality.fallback || 0) + (quality.mock || 0) > 0} />
      </section>

      <SectionCard title="策略表现">
        <DataTable
          className="report-table"
          columns={[
            { label: '策略', render: (item) => <strong>{item.strategy}</strong> },
            { label: '入池', render: (item) => item.total },
            { label: '复盘', render: (item) => percent(item.review_rate) },
            { label: '成交', render: (item) => item.deals },
            { label: '胜率', render: (item) => percent(item.win_rate) },
            { label: '平均收益', render: (item) => returnPercent(item.average_return_pct) },
            { label: '不可成交', render: (item) => limitUpReturnReportFields(item).untradable ?? '-' },
            { label: '回撤', render: (item) => percent(limitUpReturnReportFields(item).drawdown) },
            { label: '归因', render: (item) => <span className="report-attribution-text">{attributionText(limitUpReturnReportFields(item).attribution)}</span> },
            { label: '高风险', render: (item) => percent(item.high_risk_rate) },
            { label: '数据口径', render: (item) => `P${item.data_quality?.primary || 0}/F${item.data_quality?.fallback || 0}/M${item.data_quality?.mock || 0}/U${item.data_quality?.unknown || 0}` },
            {
              label: '下钻',
              render: (item) => (
                <div className="row-actions">
                  <button type="button" className="btn-secondary" onClick={() => onNavigate?.('picks', item.drilldowns?.picks?.filters || { strategy_code: item.strategy })}>候选</button>
                  <button type="button" className="btn-secondary" onClick={() => onNavigate?.('strategies', item.drilldowns?.backtests?.filters || { strategy_code: item.strategy })}>回测</button>
                </div>
              ),
            },
          ]}
          rows={groups}
          getKey={(item) => item.strategy}
          emptyText="暂无可汇总的入池与复盘数据。"
        />
      </SectionCard>

      <SectionCard title="研究报告列表">
        <DataTable
          className="compact-table"
          columns={[
            { label: '标题', render: (item) => item.title || item.id },
            { label: '股票', render: (item) => item.symbol || '-' },
            { label: '来源', render: (item) => item.source || '-' },
            { label: '追踪', render: (item) => <button type="button" className="btn-secondary" onClick={() => onNavigate?.('picks', { symbol: item.symbol, pick_id: item.pick_id })}>候选</button> },
          ]}
          rows={reports}
          getKey={(item, index) => item.id || index}
          emptyText="暂无研究报告。"
        />
      </SectionCard>
    </main>
  );
}
