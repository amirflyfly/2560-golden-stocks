import { useEffect, useMemo, useState } from 'react';
import { api, getTenantId } from '../api/client';
import { canWrite, writeDisabledReason } from '../auth/permissions';
import { DataTable, PageHeader, SectionCard, StatusBadge } from '../components/common';

const POLL_STATUSES = new Set(['pending', 'running', 'retrying', 'queued']);

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

function isPollingStatus(status) {
  return POLL_STATUSES.has(String(status || '').toLowerCase());
}

export function ScansPage({ onNavigate, authz, pagePayload = {} }) {
  const [form, setForm] = useState({ strategy_code: pagePayload.strategy_code || '2560', sample_size: 'default' });
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
  const mayWrite = canWrite(authz);
  const disabledReason = writeDisabledReason(authz);

  async function loadRecentScans() {
    const data = await api.scans({ page: 1, page_size: 5 });
    setRecentScans(data.items || []);
  }

  useEffect(() => {
    loadRecentScans().catch((err) => setError(err.message));
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
      const params = form.sample_size === 'default' ? {} : { sample_size: Number(form.sample_size) };
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

  const taskId = getTaskId(task);
  const provider = getProvider(task);
  const quality = getQuality(task);
  const taskExplanation = getExplanation(task);
  const resultItems = results?.items || task?.result?.market_data?.sample_symbols || [];
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
                <option value="default">默认股票池</option>
                <option value="30">前 30 只样本</option>
                <option value="100">前 100 只样本</option>
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
              <div className="summary-row"><span>行情源</span><strong>{provider}</strong></div>
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
        <DataTable
          className="scan-result-table"
          columns={[
            { label: '股票', render: (item) => <strong>{stockCode(item)} {stockName(item)}</strong> },
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
                  <button type="button" className="btn-secondary" onClick={() => onNavigate?.('kline', { symbol: stockCode(item) })}>K 线</button>
                </div>
              ),
            },
          ]}
          rows={resultItems}
          getKey={(item, index) => `${stockCode(item)}-${index}`}
          emptyText="暂无扫描结果。任务完成后系统会自动刷新，也可以手动点击刷新。"
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
