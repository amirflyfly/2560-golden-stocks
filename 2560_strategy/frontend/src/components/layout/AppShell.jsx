import { NavSidebar } from './NavSidebar';
import { Topbar } from './Topbar';
import { NotificationCenter } from '../notifications/NotificationCenter';

export function AppShell({ page, meta, navGroups, onNavigate, children, authz, onLogout }) {
  function navigate(nextPage, payload = {}) {
    onNavigate(nextPage, payload);
  }

  return (
    <div className="shell">
      <NavSidebar page={page} navGroups={navGroups} onNavigate={navigate} />
      <div className="content-shell">
        <div className="topbar-wrap">
          <Topbar meta={meta} authz={authz} onLogout={onLogout} />
          <NotificationCenter authz={authz} />
        </div>
        {children({ navigate })}
      </div>
    </div>
  );
}
