import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { canAdmin, canWrite } from '../auth/permissions';
import { DataTable, MetricCard, PageHeader, RiskDisclaimer, SectionCard } from '../components/common';

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

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export function ReportsPage({ onNavigate, authz }) {
  const [period, setPeriod] = useState('week');
  const [summary, setSummary] = useState(null);
  const [reports, setReports] = useState([]);
  const [externalDeliveries, setExternalDeliveries] = useState([]);
  const [externalDeliveryStats, setExternalDeliveryStats] = useState(null);
  const [dailyReview, setDailyReview] = useState(null);
  const [reviewDate, setReviewDate] = useState(todayIso());
  const [reviewPush, setReviewPush] = useState(false);
  const [reviewEvaluateExits, setReviewEvaluateExits] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const mayWrite = canWrite(authz);
  const mayAdmin = canAdmin(authz);
  const writeDisabledTitle = mayWrite ? '' : 'Current role is read-only.';
  const adminDisabledTitle = mayAdmin ? '' : 'Admin role required.';

  async function loadReports(nextPeriod = period) {
    setLoading(true);
    setError('');
    try {
      const deliveryRequest = mayWrite
        ? api.externalPushDeliveries({ limit: 8 })
        : Promise.resolve({ items: [], stats: null });
      const [summaryData, reportData, deliveryData] = await Promise.all([
        api.reportSummary({ period: nextPeriod }),
        api.reports({ page: 1, page_size: 20 }),
        deliveryRequest,
      ]);
      setSummary(summaryData);
      setReports(reportData.items || []);
      setExternalDeliveries(deliveryData.items || []);
      setExternalDeliveryStats(deliveryData.stats || null);
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

  async function createDailyReview() {
    if (!mayWrite) {
      setError(writeDisabledTitle);
      return;
    }
    setReviewing(true);
    setError('');
    setMessage('');
    try {
      const result = await api.dailyReview({
        trade_date: reviewDate,
        push: reviewPush,
        evaluate_exits: reviewEvaluateExits,
        channels: reviewPush ? ['external'] : [],
      });
      setDailyReview(result);
      setMessage(`每日复盘已生成：${result.trade_date}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setReviewing(false);
    }
  }

  async function retryExternalDelivery(item) {
    if (!mayAdmin) {
      setError(adminDisabledTitle);
      return;
    }
    setError('');
    setMessage('');
    try {
      await api.retryExternalPushDelivery(item.id);
      setMessage('External push delivery retry queued.');
      loadReports(period);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadReports(period);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  const totals = summary?.summary || {};
  const quality = totals.data_quality || {};
  const groups = summary?.groups || [];
  const feedbackItems = summary?.feedback?.items || [];
  const dailyExitSummary = dailyReview?.paper_trading?.exit_summary || {};

  return (
    <main className="page" data-testid="reports-page">
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
            <input
              className="scan-input"
              type="date"
              value={reviewDate}
              onChange={(event) => setReviewDate(event.target.value)}
              data-testid="daily-review-date-input"
            />
            <label className="checkbox-field">
              <input type="checkbox" checked={reviewPush} onChange={(event) => setReviewPush(event.target.checked)} disabled={!mayWrite} />
              推送
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={reviewEvaluateExits} onChange={(event) => setReviewEvaluateExits(event.target.checked)} disabled={!mayWrite} />
              先评估卖出
            </label>
            <button
              type="button"
              className="btn-primary"
              onClick={createDailyReview}
              disabled={reviewing || !reviewDate || !mayWrite}
              title={writeDisabledTitle}
              data-testid="daily-review-submit-button"
            >
              {reviewing ? '生成中...' : '生成每日复盘'}
            </button>
          </div>
        )}
      />

      <RiskDisclaimer />

      {error ? <div className="alert">{error}</div> : null}
      {!mayWrite ? <div className="alert warning" data-testid="reports-readonly-warning">Read-only role: daily review and push actions are disabled.</div> : null}
      {message ? <div className="alert success">{message}</div> : null}
      {loading ? <div className="card loading-card">正在加载研究报表...</div> : null}

      {dailyReview ? (
        <SectionCard
          title="每日交易复盘"
          subtitle={`${dailyReview.trade_date} · ${dailyReview.paper_trading?.orders_count ?? 0} 笔委托 · ${dailyReview.paper_trading?.fills_count ?? 0} 笔成交`}
        >
          <div className="grid" data-testid="daily-review-summary">
            <MetricCard label="账户权益" value={Number(dailyReview.paper_trading?.summary?.equity || 0).toFixed(2)} />
            <MetricCard label="当前持仓" value={dailyReview.paper_trading?.active_positions ?? 0} />
            <MetricCard label="当日标的" value={(dailyReview.paper_trading?.traded_symbols || []).length} />
            <MetricCard label="卖出评估" value={dailyExitSummary.status || 'skipped'} />
            <MetricCard label="卖出订单" value={dailyExitSummary.orders ?? 0} />
            <MetricCard label="阻断/跳过" value={`${dailyExitSummary.blocked ?? 0}/${dailyExitSummary.skipped ?? 0}`} danger={(dailyExitSummary.blocked || 0) > 0} />
            <MetricCard label="推送状态" value={dailyReview.push?.status || 'skipped'} />
          </div>
          <pre className="code-block daily-review-message" data-testid="daily-review-message">{dailyReview.message}</pre>
        </SectionCard>
      ) : null}

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

      <SectionCard title="策略反馈建议" subtitle="仅生成待确认建议，不自动修改策略参数。">
        <DataTable
          className="compact-table"
          columns={[
            { label: '策略', render: (item) => <strong>{item.strategy}</strong> },
            { label: '级别', render: (item) => <span className={`status-badge ${item.severity === 'high' ? 'danger' : 'warning'}`}>{item.severity}</span> },
            { label: '建议', render: (item) => item.action },
            { label: '原因', render: (item) => item.reason },
            {
              label: '操作',
              render: (item) => (
                <div className="row-actions">
                  <button type="button" className="btn-secondary" onClick={() => onNavigate?.('picks', item.drilldowns?.picks?.filters || { strategy_code: item.strategy })}>候选</button>
                  <button type="button" className="btn-secondary" onClick={() => onNavigate?.('strategies', item.drilldowns?.backtests?.filters || { strategy_code: item.strategy })}>回测</button>
                </div>
              ),
            },
          ]}
          rows={feedbackItems}
          getKey={(item, index) => `${item.strategy}-${item.type}-${index}`}
          emptyText="暂无策略反馈建议。"
        />
      </SectionCard>

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

      <SectionCard title="External Push Deliveries" subtitle={`Queued external notification delivery state and retry audit trail. Failed: ${externalDeliveryStats?.failed ?? 0}, queued: ${externalDeliveryStats?.queued ?? 0}, sent: ${externalDeliveryStats?.sent ?? 0}.`}>
        <DataTable
          className="compact-table"
          columns={[
            { label: 'Status', render: (item) => <strong>{item.status || '-'}</strong> },
            { label: 'Channel', render: (item) => `${item.channel_type || '-'}:${item.channel_id || '-'}` },
            { label: 'Task', render: (item) => item.task_id || '-' },
            { label: 'Retries', render: (item) => item.retry_count ?? 0 },
            { label: 'Error', render: (item) => item.last_error || '-' },
            { label: 'Updated', render: (item) => item.updated_at || item.created_at || '-' },
            {
              label: 'Action',
              render: (item) => (
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={!mayAdmin || !['failed', 'skipped'].includes(String(item.status || '').toLowerCase())}
                  title={adminDisabledTitle}
                  onClick={() => retryExternalDelivery(item)}
                >
                  Retry
                </button>
              ),
            },
          ]}
          rows={externalDeliveries}
          getKey={(item, index) => item.id || item.delivery_key || index}
          emptyText="No external push delivery records."
        />
      </SectionCard>
    </main>
  );
}
