import { useEffect, useState } from 'react';
import { api, getTenantId } from '../api/client';
import { DataTable, MetricCard, PageHeader, SectionCard, StatusBadge } from '../components/common';

function marketQualityLabel(market) {
  const value = market?.data_quality || (market?.ok === true ? 'available' : market?.ok === false ? 'unhealthy' : 'checking');
  const labels = {
    primary: '主数据源',
    fallback: '备用数据源',
    mock: '模拟数据',
    available: '正常',
    unhealthy: '异常',
    checking: '检查中',
    unknown: '未知',
  };
  return labels[value] || value || '未知';
}

function healthStatusLabel(value) {
  const labels = {
    ok: '正常',
    healthy: '正常',
    unhealthy: '异常',
    unknown: '未知',
  };
  return labels[String(value || '').toLowerCase()] || value || '未知';
}

function booleanLabel(value) {
  if (value === true) return '正常';
  if (value === false) return '异常';
  return '未知';
}

function taskStatusLabel(value) {
  const labels = {
    pending: '等待中',
    queued: '已排队',
    running: '运行中',
    retrying: '重试中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    stale: '已过期',
  };
  return labels[String(value || '').toLowerCase()] || value || '-';
}

function countByStatus(items, status) {
  return items.filter((item) => String(item.status || '').toLowerCase() === status).length;
}

function providerChainLabel(market) {
  const chain = market?.provider_chain;
  return Array.isArray(chain) && chain.length ? chain.join(' -> ') : market?.provider || '-';
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
        <div className="card loading-card">正在加载首页看板...</div>
      </main>
    );
  }

  return (
    <main className="page">
      <PageHeader
        eyebrow="工作台"
        title="今日看板"
        description="集中查看行情源、策略扫描、候选池和后台任务的运行情况。"
        badges={(
          <>
            <StatusBadge tone="success">数据空间 {getTenantId()}</StatusBadge>
            <StatusBadge tone={marketOk ? 'success' : 'warning'}>{marketQualityLabel(state.market)}</StatusBadge>
          </>
        )}
      />

      {state.error ? <div className="alert">{state.error}</div> : null}
      {!marketOk || state.market?.data_quality === 'mock' || state.market?.fallback_used ? (
        <div className="alert warning">
          当前行情质量：{marketQualityLabel(state.market)}。
          {state.market?.fallback_used ? ` 已切换到备用行情源：${state.market?.actual_provider || state.market?.provider || '未知'}。` : ''}
          {state.market?.errors?.length ? ` 最近错误：${state.market.errors[0]}。` : ''}
          扫描和回测结论需要复核后再使用。
        </div>
      ) : null}

      <section className="grid">
        <MetricCard label="接口状态" value={healthStatusLabel(state.health?.status)} hint="后端服务健康检查" />
        <MetricCard
          label="行情源"
          value={state.market?.provider || '未知'}
          badge={<span className={marketOk ? 'data-badge success small-text' : 'data-badge warning small-text'}>{booleanLabel(state.market?.ok)}</span>}
        />
        <MetricCard label="策略数量" value={state.strategies?.total ?? 0} hint="当前可用策略" />
        <MetricCard label="候选池" value={state.picks?.total ?? 0} hint="待复盘或观察的候选标的" />
        <MetricCard label="扫描任务" value={state.scans?.total ?? 0} hint="已创建的策略扫描任务" />
        <MetricCard label="失败任务" value={failedTasks} hint={`运行中 ${runningTasks}`} danger={failedTasks > 0} />
      </section>

      <section className="dashboard-layout section-gap">
        <article className="panel-card">
          <div className="section-title-row">
            <div>
              <h2>下一步操作</h2>
              <p className="muted">常用工作入口集中在这里，方便从行情检查、策略扫描到复盘验证连续操作。</p>
            </div>
          </div>
          <div className="quick-actions">
            <button type="button" className="quick-action" onClick={() => onNavigate?.('scans')}>
              <strong>创建扫描</strong>
              <span>按策略信号生成候选标的。</span>
            </button>
            <button type="button" className="quick-action" onClick={() => onNavigate?.('discovery')}>
              <strong>市场发现</strong>
              <span>扫描前先查看市场宽度和活跃标的。</span>
            </button>
            <button type="button" className="quick-action" onClick={() => onNavigate?.('picks')}>
              <strong>复盘候选池</strong>
              <span>更新状态、成交反馈和复盘备注。</span>
            </button>
            <button type="button" className="quick-action" onClick={() => onNavigate?.('strategies')}>
              <strong>运行回测</strong>
              <span>验证胜率、回撤和资金曲线。</span>
            </button>
            <button type="button" className="quick-action" onClick={() => onNavigate?.('sync')}>
              <strong>同步行情</strong>
              <span>刷新本地行情数据缓存。</span>
            </button>
          </div>
        </article>

        <article className="panel-card">
          <h2>系统状态</h2>
          <div className="scan-summary">
            <div className="summary-row"><span>数据空间</span><strong>{getTenantId()}</strong></div>
            <div className="summary-row"><span>行情状态</span><strong>{marketQualityLabel(state.market)}</strong></div>
            <div className="summary-row"><span>配置行情源</span><strong>{state.market?.provider || '-'}</strong></div>
            <div className="summary-row"><span>实际行情源</span><strong>{state.market?.actual_provider || state.market?.provider || '-'}</strong></div>
            <div className="summary-row"><span>行情源链路</span><strong>{providerChainLabel(state.market)}</strong></div>
            <div className="summary-row"><span>是否降级</span><strong>{state.market?.fallback_used ? '是' : '否'}</strong></div>
            <div className="summary-row"><span>接口</span><strong>{healthStatusLabel(state.health?.status)}</strong></div>
          </div>
        </article>
      </section>

      <SectionCard title="最近任务" actions={<button type="button" className="btn-secondary" onClick={() => onNavigate?.('monitoring')}>查看监控</button>}>
        <DataTable
          className="task-table"
          columns={[
            { label: '任务', render: (task) => task.name || task.id },
            { label: '状态', render: (task) => <StatusBadge status={task.status}>{taskStatusLabel(task.status)}</StatusBadge> },
            { label: '耗时', render: (task) => task.duration_seconds == null ? '-' : `${task.duration_seconds}s` },
            { label: '时间', render: (task) => task.created_at || '-' },
            { label: '失败原因', render: (task) => task.failure_category || task.error || '-' },
          ]}
          rows={recentTasks}
          emptyText="暂无任务。可以先创建一次策略扫描。"
        />
      </SectionCard>
    </main>
  );
}
