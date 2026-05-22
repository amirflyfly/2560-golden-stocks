import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { DataTable, MetricCard, PageHeader, SectionCard, StatusBadge } from '../components/common';

const TASK_STATUSES = ['', 'pending', 'queued', 'running', 'retrying', 'completed', 'succeeded', 'failed', 'cancelled', 'canceled', 'stale'];
const TASK_SORTS = [
  { value: 'created_at:desc', label: '最新优先' },
  { value: 'created_at:asc', label: '最早优先' },
  { value: 'duration_seconds:desc', label: '耗时最长' },
  { value: 'failure_category:asc', label: '失败类型' },
];

function taskCanCancel(task) {
  return ['pending', 'running', 'retrying'].includes(String(task.status || '').toLowerCase());
}

function statusLabel(status) {
  const labels = {
    pending: '等待中',
    queued: '已排队',
    running: '运行中',
    retrying: '重试中',
    completed: '已完成',
    succeeded: '已成功',
    failed: '失败',
    cancelled: '已取消',
    canceled: '已取消',
    stale: '已过期',
  };
  return labels[String(status || '').toLowerCase()] || status || '-';
}

function environmentLabel(value) {
  const labels = {
    development: '开发环境',
    dev: '开发环境',
    staging: '预发环境',
    production: '生产环境',
    prod: '生产环境',
    test: '测试环境',
  };
  return labels[String(value || '').toLowerCase()] || value || '-';
}

function healthLabel(ok) {
  if (ok === true) return '正常';
  if (ok === false) return '异常';
  return '未知';
}

function percentLabel(value) {
  const numeric = Number(value ?? 0);
  return `${(numeric * 100).toFixed(1)}%`;
}

function cacheBackendLabel(value) {
  const labels = {
    memory: '内存',
    redis: 'Redis',
    auto: '自动',
  };
  return labels[String(value || '').toLowerCase()] || value || '-';
}

function failureCategoryLabel(value) {
  const labels = {
    validation: '参数校验',
    timeout: '超时',
    infrastructure: '基础设施',
    stale: '心跳过期',
    unexpected: '未知异常',
  };
  return labels[String(value || '').toLowerCase()] || value || '-';
}

function detailLabel(value) {
  const labels = {
    ok: '正常',
    normal: '正常',
    memory: '内存',
    unhealthy: '异常',
  };
  return labels[String(value || '').toLowerCase()] || value || '-';
}

function hasLimitUpReturnTransition(value) {
  if (!value) return false;
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return text.includes('pullback_setup') && text.includes('breakout_confirmed');
}

function limitUpReturnTransitionAlerts(tasks, logs) {
  const taskAlerts = (tasks?.items || [])
    .filter((task) => hasLimitUpReturnTransition(task.status_transition || task.lifecycle_transition || task.result_summary || task))
    .map((task) => ({
      id: task.id || task.name,
      text: `${task.name || task.id}: pullback_setup -> breakout_confirmed，涨停回马枪突破确认。`,
    }));
  const logAlerts = (logs?.items || [])
    .filter(hasLimitUpReturnTransition)
    .slice(0, 5)
    .map((line, index) => ({
      id: `log-${index}`,
      text: `日志提醒：pullback_setup -> breakout_confirmed，涨停回马枪突破确认。${String(line).slice(0, 80)}`,
    }));
  return [...taskAlerts, ...logAlerts].slice(0, 6);
}

function launchGateItems(launchCheck) {
  return Object.entries(launchCheck?.gates || {}).map(([name, gate]) => ({ name, ...gate }));
}

function isSystemStrategyTask(task) {
  const payload = task?.payload || {};
  const params = payload.params || {};
  const source = String(params.source || payload.source || '').toLowerCase();
  return Boolean(params.scheduled_bucket || payload.scheduled_bucket) || source.includes('worker') || source.includes('scheduler');
}

function strategyCode(task) {
  return task?.payload?.strategy_code || task?.result?.strategy?.code || '-';
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

function coverageText(task) {
  const result = taskResult(task);
  const coverage = result.local_coverage || result.production_contract?.local_coverage || {};
  const synced = coverage.synced_symbols;
  const target = coverage.target_security_count || coverage.security_count;
  const ratio = coverage.coverage_ratio ?? coverage.local_coverage_ratio;
  if (synced == null && target == null) return '-';
  const base = target ? `${synced ?? 0}/${target}` : String(synced ?? '-');
  return ratio == null ? base : `${base} (${percentLabel(ratio)})`;
}

function dataFreshnessText(task) {
  const result = taskResult(task);
  const coverage = result.local_coverage || result.production_contract?.local_coverage || {};
  const snapshot = result.local_snapshot_summary || result.production_contract?.local_snapshot_summary || {};
  const latestBar = coverage.last_trade_date || '-';
  const latestSnapshot = snapshot.latest_trade_time || '-';
  return `K线 ${latestBar} / 快照 ${latestSnapshot}`;
}

function freshnessRoot(task) {
  const result = taskResult(task);
  return result.freshness || result.data_freshness || result.production_contract?.freshness || result.production_contract?.data_freshness || null;
}

function freshnessEntry(root, keys) {
  if (!root || typeof root !== 'object') return null;
  for (const key of keys) {
    if (root[key] && typeof root[key] === 'object') return root[key];
  }
  return null;
}

function normalizedFreshnessStatus(entry) {
  if (!entry) return '';
  if (entry.is_fresh === true || entry.fresh === true || entry.timely === true) return 'realtime';
  if (entry.is_fresh === false || entry.fresh === false || entry.timely === false || entry.is_stale === true || entry.stale === true) return 'delayed';
  const raw = String(entry.status || entry.state || entry.label || entry.freshness_status || '').toLowerCase();
  if (['fresh', 'realtime', 'real_time', 'timely', 'current', 'ok', 'ready'].includes(raw)) return 'realtime';
  if (['stale', 'delayed', 'delay', 'old', 'expired', 'outdated', 'late'].includes(raw)) return 'delayed';
  if (['missing', 'none', 'empty', 'unavailable', 'no_data'].includes(raw)) return 'none';
  return '';
}

function flatFreshnessEntry(root, type) {
  if (!root || typeof root !== 'object') return null;
  if (type === 'snapshot' && (root.latest_snapshot_time || root.snapshot_age_seconds != null)) {
    const age = root.snapshot_age_seconds;
    const maxAge = root.snapshot_max_age_seconds;
    const status = !root.latest_snapshot_time
      ? 'missing'
      : (age != null && maxAge != null ? (Number(age) <= Number(maxAge) ? 'fresh' : 'stale') : 'ready');
    return {
      status,
      latest_snapshot_time: root.latest_snapshot_time,
      age_seconds: age,
      max_age_seconds: maxAge,
    };
  }
  if (type === 'kline' && (root.latest_trade_date || root.daily_bar_lag_days != null)) {
    const lag = root.daily_bar_lag_days;
    const maxLag = root.daily_bar_max_lag_days;
    const status = !root.latest_trade_date
      ? 'missing'
      : (lag != null && maxLag != null ? (Number(lag) <= Number(maxLag) ? 'fresh' : 'stale') : 'ready');
    return {
      status,
      latest_trade_date: root.latest_trade_date,
      lag_days: lag,
      max_lag_days: maxLag,
    };
  }
  return null;
}

function freshnessTime(entry) {
  if (!entry) return '-';
  return entry.latest_trade_time || entry.latest_snapshot_time || entry.last_trade_time || entry.trade_time || entry.latest_bar_time || entry.last_trade_date || entry.trade_date || entry.updated_at || entry.as_of || '-';
}

function freshnessDisplay(task, type) {
  const root = freshnessRoot(task);
  const nestedEntry = type === 'snapshot'
    ? freshnessEntry(root, ['snapshot', 'snapshots', 'quote_snapshot', 'market_snapshot'])
    : freshnessEntry(root, ['kline', 'bar', 'bars', 'history', 'coverage']);
  const entry = nestedEntry || flatFreshnessEntry(root, type);
  if (!entry) return null;
  const status = normalizedFreshnessStatus(entry);
  if (status === 'realtime') return { label: type === 'snapshot' ? '实时' : '及时', tone: 'success', time: freshnessTime(entry) };
  if (status === 'delayed') return { label: '延迟', tone: 'warning', time: freshnessTime(entry) };
  if (status === 'none') return { label: '暂无', tone: 'warning', time: freshnessTime(entry) };
  return { label: '已更新', tone: 'info', time: freshnessTime(entry) };
}

function dataFreshnessNode(task) {
  const snapshot = freshnessDisplay(task, 'snapshot');
  const kline = freshnessDisplay(task, 'kline');
  if (!snapshot && !kline) return <span className="small-text">{dataFreshnessText(task)}<br />覆盖 {coverageText(task)}</span>;
  return (
    <span className="freshness-stack">
      {snapshot ? <span>快照 <StatusBadge tone={snapshot.tone}>{snapshot.label}</StatusBadge><small>{snapshot.time}</small></span> : null}
      {kline ? <span>K线 <StatusBadge tone={kline.tone}>{kline.label}</StatusBadge><small>{kline.time}</small></span> : null}
      <small>覆盖 {coverageText(task)}</small>
    </span>
  );
}

function executionNote(task) {
  const result = taskResult(task);
  const paper = paperResult(task);
  const warnings = result.warnings || [];
  const blocked = paper.blocked || [];
  const skipped = paper.skipped || [];
  const firstBlocked = blocked[0];
  const firstSkipped = skipped[0];
  if (firstBlocked) return `阻断 ${firstBlocked.symbol || '-'}: ${firstBlocked.reason || '-'}`;
  if (firstSkipped) return `跳过 ${firstSkipped.symbol || '-'}: ${firstSkipped.reason || '-'}`;
  if (warnings.length) return warnings[0];
  return '-';
}

export function MonitoringPage() {
  const [state, setState] = useState({ loading: true, error: '', overview: null, metrics: null, logs: null, tasks: null, strategyTasks: null, launchCheck: null, launchCheckError: '' });
  const [taskPage, setTaskPage] = useState(1);
  const [taskStatus, setTaskStatus] = useState('');
  const [taskSort, setTaskSort] = useState('created_at:desc');
  const [logKeyword, setLogKeyword] = useState('');

  function load(page = taskPage, status = taskStatus, sortValue = taskSort) {
    const [sort, order] = sortValue.split(':');
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    Promise.all([
      api.monitoringOverview(),
      api.monitoringMetrics(),
      api.monitoringLogs({ limit: 80 }),
      api.tasks({ page, page_size: 10, sort, order, ...(status ? { status } : {}) }),
      api.tasks({ page: 1, page_size: 8, name: 'strategy.production_run', sort: 'created_at', order: 'desc' }),
      api.adminLaunchCheck()
        .then((data) => ({ data, error: '' }))
        .catch((error) => ({ data: null, error: error.message || '上线检查不可用/权限不足' })),
    ])
      .then(([overview, metrics, logs, tasks, strategyTasks, launchCheckResult]) => setState({ loading: false, error: '', overview, metrics, logs, tasks, strategyTasks, launchCheck: launchCheckResult.data, launchCheckError: launchCheckResult.error }))
      .catch((error) => setState((prev) => ({ ...prev, loading: false, error: error.message })));
  }

  useEffect(() => {
    load(1, taskStatus);
  }, []);

  function changeStatus(event) {
    const nextStatus = event.target.value;
    setTaskStatus(nextStatus);
    setTaskPage(1);
    load(1, nextStatus, taskSort);
  }

  function changeSort(event) {
    const nextSort = event.target.value;
    setTaskSort(nextSort);
    setTaskPage(1);
    load(1, taskStatus, nextSort);
  }

  function changePage(nextPage) {
    const normalized = Math.max(1, nextPage);
    setTaskPage(normalized);
    load(normalized, taskStatus, taskSort);
  }

  function cancelTask(task) {
    api.cancelTask(task.id).then(() => load(taskPage, taskStatus, taskSort)).catch((error) => setState((prev) => ({ ...prev, error: error.message })));
  }

  function copyLaunchSummary() {
    const payload = state.launchCheck || { status: 'unavailable', message: state.launchCheckError || '上线检查不可用/权限不足' };
    navigator.clipboard?.writeText(JSON.stringify(payload, null, 2));
  }

  const { overview, metrics, logs, tasks, strategyTasks, launchCheck } = state;
  const healthItems = [
    { label: 'MySQL', ok: overview?.database?.ok, detail: overview?.database?.message || 'ok' },
    { label: 'Redis', ok: overview?.cache?.ok, detail: overview?.cache?.backend || overview?.cache?.message || '-' },
    { label: '行情数据', ok: overview?.market_data?.ok, detail: overview?.market_data?.provider || '-' },
  ];
  const unhealthyItems = healthItems.filter((item) => item.ok === false);
  const taskStatusCounts = overview?.tasks?.by_status || {};
  const failureCounts = overview?.tasks?.by_failure_category || {};
  const signalReview = overview?.signal_review || {};
  const failedTasks = taskStatusCounts.failed || 0;
  const staleTasks = taskStatusCounts.stale || 0;
  const signalReviewDegraded = signalReview.status === 'degraded' || (metrics?.signal_review_incomplete || 0) > 0;
  const runningTasks = (taskStatusCounts.running || 0) + (taskStatusCounts.pending || 0) + (taskStatusCounts.retrying || 0);
  const limitUpReturnAlerts = limitUpReturnTransitionAlerts(tasks, logs);
  const launchGates = launchGateItems(launchCheck);
  const pageCount = Math.max(1, Math.ceil((tasks?.total || 0) / (tasks?.page_size || 10)));
  const productionTasks = strategyTasks?.items || [];
  const autoProductionTasks = productionTasks.filter(isSystemStrategyTask);
  const latestProductionTask = productionTasks[0] || null;
  const latestProductionResult = taskResult(latestProductionTask);
  const latestPaper = paperResult(latestProductionTask);
  const latestScan = latestProductionResult.scan || {};
  const latestProductionWarnings = latestProductionResult.warnings || [];
  const latestProductionBlocked = itemCount(latestPaper.blocked);
  const latestProductionOrders = itemCount(latestPaper.orders);
  const latestSnapshotFreshness = freshnessDisplay(latestProductionTask, 'snapshot');
  const latestKlineFreshness = freshnessDisplay(latestProductionTask, 'kline');
  const filteredLogs = useMemo(() => {
    const keyword = logKeyword.trim().toLowerCase();
    const lines = logs?.items || [];
    return keyword ? lines.filter((line) => line.toLowerCase().includes(keyword)) : lines;
  }, [logs, logKeyword]);

  return (
    <main className="page">
      <PageHeader
        eyebrow="监控"
        title="生产监控"
        description="查看服务健康、任务生命周期、失败类型、过期任务和脱敏日志。"
        actions={<button type="button" onClick={() => load(taskPage, taskStatus, taskSort)} disabled={state.loading}>刷新</button>}
      />

      {state.error ? <div className="alert" data-testid="monitoring-error">{state.error}</div> : null}
      {unhealthyItems.length || failedTasks || staleTasks || signalReviewDegraded ? (
        <div className="alert observability-alert">
          <strong>需要关注：</strong>
          {unhealthyItems.map((item) => `${item.label} 异常`).join('，')}
          {unhealthyItems.length && (failedTasks || staleTasks || signalReviewDegraded) ? '; ' : ''}
          {failedTasks ? `失败任务 ${failedTasks}` : ''}
          {failedTasks && staleTasks ? '; ' : ''}
          {staleTasks ? `过期任务 ${staleTasks}` : ''}
          {(failedTasks || staleTasks) && signalReviewDegraded ? '; ' : ''}
          {signalReviewDegraded ? `信号复盘链路未闭合 ${metrics?.signal_review_incomplete ?? signalReview.incomplete ?? 0}` : ''}
        </div>
      ) : null}
      {state.loading ? <div className="card loading-card">正在加载生产状态...</div> : null}
      {limitUpReturnAlerts.length ? (
        <div className="alert success limit-up-alert">
          <strong>涨停回马枪确认提醒：</strong>
          {limitUpReturnAlerts.map((item) => <span key={item.id}>{item.text}</span>)}
        </div>
      ) : null}

      <section className="grid">
        <MetricCard label="运行环境" value={environmentLabel(overview?.environment)} />
        <MetricCard label="MySQL" value={healthLabel(overview?.database?.ok)} danger={overview?.database?.ok === false} />
        <MetricCard label="Redis" value={overview?.cache?.ok ? cacheBackendLabel(overview.cache.backend) : '异常'} danger={overview?.cache?.ok === false} />
        <MetricCard label="行情源" value={overview?.market_data?.provider || '-'} />
        <MetricCard label="闭环完整率" value={percentLabel(metrics?.signal_review_complete_rate ?? signalReview.complete_rate ?? 1)} danger={signalReviewDegraded} />
      </section>

      <section className="grid section-gap">
        <MetricCard label="任务总数" value={metrics?.tasks_total ?? 0} />
        <MetricCard label="活跃任务" value={runningTasks} />
        <MetricCard label="失败任务" value={failedTasks} danger={Boolean(failedTasks)} />
        <MetricCard label="过期任务" value={staleTasks} danger={Boolean(staleTasks)} />
      </section>

      <section className="grid section-gap">
        {healthItems.map((item) => (
          <article className={item.ok === false ? 'card danger-card' : 'card'} key={item.label}>
            <h2>{item.label}</h2>
            <p>{healthLabel(item.ok)}</p>
            <span className="muted small-text">{detailLabel(item.detail)}</span>
          </article>
        ))}
      </section>

      <section className="grid section-gap" data-testid="strategy-automation-summary">
        <MetricCard label="自动策略任务" value={autoProductionTasks.length} hint={`最近保留 ${productionTasks.length} 条生产运行`} />
        <MetricCard label="最近运行状态" value={latestProductionTask ? statusLabel(latestProductionTask.status) : '-'} danger={latestProductionTask?.status === 'failed'} />
        <MetricCard label="最近命中标的" value={latestScan.matched_count ?? '-'} hint={`策略 ${strategyCode(latestProductionTask)}`} />
        <MetricCard label="模拟盘新订单" value={latestProductionOrders} danger={latestProductionBlocked > 0 && latestProductionOrders === 0} />
        <MetricCard label="阻断/跳过" value={`${latestProductionBlocked}/${itemCount(latestPaper.skipped)}`} hint="阻断 / 跳过" danger={latestProductionBlocked > 0} />
        <MetricCard label="策略数据覆盖" value={coverageText(latestProductionTask)} danger={Number(latestProductionResult.local_coverage?.coverage_ratio || 0) > 0 && Number(latestProductionResult.local_coverage?.coverage_ratio || 0) < 0.8} />
        <MetricCard label="快照时效" value={latestSnapshotFreshness?.label || '-'} hint={latestSnapshotFreshness?.time || '等待时效数据'} danger={latestSnapshotFreshness?.tone === 'warning'} />
        <MetricCard label="K线时效" value={latestKlineFreshness?.label || '-'} hint={latestKlineFreshness?.time || '等待时效数据'} danger={latestKlineFreshness?.tone === 'warning'} />
      </section>

      <SectionCard
        title="上线检查"
        subtitle={state.launchCheckError || (launchCheck ? `状态：${launchCheck.status || (launchCheck.ready ? 'ready' : 'not ready')}` : '读取中')}
        actions={<button type="button" className="btn-secondary" onClick={copyLaunchSummary}>复制摘要</button>}
      >
        {launchCheck ? (
          <div className="scan-summary">
            <div className="summary-row"><span>结论</span><StatusBadge tone={launchCheck.ready || launchCheck.passed ? 'success' : 'danger'}>{launchCheck.status || (launchCheck.ready || launchCheck.passed ? '通过' : '失败')}</StatusBadge></div>
            <div className="summary-row"><span>失败 gates</span><strong>{launchGates.filter((gate) => gate.ok === false || gate.passed === false).length}</strong></div>
            {launchGates.map((gate) => (
              <div className="summary-row" key={gate.name}>
                <span>{gate.name}</span>
                <StatusBadge tone={gate.ok === false || gate.passed === false ? 'danger' : 'success'}>{gate.ok === false || gate.passed === false ? '失败' : '通过'}</StatusBadge>
              </div>
            ))}
          </div>
        ) : <div className="empty">{state.launchCheckError || '上线检查暂不可用。'}</div>}
      </SectionCard>

      <SectionCard
        title="自动策略运行"
        subtitle={latestProductionTask ? `最近任务 ${latestProductionTask.id?.slice(0, 8) || '-'}，完成时间 ${latestProductionTask.finished_at || latestProductionTask.created_at || '-'}` : '尚未读取到生产运行任务'}
      >
        {latestProductionWarnings.length ? <div className="alert warning">{latestProductionWarnings[0]}</div> : null}
        <DataTable
          className="strategy-run-table"
          columns={[
            { label: '策略', render: (task) => <strong>{strategyCode(task)}</strong> },
            { label: '触发', render: (task) => <StatusBadge tone={isSystemStrategyTask(task) ? 'success' : 'info'}>{isSystemStrategyTask(task) ? '系统定时' : '人工'}</StatusBadge> },
            { label: '状态', render: (task) => <StatusBadge status={task.lifecycle_status || task.status}>{statusLabel(task.lifecycle_status || task.status)}</StatusBadge> },
            { label: '生产结果', render: (task) => <StatusBadge status={taskResult(task).production_status || task.status}>{productionStatusLabel(taskResult(task).production_status)}</StatusBadge> },
            {
              label: '命中/订单',
              render: (task) => {
                const result = taskResult(task);
                const paper = paperResult(task);
                return `${result.scan?.matched_count ?? '-'} / ${itemCount(paper.orders)}`;
              },
            },
            { label: '数据时效', render: (task) => dataFreshnessNode(task) },
            { label: '阻断/提示', render: (task) => <span className="small-text">{executionNote(task)}</span> },
          ]}
          rows={productionTasks}
          getKey={(task) => task.id}
          emptyText="暂无自动策略运行任务。"
        />
      </SectionCard>

      <SectionCard
        title="任务中心"
        actions={(
          <div className="row-actions">
            <select className="inline-filter" value={taskStatus} onChange={changeStatus} aria-label="任务状态筛选">
              {TASK_STATUSES.map((status) => <option key={status || 'all'} value={status}>{status ? statusLabel(status) : '全部状态'}</option>)}
            </select>
            <select className="inline-filter" value={taskSort} onChange={changeSort} aria-label="任务排序">
              {TASK_SORTS.map((sort) => <option key={sort.value} value={sort.value}>{sort.label}</option>)}
            </select>
            <button type="button" className="btn-secondary" onClick={() => changePage(taskPage - 1)} disabled={taskPage <= 1}>上一页</button>
            <button type="button" className="btn-secondary" onClick={() => changePage(taskPage + 1)} disabled={taskPage >= pageCount}>下一页</button>
          </div>
        )}
      >
        <DataTable
          className="task-ops-table"
          columns={[
            { label: '任务', render: (task) => task.name || task.id },
            { label: '状态', render: (task) => <StatusBadge status={task.lifecycle_status || task.status}>{statusLabel(task.lifecycle_status || task.status)}</StatusBadge> },
            { label: '失败类型', render: (task) => failureCategoryLabel(task.failure_category) },
            { label: '耗时', render: (task) => task.duration_seconds == null ? '-' : `${task.duration_seconds}s` },
            { label: '日志摘要', render: (task) => task.error_summary || (task.result_summary?.matched_count ?? '-') },
            {
              label: '操作',
              render: (task) => (
                taskCanCancel(task)
                  ? <button type="button" className="btn-secondary" onClick={() => cancelTask(task)}>取消</button>
                  : <span className="muted">-</span>
              ),
            },
          ]}
          rows={tasks?.items || []}
          emptyText="当前筛选条件下没有任务。"
        />
        <div className="table-footer">
          第 {tasks?.page || taskPage} / {pageCount} 页，共 {tasks?.total || 0} 条
          {Object.keys(failureCounts).length ? `；失败分类 ${JSON.stringify(failureCounts)}` : ''}
        </div>
      </SectionCard>

      <section className="card section-gap">
        <div className="section-title-row">
          <h2>日志摘要</h2>
          <input
            className="inline-filter"
            placeholder="筛选日志"
            value={logKeyword}
            onChange={(event) => setLogKeyword(event.target.value)}
          />
        </div>
        <pre className="code-block">{filteredLogs.length ? filteredLogs.join('\n') : logs?.message || '没有匹配的日志'}</pre>
      </section>
    </main>
  );
}
