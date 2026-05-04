import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { DataTable, MetricCard, PageHeader, SectionCard } from '../components/common';

function percent(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

function returnPercent(value) {
  return `${Number(value || 0).toFixed(2)}%`;
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
      setMessage(`${format.toUpperCase()} report exported.`);
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
        title="Research Reports"
        description="Weekly and monthly reports with direct drilldown into candidates, reviews, and backtests."
        actions={(
          <div className="row-actions">
            <select className="scan-select" value={period} onChange={(event) => setPeriod(event.target.value)}>
              <option value="week">Weekly</option>
              <option value="month">Monthly</option>
            </select>
            <button type="button" className="btn-secondary" onClick={() => exportSummary('csv')} disabled={Boolean(exporting)}>
              {exporting === 'csv' ? 'Exporting...' : 'CSV'}
            </button>
            <button type="button" className="btn-secondary" onClick={() => exportSummary('json')} disabled={Boolean(exporting)}>
              {exporting === 'json' ? 'Exporting...' : 'JSON'}
            </button>
          </div>
        )}
      />

      {error ? <div className="alert">{error}</div> : null}
      {message ? <div className="alert success">{message}</div> : null}
      {loading ? <div className="card loading-card">Loading reports...</div> : null}

      <section className="grid">
        <MetricCard label="Pool entries" value={totals.total_picks ?? 0} />
        <MetricCard label="Review rate" value={percent(totals.review_rate)} />
        <MetricCard label="Deals" value={totals.deal_count ?? 0} />
        <MetricCard label="Win rate" value={percent(totals.win_rate)} />
        <MetricCard label="Avg return" value={returnPercent(totals.average_return_pct)} />
        <MetricCard label="High risk rate" value={percent(totals.high_risk_rate)} danger={Number(totals.high_risk_rate || 0) > 0.2} />
        <MetricCard label="Primary data" value={percent(quality.primary_rate)} />
        <MetricCard label="Fallback/Mock" value={`${quality.fallback || 0}/${quality.mock || 0}`} danger={(quality.fallback || 0) + (quality.mock || 0) > 0} />
      </section>

      <SectionCard title="Strategy performance">
        <DataTable
          className="report-table"
          columns={[
            { label: 'Strategy', render: (item) => <strong>{item.strategy}</strong> },
            { label: 'Pool', render: (item) => item.total },
            { label: 'Review', render: (item) => percent(item.review_rate) },
            { label: 'Deals', render: (item) => item.deals },
            { label: 'Win', render: (item) => percent(item.win_rate) },
            { label: 'Avg return', render: (item) => returnPercent(item.average_return_pct) },
            { label: 'High risk', render: (item) => percent(item.high_risk_rate) },
            { label: 'Data', render: (item) => `P${item.data_quality?.primary || 0}/F${item.data_quality?.fallback || 0}/M${item.data_quality?.mock || 0}/U${item.data_quality?.unknown || 0}` },
            {
              label: 'Drilldown',
              render: (item) => (
                <div className="row-actions">
                  <button type="button" className="btn-secondary" onClick={() => onNavigate?.('picks', item.drilldowns?.picks?.filters || { strategy_code: item.strategy })}>Picks</button>
                  <button type="button" className="btn-secondary" onClick={() => onNavigate?.('strategies', item.drilldowns?.backtests?.filters || { strategy_code: item.strategy })}>Backtests</button>
                </div>
              ),
            },
          ]}
          rows={groups}
          getKey={(item) => item.strategy}
          emptyText="No reportable pool data."
        />
      </SectionCard>

      <SectionCard title="Research report list">
        <DataTable
          className="compact-table"
          columns={[
            { label: 'Title', render: (item) => item.title || item.id },
            { label: 'Symbol', render: (item) => item.symbol || '-' },
            { label: 'Source', render: (item) => item.source || '-' },
            { label: 'Trace', render: (item) => <button type="button" className="btn-secondary" onClick={() => onNavigate?.('picks', { symbol: item.symbol, pick_id: item.pick_id })}>Pick</button> },
          ]}
          rows={reports}
          getKey={(item, index) => item.id || index}
          emptyText="No research reports."
        />
      </SectionCard>
    </main>
  );
}
