import { StatusBadge } from '../common';
import { getTenantId } from '../../api/client';

export function Topbar({ meta, authz, onLogout }) {
  const role = authz?.role || 'viewer';
  const roleTone = role === 'admin' ? 'success' : role === 'editor' ? 'info' : 'warning';
  const roleLabel = {
    admin: '管理员',
    editor: '编辑',
    viewer: '查看者',
    loading: '加载中',
  }[authz?.loading ? 'loading' : role] || role;

  return (
    <header className="topbar">
      <div>
        <p className="topbar-title">{meta.title}</p>
        <p className="topbar-subtitle">{meta.subtitle}</p>
      </div>
      <div className="topbar-meta" aria-label="全局状态">
        <StatusBadge tone="success">会话已登录</StatusBadge>
        <StatusBadge tone="info">数据空间 {getTenantId()}</StatusBadge>
        <StatusBadge tone={roleTone}>角色 {roleLabel}</StatusBadge>
        <button className="btn-secondary topbar-logout" type="button" onClick={onLogout}>
          退出
        </button>
      </div>
    </header>
  );
}
