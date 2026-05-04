import { useEffect, useState } from 'react';
import { api, getTenantId } from '../api/client';
import { DataTable, MetricCard, PageHeader, SectionCard, StatusBadge } from '../components/common';

function marketQualityLabel(market) {
  if (!market) return 'unknown';
  if (market.data_quality) return market.data_quality;
  if (market.ok === true) return 'available';
  if (market.ok === false) return 'unhealthy';
  return 'checking';
}

function countByStatus(items, status) {
  return items.filter((item) => String(item.status || '').toLowerCase() === status).length;
}

export function DashboardPage({ onNavigate }) {
  const [state, setState] = useState({
    loading: true,
    error: '',
    health: null,
    market: null,
    strategies: null,
    scans: null,
    tasks: null,
    failedTasks: null,
    runningTasks: null,
    picks: null,
  });

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.health(),
      api.marketDataHealth(),
      api.strategies({ page: 1, page_size: 10 }),
      api.scans({ page: 1, page_size: 5 }).catch(() => ({ total: 0, items: [] })),
      api.tasks({ page: 1, page_size: 8 }).catch(() => ({ total: 0, items: [] })),
      api.tasks({ page: 1, page_size: 1, status: 'failed' }).catch(() => ({ total: 0, items: [] })),
      api.tasks({ page: 1, page_size: 1, status: 'running' }).catch(() => ({ total: 0, items: [] })),
      api.picks({ page: 1, page_size: 5 }).catch(() => ({ total: 0, items: [] })),
    ])
      .then(([health, market, strategies, scans, tasks, failedTasks, runningTasks, picks]) => {
        if (alive) {
          setState({ loading: false, error: '', health, market, strategies, scans, tasks, failedTasks, runningTasks, picks });
        }
      })
      .catch((error) => {
        if (alive) setState((prev) => ({ ...prev, loading: false, error: error.message }));
      });
    return () => {
      alive = false;
    };
  }, []);

  const recentTasks = state.tasks?.items || [];
  const marketOk = state.market?.ok === true;
  const failedTasks = state.failedTasks?.total ?? countByStatus(recentTasks, 'failed');
  const runningTasks = state.runningTasks?.total
    ?? recentTasks.filter((task) => ['pending', 'running', 'retrying'].includes(String(task.status || '').toLowerCase())).length;

  if (state.loading) {
    return (
      <main className="page">
        <div className="card loading-card">Loading dashboard...</div>
      </main>
    );
  }

  return (
    <main className="page">
      <PageHeader
        eyebrow="Workspace"
        title="Today Dashboard"
        description="Track market data health, scans, candidate pool, and production tasks from one working surface."
        badges={(
          <>
            <StatusBadge tone="success">Tenant {getTenantId()}</StatusBadge>
            <StatusBadge tone={marketOk ? 'success' : 'warning'}>{marketQualityLabel(state.market)}</StatusBadge>
          </>
        )}
      />

      {state.error ? <div className="alert">{state.error}</div> : null}
      {!marketOk || state.market?.data_quality === 'mock' ? (
        <div className="alert warning">Market data quality is {marketQualityLabel(state.market)}. Scan and backtest conclusions need review.</div>
      ) : null}

      <section className="grid">
        <MetricCard label="API status" value={state.health?.status || 'unknown'} hint="Backend health check" />
        <MetricCard
          label="Market source"
          value={state.market?.provider || 'unknown'}
          badge={<span className={marketOk ? 'data-badge success small-text' : 'data-badge warning small-text'}>{String(state.market?.ok ?? 'unknown')}</span>}
        />
        <MetricCard label="Strategies" value={state.strategies?.total ?? 0} hint="Available strategies" />
        <MetricCard label="Candidate pool" value={state.picks?.total ?? 0} hint="Active picks waiting for review" />
        <MetricCard label="Scan tasks" value={state.scans?.total ?? 0} hint="Strategy scan jobs" />
        <MetricCard label="Failed tasks" value={failedTasks} hint={`Running ${runningTasks}`} danger={failedTasks > 0} />
      </section>

      <section className="dashboard-layout section-gap">
        <article className="panel-card">
          <div className="section-title-row">
            <div>
              <h2>Next actions</h2>
              <p className="muted">Daily research actions are grouped here so scan, review, and validation stay connected.</p>
            </div>
          </div>
          <div className="quick-actions">
            <button type="button" className="quick-action" onClick={() => onNavigate?.('scans')}>
              <strong>Create scan</strong>
              <span>Generate candidates from strategy signals.</span>
            </button>
            <button type="button" className="quick-action" onClick={() => onNavigate?.('picks')}>
              <strong>Review pool</strong>
              <span>Update status, deal feedback, and review notes.</span>
            </button>
            <button type="button" className="quick-action" onClick={() => onNavigate?.('strategies')}>
              <strong>Run backtest</strong>
              <span>Validate win rate, drawdown, and equity curve.</span>
            </button>
            <button type="button" className="quick-action" onClick={() => onNavigate?.('sync')}>
              <strong>Sync market data</strong>
              <span>Refresh local market data cache.</span>
            </button>
          </div>
        </article>

        <article className="panel-card">
          <h2>System context</h2>
          <div className="scan-summary">
            <div className="summary-row"><span>Tenant</span><strong>{getTenantId()}</strong></div>
            <div className="summary-row"><span>Market status</span><strong>{marketQualityLabel(state.market)}</strong></div>
            <div className="summary-row"><span>Provider</span><strong>{state.market?.provider || '-'}</strong></div>
            <div className="summary-row"><span>API</span><strong>{state.health?.status || '-'}</strong></div>
          </div>
        </article>
      </section>

      <SectionCard title="Recent tasks" actions={<button type="button" className="btn-secondary" onClick={() => onNavigate?.('monitoring')}>Monitoring</button>}>
        <DataTable
          className="task-table"
          columns={[
            { label: 'Task', render: (task) => task.name || task.id },
            { label: 'Status', render: (task) => <StatusBadge status={task.status}>{task.status}</StatusBadge> },
            { label: 'Duration', render: (task) => task.duration_seconds == null ? '-' : `${task.duration_seconds}s` },
            { label: 'Time', render: (task) => task.created_at || '-' },
            { label: 'Failure', render: (task) => task.failure_category || task.error || '-' },
          ]}
          rows={recentTasks}
          emptyText="No tasks yet. Create a scan to start the workflow."
        />
      </SectionCard>
    </main>
  );
}
