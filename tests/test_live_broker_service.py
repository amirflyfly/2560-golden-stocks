from __future__ import annotations

from uuid import uuid4

from backend.application.live_broker_service import BrokerAdapter, LiveBrokerService, normalize_cancel_status, transition_order_status


LIVE_ENV_KEYS = [
    "LIVE_BROKER_ADAPTER",
    "LIVE_BROKER_LAUNCH_POLICY",
    "LIVE_TRADING_ENABLED",
    "LIVE_TRADING_DRY_RUN",
    "LIVE_BROKER_ACCOUNT_ID",
    "LIVE_BROKER_HTTP_ORDER_URL",
    "LIVE_BROKER_HTTP_CANCEL_URL",
    "LIVE_BROKER_HTTP_RECONCILE_URL",
    "LIVE_BROKER_HTTP_TOKEN",
    "LIVE_BROKER_HTTP_SIGNING_SECRET",
    "LIVE_BROKER_HTTP_TIMEOUT_SECONDS",
    "LIVE_TRADING_CONFIRMATION",
    "LIVE_BROKER_RATE_LIMIT_PER_MIN",
]


def _clear_live_env(monkeypatch):
    for key in LIVE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _order() -> dict:
    return {
        "symbol": "000001",
        "side": "BUY",
        "quantity": 100,
        "order_type": "market",
        "idempotency_key": f"live:test:{uuid4().hex}",
        "strategy_code": "2560",
        "reason": "unit test",
    }


def test_live_broker_defaults_to_disabled_guard(monkeypatch):
    _clear_live_env(monkeypatch)

    result = LiveBrokerService().submit_order(1, {"order": _order()})

    assert result["status"] == "blocked"
    assert result["reason"] == "v1_live_broker_not_open"
    assert result["config"]["enabled"] is False
    assert result["config"]["dry_run"] is True
    assert result["audit"]["result"] == "blocked"


def test_live_broker_disabled_launch_policy_overrides_live_enabled(monkeypatch):
    _clear_live_env(monkeypatch)
    monkeypatch.setenv("LIVE_BROKER_ADAPTER", "generic_http")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_TRADING_DRY_RUN", "false")
    monkeypatch.setenv("LIVE_BROKER_HTTP_ORDER_URL", "https://broker.example/orders")
    calls = {"submit": 0}

    class CountingAdapter(BrokerAdapter):
        def submit_order(self, order_intent: dict, config) -> dict:
            calls["submit"] += 1
            return {"status": "submitted"}

        def reconcile_orders(self, account_id: str, config) -> dict:
            return {"status": "reconciled"}

    service = LiveBrokerService({"generic_http": lambda: CountingAdapter()})
    result = service.submit_order(1, {"order": _order(), "dry_run": False, "live_order_ack": "CONFIRM_LIVE_TRADING"})

    assert result["status"] == "blocked"
    assert result["reason"] == "v1_live_broker_not_open"
    assert result["config"]["launch_policy"] == "disabled"
    assert result["config"]["live_orders_open"] is False
    assert calls["submit"] == 0


    _clear_live_env(monkeypatch)
    monkeypatch.setenv("LIVE_BROKER_ADAPTER", "generic_http")
    monkeypatch.setenv("LIVE_BROKER_LAUNCH_POLICY", "enabled")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_BROKER_HTTP_ORDER_URL", "https://broker.example/orders")
    calls = {"submit": 0}

    class CountingAdapter(BrokerAdapter):
        def submit_order(self, order_intent: dict, config) -> dict:
            calls["submit"] += 1
            return {"status": "submitted"}

        def reconcile_orders(self, account_id: str, config) -> dict:
            return {"status": "reconciled"}

    service = LiveBrokerService({"generic_http": lambda: CountingAdapter()})
    result = service.submit_order(1, {"order": _order(), "dry_run": False})

    assert result["status"] == "dry_run"
    assert result["reason"] == "dry_run_guard"
    assert calls["submit"] == 0
    assert result["audit"]["result"] == "dry_run"


def test_live_broker_dry_run_guard_prevents_reconcile_call(monkeypatch):
    _clear_live_env(monkeypatch)
    monkeypatch.setenv("LIVE_BROKER_ADAPTER", "generic_http")
    monkeypatch.setenv("LIVE_BROKER_LAUNCH_POLICY", "enabled")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_BROKER_HTTP_RECONCILE_URL", "https://broker.example/reconcile")
    calls = {"reconcile": 0}

    class CountingAdapter(BrokerAdapter):
        def submit_order(self, order_intent: dict, config) -> dict:
            return {"status": "submitted"}

        def reconcile_orders(self, account_id: str, config) -> dict:
            calls["reconcile"] += 1
            return {"status": "reconciled"}

    service = LiveBrokerService({"generic_http": lambda: CountingAdapter()})
    result = service.reconcile_orders(1, {"account_id": "acct-1"})

    assert result["status"] == "dry_run"
    assert result["reason"] == "dry_run_guard"
    assert calls["reconcile"] == 0


def test_live_broker_rejects_real_send_without_order_url(monkeypatch):
    _clear_live_env(monkeypatch)
    monkeypatch.setenv("LIVE_BROKER_ADAPTER", "generic_http")
    monkeypatch.setenv("LIVE_BROKER_LAUNCH_POLICY", "enabled")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_TRADING_DRY_RUN", "false")

    result = LiveBrokerService().submit_order(
        1,
        {"order": _order(), "dry_run": False, "live_order_ack": "CONFIRM_LIVE_TRADING"},
    )

    assert result["status"] == "rejected"
    assert result["reason"] == "invalid_broker_config"
    assert "missing_order_url" in result["config_validation"]["errors"]


def test_generic_http_adapter_posts_only_after_all_live_gates(monkeypatch):
    from backend.application import live_broker_service as module

    _clear_live_env(monkeypatch)
    monkeypatch.setenv("LIVE_BROKER_ADAPTER", "generic_http")
    monkeypatch.setenv("LIVE_BROKER_LAUNCH_POLICY", "enabled")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_TRADING_DRY_RUN", "false")
    monkeypatch.setenv("LIVE_BROKER_HTTP_ORDER_URL", "https://broker.example/orders")
    monkeypatch.setenv("LIVE_BROKER_HTTP_TOKEN", "secret-token")
    posted: dict = {}

    class FakeResponse:
        status_code = 202
        text = ""

        def json(self):
            return {"broker_order_id": "B-1"}

    def fake_post(url, json, headers, timeout):
        posted.update({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(module.requests, "post", fake_post)

    order = _order()
    result = module.LiveBrokerService().submit_order(
        1,
        {
            "account_id": "acct-1",
            "dry_run": False,
            "live_order_ack": "CONFIRM_LIVE_TRADING",
            "order": order,
        },
    )

    assert result["status"] == "submitted"
    assert posted["url"] == "https://broker.example/orders"
    assert posted["json"]["account_id"] == "acct-1"
    assert posted["json"]["order"]["idempotency_key"] == order["idempotency_key"]
    assert posted["headers"]["Authorization"] == "Bearer secret-token"
    assert result["config"]["token_configured"] is True
    assert "secret-token" not in str(result)


def test_generic_http_adapter_adds_hmac_signature_headers(monkeypatch):
    from backend.application import live_broker_service as module

    _clear_live_env(monkeypatch)
    monkeypatch.setenv("LIVE_BROKER_ADAPTER", "generic_http")
    monkeypatch.setenv("LIVE_BROKER_LAUNCH_POLICY", "enabled")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_TRADING_DRY_RUN", "false")
    monkeypatch.setenv("LIVE_BROKER_HTTP_ORDER_URL", "https://broker.example/orders")
    monkeypatch.setenv("LIVE_BROKER_HTTP_SIGNING_SECRET", "signing-secret")
    posted: dict = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"broker_order_id": "B-2"}

    def fake_post(url, json, headers, timeout):
        posted.update({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(module.requests, "post", fake_post)

    order = {**_order(), "idempotency_key": f"live:test:signature:{uuid4().hex}"}
    result = module.LiveBrokerService().submit_order(
        1,
        {
            "account_id": "acct-1",
            "dry_run": False,
            "live_order_ack": "CONFIRM_LIVE_TRADING",
            "order": order,
        },
    )

    assert result["status"] == "submitted"
    assert posted["headers"]["X-2560-Timestamp"]
    assert posted["headers"]["X-2560-Idempotency-Key"] == order["idempotency_key"]
    assert len(posted["headers"]["X-2560-Signature"]) == 64
    assert result["config"]["signing_secret_configured"] is True


def test_live_broker_ingests_fills_idempotently(monkeypatch):
    _clear_live_env(monkeypatch)
    service = LiveBrokerService()

    first = service.ingest_fills(
        1,
        {
            "account_id": "acct-1",
            "fills": [
                {
                    "fill_key": "fill-1",
                    "broker_order_id": "B-1",
                    "symbol": "000001",
                    "side": "BUY",
                    "quantity": 100,
                    "price": 10.5,
                    "fee": 1.2,
                }
            ],
        },
    )
    second = service.ingest_fills(
        1,
        {
            "account_id": "acct-1",
            "fills": [
                {
                    "fill_key": "fill-1",
                    "broker_order_id": "B-1",
                    "symbol": "000001",
                    "side": "BUY",
                    "quantity": 100,
                    "price": 10.5,
                    "fee": 1.2,
                }
            ],
        },
    )
    fills = service.list_fills(1, {"account_id": "acct-1"})

    assert first["persisted"] == 1
    assert second["persisted"] == 1
    assert fills["total"] >= 1
    assert fills["items"][0]["fill_key"] == "fill-1"


def test_live_broker_cancel_is_guarded_by_dry_run(monkeypatch):
    _clear_live_env(monkeypatch)
    monkeypatch.setenv("LIVE_BROKER_ADAPTER", "generic_http")
    monkeypatch.setenv("LIVE_BROKER_LAUNCH_POLICY", "enabled")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_BROKER_HTTP_CANCEL_URL", "https://broker.example/cancel")

    result = LiveBrokerService().cancel_order(
        1,
        {
            "account_id": "acct-1",
            "cancel": {
                "broker_order_id": "B-1",
                "idempotency_key": "cancel:test:1",
                "reason": "unit test",
            },
        },
    )

    assert result["status"] == "dry_run"
    assert result["reason"] == "dry_run_guard"


def test_live_broker_order_status_transition_contract():
    accepted = transition_order_status("submitted", "partially_filled")
    rejected = transition_order_status("filled", "cancel_pending")

    assert accepted == {
        "from": "submitted",
        "to": "partially_filled",
        "allowed": True,
        "reason": "ok",
        "terminal": False,
    }
    assert rejected["allowed"] is False
    assert rejected["reason"] == "terminal_status"


def test_live_broker_normalizes_cancel_status_from_broker_payload():
    normalized = normalize_cancel_status(
        {
            "status": "cancel_submitted",
            "broker_response": {
                "cancel_status": "pending_cancel",
                "broker_order_id": "B-9",
            },
        }
    )

    assert normalized["status"] == "cancel_pending"
    assert normalized["terminal"] is False
    assert normalized["broker_order_id"] == "B-9"


def test_live_broker_fill_mapping_validation_rejects_unmapped_fill(monkeypatch):
    _clear_live_env(monkeypatch)
    service = LiveBrokerService()

    result = service.ingest_fills(
        1,
        {
            "account_id": "acct-1",
            "fills": [
                {"fill_key": f"fill:bad:{uuid4().hex}", "broker_order_id": "B-1", "side": "BUY", "quantity": 100, "price": 10.5},
                {"fill_key": f"fill:ok:{uuid4().hex}", "broker_order_id": "B-2", "symbol": "000001", "side": "BUY", "quantity": 100, "price": 10.5},
            ],
        },
    )

    assert result["received"] == 2
    assert result["valid"] == 1
    assert result["rejected"] == 1
    assert result["persisted"] == 1
    assert "missing_symbol" in result["items"][0]["field_mapping_validation"]["errors"]
    assert result["items"][1]["field_mapping_validation"]["valid"] is True


def test_live_broker_idempotency_key_conflict_does_not_reuse_prior_request(monkeypatch):
    _clear_live_env(monkeypatch)
    monkeypatch.setenv("LIVE_BROKER_ADAPTER", "test_adapter")
    monkeypatch.setenv("LIVE_BROKER_LAUNCH_POLICY", "enabled")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_TRADING_DRY_RUN", "false")
    calls = {"submit": 0}

    class SubmittedAdapter(BrokerAdapter):
        def submit_order(self, order_intent: dict, config) -> dict:
            calls["submit"] += 1
            return {"status": "submitted", "broker_order_id": f"B-{calls['submit']}"}

        def reconcile_orders(self, account_id: str, config) -> dict:
            return {"status": "reconciled"}

    service = LiveBrokerService({"test_adapter": lambda: SubmittedAdapter()})
    order = {**_order(), "idempotency_key": f"live:conflict:{uuid4().hex}"}
    first = service.submit_order(1, {"order": order, "dry_run": False, "live_order_ack": "CONFIRM_LIVE_TRADING"})
    conflict = service.submit_order(1, {"order": {**order, "quantity": 200}, "dry_run": False, "live_order_ack": "CONFIRM_LIVE_TRADING"})

    assert first["status"] == "submitted"
    assert conflict["status"] == "rejected"
    assert conflict["reason"] == "idempotency_key_conflict"
    assert conflict["idempotency"]["state"] == "conflict"
    assert calls["submit"] == 1


def test_live_broker_reconcile_outputs_structured_differences(monkeypatch):
    _clear_live_env(monkeypatch)
    monkeypatch.setenv("LIVE_BROKER_ADAPTER", "test_adapter")
    monkeypatch.setenv("LIVE_BROKER_LAUNCH_POLICY", "enabled")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("LIVE_TRADING_DRY_RUN", "false")

    class DiffAdapter(BrokerAdapter):
        def submit_order(self, order_intent: dict, config) -> dict:
            return {"status": "submitted"}

        def reconcile_orders(self, account_id: str, config) -> dict:
            return {
                "status": "reconciled",
                "differences": [
                    {
                        "type": "quantity",
                        "broker_order_id": "B-1",
                        "client_order_id": "C-1",
                        "symbol": "000001",
                        "expected": 100,
                        "actual": 80,
                    }
                ],
            }

    service = LiveBrokerService({"test_adapter": lambda: DiffAdapter()})
    result = service.reconcile_orders(1, {"account_id": "acct-1", "dry_run": False, "idempotency_key": f"reconcile:test:{uuid4().hex}"})

    assert result["status"] == "differences_found"
    assert result["reconciliation"]["schema_version"] == "live-broker-reconciliation/v1"
    assert result["reconciliation"]["differences_count"] == 1
    assert result["differences"][0]["type"] == "quantity"
    assert result["differences"][0]["severity"] == "error"
