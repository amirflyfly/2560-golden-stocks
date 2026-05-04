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

function percent(value) {
  if (value == null || value === '') return '-';
  return `${Number(value).toFixed(2)}%`;
}

function dataQualityLabel(item) {
  const quality = item?.data_quality || 'unknown';
  const source = item?.market_data_source || '-';
  return item?.fallback_used ? `${quality} / ${source} / fallback` : `${quality} / ${source}`;
}

export function PicksPage({ authz, pagePayload = {} }) {
  const [items, setItems] = useState([]);
  const [selectedPick, setSelectedPick] = useState(null);
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

  async function loadPicks() {
    setLoading(true);
    try {
      const query = { page: 1, page_size: 50 };
      Object.entries(filters).forEach(([key, value]) => {
        if (value && value !== 'all') query[key] = value;
      });
      const data = await api.picks(query);
      setItems(data.items || []);
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

  const metrics = useMemo(() => {
    const watching = items.filter((item) => item.watch_flag || item.status === 'watching').length;
    const reviewed = items.filter((item) => ['validated', 'rejected'].includes(String(item.status || ''))).length;
    const highRisk = items.filter((item) => String(item.risk_level || '').toLowerCase() === 'high').length;
    const wins = items.filter((item) => Number(item.return_pct) > 0).length;
    return { watching, reviewed, highRisk, wins };
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

      <section className="dashboard-layout section-gap">
        <SectionCard title="候选列表">
          {loading ? <div className="card loading-card">正在加载候选...</div> : null}
          <DataTable
            className="picks-table"
            columns={[
              { label: '股票', render: (item) => <strong>{item.symbol} {item.stock_name}</strong> },
              { label: '策略', render: (item) => item.strategy_code || '-' },
              { label: '来源', render: (item) => item.source || '-' },
              { label: 'Data', render: (item) => <StatusBadge status={item.data_quality}>{dataQualityLabel(item)}</StatusBadge> },
              { label: '状态', render: (item) => <StatusBadge status={item.status}>{item.status || 'accepted'}</StatusBadge> },
              { label: '风险', render: (item) => <StatusBadge status={item.risk_level}>{item.risk_level || 'pending'}</StatusBadge> },
              {
                label: '操作',
                render: (item) => (
                  <div className="row-actions">
                    <button type="button" className="btn-secondary" onClick={() => fillReviewForm(item)}>复盘</button>
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
