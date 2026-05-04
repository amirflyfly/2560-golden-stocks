import { getTenantId } from '../../api/client';
import { NavSidebar } from './NavSidebar';
import { Topbar } from './Topbar';

export function AppShell({ page, meta, navGroups, onNavigate, children, authz }) {
  function navigate(nextPage) {
    const nextTenantId = getTenantId();
    const params = new URLSearchParams(window.location.search);
    params.set('tenant_id', nextTenantId);
    window.history.replaceState(null, '', `${window.location.pathname}?${params.toString()}`);
    onNavigate(nextPage);
  }

  return (
    <div className="shell">
      <NavSidebar page={page} navGroups={navGroups} onNavigate={navigate} />
      <div className="content-shell">
        <Topbar meta={meta} authz={authz} />
        {children({ navigate })}
      </div>
    </div>
  );
}
