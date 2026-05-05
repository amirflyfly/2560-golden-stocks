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

export function MonitoringPage() {
  const [state, setState] = useState({ loading: true, error: '', overview: null, metrics: null, logs: null, tasks: null });
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
    ])
      .then(([overview, metrics, logs, tasks]) => setState({ loading: false, error: '', overview, metrics, logs, tasks }))
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

  const { overview, metrics, logs, tasks } = state;
  const healthItems = [
    { label: 'MySQL', ok: overview?.database?.ok, detail: overview?.database?.message || 'ok' },
    { label: 'Redis', ok: overview?.cache?.ok, detail: overview?.cache?.backend || overview?.cache?.message || '-' },
    { label: '行情数据', ok: overview?.market_data?.ok, detail: overview?.market_data?.provider || '-' },
  ];
  const unhealthyItems = healthItems.filter((item) => item.ok === false);
  const taskStatusCounts = overview?.tasks?.by_status || {};
  const failureCounts = overview?.tasks?.by_failure_category || {};
  const failedTasks = taskStatusCounts.failed || 0;
  const staleTasks = taskStatusCounts.stale || 0;
  const runningTasks = (taskStatusCounts.running || 0) + (taskStatusCounts.pending || 0) + (taskStatusCounts.retrying || 0);
  const limitUpReturnAlerts = limitUpReturnTransitionAlerts(tasks, logs);
  const pageCount = Math.max(1, Math.ceil((tasks?.total || 0) / (tasks?.page_size || 10)));
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
      {unhealthyItems.length || failedTasks || staleTasks ? (
        <div className="alert observability-alert">
          <strong>需要关注：</strong>
          {unhealthyItems.map((item) => `${item.label} 异常`).join('，')}
          {unhealthyItems.length && (failedTasks || staleTasks) ? '; ' : ''}
          {failedTasks ? `失败任务 ${failedTasks}` : ''}
          {failedTasks && staleTasks ? '; ' : ''}
          {staleTasks ? `过期任务 ${staleTasks}` : ''}
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
