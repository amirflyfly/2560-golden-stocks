"""Admin API application service."""

from __future__ import annotations

from backend.core.errors import AppError, ForbiddenError, NotFoundError
from backend.repositories import users_repo
from backend.services.password_service import hash_password

VALID_ROLES = {"admin", "editor", "viewer"}
VALID_TENANT_STATUS = {"active", "disabled"}


class AdminApiService:
    def list_users(self) -> dict:
        users = [self._public_user(user) for user in users_repo.list_users()]
        return {"items": users, "total": len(users)}

    def create_user(self, username: str, password: str, role: str = "editor", tenant_id: int | None = None) -> dict:
        username = (username or "").strip()
        password = password or ""
        normalized_role = self._normalize_role(role)
        if not username:
            raise AppError("用户名不能为空", code=400, status_code=400)
        if len(password) < 8:
            raise AppError("密码至少 8 位", code=400, status_code=400)
        if tenant_id is not None and not users_repo.get_tenant_by_id(tenant_id):
            raise NotFoundError("租户不存在")
        try:
            users_repo.create_user(username, hash_password(password), normalized_role)
        except users_repo.DuplicateUserError as exc:
            raise AppError("用户名已存在", code=400, status_code=400) from exc
        user = users_repo.get_user_by_username(username)
        if tenant_id is not None:
            users_repo.bind_user_tenant(int(user["id"]), tenant_id, normalized_role, is_default=True)
        return self._public_user(user)

    def reset_user_password(self, current_user_id: int, user_id: int, password: str) -> dict:
        user = users_repo.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("用户不存在")
        if len(password or "") < 8:
            raise AppError("密码至少 8 位", code=400, status_code=400)
        users_repo.update_password(user_id, hash_password(password))
        return self._public_user(users_repo.get_user_by_id(user_id))

    def bind_user_tenant(self, user_id: int, tenant_id: int, role: str = "editor", is_default: bool = False) -> dict:
        user = users_repo.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("用户不存在")
        tenant = users_repo.get_tenant_by_id(tenant_id)
        if not tenant:
            raise NotFoundError("租户不存在")
        normalized_role = self._normalize_role(role)
        users_repo.bind_user_tenant(user_id, tenant_id, normalized_role, is_default=is_default)
        return self._public_user(users_repo.get_user_by_id(user_id))

    def unbind_user_tenant(self, user_id: int, tenant_id: int) -> dict:
        user = users_repo.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("用户不存在")
        bindings = users_repo.list_user_tenants(user_id)
        if len(bindings) <= 1:
            raise ForbiddenError("用户至少保留一个租户绑定")
        users_repo.unbind_user_tenant(user_id, tenant_id)
        return self._public_user(users_repo.get_user_by_id(user_id))

    def set_user_active(self, current_user_id: int, user_id: int, is_active: bool) -> dict:
        user = users_repo.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("用户不存在")
        if int(user["id"]) == int(current_user_id) and not is_active:
            raise ForbiddenError("不能禁用当前登录管理员")
        if user.get("role") == "admin" and int(user.get("is_active") or 0) == 1 and not is_active:
            if users_repo.count_active_admins() <= 1:
                raise ForbiddenError("至少保留一个启用的管理员")
        users_repo.set_user_active(user_id, is_active)
        updated = users_repo.get_user_by_id(user_id)
        return self._public_user(updated)

    def set_user_role(self, current_user_id: int, user_id: int, role: str) -> dict:
        normalized_role = self._normalize_role(role)
        user = users_repo.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("用户不存在")
        if int(user["id"]) == int(current_user_id) and user.get("role") == "admin" and normalized_role != "admin":
            raise ForbiddenError("不能移除当前登录管理员角色")
        if user.get("role") == "admin" and normalized_role != "admin" and int(user.get("is_active") or 0) == 1:
            if users_repo.count_active_admins() <= 1:
                raise ForbiddenError("至少保留一个启用的管理员")
        users_repo.update_user_role(user_id, normalized_role)
        updated = users_repo.get_user_by_id(user_id)
        return self._public_user(updated)

    def list_tenants(self, current_tenant_id: int) -> dict:
        tenants = [self._public_tenant(item, current_tenant_id) for item in users_repo.list_tenants()]
        return {"items": tenants, "total": len(tenants)}

    def create_tenant(self, code: str, name: str, plan: str = "default") -> dict:
        code = (code or "").strip().lower()
        name = (name or "").strip()
        plan = (plan or "default").strip() or "default"
        if not code or not name:
            raise AppError("租户 code 和 name 不能为空", code=400, status_code=400)
        if users_repo.get_tenant_by_code(code):
            raise AppError("租户 code 已存在", code=400, status_code=400)
        users_repo.create_tenant(code, name, plan=plan, status="active")
        return self._public_tenant(users_repo.get_tenant_by_code(code))

    def update_tenant(self, tenant_id: int, payload: dict) -> dict:
        tenant = users_repo.get_tenant_by_id(tenant_id)
        if not tenant:
            raise NotFoundError("租户不存在")
        name = (payload.get("name") or tenant.get("name") or "").strip()
        plan = (payload.get("plan") or tenant.get("plan") or "default").strip() or "default"
        status = (payload.get("status") or tenant.get("status") or "active").strip()
        if status not in VALID_TENANT_STATUS:
            raise AppError("租户状态无效", code=400, status_code=400)
        if not name:
            raise AppError("租户名称不能为空", code=400, status_code=400)
        users_repo.update_tenant(tenant_id, name=name, plan=plan, status=status)
        return self._public_tenant(users_repo.get_tenant_by_id(tenant_id))

    def _normalize_role(self, role: str) -> str:
        normalized_role = (role or "").strip()
        if normalized_role not in VALID_ROLES:
            raise AppError("角色无效", code=400, status_code=400)
        return normalized_role

    def _public_user(self, user: dict | None) -> dict:
        if not user:
            raise NotFoundError("用户不存在")
        user_id = int(user.get("id"))
        return {
            "id": user.get("id"),
            "username": user.get("username"),
            "role": user.get("role"),
            "is_active": int(user.get("is_active") or 0),
            "created_at": user.get("created_at"),
            "tenants": users_repo.list_user_tenants(user_id),
        }

    def _public_tenant(self, tenant: dict | None, current_tenant_id: int | None = None) -> dict:
        if not tenant:
            raise NotFoundError("租户不存在")
        return {
            "id": tenant.get("id"),
            "code": tenant.get("code"),
            "name": tenant.get("name"),
            "status": tenant.get("status"),
            "plan": tenant.get("plan"),
            "created_at": tenant.get("created_at"),
            "updated_at": tenant.get("updated_at"),
            "is_current": int(tenant.get("id") or 0) == int(current_tenant_id or 0),
        }
