import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { canWrite, writeDisabledReason } from '../auth/permissions';
import { DataTable, MetricCard, PageHeader, RiskDisclaimer, SectionCard, StatusBadge } from '../components/common';

const SECURITY_TYPE_OPTIONS = [
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

const SIGNAL_SUBTYPE_LABELS = {
  volume_lock_shrink: '缩量回踩',
  breakout_volume: '放量突破',
  volume_build: '做量蓄势',
  volume_impulse: '冲量启动',
  mild_breakout: '温和突破',
  failed_breakout: '失败突破',
  unknown: '未知信号',
};

const VOLUME_PHASE_LABELS = {
  lock_shrink: '缩量锁筹',
  breakout_expand: '突破放量',
  build: '做量蓄势',
  impulse: '冲量启动',
  active: '量能活跃',
  extreme_risk: '极端放量',
  failed_breakout: '失败突破',
  insufficient: '量能不足',
  unknown: '未知阶段',
};

const LIMIT_UP_RETURN_STRATEGY = {
  code: 'LIMIT_UP_RETURN',
  name: '涨停回马枪',
  category: 'limit-up-pullback',
  description: '涨停锚点后等待缩量回踩，围绕支撑位、触发价和止损价完成 pullback_setup 到 breakout_confirmed 的确认。',
  enabled: true,
  target_security_type: 'stock',
  bar_interval: '1d',
};

const LIMIT_UP_RETURN_NOTES = [
  ['Anchor', '以首个有效涨停日作为锚点，后续只解释接口返回的锚点与价格线。'],
  ['Pullback', '关注回踩天数、缩量比例和支撑位，避免在无支撑的下跌中误触发。'],
  ['Trigger', '突破确认使用触发价，失败时用止损价约束风险。'],
  ['State', '状态从 pullback_setup 进入 breakout_confirmed 时，监控页会给出确认提醒。'],
];

function isLimitUpReturnStrategy(item) {
  return String(item?.code || item?.strategy_code || '').toUpperCase() === 'LIMIT_UP_RETURN';
}

function percent(value) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function benchmarkQualityLabel(benchmark) {
  if (!benchmark) return '-';
  const source = benchmark.source || benchmark.code || '-';
  const quality = benchmark.data_quality || 'unknown';
  return benchmark.fallback_used ? `${quality} / ${source} / fallback` : `${quality} / ${source}`;
}

function todayMinus(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

function safeNumber(value, fallback = null) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function chartBounds(values) {
  const numeric = values.filter((value) => Number.isFinite(value));
  if (!numeric.length) return { min: -0.01, max: 0.01 };
  const rawMin = Math.min(...numeric, 0);
  const rawMax = Math.max(...numeric, 0);
  const padding = Math.max((rawMax - rawMin) * 0.12, 0.01);
  return { min: rawMin - padding, max: rawMax + padding };
}

function linePoints(items, valueGetter, minValue, maxValue) {
  const span = Math.max(maxValue - minValue, 0.000001);
  return items
    .map((item, index) => {
      const value = safeNumber(valueGetter(item), null);
      if (value == null) return null;
      const x = items.length <= 1 ? 0 : (index / (items.length - 1)) * 100;
      const y = 100 - ((value - minValue) / span) * 100;
      return `${x},${Math.max(0, Math.min(100, y))}`;
    })
    .filter(Boolean)
    .join(' ');
}

function buildDrawdownSeries(curve) {
  let peak = 1;
  return curve.map((point, index) => {
    const equity = safeNumber(point.equity, 1 + safeNumber(point.return_pct, 0));
    peak = Math.max(peak, equity);
    const drawdown = peak ? (equity - peak) / peak : 0;
    return { step: point.step ?? index, drawdown };
  });
}

function drawdownValue(point) {
  const value = safeNumber(point?.drawdown ?? point?.drawdown_pct, null);
  if (value == null) return null;
  return value > 0 ? -value : value;
}

function buildTradeBuckets(trades) {
  const buckets = [
    { label: '< -10%', min: -Infinity, max: -0.1, count: 0 },
    { label: '-10% ~ -5%', min: -0.1, max: -0.05, count: 0 },
    { label: '-5% ~ 0', min: -0.05, max: 0, count: 0 },
    { label: '0 ~ 5%', min: 0, max: 0.05, count: 0 },
    { label: '5% ~ 10%', min: 0.05, max: 0.1, count: 0 },
    { label: '> 10%', min: 0.1, max: Infinity, count: 0 },
  ];
  trades.forEach((trade) => {
    const value = safeNumber(trade.return_pct, null);
    if (value == null) return;
    const bucket = buckets.find((item) => value >= item.min && value < item.max) || buckets[buckets.length - 1];
    bucket.count += 1;
  });
  return buckets;
}

function labelFromMap(value, labels, fallback = '未知') {
  if (value == null || value === '') return fallback;
  const key = String(value);
  return labels[key] || key;
}

function normalizeVolumePhases(phases) {
  if (!phases) return [];
  if (Array.isArray(phases)) {
    return phases
      .map((item) => {
        if (Array.isArray(item)) {
          return { phase: String(item[0] || 'unknown'), count: safeNumber(item[1], 0) || 0 };
        }
        if (item && typeof item === 'object') {
          return {
            phase: String(item.phase || item.volume_phase || item.name || item.label || 'unknown'),
            count: safeNumber(item.count ?? item.trade_count ?? item.value, 0) || 0,
          };
        }
        return { phase: String(item || 'unknown'), count: 0 };
      })
      .filter((item) => item.count > 0)
      .sort((left, right) => right.count - left.count || left.phase.localeCompare(right.phase));
  }
  if (typeof phases === 'object') {
    return Object.entries(phases)
      .map(([phase, count]) => ({ phase: String(phase || 'unknown'), count: safeNumber(count, 0) || 0 }))
      .filter((item) => item.count > 0)
      .sort((left, right) => right.count - left.count || left.phase.localeCompare(right.phase));
  }
  return [];
}

function normalizeSignalAttribution(rawAttribution) {
  if (!rawAttribution) return [];
  const rawItems = Array.isArray(rawAttribution)
    ? rawAttribution
    : Array.isArray(rawAttribution.items)
      ? rawAttribution.items
      : Object.entries(rawAttribution)
        .filter(([key, value]) => key !== 'schema_version' && value && typeof value === 'object')
        .map(([key, value]) => ({ signal_subtype: key, ...value }));

  return rawItems
    .filter((item) => item && typeof item === 'object')
    .map((item) => {
      const signalSubtype = String(item.signal_subtype || item.subtype || item.signal || item.type || 'unknown');
      const tradeCount = safeNumber(item.trade_count ?? item.total_trades ?? item.count ?? item.trades, 0) || 0;
      const winCount = safeNumber(item.win_count ?? item.wins, null);
      const winRate = safeNumber(
        item.win_rate ?? item.success_rate ?? item.win_pct,
        winCount == null || !tradeCount ? null : winCount / tradeCount,
      );
      const volumePhases = normalizeVolumePhases(
        item.volume_phases ?? item.volume_phase_distribution ?? item.volume_phase_counts ?? item.phases,
      );
      const primaryPhase = String(item.signal_phase || item.volume_phase || item.phase || item.stage || volumePhases[0]?.phase || 'unknown');
      return {
        signalSubtype,
        primaryPhase,
        tradeCount,
        winRate,
        avgReturn: safeNumber(item.avg_return ?? item.average_return ?? item.avg_return_pct, null),
        maxDrawdown: safeNumber(item.max_drawdown ?? item.drawdown ?? item.max_drawdown_pct, null),
        volumePhases,
      };
    })
    .filter((item) => item.tradeCount > 0 || item.signalSubtype !== 'unknown')
    .sort((left, right) => right.tradeCount - left.tradeCount || left.signalSubtype.localeCompare(right.signalSubtype));
}

export function StrategiesPage({ authz, pagePayload = {} }) {
  const [items, setItems] = useState([]);
  const [selectedCode, setSelectedCode] = useState(pagePayload.strategy_code || '2560');
  const [form, setForm] = useState({
    start_date: todayMinus(90),
    end_date: new Date().toISOString().slice(0, 10),
    holding_days: 5,
    max_positions_per_day: 3,
    trade_limit: 20,
    fee_bps: 0,
    slippage_bps: 0,
    limit_up_down_guard: true,
    benchmark_code: '000300',
    benchmark_return_pct: 0,
    security_type: 'stock',
    bar_interval: '1d',
    adjust: 'qfq',
  });
  const [editor, setEditor] = useState({
    id: null,
    code: '',
    name: '',
    category: '',
    description: '',
    lifecycle_status: 'draft',
    source_type: 'custom',
    enabled: false,
    target_security_type: 'stock',
    bar_interval: '1d',
    adjust: 'qfq',
    allow_t0: false,
    code_body: '',
  });
  const [backtest, setBacktest] = useState(null);
  const [historyDetail, setHistoryDetail] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const mayWrite = canWrite(authz);
  const disabledReason = writeDisabledReason(authz);

  function loadStrategies() {
    setLoading(true);
    return api.strategies({ page: 1, page_size: 20 })
      .then((data) => {
        setItems(data.items || []);
        if (pagePayload.strategy_code && data.items?.some((item) => item.code === pagePayload.strategy_code)) {
          setSelectedCode(pagePayload.strategy_code);
        } else if (data.items?.[0]?.code) {
          setSelectedCode(data.items[0].code);
        }
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadStrategies();
  }, [pagePayload.strategy_code]);

  useEffect(() => {
    if (!pagePayload.strategy_code) return;
    setSelectedCode(pagePayload.strategy_code);
  }, [pagePayload.strategy_code]);

  useEffect(() => {
    if (!selectedCode) return;
    api.strategyBacktests(selectedCode, { page: 1, page_size: 5 })
      .then((data) => {
        setHistory(data.items || []);
        setHistoryDetail(null);
      })
      .catch(() => {
        setHistory([]);
        setHistoryDetail(null);
      });
  }, [selectedCode]);

  useEffect(() => {
    const item = items.find((candidate) => candidate.code === selectedCode) || items[0];
    if (!item) return;
    setEditor({
      id: item.id,
      code: item.code || '',
      name: item.name || '',
      category: item.category || '',
      description: item.description || '',
      lifecycle_status: item.lifecycle_status || (item.enabled ? 'deployed' : 'draft'),
      source_type: item.source_type || 'builtin',
      enabled: Boolean(item.enabled),
      target_security_type: item.target_security_type || item.config?.target_security_type || 'stock',
      bar_interval: item.bar_interval || item.config?.bar_interval || '1d',
      adjust: item.adjust || item.config?.adjust || 'qfq',
      allow_t0: Boolean(item.allow_t0 || item.config?.allow_t0),
      code_body: item.code_body || '',
    });
    setForm((prev) => ({
      ...prev,
      security_type: item.target_security_type || item.config?.target_security_type || prev.security_type || 'stock',
      bar_interval: item.bar_interval || item.config?.bar_interval || prev.bar_interval || '1d',
      adjust: item.adjust || item.config?.adjust || prev.adjust || 'qfq',
    }));
  }, [items, selectedCode]);

  function buildBacktestPayload(extra = {}) {
    return {
      start_date: form.start_date,
      end_date: form.end_date,
      holding_days: Number(form.holding_days),
      max_positions_per_day: Number(form.max_positions_per_day),
      trade_limit: Number(form.trade_limit),
      fee_bps: Number(form.fee_bps),
      slippage_bps: Number(form.slippage_bps),
      limit_up_down_guard: Boolean(form.limit_up_down_guard),
      benchmark_code: form.benchmark_code,
      benchmark_return_pct: Number(form.benchmark_return_pct),
      security_type: form.security_type,
      bar_interval: form.bar_interval,
      interval: form.bar_interval,
      adjust: form.adjust,
      include_trades: true,
      ...extra,
    };
  }

  async function runBacktest(event) {
    event.preventDefault();
    if (!mayWrite) {
      setError(disabledReason);
      return;
    }
    setError('');
    setMessage('');
    setRunning(true);
    try {
      const data = await api.strategyBacktest(selectedCode, buildBacktestPayload());
      setBacktest(data);
      setMessage('回测已完成，建议结合行情源质量、样本数量和成本假设复核结论。');
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  async function runParameterComparison() {
    if (!mayWrite) {
      setError(disabledReason);
      return;
    }
    setError('');
    setMessage('');
    setRunning(true);
    try {
      const baseHoldingDays = Number(form.holding_days);
      const data = await api.strategyBacktest(selectedCode, buildBacktestPayload({
        param_groups: [
          { label: '短持有', holding_days: Math.max(1, baseHoldingDays - 2), max_positions_per_day: Number(form.max_positions_per_day) },
          { label: '当前参数', holding_days: baseHoldingDays, max_positions_per_day: Number(form.max_positions_per_day) },
          { label: '长持有', holding_days: Math.min(60, baseHoldingDays + 5), max_positions_per_day: Number(form.max_positions_per_day) },
        ],
      }));
      setBacktest(data);
      setMessage('参数组对比已完成。');
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  async function viewBacktestDetail(item) {
    if (!item?.id) return;
    setError('');
    try {
      const data = await api.strategyBacktestDetail(selectedCode, item.id);
      setHistoryDetail(data);
    } catch (err) {
      setError(err.message);
    }
  }

  async function createDraftStrategy() {
    if (!mayWrite) {
      setError(disabledReason);
      return;
    }
    const suffix = Date.now().toString().slice(-5);
    try {
      setError('');
      const created = await api.createStrategy({
        code: `custom_${suffix}`,
        name: `自定义策略 ${suffix}`,
        category: '自定义策略',
        description: '新建策略草稿',
        config: { target_security_type: 'stock', bar_interval: '1d', adjust: 'qfq', allow_t0: false },
      });
      setSelectedCode(created.code);
      await loadStrategies();
      setMessage('策略草稿已创建。');
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveStrategy() {
    if (!mayWrite || !editor.id) {
      setError(!mayWrite ? disabledReason : '请先选择策略。');
      return;
    }
    try {
      setError('');
      const saved = await api.updateStrategy(editor.id, {
        code: editor.code,
        name: editor.name,
        category: editor.category,
        description: editor.description,
        lifecycle_status: editor.lifecycle_status,
        source_type: editor.source_type,
        enabled: editor.enabled,
        config: {
          target_security_type: editor.target_security_type,
          security_type: editor.target_security_type,
          bar_interval: editor.bar_interval,
          interval: editor.bar_interval,
          adjust: editor.adjust,
          allow_t0: editor.allow_t0,
        },
        code_body: editor.code_body,
      });
      setSelectedCode(saved.code);
      await loadStrategies();
      setMessage('策略已保存，代码变更会进入 draft 状态，部署前需要测试。');
    } catch (err) {
      setError(err.message);
    }
  }

  async function testSelectedStrategy() {
    if (!mayWrite || !editor.id) {
      setError(!mayWrite ? disabledReason : '请先选择策略。');
      return;
    }
    try {
      setError('');
      const tested = await api.testStrategy(editor.id, { code_body: editor.code_body, target_date: form.end_date, security_type: editor.target_security_type, bar_interval: editor.bar_interval, adjust: editor.adjust });
      await loadStrategies();
      setMessage(tested.result?.message || '策略测试完成。');
    } catch (err) {
      setError(err.message);
    }
  }

  async function deploySelectedStrategy() {
    if (!mayWrite || !editor.id) {
      setError(!mayWrite ? disabledReason : '请先选择策略。');
      return;
    }
    try {
      setError('');
      const deployed = await api.deployStrategy(editor.id);
      await loadStrategies();
      setMessage(`策略已部署：${deployed.deployment?.status || 'deployed'}`);
    } catch (err) {
      setError(err.message);
    }
  }

  async function runProductionStrategy() {
    if (!mayWrite || !editor.id) {
      setError(!mayWrite ? disabledReason : '请先选择策略。');
      return;
    }
    try {
      setError('');
      const result = await api.productionRunStrategy(editor.id, {
        params: {
          sample_size: Number(form.trade_limit) || 20,
          scan_limit: 6000,
          security_type: editor.target_security_type,
          bar_interval: editor.bar_interval,
          interval: editor.bar_interval,
          adjust: editor.adjust,
          allow_t0: editor.allow_t0,
          full_universe: true,
          local_only: true,
          trade_date: form.end_date,
        },
      });
      const taskId = result.task?.id ? result.task.id.slice(0, 8) : '-';
      setMessage(`生产运行已入队：${taskId}。触发前会检查本地实时快照，没有快照会被门禁拦截。`);
    } catch (err) {
      setError(err.message);
    }
  }

  const displayStrategies = useMemo(() => (
    items.some(isLimitUpReturnStrategy) ? items : [...items, LIMIT_UP_RETURN_STRATEGY]
  ), [items]);
  const selectedStrategy = useMemo(
    () => displayStrategies.find((item) => item.code === selectedCode) || displayStrategies[0],
    [displayStrategies, selectedCode],
  );
  const selectedIsLimitUpReturn = isLimitUpReturnStrategy(selectedStrategy);
  const summary = backtest?.summary || {};
  const explanation = backtest?.explanation || {};
  const trades = summary.trade_page?.items || [];
  const curve = summary.equity_curve || [];
  const benchmarkCurve = summary.benchmark?.curve || [];
  const portfolioCurve = summary.portfolio_curve?.length ? summary.portfolio_curve : curve.map((point, index) => {
    const benchmarkPoint = benchmarkCurve[index] || {};
    const returnPct = safeNumber(point.return_pct, 0);
    const benchmarkReturnPct = safeNumber(benchmarkPoint.return_pct, null);
    return {
      step: point.step ?? index,
      return_pct: returnPct,
      benchmark_return_pct: benchmarkReturnPct,
      excess_return_pct: benchmarkReturnPct == null ? null : returnPct - benchmarkReturnPct,
    };
  });
  const drawdownSeries = summary.drawdown_curve?.length ? summary.drawdown_curve : buildDrawdownSeries(curve);
  const returnBounds = chartBounds(portfolioCurve.flatMap((point) => [
    safeNumber(point.return_pct, null),
    safeNumber(point.benchmark_return_pct, null),
    safeNumber(point.excess_return_pct, null),
  ]).filter((value) => value != null));
  const drawdownBounds = chartBounds(drawdownSeries.map((point) => drawdownValue(point)).filter((value) => value != null));
  const equityLine = linePoints(portfolioCurve, (point) => point.return_pct, returnBounds.min, returnBounds.max);
  const benchmarkLine = linePoints(portfolioCurve, (point) => point.benchmark_return_pct, returnBounds.min, returnBounds.max);
  const excessLine = linePoints(portfolioCurve, (point) => point.excess_return_pct, returnBounds.min, returnBounds.max);
  const drawdownLine = linePoints(drawdownSeries, (point) => drawdownValue(point), drawdownBounds.min, drawdownBounds.max);
  const returnDistribution = summary.return_distribution || {};
  const distributionBars = [
    { label: '盈利笔数', count: Number(returnDistribution.win_count || 0), className: 'up' },
    { label: '亏损/持平', count: Number(returnDistribution.flat_or_loss_count ?? returnDistribution.loss_count ?? 0), className: 'down' },
  ];
  const tradeBuckets = buildTradeBuckets(trades);
  const maxDistributionCount = Math.max(1, ...distributionBars.map((item) => item.count), ...tradeBuckets.map((item) => item.count));
  const parameterComparison = backtest?.parameter_comparison || [];
  const executionConstraints = summary.execution_constraints || {};
  const sampleRisk = Number(summary.total_trades || 0) < 20;
  const dataContract = summary.data_contract || {};
  const dataRisk = Boolean(dataContract.mock_or_fallback || summary.benchmark?.fallback_used || summary.benchmark?.data_quality === 'mock');
  const summarySignalAttributionItems = normalizeSignalAttribution(summary.signal_attribution);
  const explanationSignalAttributionItems = normalizeSignalAttribution(explanation.signal_attribution);
  const signalAttributionItems = summarySignalAttributionItems.length ? summarySignalAttributionItems : explanationSignalAttributionItems;
  const maxSignalPhaseCount = Math.max(1, ...signalAttributionItems.flatMap((item) => item.volumePhases.map((phase) => phase.count)));

  return (
    <main className="page">
      <PageHeader
        eyebrow="Strategy"
        title="策略管理"
        description="策略页不只列清单，还要能直接运行回测、查看风险解释，并把验证结果带回日常扫描。"
        badges={selectedStrategy ? (
          <>
            <StatusBadge tone={selectedStrategy.enabled ? 'success' : 'warning'}>{selectedStrategy.enabled ? '已启用' : '未启用'}</StatusBadge>
            <StatusBadge tone="info">{selectedStrategy.code}</StatusBadge>
          </>
        ) : null}
      />

      <RiskDisclaimer />

      {error ? <div className="alert">{error}</div> : null}
      {message ? <div className="alert success">{message}</div> : null}
      {!mayWrite ? <div className="alert warning">{disabledReason}</div> : null}
      {loading ? <div className="card loading-card">正在加载策略...</div> : null}

      <section className="strategy-grid">
        {displayStrategies.map((item) => (
          <button
            type="button"
            className={item.code === selectedCode ? 'strategy-card active' : 'strategy-card'}
            key={item.code}
            onClick={() => setSelectedCode(item.code)}
          >
            <div className="section-title-row">
              <strong>{item.name}</strong>
              <StatusBadge tone={item.enabled ? 'success' : 'warning'}>{item.enabled ? '启用' : '停用'}</StatusBadge>
            </div>
            <span>{item.code}</span>
            <span className="muted">{SECURITY_TYPE_LABELS[item.target_security_type || item.config?.target_security_type] || '股票'} / {BAR_INTERVAL_LABELS[item.bar_interval || item.config?.bar_interval] || '日线'}</span>
            <p className="muted">{item.description || item.category}</p>
          </button>
        ))}
      </section>

      {selectedIsLimitUpReturn ? (
        <SectionCard
          title="涨停回马枪 / LIMIT_UP_RETURN"
          subtitle="前端最小落地：展示策略关键说明，具体信号、价格线和状态均以后端返回字段为准。"
          className="section-gap"
        >
          <div className="limit-up-note-grid">
            {LIMIT_UP_RETURN_NOTES.map(([label, text]) => (
              <div className="limit-up-note" key={label}>
                <strong>{label}</strong>
                <span>{text}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      ) : null}

      <section className="dashboard-layout section-gap">
        <article className="panel-card">
          <div className="section-title-row">
            <h2>策略生命周期</h2>
            <button type="button" className="btn-secondary" onClick={createDraftStrategy} disabled={!mayWrite} title={disabledReason}>新增策略</button>
          </div>
          <div className="backtest-form">
            <label className="form-field">
              策略代码
              <input className="scan-input" value={editor.code} onChange={(event) => setEditor((prev) => ({ ...prev, code: event.target.value }))} />
            </label>
            <label className="form-field">
              策略名称
              <input className="scan-input" value={editor.name} onChange={(event) => setEditor((prev) => ({ ...prev, name: event.target.value }))} />
            </label>
            <label className="form-field">
              分类
              <input className="scan-input" value={editor.category} onChange={(event) => setEditor((prev) => ({ ...prev, category: event.target.value }))} />
            </label>
            <label className="form-field">
              运行标的
              <select className="scan-select" value={editor.target_security_type} onChange={(event) => setEditor((prev) => ({ ...prev, target_security_type: event.target.value, allow_t0: event.target.value === 'convertible_bond' ? true : prev.allow_t0 }))}>
                {SECURITY_TYPE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="form-field">
              K线级别
              <select className="scan-select" value={editor.bar_interval} onChange={(event) => {
                const barInterval = event.target.value;
                setEditor((prev) => ({ ...prev, bar_interval: barInterval, adjust: barInterval === '1d' ? prev.adjust : 'none' }));
              }}>
                {BAR_INTERVAL_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="form-field">
              复权
              <select className="scan-select" value={editor.adjust} disabled={editor.bar_interval !== '1d'} onChange={(event) => setEditor((prev) => ({ ...prev, adjust: event.target.value }))}>
                <option value="qfq">前复权</option>
                <option value="hfq">后复权</option>
                <option value="none">不复权</option>
              </select>
            </label>
            <label className="form-field">
              阶段
              <select className="scan-select" value={editor.lifecycle_status} onChange={(event) => setEditor((prev) => ({ ...prev, lifecycle_status: event.target.value }))}>
                <option value="draft">draft</option>
                <option value="tested">tested</option>
                <option value="deployed">deployed</option>
                <option value="disabled">disabled</option>
              </select>
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={editor.enabled} onChange={(event) => setEditor((prev) => ({ ...prev, enabled: event.target.checked }))} />
              启用策略
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={editor.allow_t0} onChange={(event) => setEditor((prev) => ({ ...prev, allow_t0: event.target.checked }))} />
              T+0 策略
            </label>
          </div>
          <label className="form-field section-gap">
            描述
            <textarea className="scan-input" rows="3" value={editor.description} onChange={(event) => setEditor((prev) => ({ ...prev, description: event.target.value }))} />
          </label>
          <div className="toolbar section-gap">
            <button type="button" onClick={saveStrategy} disabled={!mayWrite || !editor.id} title={disabledReason}>保存策略</button>
            <button type="button" className="btn-secondary" onClick={testSelectedStrategy} disabled={!mayWrite || !editor.id} title={disabledReason}>测试策略</button>
            <button type="button" className="btn-secondary" onClick={deploySelectedStrategy} disabled={!mayWrite || !editor.id} title={disabledReason}>部署生产</button>
            <button type="button" className="btn-secondary" onClick={runProductionStrategy} disabled={!mayWrite || !editor.id || editor.lifecycle_status !== 'deployed'} title={editor.lifecycle_status !== 'deployed' ? '策略部署后才能生产运行' : disabledReason}>生产运行</button>
          </div>
        </article>

        <article className="panel-card">
          <div className="section-title-row">
            <h2>策略代码编辑</h2>
            <StatusBadge tone={selectedStrategy?.runtime_registered ? 'success' : 'warning'}>{selectedStrategy?.runtime_registered ? 'runtime registered' : 'stored only'}</StatusBadge>
          </div>
          <textarea
            className="scan-input code-editor"
            rows="18"
            value={editor.code_body}
            spellCheck="false"
            onChange={(event) => setEditor((prev) => ({ ...prev, code_body: event.target.value }))}
          />
          <div className="scan-summary section-gap">
            <div className="summary-row"><span>版本</span><strong>{selectedStrategy?.version || '-'}</strong></div>
            <div className="summary-row"><span>最近测试</span><strong>{selectedStrategy?.last_test_status || '-'}</strong></div>
            <div className="summary-row"><span>部署时间</span><strong>{selectedStrategy?.deployed_at || '-'}</strong></div>
          </div>
        </article>
      </section>

      <section className="dashboard-layout section-gap">
        <article className="panel-card">
          <h2>运行回测</h2>
          <form className="backtest-form" onSubmit={runBacktest}>
            <label className="form-field">
              策略
              <select className="scan-select" value={selectedCode} onChange={(event) => setSelectedCode(event.target.value)}>
                {displayStrategies.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}
              </select>
            </label>
            <label className="form-field">
              标的类型
              <select className="scan-select" value={form.security_type} onChange={(event) => setForm((prev) => ({ ...prev, security_type: event.target.value }))}>
                {SECURITY_TYPE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="form-field">
              K线级别
              <select className="scan-select" value={form.bar_interval} onChange={(event) => {
                const barInterval = event.target.value;
                setForm((prev) => ({ ...prev, bar_interval: barInterval, adjust: barInterval === '1d' ? prev.adjust : 'none' }));
              }}>
                {BAR_INTERVAL_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="form-field">
              复权
              <select className="scan-select" value={form.adjust} disabled={form.bar_interval !== '1d'} onChange={(event) => setForm((prev) => ({ ...prev, adjust: event.target.value }))}>
                <option value="qfq">前复权</option>
                <option value="hfq">后复权</option>
                <option value="none">不复权</option>
              </select>
            </label>
            <label className="form-field">
              开始日期
              <input className="scan-input" type="date" value={form.start_date} onChange={(event) => setForm((prev) => ({ ...prev, start_date: event.target.value }))} />
            </label>
            <label className="form-field">
              结束日期
              <input className="scan-input" type="date" value={form.end_date} onChange={(event) => setForm((prev) => ({ ...prev, end_date: event.target.value }))} />
            </label>
            <label className="form-field">
              持有天数
              <input className="scan-input" type="number" min="1" max="60" value={form.holding_days} onChange={(event) => setForm((prev) => ({ ...prev, holding_days: event.target.value }))} />
            </label>
            <label className="form-field">
              每日最大持仓
              <input className="scan-input" type="number" min="1" max="20" value={form.max_positions_per_day} onChange={(event) => setForm((prev) => ({ ...prev, max_positions_per_day: event.target.value }))} />
            </label>
            <label className="form-field">
              交易明细上限
              <input className="scan-input" type="number" min="1" max="500" value={form.trade_limit} onChange={(event) => setForm((prev) => ({ ...prev, trade_limit: event.target.value }))} />
            </label>
            <label className="form-field">
              手续费 bps
              <input className="scan-input" type="number" min="0" max="200" step="0.1" value={form.fee_bps} onChange={(event) => setForm((prev) => ({ ...prev, fee_bps: event.target.value }))} />
            </label>
            <label className="form-field">
              滑点 bps
              <input className="scan-input" type="number" min="0" max="500" step="0.1" value={form.slippage_bps} onChange={(event) => setForm((prev) => ({ ...prev, slippage_bps: event.target.value }))} />
            </label>
            <label className="form-field">
              基准代码
              <input className="scan-input" value={form.benchmark_code} onChange={(event) => setForm((prev) => ({ ...prev, benchmark_code: event.target.value }))} />
            </label>
            <label className="form-field">
              基准收益
              <input className="scan-input" type="number" min="-1" max="1" step="0.01" value={form.benchmark_return_pct} onChange={(event) => setForm((prev) => ({ ...prev, benchmark_return_pct: event.target.value }))} />
            </label>
            <label className="checkbox-field">
              <input type="checkbox" checked={form.limit_up_down_guard} onChange={(event) => setForm((prev) => ({ ...prev, limit_up_down_guard: event.target.checked }))} />
              涨跌停约束提示
            </label>
            <button type="submit" disabled={running || !selectedCode || !mayWrite} title={disabledReason}>{running ? '回测中...' : '运行回测'}</button>
            <button type="button" className="btn-secondary" onClick={runParameterComparison} disabled={running || !selectedCode || !mayWrite} title={disabledReason}>参数组对比</button>
          </form>
        </article>

        <article className="panel-card">
          <h2>解释结论</h2>
          {backtest ? (
            <div className="scan-summary">
              <div className="summary-row"><span>结论</span><StatusBadge status={explanation.verdict}>{explanation.verdict}</StatusBadge></div>
              <div className="summary-row"><span>风险等级</span><StatusBadge status={summary.risk_level}>{summary.risk_level}</StatusBadge></div>
              <div className="summary-row"><span>解释分</span><strong>{explanation.score ?? '-'}</strong></div>
              <div className="summary-row"><span>置信度</span><strong>{explanation.confidence ?? '-'}</strong></div>
              <div className="summary-row"><span>行动建议</span><strong>{explanation.action_suggestion || '-'}</strong></div>
            </div>
          ) : (
            <div className="empty">选择日期区间后运行一次回测，系统会返回收益、回撤、胜率和解释建议。</div>
          )}
        </article>
      </section>

      {backtest ? (
        <>
          <div className="alert warning">
            回测仅用于策略研究，不构成投资建议。当前样本量 {summary.total_trades ?? 0} 笔，费用 {form.fee_bps} bps，滑点 {form.slippage_bps} bps，基准 {form.benchmark_code || '-'}。
            {sampleRisk ? ' 样本量偏小，置信度需要下调。' : ''}
            {dataRisk ? ' 本次结果包含 mock/fallback 或合成基准口径，需复核真实行情源。' : ''}
          </div>
          <section className="grid section-gap">
            <MetricCard label="交易次数" value={summary.total_trades} hint="样本量越小，置信度越低" />
            <MetricCard
              label="约束剔除"
              value={executionConstraints.excluded_count ?? 0}
              hint={executionConstraints.enabled ? '已启用涨跌停/停牌约束' : '仅剔除显式无效价格'}
              danger={Number(executionConstraints.excluded_count || 0) > 0}
            />
            <MetricCard label="胜率" value={percent(summary.win_rate)} />
            <MetricCard label="累计收益" value={percent(summary.total_return)} />
            <MetricCard label="估算净收益" value={percent(summary.net_total_return)} />
            <MetricCard label="基准收益" value={percent(summary.benchmark?.total_return)} />
            <MetricCard
              label="基准数据"
              value={benchmarkQualityLabel(summary.benchmark)}
              danger={summary.benchmark?.fallback_used || summary.benchmark?.data_quality === 'mock'}
            />
            <MetricCard label="超额收益" value={percent(summary.benchmark?.excess_return)} danger={Number(summary.benchmark?.excess_return || 0) < 0} />
            <MetricCard label="最大回撤" value={percent(summary.max_drawdown)} danger={Number(summary.max_drawdown) >= 0.12} />
            <MetricCard label="夏普比率" value={summary.sharpe_ratio ?? '-'} />
            <MetricCard label="盈亏比" value={summary.profit_factor ?? '-'} />
          </section>

          {parameterComparison.length ? (
            <SectionCard title="参数组对比">
              <DataTable
                className="backtest-history-table"
                columns={[
                  { label: '参数组', render: (item) => <strong>{item.label}</strong> },
                  { label: '持有', render: (item) => item.params?.holding_days ?? '-' },
                  { label: '胜率', render: (item) => percent(item.summary?.win_rate) },
                  { label: '净收益', render: (item) => percent(item.summary?.net_total_return) },
                  { label: '超额', render: (item) => percent(item.summary?.excess_return) },
                ]}
                rows={parameterComparison}
                getKey={(item) => item.label}
                emptyText="暂无参数组对比。"
              />
            </SectionCard>
          ) : null}

          <SectionCard title="25/60 信号归因" subtitle="按信号子类型聚合交易表现，并展示对应量能阶段分布。">
            <DataTable
              className="signal-attribution-table"
              columns={[
                {
                  label: '信号阶段/子类型',
                  render: (item) => (
                    <span className="attribution-signal-cell">
                      <strong>{labelFromMap(item.primaryPhase, VOLUME_PHASE_LABELS, '未知阶段')}</strong>
                      <small>
                        {labelFromMap(item.signalSubtype, SIGNAL_SUBTYPE_LABELS, '未知信号')}
                        <span className="muted"> / {item.signalSubtype}</span>
                      </small>
                    </span>
                  ),
                },
                { label: '交易数', render: (item) => item.tradeCount },
                { label: '胜率', render: (item) => percent(item.winRate) },
                { label: '平均收益', render: (item) => percent(item.avgReturn) },
                { label: '最大回撤', render: (item) => percent(item.maxDrawdown) },
                {
                  label: '量能阶段分布',
                  render: (item) => (
                    item.volumePhases.length ? (
                      <span className="phase-chip-list">
                        {item.volumePhases.map((phase) => (
                          <span className="phase-chip" key={phase.phase}>
                            <span>{labelFromMap(phase.phase, VOLUME_PHASE_LABELS, '未知阶段')}</span>
                            <strong>{phase.count} 笔</strong>
                            <i style={{ width: `${(phase.count / maxSignalPhaseCount) * 100}%` }} />
                          </span>
                        ))}
                      </span>
                    ) : <span className="muted">暂无阶段分布</span>
                  ),
                },
              ]}
              rows={signalAttributionItems}
              getKey={(item) => `${item.primaryPhase}-${item.signalSubtype}`}
              emptyText="本次回测未返回 25/60 信号归因。"
            />
          </SectionCard>

          <SectionCard title="收益 / 回撤曲线" subtitle="策略、基准、超额和 drawdown 使用同一回测样本序列，图例颜色固定。">
            <div className="chart-legend professional-legend">
              <span><i className="legend-line equity" /> 策略收益</span>
              <span><i className="legend-line benchmark" /> 基准收益</span>
              <span><i className="legend-line excess" /> 超额收益</span>
              <span><i className="legend-line drawdown" /> Drawdown</span>
            </div>
            <div className="backtest-chart-stack">
              <div className="backtest-chart-panel" role="img" aria-label="策略收益、基准收益和超额收益曲线">
                <div className="chart-axis-labels" aria-hidden="true">
                  <span>{percent(returnBounds.max)}</span>
                  <span>{percent(returnBounds.min)}</span>
                </div>
                <svg className="backtest-line-chart" viewBox="0 0 100 100" preserveAspectRatio="none">
                  {equityLine ? <polyline points={equityLine} className="backtest-line equity" /> : null}
                  {benchmarkLine ? <polyline points={benchmarkLine} className="backtest-line benchmark" /> : null}
                  {excessLine ? <polyline points={excessLine} className="backtest-line excess" /> : null}
                </svg>
                {!portfolioCurve.length ? <div className="empty chart-empty">本次回测未返回收益曲线。</div> : null}
              </div>
              <div className="backtest-chart-panel drawdown-panel" role="img" aria-label="回测 drawdown 曲线">
                <div className="chart-axis-labels" aria-hidden="true">
                  <span>{percent(drawdownBounds.max)}</span>
                  <span>{percent(drawdownBounds.min)}</span>
                </div>
                <svg className="backtest-line-chart" viewBox="0 0 100 100" preserveAspectRatio="none">
                  {drawdownLine ? <polyline points={drawdownLine} className="backtest-line drawdown" /> : null}
                </svg>
                {!drawdownSeries.length ? <div className="empty chart-empty">本次回测未返回 drawdown 数据。</div> : null}
              </div>
            </div>
          </SectionCard>

          <SectionCard title="交易分布">
            <div className="distribution-grid">
              {distributionBars.map((item) => (
                <div className="distribution-item" key={item.label}>
                  <div className="section-title-row">
                    <strong>{item.label}</strong>
                    <span>{item.count} 笔</span>
                  </div>
                  <span className={`distribution-bar ${item.className}`} style={{ width: `${(item.count / maxDistributionCount) * 100}%` }} />
                </div>
              ))}
              <div className="distribution-item">
                <div className="section-title-row">
                  <strong>盈利合计</strong>
                  <span>{percent(returnDistribution.positive_return_sum)}</span>
                </div>
                <span className="distribution-bar up" style={{ width: `${Math.min(100, Math.abs(Number(returnDistribution.positive_return_sum || 0)) * 100)}%` }} />
              </div>
              <div className="distribution-item">
                <div className="section-title-row">
                  <strong>亏损合计</strong>
                  <span>{percent(returnDistribution.negative_return_sum)}</span>
                </div>
                <span className="distribution-bar down" style={{ width: `${Math.min(100, Math.abs(Number(returnDistribution.negative_return_sum || 0)) * 100)}%` }} />
              </div>
            </div>
            <div className="trade-bucket-grid section-gap">
              {tradeBuckets.map((bucket) => (
                <div className="trade-bucket" key={bucket.label}>
                  <span>{bucket.label}</span>
                  <strong>{bucket.count}</strong>
                  <span className="bucket-track"><i style={{ width: `${(bucket.count / maxDistributionCount) * 100}%` }} /></span>
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="交易样本">
            <DataTable
              className="backtest-table"
              columns={[
                { label: '股票', render: (trade) => <strong>{trade.code} {trade.name}</strong> },
                { label: '信号', render: (trade) => trade.signal || '-' },
                { label: '入场', render: (trade) => trade.entry_date || '-' },
                { label: '出场', render: (trade) => trade.exit_date || '-' },
                { label: '收益', render: (trade) => percent(trade.return_pct) },
                { label: '风险分', render: (trade) => trade.risk_score ?? '-' },
              ]}
              rows={trades}
              getKey={(trade, index) => `${trade.code}-${index}`}
              emptyText="本次回测未返回交易明细。"
            />
          </SectionCard>
        </>
      ) : null}

      <SectionCard title="历史回测">
        <DataTable
          className="backtest-history-table"
          columns={[
            { label: '区间', render: (item) => `${item.start_date || '-'} 至 ${item.end_date || '-'}` },
            { label: '交易', render: (item) => item.summary?.total_trades ?? item.total_trades ?? '-' },
            { label: '胜率', render: (item) => percent(item.summary?.win_rate ?? item.win_rate) },
            { label: '收益', render: (item) => percent(item.summary?.total_return ?? item.total_return) },
            { label: '回撤', render: (item) => percent(item.summary?.max_drawdown ?? item.max_drawdown) },
            { label: '详情', render: (item) => <button type="button" className="btn-secondary" onClick={() => viewBacktestDetail(item)}>查看</button> },
          ]}
          rows={history}
          getKey={(item, index) => item.id || index}
          emptyText="暂无历史回测记录。"
        />
      </SectionCard>

      {historyDetail ? (
        <SectionCard title="历史回测详情">
          <div className="scan-summary">
            <div className="summary-row"><span>区间</span><strong>{historyDetail.item?.start_date || '-'} 至 {historyDetail.item?.end_date || '-'}</strong></div>
            <div className="summary-row"><span>交易次数</span><strong>{historyDetail.item?.summary?.total_trades ?? '-'}</strong></div>
            <div className="summary-row"><span>胜率</span><strong>{percent(historyDetail.item?.summary?.win_rate)}</strong></div>
            <div className="summary-row"><span>收益</span><strong>{percent(historyDetail.item?.summary?.total_return)}</strong></div>
            <div className="summary-row"><span>风险等级</span><StatusBadge status={historyDetail.item?.explanation?.risk_level}>{historyDetail.item?.explanation?.risk_level || '-'}</StatusBadge></div>
            <div className="summary-row"><span>审计记录</span><strong>{historyDetail.audit_trail?.length || 0}</strong></div>
          </div>
        </SectionCard>
      ) : null}
    </main>
  );
}
