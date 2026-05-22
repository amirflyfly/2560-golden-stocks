from __future__ import annotations


def test_report_summary_filters_current_period_and_reviewed_drilldown(monkeypatch):
    from datetime import date

    from backend.application import report_api_service
    from backend.application.report_api_service import ReportApiService

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 5, 11)

    captured = {}

    def fake_list_picks(where_sql, args, limit=None, tenant_id=None):
        captured["where_sql"] = where_sql
        captured["args"] = args
        return [
            {
                "id": 1,
                "pick_date": "2026-05-11",
                "code": "000001",
                "source": "production_signal",
                "strategy_name": "LIMIT_UP_RETURN",
                "review_status": "validated",
                "deal_status": "closed",
                "result_grade": "medium",
                "return_pct": 5.5,
                "data_quality": "primary",
            }
        ]

    monkeypatch.setattr(report_api_service.picks_repo, "list_picks", fake_list_picks)
    monkeypatch.setattr(report_api_service, "date", FrozenDate)

    payload = ReportApiService().summary(1, "week")

    assert "pick_date>=?" in captured["where_sql"]
    assert captured["args"] == ["2026-05-05", "2026-05-11"]
    assert payload["window"] == {"start_date": "2026-05-05", "end_date": "2026-05-11"}
    assert payload["summary"]["reviewed_count"] == 1
    assert payload["drilldowns"]["reviewed"]["filters"]["reviewed"] == "1"


def test_daily_review_marks_positions_to_market_before_summary(monkeypatch):
    from backend.application import report_api_service
    from backend.application import paper_trading_service
    from backend.application.report_api_service import ReportApiService

    calls = []

    def fake_mark_to_market(self, tenant_id, account_id=None, payload=None):
        calls.append((tenant_id, account_id))
        return {"schema_version": "paper-mark-to-market/v1", "updated": 1}

    monkeypatch.setattr(paper_trading_service.PaperTradingService, "ensure_default_account", lambda self, tenant_id, payload=None: {"id": 7})
    monkeypatch.setattr(paper_trading_service.PaperTradingService, "mark_to_market", fake_mark_to_market)
    monkeypatch.setattr(paper_trading_service.PaperTradingService, "evaluate_exits", lambda *args, **kwargs: {"enabled": True, "orders": [], "skipped": [], "blocked": []})
    monkeypatch.setattr(report_api_service.paper_trading_repo, "summary", lambda tenant_id, account_id=None: {"equity": 100, "cash": 50, "market_value": 50, "total_return_pct": 0})
    monkeypatch.setattr(report_api_service.paper_trading_repo, "list_orders", lambda *args, **kwargs: [])
    monkeypatch.setattr(report_api_service.paper_trading_repo, "list_fills", lambda *args, **kwargs: [])
    monkeypatch.setattr(report_api_service.paper_trading_repo, "list_positions", lambda *args, **kwargs: [])
    monkeypatch.setattr(report_api_service.paper_trading_repo, "signal_review_health", lambda tenant_id: {"complete_rate": 1, "incomplete": 0})
    monkeypatch.setattr(ReportApiService, "summary", lambda self, tenant_id, period="week": {"summary": {}, "attribution": {}})

    payload = ReportApiService().daily_review(1, "2026-05-11", account_id=7)

    assert calls == [(1, 7)]
    assert payload["mark_to_market"]["updated"] == 1
    assert payload["signal_review"]["complete_rate"] == 1


def test_daily_review_can_evaluate_exits_before_summary(monkeypatch):
    from backend.application import report_api_service
    from backend.application import paper_trading_service
    from backend.application.report_api_service import ReportApiService

    calls = []

    def fake_mark_to_market(self, tenant_id, account_id=None, payload=None):
        calls.append(("mark", tenant_id, account_id))
        return {"schema_version": "paper-mark-to-market/v1", "updated": 1}

    def fake_evaluate_exits(self, tenant_id, account_id, payload=None):
        calls.append(("exit", tenant_id, account_id, payload.get("trade_date")))
        return {"enabled": True, "orders": [{"id": 9}], "skipped": [], "blocked": []}

    monkeypatch.setattr(paper_trading_service.PaperTradingService, "ensure_default_account", lambda self, tenant_id, payload=None: {"id": 7})
    monkeypatch.setattr(paper_trading_service.PaperTradingService, "mark_to_market", fake_mark_to_market)
    monkeypatch.setattr(paper_trading_service.PaperTradingService, "evaluate_exits", fake_evaluate_exits)
    monkeypatch.setattr(report_api_service.paper_trading_repo, "summary", lambda tenant_id, account_id=None: {"equity": 100, "cash": 50, "market_value": 50, "total_return_pct": 0})
    monkeypatch.setattr(report_api_service.paper_trading_repo, "list_orders", lambda *args, **kwargs: [{"id": 9, "side": "SELL", "created_at": "2026-05-11T10:00:00"}])
    monkeypatch.setattr(report_api_service.paper_trading_repo, "list_fills", lambda *args, **kwargs: [])
    monkeypatch.setattr(report_api_service.paper_trading_repo, "list_positions", lambda *args, **kwargs: [])
    monkeypatch.setattr(report_api_service.paper_trading_repo, "signal_review_health", lambda tenant_id: {"complete_rate": 0.5, "incomplete": 1})
    monkeypatch.setattr(ReportApiService, "summary", lambda self, tenant_id, period="week": {"summary": {}, "attribution": {}})

    payload = ReportApiService().daily_review(1, "2026-05-11", account_id=7, evaluate_exits=True)

    assert calls == [("mark", 1, 7), ("exit", 1, 7, "2026-05-11")]
    assert payload["exit_evaluation"]["orders"][0]["id"] == 9
    assert payload["paper_trading"]["exit_summary"] == {
        "enabled": True,
        "status": "evaluated",
        "reason": "",
        "orders": 1,
        "skipped": 0,
        "blocked": 0,
    }
    assert payload["paper_trading"]["sell_orders"] == 1
    assert "自动卖出评估: evaluated，订单 1 笔" in payload["message"]
    assert "信号复盘链路完整率" in payload["message"]


def test_daily_review_uses_default_account_for_exit_evaluation(monkeypatch):
    from backend.application import report_api_service
    from backend.application import paper_trading_service
    from backend.application.report_api_service import ReportApiService

    calls = []

    monkeypatch.setattr(paper_trading_service.PaperTradingService, "ensure_default_account", lambda self, tenant_id, payload=None: {"id": 11})
    monkeypatch.setattr(paper_trading_service.PaperTradingService, "mark_to_market", lambda self, tenant_id, account_id=None, payload=None: {"schema_version": "paper-mark-to-market/v1", "updated": 0, "account_id": account_id})

    def fake_evaluate_exits(self, tenant_id, account_id, payload=None):
        calls.append((tenant_id, account_id, payload.get("trade_date")))
        return {"enabled": True, "orders": [], "skipped": [], "blocked": []}

    monkeypatch.setattr(paper_trading_service.PaperTradingService, "evaluate_exits", fake_evaluate_exits)
    monkeypatch.setattr(report_api_service.paper_trading_repo, "summary", lambda tenant_id, account_id=None: {"equity": 100, "cash": 100, "market_value": 0, "total_return_pct": 0})
    monkeypatch.setattr(report_api_service.paper_trading_repo, "list_orders", lambda *args, **kwargs: [])
    monkeypatch.setattr(report_api_service.paper_trading_repo, "list_fills", lambda *args, **kwargs: [])
    monkeypatch.setattr(report_api_service.paper_trading_repo, "list_positions", lambda *args, **kwargs: [])
    monkeypatch.setattr(report_api_service.paper_trading_repo, "signal_review_health", lambda tenant_id: {"complete_rate": 1, "incomplete": 0})
    monkeypatch.setattr(ReportApiService, "summary", lambda self, tenant_id, period="week": {"summary": {}, "attribution": {}})

    payload = ReportApiService().daily_review(1, "2026-05-11", evaluate_exits=True)

    assert payload["account_id"] == 11
    assert calls == [(1, 11, "2026-05-11")]
    assert payload["paper_trading"]["exit_summary"]["status"] == "evaluated"
