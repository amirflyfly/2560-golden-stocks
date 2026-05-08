"""External push adapters for alert notifications."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import re
import smtplib
import socket
import time
from email.message import EmailMessage
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.repositories import external_push_delivery_repo, settings_repo


SUPPORTED_PUSH_TYPES = {"dingtalk", "wecom", "email", "webhook"}
SENSITIVE_CONFIG_KEYS = {
    "bearer_token",
    "password",
    "secret",
    "smtp_password",
    "token",
    "webhook_url",
}
FORBIDDEN_HEADER_NAMES = {
    "connection",
    "content-length",
    "cookie",
    "host",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9-]+$")


class ExternalPushError(ValueError):
    """Raised when an external push configuration is unsafe or invalid."""


class ExternalPushService:
    """Dispatches alert notifications to configured external channels."""

    def __init__(self, *, http_post=None, smtp_factory=None, smtp_ssl_factory=None):
        self.http_post = http_post
        self.smtp_factory = smtp_factory or smtplib.SMTP
        self.smtp_ssl_factory = smtp_ssl_factory or smtplib.SMTP_SSL
        self._custom_transport = http_post is not None or smtp_factory is not None or smtp_ssl_factory is not None

    def dispatch_for_alert(
        self,
        *,
        tenant_id: int,
        user_id: int | None,
        alert_rule: dict,
        notification: dict,
    ) -> list[dict]:
        selected = _selected_channels(alert_rule)
        if not _uses_external_channels(selected):
            return []

        configs = settings_repo.list_external_push_channels(
            tenant_id,
            user_id,
            include_secrets=True,
        )
        candidates = [config for config in configs if self._matches_selected_channel(config, selected)]
        if not candidates:
            return [
                {
                    "ok": False,
                    "status": "skipped",
                    "channel_id": "",
                    "channel_type": "",
                    "message": "no enabled external push channel matched alert channels",
                }
            ]

        results = []
        for config in candidates:
            if self._custom_transport:
                results.append(self.dispatch(config, notification))
            else:
                results.append(self.enqueue_dispatch(tenant_id, user_id, config, notification))
        return results

    def enqueue_dispatch(
        self,
        tenant_id: int,
        user_id: int | None,
        config: dict,
        notification: dict,
        *,
        delivery_key: str | None = None,
        retry_count: int = 0,
    ) -> dict:
        from backend.infrastructure.tasks.queue import enqueue_task

        channel_id = str(config.get("id") or "")
        channel_type = _normalize_push_type(config.get("type"))
        payload = {
            "tenant_id": int(tenant_id or 0),
            "user_id": int(user_id or 0),
            "channel_id": channel_id,
            "channel_type": channel_type,
            "notification": notification,
        }
        dedupe = str(delivery_key or "").strip() or _delivery_dedupe_key(tenant_id, user_id, channel_id, notification)
        delivery = external_push_delivery_repo.record_queued_delivery(
            tenant_id=int(tenant_id or 0),
            user_id=user_id,
            delivery_key=dedupe,
            channel_id=channel_id,
            channel_type=channel_type,
            notification=notification,
            retry_count=retry_count,
        )
        payload["delivery_id"] = delivery.get("id")
        payload["delivery_key"] = dedupe
        task = enqueue_task(
            "external_push.dispatch",
            dispatch_external_push_task,
            payload,
            tenant_id=int(tenant_id or 0),
            payload=payload,
            idempotency_key=dedupe,
            max_retries=2,
        )
        payload["task_id"] = str(task.get("id") or "")
        payload["retry_count"] = max(int(retry_count or 0), int(task.get("retry_count") or 0))
        external_push_delivery_repo.update_delivery(
            delivery.get("id"),
            tenant_id=int(tenant_id or 0),
            delivery_key=dedupe,
            task_id=payload["task_id"],
            retry_count=payload["retry_count"],
        )
        return {
            "ok": True,
            "status": "queued",
            "channel_id": channel_id,
            "channel_type": channel_type,
            "task_id": task.get("id"),
            "message": "external push delivery queued",
        }

    def retry_delivery(self, tenant_id: int, delivery_id: int) -> dict:
        delivery = external_push_delivery_repo.get_delivery(delivery_id)
        if not delivery or int(delivery.get("tenant_id") or 0) != int(tenant_id or 0):
            raise ExternalPushError("external push delivery not found")
        if str(delivery.get("status") or "") not in {"failed", "skipped"}:
            raise ExternalPushError("only failed or skipped deliveries can be retried")
        notification = delivery.get("notification_payload") if isinstance(delivery.get("notification_payload"), dict) else {}
        if not notification:
            notification = {"title": delivery.get("notification_summary", {}).get("title") or "External push retry"}
        configs = settings_repo.list_external_push_channels(
            int(tenant_id or 0),
            int(delivery.get("user_id") or 0) or None,
            include_secrets=True,
        )
        config = next((item for item in configs if str(item.get("id") or "") == str(delivery.get("channel_id") or "")), None)
        if config is None:
            external_push_delivery_repo.update_delivery(
                delivery_id,
                tenant_id=int(tenant_id or 0),
                delivery_key=str(delivery.get("delivery_key") or ""),
                status="skipped",
                last_error="external push channel not found for retry",
            )
            raise ExternalPushError("external push channel not found for retry")
        return self.enqueue_dispatch(
            int(tenant_id or 0),
            int(delivery.get("user_id") or 0) or None,
            config,
            notification,
            delivery_key=str(delivery.get("delivery_key") or ""),
            retry_count=int(delivery.get("retry_count") or 0) + 1,
        )

    def dispatch(self, config: dict, notification: dict) -> dict:
        channel_id = str(config.get("id") or "")
        channel_type = _normalize_push_type(config.get("type"))
        result = {
            "ok": False,
            "status": "failed",
            "channel_id": channel_id,
            "channel_type": channel_type,
        }
        if not config.get("enabled", True):
            result.update({"status": "skipped", "message": "channel disabled"})
            return result
        try:
            if channel_type == "dingtalk":
                delivery = self._send_dingtalk(config, notification)
            elif channel_type == "wecom":
                delivery = self._send_wecom(config, notification)
            elif channel_type == "email":
                delivery = self._send_email(config, notification)
            elif channel_type == "webhook":
                delivery = self._send_webhook(config, notification)
            else:
                raise ExternalPushError("unsupported external push channel type")
        except Exception as exc:
            result["message"] = _safe_error_message(exc)
            return result
        result.update(delivery)
        return result

    def _matches_selected_channel(self, config: dict, selected: set[str]) -> bool:
        if not config.get("enabled", True):
            return False
        channel_id = str(config.get("id") or "").strip().lower()
        channel_type = _normalize_push_type(config.get("type"))
        return (
            "external" in selected
            or channel_type in selected
            or channel_id in selected
            or f"external:{channel_id}" in selected
            or f"{channel_type}:{channel_id}" in selected
        )

    def _send_dingtalk(self, config: dict, notification: dict) -> dict:
        channel_config = _config(config)
        webhook_url = _signed_dingtalk_url(
            _require_public_https_url(channel_config.get("webhook_url")),
            str(channel_config.get("secret") or "").strip(),
        )
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": _trim(str(notification.get("title") or "Alert triggered"), 64),
                "text": _markdown_message(notification),
            },
        }
        return self._post_json(webhook_url, payload, headers={})

    def _send_wecom(self, config: dict, notification: dict) -> dict:
        channel_config = _config(config)
        webhook_url = _require_public_https_url(channel_config.get("webhook_url"))
        payload = {"msgtype": "markdown", "markdown": {"content": _markdown_message(notification)}}
        return self._post_json(webhook_url, payload, headers={})

    def _send_webhook(self, config: dict, notification: dict) -> dict:
        channel_config = _config(config)
        webhook_url = _require_public_https_url(channel_config.get("webhook_url"))
        headers = _safe_headers(channel_config.get("headers"))
        bearer_token = str(channel_config.get("bearer_token") or channel_config.get("token") or "").strip()
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        payload = {
            "event": "alert_triggered",
            "schema_version": "external-push/v1",
            "notification": notification,
        }
        return self._post_json(webhook_url, payload, headers=headers)

    def _send_email(self, config: dict, notification: dict) -> dict:
        channel_config = _config(config)
        host = _require_smtp_host(channel_config.get("host"))
        port = _safe_port(channel_config.get("port"), default=465 if _bool(channel_config.get("use_ssl")) else 587)
        from_email = _require_email(channel_config.get("from_email") or channel_config.get("sender"))
        recipients = _recipient_list(channel_config.get("to_emails") or channel_config.get("recipients"))
        if not recipients:
            raise ExternalPushError("email channel requires at least one recipient")

        message = EmailMessage()
        message["Subject"] = _trim(str(notification.get("title") or "Alert triggered"), 120)
        message["From"] = from_email
        message["To"] = ", ".join(recipients)
        message.set_content(_plain_text_message(notification))

        timeout = _safe_timeout(channel_config.get("timeout_seconds"))
        use_ssl = _bool(channel_config.get("use_ssl"))
        use_tls = True if channel_config.get("use_tls") is None else _bool(channel_config.get("use_tls"))
        smtp_cls = self.smtp_ssl_factory if use_ssl else self.smtp_factory
        with smtp_cls(host, port, timeout=timeout) as smtp:
            if use_tls and not use_ssl:
                smtp.starttls()
            username = str(channel_config.get("username") or "").strip()
            password = str(channel_config.get("password") or channel_config.get("smtp_password") or "")
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return {"ok": True, "status": "sent", "message": "email sent", "status_code": None}

    def _post_json(self, url: str, payload: dict, *, headers: dict[str, str]) -> dict:
        post = self.http_post
        if post is None:
            import requests

            post = requests.post
        request_headers = {
            "Content-Type": "application/json",
            "User-Agent": "2560-strategy-alerts/1.0",
        }
        request_headers.update(headers)
        response = post(url, json=payload, headers=request_headers, timeout=5)
        status_code = int(getattr(response, "status_code", 0) or 0)
        ok = 200 <= status_code < 300
        return {
            "ok": ok,
            "status": "sent" if ok else "failed",
            "message": "webhook accepted" if ok else _trim(str(getattr(response, "text", "") or "webhook rejected"), 160),
            "status_code": status_code,
        }


def dispatch_external_push_task(payload: dict) -> dict:
    tenant_id = int(payload.get("tenant_id") or 0)
    user_id = int(payload.get("user_id") or 0) or None
    channel_id = str(payload.get("channel_id") or "")
    delivery_id = int(payload.get("delivery_id") or 0) or None
    delivery_key = str(payload.get("delivery_key") or "")
    notification = payload.get("notification") if isinstance(payload.get("notification"), dict) else {}
    configs = settings_repo.list_external_push_channels(tenant_id, user_id, include_secrets=True)
    config = next((item for item in configs if str(item.get("id") or "") == channel_id), None)
    if config is None:
        result = {
            "ok": False,
            "status": "skipped",
            "channel_id": channel_id,
            "channel_type": str(payload.get("channel_type") or ""),
            "message": "external push channel not found",
        }
        _record_delivery_result(delivery_id, tenant_id, delivery_key, result, payload)
        return result
    result = ExternalPushService().dispatch(config, notification)
    _record_delivery_result(delivery_id, tenant_id, delivery_key, result, payload)
    return result


def public_external_push_channel(config: dict) -> dict:
    item = dict(config or {})
    item["config"] = redact_external_push_config(item.get("config"))
    return item


def _record_delivery_result(
    delivery_id: int | None,
    tenant_id: int,
    delivery_key: str,
    result: dict,
    payload: dict,
) -> None:
    status = str(result.get("status") or ("sent" if result.get("ok") else "failed")).strip().lower()
    last_error = "" if status in {"sent", "queued"} else str(result.get("message") or "")
    task_id = str(payload.get("task_id") or "")
    external_push_delivery_repo.update_delivery(
        delivery_id,
        tenant_id=tenant_id,
        delivery_key=delivery_key,
        status=status,
        task_id=task_id if task_id else None,
        retry_count=int(payload.get("retry_count") or 0),
        last_error=last_error,
    )
    if status == "failed":
        settings_repo.upsert_notification(
            tenant_id,
            int(payload.get("user_id") or 0) or None,
            {
                "type": "external_push_delivery_failed",
                "channel": "in_app",
                "severity": "error",
                "title": "External push delivery failed",
                "body": last_error or "External push delivery failed",
                "source": "external_push.dispatch",
                "metadata": {
                    "delivery_id": delivery_id,
                    "delivery_key": delivery_key,
                    "channel_id": result.get("channel_id") or payload.get("channel_id") or "",
                    "channel_type": result.get("channel_type") or payload.get("channel_type") or "",
                    "task_id": task_id,
                },
                "dedupe_key": f"external_push_delivery_failed:{delivery_key}",
            },
        )


def redact_external_push_config(config: Any) -> dict:
    if not isinstance(config, dict):
        return {}
    redacted = {}
    for key, value in config.items():
        normalized = str(key or "").strip().lower()
        if normalized in SENSITIVE_CONFIG_KEYS or any(part in normalized for part in ("secret", "token", "password")):
            redacted[key] = "***configured***" if value else ""
        elif isinstance(value, dict):
            redacted[key] = redact_external_push_config(value)
        else:
            redacted[key] = value
    return redacted


def _selected_channels(alert_rule: dict) -> set[str]:
    channels = alert_rule.get("channels")
    if not isinstance(channels, list) or not channels:
        return {"in_app"}
    return {str(channel).strip().lower() for channel in channels if str(channel).strip()}


def _uses_external_channels(channels: set[str]) -> bool:
    return any(channel != "in_app" for channel in channels)


def _normalize_push_type(value: Any) -> str:
    channel_type = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "ding-talk": "dingtalk",
        "dingding": "dingtalk",
        "enterprise-wechat": "wecom",
        "wechat-work": "wecom",
        "weixin-work": "wecom",
        "smtp": "email",
        "smtp-email": "email",
        "generic-webhook": "webhook",
    }
    return aliases.get(channel_type, channel_type)


def _config(config: dict) -> dict:
    value = config.get("config")
    return dict(value) if isinstance(value, dict) else {}


def _require_public_https_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ExternalPushError("webhook_url is required")
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        raise ExternalPushError("webhook_url must use https")
    if parsed.username or parsed.password:
        raise ExternalPushError("webhook_url must not include credentials")
    host = parsed.hostname
    if not host:
        raise ExternalPushError("webhook_url host is required")
    _validate_public_host(host, parsed.port or 443)
    return raw


def _validate_public_host(host: str, port: int) -> None:
    normalized = host.strip().lower().rstrip(".")
    if normalized in {"localhost", "0.0.0.0"} or normalized.endswith((".localhost", ".local")):
        raise ExternalPushError("webhook_url host must be public")
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        try:
            resolved = socket.getaddrinfo(normalized, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ExternalPushError("webhook_url host could not be resolved") from exc
        addresses = {item[4][0].split("%", 1)[0] for item in resolved if item[4]}
        if not addresses:
            raise ExternalPushError("webhook_url host could not be resolved")
        for candidate in addresses:
            _require_global_ip(candidate)
        return
    _require_global_ip(str(address))


def _require_global_ip(value: str) -> None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ExternalPushError("webhook_url host resolved to an invalid address") from exc
    if not address.is_global:
        raise ExternalPushError("webhook_url host must resolve to public IP addresses")


def _signed_dingtalk_url(webhook_url: str, secret: str) -> str:
    if not secret:
        return webhook_url
    timestamp = str(int(time.time() * 1000))
    digest = hmac.new(secret.encode("utf-8"), f"{timestamp}\n{secret}".encode("utf-8"), hashlib.sha256).digest()
    sign = base64.b64encode(digest).decode("utf-8")
    parsed = urlparse(webhook_url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.extend([("timestamp", timestamp), ("sign", sign)])
    return urlunparse(parsed._replace(query=urlencode(query)))


def _safe_headers(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    headers = {}
    for key, raw_value in value.items():
        name = str(key or "").strip()
        if not name or not HEADER_NAME_RE.match(name):
            raise ExternalPushError("webhook header names must be HTTP token names")
        if name.lower() in FORBIDDEN_HEADER_NAMES:
            raise ExternalPushError(f"webhook header is not allowed: {name}")
        header_value = str(raw_value or "")
        if "\r" in header_value or "\n" in header_value:
            raise ExternalPushError("webhook header values must not contain newlines")
        headers[name] = header_value
    return headers


def _require_smtp_host(value: Any) -> str:
    host = str(value or "").strip()
    if not host or "\r" in host or "\n" in host:
        raise ExternalPushError("smtp host is required")
    return host


def _safe_port(value: Any, *, default: int) -> int:
    try:
        port = int(value or default)
    except (TypeError, ValueError) as exc:
        raise ExternalPushError("port must be an integer") from exc
    if port < 1 or port > 65535:
        raise ExternalPushError("port out of range")
    return port


def _safe_timeout(value: Any) -> int:
    try:
        timeout = int(value or 10)
    except (TypeError, ValueError) as exc:
        raise ExternalPushError("timeout_seconds must be an integer") from exc
    return max(1, min(timeout, 30))


def _require_email(value: Any) -> str:
    email = str(value or "").strip()
    if "\r" in email or "\n" in email or "@" not in email:
        raise ExternalPushError("valid email address is required")
    return email


def _recipient_list(value: Any) -> list[str]:
    raw_values = value if isinstance(value, list) else [value]
    recipients = []
    for item in raw_values:
        if item in (None, ""):
            continue
        recipients.append(_require_email(item))
    return recipients


def _markdown_message(notification: dict) -> str:
    entity = notification.get("entity") if isinstance(notification.get("entity"), dict) else {}
    match = notification.get("match") if isinstance(notification.get("match"), dict) else {}
    lines = [
        f"### {_trim(str(notification.get('title') or 'Alert triggered'), 120)}",
        "",
        str(notification.get("body") or ""),
        "",
        f"- Rule: {notification.get('rule_name') or notification.get('rule_id') or '-'}",
        f"- Scope: {notification.get('scope') or '-'}",
        f"- Entity: {entity.get('symbol') or entity.get('id') or '-'}",
        f"- Match: {match.get('field') or match.get('metric') or '-'}",
    ]
    return "\n".join(lines)


def _plain_text_message(notification: dict) -> str:
    entity = notification.get("entity") if isinstance(notification.get("entity"), dict) else {}
    match = notification.get("match") if isinstance(notification.get("match"), dict) else {}
    return "\n".join(
        [
            str(notification.get("title") or "Alert triggered"),
            "",
            str(notification.get("body") or ""),
            "",
            f"Rule: {notification.get('rule_name') or notification.get('rule_id') or '-'}",
            f"Scope: {notification.get('scope') or '-'}",
            f"Entity: {entity.get('symbol') or entity.get('id') or '-'}",
            f"Match: {match.get('field') or match.get('metric') or '-'}",
        ]
    )


def _safe_error_message(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    return _trim(message.replace("\r", " ").replace("\n", " "), 200)


def _trim(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _delivery_dedupe_key(tenant_id: int, user_id: int | None, channel_id: str, notification: dict) -> str:
    raw = {
        "tenant_id": int(tenant_id or 0),
        "user_id": int(user_id or 0),
        "channel_id": channel_id,
        "dedupe_key": notification.get("dedupe_key"),
        "rule_id": notification.get("rule_id"),
        "entity": notification.get("entity"),
        "match": notification.get("match"),
    }
    digest = hashlib.sha256(str(raw).encode("utf-8")).hexdigest()[:24]
    return f"external_push.dispatch:{digest}"
