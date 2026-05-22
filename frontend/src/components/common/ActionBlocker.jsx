export function ActionBlocker({ disabled = false, reason = '', nextAction = '', children, className = '' }) {
  return (
    <span className={`action-blocker ${disabled ? 'disabled' : 'enabled'} ${className}`.trim()} title={disabled ? reason : ''}>
      {children}
      {disabled && reason ? (
        <span className="action-blocker-reason" role="note">
          {reason}{nextAction ? `；${nextAction}` : ''}
        </span>
      ) : null}
    </span>
  );
}
