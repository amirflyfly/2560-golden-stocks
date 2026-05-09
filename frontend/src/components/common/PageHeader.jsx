export function PageHeader({ eyebrow, title, description, actions, badges }) {
  return (
    <div className="page-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <p className="muted">{description}</p> : null}
      </div>
      {actions || badges ? <div className="badge-row">{badges}{actions}</div> : null}
    </div>
  );
}
