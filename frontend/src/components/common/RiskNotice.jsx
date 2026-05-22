import { DataQualityGateBadge } from './DataQualityGateBadge';
import { RiskDisclaimer } from './RiskDisclaimer';

const CONTEXT_TITLES = {
  dashboard: '今日投研风险提示',
  scan: '扫描结果风险提示',
  backtest: '回测验证风险提示',
  report: '报表使用风险提示',
  paper: '模拟验证风险提示',
  kline: '行情图表风险提示',
};

function gateWarnings(gate = {}) {
  const warnings = Array.isArray(gate.warnings) ? gate.warnings : [];
  const normalized = warnings.map((item) => String(item));
  if (gate.fallback_used && !normalized.includes('fallback_used')) normalized.push('fallback_used');
  const grade = String(gate.grade || gate.data_quality || '').toLowerCase();
  if (['fallback', 'unknown', 'mock'].includes(grade) && !normalized.includes(grade)) normalized.push(grade);
  return normalized;
}

function warningText(warning) {
  const labels = {
    mock: '当前含 mock 模拟数据，生产主流程应阻断。',
    mock_market_data: '当前含 mock 模拟数据，生产主流程应阻断。',
    fallback: '当前使用备用或降级数据，结论需人工复核。',
    fallback_used: '行情源发生 fallback，关键动作需谨慎或二次确认。',
    unknown: '数据质量未知，不能静默视为正常数据。',
    degraded_market_data: '行情数据降级，建议复核来源、覆盖率和时效。',
  };
  return labels[warning] || warning;
}

export function RiskNotice({ context = 'dashboard', gate = null, full = false, className = '' }) {
  const warnings = gateWarnings(gate || {});
  return (
    <div className={`risk-notice ${className}`.trim()}>
      <RiskDisclaimer variant={full ? 'full' : 'compact'} context={context} />
      {gate ? (
        <div className="alert warning compact risk-gate-notice">
          <strong>{CONTEXT_TITLES[context] || '风险提示'}：</strong>
          <DataQualityGateBadge gate={gate} variant="compact" />
          {warnings.length ? <span>{warnings.map(warningText).join(' ')}</span> : <span>{gate.next_action || '请确认数据来源和质量门禁状态。'}</span>}
        </div>
      ) : null}
    </div>
  );
}
