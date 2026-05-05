import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { canAdmin } from '../auth/permissions';

export function AdminPage({ authz }) {
  const [state, setState] = useState({ loading: true, error: '', users: [], tenants: [], auditLogs: [] });
  const mayAdmin = canAdmin(authz);
  const disabledReason = authz?.loading ? '正在确认当前角色权限' : '当前页面需要 admin 角色。';

  function load() {
    if (!mayAdmin) {
      setState((prev) => ({ ...prev, loading: false, error: disabledReason }));
      return;
    }
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    Promise.all([api.adminUsers(), api.adminTenants(), api.adminAuditLogs({ limit: 8 }).catch(() => ({ items: [] }))])
      .then(([users, tenants, auditLogs]) => setState({ loading: false, error: '', users: users.items || [], tenants: tenants.items || [], auditLogs: auditLogs.items || [] }))
      .catch((error) => setState((prev) => ({ ...prev, loading: false, error: error.message })));
  }

  useEffect(() => {
    if (authz?.loading) return;
    load();
  }, [authz?.loading, mayAdmin]);

  function toggleActive(user) {
    if (!mayAdmin) return;
    api.setUserActive(user.id, !user.is_active).then(load).catch((error) => setState((prev) => ({ ...prev, error: error.message })));
  }

  function changeRole(user, role) {
    if (!mayAdmin) return;
    api.setUserRole(user.id, role).then(load).catch((error) => setState((prev) => ({ ...prev, error: error.message })));
  }

  return (
    <main className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Admin</p>
          <h1>后台管理</h1>
          <p className="muted">管理用户、角色、启停状态与租户视图，仅 admin 可执行管理操作。</p>
        </div>
        <button type="button" data-testid="admin-refresh" onClick={load} disabled={state.loading || !mayAdmin} title={disabledReason}>刷新</button>
      </div>
      {state.error ? <div className="alert" data-testid="admin-error">{state.error}</div> : null}
      {!mayAdmin ? <div className="alert warning">{disabledReason}</div> : null}
      {state.loading ? <p>加载中...</p> : null}

      <section className="card">
        <h2>用户</h2>
        <div className="table admin-table" data-testid="admin-users-table">
          <div className="table-row table-head"><span>用户</span><span>角色</span><span>状态</span><span>创建时间</span><span>操作</span></div>
          {state.users.map((user) => (
            <div className="table-row" data-testid={`admin-user-row-${user.username}`} key={user.id}>
              <span>{user.username}</span>
              <span>
                <select data-testid={`admin-user-role-${user.username}`} value={user.role} onChange={(event) => changeRole(user, event.target.value)} disabled={!mayAdmin} title={disabledReason}>
                  <option value="admin">admin</option>
                  <option value="editor">editor</option>
                  <option value="viewer">viewer</option>
                </select>
              </span>
              <span>{user.is_active ? '启用' : '停用'}</span>
              <span>{user.created_at || '-'}</span>
              <span><button type="button" onClick={() => toggleActive(user)} disabled={!mayAdmin} title={disabledReason}>{user.is_active ? '停用' : '启用'}</button></span>
            </div>
          ))}
          {state.users.length ? null : <div className="empty">暂无用户</div>}
        </div>
      </section>

      <section className="card section-gap">
        <h2>租户</h2>
        <div className="table compact-table" data-testid="admin-tenants-table">
          <div className="table-row table-head"><span>名称</span><span>代码</span><span>状态</span></div>
          {state.tenants.map((tenant) => (
            <div className="table-row" data-testid={`admin-tenant-row-${tenant.code}`} key={tenant.id}>
              <span>{tenant.name}</span>
              <span>{tenant.code}</span>
              <span>{tenant.status}{tenant.is_current ? ' / 当前' : ''}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="card section-gap">
        <div className="section-title-row">
          <h2>最近审计记录</h2>
          <span className="status-badge info">关键操作可追溯</span>
        </div>
        <div className="table audit-table" data-testid="admin-audit-table">
          <div className="table-row table-head"><span>动作</span><span>资源</span><span>结果</span><span>操作者</span><span>时间</span></div>
          {state.auditLogs.map((log) => (
            <div className="table-row" data-testid={`admin-audit-row-${log.id}`} key={log.id}>
              <span>{log.action}</span>
              <span>{log.resource_type}{log.resource_id ? ` / ${log.resource_id}` : ''}</span>
              <span><span className={log.result === 'success' ? 'status-badge success' : 'status-badge danger'}>{log.result}</span></span>
              <span>{log.username || `user#${log.user_id || '-'}`}</span>
              <span>{log.created_at || '-'}</span>
            </div>
          ))}
          {state.auditLogs.length ? null : <div className="empty">暂无审计记录。</div>}
        </div>
      </section>
    </main>
  );
}
