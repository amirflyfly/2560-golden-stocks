import { useSyncExternalStore } from 'react';
import { getTenantState, subscribeTenant, updateTenantId } from '../stores/tenantStore';
import { StatusBadge } from './common';

export function TenantSwitcher() {
  const state = useSyncExternalStore(subscribeTenant, getTenantState, getTenantState);

  return (
    <div className="tenant-switcher">
      <div className="tenant-current-row">
        <StatusBadge tone="success">已连接</StatusBadge>
        <StatusBadge tone="info">默认空间 #{state.tenantId}</StatusBadge>
      </div>
      <p>这里决定当前查看和操作哪一套数据。单人使用时保持默认空间即可。</p>
      <details className="tenant-advanced">
        <summary>切换数据空间</summary>
        <label>
          <span>空间编号</span>
          <input
            aria-label="数据空间编号"
            data-testid="tenant-switcher-input"
            value={state.tenantId}
            onChange={(event) => updateTenantId(event.target.value || '1')}
          />
        </label>
      </details>
    </div>
  );
}
