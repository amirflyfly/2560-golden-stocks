"""User, tenant and user-tenant repository."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError as SqlAlchemyIntegrityError
from sqlalchemy import func, select

from backend.core.config import get_settings
from backend.db.models import Role, Tenant, User, UserTenant
from backend.db.session import session_scope
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import q as sqlite_q
from backend.repositories.db import q1 as sqlite_q1


DEFAULT_TENANT_ID = int(os.getenv("AUTH_DEFAULT_TENANT_ID", "1"))
SYSTEM_ROLES = {"admin": "Tenant Admin", "editor": "Editor", "viewer": "Viewer"}


class DuplicateUserError(ValueError):
    """Raised when a username already exists in the active repository backend."""


def _repo_backend() -> str:
    forced = (os.getenv("AUTH_REPOSITORY_BACKEND") or "auto").strip().lower()
    if forced in {"sqlite", "mysql"}:
        return forced
    settings = get_settings()
    environment = (settings.environment or "").strip().lower()
    if environment in {"prod", "production"}:
        return "mysql"
    return "sqlite"


def _dt(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return value


def _role_row(session, tenant_id: int | None, code: str) -> Role | None:
    return session.execute(
        select(Role).where(Role.tenant_id == tenant_id, Role.code == code)
    ).scalar_one_or_none()


def _ensure_role(session, tenant_id: int, code: str) -> Role:
    role = _role_row(session, tenant_id, code)
    if role is not None:
        return role
    role = Role(
        tenant_id=tenant_id,
        code=code,
        name=SYSTEM_ROLES.get(code, code.title()),
        is_system=code in SYSTEM_ROLES,
        created_at=datetime.now(),
    )
    session.add(role)
    session.flush()
    return role


def _ensure_default_tenant(session) -> Tenant:
    tenant = session.get(Tenant, DEFAULT_TENANT_ID)
    if tenant is not None:
        return tenant
    tenant = session.execute(select(Tenant).where(Tenant.code == "default")).scalar_one_or_none()
    if tenant is not None:
        return tenant
    tenant = Tenant(
        id=DEFAULT_TENANT_ID,
        code="default",
        name="Default Tenant",
        status="active",
        plan="default",
    )
    session.add(tenant)
    session.flush()
    return tenant


def _default_binding(session, user_id: int) -> UserTenant | None:
    return session.execute(
        select(UserTenant)
        .where(UserTenant.user_id == int(user_id))
        .order_by(UserTenant.is_default.desc(), UserTenant.tenant_id.asc())
        .limit(1)
    ).scalar_one_or_none()


def _public_user(session, user: User | None) -> dict | None:
    if user is None:
        return None
    binding = _default_binding(session, user.id)
    role = binding.role.code if binding and binding.role else "editor"
    return {
        "id": user.id,
        "username": user.username,
        "password_hash": user.password_hash,
        "role": role,
        "is_active": 1 if user.status == "active" else 0,
        "points": int(user.points or 0),
        "last_checkin": user.last_checkin,
        "created_at": _dt(user.created_at),
        "updated_at": _dt(user.updated_at),
        "status": user.status,
    }


def _public_tenant(tenant: Tenant | None) -> dict | None:
    if tenant is None:
        return None
    return {
        "id": tenant.id,
        "code": tenant.code,
        "name": tenant.name,
        "status": tenant.status,
        "plan": tenant.plan,
        "created_at": _dt(tenant.created_at),
        "updated_at": _dt(tenant.updated_at),
    }


def _public_binding(binding: UserTenant) -> dict:
    return {
        "user_id": binding.user_id,
        "tenant_id": binding.tenant_id,
        "role": binding.role.code if binding.role else "editor",
        "is_default": 1 if binding.is_default else 0,
        "code": binding.tenant.code if binding.tenant else "",
        "name": binding.tenant.name if binding.tenant else "",
        "status": binding.tenant.status if binding.tenant else "",
        "plan": binding.tenant.plan if binding.tenant else "",
    }


def get_user_by_username(username: str):
    if _repo_backend() == "sqlite":
        return sqlite_q1("SELECT * FROM users WHERE username=?", (username,))
    with session_scope() as session:
        user = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        return _public_user(session, user)


def get_user_by_id(user_id: int):
    if _repo_backend() == "sqlite":
        return sqlite_q1("SELECT * FROM users WHERE id=?", (int(user_id),))
    with session_scope() as session:
        user = session.get(User, int(user_id))
        return _public_user(session, user)


def create_user(username: str, password_hash: str, role: str = "admin"):
    if _repo_backend() == "sqlite":
        try:
            rowcount = sqlite_execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateUserError(username) from exc
        user = get_user_by_username(username)
        if user:
            try:
                bind_user_tenant(user["id"], 1, role, is_default=True)
            except Exception:
                pass
        return rowcount
    try:
        with session_scope() as session:
            user = User(username=username, password_hash=password_hash, status="active")
            session.add(user)
            session.flush()
            tenant = _ensure_default_tenant(session)
            mapped_role = _ensure_role(session, tenant.id, role)
            session.add(
                UserTenant(
                    user_id=user.id,
                    tenant_id=tenant.id,
                    role_id=mapped_role.id,
                    is_default=True,
                    created_at=datetime.now(),
                )
            )
            session.flush()
    except SqlAlchemyIntegrityError as exc:
        raise DuplicateUserError(username) from exc
    return 1


def set_user_active(user_id: int, is_active: bool):
    if _repo_backend() == "sqlite":
        return sqlite_execute("UPDATE users SET is_active=? WHERE id=?", (1 if is_active else 0, int(user_id)))
    with session_scope() as session:
        user = session.get(User, int(user_id))
        if user is None:
            return 0
        user.status = "active" if is_active else "disabled"
        session.flush()
    return 1


def has_any_users():
    if _repo_backend() == "sqlite":
        return sqlite_q1("SELECT id FROM users LIMIT 1") is not None
    with session_scope() as session:
        return session.execute(select(User.id).limit(1)).first() is not None


def list_users():
    if _repo_backend() == "sqlite":
        return sqlite_q("SELECT id, username, role, is_active, points, last_checkin, created_at FROM users ORDER BY id")
    with session_scope() as session:
        users = session.execute(select(User).order_by(User.id)).scalars().all()
        return [_public_user(session, user) for user in users]


def update_user_role(user_id: int, role: str):
    if _repo_backend() == "sqlite":
        return sqlite_execute("UPDATE users SET role=? WHERE id=?", (role, int(user_id)))
    with session_scope() as session:
        user = session.get(User, int(user_id))
        if user is None:
            return 0
        binding = _default_binding(session, user.id)
        if binding is None:
            tenant = session.get(Tenant, DEFAULT_TENANT_ID)
            if tenant is None:
                return 0
            mapped_role = _ensure_role(session, tenant.id, role)
            session.add(
                UserTenant(
                    user_id=user.id,
                    tenant_id=tenant.id,
                    role_id=mapped_role.id,
                    is_default=True,
                    created_at=datetime.now(),
                )
            )
        else:
            binding.role_id = _ensure_role(session, binding.tenant_id, role).id
        session.flush()
    return 1


def count_active_admins():
    if _repo_backend() == "sqlite":
        row = sqlite_q1("SELECT COUNT(*) AS count FROM users WHERE role='admin' AND is_active=1")
        return int(row.get("count") or 0) if row else 0
    with session_scope() as session:
        count = session.execute(
            select(func.count(func.distinct(User.id)))
            .join(UserTenant, UserTenant.user_id == User.id)
            .join(Role, Role.id == UserTenant.role_id)
            .where(User.status == "active", Role.code == "admin")
        ).scalar_one()
    return int(count or 0)


def update_password(user_id: int, password_hash: str):
    if _repo_backend() == "sqlite":
        return sqlite_execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, int(user_id)))
    with session_scope() as session:
        user = session.get(User, int(user_id))
        if user is None:
            return 0
        user.password_hash = password_hash
        session.flush()
    return 1


def list_tenants():
    if _repo_backend() == "sqlite":
        return sqlite_q("SELECT id, code, name, status, plan, created_at, updated_at FROM tenants ORDER BY id")
    with session_scope() as session:
        tenants = session.execute(select(Tenant).order_by(Tenant.id)).scalars().all()
        return [_public_tenant(tenant) for tenant in tenants]


def get_tenant_by_id(tenant_id: int):
    if _repo_backend() == "sqlite":
        return sqlite_q1(
            "SELECT id, code, name, status, plan, created_at, updated_at FROM tenants WHERE id=?",
            (int(tenant_id),),
        )
    with session_scope() as session:
        return _public_tenant(session.get(Tenant, int(tenant_id)))


def get_tenant_by_code(code: str):
    if _repo_backend() == "sqlite":
        return sqlite_q1(
            "SELECT id, code, name, status, plan, created_at, updated_at FROM tenants WHERE code=?",
            (code,),
        )
    with session_scope() as session:
        tenant = session.execute(select(Tenant).where(Tenant.code == code)).scalar_one_or_none()
        return _public_tenant(tenant)


def create_tenant(code: str, name: str, plan: str = "default", status: str = "active"):
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            "INSERT INTO tenants (code, name, plan, status) VALUES (?, ?, ?, ?)",
            (code, name, plan, status),
        )
    with session_scope() as session:
        session.add(Tenant(code=code, name=name, plan=plan, status=status))
        session.flush()
    return 1


def update_tenant(tenant_id: int, *, name: str, plan: str, status: str):
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            "UPDATE tenants SET name=?, plan=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (name, plan, status, int(tenant_id)),
        )
    with session_scope() as session:
        tenant = session.get(Tenant, int(tenant_id))
        if tenant is None:
            return 0
        tenant.name = name
        tenant.plan = plan
        tenant.status = status
        session.flush()
    return 1


def list_user_tenants(user_id: int):
    if _repo_backend() == "sqlite":
        return sqlite_q(
            """SELECT ut.user_id, ut.tenant_id, ut.role, ut.is_default, t.code, t.name, t.status, t.plan
            FROM user_tenants ut
            JOIN tenants t ON t.id = ut.tenant_id
            WHERE ut.user_id=?
            ORDER BY ut.is_default DESC, ut.tenant_id""",
            (int(user_id),),
        )
    with session_scope() as session:
        bindings = session.execute(
            select(UserTenant)
            .where(UserTenant.user_id == int(user_id))
            .order_by(UserTenant.is_default.desc(), UserTenant.tenant_id.asc())
        ).scalars().all()
        return [_public_binding(binding) for binding in bindings]


def get_user_tenant_binding(user_id: int, tenant_id: int):
    if _repo_backend() == "sqlite":
        return sqlite_q1(
            """SELECT ut.user_id, ut.tenant_id, ut.role, ut.is_default, t.code, t.name, t.status, t.plan
            FROM user_tenants ut
            JOIN tenants t ON t.id = ut.tenant_id
            WHERE ut.user_id=? AND ut.tenant_id=?""",
            (int(user_id), int(tenant_id)),
        )
    with session_scope() as session:
        binding = session.execute(
            select(UserTenant).where(
                UserTenant.user_id == int(user_id),
                UserTenant.tenant_id == int(tenant_id),
            )
        ).scalar_one_or_none()
        return _public_binding(binding) if binding else None


def bind_user_tenant(user_id: int, tenant_id: int, role: str = "editor", is_default: bool = False):
    if _repo_backend() == "sqlite":
        if is_default:
            sqlite_execute("UPDATE user_tenants SET is_default=0 WHERE user_id=?", (int(user_id),))
        return sqlite_execute(
            """INSERT INTO user_tenants (user_id, tenant_id, role, is_default)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, tenant_id) DO UPDATE SET role=excluded.role, is_default=excluded.is_default""",
            (int(user_id), int(tenant_id), role, 1 if is_default else 0),
        )
    with session_scope() as session:
        if is_default:
            for binding in session.execute(
                select(UserTenant).where(UserTenant.user_id == int(user_id))
            ).scalars().all():
                binding.is_default = False
        mapped_role = _ensure_role(session, int(tenant_id), role)
        binding = session.execute(
            select(UserTenant).where(
                UserTenant.user_id == int(user_id),
                UserTenant.tenant_id == int(tenant_id),
            )
        ).scalar_one_or_none()
        if binding is None:
            session.add(
                UserTenant(
                    user_id=int(user_id),
                    tenant_id=int(tenant_id),
                    role_id=mapped_role.id,
                    is_default=bool(is_default),
                    created_at=datetime.now(),
                )
            )
        else:
            binding.role_id = mapped_role.id
            binding.is_default = bool(is_default)
        session.flush()
    return 1


def unbind_user_tenant(user_id: int, tenant_id: int):
    if _repo_backend() == "sqlite":
        return sqlite_execute("DELETE FROM user_tenants WHERE user_id=? AND tenant_id=?", (int(user_id), int(tenant_id)))
    with session_scope() as session:
        binding = session.execute(
            select(UserTenant).where(
                UserTenant.user_id == int(user_id),
                UserTenant.tenant_id == int(tenant_id),
            )
        ).scalar_one_or_none()
        if binding is None:
            return 0
        session.delete(binding)
        session.flush()
    return 1


def update_user_points(user_id: int, points: int):
    if _repo_backend() == "sqlite":
        user = get_user_by_id(user_id)
        current_points = user.get("points", 0) if user else 0
        new_points = current_points + points
        return sqlite_execute("UPDATE users SET points=? WHERE id=?", (new_points, int(user_id)))
    with session_scope() as session:
        user = session.get(User, int(user_id))
        if user is None:
            return 0
        user.points = int(user.points or 0) + int(points or 0)
        session.flush()
    return 1


def get_user_last_checkin(user_id: int):
    if _repo_backend() == "sqlite":
        user = get_user_by_id(user_id)
        return user.get("last_checkin") if user else None
    with session_scope() as session:
        user = session.get(User, int(user_id))
        return user.last_checkin if user else None


def update_user_last_checkin(user_id: int, checkin_date: str):
    if _repo_backend() == "sqlite":
        return sqlite_execute("UPDATE users SET last_checkin=? WHERE id=?", (checkin_date, int(user_id)))
    with session_scope() as session:
        user = session.get(User, int(user_id))
        if user is None:
            return 0
        user.last_checkin = checkin_date
        session.flush()
    return 1
