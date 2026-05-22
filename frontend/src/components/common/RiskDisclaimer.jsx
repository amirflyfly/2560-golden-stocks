const CONTEXT_TEXT = {
  dashboard: '今日结论只用于安排投研工作顺序，数据异常时请先处理门禁或人工复核。',
  scan: '策略扫描只产出研究线索和候选，不构成买入或卖出建议。',
  backtest: '历史回测基于样本和假设，不能代表未来收益。',
  report: '报表用于复盘归档，导出后仍需保留免责声明并区分数据质量。',
  paper: '模拟验证不代表真实成交、流动性、滑点或交易限制。',
  kline: '行情、K 线和复权口径可能延迟、缺失或降级。',
};

export const RISK_DISCLAIMER_TEXT = '本系统仅用于策略研究、模拟验证和复盘管理，不构成任何投资建议。行情数据可能延迟、缺失或降级，回测结果不代表未来收益。请勿将扫描、回测或报表结果直接作为实盘交易依据。';

export function RiskDisclaimer({ variant = 'compact', context = '', className = '' }) {
  const compact = variant === 'compact';
  const contextText = CONTEXT_TEXT[context] || '';
  const text = compact
    ? `非投资建议；行情可能延迟、缺失或降级；回测和模拟验证不代表未来收益或真实成交。${contextText ? ` ${contextText}` : ''}`
    : `${RISK_DISCLAIMER_TEXT}${contextText ? ` ${contextText}` : ''} v1.1 不开放实盘自动交易，所有结果均需人工复核。`;

  return (
    <div className={`alert warning risk-disclaimer ${compact ? 'compact' : 'full'} ${className}`.trim()} role="note">
      <strong>风险声明：</strong>{text}
    </div>
  );
}
