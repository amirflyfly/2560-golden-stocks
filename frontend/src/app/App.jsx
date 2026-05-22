import { useEffect, useState, useSyncExternalStore } from 'react';
import { api } from '../api/client';
import { DEFAULT_AUTHZ } from '../auth/permissions';
import { AppShell } from '../components/layout';
import { getTenantState, subscribeTenant, updateTenantId } from '../stores/tenantStore';
import { AdminPage } from '../pages/AdminPage';
import { DashboardPage } from '../pages/DashboardPage';
import { LoginPage } from '../pages/LoginPage';
import { MarketDiscoveryPage } from '../pages/MarketDiscoveryPage';
import { MarketSyncPage } from '../pages/MarketSyncPage';
import { MonitoringPage } from '../pages/MonitoringPage';
import { PaperTradingPage } from '../pages/PaperTradingPage';
import { PicksPage } from '../pages/PicksPage';
import { ReportsPage } from '../pages/ReportsPage';
import { ScansPage } from '../pages/ScansPage';
import { StockKlinePage } from '../pages/StockKlinePage';
import { StrategiesPage } from '../pages/StrategiesPage';

const pages = {
  dashboard: DashboardPage,
  discovery: MarketDiscoveryPage,
  strategies: StrategiesPage,
  scans: ScansPage,
  trading: PaperTradingPage,
  kline: StockKlinePage,
  picks: PicksPage,
  reports: ReportsPage,
  monitoring: MonitoringPage,
  sync: MarketSyncPage,
  admin: AdminPage,
};

const pageMeta = {
  dashboard: { title: '今日行动指挥台', subtitle: '判断今日是否可扫描、可复盘、可回测、可上线，并查看阻断原因。' },
  discovery: { title: '市场发现', subtitle: '扫描前先看市场宽度、强势样本、活跃标的和行情质量。' },
  strategies: { title: '策略管理 / 回测验证', subtitle: '查看策略能力、运行回测并沉淀验证结果。' },
  scans: { title: '策略扫描', subtitle: '创建扫描任务，解释候选原因，并把标的加入选股池。' },
  kline: { title: '股票 K 线', subtitle: '查看个股走势、均线和复盘线索。' },
  picks: { title: '选股池', subtitle: '管理候选标的、观察状态和复盘结论。' },
  reports: { title: '研究报表', subtitle: '归档研究结论、策略表现和数据质量。' },
  trading: { title: '模拟验证', subtitle: '验证策略命中后的模拟订单、成交、持仓和账户权益，不代表真实成交。' },
  sync: { title: '数据中心', subtitle: '管理本地行情仓、同步任务和每只股票的数据覆盖。' },
  monitoring: { title: '生产监控', subtitle: '检查服务、任务、日志健康状态和上线门禁。' },
  admin: { title: '后台管理', subtitle: '管理用户、角色、租户、审计记录和上线检查入口。' },
};

const navGroups = [
  {
    title: '今日',
    items: [
      ['dashboard', '今日行动指挥台', 'nav-dashboard'],
    ],
  },
  {
    title: '发现与研究',
    items: [
      ['discovery', '市场发现', 'nav-discovery'],
      ['scans', '策略扫描', 'nav-scans'],
      ['picks', '选股池', 'nav-picks'],
      ['kline', '股票 K 线', 'nav-kline'],
    ],
  },
  {
    title: '验证与报表',
    items: [
      ['strategies', '策略管理 / 回测验证', 'nav-strategies'],
      ['reports', '研究报表', 'nav-reports'],
      ['trading', '模拟验证', 'nav-trading'],
    ],
  },
  {
    title: '系统',
    items: [
      ['sync', '数据中心', 'nav-sync'],
      ['monitoring', '生产监控', 'nav-monitoring'],
      ['admin', '后台管理', 'nav-admin'],
    ],
  },
];

function getInitialRoute() {
  if (typeof window === 'undefined') return { page: 'dashboard', payload: {} };
  const params = new URLSearchParams(window.location.search);
  const requestedPage = params.get('page') || 'dashboard';
  const page = pages[requestedPage] ? requestedPage : 'dashboard';
  const symbol = params.get('symbol') || params.get('code') || '';
  const strategyCode = params.get('strategy_code') || params.get('strategy') || '';
  const status = params.get('status') || '';
  const pickId = params.get('pick_id') || params.get('id') || '';
  return {
    page,
    payload: {
      ...(symbol ? { symbol } : {}),
      ...(strategyCode ? { strategy_code: strategyCode } : {}),
      ...(status ? { status } : {}),
      ...(pickId ? { pick_id: pickId } : {}),
    },
  };
}

function syncRoute(nextPage, payload = {}) {
  if (typeof window === 'undefined') return;
  const currentParams = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  const tenantId = currentParams.get('tenant_id');
  if (tenantId) params.set('tenant_id', tenantId);
  params.set('page', nextPage);
  Object.entries(payload || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      params.delete(key);
    } else {
      params.set(key, String(value));
    }
  });
  window.history.pushState({ page: nextPage, payload }, '', `${window.location.pathname}?${params.toString()}`);
}

export function App() {
  const initialRoute = getInitialRoute();
  const [page, setPage] = useState(initialRoute.page);
  const [pagePayload, setPagePayload] = useState(initialRoute.payload);
  const [authz, setAuthz] = useState(DEFAULT_AUTHZ);
  const [authState, setAuthState] = useState('checking');
  const tenantState = useSyncExternalStore(subscribeTenant, getTenantState, getTenantState);
  const Page = pages[page];
  const meta = pageMeta[page];
  const navigate = (nextPage, payload = {}) => {
    if (!pages[nextPage]) return;
    syncRoute(nextPage, payload);
    setPagePayload(payload || {});
    setPage(nextPage);
  };

  useEffect(() => {
    let alive = true;
    setAuthState('checking');
    setAuthz((prev) => ({ ...prev, loading: true, error: '' }));
    api.me()
      .then((profile) => {
        if (!alive) return;
        setAuthz({ ...profile, loading: false, error: '' });
        setAuthState('authenticated');
      })
      .catch((error) => {
        if (!alive) return;
        setAuthz({ ...DEFAULT_AUTHZ, loading: false, error: error.message });
        setAuthState('login');
      });
    return () => {
      alive = false;
    };
  }, [tenantState.tenantId]);

  async function handleLogin(credentials) {
    const session = await api.login(credentials);
    if (session?.tenant_id && String(session.tenant_id) !== tenantState.tenantId) {
      updateTenantId(session.tenant_id);
    }
    const profile = await api.me();
    setAuthz({ ...profile, loading: false, error: '' });
    setAuthState('authenticated');
  }

  async function handleLogout() {
    try {
      await api.logout();
    } finally {
      setAuthz({ ...DEFAULT_AUTHZ, loading: false, error: '' });
      setAuthState('login');
    }
  }

  useEffect(() => {
    const handlePopState = () => {
      const route = getInitialRoute();
      setPagePayload(route.payload);
      setPage(route.page);
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  if (authState === 'checking') {
    return (
      <main className="login-screen">
        <section className="login-panel compact">
          <p className="login-eyebrow">2560 Strategy</p>
          <h1>正在确认会话</h1>
        </section>
      </main>
    );
  }

  if (authState === 'login') {
    return <LoginPage onLogin={handleLogin} authError={authz.error} />;
  }

  return (
    <AppShell page={page} meta={meta} navGroups={navGroups} onNavigate={navigate} authz={authz} onLogout={handleLogout}>
      {() => <Page onNavigate={navigate} pagePayload={pagePayload} initialSymbol={pagePayload.symbol} authz={authz} />}
    </AppShell>
  );
}
