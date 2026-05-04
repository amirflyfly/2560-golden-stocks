"""Bootstrap required seed data for the refactored MySQL schema.

Usage:
    APP_ENV=production DATABASE_URL=mysql+pymysql://... \
    ADMIN_INIT_USERNAME=... ADMIN_INIT_PASSWORD=... \
    python scripts/bootstrap_mysql_seed.py

The script is idempotent. It creates a default tenant, core permissions,
an admin role, and the initial admin user mapped to that tenant.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from backend.db.models import Permission, Role, RolePermission, Strategy, Tenant, User, UserTenant
from backend.db.session import session_scope
from backend.services.password_service import hash_password

DEFAULT_PERMISSIONS = [
    ("strategies:read", "Read strategies", "strategies"),
    ("strategies:write", "Write strategies", "strategies"),
    ("scans:read", "Read scan tasks and results", "scans"),
    ("scans:write", "Create scan tasks", "scans"),
    ("picks:read", "Read picks", "picks"),
    ("picks:write", "Write picks", "picks"),
    ("reports:read", "Read reports", "reports"),
    ("reports:write", "Write reports", "reports"),
    ("admin:read", "Read admin resources", "admin"),
    ("admin:write", "Write admin resources", "admin"),
]

DEFAULT_STRATEGIES = [
    ("2560", "2560 Strategy", "trend", "25-day moving average and 60-day volume strategy"),
    ("first_limit_up", "First Limit Up", "limit-up", "First limit-up discovery and follow-up strategy"),
]


def seed_default_strategies(session, tenant: Tenant, now: datetime) -> dict[str, int]:
    created = 0
    existing = 0
    for code, name, category, description in DEFAULT_STRATEGIES:
        strategy = session.execute(
            select(Strategy).where(Strategy.tenant_id == tenant.id, Strategy.code == code)
        ).scalar_one_or_none()
        if strategy is None:
            session.add(
                Strategy(
                    tenant_id=tenant.id,
                    code=code,
                    name=name,
                    category=category,
                    description=description,
                    config_json={},
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            created += 1
            print(f"created strategy: {code}")
        else:
            existing += 1
            print(f"strategy exists: {code}")
    return {"created": created, "existing": existing}


def ensure_user_tenant_admin_binding(session, user: User, tenant: Tenant, role: Role, now: datetime) -> str:
    user_tenant = session.execute(
        select(UserTenant).where(UserTenant.user_id == user.id, UserTenant.tenant_id == tenant.id)
    ).scalar_one_or_none()
    if user_tenant is None:
        session.add(
            UserTenant(
                user_id=user.id,
                tenant_id=tenant.id,
                role_id=role.id,
                is_default=True,
                created_at=now,
            )
        )
        return "created"
    changed = False
    if user_tenant.role_id != role.id:
        user_tenant.role_id = role.id
        changed = True
    if not user_tenant.is_default:
        user_tenant.is_default = True
        changed = True
    return "updated" if changed else "existing"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> None:
    tenant_code = os.getenv("DEFAULT_TENANT_CODE", "default").strip() or "default"
    tenant_name = os.getenv("DEFAULT_TENANT_NAME", "Default Tenant").strip() or "Default Tenant"
    admin_username = _required_env("ADMIN_INIT_USERNAME")
    admin_password = _required_env("ADMIN_INIT_PASSWORD")
    if len(admin_password) < 12 or admin_password == "admin123":
        raise RuntimeError("ADMIN_INIT_PASSWORD must be strong and must not be admin123")

    now = datetime.now(UTC).replace(tzinfo=None)
    with session_scope() as session:
        tenant = session.execute(select(Tenant).where(Tenant.code == tenant_code)).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(name=tenant_name, code=tenant_code, status="active", plan="default")
            session.add(tenant)
            session.flush()
            print(f"created tenant: {tenant_code}")
        else:
            print(f"tenant exists: {tenant_code}")

        permissions: dict[str, Permission] = {}
        for code, name, module in DEFAULT_PERMISSIONS:
            permission = session.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
            if permission is None:
                permission = Permission(code=code, name=name, module=module)
                session.add(permission)
                session.flush()
                print(f"created permission: {code}")
            permissions[code] = permission

        role = session.execute(
            select(Role).where(Role.tenant_id == tenant.id, Role.code == "admin")
        ).scalar_one_or_none()
        if role is None:
            role = Role(tenant_id=tenant.id, code="admin", name="Tenant Admin", is_system=True, created_at=now)
            session.add(role)
            session.flush()
            print("created role: admin")
        else:
            print("role exists: admin")

        existing_permission_ids = {
            row[0]
            for row in session.execute(
                select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
            ).all()
        }
        for permission in permissions.values():
            if permission.id not in existing_permission_ids:
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))
                print(f"granted permission: {permission.code}")

        user = session.execute(select(User).where(User.username == admin_username)).scalar_one_or_none()
        if user is None:
            user = User(
                username=admin_username,
                email=os.getenv("ADMIN_INIT_EMAIL") or None,
                password_hash=hash_password(admin_password),
                status="active",
            )
            session.add(user)
            session.flush()
            print(f"created user: {admin_username}")
        else:
            print(f"user exists: {admin_username}")

        binding_status = ensure_user_tenant_admin_binding(session, user, tenant, role, now)
        if binding_status == "created":
            print(f"mapped user {admin_username} to tenant {tenant_code}")
        elif binding_status == "updated":
            print(f"updated user tenant mapping: {admin_username}/{tenant_code}")
        else:
            print(f"user tenant mapping exists: {admin_username}/{tenant_code}")

        seed_default_strategies(session, tenant, now)

    print("mysql seed bootstrap ok")


if __name__ == "__main__":
    main()
