const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1';

function getCookieValue(name) {
  const cookie = document.cookie
    .split('; ')
    .find((row) => row.startsWith(name + '='));
  return cookie ? decodeURIComponent(cookie.split('=').slice(1).join('=')) : '';
}

function getCsrfToken() {
  return getCookieValue('promo_panel_csrf');
}

export class ApiError extends Error {
  constructor(message, response, payload) {
    super(message);
    this.name = 'ApiError';
    this.response = response;
    this.payload = payload;
  }
}

export function getTenantId() {
  return localStorage.getItem('tenant_id') || '1';
}

export function setTenantId(tenantId) {
  localStorage.setItem('tenant_id', String(tenantId));
}

export async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('Accept', 'application/json');
  headers.set('X-Tenant-ID', getTenantId());
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes((options.method || 'GET').toUpperCase())) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers.set('X-CSRF-Token', csrfToken);
    }
  }

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'same-origin',
    ...options,
    headers,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || payload?.code !== 0) {
    throw new ApiError(payload?.message || response.statusText, response, payload);
  }
  return payload.data;
}

export async function requestFile(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('Accept', options.accept || '*/*');
  headers.set('X-Tenant-ID', getTenantId());

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'same-origin',
    ...options,
    headers,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(payload?.message || response.statusText, response, payload);
  }
  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') || '';
  const filename = disposition.match(/filename=([^;]+)/)?.[1]?.replaceAll('"', '') || 'report-export';
  return { blob, filename };
}

export const api = {
  health: () => request('/health', { headers: { 'X-Tenant-ID': getTenantId() } }),
  authBootstrap: () => request('/auth/bootstrap'),
  login: (payload) => request('/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  logout: () => request('/auth/logout', { method: 'POST', body: JSON.stringify({}) }),
  me: () => request('/me'),
  marketDataHealth: () => request('/market-data/health'),
  marketDiscovery: (params = {}) => request(`/market-discovery?${new URLSearchParams(params)}`),
  strategies: (params = {}) => request(`/strategies?${new URLSearchParams(params)}`),
  createStrategy: (payload) => request('/strategies', { method: 'POST', body: JSON.stringify(payload) }),
  updateStrategy: (strategyId, payload) => request(`/strategies/${encodeURIComponent(strategyId)}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  testStrategy: (strategyId, payload = {}) => request(`/strategies/${encodeURIComponent(strategyId)}/test`, { method: 'POST', body: JSON.stringify(payload) }),
  deployStrategy: (strategyId) => request(`/strategies/${encodeURIComponent(strategyId)}/deploy`, { method: 'POST', body: JSON.stringify({}) }),
  productionRunStrategy: (strategyId, payload = {}) => request(`/strategies/${encodeURIComponent(strategyId)}/production-run`, { method: 'POST', body: JSON.stringify(payload) }),
  strategyBacktest: (strategyCode, payload) => request(`/strategies/${encodeURIComponent(strategyCode)}/backtest`, { method: 'POST', body: JSON.stringify(payload) }),
  strategyBacktests: (strategyCode, params = {}) => request(`/strategies/${encodeURIComponent(strategyCode)}/backtests?${new URLSearchParams(params)}`),
  strategyBacktestDetail: (strategyCode, backtestId) => request(`/strategies/${encodeURIComponent(strategyCode)}/backtests/${encodeURIComponent(backtestId)}`),
  scans: (params = {}) => request(`/scans?${new URLSearchParams(params)}`),
  createScan: (payload) => request('/scans', { method: 'POST', body: JSON.stringify(payload) }),
  scanResults: (scanId, params = {}) => request(`/scans/${scanId}/results?${new URLSearchParams(params)}`),
  picks: (params = {}) => request(`/picks?${new URLSearchParams(params)}`),
  createPick: (payload) => request('/picks', { method: 'POST', body: JSON.stringify(payload) }),
  pick: (pickId) => request(`/picks/${encodeURIComponent(pickId)}`),
  updatePickReview: (pickId, payload) => request(`/picks/${encodeURIComponent(pickId)}/review`, { method: 'PATCH', body: JSON.stringify(payload) }),
  batchUpdatePickReview: (payload) => request('/picks/batch/review', { method: 'PATCH', body: JSON.stringify(payload) }),
  pickTimeline: (pickId) => request(`/picks/${encodeURIComponent(pickId)}/timeline`),
  reports: (params = {}) => request(`/reports?${new URLSearchParams(params)}`),
  reportSummary: (params = {}) => request(`/reports/summary?${new URLSearchParams(params)}`),
  exportReportSummary: (params = {}) => requestFile(`/reports/summary/export?${new URLSearchParams(params)}`),
  stocks: (params = {}) => request(`/stocks?${new URLSearchParams(params)}`),
  stockKline: (symbol, params = {}) => request(`/stocks/${encodeURIComponent(symbol)}/kline?${new URLSearchParams(params)}`),
  stockContext: (symbol, params = {}) => request(`/stocks/${encodeURIComponent(symbol)}/context?${new URLSearchParams(params)}`),
  tasks: (params = {}) => request(`/tasks?${new URLSearchParams(params)}`),
  task: (taskId) => request(`/tasks/${encodeURIComponent(taskId)}`),
  cancelTask: (taskId) => request(`/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST', body: JSON.stringify({}) }),
  createMarketSync: (payload) => request('/market-data/sync', { method: 'POST', body: JSON.stringify(payload) }),
  marketDataCoverage: (params = {}) => request(`/market-data/coverage?${new URLSearchParams(params)}`),
  marketDataSyncState: (params = {}) => request(`/market-data/sync/state?${new URLSearchParams(params)}`),
  marketDataSyncRuns: (params = {}) => request(`/market-data/sync/runs?${new URLSearchParams(params)}`),
  createMarketBootstrap: (payload) => request('/market-data/bootstrap', { method: 'POST', body: JSON.stringify(payload) }),
  createMarketSnapshotSync: (payload) => request('/market-data/snapshots/sync', { method: 'POST', body: JSON.stringify(payload) }),
  marketDataSnapshots: (params = {}) => request(`/market-data/snapshots?${new URLSearchParams(params)}`),
  paperSummary: (params = {}) => request(`/trading/paper/summary?${new URLSearchParams(params)}`),
  paperAccounts: () => request('/trading/paper/accounts'),
  paperPositions: (params = {}) => request(`/trading/paper/positions?${new URLSearchParams(params)}`),
  paperOrders: (params = {}) => request(`/trading/paper/orders?${new URLSearchParams(params)}`),
  paperFills: (params = {}) => request(`/trading/paper/fills?${new URLSearchParams(params)}`),
  tradeSignals: (params = {}) => request(`/trading/signals?${new URLSearchParams(params)}`),
  evaluatePaperExits: (payload = {}) => request('/trading/paper/evaluate-exits', { method: 'POST', body: JSON.stringify(payload) }),
  resetPaperAccount: (accountId) => request(`/trading/paper/accounts/${encodeURIComponent(accountId)}/reset`, { method: 'POST', body: JSON.stringify({}) }),
  monitoringOverview: () => request('/monitoring/overview'),
  monitoringMetrics: () => request('/monitoring/metrics'),
  monitoringLogs: (params = {}) => request(`/monitoring/logs?${new URLSearchParams(params)}`),
  savedViews: () => request('/settings/saved-views'),
  createSavedView: (payload) => request('/settings/saved-views', { method: 'POST', body: JSON.stringify(payload) }),
  updateSavedView: (viewId, payload) => request(`/settings/saved-views/${encodeURIComponent(viewId)}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteSavedView: (viewId) => request(`/settings/saved-views/${encodeURIComponent(viewId)}`, { method: 'DELETE' }),
  alertRules: () => request('/settings/alerts'),
  createAlertRule: (payload) => request('/settings/alerts', { method: 'POST', body: JSON.stringify(payload) }),
  updateAlertRule: (alertId, payload) => request(`/settings/alerts/${encodeURIComponent(alertId)}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteAlertRule: (alertId) => request(`/settings/alerts/${encodeURIComponent(alertId)}`, { method: 'DELETE' }),
  notifications: (params = {}) => request(`/settings/notifications?${new URLSearchParams(params)}`),
  evaluateNotifications: (payload = {}) => request('/settings/notifications/evaluate', { method: 'POST', body: JSON.stringify(payload) }),
  markNotificationRead: (notificationId) => request(`/settings/notifications/${encodeURIComponent(notificationId)}/read`, { method: 'PATCH', body: JSON.stringify({ read: true }) }),
  adminUsers: () => request('/admin/users'),
  adminAuditLogs: (params = {}) => request(`/admin/audit-logs?${new URLSearchParams(params)}`),
  setUserActive: (userId, isActive) => request(`/admin/users/${encodeURIComponent(userId)}/active`, { method: 'PATCH', body: JSON.stringify({ is_active: isActive }) }),
  setUserRole: (userId, role) => request(`/admin/users/${encodeURIComponent(userId)}/role`, { method: 'PATCH', body: JSON.stringify({ role }) }),
  adminTenants: () => request('/admin/tenants'),
};
