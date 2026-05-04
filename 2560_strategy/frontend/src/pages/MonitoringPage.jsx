import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { DataTable, MetricCard, PageHeader, SectionCard, StatusBadge } from '../components/common';

const TASK_STATUSES = ['', 'queued', 'running', 'retrying', 'succeeded', 'failed', 'canceled', 'stale'];
const TASK_SORTS = [
  { value: 'created_at:desc', label: 'Newest' },
  { value: 'created_at:asc', label: 'Oldest' },
  { value: 'duration_seconds:desc', label: 'Longest' },
  { value: 'failure_category:asc', label: 'Failure type' },
];

function taskCanCancel(task) {
  return ['pending', 'running', 'retrying'].includes(String(task.status || '').toLowerCase());
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
    { label: 'Market data', ok: overview?.market_data?.ok, detail: overview?.market_data?.provider || '-' },
  ];
  const unhealthyItems = healthItems.filter((item) => item.ok === false);
  const taskStatusCounts = overview?.tasks?.by_status || {};
  const failureCounts = overview?.tasks?.by_failure_category || {};
  const failedTasks = taskStatusCounts.failed || 0;
  const staleTasks = taskStatusCounts.stale || 0;
  const runningTasks = (taskStatusCounts.running || 0) + (taskStatusCounts.pending || 0) + (taskStatusCounts.retrying || 0);
  const pageCount = Math.max(1, Math.ceil((tasks?.total || 0) / (tasks?.page_size || 10)));
  const filteredLogs = useMemo(() => {
    const keyword = logKeyword.trim().toLowerCase();
    const lines = logs?.items || [];
    return keyword ? lines.filter((line) => line.toLowerCase().includes(keyword)) : lines;
  }, [logs, logKeyword]);

  return (
    <main className="page">
      <PageHeader
        eyebrow="Monitoring"
        title="Production Monitoring"
        description="Review service health, task lifecycle, failure categories, stale jobs, and sanitized logs."
        actions={<button type="button" onClick={() => load(taskPage, taskStatus, taskSort)} disabled={state.loading}>Refresh</button>}
      />

      {state.error ? <div className="alert" data-testid="monitoring-error">{state.error}</div> : null}
      {unhealthyItems.length || failedTasks || staleTasks ? (
        <div className="alert observability-alert">
          <strong>Attention: </strong>
          {unhealthyItems.map((item) => `${item.label} unhealthy`).join(', ')}
          {unhealthyItems.length && (failedTasks || staleTasks) ? '; ' : ''}
          {failedTasks ? `failed tasks ${failedTasks}` : ''}
          {failedTasks && staleTasks ? '; ' : ''}
          {staleTasks ? `stale tasks ${staleTasks}` : ''}
        </div>
      ) : null}
      {state.loading ? <div className="card loading-card">Loading production state...</div> : null}

      <section className="grid">
        <MetricCard label="Environment" value={overview?.environment || '-'} />
        <MetricCard label="MySQL" value={overview?.database?.ok ? 'normal' : 'unhealthy'} danger={overview?.database?.ok === false} />
        <MetricCard label="Redis" value={overview?.cache?.ok ? overview.cache.backend : 'unhealthy'} danger={overview?.cache?.ok === false} />
        <MetricCard label="Market source" value={overview?.market_data?.provider || '-'} />
      </section>

      <section className="grid section-gap">
        <MetricCard label="Tasks" value={metrics?.tasks_total ?? 0} />
        <MetricCard label="Active" value={runningTasks} />
        <MetricCard label="Failed" value={failedTasks} danger={Boolean(failedTasks)} />
        <MetricCard label="Stale" value={staleTasks} danger={Boolean(staleTasks)} />
      </section>

      <section className="grid section-gap">
        {healthItems.map((item) => (
          <article className={item.ok === false ? 'card danger-card' : 'card'} key={item.label}>
            <h2>{item.label}</h2>
            <p>{item.ok === false ? 'unhealthy' : 'normal'}</p>
            <span className="muted small-text">{item.detail}</span>
          </article>
        ))}
      </section>

      <SectionCard
        title="Task Center"
        actions={(
          <div className="row-actions">
            <select className="inline-filter" value={taskStatus} onChange={changeStatus} aria-label="Task status filter">
              {TASK_STATUSES.map((status) => <option key={status || 'all'} value={status}>{status || 'all statuses'}</option>)}
            </select>
            <select className="inline-filter" value={taskSort} onChange={changeSort} aria-label="Task sort">
              {TASK_SORTS.map((sort) => <option key={sort.value} value={sort.value}>{sort.label}</option>)}
            </select>
            <button type="button" className="btn-secondary" onClick={() => changePage(taskPage - 1)} disabled={taskPage <= 1}>Prev</button>
            <button type="button" className="btn-secondary" onClick={() => changePage(taskPage + 1)} disabled={taskPage >= pageCount}>Next</button>
          </div>
        )}
      >
        <DataTable
          className="task-ops-table"
          columns={[
            { label: 'Task', render: (task) => task.name || task.id },
            { label: 'Status', render: (task) => <StatusBadge status={task.lifecycle_status || task.status}>{task.lifecycle_status || task.status}</StatusBadge> },
            { label: 'Failure', render: (task) => task.failure_category || '-' },
            { label: 'Duration', render: (task) => task.duration_seconds == null ? '-' : `${task.duration_seconds}s` },
            { label: 'Log summary', render: (task) => task.error_summary || (task.result_summary?.matched_count ?? '-') },
            {
              label: 'Action',
              render: (task) => (
                taskCanCancel(task)
                  ? <button type="button" className="btn-secondary" onClick={() => cancelTask(task)}>Cancel</button>
                  : <span className="muted">-</span>
              ),
            },
          ]}
          rows={tasks?.items || []}
          emptyText="No tasks match the current filter."
        />
        <div className="table-footer">
          Page {tasks?.page || taskPage} / {pageCount}, total {tasks?.total || 0}
          {Object.keys(failureCounts).length ? `; failures ${JSON.stringify(failureCounts)}` : ''}
        </div>
      </SectionCard>

      <section className="card section-gap">
        <div className="section-title-row">
          <h2>Log Summary</h2>
          <input
            className="inline-filter"
            placeholder="Filter logs"
            value={logKeyword}
            onChange={(event) => setLogKeyword(event.target.value)}
          />
        </div>
        <pre className="code-block">{filteredLogs.length ? filteredLogs.join('\n') : logs?.message || 'No matching logs'}</pre>
      </section>
    </main>
  );
}
