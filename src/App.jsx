import React, { useEffect, useMemo, useState } from 'react';
import { KLineChart } from 'kline-charts-react';
import 'kline-charts-react/style.css';

function App() {
  const getStockCodeFromUrl = () => {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('code') || '600519';
  };

  const normalizeCode = (code) => (code || '').trim().replace(/^(sh|sz|bj)/i, '').toUpperCase();

  const toLibrarySymbol = (code) => {
    const normalizedCode = normalizeCode(code);
    if (!normalizedCode) {
      return 'sh600519';
    }
    if (/^(600|601|603|605|688|689|900)/.test(normalizedCode)) {
      return `sh${normalizedCode}`;
    }
    if (/^(000|001|002|003|200|300|301)/.test(normalizedCode)) {
      return `sz${normalizedCode}`;
    }
    if (/^(430|830|831|832|833|835|836|837|838|839|870|871|872|873|874|875|876|877|878|879|880|881|882|883|884|885|886|887|888|889)/.test(normalizedCode)) {
      return `bj${normalizedCode}`;
    }
    return `sz${normalizedCode}`;
  };

  const getDateRangeByPeriod = (period) => {
    const now = new Date();
    const endDate = now.toISOString().split('T')[0];
    let startDate = endDate;

    switch (period) {
      case 'timeline':
      case '1':
      case '5':
      case '15':
      case '30':
      case '60':
        startDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
        break;
      case 'weekly':
        startDate = new Date(now.getTime() - 365 * 2 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
        break;
      case 'monthly':
        startDate = new Date(now.getTime() - 365 * 5 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
        break;
      case 'daily':
      default:
        startDate = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
        break;
    }

    return { startDate, endDate };
  };

  const [stockCode, setStockCode] = useState(normalizeCode(getStockCodeFromUrl()));
  const [inputCode, setInputCode] = useState(normalizeCode(getStockCodeFromUrl()));
  const [chartType, setChartType] = useState('daily');
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    const handlePopState = () => {
      const nextCode = normalizeCode(getStockCodeFromUrl());
      setStockCode(nextCode);
      setInputCode(nextCode);
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const periodOptions = [
    { value: 'daily', label: '日K' },
    { value: 'weekly', label: '周K' },
    { value: 'monthly', label: '月K' }
  ];

  const chartTypeOptions = [
    { value: 'daily', label: 'K线图' },
    { value: 'timeline', label: '分时图' }
  ];

  const dataProvider = useMemo(() => ({
    getKline: async (params, signal) => {
      const code = normalizeCode(params.symbol || '');
      const pureCode = code.replace(/^(SH|SZ|BJ)/, '');
      const period = params.period || 'daily';
      const { startDate, endDate } = getDateRangeByPeriod(period);
      const response = await fetch(
        `/api/stock-data?code=${encodeURIComponent(pureCode)}&start_date=${startDate}&end_date=${endDate}`,
        { signal }
      );
      const result = await response.json();

      if (!response.ok || !result.success || !Array.isArray(result.data)) {
        throw new Error(result.message || '数据加载失败');
      }

      return result.data.map((item) => ({
        date: item.time,
        open: Number(item.open),
        close: Number(item.close),
        high: Number(item.high),
        low: Number(item.low),
        volume: Number(item.volume),
        amount: null,
        changePercent: null,
        change: null,
        amplitude: null,
        turnoverRate: null,
      }));
    },
    getTimeline: async (params, signal) => {
      const code = normalizeCode(params.symbol || '');
      const pureCode = code.replace(/^(SH|SZ|BJ)/, '');
      const { startDate, endDate } = getDateRangeByPeriod('timeline');
      const response = await fetch(
        `/api/stock-data?code=${encodeURIComponent(pureCode)}&start_date=${startDate}&end_date=${endDate}`,
        { signal }
      );
      const result = await response.json();

      if (!response.ok || !result.success || !Array.isArray(result.data)) {
        throw new Error(result.message || '分时数据加载失败');
      }

      return result.data.map((item) => ({
        time: `${item.time} 15:00`,
        price: Number(item.close),
        volume: Number(item.volume),
        amount: 0,
        avgPrice: Number(item.close),
      }));
    }
  }), []);

  const librarySymbol = useMemo(() => toLibrarySymbol(stockCode), [stockCode]);

  const applyCodeFromInput = () => {
    const nextCode = normalizeCode(inputCode);
    if (!nextCode) {
      setErrorMessage('请输入股票代码');
      return;
    }
    setErrorMessage('');
    setStockCode(nextCode);
    const url = new URL(window.location.href);
    url.searchParams.set('code', nextCode);
    window.history.replaceState({}, '', url.toString());
  };

  return (
    <div style={{ padding: '20px' }}>
      <h1 style={{ textAlign: 'center' }}>股票K线图表</h1>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <label htmlFor="stock-code-input">股票代码:</label>
          <input
            id="stock-code-input"
            type="text"
            value={inputCode}
            onChange={(e) => setInputCode(normalizeCode(e.target.value))}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                applyCodeFromInput();
              }
            }}
            placeholder="请输入股票代码，如 002594"
            style={{ padding: '8px 12px', border: '1px solid #ced4da', borderRadius: '4px', minWidth: '220px' }}
          />
          <button
            onClick={applyCodeFromInput}
            style={{ padding: '8px 14px', border: '1px solid #007bff', background: '#007bff', color: '#fff', borderRadius: '4px', cursor: 'pointer' }}
          >
            查看
          </button>
          <span style={{ color: '#666', fontSize: '14px' }}>当前代码：{stockCode || '-'}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <label htmlFor="chart-type">图表类型:</label>
          <select
            id="chart-type"
            value={chartType}
            onChange={(e) => setChartType(e.target.value)}
            style={{ padding: '8px 12px', border: '1px solid #ced4da', borderRadius: '4px' }}
          >
            {chartTypeOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>

        {chartType === 'daily' ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <label htmlFor="period-select">周期:</label>
            <select
              id="period-select"
              value={chartType}
              disabled
              style={{ padding: '8px 12px', border: '1px solid #ced4da', borderRadius: '4px', backgroundColor: '#f8f9fa' }}
            >
              {periodOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
        ) : null}
      </div>

      {errorMessage ? (
        <div style={{ marginBottom: '12px', color: '#dc3545', fontSize: '14px' }}>{errorMessage}</div>
      ) : null}

      <div style={{ width: '100%', minHeight: '700px', border: '1px solid #e0e0e0', borderRadius: '8px', overflow: 'hidden', background: '#fff' }}>
        <KLineChart
          key={`${librarySymbol}-${chartType}`}
          symbol={librarySymbol}
          market="A"
          period={chartType === 'timeline' ? 'timeline' : 'daily'}
          adjust="qfq"
          height={700}
          theme="light"
          indicators={['ma', 'volume', 'macd', 'kdj', 'rsi']}
          indicatorOptions={{
            ma: { periods: [5, 10, 20, 30] }
          }}
          showToolbar={true}
          showPeriodSelector={true}
          showIndicatorSelector={true}
          visibleCount={120}
          dataProvider={dataProvider}
          onError={(error) => {
            setErrorMessage(error?.message || '图表加载失败');
          }}
          onDataLoad={() => {
            setErrorMessage('');
          }}
          style={{ width: '100%', height: '700px' }}
        />
      </div>
    </div>
  );
}

export default App;
