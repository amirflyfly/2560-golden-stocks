export const DEFAULT_AUTHZ = {
  loading: true,
  error: '',
  role: 'viewer',
  permissions: {
    can_read: true,
    can_write: false,
    can_admin: false,
  },
};

export function canWrite(authz) {
  return Boolean(authz?.permissions?.can_write);
}

export function canAdmin(authz) {
  return Boolean(authz?.permissions?.can_admin);
}

export function writeDisabledReason(authz) {
  if (authz?.loading) return '正在确认当前角色权限';
  if (canWrite(authz)) return '';
  return '当前角色为 viewer，只能查看，不能执行写操作。';
}
