import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { canAdmin, canWrite } from '../auth/permissions';

function money(value) {
  const numeric = Number(value || 0);
  return numeric.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function pct(value) {
  const numeric = Number(value || 0) * 100;
  return `${numeric.toFixed(2)}%`;
}

function toneForPnl(value) {
  const numeric = Number(value || 0);
  if (numeric > 0) return 'success';
  if (numeric < 0) return 'danger';
  return 'info';
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

export function PaperTradingPage({ authz }) {
  const [state, setState] = useState({
    loading: true,
    actionLoading: false,
    error: '',
    summary: null,
    accounts: [],
    positions: [],
    orders: [],
    fills: [],
    signals: [],
  });
  const mayWrite = canWrite(authz);
  const mayAdmin = canAdmin(authz);
  const defaultAccount = state.accounts[0];
  const summary = state.summary || {};

  function load() {
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    Promise.all([
      api.paperSummary(),
      api.paperAccounts(),
      api.paperPositions({ active_only: 0 }),
      api.paperOrders({ limit: 50 }),
      api.paperFills({ limit: 50 }),
      api.tradeSignals({ limit: 50 }),
    ])
      .then(([summaryData, accountData, positionData, orderData, fillData, signalData]) => {
        setState((prev) => ({
          ...prev,
          loading: false,
          summary: summaryData,
          accounts: accountData.items || [],
          positions: positionData.items || [],
          orders: orderData.items || [],
          fills: fillData.items || [],
          signals: signalData.items || [],
        }));
      })
      .catch((error) => setState((prev) => ({ ...prev, loading: false, error: error.message })));
  }

  useEffect(() => {
    load();
  }, []);

  function evaluateExits() {
    if (!mayWrite) {
      setState((prev) => ({ ...prev, error: '当前账号没有交易评估权限' }));
      return;
    }
    setState((prev) => ({ ...prev, actionLoading: true, error: '' }));
    api.evaluatePaperExits({ account_id: defaultAccount?.id })
      .then(load)
      .catch((error) => setState((prev) => ({ ...prev, error: error.message })))
      .finally(() => setState((prev) => ({ ...prev, actionLoading: false })));
  }

  function resetAccount() {
    if (!mayAdmin || !defaultAccount) {
      setState((prev) => ({ ...prev, error: '当前操作需要 admin 权限' }));
      return;
    }
    setState((prev) => ({ ...prev, actionLoading: true, error: '' }));
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
          <h1>模拟交易账户簿</h1>
          <p className="muted">策略生产运行命中后会进入纸上账户，形成订单、成交、持仓和权益汇总。</p>
        </div>
        <div className="button-row">
          <button type="button" data-testid="paper-evaluate-exits-button" className="btn-secondary" onClick={evaluateExits} disabled={state.actionLoading || !mayWrite}>
            评估卖出
          </button>
          <button type="button" data-testid="paper-reset-account-button" className="btn-secondary" onClick={resetAccount} disabled={state.actionLoading || !mayAdmin}>
            重置账户
          </button>
          <button type="button" data-testid="paper-refresh-button" onClick={load} disabled={state.loading}>刷新</button>
        </div>
      </div>

      {state.error ? <div className="alert">{state.error}</div> : null}
      {!mayWrite ? <div className="alert warning">当前账号只能查看模拟交易，不能触发评估或重置。</div> : null}
      {state.loading ? <div className="card loading-card">正在读取模拟交易账户...</div> : null}

      <section className="grid section-gap">
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
      </section>

      <section className="grid section-gap">
        <article className="card">
          <h2>运行模式</h2>
          <p><span className="status-badge info">{summary.mode || 'paper'}</span></p>
        </article>
        <article className="card">
          <h2>实盘接口</h2>
          <p><span className="status-badge warning">预留未启用</span></p>
        </article>
        <article className="card">
          <h2>账户数量</h2>
          <p>{summary.account_count ?? 0}</p>
        </article>
        <article className="card">
          <h2>活跃持仓</h2>
          <p>{summary.active_positions ?? 0}</p>
        </article>
      </section>

      <section className="table paper-positions-table section-gap" data-testid="paper-positions-table">
        <div className="table-row table-head">
          <span>标的</span>
          <span>持仓</span>
          <span>成本</span>
          <span>现价</span>
          <span>市值</span>
          <span>浮动盈亏</span>
        </div>
        {state.positions.length ? state.positions.map((item) => (
          <div className="table-row" key={`${item.account_id}-${item.symbol}`}>
            <span><strong>{item.symbol}</strong>{securityMeta(item) ? <small>{securityMeta(item)}</small> : null}</span>
            <span>{item.quantity}</span>
            <span>{money(item.avg_cost)}</span>
            <span>{item.market_price == null ? '-' : money(item.market_price)}</span>
            <span>{money(item.market_value)}</span>
            <span><span className={`status-badge ${toneForPnl(item.unrealized_pnl)}`}>{money(item.unrealized_pnl)}</span></span>
          </div>
        )) : <div className="empty">暂无模拟持仓</div>}
      </section>

      <section className="table paper-signals-table section-gap" data-testid="paper-signals-table">
        <div className="table-row table-head">
          <span>信号</span>
          <span>策略</span>
          <span>战法阶段</span>
          <span>量能阶段</span>
          <span>方向</span>
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
            <span>{item.price_ref == null ? '-' : money(item.price_ref)}</span>
            <span>{item.data_quality || '-'}</span>
            <span>{item.signal_date || '-'}</span>
          </div>
        )) : <div className="empty">暂无策略交易信号</div>}
      </section>

      <section className="table paper-orders-table section-gap" data-testid="paper-orders-table">
        <div className="table-row table-head">
          <span>订单</span>
          <span>方向</span>
          <span>数量</span>
          <span>成交价</span>
          <span>状态</span>
          <span>时间</span>
        </div>
        {state.orders.length ? state.orders.map((item) => (
          <div className="table-row" key={item.id}>
            <span><strong>{item.symbol}</strong><small>{[item.strategy_code, securityMeta(item)].filter(Boolean).join(' / ') || '-'}</small></span>
            <span><span className={`status-badge ${item.side === 'BUY' ? 'success' : 'warning'}`}>{item.side}</span></span>
            <span>{item.quantity}</span>
            <span>{item.avg_fill_price == null ? '-' : money(item.avg_fill_price)}</span>
            <span>{item.status}</span>
            <span>{item.created_at || '-'}</span>
          </div>
        )) : <div className="empty">暂无模拟订单</div>}
      </section>

      <section className="table paper-fills-table section-gap" data-testid="paper-fills-table">
        <div className="table-row table-head">
          <span>成交</span>
          <span>方向</span>
          <span>数量</span>
          <span>价格</span>
          <span>金额</span>
          <span>时间</span>
        </div>
        {state.fills.length ? state.fills.map((item) => (
          <div className="table-row" key={item.id}>
            <span><strong>{item.symbol}</strong>{securityMeta(item) ? <small>{securityMeta(item)}</small> : null}</span>
            <span>{item.side}</span>
            <span>{item.quantity}</span>
            <span>{money(item.price)}</span>
            <span>{money(item.amount)}</span>
            <span>{item.filled_at || '-'}</span>
          </div>
        )) : <div className="empty">暂无模拟成交</div>}
      </section>
    </main>
  );
}
