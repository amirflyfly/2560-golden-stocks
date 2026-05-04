import { useSyncExternalStore } from 'react';
import { getTenantState, subscribeTenant, updateTenantId } from '../stores/tenantStore';

export function TenantSwitcher() {
  const state = useSyncExternalStore(subscribeTenant, getTenantState, getTenantState);

  return (
    <label className="tenant-switcher">
      <span>当前租户</span>
      <input
        aria-label="当前租户 ID"
        data-testid="tenant-switcher-input"
        value={state.tenantId}
        onChange={(event) => updateTenantId(event.target.value || '1')}
      />
    </label>
  );
}
