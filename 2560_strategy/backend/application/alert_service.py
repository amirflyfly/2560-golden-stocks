"""Server-side alert rule evaluation and in-app notification delivery."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from backend.infrastructure.tasks.queue import list_tasks
from backend.repositories import picks_repo, settings_repo


class AlertEvaluationService:
    """Evaluates persisted alert rules against server-side data sources."""

    SCAN_METRICS = {"score_gte", "confidence_lte", "risk_eq", "quality_eq", "signal_state_transition", "signal_transition"}
    PICK_METRICS = {"watching_high_risk", "drawdown_abs_gte", "holding_days_gte", "status_eq"}
    GENERIC_TARGETS = {"", "all", "picks", "pick", "scan_results", "scans", "scan", "symbol"}

    def evaluate_all(
        self,
        *,
        tenant_id: int | None = None,
        user_id: int | None = None,
        limit_per_rule: int = 50,
        source: str = "api",
    ) -> dict:
        evaluated_at = self._now()
        rules = settings_repo.list_all_alert_rules(tenant_id=tenant_id, user_id=user_id)
        result = {
            "schema_version": "alert-evaluation/v1",
            "evaluated_at": evaluated_at,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "source": source,
            "rules_evaluated": 0,
            "rules_skipped": 0,
            "matches": 0,
            "notifications_created": 0,
            "notifications": [],
            "by_scope": {
                "picks": {"rules": 0, "matches": 0, "notifications": 0},
                "scan_results": {"rules": 0, "matches": 0, "notifications": 0},
            },
            "errors": [],
        }

        for record in rules:
            alert_rule = dict(record.get("item") or {})
            if not alert_rule.get("enabled", True):
                result["rules_skipped"] += 1
                continue

            record_tenant_id = int(record["tenant_id"])
            record_user_id = int(record.get("user_id") or 0)
            scope = self._rule_scope(alert_rule)
            if scope not in result["by_scope"]:
                result["rules_skipped"] += 1
                result["errors"].append(
                    {
                        "rule_id": alert_rule.get("id"),
                        "scope": scope,
                        "message": "unsupported alert scope",
                    }
                )
                continue

            result["rules_evaluated"] += 1
            result["by_scope"][scope]["rules"] += 1
            rule_matches = self._evaluate_rule(
                tenant_id=record_tenant_id,
                user_id=record_user_id,
                alert_rule=alert_rule,
                scope=scope,
                limit_per_rule=limit_per_rule,
            )
            if rule_matches["errors"]:
                result["errors"].extend(rule_matches["errors"])

            match_count = len(rule_matches["matches"])
            result["matches"] += match_count
            result["by_scope"][scope]["matches"] += match_count
            notifications = rule_matches["notifications"]
            result["notifications_created"] += len(notifications)
            result["by_scope"][scope]["notifications"] += len(notifications)
            result["notifications"].extend(notifications[:50])
            settings_repo.update_alert_rule_trigger_state(
                record_tenant_id,
                record_user_id,
                str(alert_rule.get("id") or ""),
                evaluated_at=evaluated_at,
                triggered_at=evaluated_at if match_count else None,
                match_count=match_count,
            )

        result["notifications"] = result["notifications"][:50]
        return result

    def evaluate_for_user(self, tenant_id: int, user_id: int | None, *, limit_per_rule: int = 50) -> dict:
        return self.evaluate_all(
            tenant_id=int(tenant_id),
            user_id=int(user_id or 0),
            limit_per_rule=limit_per_rule,
            source="api",
        )

    def _evaluate_rule(
        self,
        *,
        tenant_id: int,
        user_id: int,
        alert_rule: dict,
        scope: str,
        limit_per_rule: int,
    ) -> dict:
        matches = []
        notifications = []
        errors = []
        candidates = self._picks_candidates(tenant_id, alert_rule) if scope == "picks" else self._scan_candidates(tenant_id)
        for candidate in candidates:
            if len(matches) >= max(1, int(limit_per_rule or 50)):
                break
            if not self._target_matches(alert_rule, candidate):
                continue
            matched, match_payload = self._matches_rule(alert_rule, candidate, scope)
            if not matched:
                continue
            matches.append(match_payload)
            if not self._uses_in_app_channel(alert_rule):
                continue
            notification = settings_repo.upsert_notification(
                tenant_id,
                user_id,
                self._notification_payload(alert_rule, candidate, scope, match_payload),
            )
            notifications.append(notification)
        return {"matches": matches, "notifications": notifications, "errors": errors}

    def _picks_candidates(self, tenant_id: int, alert_rule: dict) -> list[dict]:
        target = self._target(alert_rule)
        where = ["COALESCE(archived,0)=0"]
        args: list[Any] = []
        if target and target.lower() not in self.GENERIC_TARGETS:
            where.append("code=?")
            args.append(target)
        rows = picks_repo.list_picks(
            "WHERE " + " AND ".join(where),
            args,
            limit=1000,
            tenant_id=tenant_id,
        )
        return [self._pick_candidate(row) for row in rows]

    def _scan_candidates(self, tenant_id: int) -> list[dict]:
        candidates = []
        for task in list_tasks(limit=300):
            if task.get("tenant_id") != tenant_id:
                continue
            if task.get("status") != "completed":
                continue
            task_name = str(task.get("name") or "")
            if not task_name.startswith("scan."):
                continue
            result = task.get("result") if isinstance(task.get("result"), dict) else {}
            payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
            market_data = result.get("market_data") if isinstance(result.get("market_data"), dict) else {}
            if not market_data:
                market_data = payload.get("market_data") if isinstance(payload.get("market_data"), dict) else {}
            items = (
                market_data.get("sample_symbols")
                or result.get("items")
                or result.get("sample_symbols")
                or []
            )
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                candidate = dict(item)
                symbol = self._symbol(candidate) or f"row-{index}"
                candidate.setdefault("data_quality", market_data.get("data_quality"))
                candidate.setdefault("fallback_used", market_data.get("fallback_used"))
                candidate["_entity_id"] = f"{task.get('id')}:{symbol}"
                candidate["_source_id"] = task.get("id")
                candidate["_source_name"] = task_name
                candidate["_market_data"] = {
                    key: value for key, value in market_data.items() if key != "sample_symbols"
                }
                candidates.append(candidate)
        return candidates

    def _pick_candidate(self, row: dict) -> dict:
        return {
            "id": row.get("id"),
            "_entity_id": str(row.get("id") or row.get("code") or ""),
            "symbol": row.get("code"),
            "stock_name": row.get("name"),
            "trade_date": row.get("pick_date"),
            "source": row.get("source"),
            "strategy_code": row.get("strategy_name"),
            "status": row.get("review_status") or "accepted",
            "review_status": row.get("review_status") or "accepted",
            "deal_status": row.get("deal_status") or "",
            "risk_level": row.get("result_grade") or "",
            "result_grade": row.get("result_grade") or "",
            "watch_flag": self._bool(row.get("watch_flag")),
            "return_pct": row.get("return_pct"),
            "max_return_pct": row.get("max_return_pct"),
            "drawdown_pct": row.get("drawdown_pct"),
            "holding_days": row.get("holding_days"),
            "data_quality": row.get("data_quality") or "",
            "market_data_source": row.get("market_data_source") or "",
            "fallback_used": self._bool(row.get("fallback_used")),
            "created_at": row.get("created_at"),
        }

    def _matches_rule(self, alert_rule: dict, candidate: dict, scope: str) -> tuple[bool, dict]:
        rule = self._rule_body(alert_rule)
        metric = str(rule.get("metric") or "").strip()
        if metric:
            return self._matches_metric(metric, rule, candidate, scope)

        field = str(rule.get("field") or rule.get("key") or "").strip()
        operator = str(rule.get("operator") or rule.get("op") or "==").strip() or "=="
        expected = rule.get("value", rule.get("threshold"))
        actual = self._field_value(candidate, field)
        matched = self._compare(actual, operator, expected)
        return matched, self._match_payload(
            candidate,
            metric="generic",
            field=field,
            operator=operator,
            expected=expected,
            actual=actual,
        )

    def _matches_metric(self, metric: str, rule: dict, candidate: dict, scope: str) -> tuple[bool, dict]:
        if scope == "picks":
            if metric == "watching_high_risk":
                actual = {
                    "watch_flag": self._bool(candidate.get("watch_flag")),
                    "status": candidate.get("status"),
                    "risk_level": candidate.get("risk_level"),
                }
                matched = (actual["watch_flag"] or actual["status"] == "watching") and str(actual["risk_level"]).lower() == "high"
                return matched, self._match_payload(candidate, metric=metric, field="risk_level", operator="==", expected="high", actual=actual)
            if metric == "drawdown_abs_gte":
                actual = abs(self._float(candidate.get("drawdown_pct")) or 0)
                expected = self._float(rule.get("threshold")) or 0
                return actual >= expected, self._match_payload(candidate, metric=metric, field="drawdown_pct", operator="abs>=", expected=expected, actual=actual)
            if metric == "holding_days_gte":
                actual = self._float(candidate.get("holding_days")) or 0
                expected = self._float(rule.get("threshold")) or 0
                return actual >= expected, self._match_payload(candidate, metric=metric, field="holding_days", operator=">=", expected=expected, actual=actual)
            if metric == "status_eq":
                actual = str(candidate.get("status") or "accepted")
                expected = str(rule.get("status") or "")
                return actual == expected, self._match_payload(candidate, metric=metric, field="status", operator="==", expected=expected, actual=actual)

        if scope == "scan_results":
            explanation = candidate.get("explanation") if isinstance(candidate.get("explanation"), dict) else {}
            if metric == "score_gte":
                actual = self._float(explanation.get("score")) or 0
                expected = self._float(rule.get("threshold")) or 0
                return actual >= expected, self._match_payload(candidate, metric=metric, field="explanation.score", operator=">=", expected=expected, actual=actual)
            if metric == "confidence_lte":
                actual = self._float(explanation.get("confidence")) or 0
                expected = self._float(rule.get("threshold")) or 0
                return actual <= expected, self._match_payload(candidate, metric=metric, field="explanation.confidence", operator="<=", expected=expected, actual=actual)
            if metric == "risk_eq":
                actual = str(explanation.get("risk_level") or "unknown")
                expected = str(rule.get("risk_level") or "")
                return actual == expected, self._match_payload(candidate, metric=metric, field="explanation.risk_level", operator="==", expected=expected, actual=actual)
            if metric == "quality_eq":
                actual = str(candidate.get("data_quality") or candidate.get("_market_data", {}).get("data_quality") or "unknown")
                expected = str(rule.get("quality") or "")
                return actual == expected, self._match_payload(candidate, metric=metric, field="data_quality", operator="==", expected=expected, actual=actual)
            if metric in {"signal_state_transition", "signal_transition"}:
                actual = {
                    "from": str(
                        candidate.get("previous_signal_subtype")
                        or candidate.get("from_signal_subtype")
                        or candidate.get("previous_signal")
                        or ""
                    ).strip(),
                    "to": str(candidate.get("signal_subtype") or candidate.get("to_signal_subtype") or candidate.get("signal") or "").strip(),
                    "strategy_code": str(candidate.get("strategy_code") or "").strip(),
                }
                expected = {
                    "from": str(rule.get("from") or rule.get("from_subtype") or "pullback_setup").strip(),
                    "to": str(rule.get("to") or rule.get("to_subtype") or "breakout_confirmed").strip(),
                    "strategy_code": str(rule.get("strategy_code") or "").strip(),
                }
                strategy_ok = not expected["strategy_code"] or actual["strategy_code"] == expected["strategy_code"]
                matched = strategy_ok and actual["from"] == expected["from"] and actual["to"] == expected["to"]
                return matched, self._match_payload(candidate, metric=metric, field="signal_subtype", operator="transition", expected=expected, actual=actual)

        return False, self._match_payload(candidate, metric=metric, field="", operator="", expected=None, actual=None)

    def _notification_payload(self, alert_rule: dict, candidate: dict, scope: str, match_payload: dict) -> dict:
        rule_id = str(alert_rule.get("id") or "")
        rule_name = str(alert_rule.get("name") or "Alert")
        entity = self._entity_payload(candidate, scope)
        dedupe_key = self._dedupe_key(rule_id, scope, entity.get("id") or entity.get("symbol"), match_payload.get("metric"))
        actual = match_payload.get("actual")
        body = f"{scope} entity {entity.get('symbol') or entity.get('id')} matched {match_payload.get('field')}={actual}"
        return {
            "type": "alert_triggered",
            "channel": "in_app",
            "severity": self._severity(alert_rule),
            "title": f"{rule_name}: alert matched",
            "body": body,
            "rule_id": rule_id,
            "rule_name": rule_name,
            "scope": scope,
            "source": scope,
            "entity": entity,
            "match": match_payload,
            "metadata": {
                "channels": self._channels(alert_rule),
                "rule_scope": alert_rule.get("scope"),
                "target": alert_rule.get("target"),
                "created_by": "alert_evaluation_service",
            },
            "dedupe_key": dedupe_key,
        }

    def _match_payload(
        self,
        candidate: dict,
        *,
        metric: str,
        field: str,
        operator: str,
        expected: Any,
        actual: Any,
    ) -> dict:
        return {
            "metric": metric,
            "field": field,
            "operator": operator,
            "expected": expected,
            "actual": actual,
            "entity_id": candidate.get("_entity_id") or candidate.get("id") or self._symbol(candidate),
            "symbol": self._symbol(candidate),
            "matched_at": self._now(),
        }

    def _entity_payload(self, candidate: dict, scope: str) -> dict:
        if scope == "scan_results":
            return {
                "type": "scan_result",
                "id": candidate.get("_entity_id"),
                "scan_id": candidate.get("_source_id"),
                "symbol": self._symbol(candidate),
                "name": candidate.get("name") or candidate.get("stock_name") or "",
            }
        return {
            "type": "pick",
            "id": candidate.get("id"),
            "symbol": self._symbol(candidate),
            "name": candidate.get("stock_name") or candidate.get("name") or "",
        }

    def _rule_scope(self, alert_rule: dict) -> str:
        scope = str(alert_rule.get("scope") or "").strip().lower()
        metadata = alert_rule.get("metadata") if isinstance(alert_rule.get("metadata"), dict) else {}
        page = str(metadata.get("page") or "").strip().lower()
        rule = self._rule_body(alert_rule)
        metric = str(rule.get("metric") or "").strip()
        if scope in {"scan_results", "scans", "scan"} or page == "scans" or metric in self.SCAN_METRICS:
            return "scan_results"
        if scope in {"picks", "pick", "symbol"} or page == "picks" or metric in self.PICK_METRICS:
            return "picks"
        return "picks"

    def _rule_body(self, alert_rule: dict) -> dict:
        rule = alert_rule.get("rule")
        return dict(rule) if isinstance(rule, dict) else {}

    def _target_matches(self, alert_rule: dict, candidate: dict) -> bool:
        target = self._target(alert_rule)
        if not target or target.lower() in self.GENERIC_TARGETS:
            return True
        return target == self._symbol(candidate)

    def _target(self, alert_rule: dict) -> str:
        return str(alert_rule.get("target") or alert_rule.get("symbol") or "").strip()

    def _channels(self, alert_rule: dict) -> list[str]:
        channels = alert_rule.get("channels")
        if not isinstance(channels, list) or not channels:
            return ["in_app"]
        return [str(channel).strip().lower() for channel in channels if str(channel).strip()]

    def _uses_in_app_channel(self, alert_rule: dict) -> bool:
        return "in_app" in self._channels(alert_rule)

    def _severity(self, alert_rule: dict) -> str:
        metadata = alert_rule.get("metadata") if isinstance(alert_rule.get("metadata"), dict) else {}
        severity = str(metadata.get("severity") or alert_rule.get("severity") or "warning").strip().lower()
        return severity if severity in {"info", "warning", "critical"} else "warning"

    def _field_value(self, candidate: dict, field: str) -> Any:
        if not field:
            return None
        aliases = {
            "score": "explanation.score",
            "confidence": "explanation.confidence",
            "risk": "risk_level",
            "risk_level": "risk_level",
            "status": "status",
            "symbol": "symbol",
            "code": "symbol",
        }
        path = aliases.get(field, field).split(".")
        current: Any = candidate
        for part in path:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    def _compare(self, actual: Any, operator: str, expected: Any) -> bool:
        op = operator.strip().lower()
        numeric_actual = self._float(actual)
        numeric_expected = self._float(expected)
        if numeric_actual is not None and numeric_expected is not None:
            return self._compare_numeric(numeric_actual, op, numeric_expected)
        left = str(actual or "")
        if op in {"=", "==", "eq"}:
            return left == str(expected)
        if op in {"!=", "<>", "ne"}:
            return left != str(expected)
        if op == "contains":
            return str(expected) in left
        if op == "in":
            values = expected if isinstance(expected, list) else [expected]
            return left in {str(value) for value in values}
        if op in {"not_in", "not in"}:
            values = expected if isinstance(expected, list) else [expected]
            return left not in {str(value) for value in values}
        return False

    def _compare_numeric(self, actual: float, operator: str, expected: float) -> bool:
        if operator in {">", "gt"}:
            return actual > expected
        if operator in {">=", "gte"}:
            return actual >= expected
        if operator in {"<", "lt"}:
            return actual < expected
        if operator in {"<=", "lte"}:
            return actual <= expected
        if operator in {"=", "==", "eq"}:
            return actual == expected
        if operator in {"!=", "<>", "ne"}:
            return actual != expected
        return False

    def _dedupe_key(self, rule_id: str, scope: str, entity_id: Any, metric: Any) -> str:
        raw = json.dumps(
            {
                "rule_id": rule_id,
                "scope": scope,
                "entity_id": str(entity_id or ""),
                "metric": str(metric or ""),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def _symbol(self, candidate: dict) -> str:
        return str(candidate.get("symbol") or candidate.get("code") or candidate.get("stock_code") or "").strip()

    def _float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")
