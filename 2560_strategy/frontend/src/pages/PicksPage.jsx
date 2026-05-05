import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { canWrite, writeDisabledReason } from '../auth/permissions';
import { DataTable, MetricCard, PageHeader, SectionCard, StatusBadge } from '../components/common';

const STATUS_OPTIONS = [
  ['accepted', '待复盘'],
  ['watching', '观察中'],
  ['validated', '已验证'],
  ['rejected', '已淘汰'],
];
const PICKS_SAVED_VIEWS_KEY = '2560_picks_saved_views_v1';
const PICKS_LOCAL_ALERTS_KEY = '2560_picks_local_alerts_v1';

function percent(value) {
  if (value == null || value === '') return '-';
  return `${Number(value).toFixed(2)}%`;
}

function dataQualityLabel(item) {
  const quality = item?.data_quality || 'unknown';
  const source = item?.market_data_source || '-';
  return item?.fallback_used ? `${quality} / ${source} / fallback` : `${quality} / ${source}`;
}

function makeLocalId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function readLocalArray(key) {
  if (typeof window === 'undefined') return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeLocalArray(key, value) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(key, JSON.stringify(value));
}

function refreshNotificationCenter() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent('notifications:refresh'));
}

function normalizeServerPickView(item) {
  return {
    ...item,
    storage: 'server',
    filters: item.metadata?.filters || item.filters || {},
  };
}

function normalizeServerPickAlert(item) {
  const rule = item.rule || {};
  return {
    ...rule,
    id: item.id,
    name: item.name,
    created_at: item.created_at,
    storage: 'server',
  };
}

function pickAlertMatches(rule, item) {
  if (rule.metric === 'watching_high_risk') {
    return Boolean(item.watch_flag || item.status === 'watching') && String(item.risk_level || '').toLowerCase() === 'high';
  }
  if (rule.metric === 'drawdown_abs_gte') return Math.abs(Number(item.drawdown_pct || 0)) >= Number(rule.threshold || 0);
  if (rule.metric === 'holding_days_gte') return Number(item.holding_days || 0) >= Number(rule.threshold || 0);
  if (rule.metric === 'status_eq') return String(item.status || 'accepted') === rule.status;
  return false;
}

export function PicksPage({ onNavigate, authz, pagePayload = {} }) {
  const [items, setItems] = useState([]);
  const [selectedPick, setSelectedPick] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [filters, setFilters] = useState({
    status: pagePayload.status || 'all',
    strategy: pagePayload.strategy_code || 'all',
    risk: 'all',
    source: 'all',
    symbol: pagePayload.symbol || '',
    from_date: '',
    to_date: '',
  });
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingReview, setSavingReview] = useState(false);
  const [form, setForm] = useState({ symbol: '000001', stock_name: '平安银行', source: 'manual', strategy_code: '2560', reason: '' });
  const [reviewForm, setReviewForm] = useState({
    status: 'accepted',
    risk_level: 'pending',
    deal_status: 'pending',
    review_comment: '',
    validation_result: '',
    validation_note: '',
    return_pct: '',
    max_return_pct: '',
    drawdown_pct: '',
    holding_days: '',
    watch_flag: false,
  });
  const [batchForm, setBatchForm] = useState({ status: 'watching', risk_level: '', deal_status: '', watch_flag: true });
  const [savingBatch, setSavingBatch] = useState(false);
  const [savedViews, setSavedViews] = useState([]);
  const [viewName, setViewName] = useState('');
  const [localAlerts, setLocalAlerts] = useState([]);
  const [alertForm, setAlertForm] = useState({
    name: '观察中高风险提醒',
    metric: 'watching_high_risk',
    threshold: 5,
    status: 'watching',
  });
  const mayWrite = canWrite(authz);
  const disabledReason = writeDisabledReason(authz);

  useEffect(() => {
    setFilters((prev) => ({
      ...prev,
      status: pagePayload.status || prev.status || 'all',
      strategy: pagePayload.strategy_code || prev.strategy || 'all',
      symbol: pagePayload.symbol || prev.symbol || '',
    }));
  }, [pagePayload.status, pagePayload.strategy_code, pagePayload.symbol]);

  async function loadSavedTools() {
    const localViews = readLocalArray(PICKS_SAVED_VIEWS_KEY).map((item) => ({ ...item, storage: item.storage || 'local' }));
    const localRules = readLocalArray(PICKS_LOCAL_ALERTS_KEY).map((item) => ({ ...item, storage: item.storage || 'local' }));
    try {
      const [serverViews, serverRules] = await Promise.all([api.savedViews(), api.alertRules()]);
      const pickViews = (serverViews.items || [])
        .filter((item) => item.page === 'picks' || item.metadata?.page === 'picks')
        .map(normalizeServerPickView);
      const pickRules = (serverRules.items || [])
        .filter((item) => item.scope === 'picks' || item.metadata?.page === 'picks')
        .map(normalizeServerPickAlert);
      setSavedViews([...pickViews, ...localViews].slice(0, 16));
      setLocalAlerts([...pickRules, ...localRules].slice(0, 16));
    } catch {
      setSavedViews(localViews);
      setLocalAlerts(localRules);
    }
  }

  useEffect(() => {
    loadSavedTools();
  }, []);

  async function loadPicks() {
    setLoading(true);
    try {
      const query = { page: 1, page_size: 50 };
      Object.entries(filters).forEach(([key, value]) => {
        if (value && value !== 'all') query[key] = value;
      });
      const data = await api.picks(query);
      setItems(data.items || []);
      setSelectedIds((prev) => prev.filter((id) => (data.items || []).some((item) => item.id === id)));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function createPick(event) {
    event.preventDefault();
    if (!mayWrite) {
      setError(disabledReason);
      return;
    }
    setError('');
    setMessage('');
    try {
      const item = await api.createPick({ ...form, trade_date: new Date().toISOString().slice(0, 10) });
      await loadPicks();
      setMessage(`${item.symbol} 已加入或更新选股池。`);
    } catch (err) {
      setError(err.message);
    }
  }

  function fillReviewForm(item) {
    setSelectedPick(item);
    setReviewForm({
      status: item.status || 'accepted',
      risk_level: item.risk_level || 'pending',
      deal_status: item.deal_status || 'pending',
      review_comment: item.review_comment || '',
      validation_result: item.validation_result || '',
      validation_note: item.validation_note || '',
      return_pct: item.return_pct ?? '',
      max_return_pct: item.max_return_pct ?? '',
      drawdown_pct: item.drawdown_pct ?? '',
      holding_days: item.holding_days ?? '',
      watch_flag: Boolean(item.watch_flag),
    });
    api.pickTimeline(item.id)
      .then((data) => setTimeline(data.items || []))
      .catch(() => setTimeline([]));
  }

  async function saveReview(event) {
    event.preventDefault();
    if (!selectedPick) return;
    if (!mayWrite) {
      setError(disabledReason);
      return;
    }
    setSavingReview(true);
    setError('');
    setMessage('');
    try {
      const updated = await api.updatePickReview(selectedPick.id, reviewForm);
      setSelectedPick(updated);
      setItems((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      const nextTimeline = await api.pickTimeline(updated.id);
      setTimeline(nextTimeline.items || []);
      setMessage(`${updated.symbol} 复盘已更新。`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingReview(false);
    }
  }

  function togglePickSelection(pickId) {
    setSelectedIds((prev) => (
      prev.includes(pickId) ? prev.filter((id) => id !== pickId) : [...prev, pickId]
    ));
  }

  function selectBoardStatus(status) {
    setSelectedIds([]);
    setFilters((prev) => ({ ...prev, status }));
  }

  function selectBoardItems(status) {
    const ids = items.filter((item) => String(item.status || 'accepted') === status).map((item) => item.id).filter(Boolean);
    setFilters((prev) => ({ ...prev, status }));
    setSelectedIds(ids);
  }

  async function saveBatchReview(event) {
    event.preventDefault();
    if (!selectedIds.length) {
      setError('请先选择候选。');
      return;
    }
    if (!mayWrite) {
      setError(disabledReason);
      return;
    }
    setSavingBatch(true);
    setError('');
    setMessage('');
    try {
      const payload = {
        ids: selectedIds,
        status: batchForm.status,
        watch_flag: batchForm.watch_flag,
        ...(batchForm.risk_level ? { risk_level: batchForm.risk_level } : {}),
        ...(batchForm.deal_status ? { deal_status: batchForm.deal_status } : {}),
      };
      const result = await api.batchUpdatePickReview(payload);
      await loadPicks();
      setSelectedIds([]);
      setMessage(`批量复盘已更新 ${result.updated} 条候选。`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingBatch(false);
    }
  }

  async function saveCurrentView() {
    const createdAt = new Date().toLocaleString('zh-CN', { hour12: false });
    const name = viewName.trim() || `选股池视图 ${createdAt}`;
    const nextView = {
      id: makeLocalId('picks-view'),
      name,
      created_at: createdAt,
      filters,
      storage: 'local',
    };
    if (mayWrite) {
      try {
        const saved = await api.createSavedView({
          name,
          page: 'picks',
          filters,
          metadata: { page: 'picks', filters },
        });
        const serverView = normalizeServerPickView(saved);
        setSavedViews((prev) => [serverView, ...prev.filter((item) => item.id !== serverView.id && item.name !== name)].slice(0, 16));
        setViewName('');
        setMessage(`服务端保存：选股池视图“${name}”已保存到当前账号，可跨浏览器读取。`);
        return;
      } catch (err) {
        setMessage(`服务端保存失败，已回退到本地浏览器：${err.message}`);
      }
    }
    const nextViews = [nextView, ...savedViews.filter((item) => item.name !== name)].slice(0, 8);
    setSavedViews(nextViews);
    writeLocalArray(PICKS_SAVED_VIEWS_KEY, nextViews.filter((item) => item.storage !== 'server'));
    setViewName('');
    setMessage(`本地保存：选股池视图“${name}”已保存到当前浏览器 localStorage，不会同步到后端。`);
  }

  function applySavedView(view) {
    setFilters((prev) => ({ ...prev, ...(view.filters || {}) }));
    setMessage(`已应用${view.storage === 'server' ? '服务端' : '本地'}保存视图“${view.name}”。`);
  }

  async function deleteSavedView(viewId) {
    const target = savedViews.find((item) => item.id === viewId);
    if (target?.storage === 'server' && mayWrite) {
      try {
        await api.deleteSavedView(viewId);
      } catch (err) {
        setError(err.message);
        return;
      }
    }
    const nextViews = savedViews.filter((item) => item.id !== viewId);
    setSavedViews(nextViews);
    writeLocalArray(PICKS_SAVED_VIEWS_KEY, nextViews.filter((item) => item.storage !== 'server'));
  }

  async function saveLocalAlert(event) {
    event.preventDefault();
    const name = alertForm.name.trim() || '选股池提醒规则';
    const nextRule = {
      ...alertForm,
      id: makeLocalId('picks-alert'),
      name,
      created_at: new Date().toLocaleString('zh-CN', { hour12: false }),
      storage: 'local',
    };
    if (mayWrite) {
      try {
        const saved = await api.createAlertRule({
          name,
          scope: 'picks',
          target: 'picks',
          rule: alertForm,
          channels: ['in_app'],
          enabled: true,
          metadata: { page: 'picks', evaluation: 'worker_scheduled', fallback: 'client_visible_list' },
        });
        const serverRule = normalizeServerPickAlert(saved);
        setLocalAlerts((prev) => [serverRule, ...prev.filter((item) => item.id !== serverRule.id && item.name !== name)].slice(0, 16));
        api.evaluateNotifications({ scope: 'picks', source: 'picks_page', channel: 'in_app' })
          .catch(() => null)
          .then(refreshNotificationCenter);
        setMessage(`服务端提醒规则“${name}”已保存；worker 会后台定时评估并通过通知中心投递，已尝试触发一次立即评估。`);
        return;
      } catch (err) {
        setMessage(`服务端提醒保存失败，已回退到本地浏览器：${err.message}；本地回退仅在本机页面加载或刷新候选列表时计算，不会后台推送。`);
      }
    }
    const nextRules = [nextRule, ...localAlerts.filter((item) => item.name !== name)].slice(0, 8);
    setLocalAlerts(nextRules);
    writeLocalArray(PICKS_LOCAL_ALERTS_KEY, nextRules.filter((item) => item.storage !== 'server'));
    setMessage(`本地回退提醒规则“${name}”已保存到当前浏览器 localStorage；仅在本机页面加载或刷新候选列表时计算，不会后台推送。`);
  }

  async function deleteLocalAlert(ruleId) {
    const target = localAlerts.find((item) => item.id === ruleId);
    if (target?.storage === 'server' && mayWrite) {
      try {
        await api.deleteAlertRule(ruleId);
        refreshNotificationCenter();
      } catch (err) {
        setError(err.message);
        return;
      }
    }
    const nextRules = localAlerts.filter((item) => item.id !== ruleId);
    setLocalAlerts(nextRules);
    writeLocalArray(PICKS_LOCAL_ALERTS_KEY, nextRules.filter((item) => item.storage !== 'server'));
  }

  useEffect(() => {
    loadPicks();
  }, [filters.status, filters.strategy, filters.risk, filters.source, filters.symbol, filters.from_date, filters.to_date]);

  const filteredItems = useMemo(() => items.filter((item) => {
    if (filters.status !== 'all' && String(item.status || '') !== filters.status) return false;
    if (filters.strategy !== 'all' && String(item.strategy_code || '') !== filters.strategy) return false;
    if (filters.risk !== 'all' && String(item.risk_level || '') !== filters.risk) return false;
    if (filters.symbol && String(item.symbol || '') !== filters.symbol) return false;
    return true;
  }), [items, filters]);

  const localAlertHits = useMemo(() => localAlerts.filter((rule) => rule.storage !== 'server').map((rule) => {
    const matches = filteredItems.filter((item) => pickAlertMatches(rule, item));
    return { rule, matches, total: matches.length };
  }).filter((item) => item.total > 0), [localAlerts, filteredItems]);

  const metrics = useMemo(() => {
    const watching = items.filter((item) => item.watch_flag || item.status === 'watching').length;
    const reviewed = items.filter((item) => ['validated', 'rejected'].includes(String(item.status || ''))).length;
    const highRisk = items.filter((item) => String(item.risk_level || '').toLowerCase() === 'high').length;
    const wins = items.filter((item) => Number(item.return_pct) > 0).length;
    return { watching, reviewed, highRisk, wins };
  }, [items]);

  const board = useMemo(() => {
    const countStatus = (status) => items.filter((item) => String(item.status || 'accepted') === status).length;
    return [
      { status: 'accepted', title: '待复盘', count: countStatus('accepted'), hint: '扫描或人工入池后等待确认' },
      { status: 'watching', title: '观察中', count: countStatus('watching'), hint: '需要持续跟踪 T+1/T+5' },
      { status: 'validated', title: '已验证', count: countStatus('validated'), hint: '已有复盘结论的有效样本' },
      { status: 'rejected', title: '已淘汰', count: countStatus('rejected'), hint: '不再继续跟踪的样本' },
    ];
  }, [items]);

  const strategies = [...new Set(items.map((item) => item.strategy_code).filter(Boolean))];
  const risks = [...new Set(items.map((item) => item.risk_level).filter(Boolean))];

  return (
    <main className="page">
      <PageHeader
        eyebrow="Picks"
        title="选股池"
        description="承接扫描结果和人工录入，集中完成观察、验证、淘汰和成交复盘。"
      />
      {error ? <div className="alert">{error}</div> : null}
      {message ? <div className="alert success">{message}</div> : null}
      {!mayWrite ? <div className="alert warning">{disabledReason}</div> : null}

      <section className="grid">
        <MetricCard label="候选总数" value={items.length} hint="当前页未归档记录" />
        <MetricCard label="观察中" value={metrics.watching} hint="watch_flag 或 watching" />
        <MetricCard label="已复盘" value={metrics.reviewed} hint="已验证或已淘汰" />
        <MetricCard label="盈利样本" value={metrics.wins} />
        <MetricCard label="高风险" value={metrics.highRisk} danger={metrics.highRisk > 0} />
      </section>

      <SectionCard title="观察池看板" className="section-gap">
        <div className="kanban-grid">
          {board.map((column) => (
            <div className={filters.status === column.status ? 'kanban-column active' : 'kanban-column'} key={column.status}>
              <span>{column.title}</span>
              <strong>{column.count}</strong>
              <small>{column.hint}</small>
              <div className="row-actions">
                <button type="button" className="btn-secondary" onClick={() => selectBoardStatus(column.status)}>筛选</button>
                <button type="button" className="btn-secondary" onClick={() => selectBoardItems(column.status)} disabled={!column.count}>全选本列</button>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      {selectedIds.length ? (
        <div className="alert warning">
          即将批量更新 {selectedIds.length} 条候选。请确认筛选条件、状态和风险等级后再保存，批量复盘会写入审计日志。
        </div>
      ) : null}

      <form className="toolbar section-gap" onSubmit={saveBatchReview}>
        <label>
          已选候选
          <input value={`${selectedIds.length} 条`} readOnly />
        </label>
        <label>
          批量状态
          <select value={batchForm.status} onChange={(event) => setBatchForm((prev) => ({ ...prev, status: event.target.value }))}>
            {STATUS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>
          风险等级
          <select value={batchForm.risk_level} onChange={(event) => setBatchForm((prev) => ({ ...prev, risk_level: event.target.value }))}>
            <option value="">保持不变</option>
            <option value="pending">待定</option>
            <option value="low">低</option>
            <option value="medium">中</option>
            <option value="high">高</option>
          </select>
        </label>
        <label>
          成交状态
          <select value={batchForm.deal_status} onChange={(event) => setBatchForm((prev) => ({ ...prev, deal_status: event.target.value }))}>
            <option value="">保持不变</option>
            <option value="pending">待确认</option>
            <option value="watched">仅观察</option>
            <option value="dealt">已成交</option>
            <option value="missed">错过</option>
          </select>
        </label>
        <label className="checkbox-field">
          <input type="checkbox" checked={batchForm.watch_flag} onChange={(event) => setBatchForm((prev) => ({ ...prev, watch_flag: event.target.checked }))} />
          同步观察标记
        </label>
        <button type="submit" disabled={savingBatch || !selectedIds.length || !mayWrite} title={disabledReason}>
          {savingBatch ? '批量保存中...' : '批量复盘'}
        </button>
        <button type="button" className="btn-secondary" onClick={() => setSelectedIds([])}>清空选择</button>
      </form>

      <form className="toolbar section-gap" onSubmit={createPick}>
        <label>
          股票代码
          <input value={form.symbol} onChange={(event) => setForm((prev) => ({ ...prev, symbol: event.target.value }))} />
        </label>
        <label>
          股票名称
          <input value={form.stock_name} onChange={(event) => setForm((prev) => ({ ...prev, stock_name: event.target.value }))} />
        </label>
        <label>
          来源
          <select value={form.source} onChange={(event) => setForm((prev) => ({ ...prev, source: event.target.value }))}>
            <option value="manual">人工录入</option>
            <option value="scan">策略扫描</option>
            <option value="backtest">回测验证</option>
          </select>
        </label>
        <label>
          策略
          <select value={form.strategy_code} onChange={(event) => setForm((prev) => ({ ...prev, strategy_code: event.target.value }))}>
            <option value="2560">2560</option>
            <option value="first_limit_up">首板涨停</option>
          </select>
        </label>
        <label className="wide-field">
          入池原因
          <input value={form.reason} onChange={(event) => setForm((prev) => ({ ...prev, reason: event.target.value }))} />
        </label>
        <button type="submit" disabled={!mayWrite} title={disabledReason}>加入选股池</button>
        <button type="button" className="btn-secondary" onClick={loadPicks}>刷新</button>
      </form>

      <section className="toolbar">
        <label>
          复盘状态
          <select value={filters.status} onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))}>
            <option value="all">全部</option>
            {STATUS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>
          策略
          <select value={filters.strategy} onChange={(event) => setFilters((prev) => ({ ...prev, strategy: event.target.value }))}>
            <option value="all">全部</option>
            {strategies.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label>
          风险
          <select value={filters.risk} onChange={(event) => setFilters((prev) => ({ ...prev, risk: event.target.value }))}>
            <option value="all">全部</option>
            {risks.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label>
          来源
          <select value={filters.source} onChange={(event) => setFilters((prev) => ({ ...prev, source: event.target.value }))}>
            <option value="all">全部</option>
            <option value="manual">人工录入</option>
            <option value="scan">策略扫描</option>
            <option value="backtest">回测验证</option>
          </select>
        </label>
        <label>
          开始日期
          <input type="date" value={filters.from_date} onChange={(event) => setFilters((prev) => ({ ...prev, from_date: event.target.value }))} />
        </label>
        <label>
          结束日期
          <input type="date" value={filters.to_date} onChange={(event) => setFilters((prev) => ({ ...prev, to_date: event.target.value }))} />
        </label>
      </section>

      <SectionCard
        title="保存视图 / 提醒规则"
        subtitle="优先保存到服务端账号；服务端提醒由 worker 后台定时评估，并通过通知中心投递。服务端不可用时回退到 localStorage，仅本机页面计算。"
      >
        <div className="toolbar compact-toolbar local-tool-strip">
          <label>
            视图名称
            <input value={viewName} onChange={(event) => setViewName(event.target.value)} placeholder="例如：观察中高风险" />
          </label>
          <button type="button" onClick={saveCurrentView}>保存当前视图</button>
          <span className="muted">当前视图：状态 {filters.status}，策略 {filters.strategy}，风险 {filters.risk}，来源 {filters.source}</span>
        </div>
        {savedViews.length ? (
          <div className="quick-actions local-view-list">
            {savedViews.map((view) => (
              <div className="quick-action local-view-card" key={view.id}>
                <strong>{view.name}</strong>
                <span>{view.storage === 'server' ? '服务端保存于' : '本地保存于'} {view.created_at}</span>
                <small>状态 {view.filters?.status || 'all'} / 策略 {view.filters?.strategy || 'all'} / 风险 {view.filters?.risk || 'all'}</small>
                <div className="row-actions">
                  <button type="button" className="btn-secondary" onClick={() => applySavedView(view)}>应用</button>
                  <button type="button" className="btn-secondary" onClick={() => deleteSavedView(view.id)}>删除</button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty compact-empty">暂无保存视图。</div>
        )}

        <form className="toolbar compact-toolbar local-alert-form" onSubmit={saveLocalAlert}>
          <label>
            规则名称
            <input value={alertForm.name} onChange={(event) => setAlertForm((prev) => ({ ...prev, name: event.target.value }))} />
          </label>
          <label>
            提醒条件
            <select value={alertForm.metric} onChange={(event) => setAlertForm((prev) => ({ ...prev, metric: event.target.value }))}>
              <option value="watching_high_risk">观察中且高风险</option>
              <option value="drawdown_abs_gte">回撤绝对值大于等于</option>
              <option value="holding_days_gte">持有天数大于等于</option>
              <option value="status_eq">状态等于</option>
            </select>
          </label>
          {['drawdown_abs_gte', 'holding_days_gte'].includes(alertForm.metric) ? (
            <label>
              阈值
              <input type="number" value={alertForm.threshold} onChange={(event) => setAlertForm((prev) => ({ ...prev, threshold: event.target.value }))} />
            </label>
          ) : null}
          {alertForm.metric === 'status_eq' ? (
            <label>
              状态
              <select value={alertForm.status} onChange={(event) => setAlertForm((prev) => ({ ...prev, status: event.target.value }))}>
                {STATUS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
          ) : null}
          <button type="submit">保存提醒规则</button>
        </form>

        {localAlerts.length ? (
          <div className="local-alert-list">
            {localAlerts.map((rule) => (
              <div className="local-alert-rule" key={rule.id}>
                <span><strong>{rule.name}</strong> {rule.storage === 'server' ? '服务端规则 · worker 后台评估 · 通知中心投递' : '本地回退规则 · 仅本机计算'}</span>
                <button type="button" className="btn-secondary" onClick={() => deleteLocalAlert(rule.id)}>删除</button>
              </div>
            ))}
          </div>
        ) : null}
        {localAlertHits.length ? (
          <div className="alert warning section-gap">
            {localAlertHits.map(({ rule, matches, total }) => (
              <div key={rule.id}>
                本地回退提醒命中“{rule.name}”：{total} 条。{matches.slice(0, 4).map((item) => `${item.symbol} ${item.stock_name}`).join('、')}
              </div>
            ))}
          </div>
        ) : (
          <div className="empty compact-empty">当前候选未命中本地回退提醒规则，或尚无本地回退规则。</div>
        )}
      </SectionCard>

      <section className="dashboard-layout section-gap">
        <SectionCard title="候选列表">
          {loading ? <div className="card loading-card">正在加载候选...</div> : null}
          <DataTable
            className="picks-table"
            columns={[
              {
                label: '选择',
                render: (item) => (
                  <input
                    type="checkbox"
                    aria-label={`选择 ${item.symbol}`}
                    checked={selectedIds.includes(item.id)}
                    onChange={() => togglePickSelection(item.id)}
                  />
                ),
              },
              { label: '股票', render: (item) => <strong>{item.symbol} {item.stock_name}</strong> },
              { label: '策略', render: (item) => item.strategy_code || '-' },
              { label: '来源', render: (item) => item.source || '-' },
              { label: '入池理由', render: (item) => item.reason || item.note || '-' },
              { label: 'Data', render: (item) => <StatusBadge status={item.data_quality}>{dataQualityLabel(item)}</StatusBadge> },
              { label: '状态', render: (item) => <StatusBadge status={item.status}>{item.status || 'accepted'}</StatusBadge> },
              { label: '风险', render: (item) => <StatusBadge status={item.risk_level}>{item.risk_level || 'pending'}</StatusBadge> },
              {
                label: '操作',
                render: (item) => (
                  <div className="row-actions">
                    <button type="button" className="btn-secondary" onClick={() => fillReviewForm(item)}>复盘</button>
                    <button type="button" className="btn-secondary" onClick={() => onNavigate?.('kline', { symbol: item.symbol })}>K 线</button>
                  </div>
                ),
              },
            ]}
            rows={filteredItems}
            getKey={(item, index) => item.id || `${item.symbol}-${item.trade_date}-${index}`}
            emptyText="暂无选股记录。可从扫描结果一键加入，也可以在上方人工录入。"
          />
        </SectionCard>

        <article className="panel-card">
          <h2>复盘详情</h2>
          {selectedPick ? (
            <form className="scan-form" onSubmit={saveReview}>
              <div className="summary-row"><span>标的</span><strong>{selectedPick.symbol} {selectedPick.stock_name}</strong></div>
              <div className="summary-row"><span>Data quality</span><strong>{dataQualityLabel(selectedPick)}</strong></div>
              <label className="form-field">
                状态
                <select className="scan-select" value={reviewForm.status} onChange={(event) => setReviewForm((prev) => ({ ...prev, status: event.target.value }))}>
                  {STATUS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              <label className="form-field">
                风险等级
                <select className="scan-select" value={reviewForm.risk_level} onChange={(event) => setReviewForm((prev) => ({ ...prev, risk_level: event.target.value }))}>
                  <option value="pending">待定</option>
                  <option value="low">低</option>
                  <option value="medium">中</option>
                  <option value="high">高</option>
                </select>
              </label>
              <label className="form-field">
                成交状态
                <select className="scan-select" value={reviewForm.deal_status} onChange={(event) => setReviewForm((prev) => ({ ...prev, deal_status: event.target.value }))}>
                  <option value="pending">待确认</option>
                  <option value="watched">仅观察</option>
                  <option value="dealt">已成交</option>
                  <option value="missed">错过</option>
                </select>
              </label>
              <label className="form-field">
                收益 %
                <input className="scan-input" type="number" step="0.01" value={reviewForm.return_pct} onChange={(event) => setReviewForm((prev) => ({ ...prev, return_pct: event.target.value }))} />
              </label>
              <label className="form-field">
                最大收益 %
                <input className="scan-input" type="number" step="0.01" value={reviewForm.max_return_pct} onChange={(event) => setReviewForm((prev) => ({ ...prev, max_return_pct: event.target.value }))} />
              </label>
              <label className="form-field">
                回撤 %
                <input className="scan-input" type="number" step="0.01" value={reviewForm.drawdown_pct} onChange={(event) => setReviewForm((prev) => ({ ...prev, drawdown_pct: event.target.value }))} />
              </label>
              <label className="form-field">
                持有天数
                <input className="scan-input" type="number" min="0" value={reviewForm.holding_days} onChange={(event) => setReviewForm((prev) => ({ ...prev, holding_days: event.target.value }))} />
              </label>
              <label className="checkbox-field">
                <input type="checkbox" checked={reviewForm.watch_flag} onChange={(event) => setReviewForm((prev) => ({ ...prev, watch_flag: event.target.checked }))} />
                加入观察
              </label>
              <label className="form-field">
                复盘结论
                <textarea className="scan-input" rows="3" value={reviewForm.review_comment} onChange={(event) => setReviewForm((prev) => ({ ...prev, review_comment: event.target.value }))} />
              </label>
              <label className="form-field">
                验证结果
                <input className="scan-input" value={reviewForm.validation_result} onChange={(event) => setReviewForm((prev) => ({ ...prev, validation_result: event.target.value }))} />
              </label>
              <label className="form-field">
                风险备注
                <textarea className="scan-input" rows="3" value={reviewForm.validation_note} onChange={(event) => setReviewForm((prev) => ({ ...prev, validation_note: event.target.value }))} />
              </label>
              <button type="submit" disabled={savingReview || !mayWrite} title={disabledReason}>{savingReview ? '保存中...' : '保存复盘'}</button>
            </form>
          ) : (
            <div className="empty">选择一条候选后可更新复盘状态、成交反馈和收益表现。</div>
          )}
        </article>
      </section>

      {selectedPick ? (
        <SectionCard title="复盘时间线">
          <div className="timeline">
            {timeline.map((event, index) => (
              <div className="timeline-item" key={`${event.event_type}-${index}`}>
                <span className="timeline-dot" />
                <div>
                  <strong>{event.title}</strong>
                  <p className="muted">{event.description || '-'}</p>
                  <span className="small-text">{event.at || '-'}</span>
                </div>
              </div>
            ))}
            {!timeline.length ? <div className="empty">暂无时间线。</div> : null}
          </div>
        </SectionCard>
      ) : null}

      {selectedPick ? (
        <SectionCard title="当前复盘摘要">
          <div className="quick-actions">
            <div className="quick-action"><strong>收益</strong><span>{percent(selectedPick.return_pct)}</span></div>
            <div className="quick-action"><strong>最大收益</strong><span>{percent(selectedPick.max_return_pct)}</span></div>
            <div className="quick-action"><strong>回撤</strong><span>{percent(selectedPick.drawdown_pct)}</span></div>
            <div className="quick-action"><strong>持有天数</strong><span>{selectedPick.holding_days ?? '-'}</span></div>
          </div>
        </SectionCard>
      ) : null}
    </main>
  );
}
