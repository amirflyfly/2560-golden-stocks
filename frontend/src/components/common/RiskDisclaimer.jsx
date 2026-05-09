export function RiskDisclaimer({ variant = 'compact', className = '' }) {
  const compact = variant === 'compact';
  const text = compact
    ? '本系统仅用于内部投研辅助，非投资建议；历史回测不代表未来收益；实盘自动交易 v1.0 未开放。'
    : 'AiStocks 仅用于内部投研辅助，不构成任何投资建议或收益承诺。历史回测不代表未来收益，扫描、回测、模拟交易结果需人工复核；实盘自动交易 v1.0 未开放。';

  return (
    <div className={`alert warning risk-disclaimer ${compact ? 'compact' : 'full'} ${className}`.trim()} role="note">
      <strong>风险声明：</strong>{text}
    </div>
  );
}
