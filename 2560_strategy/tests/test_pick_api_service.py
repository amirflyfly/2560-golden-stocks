from __future__ import annotations


def test_create_pick_uses_repository_returned_id(monkeypatch):
    from backend.application import pick_api_service
    from backend.application.pick_api_service import PickApiService

    def fake_create_or_replace_pick(*args, **kwargs):
        return 42

    def fake_get_pick_by_id(pick_id, tenant_id=None):
        assert pick_id == 42
        return {
            "id": 42,
            "code": "000001",
            "name": "平安银行",
            "pick_date": "2026-05-04",
            "source": "manual",
            "strategy_name": "2560",
            "review_status": "accepted",
            "result_grade": "pending",
        }

    monkeypatch.setattr(pick_api_service.picks_repo, "get_pick_by_unique", lambda *args, **kwargs: None)
    monkeypatch.setattr(pick_api_service.picks_repo, "create_or_replace_pick", fake_create_or_replace_pick)
    monkeypatch.setattr(pick_api_service.picks_repo, "last_inserted_id", lambda: 999)
    monkeypatch.setattr(pick_api_service.picks_repo, "get_pick_by_id", fake_get_pick_by_id)

    item = PickApiService().create_pick(
        1,
        {
            "symbol": "000001",
            "stock_name": "平安银行",
            "trade_date": "2026-05-04",
            "source": "manual",
            "strategy_code": "2560",
        },
    )

    assert item["id"] == 42
    assert item["symbol"] == "000001"
