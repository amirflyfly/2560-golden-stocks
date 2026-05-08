import { useEffect, useMemo, useState } from 'react';
import { api, getTenantId } from '../api/client';
import { canWrite, writeDisabledReason } from '../auth/permissions';
import { DataTable, PageHeader, SectionCard, StatusBadge } from '../components/common';

const POLL_STATUSES = new Set(['pending', 'running', 'retrying', 'queued']);
const SCAN_SAVED_VIEWS_KEY = '2560_scan_saved_views_v1';
const SCAN_LOCAL_ALERTS_KEY = '2560_scan_local_alerts_v1';
const SECURITY_TYPE_OPTIONS = [
  ['', '全部证券'],
  ['stock', '股票'],
  ['etf', 'ETF'],
  ['index', '指数'],
  ['fund', '基金'],
  ['bond', '债券'],
  ['convertible_bond', '可转债'],
  ['b_share', 'B股'],
  ['other', '其他'],
];
const BAR_INTERVAL_OPTIONS = [
  ['1d', '日线'],
  ['1h', '60分钟'],
  ['30m', '30分钟'],
  ['15m', '15分钟'],
  ['5m', '5分钟'],
  ['1m', '1分钟'],
];
const ADJUST_OPTIONS = [
  ['qfq', '前复权'],
  ['hfq', '后复权'],
  ['none', '不复权'],
];
const SECURITY_TYPE_LABELS = Object.fromEntries(SECURITY_TYPE_OPTIONS);
const BAR_INTERVAL_LABELS = Object.fromEntries(BAR_INTERVAL_OPTIONS);

function getTaskId(task) {
  return task?.task_id || task?.id || task?.scan_id || '';
}

function getProvider(task) {
  return task?.market_data?.actual_provider || task?.actual_provider || task?.market_data_provider || task?.provider || '-';
}

function getQuality(task) {
  return task?.market_data?.data_quality || task?.data_quality || task?.quality || '待生成';
}

function getExplanation(item) {
  return item?.explanation || {
    score: 0,
    confidence: 0,
    reasons: ['扫描完成后会生成解释字段'],
    indicators: {},
    risk_tags: ['等待执行'],
    risk_level: 'unknown',
  };
}

function stockCode(item) {
  return item?.symbol || item?.code || item?.stock_code || '-';
}

function stockName(item) {
  return item?.name || item?.stock_name || '-';
}

function securityTypeLabel(value) {
  const key = String(value || '').trim();
  return SECURITY_TYPE_LABELS[key] || key || '-';
}

function barIntervalLabel(value) {
  const key = String(value || '').trim();
  return BAR_INTERVAL_LABELS[key] || key || '-';
}

const SIGNAL_SUBTYPE_LABELS = {
  volume_impulse: '冲量启动',
  volume_build: '做量蓄势',
  volume_lock_shrink: '缩量回踩',
  breakout_volume: '放量突破',
  failed_breakout: '失败突破',
  mild_breakout: '温和突破',
};

SIGNAL_SUBTYPE_LABELS.pullback_setup = '回踩准备';
SIGNAL_SUBTYPE_LABELS.breakout_confirmed = '突破确认';
SIGNAL_SUBTYPE_LABELS.preopen_watch = '首板观察';
SIGNAL_SUBTYPE_LABELS.auction_confirmed = '竞价确认';
SIGNAL_SUBTYPE_LABELS.auction_rejected = '竞价放弃';

const VOLUME_PHASE_LABELS = {
  insufficient: '量能不足',
  impulse: '冲量',
  build: '做量',
  lock_shrink: '缩量锁量',
  breakout_expand: '放量突破',
  extreme_risk: '异常巨量',
  failed_breakout: '失败突破',
  active: '量能活跃',
};

function strategyIndicators(item) {
  return getExplanation(item).indicators || item?.indicators || {};
}

function signalSubtypeLabel(item) {
  const indicators = strategyIndicators(item);
  const value = item?.signal_subtype || indicators.signal_subtype || item?.phase?.signal_subtype || '';
  return SIGNAL_SUBTYPE_LABELS[value] || value || '-';
}

function volumePhaseLabel(item) {
  const indicators = strategyIndicators(item);
  const value = item?.volume_phase || indicators.volume_phase || item?.phase?.volume_phase || '';
  return VOLUME_PHASE_LABELS[value] || value || '-';
}

function indicatorNumber(value, digits = 2) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '-';
  return numeric.toFixed(digits);
}

function indicatorPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '-';
  return `${(numeric * 100).toFixed(1)}%`;
}

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== '');
}

function limitUpReturnFields(item) {
  const indicators = strategyIndicators(item);
  const source = indicators.limit_up_return || indicators.LIMIT_UP_RETURN || item?.limit_up_return || item?.LIMIT_UP_RETURN || {};
  return {
    anchorDate: firstValue(source.anchor_date, source.anchor_day, indicators.anchor_date, item?.anchor_date),
    pullbackDays: firstValue(source.pullback_days, source.pullback_day_count, indicators.pullback_days, item?.pullback_days),
    volumeShrinkRatio: firstValue(source.volume_shrink_ratio, source.shrink_ratio, indicators.volume_shrink_ratio, item?.volume_shrink_ratio),
    supportPrice: firstValue(source.support_price, source.support_level, indicators.support_price, item?.support_price),
    triggerPrice: firstValue(source.trigger_price, source.breakout_price, indicators.trigger_price, item?.trigger_price),
    stopLossPrice: firstValue(source.stop_loss_price, source.stop_price, indicators.stop_loss_price, item?.stop_loss_price),
    signalSubtype: firstValue(source.signal_subtype, item?.signal_subtype, indicators.signal_subtype),
  };
}

function hasLimitUpReturnFields(item) {
  return Object.values(limitUpReturnFields(item)).some((value) => value !== undefined && value !== null && value !== '');
}

function isPollingStatus(status) {
  return POLL_STATUSES.has(String(status || '').toLowerCase());
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

function normalizeServerScanView(item) {
  return {
    ...item,
    storage: 'server',
    form: item.metadata?.form || item.filters || item.form || {},
    resultView: item.metadata?.resultView || item.sort || item.resultView || {},
  };
}

function normalizeServerScanAlert(item) {
  const rule = item.rule || {};
  return {
    ...rule,
    id: item.id,
    name: item.name,
    created_at: item.created_at,
    storage: 'server',
  };
}

function scanAlertMatches(rule, item, fallbackQuality) {
  const explanation = getExplanation(item);
  if (rule.metric === 'score_gte') return Number(explanation.score || 0) >= Number(rule.threshold || 0);
  if (rule.metric === 'confidence_lte') return Number(explanation.confidence || 0) <= Number(rule.threshold || 0);
  if (rule.metric === 'risk_eq') return String(explanation.risk_level || 'unknown') === rule.risk_level;
  if (rule.metric === 'quality_eq') return String(item.data_quality || fallbackQuality || 'unknown') === rule.quality;
  return false;
}

export function ScansPage({ onNavigate, authz, pagePayload = {} }) {
  const [form, setForm] = useState({
    strategy_code: pagePayload.strategy_code || '2560',
    sample_size: 'default',
    security_type: pagePayload.security_type || '',
    bar_interval: pagePayload.bar_interval || pagePayload.interval || '1d',
    adjust: pagePayload.adjust || 'qfq',
  });
  const [task, setTask] = useState(null);
  const [results, setResults] = useState(null);
  const [recentScans, setRecentScans] = useState([]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [addingSymbol, setAddingSymbol] = useState('');
  const [resultPage, setResultPage] = useState(1);
  const [resultPageSize] = useState(20);
  const [resultView, setResultView] = useState({ risk: 'all', quality: 'all', sort: 'score_desc' });
  const [savedViews, setSavedViews] = useState([]);
  const [viewName, setViewName] = useState('');
  const [localAlerts, setLocalAlerts] = useState([]);
  const [alertForm, setAlertForm] = useState({
    name: '高分候选提醒',
    metric: 'score_gte',
    threshold: 80,
    risk_level: 'high',
    quality: 'primary',
  });
  const focusSymbol = pagePayload.symbol || '';
  const mayWrite = canWrite(authz);
  const disabledReason = writeDisabledReason(authz);

  async function loadRecentScans() {
    const data = await api.scans({ page: 1, page_size: 5 });
    setRecentScans(data.items || []);
  }

  async function loadSavedTools() {
    const localViews = readLocalArray(SCAN_SAVED_VIEWS_KEY).map((item) => ({ ...item, storage: item.storage || 'local' }));
    const localRules = readLocalArray(SCAN_LOCAL_ALERTS_KEY).map((item) => ({ ...item, storage: item.storage || 'local' }));
    try {
      const [serverViews, serverRules] = await Promise.all([api.savedViews(), api.alertRules()]);
      const scanViews = (serverViews.items || [])
        .filter((item) => item.page === 'scans' || item.metadata?.page === 'scans')
        .map(normalizeServerScanView);
      const scanRules = (serverRules.items || [])
        .filter((item) => item.scope === 'scan_results' || item.metadata?.page === 'scans')
        .map(normalizeServerScanAlert);
      setSavedViews([...scanViews, ...localViews].slice(0, 16));
      setLocalAlerts([...scanRules, ...localRules].slice(0, 16));
    } catch {
      setSavedViews(localViews);
      setLocalAlerts(localRules);
    }
  }

  useEffect(() => {
    loadRecentScans().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    loadSavedTools();
  }, []);

  useEffect(() => {
    if (!pagePayload.strategy_code) return;
    setForm((prev) => ({ ...prev, strategy_code: pagePayload.strategy_code }));
  }, [pagePayload.strategy_code]);

  async function refreshResults(scanTask = task, page = resultPage, { quiet = false } = {}) {
    const taskId = getTaskId(scanTask);
    if (!taskId) return;
    if (!quiet) setRefreshing(true);
    setError('');
    try {
      const data = await api.scanResults(taskId, { page, page_size: resultPageSize });
      setResults(data);
      setResultPage(data.page || page);
      setTask((prev) => ({ ...(prev || scanTask), status: data.status, result: data }));
      if (!quiet) {
        setMessage(data.items?.length ? '扫描结果已刷新。' : '任务已创建，结果仍在生成中。');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      if (!quiet) setRefreshing(false);
    }
  }

  useEffect(() => {
    const taskId = getTaskId(task);
    if (!taskId || !isPollingStatus(task?.status)) return undefined;
    const timer = window.setInterval(() => {
      refreshResults(task, resultPage, { quiet: true });
    }, 1500);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task?.id, task?.task_id, task?.status, resultPage]);

  async function runScan() {
    if (!mayWrite) {
      setError(disabledReason);
      return;
    }
    setError('');
    setMessage('');
    setResults(null);
    setResultPage(1);
    setSubmitting(true);
    try {
      const params = {
        security_type: form.security_type,
        bar_interval: form.bar_interval,
        interval: form.bar_interval,
        adjust: form.bar_interval === '1d' ? form.adjust : 'none',
      };
      if (form.sample_size !== 'default') {
        params.sample_size = Number(form.sample_size);
      }
      const data = await api.createScan({ strategy_code: form.strategy_code, params });
      setTask(data);
      setMessage('扫描任务已创建，系统会自动轮询结果。');
      await loadRecentScans();
      setTimeout(() => refreshResults(data, 1), 500);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function addToPicks(item) {
    if (!mayWrite) {
      setError(disabledReason);
      return;
    }
    const code = stockCode(item);
    if (!code || code === '-') return;
    setAddingSymbol(code);
    setError('');
    try {
      const explanation = getExplanation(item);
      const pick = await api.createPick({
        symbol: code,
        stock_name: stockName(item),
        trade_date: new Date().toISOString().slice(0, 10),
        source: 'scan',
        source_channel: 'scan-result',
        strategy_code: task?.strategy_code || form.strategy_code,
        reason: (explanation.reasons || []).join('；'),
        note: explanation.action_suggestion || '',
        risk_level: explanation.risk_level || item.risk_level || 'unknown',
        signal: explanation.indicators?.signal || item.signal || '',
        pick_price: item.last_price || item.price || item.pick_price || null,
        data_quality: item.data_quality || results?.market_data?.data_quality || task?.market_data?.data_quality || '',
        market_data_source: item.market_data_source || results?.market_data?.actual_provider || task?.market_data?.actual_provider || '',
        fallback_used: Boolean(item.fallback_used ?? results?.market_data?.fallback_used ?? task?.market_data?.fallback_used),
      });
      setMessage(`${pick.symbol || code} 已加入或更新选股池。`);
    } catch (err) {
      setError(err.message);
    } finally {
      setAddingSymbol('');
    }
  }

  async function saveCurrentView() {
    const createdAt = new Date().toLocaleString('zh-CN', { hour12: false });
    const name = viewName.trim() || `扫描视图 ${createdAt}`;
    const nextView = {
      id: makeLocalId('scan-view'),
      name,
      created_at: createdAt,
      form,
      resultView,
      storage: 'local',
    };
    if (mayWrite) {
      try {
        const saved = await api.createSavedView({
          name,
          page: 'scans',
          filters: form,
          sort: resultView,
          metadata: { page: 'scans', form, resultView },
        });
        const serverView = normalizeServerScanView(saved);
        setSavedViews((prev) => [serverView, ...prev.filter((item) => item.id !== serverView.id && item.name !== name)].slice(0, 16));
        setViewName('');
        setMessage(`服务端保存：扫描视图“${name}”已保存到当前账号，可跨浏览器读取。`);
        return;
      } catch (err) {
        setMessage(`服务端保存失败，已回退到本地浏览器：${err.message}`);
      }
    }
    const nextViews = [nextView, ...savedViews.filter((item) => item.name !== name)].slice(0, 8);
    setSavedViews(nextViews);
    writeLocalArray(SCAN_SAVED_VIEWS_KEY, nextViews.filter((item) => item.storage !== 'server'));
    setViewName('');
    setMessage(`本地保存：扫描视图“${name}”已保存到当前浏览器 localStorage，不会同步到后端。`);
  }

  function applySavedView(view) {
    setForm((prev) => ({ ...prev, ...(view.form || {}) }));
    setResultView((prev) => ({ ...prev, ...(view.resultView || {}) }));
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
    writeLocalArray(SCAN_SAVED_VIEWS_KEY, nextViews.filter((item) => item.storage !== 'server'));
  }

  async function saveLocalAlert(event) {
    event.preventDefault();
    const name = alertForm.name.trim() || '扫描提醒规则';
    const nextRule = {
      ...alertForm,
      id: makeLocalId('scan-alert'),
      name,
      created_at: new Date().toLocaleString('zh-CN', { hour12: false }),
      storage: 'local',
    };
    if (mayWrite) {
      try {
        const saved = await api.createAlertRule({
          name,
          scope: 'scan_results',
          target: 'scan_results',
          rule: alertForm,
          channels: ['in_app'],
          enabled: true,
          metadata: { page: 'scans', evaluation: 'worker_scheduled', fallback: 'client_visible_results' },
        });
        const serverRule = normalizeServerScanAlert(saved);
        setLocalAlerts((prev) => [serverRule, ...prev.filter((item) => item.id !== serverRule.id && item.name !== name)].slice(0, 16));
        api.evaluateNotifications({ scope: 'scan_results', source: 'scans_page', channel: 'in_app' })
          .catch(() => null)
          .then(refreshNotificationCenter);
        setMessage(`服务端提醒规则“${name}”已保存；worker 会后台定时评估并通过通知中心投递，已尝试触发一次立即评估。`);
        return;
      } catch (err) {
        setMessage(`服务端提醒保存失败，已回退到本地浏览器：${err.message}；本地回退仅在本机页面加载或刷新扫描结果时计算，不会后台推送。`);
      }
    }
    const nextRules = [nextRule, ...localAlerts.filter((item) => item.name !== name)].slice(0, 8);
    setLocalAlerts(nextRules);
    writeLocalArray(SCAN_LOCAL_ALERTS_KEY, nextRules.filter((item) => item.storage !== 'server'));
    setMessage(`本地回退提醒规则“${name}”已保存到当前浏览器 localStorage；仅在本机页面加载或刷新扫描结果时计算，不会后台推送。`);
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
    writeLocalArray(SCAN_LOCAL_ALERTS_KEY, nextRules.filter((item) => item.storage !== 'server'));
  }

  const taskId = getTaskId(task);
  const provider = getProvider(task);
  const quality = getQuality(task);
  const taskExplanation = getExplanation(task);
  const resultItems = results?.items || task?.result?.market_data?.sample_symbols || [];
  const scanParams = results?.task?.payload?.params || task?.params || task?.payload?.params || form;
  const activeSecurityType = scanParams.security_type || form.security_type;
  const activeBarInterval = scanParams.bar_interval || scanParams.interval || form.bar_interval;
  const activeAdjust = scanParams.adjust || form.adjust;
  const strategyRunner = results?.strategy_runner || task?.result?.strategy_runner || taskExplanation.indicators?.strategy_runner || 'registry';
  const totalResults = results?.total ?? resultItems.length;
  const totalPages = Math.max(1, Math.ceil(totalResults / resultPageSize));
  const dataQualityTone = quality === 'mock' ? 'warning' : 'success';

  const resultSummary = useMemo(() => {
    const highRisk = resultItems.filter((item) => getExplanation(item).risk_level === 'high').length;
    const averageScore = resultItems.length
      ? Math.round(resultItems.reduce((sum, item) => sum + (Number(getExplanation(item).score) || 0), 0) / resultItems.length)
      : 0;
    return { highRisk, averageScore };
  }, [resultItems]);

  const visibleResultItems = useMemo(() => {
    const filtered = resultItems.filter((item) => {
      const explanation = getExplanation(item);
      if (resultView.risk !== 'all' && explanation.risk_level !== resultView.risk) return false;
      if (resultView.quality !== 'all' && String(item.data_quality || quality) !== resultView.quality) return false;
      return true;
    });
    const score = (item) => Number(getExplanation(item).score || 0);
    const confidence = (item) => Number(getExplanation(item).confidence || 0);
    return [...filtered].sort((left, right) => {
      if (resultView.sort === 'score_asc') return score(left) - score(right);
      if (resultView.sort === 'confidence_desc') return confidence(right) - confidence(left);
      if (resultView.sort === 'risk_desc') {
        const rank = { high: 3, medium: 2, low: 1, unknown: 0 };
        return (rank[getExplanation(right).risk_level] || 0) - (rank[getExplanation(left).risk_level] || 0);
      }
      return score(right) - score(left);
    });
  }, [resultItems, resultView, quality]);

  const localAlertHits = useMemo(() => localAlerts.filter((rule) => rule.storage !== 'server').map((rule) => {
    const matches = visibleResultItems.filter((item) => scanAlertMatches(rule, item, quality));
    return { rule, matches, total: matches.length };
  }).filter((item) => item.total > 0), [localAlerts, visibleResultItems, quality]);

  function goResultPage(nextPage) {
    const page = Math.min(totalPages, Math.max(1, nextPage));
    setResultPage(page);
    refreshResults(task, page);
  }

  return (
    <main className="page">
      <PageHeader
        eyebrow="Scan"
        title="策略扫描"
        description="创建扫描任务后优先查看解释结果、风险等级和行情源质量，再把候选标的加入选股池。"
        badges={(
          <>
            <StatusBadge tone="success">租户 {getTenantId()}</StatusBadge>
            <StatusBadge tone="info">策略 {form.strategy_code}</StatusBadge>
            {task?.status ? <StatusBadge status={task.status}>{task.status}</StatusBadge> : null}
          </>
        )}
      />

      {error ? <div className="alert" data-testid="scan-error">{error}</div> : null}
      {message ? <div className="alert success">{message}</div> : null}
      {!mayWrite ? <div className="alert warning">{disabledReason}</div> : null}
      {quality === 'mock' ? <div className="alert warning">当前结果使用 mock 行情，仅适合链路验证，不能直接用于交易决策。</div> : null}
      {focusSymbol ? (
        <div className="alert warning">
          当前从市场发现带入焦点标的 {focusSymbol}。扫描任务仍按策略样本池运行；如需单标的复核，请先查看 K 线或加入选股池观察。
          <button type="button" className="btn-secondary inline-action" onClick={() => onNavigate?.('kline', { symbol: focusSymbol })}>查看 K 线</button>
        </div>
      ) : null}

      <SectionCard
        title="保存视图 / 提醒规则"
        subtitle="优先保存到服务端账号；服务端提醒由 worker 后台定时评估，并通过通知中心投递。服务端不可用时回退到 localStorage，仅本机页面计算。"
      >
        <div className="toolbar compact-toolbar local-tool-strip">
          <label>
            视图名称
            <input value={viewName} onChange={(event) => setViewName(event.target.value)} placeholder="例如：高分低风险" />
          </label>
          <button type="button" onClick={saveCurrentView}>保存当前视图</button>
          <span className="muted">当前视图：策略 {form.strategy_code}，风险 {resultView.risk}，质量 {resultView.quality}，排序 {resultView.sort}</span>
        </div>
        {savedViews.length ? (
          <div className="quick-actions local-view-list">
            {savedViews.map((view) => (
              <div className="quick-action local-view-card" key={view.id}>
                <strong>{view.name}</strong>
                <span>{view.storage === 'server' ? '服务端保存于' : '本地保存于'} {view.created_at}</span>
                <small>策略 {view.form?.strategy_code || '-'} / 风险 {view.resultView?.risk || 'all'} / 质量 {view.resultView?.quality || 'all'}</small>
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
              <option value="score_gte">评分大于等于</option>
              <option value="confidence_lte">置信度小于等于</option>
              <option value="risk_eq">风险等级等于</option>
              <option value="quality_eq">数据质量等于</option>
            </select>
          </label>
          {['score_gte', 'confidence_lte'].includes(alertForm.metric) ? (
            <label>
              阈值
              <input type="number" value={alertForm.threshold} onChange={(event) => setAlertForm((prev) => ({ ...prev, threshold: event.target.value }))} />
            </label>
          ) : null}
          {alertForm.metric === 'risk_eq' ? (
            <label>
              风险等级
              <select value={alertForm.risk_level} onChange={(event) => setAlertForm((prev) => ({ ...prev, risk_level: event.target.value }))}>
                <option value="high">high</option>
                <option value="medium">medium</option>
                <option value="low">low</option>
                <option value="unknown">unknown</option>
              </select>
            </label>
          ) : null}
          {alertForm.metric === 'quality_eq' ? (
            <label>
              数据质量
              <select value={alertForm.quality} onChange={(event) => setAlertForm((prev) => ({ ...prev, quality: event.target.value }))}>
                <option value="fallback">fallback</option>
                <option value="primary">primary</option>
                <option value="unknown">unknown</option>
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
                本地回退提醒命中“{rule.name}”：{total} 条。{matches.slice(0, 4).map((item) => `${stockCode(item)} ${stockName(item)}`).join('、')}
              </div>
            ))}
          </div>
        ) : (
          <div className="empty compact-empty">当前结果未命中本地回退提醒规则，或尚无扫描结果。</div>
        )}
      </SectionCard>

      <section className="scan-layout">
        <article className="panel-card">
          <h2>扫描配置</h2>
          <div className="scan-form">
            <label className="form-field">
              策略代码
              <select className="scan-select" value={form.strategy_code} onChange={(event) => setForm({ ...form, strategy_code: event.target.value })}>
                <option value="2560">2560 战法</option>
                <option value="first_limit_up">首板涨停</option>
              </select>
            </label>
            <label className="form-field">
              样本范围
              <select className="scan-select" value={form.sample_size} onChange={(event) => setForm({ ...form, sample_size: event.target.value })}>
                <option value="default">默认标的池</option>
                <option value="30">前 30 只样本</option>
                <option value="100">前 100 只样本</option>
              </select>
            </label>
            <label className="form-field">
              证券类型
              <select className="scan-select" value={form.security_type} onChange={(event) => setForm({ ...form, security_type: event.target.value })}>
                {SECURITY_TYPE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="form-field">
              K线级别
              <select className="scan-select" value={form.bar_interval} onChange={(event) => setForm({ ...form, bar_interval: event.target.value })}>
                {BAR_INTERVAL_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="form-field">
              复权
              <select className="scan-select" value={form.adjust} onChange={(event) => setForm({ ...form, adjust: event.target.value })} disabled={form.bar_interval !== '1d'}>
                {ADJUST_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <div className="alert warning">
              扫描会携带当前租户和 CSRF 凭据；viewer 角色只能查看，不能创建任务。
            </div>
            <button type="button" data-testid="create-scan-button" onClick={runScan} disabled={submitting || !mayWrite} title={disabledReason}>
              {submitting ? '正在创建...' : '创建扫描任务'}
            </button>
          </div>
        </article>

        <article className="panel-card">
          <h2>任务摘要</h2>
          {task ? (
            <div className="scan-summary" data-testid="scan-result">
              <div className="summary-row"><span>任务 ID</span><strong>{taskId}</strong></div>
              <div className="summary-row"><span>策略</span><strong>{task.strategy_code || form.strategy_code}</strong></div>
              <div className="summary-row"><span>状态</span><strong>{task.status || task.task_status || '已创建'}</strong></div>
              <div className="summary-row"><span>证券类型</span><strong>{securityTypeLabel(activeSecurityType)}</strong></div>
              <div className="summary-row"><span>K线级别</span><strong>{barIntervalLabel(activeBarInterval)}</strong></div>
              <div className="summary-row"><span>复权</span><strong>{activeBarInterval === '1d' ? activeAdjust : 'none'}</strong></div>
              <div className="summary-row"><span>行情源</span><strong>{provider}</strong></div>
              <div className="summary-row"><span>扫描口径</span><StatusBadge tone={strategyRunner === 'registry' ? 'success' : 'warning'}>{strategyRunner === 'registry' ? '策略算法' : '行情样本兜底'}</StatusBadge></div>
              <div className="summary-row"><span>数据质量</span><StatusBadge tone={dataQualityTone}>{quality}</StatusBadge></div>
              <div className="summary-row"><span>解释评分</span><strong>{taskExplanation.score ?? 0}</strong></div>
              <div className="summary-row"><span>平均分</span><strong>{resultSummary.averageScore}</strong></div>
              <div className="summary-row"><span>高风险标的</span><strong>{resultSummary.highRisk}</strong></div>
              <button type="button" className="btn-secondary" onClick={() => refreshResults()} disabled={refreshing}>
                {refreshing ? '刷新中...' : '刷新结果'}
              </button>
            </div>
          ) : (
            <div className="empty">还没有扫描任务。选择策略后点击“创建扫描任务”。</div>
          )}
        </article>
      </section>

      <SectionCard
        title="扫描结果"
        actions={taskId ? <button type="button" className="btn-secondary" onClick={() => refreshResults()} disabled={refreshing}>刷新结果</button> : null}
      >
        <div className="toolbar compact-toolbar">
          <label>
            风险
            <select value={resultView.risk} onChange={(event) => setResultView((prev) => ({ ...prev, risk: event.target.value }))}>
              <option value="all">全部</option>
              <option value="high">高</option>
              <option value="medium">中</option>
              <option value="low">低</option>
              <option value="unknown">未知</option>
            </select>
          </label>
          <label>
            数据质量
            <select value={resultView.quality} onChange={(event) => setResultView((prev) => ({ ...prev, quality: event.target.value }))}>
              <option value="all">全部</option>
              <option value="primary">primary</option>
              <option value="fallback">fallback</option>
              <option value="unknown">unknown</option>
            </select>
          </label>
          <label>
            排序
            <select value={resultView.sort} onChange={(event) => setResultView((prev) => ({ ...prev, sort: event.target.value }))}>
              <option value="score_desc">评分从高到低</option>
              <option value="score_asc">评分从低到高</option>
              <option value="confidence_desc">置信度从高到低</option>
              <option value="risk_desc">风险从高到低</option>
            </select>
          </label>
          <span className="muted">当前页显示 {visibleResultItems.length} / {resultItems.length} 条</span>
        </div>
        <DataTable
          className="scan-result-table"
          columns={[
            { label: '标的', render: (item) => <strong>{stockCode(item)} {stockName(item)}</strong> },
            { label: '类型', render: (item) => <StatusBadge tone="info">{securityTypeLabel(item.security_type || activeSecurityType)}</StatusBadge> },
            { label: 'K线', render: (item) => barIntervalLabel(item.bar_interval || item.interval || activeBarInterval) },
            { label: '战法阶段', render: (item) => <StatusBadge tone="info">{signalSubtypeLabel(item)}</StatusBadge> },
            {
              label: 'LIMIT_UP_RETURN',
              render: (item) => {
                if (!hasLimitUpReturnFields(item)) return <span className="muted">-</span>;
                const fields = limitUpReturnFields(item);
                return (
                  <span className="limit-up-field-list">
                    <span>锚点 {fields.anchorDate || '-'}</span>
                    <span>回踩 {fields.pullbackDays ?? '-'} 天</span>
                    <span>缩量 {indicatorPercent(fields.volumeShrinkRatio)}</span>
                    <span>支撑 {indicatorNumber(fields.supportPrice)}</span>
                    <span>触发 {indicatorNumber(fields.triggerPrice)}</span>
                    <span>止损 {indicatorNumber(fields.stopLossPrice)}</span>
                    <span>{SIGNAL_SUBTYPE_LABELS[fields.signalSubtype] || fields.signalSubtype || '-'}</span>
                  </span>
                );
              },
            },
            { label: '量能阶段', render: (item) => volumePhaseLabel(item) },
            { label: 'MA60', render: (item) => indicatorNumber(strategyIndicators(item).ma60 ?? item.ma60) },
            { label: '量比', render: (item) => indicatorNumber(strategyIndicators(item).vr5_60 ?? item.vr5_60 ?? item.vol_ratio) },
            { label: '评分', render: (item) => getExplanation(item).score ?? '-' },
            { label: '置信度', render: (item) => getExplanation(item).confidence ?? '-' },
            { label: '风险', render: (item) => <StatusBadge status={getExplanation(item).risk_level}>{getExplanation(item).risk_level}</StatusBadge> },
            { label: '行情源', render: (item) => <StatusBadge tone={item.data_quality === 'mock' ? 'warning' : 'info'}>{item.market_data_source || provider}</StatusBadge> },
            { label: '入选理由', render: (item) => (getExplanation(item).reasons || []).slice(0, 2).join('；') || '-' },
            {
              label: '操作',
              render: (item) => (
                <div className="row-actions">
                  <button type="button" className="btn-secondary" onClick={() => addToPicks(item)} disabled={addingSymbol === stockCode(item) || !mayWrite} title={disabledReason}>
                    {addingSymbol === stockCode(item) ? '加入中' : '加入池'}
                  </button>
                  <button type="button" className="btn-secondary" onClick={() => onNavigate?.('kline', { symbol: stockCode(item), security_type: item.security_type || activeSecurityType, interval: item.bar_interval || item.interval || activeBarInterval })}>K 线</button>
                  <button type="button" className="btn-secondary" onClick={() => onNavigate?.('strategies', { strategy_code: task?.strategy_code || form.strategy_code })}>回测</button>
                </div>
              ),
            },
          ]}
          rows={visibleResultItems}
          getKey={(item, index) => `${stockCode(item)}-${index}`}
          emptyText="暂无匹配当前筛选条件的扫描结果。可调整风险、数据质量或等待任务完成后刷新。"
        />
        <div className="pagination-row">
          <span>共 {totalResults} 条，第 {resultPage} / {totalPages} 页</span>
          <div className="row-actions">
            <button type="button" className="btn-secondary" onClick={() => goResultPage(resultPage - 1)} disabled={!taskId || resultPage <= 1 || refreshing}>上一页</button>
            <button type="button" className="btn-secondary" onClick={() => goResultPage(resultPage + 1)} disabled={!taskId || resultPage >= totalPages || refreshing}>下一页</button>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="最近扫描" className="section-gap">
        <DataTable
          className="compact-table"
          columns={[
            { label: '任务', render: (item) => item.name || item.id },
            { label: '状态', render: (item) => <StatusBadge status={item.status}>{item.status}</StatusBadge> },
            { label: '时间', render: (item) => item.created_at || '-' },
            {
              label: '操作',
              render: (item) => (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => {
                    setTask(item);
                    setResultPage(1);
                    refreshResults(item, 1);
                  }}
                >
                  查看结果
                </button>
              ),
            },
          ]}
          rows={recentScans}
          getKey={(item) => item.id}
          emptyText="暂无历史扫描。"
        />
      </SectionCard>

      {task ? (
        <details className="card section-gap">
          <summary>开发详情</summary>
          <pre className="code-block">{JSON.stringify({ task, results }, null, 2)}</pre>
        </details>
      ) : null}
    </main>
  );
}
