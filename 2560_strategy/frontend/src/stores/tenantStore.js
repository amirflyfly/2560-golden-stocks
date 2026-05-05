import { getTenantId, setTenantId } from '../api/client';

const listeners = new Set();
let state = {
  tenantId: getTenantId(),
};

export function getTenantState() {
  return state;
}

export function updateTenantId(tenantId) {
  setTenantId(tenantId);
  state = { ...state, tenantId: String(tenantId) };
  listeners.forEach((listener) => listener(state));
}

export function subscribeTenant(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
