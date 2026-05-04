export function SectionCard({ title, subtitle, actions, children, className = '' }) {
  return (
    <section className={`card section-gap ${className}`.trim()}>
      {title || actions ? (
        <div className="section-title-row">
          <div>
            {title ? <h2>{title}</h2> : null}
            {subtitle ? <p className="muted">{subtitle}</p> : null}
          </div>
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}
