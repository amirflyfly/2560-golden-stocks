import { TenantSwitcher } from '../TenantSwitcher';
import { StatusBadge } from '../common';
import { getTenantId } from '../../api/client';

export function NavSidebar({ page, navGroups, onNavigate }) {
  return (
    <aside className="sidebar" aria-label="主导航">
      <div className="brand-block">
        <span className="brand-mark" aria-hidden="true">25</span>
        <div>
          <h1>2560 strategy</h1>
          <p className="sidebar-subtitle">战法复盘工作台</p>
        </div>
      </div>

      <div className="tenant-card">
        <p className="tenant-card-title">当前操作上下文</p>
        <TenantSwitcher />
        <div className="tenant-status-row section-gap">
          <StatusBadge tone="success">active</StatusBadge>
          <StatusBadge tone="info">tenant {getTenantId()}</StatusBadge>
        </div>
      </div>

      <nav>
        {navGroups.map((group) => (
          <div className="nav-section" key={group.title}>
            <p className="nav-section-title">{group.title}</p>
            {group.items.map(([key, label, testId]) => (
              <button
                type="button"
                data-testid={testId}
                className={page === key ? 'active' : ''}
                onClick={() => onNavigate(key)}
                key={key}
              >
                {label}
              </button>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
