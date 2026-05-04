from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db.base import Base
from backend.db.models import Role, Strategy, Tenant, User, UserTenant
from scripts.bootstrap_mysql_seed import DEFAULT_STRATEGIES, ensure_user_tenant_admin_binding, seed_default_strategies


def test_seed_default_strategies_is_idempotent():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 5, 4, 9, 0, 0)

    with Session(engine) as session:
        tenant = Tenant(id=1, code="default", name="Default Tenant", status="active", plan="default")
        session.add(tenant)
        session.commit()

        first = seed_default_strategies(session, tenant, now)
        session.commit()
        second = seed_default_strategies(session, tenant, now)
        session.commit()

        codes = {row[0] for row in session.execute(select(Strategy.code)).all()}

    assert first == {"created": len(DEFAULT_STRATEGIES), "existing": 0}
    assert second == {"created": 0, "existing": len(DEFAULT_STRATEGIES)}
    assert {"2560", "first_limit_up"} <= codes


def test_seed_repairs_existing_admin_tenant_binding_role():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 5, 4, 9, 0, 0)

    with Session(engine) as session:
        tenant = Tenant(id=1, code="default", name="Default Tenant", status="active", plan="default")
        admin_role = Role(id=1, tenant_id=1, code="admin", name="Tenant Admin", is_system=True, created_at=now)
        editor_role = Role(id=2, tenant_id=1, code="editor", name="Editor", is_system=True, created_at=now)
        user = User(id=1, username="admin", password_hash="hash", status="active")
        session.add_all([tenant, admin_role, editor_role, user])
        session.flush()
        session.add(UserTenant(user_id=1, tenant_id=1, role_id=2, is_default=False, created_at=now))
        session.commit()

        status = ensure_user_tenant_admin_binding(session, user, tenant, admin_role, now)
        session.commit()
        binding = session.execute(select(UserTenant).where(UserTenant.user_id == 1)).scalar_one()

    assert status == "updated"
    assert binding.role_id == 1
    assert binding.is_default is True


def test_users_repo_can_create_default_tenant_for_mysql_bootstrap_path():
    from backend.repositories.users_repo import _ensure_default_tenant

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        tenant = _ensure_default_tenant(session)
        session.commit()
        loaded = session.get(Tenant, tenant.id)

    assert loaded is not None
    assert loaded.code == "default"
