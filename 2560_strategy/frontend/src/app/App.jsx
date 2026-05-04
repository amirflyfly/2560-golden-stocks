import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { DEFAULT_AUTHZ } from '../auth/permissions';
import { AppShell } from '../components/layout';
import { AdminPage } from '../pages/AdminPage';
import { DashboardPage } from '../pages/DashboardPage';
import { MarketSyncPage } from '../pages/MarketSyncPage';
import { MonitoringPage } from '../pages/MonitoringPage';
import { PicksPage } from '../pages/PicksPage';
import { ReportsPage } from '../pages/ReportsPage';
import { ScansPage } from '../pages/ScansPage';
import { StockKlinePage } from '../pages/StockKlinePage';
import { StrategiesPage } from '../pages/StrategiesPage';

const pages = {
  dashboard: DashboardPage,
  strategies: StrategiesPage,
  scans: ScansPage,
  kline: StockKlinePage,
  picks: PicksPage,
  reports: ReportsPage,
  monitoring: MonitoringPage,
  sync: MarketSyncPage,
  admin: AdminPage,
};

const pageMeta = {
  dashboard: { title: '今日工作台', subtitle: '集中查看扫描、候选、行情源和任务健康状态。' },
  strategies: { title: '策略管理', subtitle: '查看策略能力、运行回测并沉淀验证结果。' },
  scans: { title: '策略扫描', subtitle: '创建扫描任务，解释候选原因，并把标的加入选股池。' },
  kline: { title: '股票 K 线', subtitle: '查看个股走势、均线和复盘线索。' },
  picks: { title: '选股池', subtitle: '管理候选标的、观察状态和复盘结论。' },
  reports: { title: '研究报告', subtitle: '归档研究结论和策略解释。' },
  monitoring: { title: '生产监控', subtitle: '检查服务、任务和日志健康状态。' },
  sync: { title: '行情同步', subtitle: '同步股票行情并查看任务进度。' },
  admin: { title: '后台管理', subtitle: '管理用户、角色、租户和审计记录。' },
};

const navGroups = [
  {
    title: '工作区',
    items: [
      ['dashboard', '首页看板', 'nav-dashboard'],
      ['strategies', '策略管理', 'nav-strategies'],
      ['scans', '策略扫描', 'nav-scans'],
    ],
  },
  {
    title: '研究',
    items: [
      ['kline', '股票 K 线', 'nav-kline'],
      ['picks', '选股池', 'nav-picks'],
      ['reports', '研究报告', 'nav-reports'],
    ],
  },
  {
    title: '运维',
    items: [
      ['monitoring', '生产监控', 'nav-monitoring'],
      ['sync', '行情同步', 'nav-sync'],
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

export function App() {
  const initialRoute = getInitialRoute();
  const [page, setPage] = useState(initialRoute.page);
  const [pagePayload, setPagePayload] = useState(initialRoute.payload);
  const [authz, setAuthz] = useState(DEFAULT_AUTHZ);
  const Page = pages[page];
  const meta = pageMeta[page];
  const navigate = (nextPage, payload = {}) => {
    setPagePayload(payload || {});
    setPage(nextPage);
  };

  useEffect(() => {
    let alive = true;
    setAuthz((prev) => ({ ...prev, loading: true, error: '' }));
    api.me()
      .then((profile) => {
        if (alive) setAuthz({ ...profile, loading: false, error: '' });
      })
      .catch((error) => {
        if (alive) setAuthz({ ...DEFAULT_AUTHZ, loading: false, error: error.message });
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <AppShell page={page} meta={meta} navGroups={navGroups} onNavigate={navigate} authz={authz}>
      {() => <Page onNavigate={navigate} pagePayload={pagePayload} initialSymbol={pagePayload.symbol} authz={authz} />}
    </AppShell>
  );
}
