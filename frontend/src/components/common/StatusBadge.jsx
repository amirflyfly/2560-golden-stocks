export function statusBadgeClass(status, fallback = 'info') {
  const normalized = String(status || '').toLowerCase();
  if (['success', 'completed', 'active', 'ok', 'healthy', 'normal', 'low', 'positive'].includes(normalized)) return 'success';
  if (['warning', 'pending', 'running', 'queued', 'retrying', 'stale', 'medium', 'neutral', 'cautious', 'unknown'].includes(normalized)) return 'warning';
  if (['danger', 'failed', 'error', 'cancelled', 'disabled', 'unhealthy', 'high'].includes(normalized)) return 'danger';
  if (['info', 'mock', 'primary', 'accepted'].includes(normalized)) return 'info';
  return fallback;
}

export function StatusBadge({ children, status, tone, className = '' }) {
  const badgeTone = tone || statusBadgeClass(status || children);
  return <span className={`status-badge ${badgeTone} ${className}`.trim()}>{children ?? status}</span>;
}
