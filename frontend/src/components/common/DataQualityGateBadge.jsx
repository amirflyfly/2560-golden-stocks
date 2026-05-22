import { StatusBadge } from './StatusBadge';

const GRADE_LABELS = {
  primary: '主数据源',
  ok: '正常',
  fallback: '备用数据源',
  unknown: '未知质量',
  mock: '模拟数据',
};

const STATUS_LABELS = {
  allowed: '允许',
  warning: '需谨慎',
  blocked: '已阻断',
};

function gateStatus(gate = {}) {
  if (gate.blocked === true) return 'blocked';
  return String(gate.status || '').toLowerCase() || 'unknown';
}

function gateTone(gate = {}) {
  const status = gateStatus(gate);
  const grade = String(gate.grade || gate.data_quality || '').toLowerCase();
  if (status === 'blocked' || grade === 'mock') return 'danger';
  if (status === 'warning' || ['fallback', 'unknown', ''].includes(grade) || gate.fallback_used || gate.requires_confirmation) return 'warning';
  if (status === 'allowed' || ['primary', 'ok'].includes(grade)) return 'success';
  return 'info';
}

function gradeLabel(value) {
  const key = String(value || '').toLowerCase();
  return GRADE_LABELS[key] || value || '未知质量';
}

export function DataQualityGateBadge({ gate, variant = 'full', className = '' }) {
  const safeGate = gate || {};
  const status = gateStatus(safeGate);
  const grade = safeGate.grade || safeGate.data_quality || safeGate.quality || 'unknown';
  const source = safeGate.source || safeGate.market_data_source || safeGate.actual_provider || safeGate.provider || 'unknown';
  const statusLabel = STATUS_LABELS[status] || status || '未知';
  const details = [
    gradeLabel(grade),
    source ? `来源 ${source}` : '',
    safeGate.fallback_used ? '已降级' : '',
    safeGate.requires_confirmation ? '需确认' : '',
  ].filter(Boolean).join(' · ');

  if (variant === 'compact') {
    return <StatusBadge tone={gateTone(safeGate)} className={className}>{statusLabel} · {gradeLabel(grade)}</StatusBadge>;
  }

  return (
    <span className={`quality-gate-badge ${gateTone(safeGate)} ${className}`.trim()} title={safeGate.next_action || safeGate.quality_reason || safeGate.reason || details}>
      <StatusBadge tone={gateTone(safeGate)}>{statusLabel}</StatusBadge>
      <span className="quality-gate-detail">{details}</span>
    </span>
  );
}

export { gateTone as dataQualityGateTone };
