from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models.strategy import Pick
from backend.db.tenant_repository import TenantScopedRepository


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def test_tenant_scoped_repository_filters_by_tenant_id():
    session = make_session()
    repo_tenant_1 = TenantScopedRepository(session, Pick, tenant_id=1)
    repo_tenant_2 = TenantScopedRepository(session, Pick, tenant_id=2)

    repo_tenant_1.add(
        {
            "symbol": "000001",
            "stock_name": "平安银行",
            "trade_date": date(2026, 5, 1),
            "source": "test",
            "score": Decimal("88.8"),
        }
    )
    repo_tenant_2.add(
        {
            "symbol": "600000",
            "stock_name": "浦发银行",
            "trade_date": date(2026, 5, 1),
            "source": "test",
            "score": Decimal("66.6"),
        }
    )
    session.commit()

    tenant_1_items = repo_tenant_1.list()
    tenant_2_items = repo_tenant_2.list()

    assert [item.symbol for item in tenant_1_items] == ["000001"]
    assert [item.symbol for item in tenant_2_items] == ["600000"]
    assert tenant_1_items[0].tenant_id == 1
    assert tenant_2_items[0].tenant_id == 2


def test_tenant_scoped_repository_get_cannot_cross_tenant():
    session = make_session()
    repo_tenant_1 = TenantScopedRepository(session, Pick, tenant_id=1)
    repo_tenant_2 = TenantScopedRepository(session, Pick, tenant_id=2)
    pick = repo_tenant_1.add(
        {
            "symbol": "000001",
            "stock_name": "平安银行",
            "trade_date": date(2026, 5, 1),
            "source": "test",
        }
    )
    session.commit()

    assert repo_tenant_1.get(pick.id) is not None
    assert repo_tenant_2.get(pick.id) is None
