import { StatusBadge } from '../common';
import { getTenantId } from '../../api/client';

export function Topbar({ meta, authz }) {
  const role = authz?.role || 'viewer';
  const roleTone = role === 'admin' ? 'success' : role === 'editor' ? 'info' : 'warning';

  return (
    <header className="topbar">
      <div>
        <p className="topbar-title">{meta.title}</p>
        <p className="topbar-subtitle">{meta.subtitle}</p>
      </div>
      <div className="topbar-meta" aria-label="全局状态">
        <StatusBadge tone="success">会话已登录</StatusBadge>
        <StatusBadge tone="info">租户 {getTenantId()}</StatusBadge>
        <StatusBadge tone={roleTone}>role {authz?.loading ? 'loading' : role}</StatusBadge>
      </div>
    </header>
  );
}
