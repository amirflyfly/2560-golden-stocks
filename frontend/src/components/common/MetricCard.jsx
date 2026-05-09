export function MetricCard({ label, value, hint, badge, danger = false }) {
  return (
    <article className={danger ? 'card metric-card danger-card' : 'card metric-card'}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value ?? '-'}</p>
      {badge || (hint ? <span className="muted small-text">{hint}</span> : null)}
    </article>
  );
}
