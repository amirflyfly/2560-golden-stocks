import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { canAdmin } from '../auth/permissions';

const SECURITY_TYPE_OPTIONS = [
  ['', '全部类型'],
  ['stock', '股票'],
  ['etf', 'ETF'],
  ['index', '指数/板块'],
  ['convertible_bond', '可转债'],
  ['bond', '债券'],
  ['fund', '基金'],
  ['b_share', 'B股'],
];

const BAR_INTERVAL_OPTIONS = [
  ['1d', '日线'],
  ['15m', '15分钟'],
  ['30m', '30分钟'],
  ['5m', '5分钟'],
  ['1h', '60分钟'],
];

const SECURITY_TYPE_LABELS = Object.fromEntries(SECURITY_TYPE_OPTIONS);
const BAR_INTERVAL_LABELS = Object.fromEntries(BAR_INTERVAL_OPTIONS);

function uniqueValues(values) {
  return [...new Set((values || []).map((value) => String(value || '').trim()).filter(Boolean))];
}

function joinValues(values, fallback = '-') {
  const list = uniqueValues(values);
  return list.length ? list.join(', ') : fallback;
}

function latestValue(values) {
  const list = uniqueValues(values).sort();
  return list.length ? list[list.length - 1] : '';
}

function statusBadgeClass(status, synced = false) {
  const normalized = String(status || '').toLowerCase();
  if (['success', 'completed', '已同步'].includes(normalized)) return 'status-badge success';
  if (['failed', 'error'].includes(normalized)) return 'status-badge danger';
  if (['running', 'pending'].includes(normalized)) return 'status-badge info';
  return synced ? 'status-badge success' : 'status-badge warning';
}

function syncStatusLabels(rows, synced) {
  const statuses = uniqueValues((rows || []).map((row) => row.status));
  return statuses.length ? statuses : [synced ? '已同步' : '未同步'];
}

export function MarketSyncPage({ authz }) {
  const [form, setForm] = useState({ symbols: '000001,600519', start_date: '', end_date: '', adjust: 'qfq', interval: '1d', security_type: 'stock', max_symbols: '', batch_size: '' });
  const [state, setState] = useState({
    loading: true,
    submitting: false,
    coverageLoading: true,
    syncStateLoading: true,
    marketHealthLoading: true,
    snapshotLoading: true,
    error: '',
    marketHealthError: '',
    tasks: [],
    coverage: null,
    syncState: null,
    snapshots: null,
    marketHealth: null,
    coverageKeyword: '',
    coverageSource: '',
    coverageSecurityType: 'stock',
    coverageInterval: '1d',
  });
  const mayAdmin = canAdmin(authz);
  const disabledReason = authz?.loading ? '正在确认当前角色权限' : '当前操作需要 admin 角色。';
  const failedTasks = state.tasks.filter((task) => task.status === 'failed');
  const runningTasks = state.tasks.filter((task) => task.status === 'running' || task.status === 'pending');
  const coverageItems = state.coverage?.items || [];
  const coverageSummary = state.coverage?.summary || {};
  const securityTypeCounts = coverageSummary.security_type_counts || {};
  const syncStateItems = state.syncState?.items || [];
  const syncStateSummary = state.syncState?.summary || {};
  const syncStateBySymbol = syncStateItems.reduce((groups, item) => {
    const key = item.symbol || '';
    if (!key) return groups;
    groups[key] = groups[key] || [];
    groups[key].push(item);
    return groups;
  }, {});
  const snapshotItems = state.snapshots?.items || [];
  const snapshotSummary = state.snapshots?.summary || {};
  const marketHealth = state.marketHealth || {};
  const marketOk = marketHealth.ok === true;
  const marketHealthTone = marketOk && !marketHealth.fallback_used && marketHealth.data_quality !== 'mock'
    ? 'success'
    : marketOk ? 'warning' : 'danger';
  const providerChain = Array.isArray(marketHealth.provider_chain) && marketHealth.provider_chain.length
    ? marketHealth.provider_chain.join(' -> ')
    : marketHealth.provider || '-';
  const primaryProvider = marketHealth.primary_provider || marketHealth.provider || '-';
  const actualProvider = marketHealth.actual_provider || marketHealth.provider || '-';
  const dataQuality = marketHealth.data_quality || (marketOk ? 'primary' : 'unknown');
  const marketWarnings = marketHealth.errors || [];

  function load() {
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    api.tasks({ page: 1, page_size: 50 })
      .then((data) => setState((prev) => ({
        ...prev,
        loading: false,
        tasks: (data.items || []).filter((task) => String(task.name || '').startsWith('market.')),
      })))
      .catch((error) => setState((prev) => ({ ...prev, loading: false, error: error.message })));
    api.marketDataHealth()
      .then((data) => setState((prev) => ({ ...prev, marketHealthLoading: false, marketHealth: data, marketHealthError: '' })))
      .catch((error) => setState((prev) => ({ ...prev, marketHealthLoading: false, marketHealthError: error.message })));
    loadCoverage();
    loadSyncState();
    loadSnapshots();
  }

  function loadCoverage(overrides = {}) {
    const keyword = overrides.keyword ?? state.coverageKeyword;
    const source = overrides.source ?? state.coverageSource;
    const securityType = overrides.securityType ?? state.coverageSecurityType;
    const interval = overrides.interval ?? state.coverageInterval;
    setState((prev) => ({ ...prev, coverageLoading: true, coverageKeyword: keyword, coverageSource: source, coverageSecurityType: securityType, coverageInterval: interval }));
    api.marketDataCoverage({ page: 1, page_size: 20, keyword, source, security_type: securityType, interval })
      .then((data) => setState((prev) => ({ ...prev, coverageLoading: false, coverage: data })))
      .catch((error) => setState((prev) => ({ ...prev, coverageLoading: false, error: error.message })));
  }

  function loadSnapshots(overrides = {}) {
    const keyword = overrides.keyword ?? state.coverageKeyword;
    const source = overrides.source ?? state.coverageSource;
    const securityType = overrides.securityType ?? state.coverageSecurityType;
    setState((prev) => ({ ...prev, snapshotLoading: true }));
    api.marketDataSnapshots({ page: 1, page_size: 20, keyword, source, security_type: securityType })
      .then((data) => setState((prev) => ({ ...prev, snapshotLoading: false, snapshots: data })))
      .catch((error) => setState((prev) => ({ ...prev, snapshotLoading: false, error: error.message })));
  }

  function loadSyncState(overrides = {}) {
    const keyword = overrides.keyword ?? state.coverageKeyword;
    const source = overrides.source ?? state.coverageSource;
    const interval = overrides.interval ?? state.coverageInterval;
    setState((prev) => ({ ...prev, syncStateLoading: true }));
    api.marketDataSyncState({ page: 1, page_size: 50, keyword, source, interval })
      .then((data) => setState((prev) => ({ ...prev, syncStateLoading: false, syncState: data })))
      .catch((error) => setState((prev) => ({ ...prev, syncStateLoading: false, error: error.message })));
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!runningTasks.length) return undefined;
    const timer = window.setInterval(() => load(), 3000);
    return () => window.clearInterval(timer);
  }, [runningTasks.length]);

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
      interval: form.interval,
      security_type: form.security_type,
      max_symbols: Number(form.max_symbols) || 0,
      batch_size: Number(form.batch_size) || 0,
    };
    setState((prev) => ({ ...prev, submitting: true, error: '' }));
    api.createMarketSync(payload)
      .then(() => {
        load();
        window.setTimeout(load, 1500);
      })
      .catch((error) => setState((prev) => ({ ...prev, error: error.message })))
      .finally(() => setState((prev) => ({ ...prev, submitting: false })));
  }

  function syncSnapshots() {
    if (!mayAdmin) {
      setState((prev) => ({ ...prev, error: disabledReason }));
      return;
    }
    const symbols = form.symbols.split(',').map((item) => item.trim()).filter(Boolean);
    if (!symbols.length) {
      setState((prev) => ({ ...prev, error: '请至少输入一个股票代码，或输入 all 同步全市场快照。' }));
      return;
    }
    setState((prev) => ({ ...prev, submitting: true, error: '' }));
    api.createMarketSnapshotSync({ symbols, security_type: form.security_type, max_symbols: Number(form.max_symbols) || 0, batch_size: Number(form.batch_size) || 0 })
      .then(() => {
        load();
        window.setTimeout(load, 1500);
      })
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
          <p className="eyebrow">Data Center</p>
          <h1>数据中心</h1>
          <p className="muted">统一管理本地行情仓、同步任务、数据源健康和每只股票的覆盖截止日。</p>
        </div>
        <button type="button" onClick={load} disabled={state.loading}>刷新</button>
      </div>
      {state.error ? <div className="alert">{state.error}</div> : null}
      {state.marketHealthError ? <div className="alert warning">行情源健康检查失败：{state.marketHealthError}</div> : null}
      {!mayAdmin ? <div className="alert warning">{disabledReason}</div> : null}
      {state.marketHealth && (!marketOk || marketHealth.fallback_used || dataQuality === 'mock') ? (
        <div className="alert warning">
          行情源当前为 {dataQuality}，实际使用 {actualProvider}。
          {marketHealth.fallback_used ? ` 主源 ${primaryProvider} 已发生 fallback。` : ''}
          {marketWarnings.length ? ` 最近错误：${marketWarnings[0]}` : ''}
        </div>
      ) : null}
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
        <article className="card"><h2>行情源健康</h2><p><span className={`status-badge ${marketHealthTone}`}>{state.marketHealthLoading ? 'checking' : marketOk ? 'healthy' : 'unhealthy'}</span></p></article>
        <article className="card"><h2>主行情源</h2><p>{primaryProvider}</p></article>
        <article className="card"><h2>实际数据源</h2><p>{actualProvider}</p></article>
        <article className="card"><h2>数据质量</h2><p>{dataQuality}</p></article>
      </section>

      <section className="grid section-gap">
        <article className="card"><h2>Provider Chain</h2><p>{providerChain}</p></article>
        <article className="card"><h2>Fallback</h2><p>{marketHealth.fallback_used ? '已降级' : '未降级'}</p></article>
        <article className="card"><h2>健康详情</h2><p>{marketHealth.message || '-'}</p></article>
      </section>

      <section className="grid section-gap">
        <article className="card"><h2>同步任务</h2><p>{state.tasks.length}</p></article>
        <article className="card"><h2>运行/等待</h2><p>{runningTasks.length}</p></article>
        <article className={failedTasks.length ? 'card danger-card' : 'card'}><h2>失败任务</h2><p>{failedTasks.length}</p></article>
      </section>

      <section className="grid section-gap">
        <article className="card"><h2>本地证券</h2><p>{coverageSummary.security_count ?? '-'}</p></article>
        <article className="card"><h2>本地股票</h2><p>{coverageSummary.stock_count ?? '-'}</p></article>
        <article className="card"><h2>已同步标的</h2><p>{coverageSummary.synced_symbols ?? '-'}</p></article>
        <article className="card"><h2>同步状态</h2><p>{syncStateSummary.success_count ?? '-'} / {syncStateSummary.state_count ?? '-'}</p></article>
        <article className="card"><h2>K线周期</h2><p>{BAR_INTERVAL_LABELS[coverageSummary.interval || state.coverageInterval] || coverageSummary.interval || state.coverageInterval}</p></article>
        <article className="card"><h2>最新截止日</h2><p>{coverageSummary.last_trade_date || '-'}</p></article>
        <article className="card"><h2>最近同步</h2><p>{syncStateSummary.last_synced_at || '-'}</p></article>
        <article className="card"><h2>实时快照</h2><p>{snapshotSummary.snapshot_count ?? '-'}</p></article>
      </section>

      <section className="card section-gap">
        <div className="section-title-row">
          <h2>证券类型分布</h2>
          <span className="status-badge info">mootdx typed universe</span>
        </div>
        <div className="type-count-strip">
          {Object.entries(securityTypeCounts).map(([type, count]) => (
            <span className="data-badge info" key={type}>{SECURITY_TYPE_LABELS[type] || type}: {count}</span>
          ))}
          {Object.keys(securityTypeCounts).length ? null : <span className="muted">暂无类型统计</span>}
        </div>
      </section>

      <form className="toolbar section-gap" onSubmit={submit}>
        <label>标的代码
          <input value={form.symbols} placeholder="000001,600519 或 all" onChange={(event) => setForm({ ...form, symbols: event.target.value })} />
        </label>
        <label>证券类型
          <select value={form.security_type} onChange={(event) => setForm({ ...form, security_type: event.target.value })}>
            {SECURITY_TYPE_OPTIONS.map(([value, label]) => <option key={value || 'all'} value={value}>{label}</option>)}
          </select>
        </label>
        <label>K线周期
          <select
            value={form.interval}
            onChange={(event) => {
              const interval = event.target.value;
              setForm({ ...form, interval, adjust: interval === '1d' ? form.adjust : 'none' });
            }}
          >
            {BAR_INTERVAL_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
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
            <option value="none">不复权</option>
          </select>
        </label>
        <label>上限
          <input type="number" min="0" max="20000" placeholder="all 时可限制" value={form.max_symbols} onChange={(event) => setForm({ ...form, max_symbols: event.target.value })} />
        </label>
        <label>批大小
          <input type="number" min="0" max="1000" placeholder="all 默认分批" value={form.batch_size} onChange={(event) => setForm({ ...form, batch_size: event.target.value })} />
        </label>
        <button type="submit" disabled={state.submitting || !mayAdmin} title={disabledReason}>创建同步</button>
        <button type="button" className="btn-secondary" onClick={syncSnapshots} disabled={state.submitting || !mayAdmin} title={disabledReason}>同步实时快照</button>
      </form>

      <section className="card section-gap">
        <div className="section-title-row">
          <h2>本地行情覆盖</h2>
          <span className="status-badge info">{coverageSummary.backend || 'local'} / sync {syncStateSummary.success_count ?? '-'}/{syncStateSummary.state_count ?? '-'}</span>
        </div>
        <form className="toolbar local-tool-strip" onSubmit={(event) => { event.preventDefault(); loadCoverage(); loadSyncState(); loadSnapshots(); }}>
          <label>股票搜索
            <input
              value={state.coverageKeyword}
              placeholder="代码或名称"
              onChange={(event) => setState((prev) => ({ ...prev, coverageKeyword: event.target.value }))}
            />
          </label>
          <label>数据源
            <select
              value={state.coverageSource}
              onChange={(event) => {
                const source = event.target.value;
                setState((prev) => ({ ...prev, coverageSource: source }));
                loadCoverage({ source });
                loadSyncState({ source });
                loadSnapshots({ source });
              }}
            >
              <option value="">全部</option>
              <option value="mootdx">mootdx</option>
              <option value="akshare">akshare</option>
              <option value="mock">mock</option>
            </select>
          </label>
          <label>证券类型
            <select
              value={state.coverageSecurityType}
              onChange={(event) => {
                const securityType = event.target.value;
                setState((prev) => ({ ...prev, coverageSecurityType: securityType }));
                loadCoverage({ securityType });
                loadSyncState();
                loadSnapshots({ securityType });
              }}
            >
              {SECURITY_TYPE_OPTIONS.map(([value, label]) => <option key={value || 'all'} value={value}>{label}</option>)}
            </select>
          </label>
          <label>K线周期
            <select
              value={state.coverageInterval}
              onChange={(event) => {
                const interval = event.target.value;
                setState((prev) => ({ ...prev, coverageInterval: interval }));
                loadCoverage({ interval });
                loadSyncState({ interval });
              }}
            >
              {BAR_INTERVAL_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <button type="submit" disabled={state.coverageLoading}>查询覆盖</button>
        </form>
        <div className="table task-table market-coverage-table">
          <div className="table-row table-head"><span>标的</span><span>类型</span><span>同步状态</span><span>覆盖/最新</span><span>K线/复权/来源</span></div>
          {coverageItems.map((item) => {
            const syncRows = syncStateBySymbol[item.symbol] || [];
            const intervals = uniqueValues([...(item.intervals || []), ...syncRows.map((row) => row.interval)]);
            const adjusts = uniqueValues([...(item.adjusts || []), ...syncRows.map((row) => row.adjust)]);
            const sources = uniqueValues([...(item.sources || []), ...syncRows.map((row) => row.source)]);
            const firstCoverage = item.first_trade_date || syncRows.find((row) => row.coverage_start_date)?.coverage_start_date || '-';
            const lastCoverage = item.last_trade_date || syncRows.find((row) => row.coverage_end_date)?.coverage_end_date || '-';
            const latestTradeTime = item.last_trade_time || latestValue(syncRows.map((row) => row.last_success_trade_date)) || lastCoverage;
            const lastSyncedAt = latestValue(syncRows.map((row) => row.last_synced_at));
            return (
              <div className="table-row" key={item.symbol}>
                <span>{item.symbol} / {item.name || '-'}</span>
                <span><span className="data-badge info small-text">{SECURITY_TYPE_LABELS[item.security_type] || item.security_type || '-'}</span></span>
                <span>
                  {syncStatusLabels(syncRows, item.synced).map((status) => (
                    <span className={statusBadgeClass(status, item.synced)} key={status}>{status}</span>
                  ))}
                  {state.syncStateLoading ? <small className="muted">刷新中</small> : null}
                </span>
                <span>{firstCoverage} 至 {lastCoverage}<br /><small className="muted">最新 {latestTradeTime || '-'}</small></span>
                <span>{item.bar_count} 根 / {joinValues(intervals, state.coverageInterval)} / {joinValues(adjusts)}<br /><small className="muted">来源 {joinValues(sources)} / 最近同步 {lastSyncedAt || '-'}</small></span>
              </div>
            );
          })}
          {coverageItems.length ? null : <div className="empty">{state.coverageLoading ? '正在读取本地覆盖...' : '暂无本地行情覆盖记录'}</div>}
        </div>
      </section>

      <section className="card section-gap">
        <div className="section-title-row">
          <h2>实时快照</h2>
          <span className="status-badge info">{(snapshotSummary.sources || []).join(', ') || 'local'}</span>
        </div>
        <div className="table task-table market-snapshot-table">
          <div className="table-row table-head"><span>标的</span><span>类型</span><span>最新价</span><span>成交量/额</span><span>快照时间</span><span>来源</span></div>
          {snapshotItems.map((item) => (
            <div className="table-row" key={item.symbol}>
              <span>{item.symbol} / {item.name || '-'}</span>
              <span>{SECURITY_TYPE_LABELS[item.security_type] || item.security_type || '-'}</span>
              <span>{item.last_price ?? '-'}</span>
              <span>{item.volume ?? '-'} / {item.amount ?? '-'}</span>
              <span>{item.trade_time || item.updated_at || '-'}</span>
              <span>{item.source || '-'}</span>
            </div>
          ))}
          {snapshotItems.length ? null : <div className="empty">{state.snapshotLoading ? '正在读取实时快照...' : '暂无实时快照，请先同步。'}</div>}
        </div>
      </section>

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
