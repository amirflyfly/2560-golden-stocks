import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { canAdmin, canWrite } from '../auth/permissions';
import { RiskDisclaimer } from '../components/common';

function money(value) {
  const numeric = Number(value || 0);
  return numeric.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function signedMoney(value) {
  const numeric = Number(value || 0);
  const prefix = numeric > 0 ? '+' : '';
  return `${prefix}${money(numeric)}`;
}

function pct(value) {
  const numeric = Number(value || 0) * 100;
  return `${numeric.toFixed(2)}%`;
}

function returnPercent(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function signedPct(value) {
  const numeric = Number(value || 0);
  return `${numeric > 0 ? '+' : ''}${numeric.toFixed(2)}%`;
}

function toneForPnl(value) {
  const numeric = Number(value || 0);
  if (numeric > 0) return 'success';
  if (numeric < 0) return 'danger';
  return 'info';
}

const EXIT_REASON_LABELS = {
  stop_loss: '触发止损',
  take_profit: '达到止盈',
  take_profit_price: '到达止盈价',
  premium_expanded: '溢价率过高',
  max_holding_days: '持仓到期',
  ma25_breakdown: '跌破25日线',
  ma60_breakdown: '跌破60日线',
  failed_breakout: '突破失败',
  limit_down: '跌停无法卖出',
  suspended: '停牌无法交易',
  missing_exit_price: '缺少卖出价格',
  t0_sell_blocked: '当天买入暂不卖出',
};

function exitReasonLabel(value) {
  const key = String(value || '').trim();
  return EXIT_REASON_LABELS[key] || key || '-';
}

function sideLabel(value) {
  const side = String(value || '').toUpperCase();
  if (side === 'BUY') return '买入';
  if (side === 'SELL') return '卖出';
  return side || '-';
}

const SECURITY_TYPE_LABELS = {
  stock: '股票',
  etf: 'ETF',
  index: '指数',
  fund: '基金',
  bond: '债券',
  convertible_bond: '可转债',
  b_share: 'B股',
  other: '其他',
};

const BAR_INTERVAL_LABELS = {
  '1d': '日线',
  '1h': '60分钟',
  '60m': '60分钟',
  '30m': '30分钟',
  '15m': '15分钟',
  '5m': '5分钟',
  '1m': '1分钟',
};

function securityTypeLabel(value) {
  const key = String(value || '').trim();
  return SECURITY_TYPE_LABELS[key] || key || '';
}

function barIntervalLabel(value) {
  const key = String(value || '').trim();
  return BAR_INTERVAL_LABELS[key] || key || '';
}

function securityMeta(item) {
  const interval = item?.bar_interval || item?.interval || item?.signal_interval;
  return [securityTypeLabel(item?.security_type), barIntervalLabel(interval)].filter(Boolean).join(' / ');
}

const SIGNAL_SUBTYPE_LABELS = {
  volume_impulse: '冲量启动',
  volume_build: '做量蓄势',
  volume_lock_shrink: '缩量回踩',
  breakout_volume: '放量突破',
  failed_breakout: '失败突破',
  mild_breakout: '温和突破',
};

function signalSubtypeLabel(item) {
  const payload = item?.payload || item?.payload_json || {};
  const subtype = item?.signal_subtype || payload.signal_subtype || payload.phase?.signal_subtype || '';
  return SIGNAL_SUBTYPE_LABELS[subtype] || subtype || '-';
}

function volumePhaseLabel(item) {
  const payload = item?.payload || item?.payload_json || {};
  const phase = item?.volume_phase || payload.volume_phase || payload.phase?.volume_phase || '';
  return phase || '-';
}

function firstValue(...values) {
  const found = values.find((value) => value !== undefined && value !== null && String(value).trim() !== '');
  return found === undefined ? '' : found;
}

const DEFAULT_EXIT_RULES = {
  '2560': { stop_loss_pct: -0.08, take_profit_pct: 0.15, max_holding_days: 20, technical_exit_enabled: true },
  FIRST_LIMIT_UP: { stop_loss_pct: -0.06, take_profit_pct: 0.12, max_holding_days: 5, technical_exit_enabled: true },
  LIMIT_UP_RETURN: { stop_loss_pct: -0.05, take_profit_pct: 0.10, max_holding_days: 7, technical_exit_enabled: true },
  CONVERTIBLE_BOND_LOW_PREMIUM: {
    stop_loss_pct: -0.06,
    take_profit_pct: null,
    take_profit_price: 130,
    sell_premium_rate: 0.40,
    max_holding_days: 20,
    technical_exit_enabled: false,
  },
};

const LOOP_STORAGE_KEY = 'aistocks.paper.lastLoop.v1';
const AUTO_TASK_SPECS = [
  {
    key: 'strategy',
    title: '策略自动运行',
    names: ['strategy.production_run'],
    fallback: '等待策略任务',
  },
  {
    key: 'monitor',
    title: '持仓盯盘卖出',
    names: ['paper.positions.monitor'],
    fallback: '等待盯盘任务',
  },
  {
    key: 'snapshot',
    title: '行情快照同步',
    names: ['market.snapshot.plan', 'market.snapshot'],
    fallback: '等待快照任务',
  },
  {
    key: 'review',
    title: '每日复盘',
    names: ['reports.daily_review'],
    fallback: '等待复盘任务',
  },
];

function numericOrNull(value) {
  if (value === undefined || value === null || String(value).trim() === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function daysSince(value) {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return null;
  const start = new Date(parsed);
  const now = new Date();
  start.setHours(0, 0, 0, 0);
  now.setHours(0, 0, 0, 0);
  return Math.max(0, Math.floor((now.getTime() - start.getTime()) / 86400000));
}

function exitRulePlan(item, links = [], orders = []) {
  const metadata = item?.metadata || item?.metadata_json || {};
  const planSource = item?.exit_plan || item?.exit_rule || metadata.exit_plan || metadata.exit_rule || {};
  const strategy = String(positionStrategy(item, links, orders) || '').toUpperCase();
  const defaults = DEFAULT_EXIT_RULES[strategy] || DEFAULT_EXIT_RULES['2560'];
  const avgCost = Number(item?.avg_cost || 0);
  const stopLossPct = Number(firstValue(planSource.stop_loss_pct, item?.stop_loss_pct, metadata.stop_loss_pct, defaults.stop_loss_pct));
  const takeProfitPct = numericOrNull(firstValue(planSource.take_profit_pct, item?.take_profit_pct, metadata.take_profit_pct, defaults.take_profit_pct));
  const takeProfitPrice = numericOrNull(firstValue(planSource.take_profit_price, item?.take_profit_price, metadata.take_profit_price, defaults.take_profit_price));
  const sellPremiumRate = numericOrNull(firstValue(planSource.sell_premium_rate, item?.sell_premium_rate, metadata.sell_premium_rate, defaults.sell_premium_rate));
  const maxHoldingDays = Number(firstValue(planSource.max_holding_days, item?.max_holding_days, metadata.max_holding_days, defaults.max_holding_days));
  const openedDays = firstValue(item?.holding_days, metadata.holding_days, planSource.holding_days, daysSince(item?.opened_at));
  const rawTechnicalEnabled = firstValue(planSource.technical_exit_enabled, defaults.technical_exit_enabled);
  const technicalEnabled = rawTechnicalEnabled === false || String(rawTechnicalEnabled).toLowerCase() === 'false' ? false : Boolean(rawTechnicalEnabled);
  return {
    stopLossPct,
    takeProfitPct,
    takeProfitPrice,
    sellPremiumRate,
    maxHoldingDays,
    holdingDays: openedDays === '' || openedDays === null ? null : Number(openedDays),
    stopLossPrice: avgCost ? avgCost * (1 + stopLossPct) : null,
    takeProfitReturnPrice: avgCost && takeProfitPct !== null ? avgCost * (1 + takeProfitPct) : null,
    technicalEnabled,
    technical: technicalEnabled === false ? '按价格、溢价率或持仓期限退出' : '跌破25日线或60日线、突破失败时退出',
  };
}

function exitPlanSummary(item, links = [], orders = []) {
  const plan = exitRulePlan(item, links, orders);
  const parts = [
    `止损${signedPct(plan.stopLossPct * 100)}`,
    plan.takeProfitPct === null ? '止盈按价格' : `止盈${signedPct(plan.takeProfitPct * 100)}`,
    `最长${plan.maxHoldingDays}天`,
    plan.sellPremiumRate !== null ? `溢价${pct(plan.sellPremiumRate)}` : null,
    plan.technicalEnabled ? '技术退出' : '价格/期限退出',
  ];
  return parts.filter(Boolean).join(' / ');
}

function orderExitReason(item) {
  const metadata = item?.metadata || item?.metadata_json || {};
  return firstValue(item?.exit_reason, item?.reason, metadata.exit_reason, metadata.reason);
}

function positionStrategy(item, links, orders) {
  const direct = firstValue(item?.strategy_code, item?.strategy);
  if (direct && String(direct).toLowerCase() !== 'exit_rule') return direct;
  const sourceHash = firstValue(item?.source_signal_hash);
  if (sourceHash) {
    const sourceLink = links.find((candidate) => String(candidate?.source_signal_hash || '') === String(sourceHash));
    if (sourceLink?.metadata?.strategy_code) return sourceLink.metadata.strategy_code;
  }
  const link = links.find((candidate) => (
    String(candidate?.metadata?.symbol || '') === String(item?.symbol || '') && candidate?.metadata?.strategy_code
  ));
  if (link?.metadata?.strategy_code) return link.metadata.strategy_code;
  const buyOrder = orders.find((order) => (
    String(order?.symbol || '') === String(item?.symbol || '') && String(order?.side || '').toUpperCase() === 'BUY' && order?.strategy_code
  ));
  return buyOrder?.strategy_code || '当前持仓';
}

function fillExitReason(item, orders) {
  const order = orders.find((candidate) => String(candidate?.id || '') === String(item?.order_id || ''));
  return orderExitReason(order || item);
}

function normalizeFreshnessStatus(value) {
  const raw = String(value || '').toLowerCase();
  if (['fresh', 'realtime', 'real_time', 'timely', 'current', 'ok', 'ready'].includes(raw)) return 'realtime';
  if (['stale', 'delayed', 'delay', 'old', 'expired', 'outdated', 'late'].includes(raw)) return 'delayed';
  if (['missing', 'none', 'empty', 'unavailable', 'no_data'].includes(raw)) return 'none';
  return '';
}

function isSameLocalDate(value) {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return false;
  const date = new Date(parsed);
  const now = new Date();
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
}

function positionFreshness(item) {
  const freshness = item?.freshness || item?.data_freshness || {};
  const snapshot = freshness.snapshot || freshness.market_snapshot || {};
  const explicitStatus = normalizeFreshnessStatus(firstValue(
    item?.snapshot_status,
    item?.snapshot_freshness,
    snapshot.status,
    snapshot.state,
    freshness.status,
  ));
  const snapshotTime = firstValue(
    item?.snapshot_trade_time,
    item?.latest_snapshot_time,
    item?.last_snapshot_time,
    item?.market_snapshot_time,
    snapshot.latest_trade_time,
    snapshot.trade_time,
    snapshot.updated_at,
  );
  const fallbackTime = firstValue(item?.price_updated_at, item?.market_price_updated_at, item?.updated_at);
  const time = snapshotTime || fallbackTime;
  const sourceLabel = snapshotTime ? '快照' : '盯市';

  if (explicitStatus === 'realtime' || snapshot.is_fresh === true || snapshot.timely === true) {
    return { label: '已同步', tone: 'success', time: time || '-', sourceLabel };
  }
  if (explicitStatus === 'delayed' || snapshot.is_fresh === false || snapshot.timely === false || snapshot.stale === true) {
    return { label: '延迟', tone: 'warning', time: time || '-', sourceLabel };
  }
  if (explicitStatus === 'none' || !time || item?.market_price == null) {
    return { label: '暂无', tone: 'warning', time: time || '-', sourceLabel };
  }
  if (isSameLocalDate(time)) {
    return { label: '已同步', tone: 'success', time, sourceLabel };
  }
  return { label: '延迟', tone: 'warning', time, sourceLabel };
}

function countSide(items, side) {
  const wanted = String(side || '').toUpperCase();
  return (items || []).filter((item) => String(item?.side || '').toUpperCase() === wanted).length;
}

function sumAccountMetric(accounts, section, key) {
  return (accounts || []).reduce((total, item) => total + Number(item?.[section]?.[key] || 0), 0);
}

function loopSnapshotFromState(state) {
  const summary = state.summary || {};
  const positions = state.positions || [];
  const orders = state.orders || [];
  return {
    equity: Number(summary.equity || 0),
    cash: Number(summary.cash || 0),
    marketValue: Number(summary.market_value || 0),
    activePositions: positions.filter((item) => Number(item?.quantity || 0) > 0).length,
    orders: orders.length,
    buyOrders: countSide(orders, 'BUY'),
    sellOrders: countSide(orders, 'SELL'),
    fills: (state.fills || []).length,
    signals: (state.signals || []).length,
    links: (state.links || []).length,
  };
}

function countDelta(current, before, key) {
  if (!before) return null;
  return Number(current?.[key] || 0) - Number(before?.[key] || 0);
}

function deltaLabel(value, suffix = '') {
  if (value === null || value === undefined) return '-';
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${value}${suffix}`;
}

function deltaTone(value) {
  if (value > 0) return 'success';
  if (value < 0) return 'danger';
  return 'info';
}

function latestSide(items, side) {
  const wanted = String(side || '').toUpperCase();
  return (items || []).find((item) => String(item?.side || '').toUpperCase() === wanted);
}

function loadStoredLoopState() {
  if (typeof window === 'undefined') return null;
  try {
    return JSON.parse(window.localStorage.getItem(LOOP_STORAGE_KEY) || 'null');
  } catch {
    return null;
  }
}

function saveStoredLoopState(before, result) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LOOP_STORAGE_KEY, JSON.stringify({ before, result, stored_at: new Date().toISOString() }));
  } catch {
    // Ignore storage failures; live page state still shows the result.
  }
}

function taskTime(task) {
  return task?.finished_at || task?.heartbeat_at || task?.started_at || task?.created_at || '';
}

function taskStatusLabel(task) {
  const status = String(task?.status || '').toLowerCase();
  if (status === 'completed') return '完成';
  if (status === 'running') return '运行中';
  if (status === 'pending') return '排队';
  if (status === 'retrying') return '重试';
  if (status === 'failed') return '失败';
  if (status === 'stale') return '超时';
  if (status === 'cancelled') return '取消';
  return status || '暂无';
}

function minutesSince(value) {
  if (!value) return null;
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return null;
  return Math.max(0, Math.round((Date.now() - parsed) / 60000));
}

function taskFreshnessText(task) {
  const minutes = minutesSince(taskTime(task));
  if (minutes === null) return '暂无运行时间';
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  return `${Math.floor(minutes / 60)}小时前`;
}

function latestTaskByNames(tasks, names) {
  const wanted = new Set(names);
  return (tasks || []).find((task) => wanted.has(task?.name));
}

function taskSummaryText(task, fallback) {
  if (!task) return fallback;
  const result = task.result || {};
  const summary = task.result_summary || {};
  if (task.name === 'strategy.production_run') {
    const scan = result.scan || {};
    const paper = result.paper_trading || {};
    const matched = scan.matched_count ?? summary.matched_count ?? 0;
    const buys = (paper.orders || []).length;
    const skipped = (paper.skipped || []).length;
    return `命中 ${matched} / 买入 ${buys} / 跳过 ${skipped}`;
  }
  if (task.name === 'paper.positions.monitor') {
    const snapshot = result.snapshot_sync || {};
    const exits = result.exit_summary || {};
    return `同步 ${snapshot.snapshot_count || 0} / 更新 ${sumAccountMetric(result.accounts || [], 'mark_to_market', 'updated')} / 卖出 ${exits.orders || 0}`;
  }
  if (['market.snapshot.plan', 'market.snapshot'].includes(task.name)) {
    return `快照 ${summary.snapshot_count || result.snapshot_count || 0} / 写入 ${summary.persisted_snapshots || result.persisted_snapshots || 0}`;
  }
  if (task.name === 'reports.daily_review') {
    const exitSummary = result.exit_summary || {};
    return `复盘完成 / 卖出 ${exitSummary.orders || 0}`;
  }
  return task.error_summary || taskStatusLabel(task);
}

function isHealthyTask(task) {
  const status = String(task?.status || '').toLowerCase();
  const age = minutesSince(taskTime(task));
  const recent = age === null ? false : age <= 45;
  return !!task && ['completed', 'running', 'pending'].includes(status) && recent;
}

function healthSummary({ autoTaskCards, linkHealth, missingPositions, delayedPositions, activePositions }) {
  const strategyOk = isHealthyTask(autoTaskCards.find((item) => item.key === 'strategy')?.task);
  const monitorOk = isHealthyTask(autoTaskCards.find((item) => item.key === 'monitor')?.task);
  const snapshotOk = isHealthyTask(autoTaskCards.find((item) => item.key === 'snapshot')?.task);
  const linkOk = !linkHealth || linkHealth.status !== 'degraded';
  const freshnessOk = activePositions === 0 || (!missingPositions && !delayedPositions);
  const checks = [
    { key: 'strategy', label: '策略自动选标的', ok: strategyOk, detail: strategyOk ? '最近有策略任务' : '暂未看到策略任务' },
    { key: 'buy', label: '模拟买入入账', ok: linkOk, detail: linkOk ? '信号链路完整' : `缺失 ${linkHealth?.incomplete || 0} 条链路` },
    { key: 'snapshot', label: 'K线/快照同步', ok: snapshotOk, detail: snapshotOk ? '最近有行情同步' : '暂未看到快照任务' },
    { key: 'monitor', label: '持仓盯盘卖出', ok: monitorOk, detail: monitorOk ? '最近有盯盘任务' : '暂未看到盯盘任务' },
    { key: 'freshness', label: '持仓行情时效', ok: freshnessOk, detail: activePositions ? `已同步 ${Math.max(0, activePositions - missingPositions - delayedPositions)} / 延迟 ${delayedPositions} / 缺失 ${missingPositions}` : '暂无持仓' },
  ];
  const blocked = checks.filter((item) => !item.ok);
  return {
    checks,
    blocked,
    tone: blocked.length ? 'warning' : 'success',
    title: blocked.length ? '闭环有待确认' : '闭环可运行',
    detail: blocked.length ? `还有 ${blocked.length} 个环节需要关注` : '策略、行情、盯盘和复盘链路都有最近证据',
  };
}

function scrollToEvidence(id) {
  if (typeof document === 'undefined') return;
  const target = document.getElementById(id);
  if (!target) return;
  if ('open' in target) target.open = true;
  target.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function linkRateLabel(health) {
  if (!health || Number(health.total || 0) === 0) return '暂无链路';
  return pct(health.complete_rate ?? 0);
}

function linkRateTone(health) {
  if (!health || Number(health.total || 0) === 0) return 'info';
  return health.status === 'degraded' ? 'warning' : 'success';
}

function triggerDistanceText(position, links, orders) {
  const plan = exitRulePlan(position, links, orders);
  const price = Number(firstValue(position?.market_price, position?.snapshot_last_price));
  if (!price || !plan.stopLossPrice) return '等待有效行情';
  const stopDistance = ((price - plan.stopLossPrice) / price) * 100;
  const takeProfitTarget = plan.takeProfitReturnPrice || plan.takeProfitPrice;
  const takeProfitDistance = takeProfitTarget ? ((takeProfitTarget - price) / price) * 100 : null;
  const parts = [`离止损 ${signedPct(stopDistance)}`];
  if (takeProfitDistance !== null) parts.push(`离止盈 ${signedPct(takeProfitDistance)}`);
  return parts.join(' / ');
}

function positionDecision(position, links, orders) {
  const freshness = positionFreshness(position);
  if (freshness.label !== '已同步') return { tone: 'warning', label: '先同步行情' };
  const plan = exitRulePlan(position, links, orders);
  const price = Number(firstValue(position?.market_price, position?.snapshot_last_price));
  if (!price) return { tone: 'warning', label: '缺少价格' };
  if (plan.stopLossPrice && price <= plan.stopLossPrice) return { tone: 'danger', label: '接近/触发止损' };
  if (plan.takeProfitReturnPrice && price >= plan.takeProfitReturnPrice) return { tone: 'success', label: '接近/触发止盈' };
  if (plan.takeProfitPrice && price >= plan.takeProfitPrice) return { tone: 'success', label: '接近/触发止盈价' };
  return { tone: 'info', label: '继续盯盘' };
}

export function PaperTradingPage({ authz }) {
  const [state, setState] = useState(() => {
    const storedLoop = loadStoredLoopState();
    return {
    loading: true,
    actionLoading: false,
    error: '',
    message: '',
    summary: null,
    accounts: [],
    positions: [],
    orders: [],
    fills: [],
    signals: [],
    links: [],
    linkHealth: null,
    lastLoopEvaluation: storedLoop?.result || null,
    loopBefore: storedLoop?.before || null,
    loopStatus: storedLoop?.result?.status || 'idle',
    taskTelemetry: [],
    taskTelemetryError: '',
  };
  });
  const mayWrite = canWrite(authz);
  const mayAdmin = canAdmin(authz);
  const defaultAccount = state.accounts[0];
  const summary = state.summary || {};
  const positionFreshnessItems = state.positions.map((item) => ({ symbol: item.symbol, ...positionFreshness(item) }));
  const delayedPositions = positionFreshnessItems.filter((item) => item.label === '延迟').length;
  const missingPositions = positionFreshnessItems.filter((item) => item.label === '暂无').length;
  const tradablePositions = positionFreshnessItems.filter((item) => item.label === '已同步').length;
  const lastLoopEvaluation = state.lastLoopEvaluation || null;
  const loopMonitor = lastLoopEvaluation?.position_monitor || lastLoopEvaluation || {};
  const loopSnapshot = loopMonitor?.snapshot_sync || {};
  const loopAccounts = loopMonitor?.accounts || [];
  const loopExitSummary = loopMonitor?.exit_summary || {};
  const loopStrategySummary = lastLoopEvaluation?.strategy_summary || {};
  const buyOrderCount = countSide(state.orders, 'BUY');
  const sellOrderCount = countSide(state.orders, 'SELL');
  const loopUpdatedPositions = sumAccountMetric(loopAccounts, 'mark_to_market', 'updated');
  const currentLoopSnapshot = loopSnapshotFromState(state);
  const loopRunItems = lastLoopEvaluation?.strategy_runs || [];
  const latestBuy = latestSide(state.orders, 'BUY');
  const latestSell = latestSide(state.orders, 'SELL');
  const latestFill = state.fills[0];
  const latestLink = state.links[0];
  const latestPosition = state.positions.find((item) => Number(item?.quantity || 0) > 0) || state.positions[0];
  const autoTaskCards = AUTO_TASK_SPECS.map((spec) => ({ ...spec, task: latestTaskByNames(state.taskTelemetry, spec.names) }));
  const taskByKey = Object.fromEntries(autoTaskCards.map((item) => [item.key, item.task]));
  const loopHealth = healthSummary({
    autoTaskCards,
    linkHealth: state.linkHealth,
    missingPositions,
    delayedPositions,
    activePositions: Number(summary.active_positions || 0),
  });
  const loopDeltas = [
    { label: '信号', value: countDelta(currentLoopSnapshot, state.loopBefore, 'signals'), suffix: '条' },
    { label: '买单', value: countDelta(currentLoopSnapshot, state.loopBefore, 'buyOrders'), suffix: '笔' },
    { label: '卖单', value: countDelta(currentLoopSnapshot, state.loopBefore, 'sellOrders'), suffix: '笔' },
    { label: '成交', value: countDelta(currentLoopSnapshot, state.loopBefore, 'fills'), suffix: '笔' },
    { label: '持仓', value: countDelta(currentLoopSnapshot, state.loopBefore, 'activePositions'), suffix: '个' },
    { label: '权益', value: state.loopBefore ? currentLoopSnapshot.equity - state.loopBefore.equity : null, money: true },
  ];
  const cockpitSteps = [
    {
      label: '策略选标的',
      value: lastLoopEvaluation ? Number(loopStrategySummary.matched_count || 0) : taskSummaryText(taskByKey.strategy, '等待运行'),
      detail: taskByKey.strategy ? `${taskStatusLabel(taskByKey.strategy)} / ${taskFreshnessText(taskByKey.strategy)}` : '等待策略任务',
      tone: isHealthyTask(taskByKey.strategy) ? 'done' : 'waiting',
    },
    {
      label: '模拟买入',
      value: lastLoopEvaluation ? Number(loopStrategySummary.buy_orders || 0) : buyOrderCount,
      detail: lastLoopEvaluation ? `跳过 ${loopStrategySummary.buy_skipped || 0} / 阻断 ${loopStrategySummary.buy_blocked || 0}` : '写入模拟账户簿',
      tone: buyOrderCount ? 'done' : 'waiting',
    },
    {
      label: '行情/K线同步',
      value: lastLoopEvaluation ? Number(loopSnapshot.snapshot_count || 0) : taskSummaryText(taskByKey.snapshot, '等待同步'),
      detail: taskByKey.snapshot ? `${taskStatusLabel(taskByKey.snapshot)} / ${taskFreshnessText(taskByKey.snapshot)}` : '快照与本地K线',
      tone: isHealthyTask(taskByKey.snapshot) ? 'done' : 'waiting',
    },
    {
      label: '持仓盯盘',
      value: lastLoopEvaluation ? loopUpdatedPositions : state.positions.length,
      detail: `已同步 ${tradablePositions} / 延迟 ${delayedPositions} / 缺失 ${missingPositions}`,
      tone: missingPositions || delayedPositions ? 'warning' : 'done',
    },
    {
      label: '止盈止损卖出',
      value: lastLoopEvaluation ? Number(loopExitSummary.orders || 0) : sellOrderCount,
      detail: lastLoopEvaluation ? `继续 ${loopExitSummary.skipped || 0} / 受限 ${loopExitSummary.blocked || 0}` : '会生成模拟卖单',
      tone: isHealthyTask(taskByKey.monitor) ? 'done' : 'waiting',
    },
    {
      label: '复盘归因',
      value: linkRateLabel(state.linkHealth),
      detail: state.linkHealth?.status === 'degraded' ? `缺失 ${state.linkHealth.incomplete || 0} 条链路` : '信号到成交可追溯',
      tone: linkRateTone(state.linkHealth) === 'success' ? 'done' : linkRateTone(state.linkHealth) === 'warning' ? 'warning' : 'waiting',
    },
  ];
  const positionCards = state.positions
    .filter((item) => Number(item?.quantity || 0) > 0)
    .slice(0, 6);
  const tradeRecords = [
    ...(state.orders || []).map((item) => ({ ...item, recordType: 'order', recordTime: item.created_at || '' })),
    ...(state.fills || []).map((item) => ({ ...item, recordType: 'fill', recordTime: item.filled_at || '' })),
  ]
    .sort((a, b) => String(b.recordTime).localeCompare(String(a.recordTime)))
    .slice(0, 8);
  const attributionItems = state.links.slice(0, 8);

  function loadTaskTelemetry() {
    return api.tasks({ page: 1, page_size: 80, sort: 'created_at', order: 'desc' })
      .then((data) => setState((prev) => ({ ...prev, taskTelemetry: data.items || [], taskTelemetryError: '' })))
      .catch((error) => setState((prev) => ({ ...prev, taskTelemetryError: error.message })));
  }

  function load() {
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    return Promise.all([
      api.paperSummary(),
      api.paperAccounts(),
      api.paperPositions({ active_only: 0 }),
      api.paperOrders({ limit: 50 }),
      api.paperFills({ limit: 50 }),
      api.tradeSignals({ limit: 50 }),
      api.signalReviewLinks({ limit: 50 }),
    ])
      .then(([summaryData, accountData, positionData, orderData, fillData, signalData, linkData]) => {
        setState((prev) => ({
          ...prev,
          loading: false,
          summary: summaryData,
          accounts: accountData.items || [],
          positions: positionData.items || [],
          orders: orderData.items || [],
          fills: fillData.items || [],
          signals: signalData.items || [],
          links: linkData.items || [],
          linkHealth: linkData.health || null,
        }));
        return { summaryData, accountData, positionData, orderData, fillData, signalData, linkData };
      })
      .catch((error) => setState((prev) => ({ ...prev, loading: false, error: error.message })));
  }

  function refreshAll() {
    load();
    loadTaskTelemetry();
  }

  useEffect(() => {
    refreshAll();
    const timer = window.setInterval(loadTaskTelemetry, 10000);
    return () => window.clearInterval(timer);
  }, []);

  function evaluateExits() {
    if (!mayWrite) {
      setState((prev) => ({ ...prev, error: '当前账号没有交易评估权限' }));
      return;
    }
    if (!window.confirm('检查止盈止损会按当前规则生成模拟卖单和成交，确认继续？')) {
      return;
    }
    setState((prev) => ({ ...prev, actionLoading: true, error: '', message: '' }));
    api.evaluatePaperExits({ account_id: defaultAccount?.id })
      .then((result) => {
        setState((prev) => ({
          ...prev,
          message: `卖出评估完成：生成 ${result.orders?.length || 0} 笔订单，跳过 ${result.skipped?.length || 0} 个持仓，阻断 ${result.blocked?.length || 0} 个持仓`,
        }));
        load();
      })
      .catch((error) => setState((prev) => ({ ...prev, error: error.message })))
      .finally(() => setState((prev) => ({ ...prev, actionLoading: false })));
  }

  function markToMarket() {
    if (!mayWrite) {
      setState((prev) => ({ ...prev, error: '当前账号没有持仓盯市权限' }));
      return;
    }
    setState((prev) => ({ ...prev, actionLoading: true, error: '', message: '' }));
    api.markPaperToMarket({ account_id: defaultAccount?.id })
      .then((result) => {
        const stale = result.stale?.length || 0;
        const missing = result.missing?.length || 0;
        setState((prev) => ({ ...prev, message: `持仓盯市完成：更新 ${result.updated || 0} 条，过期 ${stale} 条，缺失 ${missing} 条` }));
        load();
      })
      .catch((error) => setState((prev) => ({ ...prev, error: error.message })))
      .finally(() => setState((prev) => ({ ...prev, actionLoading: false })));
  }

  function runClosedLoop() {
    if (!mayWrite) {
      setState((prev) => ({ ...prev, error: '当前账号没有闭环执行权限' }));
      return;
    }
    if (!window.confirm('运行今日闭环会执行策略扫描，并可能生成模拟买单、卖单和成交记录，确认继续？')) {
      return;
    }
    const loopBefore = loopSnapshotFromState(state);
    setState((prev) => ({
      ...prev,
      actionLoading: true,
      error: '',
      message: '',
      loopBefore,
      loopStatus: 'running',
      lastLoopEvaluation: null,
    }));
    api.runPaperCompleteLoop({
      account_id: defaultAccount?.id,
      run_strategies: true,
      sync_snapshots: true,
      evaluate_exits: true,
    })
      .then((result) => {
        const monitor = result.position_monitor || result || {};
        const exitSummary = monitor.exit_summary || {};
        const snapshot = monitor.snapshot_sync || {};
        const strategySummary = result.strategy_summary || {};
        saveStoredLoopState(loopBefore, result);
        setState((prev) => ({
          ...prev,
          lastLoopEvaluation: result,
          loopStatus: result.status || 'completed',
          message: `闭环执行完成：策略运行 ${strategySummary.executed || 0} 个，买入 ${strategySummary.buy_orders || 0} 笔，同步行情 ${snapshot.snapshot_count || 0} 条，更新持仓 ${sumAccountMetric(monitor.accounts || [], 'mark_to_market', 'updated')} 条，生成卖单 ${exitSummary.orders || 0} 笔`,
        }));
        refreshAll();
      })
      .catch((error) => setState((prev) => ({ ...prev, loopStatus: 'error', error: error.message })))
      .finally(() => setState((prev) => ({ ...prev, actionLoading: false })));
  }

  function resetAccount() {
    if (!mayAdmin || !defaultAccount) {
      setState((prev) => ({ ...prev, error: '当前操作需要 admin 权限' }));
      return;
    }
    if (!window.confirm('重置会清空当前模拟账户记录，此操作仅限重新演练闭环，确认重置？')) {
      return;
    }
    setState((prev) => ({ ...prev, actionLoading: true, error: '', message: '' }));
    api.resetPaperAccount(defaultAccount.id)
      .then(load)
      .catch((error) => setState((prev) => ({ ...prev, error: error.message })))
      .finally(() => setState((prev) => ({ ...prev, actionLoading: false })));
  }

  return (
    <main className="page" data-testid="paper-trading-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Paper Trading</p>
          <h1>模拟交易闭环</h1>
          <p className="muted">从策略选标的到买入、行情同步、持仓盯盘、止盈止损和复盘归因。</p>
        </div>
        <div className="button-row">
          <button type="button" data-testid="paper-run-loop-button" onClick={runClosedLoop} disabled={state.actionLoading || !mayWrite}>
            运行今日闭环
          </button>
          <button type="button" data-testid="paper-refresh-button" className="btn-secondary" onClick={refreshAll} disabled={state.loading}>刷新状态</button>
        </div>
      </div>

      <RiskDisclaimer />

      {state.error ? <div className="alert">{state.error}</div> : null}
      {state.message ? <div className="alert success">{state.message}</div> : null}
      {!mayWrite ? <div className="alert warning">当前账号只能查看模拟交易，不能触发评估或重置。</div> : null}
      {state.loading ? <div className="card loading-card">正在读取模拟交易账户...</div> : null}

      <section className="grid section-gap paper-account-grid" data-testid="paper-account-risk">
        <article className="card">
          <h2>账户权益</h2>
          <p>{money(summary.equity)}</p>
        </article>
        <article className="card">
          <h2>可用现金</h2>
          <p>{money(summary.cash)}</p>
        </article>
        <article className="card">
          <h2>持仓市值</h2>
          <p>{money(summary.market_value)}</p>
        </article>
        <article className="card">
          <h2>总收益率</h2>
          <p><span className={`status-badge ${toneForPnl(summary.total_return_pct)}`}>{pct(summary.total_return_pct)}</span></p>
        </article>
        <article className="card">
          <h2>活跃持仓</h2>
          <p>{summary.active_positions ?? 0}</p>
        </article>
        <article className="card">
          <h2>今日买入/卖出</h2>
          <p>{buyOrderCount} / {sellOrderCount}</p>
        </article>
        <article className="card">
          <h2>链路完整率</h2>
          <p><span className={`status-badge ${linkRateTone(state.linkHealth)}`}>{linkRateLabel(state.linkHealth)}</span></p>
        </article>
      </section>

      <section id="paper-loop-section" className="card section-gap paper-loop-panel" data-testid="paper-loop-panel">
        <div className="section-title-row">
          <div>
            <h2>今日闭环驾驶舱</h2>
            <p className="muted">按交易流程呈现：选标的、买入、行情同步、盯盘、止盈止损、复盘归因。</p>
          </div>
          <span className={`status-badge ${state.loopStatus === 'running' ? 'info' : lastLoopEvaluation?.status === 'completed' ? 'success' : lastLoopEvaluation?.status === 'completed_with_errors' || state.linkHealth?.status === 'degraded' ? 'warning' : 'info'}`}>
            {state.loopStatus === 'running' ? '执行中' : lastLoopEvaluation?.status === 'completed' ? '刚执行' : lastLoopEvaluation?.status === 'completed_with_errors' ? '部分完成' : '等待执行'}
          </span>
        </div>
        <div className={`paper-loop-verdict ${loopHealth.tone}`}>
          <div>
            <strong>{loopHealth.title}</strong>
            <span>{loopHealth.detail}</span>
          </div>
          <small>模拟成交会写入账户簿，实盘接口保持禁用隔离。</small>
        </div>
        <div className="paper-loop-flow" data-testid="paper-loop-flow">
          {cockpitSteps.map((item, index) => (
            <div className={`paper-loop-node ${item.tone}`} key={item.label}>
              <span className="paper-loop-index">{index + 1}</span>
              <span>
                <strong>{item.label}</strong>
                <small>{item.detail}</small>
              </span>
              <b>{item.value}</b>
            </div>
          ))}
        </div>
        <div className="paper-action-strip" data-testid="paper-action-strip">
          <button type="button" className="btn-secondary" onClick={markToMarket} disabled={state.actionLoading || !mayWrite}>同步持仓行情</button>
          <button type="button" className="btn-secondary" onClick={evaluateExits} disabled={state.actionLoading || !mayWrite}>检查止盈止损</button>
          <button type="button" className="btn-secondary" onClick={() => scrollToEvidence('paper-evidence-section')}>查看明细证据</button>
        </div>
        {lastLoopEvaluation ? (
          <div className="paper-loop-result">
            <div>
              <span>行情同步</span>
              <strong>{loopSnapshot.snapshot_count || 0}</strong>
              <small>写入 {loopSnapshot.persisted_snapshots || 0} 条 / {loopSnapshot.source || '-'}</small>
            </div>
            <div>
              <span>账户检查</span>
              <strong>{loopAccounts.length}</strong>
              <small>持仓 {loopMonitor.position_count || 0} 个</small>
            </div>
            <div>
              <span>闭环时间</span>
              <strong>{lastLoopEvaluation.updated_at ? lastLoopEvaluation.updated_at.slice(11, 19) : '-'}</strong>
              <small>{lastLoopEvaluation.source || '-'}</small>
            </div>
          </div>
        ) : <div className="empty">点击“运行今日闭环”后，这里会显示策略运行、模拟买入、行情同步、持仓盯盘和自动卖出结果</div>}
        {state.loopBefore ? (
          <div className="paper-loop-delta" data-testid="paper-loop-delta">
            {loopDeltas.map((item) => (
              <div key={item.label}>
                <span>{item.label}</span>
                <strong className={`status-badge ${deltaTone(item.value || 0)}`}>
                  {item.money ? (item.value == null ? '-' : signedMoney(item.value)) : deltaLabel(item.value, item.suffix)}
                </strong>
              </div>
            ))}
          </div>
        ) : null}
        {lastLoopEvaluation ? (
          <div className="paper-loop-live-grid">
            <div className="paper-loop-runs" data-testid="paper-loop-runs">
              <div className="paper-loop-subtitle">
                <strong>策略执行明细</strong>
                <span>{loopRunItems.length} 个策略</span>
              </div>
              {loopRunItems.length ? loopRunItems.map((item) => {
                const detail = item.summary || {};
                return (
                  <div className="paper-loop-run-row" key={`${item.strategy_id}-${item.strategy_code}`}>
                    <span>
                      <strong>{item.strategy_code || '-'}</strong>
                      <small>{item.strategy_name || item.status}</small>
                    </span>
                    <span className={`status-badge ${item.status === 'failed' ? 'danger' : item.status === 'completed' ? 'success' : 'info'}`}>
                      {item.status === 'failed' ? '失败' : item.status === 'completed' ? '完成' : item.status}
                    </span>
                    <span>命中 {detail.matched_count || 0}</span>
                    <span>买入 {detail.buy_orders || 0}</span>
                    <span>跳过 {detail.buy_skipped || 0}</span>
                  </div>
                );
              }) : <div className="empty">本次没有可执行策略</div>}
            </div>
            <div className="paper-loop-evidence" data-testid="paper-loop-evidence">
              <div className="paper-loop-subtitle">
                <strong>最新入账证据</strong>
                <span>{lastLoopEvaluation.updated_at?.slice(11, 19) || '-'}</span>
              </div>
              <div className="paper-loop-evidence-list">
                <div>
                  <span>买单</span>
                  <strong>{latestBuy?.symbol || '-'}</strong>
                  <small>{latestBuy ? `${latestBuy.quantity} 股 / ${money(latestBuy.avg_fill_price)}` : '无新增买单'}</small>
                </div>
                <div>
                  <span>卖单</span>
                  <strong>{latestSell?.symbol || '-'}</strong>
                  <small>{latestSell ? `${latestSell.quantity} 股 / ${exitReasonLabel(orderExitReason(latestSell))}` : '无触发卖出'}</small>
                </div>
                <div>
                  <span>成交</span>
                  <strong>{latestFill?.symbol || '-'}</strong>
                  <small>{latestFill ? `${sideLabel(latestFill.side)} / ${money(latestFill.amount)}` : '暂无成交'}</small>
                </div>
                <div>
                  <span>持仓</span>
                  <strong>{latestPosition?.symbol || '-'}</strong>
                  <small>{latestPosition ? `${latestPosition.quantity || 0} 股 / 市值 ${money(latestPosition.market_value)}` : '暂无持仓'}</small>
                </div>
                <div>
                  <span>复盘链路</span>
                  <strong>{latestLink?.status || '-'}</strong>
                  <small>{latestLink ? String(latestLink.source_signal_hash || '').slice(0, 12) : '暂无链路'}</small>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </section>

      <section className="card section-gap paper-position-workbench" data-testid="position-freshness-panel">
        <div className="section-title-row">
          <div>
            <h2>当前持仓盯盘</h2>
            <p className="muted">优先看行情是否新鲜、浮盈浮亏以及距离止盈止损的位置。</p>
          </div>
          <span className={`status-badge ${missingPositions || delayedPositions ? 'warning' : 'success'}`}>
            {missingPositions ? '有缺失' : delayedPositions ? '有延迟' : '可盯盘'}
          </span>
        </div>
        <div className="freshness-summary-grid">
          <article><span>已同步</span><strong>{tradablePositions}</strong></article>
          <article><span>延迟</span><strong>{delayedPositions}</strong></article>
          <article><span>暂无</span><strong>{missingPositions}</strong></article>
        </div>
        {positionCards.length ? (
          <div className="paper-position-card-grid">
            {positionCards.map((item) => {
              const freshness = positionFreshness(item);
              const decision = positionDecision(item, state.links, state.orders);
              return (
                <article className={`paper-position-card ${decision.tone}`} key={`${item.account_id}-${item.symbol}-watch`}>
                  <div className="paper-position-card-head">
                    <span>
                      <strong>{item.symbol}</strong>
                      <small>{positionStrategy(item, state.links, state.orders)}</small>
                    </span>
                    <span className={`status-badge ${decision.tone}`}>{decision.label}</span>
                  </div>
                  <div className="paper-position-card-metrics">
                    <span><small>现价</small><strong>{item.market_price == null ? '-' : money(item.market_price)}</strong></span>
                    <span><small>浮盈亏</small><strong className={`status-badge ${toneForPnl(item.unrealized_pnl)}`}>{money(item.unrealized_pnl)}</strong></span>
                    <span><small>行情</small><strong className={`status-badge ${freshness.tone}`}>{freshness.label}</strong></span>
                  </div>
                  <p>{triggerDistanceText(item, state.links, state.orders)}</p>
                  <small>{freshness.sourceLabel} {freshness.time}</small>
                </article>
              );
            })}
          </div>
        ) : <div className="empty">暂无持仓需要盯盘</div>}
      </section>

      <section className="card section-gap paper-trade-records" data-testid="paper-trade-records">
        <div className="section-title-row">
          <div>
            <h2>最近交易流水</h2>
            <p className="muted">合并展示最近订单和成交，先看账户簿是否真的落账。</p>
          </div>
          <span className="status-badge info">{tradeRecords.length} 条</span>
        </div>
        {tradeRecords.length ? (
          <div className="paper-timeline-list">
            {tradeRecords.map((item, index) => (
              <div className="paper-timeline-item" key={`${item.recordType}-${item.id || index}`}>
                <span className={`status-badge ${String(item.side || '').toUpperCase() === 'SELL' ? 'warning' : item.recordType === 'fill' ? 'success' : 'info'}`}>
                  {item.recordType === 'fill' ? '成交' : sideLabel(item.side)}
                </span>
                <span><strong>{item.symbol || '-'}</strong><small>{item.strategy_code || securityMeta(item) || '-'}</small></span>
                <span>{item.quantity || '-'} / {money(item.avg_fill_price ?? item.price)}</span>
                <span>{item.recordTime || '-'}</span>
              </div>
            ))}
          </div>
        ) : <div className="empty">暂无交易流水</div>}
      </section>

      <section className="card section-gap paper-attribution-panel" data-testid="paper-attribution-panel">
        <div className="section-title-row">
          <div>
            <h2>复盘归因</h2>
            <p className="muted">按标的串起策略信号、买入、卖出和实现收益。</p>
          </div>
          <span className={`status-badge ${linkRateTone(state.linkHealth)}`}>{linkRateLabel(state.linkHealth)}</span>
        </div>
        {attributionItems.length ? (
          <div className="paper-attribution-list">
            {attributionItems.map((item) => (
              <div className="paper-attribution-item" key={item.id}>
                <span>
                  <strong>{item.metadata?.symbol || '-'}</strong>
                  <small>{item.metadata?.strategy_code || '-'}</small>
                </span>
                <span className={`status-badge ${item.status === 'closed' ? 'info' : 'success'}`}>{item.status === 'closed' ? '已闭合' : '持仓中'}</span>
                <span>买入 {item.buy_order_id && item.buy_fill_id ? '完成' : '待补证据'}</span>
                <span>卖出 {item.sell_order_id || item.sell_fill_id ? '有记录' : '未触发'}</span>
                <span>{item.realized_return_pct == null ? '-' : returnPercent(item.realized_return_pct)}</span>
              </div>
            ))}
          </div>
        ) : <div className="empty">暂无复盘归因记录</div>}
      </section>

      <details id="paper-evidence-section" className="card section-gap paper-evidence-details" data-testid="paper-evidence-section">
        <summary>明细与证据台账</summary>
        <p className="muted">这里保留完整持仓、策略信号、复盘链路、订单和成交记录，便于专业排查。</p>

      <section id="paper-positions-section" className="table paper-positions-table section-gap" data-testid="paper-positions-table">
        <div className="table-row table-head">
          <span>标的</span>
          <span>持仓</span>
          <span>成本</span>
          <span>现价</span>
          <span>市值</span>
          <span>浮动盈亏</span>
          <span>卖出计划</span>
          <span>行情时效</span>
        </div>
        {state.positions.length ? state.positions.map((item) => {
          const freshness = positionFreshness(item);
          return (
            <div className="table-row" key={`${item.account_id}-${item.symbol}`}>
              <span><strong>{item.symbol}</strong>{securityMeta(item) ? <small>{securityMeta(item)}</small> : null}</span>
              <span>{item.quantity}</span>
              <span>{money(item.avg_cost)}</span>
              <span>{item.market_price == null ? '-' : money(item.market_price)}</span>
              <span>{money(item.market_value)}</span>
              <span><span className={`status-badge ${toneForPnl(item.unrealized_pnl)}`}>{money(item.unrealized_pnl)}</span></span>
              <span><strong>{positionStrategy(item, state.links, state.orders)}</strong><small>{exitPlanSummary(item, state.links, state.orders)}</small></span>
              <span><span className={`status-badge ${freshness.tone}`}>{freshness.label}</span><small>{freshness.sourceLabel} {freshness.time}</small></span>
            </div>
          );
        }) : <div className="empty">暂无模拟持仓</div>}
      </section>

      <section id="paper-signals-section" className="table paper-signals-table section-gap" data-testid="paper-signals-table">
        <div className="table-row table-head">
          <span>信号</span>
          <span>策略</span>
          <span>战法阶段</span>
          <span>量能阶段</span>
          <span>方向</span>
          <span>状态</span>
          <span>价格</span>
          <span>质量</span>
          <span>日期</span>
        </div>
        {state.signals.length ? state.signals.map((item) => (
          <div className="table-row" key={item.id}>
            <span><strong>{item.symbol}</strong>{securityMeta(item) ? <small>{securityMeta(item)}</small> : null}</span>
            <span>{item.strategy_code || '-'}</span>
            <span>{signalSubtypeLabel(item)}</span>
            <span>{volumePhaseLabel(item)}</span>
            <span><span className="status-badge success">{item.signal_type}</span></span>
            <span><span className={`status-badge ${item.status === 'closed' ? 'info' : 'success'}`}>{item.status || 'open'}</span></span>
            <span>{item.price_ref == null ? '-' : money(item.price_ref)}</span>
            <span>{item.data_quality || '-'}</span>
            <span>{item.signal_date || '-'}</span>
          </div>
        )) : <div className="empty">暂无策略交易信号</div>}
      </section>

      <section id="paper-links-section" className="table paper-links-table section-gap" data-testid="paper-links-table">
        {state.linkHealth?.status === 'degraded' ? (
          <div className="alert warning">闭环链路存在 {state.linkHealth.incomplete} 条不完整记录，请优先检查缺失的 pick、订单或成交。</div>
        ) : null}
        <div className="table-row table-head">
          <span>信号哈希</span>
          <span>状态</span>
          <span>Pick</span>
          <span>买单/成交</span>
          <span>卖单/成交</span>
          <span>实现收益</span>
          <span>更新时间</span>
        </div>
        {state.links.length ? state.links.map((item) => (
          <div className="table-row" key={item.id}>
            <span><strong>{String(item.source_signal_hash || '').slice(0, 12)}</strong><small>{item.metadata?.symbol || item.metadata?.strategy_code || '-'}</small></span>
            <span><span className={`status-badge ${item.status === 'closed' ? 'info' : 'success'}`}>{item.status}</span></span>
            <span>{item.pick_id || '-'}</span>
            <span>{[item.buy_order_id, item.buy_fill_id].filter(Boolean).join(' / ') || '-'}</span>
            <span>{[item.sell_order_id, item.sell_fill_id].filter(Boolean).join(' / ') || '-'}</span>
            <span>{item.realized_return_pct == null ? '-' : returnPercent(item.realized_return_pct)}</span>
            <span>{item.updated_at || item.created_at || '-'}</span>
          </div>
        )) : <div className="empty">暂无信号复盘链路</div>}
      </section>

      <section id="paper-orders-section" className="table paper-orders-table section-gap" data-testid="paper-orders-table">
        <div className="table-row table-head">
          <span>订单</span>
          <span>方向</span>
          <span>数量</span>
          <span>成交价</span>
          <span>卖出原因</span>
          <span>状态</span>
          <span>时间</span>
        </div>
        {state.orders.length ? state.orders.map((item) => (
          <div className="table-row" key={item.id}>
            <span><strong>{item.symbol}</strong><small>{[item.strategy_code, securityMeta(item)].filter(Boolean).join(' / ') || '-'}</small></span>
            <span><span className={`status-badge ${item.side === 'BUY' ? 'success' : 'warning'}`}>{sideLabel(item.side)}</span></span>
            <span>{item.quantity}</span>
            <span>{item.avg_fill_price == null ? '-' : money(item.avg_fill_price)}</span>
            <span>{String(item.side || '').toUpperCase() === 'SELL' ? exitReasonLabel(orderExitReason(item)) : '-'}</span>
            <span>{item.status}</span>
            <span>{item.created_at || '-'}</span>
          </div>
        )) : <div className="empty">暂无模拟订单</div>}
      </section>

      <section id="paper-fills-section" className="table paper-fills-table section-gap" data-testid="paper-fills-table">
        <div className="table-row table-head">
          <span>成交</span>
          <span>方向</span>
          <span>数量</span>
          <span>价格</span>
          <span>金额</span>
          <span>说明</span>
          <span>时间</span>
        </div>
        {state.fills.length ? state.fills.map((item) => (
          <div className="table-row" key={item.id}>
            <span><strong>{item.symbol}</strong>{securityMeta(item) ? <small>{securityMeta(item)}</small> : null}</span>
            <span>{sideLabel(item.side)}</span>
            <span>{item.quantity}</span>
            <span>{money(item.price)}</span>
            <span>{money(item.amount)}</span>
            <span>{String(item.side || '').toUpperCase() === 'SELL' ? exitReasonLabel(fillExitReason(item, state.orders)) : '-'}</span>
            <span>{item.filled_at || '-'}</span>
          </div>
        )) : <div className="empty">暂无模拟成交</div>}
      </section>
      </details>
    </main>
  );
}
