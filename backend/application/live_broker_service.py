"""Live broker adapter boundary with opt-in safety guards."""

from __future__ import annotations

import os
import hashlib
import hmac
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Callable

import requests

from backend.repositories import live_broker_repo


LIVE_CONFIRMATION_PHRASE = "CONFIRM_LIVE_TRADING"
LIVE_BROKER_DISABLED_REASON = "v1_live_broker_not_open"
SUPPORTED_ORDER_TYPES = {"market", "limit"}
SUPPORTED_SIDES = {"BUY", "SELL"}


class BrokerOrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_PENDING = "cancel_pending"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"
    UNKNOWN = "unknown"


TERMINAL_ORDER_STATUSES = {
    BrokerOrderStatus.FILLED.value,
    BrokerOrderStatus.CANCELED.value,
    BrokerOrderStatus.REJECTED.value,
    BrokerOrderStatus.EXPIRED.value,
    BrokerOrderStatus.FAILED.value,
}
ORDER_STATUS_TRANSITIONS: dict[str, set[str]] = {
    BrokerOrderStatus.PENDING.value: {
        BrokerOrderStatus.SUBMITTED.value,
        BrokerOrderStatus.PARTIALLY_FILLED.value,
        BrokerOrderStatus.FILLED.value,
        BrokerOrderStatus.CANCEL_PENDING.value,
        BrokerOrderStatus.CANCELED.value,
        BrokerOrderStatus.REJECTED.value,
        BrokerOrderStatus.EXPIRED.value,
        BrokerOrderStatus.FAILED.value,
    },
    BrokerOrderStatus.SUBMITTED.value: {
        BrokerOrderStatus.PARTIALLY_FILLED.value,
        BrokerOrderStatus.FILLED.value,
        BrokerOrderStatus.CANCEL_PENDING.value,
        BrokerOrderStatus.CANCELED.value,
        BrokerOrderStatus.REJECTED.value,
        BrokerOrderStatus.EXPIRED.value,
        BrokerOrderStatus.FAILED.value,
    },
    BrokerOrderStatus.PARTIALLY_FILLED.value: {
        BrokerOrderStatus.FILLED.value,
        BrokerOrderStatus.CANCEL_PENDING.value,
        BrokerOrderStatus.CANCELED.value,
        BrokerOrderStatus.FAILED.value,
    },
    BrokerOrderStatus.CANCEL_PENDING.value: {
        BrokerOrderStatus.CANCELED.value,
        BrokerOrderStatus.PARTIALLY_FILLED.value,
        BrokerOrderStatus.FILLED.value,
        BrokerOrderStatus.FAILED.value,
    },
    BrokerOrderStatus.UNKNOWN.value: {
        BrokerOrderStatus.PENDING.value,
        BrokerOrderStatus.SUBMITTED.value,
        BrokerOrderStatus.PARTIALLY_FILLED.value,
        BrokerOrderStatus.FILLED.value,
        BrokerOrderStatus.CANCEL_PENDING.value,
        BrokerOrderStatus.CANCELED.value,
        BrokerOrderStatus.REJECTED.value,
        BrokerOrderStatus.EXPIRED.value,
        BrokerOrderStatus.FAILED.value,
    },
}
ORDER_STATUS_ALIASES = {
    "": BrokerOrderStatus.UNKNOWN.value,
    "new": BrokerOrderStatus.SUBMITTED.value,
    "accepted": BrokerOrderStatus.SUBMITTED.value,
    "open": BrokerOrderStatus.SUBMITTED.value,
    "submitted": BrokerOrderStatus.SUBMITTED.value,
    "pending": BrokerOrderStatus.PENDING.value,
    "created": BrokerOrderStatus.PENDING.value,
    "partially_filled": BrokerOrderStatus.PARTIALLY_FILLED.value,
    "partial_filled": BrokerOrderStatus.PARTIALLY_FILLED.value,
    "partial": BrokerOrderStatus.PARTIALLY_FILLED.value,
    "partfilled": BrokerOrderStatus.PARTIALLY_FILLED.value,
    "filled": BrokerOrderStatus.FILLED.value,
    "done": BrokerOrderStatus.FILLED.value,
    "cancel_submitted": BrokerOrderStatus.CANCEL_PENDING.value,
    "cancel_pending": BrokerOrderStatus.CANCEL_PENDING.value,
    "pending_cancel": BrokerOrderStatus.CANCEL_PENDING.value,
    "canceling": BrokerOrderStatus.CANCEL_PENDING.value,
    "cancelled": BrokerOrderStatus.CANCELED.value,
    "canceled": BrokerOrderStatus.CANCELED.value,
    "withdrawn": BrokerOrderStatus.CANCELED.value,
    "rejected": BrokerOrderStatus.REJECTED.value,
    "broker_rejected": BrokerOrderStatus.REJECTED.value,
    "expired": BrokerOrderStatus.EXPIRED.value,
    "failed": BrokerOrderStatus.FAILED.value,
    "error": BrokerOrderStatus.FAILED.value,
}


class BrokerAdapter(ABC):
    """Interface implemented by live broker adapters."""

    mode = "live"

    @abstractmethod
    def submit_order(self, order_intent: dict, config: "LiveBrokerConfig") -> dict:
        raise NotImplementedError

    @abstractmethod
    def reconcile_orders(self, account_id: str, config: "LiveBrokerConfig") -> dict:
        raise NotImplementedError

    def cancel_order(self, cancel_intent: dict, config: "LiveBrokerConfig") -> dict:
        return {"status": "blocked", "reason": "cancel_not_supported", "adapter": getattr(self, "name", "unknown")}


class DisabledBrokerAdapter(BrokerAdapter):
    name = "disabled"

    def submit_order(self, order_intent: dict, config: "LiveBrokerConfig") -> dict:
        return {"status": "blocked", "reason": LIVE_BROKER_DISABLED_REASON, "adapter": self.name}

    def reconcile_orders(self, account_id: str, config: "LiveBrokerConfig") -> dict:
        return {"status": "blocked", "reason": LIVE_BROKER_DISABLED_REASON, "adapter": self.name}

    def cancel_order(self, cancel_intent: dict, config: "LiveBrokerConfig") -> dict:
        return {"status": "blocked", "reason": LIVE_BROKER_DISABLED_REASON, "adapter": self.name}


class GenericHttpBrokerAdapter(BrokerAdapter):
    """Minimal adapter for broker gateways that accept JSON over HTTP."""

    name = "generic_http"

    def submit_order(self, order_intent: dict, config: "LiveBrokerConfig") -> dict:
        payload = {"account_id": config.account_id, "order": order_intent}
        response = requests.post(
            config.order_url,
            json=payload,
            headers=config.http_headers(payload, idempotency_key=order_intent.get("idempotency_key")),
            timeout=config.timeout_seconds,
        )
        return {
            "status": "submitted" if 200 <= response.status_code < 300 else "broker_rejected",
            "adapter": self.name,
            "http_status": response.status_code,
            "broker_response": _response_body(response),
        }

    def reconcile_orders(self, account_id: str, config: "LiveBrokerConfig") -> dict:
        payload = {"account_id": account_id}
        response = requests.post(
            config.reconcile_url,
            json=payload,
            headers=config.http_headers(payload, idempotency_key=f"reconcile:{account_id}:{int(time.time() // 60)}"),
            timeout=config.timeout_seconds,
        )
        return {
            "status": "reconciled" if 200 <= response.status_code < 300 else "broker_rejected",
            "adapter": self.name,
            "http_status": response.status_code,
            "broker_response": _response_body(response),
        }

    def cancel_order(self, cancel_intent: dict, config: "LiveBrokerConfig") -> dict:
        if not config.cancel_url:
            return {"status": "blocked", "reason": "cancel_url_missing", "adapter": self.name}
        payload = {"account_id": config.account_id, "cancel": cancel_intent}
        response = requests.post(
            config.cancel_url,
            json=payload,
            headers=config.http_headers(payload, idempotency_key=cancel_intent.get("idempotency_key")),
            timeout=config.timeout_seconds,
        )
        return {
            "status": "cancel_submitted" if 200 <= response.status_code < 300 else "broker_rejected",
            "adapter": self.name,
            "http_status": response.status_code,
            "broker_response": _response_body(response),
        }


def _response_body(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"text": response.text[:1000]}


@dataclass(frozen=True)
class LiveBrokerConfig:
    adapter_name: str
    launch_policy: str
    enabled: bool
    dry_run: bool
    account_id: str
    order_url: str
    cancel_url: str
    reconcile_url: str
    token: str
    signing_secret: str
    timeout_seconds: float
    confirmation_phrase: str
    request_confirmation: str

    def http_headers(self, payload: dict | None = None, *, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.signing_secret and payload is not None:
            timestamp = str(int(time.time()))
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            signature_payload = "\n".join([timestamp, idempotency_key or "", body])
            signature = hmac.new(self.signing_secret.encode("utf-8"), signature_payload.encode("utf-8"), hashlib.sha256).hexdigest()
            headers["X-2560-Timestamp"] = timestamp
            headers["X-2560-Idempotency-Key"] = idempotency_key or ""
            headers["X-2560-Signature"] = signature
        return headers

    def public_dict(self) -> dict:
        return {
            "adapter": self.adapter_name,
            "launch_policy": self.launch_policy,
            "live_orders_open": self.launch_policy == "enabled",
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "account_id_configured": bool(self.account_id),
            "order_url_configured": bool(self.order_url),
            "cancel_url_configured": bool(self.cancel_url),
            "reconcile_url_configured": bool(self.reconcile_url),
            "token_configured": bool(self.token),
            "signing_secret_configured": bool(self.signing_secret),
            "timeout_seconds": self.timeout_seconds,
            "confirmation_required": self.confirmation_phrase,
            "confirmation_received": self.request_confirmation == self.confirmation_phrase,
        }


AdapterFactory = Callable[[], BrokerAdapter]


def _bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_bool(name: str, default: bool = False) -> bool:
    return _bool_value(os.getenv(name), default)


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def normalize_order_status(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return ORDER_STATUS_ALIASES.get(normalized, normalized if normalized in {item.value for item in BrokerOrderStatus} else BrokerOrderStatus.UNKNOWN.value)


def transition_order_status(current_status: Any, next_status: Any) -> dict:
    current = normalize_order_status(current_status)
    target = normalize_order_status(next_status)
    allowed = current == target or target in ORDER_STATUS_TRANSITIONS.get(current, set())
    if current in TERMINAL_ORDER_STATUSES and current != target:
        allowed = False
    reason = "ok" if allowed else ("terminal_status" if current in TERMINAL_ORDER_STATUSES else "invalid_transition")
    return {
        "from": current,
        "to": target,
        "allowed": allowed,
        "reason": reason,
        "terminal": target in TERMINAL_ORDER_STATUSES,
    }


def normalize_cancel_status(adapter_result: dict | None) -> dict:
    result = adapter_result or {}
    broker_response = result.get("broker_response") if isinstance(result.get("broker_response"), dict) else {}
    raw_status = (
        result.get("order_status")
        or result.get("cancel_status")
        or broker_response.get("order_status")
        or broker_response.get("cancel_status")
        or result.get("status")
        or broker_response.get("status")
    )
    status = normalize_order_status(raw_status)
    if status == BrokerOrderStatus.SUBMITTED.value:
        status = BrokerOrderStatus.CANCEL_PENDING.value
    return {
        "status": status,
        "raw_status": str(raw_status or ""),
        "terminal": status in TERMINAL_ORDER_STATUSES,
        "broker_order_id": str(broker_response.get("broker_order_id") or result.get("broker_order_id") or ""),
        "client_order_id": str(broker_response.get("client_order_id") or result.get("client_order_id") or ""),
        "reason": str(result.get("reason") or broker_response.get("reason") or ""),
    }


class LiveBrokerService:
    def __init__(self, adapter_registry: dict[str, AdapterFactory] | None = None):
        self.adapter_registry = adapter_registry or {
            "disabled": DisabledBrokerAdapter,
            "generic_http": GenericHttpBrokerAdapter,
        }

    def register_adapter(self, name: str, factory: AdapterFactory) -> None:
        normalized = str(name or "").strip().lower()
        if not normalized:
            raise ValueError("adapter name is required")
        self.adapter_registry[normalized] = factory

    def broker_status(self, payload: dict | None = None) -> dict:
        config = self._load_config(payload or {})
        validation = self.validate_config(payload or {})
        return {
            "mode": "live",
            "status": "ready" if validation["ready_for_live_orders"] else "guarded",
            "reason": "" if validation["ready_for_live_orders"] else (LIVE_BROKER_DISABLED_REASON if config.launch_policy == "disabled" else "live_broker_guarded"),
            "config": config.public_dict(),
            "validation": validation,
            "adapters": sorted(self.adapter_registry.keys()),
            "guard": "v1.0 live broker is closed unless LIVE_BROKER_LAUNCH_POLICY=enabled plus all live order gates pass",
        }

    def submit_order(self, tenant_id: int, payload: dict | None = None) -> dict:
        payload = payload or {}
        config = self._load_config(payload)
        order_intent = self._normalize_order_intent(payload)
        order_validation = self.validate_order_intent(order_intent)
        config_validation = self.validate_config(payload)
        audit = self._audit_base(tenant_id, "live_broker.submit_order", config, order_intent)
        previous = live_broker_repo.get_request(tenant_id, order_intent.get("idempotency_key") or "")
        incoming_hash = live_broker_repo.request_hash(order_intent)
        if previous and previous.get("request_hash") != incoming_hash:
            return self._idempotency_conflict_result(previous, config, order_intent, audit)
        if (
            previous
            and previous.get("status") not in {"blocked", "dry_run", "rejected", "broker_rejected", "broker_error", "failed"}
            and config.enabled
            and not config.dry_run
            and config.request_confirmation == config.confirmation_phrase
        ):
            return self._stored_result("idempotent_replay", previous, config, order_intent, audit)
        if self._rate_limited(tenant_id, "live_broker.submit_order"):
            result = self._guarded_result("blocked", "rate_limited", config, audit, order_validation=order_validation, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.submit_order", config, order_intent, result)
            return result

        if not order_validation["valid"]:
            result = self._guarded_result("rejected", "invalid_order_intent", config, audit, order_validation=order_validation)
            self._record_request(tenant_id, "live_broker.submit_order", config, order_intent, result)
            return result
        if config_validation["errors"]:
            result = self._guarded_result("rejected", "invalid_broker_config", config, audit, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.submit_order", config, order_intent, result)
            return result
        if config.launch_policy == "disabled":
            result = self._guarded_result("blocked", LIVE_BROKER_DISABLED_REASON, config, audit, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.submit_order", config, order_intent, result)
            return result
        if not config.enabled:
            result = self._guarded_result("blocked", "live_trading_disabled", config, audit, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.submit_order", config, order_intent, result)
            return result
        if config.dry_run:
            result = {
                "status": "dry_run",
                "reason": "dry_run_guard",
                "mode": "live",
                "adapter": config.adapter_name,
                "order_intent": order_intent,
                "config": config.public_dict(),
                "order_validation": order_validation,
                "config_validation": config_validation,
                "audit": {**audit, "result": "dry_run"},
            }
            self._record_request(tenant_id, "live_broker.submit_order", config, order_intent, result)
            return result
        if config.request_confirmation != config.confirmation_phrase:
            result = self._guarded_result("blocked", "live_order_confirmation_required", config, audit, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.submit_order", config, order_intent, result)
            return result

        adapter = self._adapter(config.adapter_name)
        try:
            adapter_result = adapter.submit_order(order_intent, config)
        except Exception as exc:  # pragma: no cover - defensive around external broker code
            result = self._guarded_result("broker_error", str(exc), config, audit, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.submit_order", config, order_intent, result)
            return result
        order_status = normalize_order_status(adapter_result.get("order_status") or adapter_result.get("status") or "submitted")
        result_status = adapter_result.get("status") or order_status
        result = {
            "status": result_status,
            "reason": adapter_result.get("reason") or "",
            "mode": "live",
            "adapter": config.adapter_name,
            "order_intent": order_intent,
            "order_status": order_status,
            "order_state_transition": transition_order_status(BrokerOrderStatus.PENDING.value, order_status),
            "broker_result": adapter_result,
            "config": config.public_dict(),
            "order_validation": order_validation,
            "config_validation": config_validation,
            "audit": {**audit, "result": result_status},
        }
        self._record_request(tenant_id, "live_broker.submit_order", config, order_intent, result)
        return result

    def reconcile_orders(self, tenant_id: int, payload: dict | None = None) -> dict:
        payload = payload or {}
        config = self._load_config(payload)
        config_validation = self.validate_config(payload, require_order_url=False)
        audit = {
            "tenant_id": int(tenant_id or 0),
            "action": "live_broker.reconcile_orders",
            "adapter": config.adapter_name,
            "account_id": config.account_id,
            "dry_run": config.dry_run,
        }
        if config_validation["errors"]:
            return self._guarded_result("rejected", "invalid_broker_config", config, audit, config_validation=config_validation)
        if config.launch_policy == "disabled":
            return self._guarded_result("blocked", LIVE_BROKER_DISABLED_REASON, config, audit, config_validation=config_validation)
        if not config.enabled:
            return self._guarded_result("blocked", "live_trading_disabled", config, audit, config_validation=config_validation)
        if config.dry_run:
            return self._guarded_result("dry_run", "dry_run_guard", config, audit, config_validation=config_validation)
        if config.adapter_name == "generic_http" and not config.reconcile_url:
            return self._guarded_result("rejected", "missing_reconcile_url", config, audit, config_validation=config_validation)

        adapter = self._adapter(config.adapter_name)
        try:
            adapter_result = adapter.reconcile_orders(config.account_id, config)
        except Exception as exc:  # pragma: no cover - defensive around external broker code
            return self._guarded_result("broker_error", str(exc), config, audit, config_validation=config_validation)
        reconciliation = self._normalize_reconciliation(adapter_result)
        result = {
            "status": "differences_found" if reconciliation["differences"] else adapter_result.get("status") or "reconciled",
            "reason": adapter_result.get("reason") or "",
            "mode": "live",
            "adapter": config.adapter_name,
            "broker_result": adapter_result,
            "reconciliation": reconciliation,
            "differences": reconciliation["differences"],
            "config": config.public_dict(),
            "config_validation": config_validation,
            "audit": {**audit, "result": "differences_found" if reconciliation["differences"] else adapter_result.get("status") or "reconciled"},
        }
        reconciliation_key = str(payload.get("idempotency_key") or f"reconcile:{config.account_id}:{int(time.time() // 60)}")
        live_broker_repo.record_reconciliation(
            tenant_id,
            account_id=config.account_id,
            idempotency_key=reconciliation_key,
            request={"account_id": config.account_id},
            result=result,
        )
        return result

    def cancel_order(self, tenant_id: int, payload: dict | None = None) -> dict:
        payload = payload or {}
        config = self._load_config(payload)
        cancel_intent = self._normalize_cancel_intent(payload)
        validation = self.validate_cancel_intent(cancel_intent)
        config_validation = self.validate_config(payload, require_order_url=False)
        audit = self._audit_base(tenant_id, "live_broker.cancel_order", config, cancel_intent)
        previous = live_broker_repo.get_request(tenant_id, cancel_intent.get("idempotency_key") or "")
        if previous and previous.get("request_hash") != live_broker_repo.request_hash(cancel_intent):
            return self._idempotency_conflict_result(previous, config, cancel_intent, audit)
        if (
            previous
            and previous.get("status") not in {"blocked", "dry_run", "rejected", "broker_rejected", "broker_error", "failed"}
            and config.enabled
            and not config.dry_run
            and config.request_confirmation == config.confirmation_phrase
        ):
            return self._stored_result("idempotent_replay", previous, config, cancel_intent, audit)
        if not validation["valid"]:
            result = self._guarded_result("rejected", "invalid_cancel_intent", config, audit, order_validation=validation, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.cancel_order", config, cancel_intent, result)
            return result
        if config_validation["errors"]:
            result = self._guarded_result("rejected", "invalid_broker_config", config, audit, order_validation=validation, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.cancel_order", config, cancel_intent, result)
            return result
        if config.launch_policy == "disabled":
            result = self._guarded_result("blocked", LIVE_BROKER_DISABLED_REASON, config, audit, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.cancel_order", config, cancel_intent, result)
            return result
        if not config.enabled:
            result = self._guarded_result("blocked", "live_trading_disabled", config, audit, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.cancel_order", config, cancel_intent, result)
            return result
        if config.dry_run:
            result = self._guarded_result("dry_run", "dry_run_guard", config, audit, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.cancel_order", config, cancel_intent, result)
            return result
        if config.request_confirmation != config.confirmation_phrase:
            result = self._guarded_result("blocked", "live_order_confirmation_required", config, audit, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.cancel_order", config, cancel_intent, result)
            return result
        adapter = self._adapter(config.adapter_name)
        try:
            adapter_result = adapter.cancel_order(cancel_intent, config)
        except Exception as exc:
            result = self._guarded_result("broker_error", str(exc), config, audit, config_validation=config_validation)
            self._record_request(tenant_id, "live_broker.cancel_order", config, cancel_intent, result)
            return result
        cancel_status = normalize_cancel_status(adapter_result)
        result = {
            "status": adapter_result.get("status") or cancel_status["status"],
            "reason": adapter_result.get("reason") or "",
            "mode": "live",
            "adapter": config.adapter_name,
            "cancel_intent": cancel_intent,
            "cancel_status": cancel_status,
            "order_state_transition": transition_order_status(BrokerOrderStatus.SUBMITTED.value, cancel_status["status"]),
            "broker_result": adapter_result,
            "config": config.public_dict(),
            "cancel_validation": validation,
            "config_validation": config_validation,
            "audit": {**audit, "result": adapter_result.get("status") or "cancel_submitted"},
        }
        self._record_request(tenant_id, "live_broker.cancel_order", config, cancel_intent, result)
        return result

    def ingest_fills(self, tenant_id: int, payload: dict | None = None) -> dict:
        payload = payload or {}
        fills = payload.get("fills") if isinstance(payload.get("fills"), list) else [payload]
        normalized = [self._normalize_fill(item, payload) for item in fills if isinstance(item, dict)]
        valid_items = [item for item in normalized if item.get("field_mapping_validation", {}).get("valid")]
        persisted = live_broker_repo.upsert_fills(tenant_id, valid_items)
        return {
            "schema_version": "live-broker-fills/v1",
            "tenant_id": int(tenant_id or 0),
            "received": len(normalized),
            "valid": len(valid_items),
            "rejected": len(normalized) - len(valid_items),
            "persisted": persisted,
            "items": normalized[:50],
        }

    def list_fills(self, tenant_id: int, payload: dict | None = None) -> dict:
        payload = payload or {}
        account_id = str(payload.get("account_id") or "").strip()
        limit = int(payload.get("limit") or 100)
        items = live_broker_repo.list_fills(tenant_id, account_id=account_id, limit=limit)
        return {"items": items, "total": len(items), "tenant_id": int(tenant_id or 0), "account_id": account_id}

    def validate_config(self, payload: dict | None = None, *, require_order_url: bool = True) -> dict:
        config = self._load_config(payload or {})
        errors: list[str] = []
        warnings: list[str] = []

        if config.adapter_name not in self.adapter_registry:
            errors.append("unsupported_broker_adapter")
        if config.launch_policy == "disabled":
            warnings.append(LIVE_BROKER_DISABLED_REASON)
        elif config.launch_policy != "enabled":
            errors.append("unsupported_live_broker_launch_policy")
        if not config.enabled:
            warnings.append("live_trading_disabled")
        if config.dry_run:
            warnings.append("dry_run_guard_enabled")
        if config.adapter_name == "generic_http":
            if require_order_url and not config.order_url:
                warnings.append("missing_order_url")
                if config.enabled and not config.dry_run:
                    errors.append("missing_order_url")
            if config.order_url and not self._is_http_url(config.order_url):
                errors.append("invalid_order_url")
            if config.reconcile_url and not self._is_http_url(config.reconcile_url):
                errors.append("invalid_reconcile_url")
            if config.cancel_url and not self._is_http_url(config.cancel_url):
                errors.append("invalid_cancel_url")
        if config.enabled and not config.dry_run and config.request_confirmation != config.confirmation_phrase:
            warnings.append("live_order_confirmation_required")

        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "ready_for_live_orders": (
                not errors
                and config.launch_policy == "enabled"
                and config.enabled
                and not config.dry_run
                and config.request_confirmation == config.confirmation_phrase
                and config.adapter_name != "disabled"
            ),
        }

    def validate_order_intent(self, order_intent: dict) -> dict:
        errors: list[str] = []
        symbol = str(order_intent.get("symbol") or "").strip()
        side = str(order_intent.get("side") or "").strip().upper()
        order_type = str(order_intent.get("order_type") or "market").strip().lower()
        quantity = int(_decimal(order_intent.get("quantity")))
        limit_price = _decimal(order_intent.get("limit_price") or order_intent.get("price"))
        idempotency_key = str(order_intent.get("idempotency_key") or "").strip()

        if not symbol:
            errors.append("missing_symbol")
        if side not in SUPPORTED_SIDES:
            errors.append("invalid_side")
        if quantity <= 0:
            errors.append("invalid_quantity")
        if order_type not in SUPPORTED_ORDER_TYPES:
            errors.append("invalid_order_type")
        if order_type == "limit" and limit_price <= 0:
            errors.append("missing_limit_price")
        if not idempotency_key:
            errors.append("missing_idempotency_key")
        return {"valid": not errors, "errors": errors}

    def validate_cancel_intent(self, cancel_intent: dict) -> dict:
        errors: list[str] = []
        if not str(cancel_intent.get("broker_order_id") or cancel_intent.get("client_order_id") or "").strip():
            errors.append("missing_order_identifier")
        if not str(cancel_intent.get("idempotency_key") or "").strip():
            errors.append("missing_idempotency_key")
        return {"valid": not errors, "errors": errors}

    def validate_fill_mapping(self, fill: dict) -> dict:
        errors: list[str] = []
        warnings: list[str] = []
        if not str(fill.get("account_id") or "").strip():
            errors.append("missing_account_id")
        if not str(fill.get("broker_order_id") or fill.get("client_order_id") or "").strip():
            errors.append("missing_order_identifier")
        if not str(fill.get("symbol") or "").strip():
            errors.append("missing_symbol")
        if str(fill.get("side") or "").strip().upper() not in SUPPORTED_SIDES:
            errors.append("invalid_side")
        if int(_decimal(fill.get("quantity"))) <= 0:
            errors.append("invalid_quantity")
        if _decimal(fill.get("price")) <= 0:
            errors.append("invalid_price")
        if not str(fill.get("fill_key") or "").strip():
            warnings.append("missing_fill_key_generated_by_repository")
        return {"valid": not errors, "errors": errors, "warnings": warnings}

    def _adapter(self, adapter_name: str) -> BrokerAdapter:
        factory = self.adapter_registry.get(adapter_name)
        if not factory:
            return DisabledBrokerAdapter()
        return factory()

    def _load_config(self, payload: dict) -> LiveBrokerConfig:
        adapter_name = str(os.getenv("LIVE_BROKER_ADAPTER") or "disabled").strip().lower()
        env_dry_run = _env_bool("LIVE_TRADING_DRY_RUN", True)
        request_dry_run = payload.get("dry_run")
        dry_run = not (env_dry_run is False and request_dry_run is False)
        timeout_seconds = float(_decimal(os.getenv("LIVE_BROKER_HTTP_TIMEOUT_SECONDS"), Decimal("3")))
        return LiveBrokerConfig(
            adapter_name=adapter_name,
            launch_policy=str(os.getenv("LIVE_BROKER_LAUNCH_POLICY") or "disabled").strip().lower(),
            enabled=_env_bool("LIVE_TRADING_ENABLED", False),
            dry_run=dry_run,
            account_id=str(payload.get("account_id") or os.getenv("LIVE_BROKER_ACCOUNT_ID") or "").strip(),
            order_url=str(os.getenv("LIVE_BROKER_HTTP_ORDER_URL") or "").strip(),
            cancel_url=str(os.getenv("LIVE_BROKER_HTTP_CANCEL_URL") or "").strip(),
            reconcile_url=str(os.getenv("LIVE_BROKER_HTTP_RECONCILE_URL") or "").strip(),
            token=str(os.getenv("LIVE_BROKER_HTTP_TOKEN") or "").strip(),
            signing_secret=str(os.getenv("LIVE_BROKER_HTTP_SIGNING_SECRET") or "").strip(),
            timeout_seconds=max(0.5, min(timeout_seconds, 30.0)),
            confirmation_phrase=str(os.getenv("LIVE_TRADING_CONFIRMATION") or LIVE_CONFIRMATION_PHRASE).strip(),
            request_confirmation=str(payload.get("live_order_ack") or "").strip(),
        )

    def _normalize_order_intent(self, payload: dict) -> dict:
        raw = payload.get("order") if isinstance(payload.get("order"), dict) else payload
        side = str(raw.get("side") or "").strip().upper()
        order_type = str(raw.get("order_type") or "market").strip().lower()
        normalized = {
            "symbol": str(raw.get("symbol") or "").strip(),
            "side": side,
            "quantity": int(_decimal(raw.get("quantity"))),
            "order_type": order_type,
            "idempotency_key": str(raw.get("idempotency_key") or "").strip(),
            "client_order_id": str(raw.get("client_order_id") or raw.get("idempotency_key") or "").strip(),
            "strategy_code": str(raw.get("strategy_code") or "").strip(),
            "reason": str(raw.get("reason") or "").strip(),
        }
        price = _decimal(raw.get("limit_price") or raw.get("price"))
        if order_type == "limit" or price > 0:
            normalized["limit_price"] = float(price)
        return normalized

    def _normalize_cancel_intent(self, payload: dict) -> dict:
        raw = payload.get("cancel") if isinstance(payload.get("cancel"), dict) else payload
        return {
            "broker_order_id": str(raw.get("broker_order_id") or raw.get("order_id") or "").strip(),
            "client_order_id": str(raw.get("client_order_id") or "").strip(),
            "symbol": str(raw.get("symbol") or "").strip(),
            "idempotency_key": str(raw.get("idempotency_key") or "").strip(),
            "reason": str(raw.get("reason") or "").strip(),
        }

    def _normalize_fill(self, item: dict, envelope: dict) -> dict:
        account_id = str(item.get("account_id") or envelope.get("account_id") or "").strip()
        quantity = int(_decimal(item.get("quantity") or item.get("filled_quantity") or item.get("filled_qty") or item.get("qty")))
        price = _decimal(item.get("price") or item.get("filled_price") or item.get("trade_price") or item.get("avg_price"))
        fill_key = str(item.get("fill_key") or item.get("fill_id") or item.get("execution_id") or item.get("trade_id") or item.get("id") or "").strip()
        normalized = {
            "account_id": account_id,
            "broker_order_id": str(item.get("broker_order_id") or item.get("order_id") or "").strip(),
            "client_order_id": str(item.get("client_order_id") or item.get("client_id") or "").strip(),
            "symbol": str(item.get("symbol") or item.get("ticker") or "").strip(),
            "side": str(item.get("side") or item.get("direction") or "").strip().upper(),
            "quantity": quantity,
            "price": float(price) if price else None,
            "amount": float(_decimal(item.get("amount"), price * Decimal(quantity) if price and quantity else Decimal("0"))) if (item.get("amount") not in (None, "") or (price and quantity)) else None,
            "fee": float(_decimal(item.get("fee") or item.get("commission"))) if item.get("fee") not in (None, "") or item.get("commission") not in (None, "") else None,
            "currency": str(item.get("currency") or envelope.get("currency") or "CNY").strip() or "CNY",
            "filled_at": str(item.get("filled_at") or item.get("trade_time") or item.get("executed_at") or "").strip(),
            "fill_key": fill_key,
            "source": item.get("source") or envelope.get("source") or "callback",
            "payload": dict(item),
        }
        normalized["field_mapping_validation"] = self.validate_fill_mapping(normalized)
        return normalized

    def _guarded_result(
        self,
        status: str,
        reason: str,
        config: LiveBrokerConfig,
        audit: dict,
        *,
        order_validation: dict | None = None,
        config_validation: dict | None = None,
    ) -> dict:
        return {
            "status": status,
            "reason": reason,
            "mode": "live",
            "adapter": config.adapter_name,
            "config": config.public_dict(),
            "order_validation": order_validation,
            "config_validation": config_validation,
            "audit": {**audit, "result": status, "reason": reason},
        }

    def _normalize_reconciliation(self, adapter_result: dict) -> dict:
        broker_response = adapter_result.get("broker_response") if isinstance(adapter_result.get("broker_response"), dict) else {}
        raw_differences = adapter_result.get("differences") or broker_response.get("differences") or []
        if isinstance(raw_differences, dict):
            raw_differences = [raw_differences]
        differences = [self._normalize_reconciliation_difference(item) for item in raw_differences if isinstance(item, dict)]
        broker_orders = broker_response.get("orders") if isinstance(broker_response.get("orders"), list) else adapter_result.get("orders")
        local_orders = adapter_result.get("local_orders")
        return {
            "schema_version": "live-broker-reconciliation/v1",
            "status": "differences_found" if differences else "matched",
            "differences_count": len(differences),
            "differences": differences,
            "broker_orders_count": len(broker_orders) if isinstance(broker_orders, list) else None,
            "local_orders_count": len(local_orders) if isinstance(local_orders, list) else None,
        }

    def _normalize_reconciliation_difference(self, item: dict) -> dict:
        diff_type = str(item.get("type") or item.get("difference_type") or item.get("field") or "unknown").strip() or "unknown"
        expected = item.get("expected") if "expected" in item else item.get("local")
        actual = item.get("actual") if "actual" in item else item.get("broker")
        severity = str(item.get("severity") or ("error" if diff_type in {"missing_broker_order", "missing_local_order", "quantity", "price"} else "warning")).strip()
        return {
            "type": diff_type,
            "severity": severity,
            "broker_order_id": str(item.get("broker_order_id") or item.get("order_id") or "").strip(),
            "client_order_id": str(item.get("client_order_id") or "").strip(),
            "symbol": str(item.get("symbol") or "").strip(),
            "field": str(item.get("field") or "").strip(),
            "expected": expected,
            "actual": actual,
            "message": str(item.get("message") or item.get("reason") or "").strip(),
        }

    def _audit_base(self, tenant_id: int, action: str, config: LiveBrokerConfig, order_intent: dict) -> dict:
        return {
            "tenant_id": int(tenant_id or 0),
            "action": action,
            "adapter": config.adapter_name,
            "account_id": config.account_id,
            "dry_run": config.dry_run,
            "symbol": order_intent.get("symbol") or "",
            "side": order_intent.get("side") or "",
            "quantity": order_intent.get("quantity") or 0,
            "idempotency_key": order_intent.get("idempotency_key") or "",
        }

    def _record_request(self, tenant_id: int, action: str, config: LiveBrokerConfig, intent: dict, result: dict) -> None:
        broker_result = result.get("broker_result") if isinstance(result.get("broker_result"), dict) else {}
        broker_response = broker_result.get("broker_response") if isinstance(broker_result.get("broker_response"), dict) else {}
        live_broker_repo.record_request(
            tenant_id,
            action=action,
            adapter=config.adapter_name,
            account_id=config.account_id,
            idempotency_key=str(intent.get("idempotency_key") or ""),
            payload=intent,
            status=str(result.get("status") or ""),
            reason=str(result.get("reason") or ""),
            response=result,
            broker_order_id=str(broker_response.get("broker_order_id") or broker_result.get("broker_order_id") or intent.get("broker_order_id") or ""),
            client_order_id=str(intent.get("client_order_id") or ""),
        )

    def _stored_result(self, status: str, previous: dict, config: LiveBrokerConfig, intent: dict, audit: dict) -> dict:
        return {
            "status": status,
            "reason": "idempotency_key_already_processed",
            "mode": "live",
            "adapter": config.adapter_name,
            "order_intent": intent,
            "config": config.public_dict(),
            "stored_request": previous,
            "idempotency": {
                "state": "replay",
                "idempotency_key": intent.get("idempotency_key") or "",
                "existing_request_hash": previous.get("request_hash") or "",
                "incoming_request_hash": live_broker_repo.request_hash(intent),
                "existing_status": previous.get("status") or "",
            },
            "audit": {**audit, "result": status},
        }

    def _idempotency_conflict_result(self, previous: dict, config: LiveBrokerConfig, intent: dict, audit: dict) -> dict:
        return {
            "status": "rejected",
            "reason": "idempotency_key_conflict",
            "mode": "live",
            "adapter": config.adapter_name,
            "order_intent": intent,
            "config": config.public_dict(),
            "idempotency": {
                "state": "conflict",
                "idempotency_key": intent.get("idempotency_key") or "",
                "existing_request_hash": previous.get("request_hash") or "",
                "incoming_request_hash": live_broker_repo.request_hash(intent),
                "existing_status": previous.get("status") or "",
            },
            "audit": {**audit, "result": "rejected", "reason": "idempotency_key_conflict"},
        }

    def _rate_limited(self, tenant_id: int, action: str) -> bool:
        try:
            limit = int(os.getenv("LIVE_BROKER_RATE_LIMIT_PER_MIN", "30") or 30)
        except ValueError:
            limit = 30
        if limit <= 0:
            return False
        return live_broker_repo.count_recent_requests(tenant_id, action=action, since_seconds=60) >= limit

    def _is_http_url(self, value: str) -> bool:
        return value.startswith("https://") or value.startswith("http://")


live_broker_service = LiveBrokerService()
