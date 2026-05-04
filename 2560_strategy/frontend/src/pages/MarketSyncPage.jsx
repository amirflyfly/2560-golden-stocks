import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { canAdmin } from '../auth/permissions';

export function MarketSyncPage({ authz }) {
  const [form, setForm] = useState({ symbols: '000001,600519', start_date: '', end_date: '', adjust: 'qfq' });
  const [state, setState] = useState({ loading: true, submitting: false, error: '', tasks: [] });
  const mayAdmin = canAdmin(authz);
  const disabledReason = authz?.loading ? '正在确认当前角色权限' : '当前操作需要 admin 角色。';
  const failedTasks = state.tasks.filter((task) => task.status === 'failed');
  const runningTasks = state.tasks.filter((task) => task.status === 'running' || task.status === 'pending');

  function load() {
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    api.tasks({ page: 1, page_size: 20, name: 'market.sync' })
      .then((data) => setState((prev) => ({ ...prev, loading: false, tasks: data.items || [] })))
      .catch((error) => setState((prev) => ({ ...prev, loading: false, error: error.message })));
  }

  useEffect(() => {
    load();
  }, []);

  function submit(event) {
    event.preventDefault();
    if (!mayAdmin) {
      setState((prev) => ({ ...prev, error: disabledReason }));
      return;
    }
    const symbols = form.symbols.split(',').map((item) => item.trim()).filter(Boolean);
    if (!symbols.length) {
      setState((prev) => ({ ...prev, error: '请至少输入一个股票代码。' }));
      return;
    }
    if (form.start_date && form.end_date && form.start_date > form.end_date) {
      setState((prev) => ({ ...prev, error: '开始日期不能晚于结束日期。' }));
      return;
    }
    const payload = {
      symbols,
      start_date: form.start_date,
      end_date: form.end_date,
      adjust: form.adjust,
    };
    setState((prev) => ({ ...prev, submitting: true, error: '' }));
    api.createMarketSync(payload)
      .then(() => load())
      .catch((error) => setState((prev) => ({ ...prev, error: error.message })))
      .finally(() => setState((prev) => ({ ...prev, submitting: false })));
  }

  function cancel(taskId) {
    if (!mayAdmin) {
      setState((prev) => ({ ...prev, error: disabledReason }));
      return;
    }
    api.cancelTask(taskId).then(load).catch((error) => setState((prev) => ({ ...prev, error: error.message })));
  }

  return (
    <main className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Market Sync</p>
          <h1>行情同步</h1>
          <p className="muted">创建行情同步任务，查看运行状态、进度与失败原因。</p>
        </div>
        <button type="button" onClick={load} disabled={state.loading}>刷新</button>
      </div>
      {state.error ? <div className="alert">{state.error}</div> : null}
      {!mayAdmin ? <div className="alert warning">{disabledReason}</div> : null}
      {failedTasks.length ? <div className="alert observability-alert">最近同步任务存在 {failedTasks.length} 个失败，请查看失败原因并重试。</div> : null}
      {state.loading ? <div className="card loading-card">正在读取同步任务...</div> : null}

      <section className="card section-gap ops-guide">
        <div className="section-title-row">
          <h2>同步流程</h2>
          <span className="status-badge info">管理员操作</span>
        </div>
        <div className="quick-actions">
          <div className="quick-action"><strong>1. 输入代码</strong><span>多个股票用英文逗号分隔，例如 000001,600519。</span></div>
          <div className="quick-action"><strong>2. 校验区间</strong><span>开始日期不能晚于结束日期，留空则使用默认窗口。</span></div>
          <div className="quick-action"><strong>3. 查看进度</strong><span>任务会显示 pending、running、completed、failed 或 cancelled。</span></div>
        </div>
      </section>

      <section className="grid section-gap">
        <article className="card"><h2>同步任务</h2><p>{state.tasks.length}</p></article>
        <article className="card"><h2>运行/等待</h2><p>{runningTasks.length}</p></article>
        <article className={failedTasks.length ? 'card danger-card' : 'card'}><h2>失败任务</h2><p>{failedTasks.length}</p></article>
      </section>

      <form className="toolbar section-gap" onSubmit={submit}>
        <label>股票代码
          <input value={form.symbols} onChange={(event) => setForm({ ...form, symbols: event.target.value })} />
        </label>
        <label>开始日期
          <input type="date" value={form.start_date} onChange={(event) => setForm({ ...form, start_date: event.target.value })} />
        </label>
        <label>结束日期
          <input type="date" value={form.end_date} onChange={(event) => setForm({ ...form, end_date: event.target.value })} />
        </label>
        <label>复权
          <select value={form.adjust} onChange={(event) => setForm({ ...form, adjust: event.target.value })}>
            <option value="qfq">前复权</option>
            <option value="hfq">后复权</option>
            <option value="">不复权</option>
          </select>
        </label>
        <button type="submit" disabled={state.submitting || !mayAdmin} title={disabledReason}>创建同步</button>
      </form>

      <section className="card">
        <h2>同步任务</h2>
        <div className="table task-table">
          <div className="table-row table-head"><span>任务</span><span>状态</span><span>进度</span><span>时间</span><span>操作</span></div>
          {state.tasks.map((task) => {
            const progress = task.result?.progress || task.result_summary || {};
            return (
              <div className="table-row" key={task.id}>
                <span>{task.id.slice(0, 8)} / {task.name}</span>
                <span><span className={task.status === 'failed' ? 'status-badge danger' : task.status === 'completed' ? 'status-badge success' : task.status === 'cancelled' ? 'status-badge warning' : 'status-badge info'}>{task.status}</span></span>
                <span>{progress.percent ?? '-'}%</span>
                <span>{task.created_at}</span>
                <span>
                  {['pending', 'running'].includes(task.status)
                    ? <button type="button" onClick={() => cancel(task.id)} disabled={!mayAdmin} title={disabledReason}>标记取消</button>
                    : task.error_summary || '-'}
                </span>
              </div>
            );
          })}
          {state.tasks.length ? null : <div className="empty">暂无同步任务</div>}
        </div>
      </section>
    </main>
  );
}
