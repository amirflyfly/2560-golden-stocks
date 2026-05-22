import { useEffect, useState } from 'react';
import { api, getTenantId } from '../api/client';
import { DataTable, MetricCard, PageHeader, RiskDisclaimer, SectionCard, StatusBadge } from '../components/common';

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

function productionStatusLabel(value) {
  const labels = {
    completed: '已完成',
    metadata_only: '仅元数据',
    blocked_no_snapshot: '缺实时快照',
    blocked_no_history: '缺K线历史',
    blocked_mock_fallback_source: '数据源阻断',
    blocked_low_coverage: '覆盖不足',
    blocked_no_qfq_history: '缺前复权',
    blocked_no_raw_history: '缺不复权',
    blocked_no_limit_rules: '缺涨跌停规则',
    blocked_oos_backtest_required: '需样本外验证',
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

function readinessCheckItems(readiness) {
  return Object.entries(readiness?.checks || {}).map(([name, ok]) => ({ name, ok }));
}

function taskResult(task) {
  return task?.result && typeof task.result === 'object' ? task.result : {};
}

function paperResult(task) {
  const result = taskResult(task);
  return result.paper_trading && typeof result.paper_trading === 'object' ? result.paper_trading : {};
}

function itemCount(value) {
  return Array.isArray(value) ? value.length : 0;
}

function strategyCode(task) {
  return task?.payload?.strategy_code || taskResult(task).strategy?.code || '-';
}

function isSystemStrategyTask(task) {
  const payload = task?.payload || {};
  const params = payload.params || {};
  const source = String(params.source || payload.source || '').toLowerCase();
  return Boolean(params.scheduled_bucket || payload.scheduled_bucket) || source.includes('worker') || source.includes('scheduler');
}

function productionScan(task) {
  const scan = taskResult(task).scan;
  return scan && typeof scan === 'object' ? scan : {};
}

function productionMatchedCount(task) {
  const scan = productionScan(task);
  return scan.matched_count ?? task?.result_summary?.matched_count ?? null;
}

function hitSymbolText(task) {
  const symbols = productionScan(task)?.market_data?.sample_symbols || [];
  const text = symbols
    .slice(0, 5)
    .map((item) => item.symbol || item.code || item.stock_code || '')
    .filter(Boolean)
    .join('、');
  return text || '-';
}

function productionNote(task) {
  const result = taskResult(task);
  const paper = paperResult(task);
  const warnings = result.warnings || [];
  const blocked = paper.blocked || [];
  const skipped = paper.skipped || [];
  if (blocked[0]) return `阻断 ${blocked[0].symbol || '-'}：${blocked[0].reason || '-'}`;
  if (skipped[0]) return `跳过 ${skipped[0].symbol || '-'}：${skipped[0].reason || '-'}`;
  if (warnings[0]) return warnings[0];
  return '-';
}

function actionVerdict({ readiness, market, failedTasks, staleTasks }) {
  const quality = String(market?.data_quality || '').toLowerCase();
  const hasMarketFallback = market?.fallback_used || ['fallback', 'mock'].includes(quality);
  if (readiness?.ready === false) {
    return { label: '不可上线', tone: 'danger', reason: 'readiness 未通过，请先处理上线门禁。' };
  }
  if (market?.ok === false || quality === 'mock') {
    return { label: '不可扫描', tone: 'danger', reason: '行情源不可用或为 mock，扫描结论不可使用。' };
  }
  if (hasMarketFallback || failedTasks > 0 || staleTasks > 0) {
    return { label: '谨慎使用', tone: 'warning', reason: '存在降级行情、失败任务或过期任务，需要人工复核。' };
  }
  return { label: '可正常使用', tone: 'success', reason: '核心检查、任务状态和行情质量未发现阻塞项。' };
}

export function DashboardPage({ onNavigate }) {
  const [state, setState] = useState({
    loading: true,
    error: '',
    health: null,
    market: null,
    readiness: null,
    strategies: null,
    scans: null,
    tasks: null,
    failedTasks: null,
    runningTasks: null,
    staleTasks: null,
    picks: null,
    strategyTasks: null,
  });

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.health(),
      api.marketDataHealth(),
      api.readiness().catch(() => null),
      api.strategies({ page: 1, page_size: 10 }),
      api.scans({ page: 1, page_size: 5 }).catch(() => ({ total: 0, items: [] })),
      api.tasks({ page: 1, page_size: 8 }).catch(() => ({ total: 0, items: [] })),
      api.tasks({ page: 1, page_size: 1, status: 'failed' }).catch(() => ({ total: 0, items: [] })),
      api.tasks({ page: 1, page_size: 1, status: 'stale' }).catch(() => ({ total: 0, items: [] })),
      api.tasks({ page: 1, page_size: 1, status: 'running' }).catch(() => ({ total: 0, items: [] })),
      api.picks({ page: 1, page_size: 5 }).catch(() => ({ total: 0, items: [] })),
      api.tasks({ page: 1, page_size: 8, name: 'strategy.production_run', sort: 'created_at', order: 'desc' }).catch(() => ({ total: 0, items: [] })),
    ])
      .then(([health, market, readiness, strategies, scans, tasks, failedTasks, staleTasks, runningTasks, picks, strategyTasks]) => {
        if (alive) {
          setState({ loading: false, error: '', health, market, readiness, strategies, scans, tasks, failedTasks, staleTasks, runningTasks, picks, strategyTasks });
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
  const failedTasks = state.failedTasks?.total ?? state.readiness?.tasks?.failed ?? countByStatus(recentTasks, 'failed');
  const staleTasks = state.staleTasks?.total ?? state.readiness?.tasks?.stale ?? countByStatus(recentTasks, 'stale');
  const runningTasks = state.runningTasks?.total
    ?? recentTasks.filter((task) => ['pending', 'running', 'retrying'].includes(String(task.status || '').toLowerCase())).length;
  const verdict = actionVerdict({ readiness: state.readiness, market: state.market, failedTasks, staleTasks });
  const checks = readinessCheckItems(state.readiness);
  const productionTasks = state.strategyTasks?.items || [];
  const latest2560Task = productionTasks.find((task) => String(strategyCode(task)).toLowerCase() === '2560') || null;
  const latest2560Count = productionMatchedCount(latest2560Task);

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

      <RiskDisclaimer />

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
        <MetricCard label="今日使用结论" value={verdict.label} hint={verdict.reason} danger={verdict.tone === 'danger'} badge={<StatusBadge tone={verdict.tone}>{verdict.label}</StatusBadge>} />
        <MetricCard label="接口状态" value={healthStatusLabel(state.health?.status)} hint="后端服务健康检查" />
        <MetricCard
          label="行情源"
          value={state.market?.provider || '未知'}
          badge={<span className={marketOk ? 'data-badge success small-text' : 'data-badge warning small-text'}>{booleanLabel(state.market?.ok)}</span>}
        />
        <MetricCard label="策略数量" value={state.strategies?.total ?? 0} hint="当前可用策略" />
        <MetricCard
          label="2560 最新命中"
          value={latest2560Count ?? '-'}
          hint={latest2560Task ? hitSymbolText(latest2560Task) : '等待自动策略运行'}
        />
        <MetricCard label="候选池" value={state.picks?.total ?? 0} hint="待复盘或观察的候选标的" />
        <MetricCard label="扫描任务" value={state.scans?.total ?? 0} hint="已创建的策略扫描任务" />
        <MetricCard label="失败任务" value={failedTasks} hint={`运行中 ${runningTasks}`} danger={failedTasks > 0} />
        <MetricCard label="过期任务" value={staleTasks} hint="stale task 会降低使用结论" danger={staleTasks > 0} />
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
            <button type="button" className="quick-action" onClick={() => onNavigate?.('monitoring')}>
              <strong>上线检查</strong>
              <span>查看 readiness 与 admin launch gates。</span>
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
            <div className="summary-row"><span>readiness</span><StatusBadge tone={state.readiness?.ready ? 'success' : 'danger'}>{state.readiness ? (state.readiness.ready ? 'ready' : 'not ready') : '未知'}</StatusBadge></div>
            <div className="summary-row"><span>失败 / 过期任务</span><strong>{failedTasks} / {staleTasks}</strong></div>
          </div>
        </article>
      </section>

      <SectionCard title="Readiness checks" actions={<button type="button" className="btn-secondary" onClick={() => onNavigate?.('monitoring')}>上线检查入口</button>}>
        {checks.length ? (
          <div className="scan-summary">
            {checks.map((item) => (
              <div className="summary-row" key={item.name}>
                <span>{item.name}</span>
                <StatusBadge tone={item.ok ? 'success' : 'danger'}>{item.ok ? '通过' : '失败'}</StatusBadge>
              </div>
            ))}
          </div>
        ) : <div className="empty">readiness checks 暂不可用。</div>}
      </SectionCard>

      <SectionCard
        title="最近策略命中"
        subtitle={latest2560Task ? `2560 最近完成时间 ${latest2560Task.finished_at || latest2560Task.created_at || '-'}` : '尚未读取到 2560 生产运行任务'}
        actions={<button type="button" className="btn-secondary" onClick={() => onNavigate?.('monitoring')}>查看生产监控</button>}
      >
        <DataTable
          className="strategy-run-table"
          columns={[
            { label: '策略', render: (task) => <strong>{strategyCode(task)}</strong> },
            { label: '触发', render: (task) => <StatusBadge tone={isSystemStrategyTask(task) ? 'success' : 'info'}>{isSystemStrategyTask(task) ? '系统定时' : '人工'}</StatusBadge> },
            { label: '状态', render: (task) => <StatusBadge status={task.status}>{taskStatusLabel(task.status)}</StatusBadge> },
            { label: '生产结果', render: (task) => <StatusBadge status={taskResult(task).production_status || task.status}>{productionStatusLabel(taskResult(task).production_status)}</StatusBadge> },
            {
              label: '命中/阻断',
              render: (task) => {
                const paper = paperResult(task);
                return `${productionMatchedCount(task) ?? '-'} / ${itemCount(paper.blocked)}`;
              },
            },
            { label: '命中标的', render: (task) => <span className="small-text">{hitSymbolText(task)}</span> },
            { label: '提示', render: (task) => <span className="small-text">{productionNote(task)}</span> },
          ]}
          rows={productionTasks}
          getKey={(task) => task.id}
          emptyText="暂无自动策略运行任务。"
        />
      </SectionCard>

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
