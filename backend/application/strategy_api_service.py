"""Application service for strategy lifecycle API endpoints."""

from __future__ import annotations

import ast
import os
import re
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any

from backend.application.pagination import PaginationParams
from backend.core.errors import AppError, NotFoundError
from backend.infrastructure.tasks.queue import enqueue_task
from backend.repositories import market_data_repo
from backend.repositories import strategy_repo
from backend.strategies import registry


CODE_PATTERN = re.compile(r"^[A-Za-z0-9_]{2,64}$")
SECURITY_TYPES = {"stock", "etf", "index", "convertible_bond", "bond", "fund", "b_share"}
BAR_INTERVALS = {"1d", "15m", "30m", "5m", "1h", "1m"}


class StrategyApiService:
    def list_strategies(self, tenant_id: int, pagination: PaginationParams) -> dict:
        rows = strategy_repo.list_strategies(active_only=False)
        items = [self._strategy_contract(row, tenant_id) for row in rows]
        start = pagination.offset
        end = start + pagination.page_size
        return {
            "items": items[start:end],
            "total": len(items),
            "page": pagination.page,
            "page_size": pagination.page_size,
            "tenant_id": tenant_id,
            "workflow": self.workflow_contract(),
        }

    def get_strategy(self, tenant_id: int, strategy_id: int) -> dict | None:
        row = strategy_repo.get_strategy_by_id(strategy_id)
        return self._strategy_contract(row, tenant_id) if row else None

    def create_strategy(self, tenant_id: int, payload: dict[str, Any], *, user_id: int | None = None) -> dict:
        code = self._validate_code(payload.get("code"))
        if strategy_repo.get_strategy_by_code(code):
            raise AppError("strategy code already exists")
        name = self._required_text(payload.get("name"), "name")
        config_payload = payload.get("config") or payload.get("config_json") or {
            key: payload.get(key)
            for key in ("security_type", "target_security_type", "bar_interval", "interval", "adjust", "allow_t0", "t0_enabled")
            if key in payload
        }
        strategy_repo.create_strategy(
            code,
            name,
            category=str(payload.get("category") or ""),
            description=str(payload.get("description") or ""),
            sort_order=int(payload.get("sort_order") or 100),
            code_body=str(payload.get("code_body") or self.default_code_template(code, name)),
            config_json=self._normalize_strategy_config(config_payload),
            source_type=str(payload.get("source_type") or "custom"),
            lifecycle_status=str(payload.get("lifecycle_status") or "draft"),
            enabled=bool(payload.get("enabled", False)),
            created_by=user_id,
        )
        created = strategy_repo.get_strategy_by_code(code)
        return self._strategy_contract(created, tenant_id)

    def update_strategy(self, tenant_id: int, strategy_id: int, payload: dict[str, Any]) -> dict:
        row = strategy_repo.get_strategy_by_id(strategy_id)
        if not row:
            raise NotFoundError("strategy not found")
        update: dict[str, Any] = {}
        if "code" in payload:
            update["code"] = self._validate_code(payload.get("code"))
        if "name" in payload:
            update["name"] = self._required_text(payload.get("name"), "name")
        for key in ("category", "description", "code_body", "source_type", "lifecycle_status"):
            if key in payload:
                update[key] = str(payload.get(key) or "")
        config_payload = None
        if "config" in payload or "config_json" in payload:
            config_payload = payload.get("config") if "config" in payload else payload.get("config_json")
        if any(key in payload for key in ("security_type", "target_security_type", "bar_interval", "interval", "adjust", "allow_t0", "t0_enabled")):
            config_payload = {**(row.get("config") or {}), **(config_payload or {}), **payload}
        if config_payload is not None:
            update["config_json"] = self._normalize_strategy_config(config_payload)
        if "enabled" in payload:
            update["enabled"] = bool(payload.get("enabled"))
        if "is_active" in payload:
            update["is_active"] = bool(payload.get("is_active"))
        if "sort_order" in payload:
            update["sort_order"] = int(payload.get("sort_order") or 0)
        if update.get("code") and update["code"] != row.get("code") and strategy_repo.get_strategy_by_code(update["code"]):
            raise AppError("strategy code already exists")
        if "code_body" in update:
            update["version"] = int(row.get("version") or 1) + 1
            update.setdefault("lifecycle_status", "draft")
        if not update:
            return self._strategy_contract(row, tenant_id)
        strategy_repo.update_strategy(strategy_id, **update)
        return self._strategy_contract(strategy_repo.get_strategy_by_id(strategy_id), tenant_id)

    def test_strategy(self, tenant_id: int, strategy_id: int, payload: dict[str, Any] | None = None) -> dict:
        payload = payload or {}
        row = strategy_repo.get_strategy_by_id(strategy_id)
        if not row:
            raise NotFoundError("strategy not found")
        code_body = str(payload.get("code_body") if "code_body" in payload else row.get("code_body") or "")
        result = self._syntax_test(code_body)
        sample = []
        runtime_strategy = registry.get(row.get("code"))
        target_date = str(payload.get("target_date") or date.today().isoformat())
        if result["passed"] and runtime_strategy:
            try:
                sample = runtime_strategy.scan(target_date)[: int(payload.get("sample_limit") or 5)]
                result["runtime_registered"] = True
                result["sample_count"] = len(sample)
            except Exception as exc:
                result = {**result, "passed": False, "message": f"runtime scan failed: {exc}", "runtime_registered": True}
        elif result["passed"]:
            result["runtime_registered"] = False
            result["message"] = "syntax passed; custom code is stored but not loaded into production runtime yet"
        now = datetime.now()
        strategy_repo.update_strategy(
            strategy_id,
            last_test_status="passed" if result["passed"] else "failed",
            last_test_message=result["message"],
            last_test_at=now,
            lifecycle_status="tested" if result["passed"] else "draft",
        )
        return {
            "tenant_id": tenant_id,
            "strategy": self._strategy_contract(strategy_repo.get_strategy_by_id(strategy_id), tenant_id),
            "result": result,
            "sample": sample,
            "target_date": target_date,
        }

    def deploy_strategy(self, tenant_id: int, strategy_id: int) -> dict:
        row = strategy_repo.get_strategy_by_id(strategy_id)
        if not row:
            raise NotFoundError("strategy not found")
        if row.get("last_test_status") not in {"passed", "pass", "ok"} and row.get("source_type") != "builtin":
            raise AppError("custom strategy must pass test before deployment")
        now = datetime.now()
        strategy_repo.update_strategy(
            strategy_id,
            enabled=True,
            is_active=True,
            lifecycle_status="deployed",
            deployed_at=now,
        )
        return {
            "tenant_id": tenant_id,
            "strategy": self._strategy_contract(strategy_repo.get_strategy_by_id(strategy_id), tenant_id),
            "deployment": {
                "status": "deployed",
                "deployed_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "runtime_registered": bool(registry.get(row.get("code"))),
                "contract": "deployed strategies use local data center first; realtime triggers should read snapshot data written by workers",
            },
        }

    def trigger_production_run(self, tenant_id: int, strategy_id: int, payload: dict[str, Any] | None = None) -> dict:
        row = strategy_repo.get_strategy_by_id(strategy_id)
        if not row:
            raise NotFoundError("strategy not found")
        if not bool(row.get("enabled")) or row.get("lifecycle_status") != "deployed":
            raise AppError("strategy must be deployed and enabled before production run")
        payload = payload or {}
        params = payload.get("params") if "params" in payload else payload
        run_params = self._normalize_production_params(row, params)
        target_security_type = run_params["security_type"]
        bar_interval = run_params["bar_interval"]
        adjust = run_params["adjust"]
        local_coverage = market_data_repo.coverage_summary(
            interval=bar_interval,
            security_type=target_security_type,
            adjust=adjust,
        )
        snapshot_payload = market_data_repo.list_latest_snapshots(page=1, page_size=1, security_type=target_security_type)
        production_contract = self._production_contract(
            strategy_code=row.get("code"),
            security_type=target_security_type,
            bar_interval=bar_interval,
            adjust=adjust,
            local_coverage=local_coverage,
            local_snapshot_summary=snapshot_payload.get("summary") or {},
            min_coverage_ratio=float(run_params.get("min_coverage_ratio") or 0),
        )
        if row.get("code") == "LIMIT_UP_RETURN":
            production_contract["strategy_requirements"] = self._limit_up_return_requirements(
                target_security_type,
                bar_interval,
                float(run_params.get("min_coverage_ratio") or 0),
            )
        task = enqueue_task(
            "strategy.production_run",
            self.run_deployed_strategy,
            tenant_id,
            strategy_id,
            run_params,
            tenant_id=tenant_id,
            payload={"strategy_id": strategy_id, "strategy_code": row.get("code"), "params": run_params, "production_contract": production_contract},
            max_retries=1,
        )
        return {
            "tenant_id": tenant_id,
            "strategy": self._strategy_contract(row, tenant_id),
            "task": task,
            "params": run_params,
            "production_contract": production_contract,
        }

    def run_deployed_strategy(self, tenant_id: int, strategy_id: int, params: dict[str, Any] | None = None) -> dict:
        row = strategy_repo.get_strategy_by_id(strategy_id)
        if not row:
            raise NotFoundError("strategy not found")
        if not bool(row.get("enabled")) or row.get("lifecycle_status") != "deployed":
            raise AppError("strategy must be deployed and enabled before production run")
        params = self._normalize_production_params(row, params or {})
        sample_size = max(1, min(int(params.get("sample_size") or 20), 200))
        scan_limit = max(1, min(int(params.get("scan_limit") or 6000), 10000))
        target_security_type = params["security_type"]
        bar_interval = params["bar_interval"]
        adjust = params["adjust"]
        snapshot_payload = market_data_repo.list_latest_snapshots(page=1, page_size=sample_size, security_type=target_security_type)
        snapshot_items = snapshot_payload.get("items") or []
        snapshot_summary = snapshot_payload.get("summary") or {}
        coverage = market_data_repo.coverage_summary(interval=bar_interval, security_type=target_security_type, adjust=adjust)
        freshness = self._market_data_freshness(
            security_type=target_security_type,
            bar_interval=bar_interval,
            adjust=adjust,
        )
        target_count = int(coverage.get("target_security_count") or coverage.get("security_count") or (coverage.get("security_type_counts") or {}).get(target_security_type) or 0)
        synced_symbols = int(coverage.get("synced_symbols") or 0)
        coverage_ratio = float(coverage.get("coverage_ratio") or (round(synced_symbols / target_count, 4) if target_count else 0))
        min_coverage_ratio = float(params.get("min_coverage_ratio") or 0)
        production_contract = self._production_contract(
            strategy_code=row.get("code"),
            security_type=target_security_type,
            bar_interval=bar_interval,
            adjust=adjust,
            local_coverage=coverage,
            local_snapshot_summary=snapshot_summary,
            min_coverage_ratio=min_coverage_ratio,
        )
        production_contract["data_freshness"] = freshness["data_freshness"]
        scan_params = {
            **params,
            "sample_size": sample_size,
            "scan_limit": scan_limit,
            "security_type": target_security_type,
            "target_security_type": target_security_type,
            "bar_interval": bar_interval,
            "interval": bar_interval,
            "adjust": adjust,
            "allow_t0": self._bool_value(params.get("allow_t0"), default=target_security_type == "convertible_bond"),
            "full_universe": self._bool_value(params.get("full_universe"), default=True),
            "local_only": True,
            "disable_market_sample_fallback": True,
            "data_policy": "local_snapshot_and_history_first",
            "local_snapshot_summary": snapshot_summary,
            "local_coverage": coverage,
            "local_coverage_ratio": coverage_ratio,
            "data_freshness": freshness["data_freshness"],
        }
        warnings = []
        if not snapshot_items:
            warnings.append("no local realtime snapshots; run market.snapshot sync before production trigger")
            return {
                "tenant_id": tenant_id,
                "strategy": self._strategy_contract(row, tenant_id),
                "production_status": "blocked_no_snapshot",
                "production_contract": production_contract,
                "scan_params": scan_params,
                "local_snapshot_summary": snapshot_summary,
                "local_coverage": coverage,
                "snapshot_sample": [],
                "scan": None,
                "warnings": warnings,
                "data_policy": "local_snapshot_and_history_first",
                **freshness,
            }
        if synced_symbols <= 0:
            warnings.append("no local historical K-line data; run market.sync before production trigger")
            return {
                "tenant_id": tenant_id,
                "strategy": self._strategy_contract(row, tenant_id),
                "production_status": "blocked_no_history",
                "production_contract": production_contract,
                "scan_params": scan_params,
                "local_snapshot_summary": snapshot_summary,
                "local_coverage": coverage,
                "snapshot_sample": snapshot_items[:10],
                "scan": None,
                "warnings": warnings,
                "data_policy": "local_snapshot_and_history_first",
                **freshness,
            }
        snapshot_max_age_seconds = freshness.get("snapshot_max_age_seconds")
        snapshot_age_seconds = freshness.get("snapshot_age_seconds")
        if snapshot_max_age_seconds and snapshot_age_seconds is not None and snapshot_age_seconds > snapshot_max_age_seconds:
            warnings.append(
                f"latest local snapshot is stale: age {snapshot_age_seconds}s exceeds allowed {snapshot_max_age_seconds}s"
            )
            return {
                "tenant_id": tenant_id,
                "strategy": self._strategy_contract(row, tenant_id),
                "production_status": "blocked_stale_snapshot",
                "skip_reason": "stale_snapshot",
                "production_contract": production_contract,
                "scan_params": scan_params,
                "local_snapshot_summary": snapshot_summary,
                "local_coverage": coverage,
                "snapshot_sample": snapshot_items[:10],
                "scan": None,
                "warnings": warnings,
                "data_policy": "local_snapshot_and_history_first",
                **freshness,
            }
        daily_bar_max_lag_days = freshness.get("daily_bar_max_lag_days")
        daily_bar_lag_days = freshness.get("daily_bar_lag_days")
        if daily_bar_max_lag_days and daily_bar_lag_days is not None and daily_bar_lag_days > daily_bar_max_lag_days:
            warnings.append(
                f"latest local daily bar is stale: lag {daily_bar_lag_days}d exceeds allowed {daily_bar_max_lag_days}d"
            )
            return {
                "tenant_id": tenant_id,
                "strategy": self._strategy_contract(row, tenant_id),
                "production_status": "blocked_stale_daily_bar",
                "skip_reason": "stale_daily_bar",
                "production_contract": production_contract,
                "scan_params": scan_params,
                "local_snapshot_summary": snapshot_summary,
                "local_coverage": coverage,
                "snapshot_sample": snapshot_items[:10],
                "scan": None,
                "warnings": warnings,
                "data_policy": "local_snapshot_and_history_first",
                **freshness,
            }
        if self._has_forbidden_sources(coverage, snapshot_summary):
            warnings.append("mock/fallback market data is forbidden for production signals")
            return {
                "tenant_id": tenant_id,
                "strategy": self._strategy_contract(row, tenant_id),
                "production_status": "blocked_mock_fallback_source",
                "production_contract": production_contract,
                "scan_params": scan_params,
                "local_snapshot_summary": snapshot_summary,
                "local_coverage": coverage,
                "snapshot_sample": snapshot_items[:10],
                "scan": None,
                "warnings": warnings,
                "data_policy": "local_snapshot_and_history_first",
                **freshness,
            }
        limit_return_requirements = self._limit_up_return_requirements(target_security_type, bar_interval, min_coverage_ratio)
        if row.get("code") == "LIMIT_UP_RETURN":
            production_contract["strategy_requirements"] = limit_return_requirements
            blocking_requirement = next((item for item in limit_return_requirements.get("checks", []) if item.get("blocking") and not item.get("passed")), None)
            if blocking_requirement:
                warnings.append(blocking_requirement.get("message") or "LIMIT_UP_RETURN production requirement failed")
                return {
                    "tenant_id": tenant_id,
                    "strategy": self._strategy_contract(row, tenant_id),
                    "production_status": blocking_requirement.get("status") or "blocked_strategy_requirement",
                    "production_contract": production_contract,
                    "scan_params": scan_params,
                    "local_snapshot_summary": snapshot_summary,
                    "local_coverage": coverage,
                    "snapshot_sample": snapshot_items[:10],
                    "scan": None,
                    "warnings": warnings,
                    "data_policy": "local_snapshot_and_history_first",
                    **freshness,
                }
        if min_coverage_ratio > 0 and coverage_ratio < min_coverage_ratio:
            warnings.append(f"local historical K-line coverage ratio {coverage_ratio} is below required {min_coverage_ratio}")
            return {
                "tenant_id": tenant_id,
                "strategy": self._strategy_contract(row, tenant_id),
                "production_status": "blocked_low_coverage",
                "production_contract": production_contract,
                "scan_params": scan_params,
                "local_snapshot_summary": snapshot_summary,
                "local_coverage": coverage,
                "snapshot_sample": snapshot_items[:10],
                "scan": None,
                "warnings": warnings,
                "data_policy": "local_snapshot_and_history_first",
                **freshness,
            }
        if target_count and synced_symbols < target_count:
            warnings.append(f"local K-line coverage is partial for {target_security_type}/{bar_interval}: {synced_symbols}/{target_count}")
        runtime_strategy = registry.get(row.get("code"))
        if not runtime_strategy:
            warnings.append("strategy is deployed in metadata but not registered in runtime")
        from backend.application.scan_api_service import ScanApiService

        with self._local_market_data_only(enabled=True):
            scan = ScanApiService()._run_scan(tenant_id, row.get("code"), scan_params) if runtime_strategy else None
        paper_trading = None
        paper_enabled = self._bool_value(params.get("paper_trade"), os.getenv("PAPER_TRADING_ENABLED", "1").strip().lower() not in {"0", "false", "no"})
        paper_gate = self._paper_trading_gate(row, params)
        if paper_enabled and not paper_gate["passed"]:
            warnings.append(paper_gate["message"])
            paper_enabled = False
            paper_trading = {
                "enabled": False,
                "reason": paper_gate["status"],
                "gate": paper_gate,
                "live_trading": {
                    "supported": False,
                    "reserved_adapter": "BrokerAdapter.submit_order/reconcile_orders",
                    "guard": "paper execution only; no real broker order is sent",
                },
            }
        if scan and paper_enabled:
            try:
                from backend.application.paper_trading_service import PaperTradingService

                paper_trading = PaperTradingService().apply_strategy_scan(tenant_id, row, scan, params)
            except Exception as exc:
                warnings.append(f"paper trading failed: {exc}")
                paper_trading = {"enabled": False, "error": str(exc)}
        return {
            "tenant_id": tenant_id,
            "strategy": self._strategy_contract(row, tenant_id),
            "production_status": "completed" if scan else "metadata_only",
            "production_contract": production_contract,
            "scan_params": scan_params,
            "local_snapshot_summary": snapshot_summary,
            "local_coverage": coverage,
            "snapshot_sample": snapshot_items[:10],
            "scan": scan,
            "paper_trading": paper_trading,
            "warnings": warnings,
            "data_policy": "local_snapshot_and_history_first",
            **freshness,
        }

    def workflow_contract(self) -> dict:
        return {
            "schema_version": "strategy-lifecycle/v1",
            "stages": ["draft", "tested", "deployed", "disabled"],
            "actions": ["create", "edit", "syntax_test", "backtest", "deploy", "run_scan", "production_run"],
            "data_policy": {
                "backtest": "local_market_data_first",
                "live_trigger": "worker_sync_snapshot_first",
                "external_provider": "mootdx_or_fallback_only_on_cache_miss",
                "production_run": "requires_local_snapshot_and_history",
                "local_only_default": True,
                "security_types": sorted(SECURITY_TYPES),
                "bar_intervals": sorted(BAR_INTERVALS),
            },
        }

    def default_code_template(self, code: str, name: str) -> str:
        class_name = "".join(part.capitalize() for part in code.split("_") if part) or "CustomStrategy"
        return (
            "from backend.strategies import BaseStrategy\n\n\n"
            f"class {class_name}(BaseStrategy):\n"
            f"    def get_code(self):\n        return {code!r}\n\n"
            f"    def get_name(self):\n        return {name!r}\n\n"
            "    def get_description(self):\n        return 'custom strategy draft'\n\n"
            "    def scan(self, date=None):\n        return []\n"
        )

    def _strategy_contract(self, row: dict | None, tenant_id: int) -> dict:
        if not row:
            return {}
        runtime_strategy = registry.get(row.get("code"))
        parameters = runtime_strategy.get_parameters() if runtime_strategy and hasattr(runtime_strategy, "get_parameters") else {}
        config = self._normalize_strategy_config(row.get("config") or row.get("config_json") or {})
        enabled = bool(row.get("enabled", row.get("is_active", True)))
        lifecycle = row.get("lifecycle_status") or ("deployed" if enabled else "disabled")
        return {
            **row,
            "tenant_id": tenant_id,
            "enabled": enabled,
            "is_active": bool(row.get("is_active", True)),
            "lifecycle_status": lifecycle,
            "runtime_registered": bool(runtime_strategy),
            "parameters": parameters,
            "config": config,
            "target_security_type": config["target_security_type"],
            "bar_interval": config["bar_interval"],
            "adjust": config["adjust"],
            "allow_t0": config["allow_t0"],
            "data_requirements": {
                "security_type": config["target_security_type"],
                "bar_interval": config["bar_interval"],
                "adjust": config["adjust"],
                "history_table": "stock_daily_bars",
                "snapshot_table": "stock_price_snapshots",
                "t0_supported": bool(config["target_security_type"] == "convertible_bond" and config["bar_interval"] != "1d"),
            },
            "can_deploy": bool(row.get("source_type") == "builtin" or row.get("last_test_status") == "passed"),
        }

    def _syntax_test(self, code_body: str) -> dict:
        if not code_body.strip():
            return {"passed": False, "message": "strategy code is empty", "checks": ["syntax"]}
        try:
            ast.parse(code_body)
        except SyntaxError as exc:
            return {"passed": False, "message": f"syntax error at line {exc.lineno}: {exc.msg}", "checks": ["syntax"]}
        return {"passed": True, "message": "syntax passed", "checks": ["syntax"]}

    def _validate_code(self, value: Any) -> str:
        code = str(value or "").strip()
        if not CODE_PATTERN.match(code):
            raise AppError("invalid strategy code, use 2-64 letters, numbers, or underscore")
        return code

    def _normalize_security_type(self, value: Any) -> str:
        normalized = str(value or "stock").strip().lower()
        return normalized if normalized in SECURITY_TYPES else "stock"

    def _normalize_bar_interval(self, value: Any) -> str:
        normalized = str(value or "1d").strip().lower()
        aliases = {"day": "1d", "daily": "1d", "15": "15m", "30": "30m", "60m": "1h"}
        normalized = aliases.get(normalized, normalized)
        return normalized if normalized in BAR_INTERVALS else "1d"

    def _normalize_adjust(self, value: Any, bar_interval: str) -> str:
        adjust = str(value or ("none" if bar_interval != "1d" else "qfq")).strip().lower()
        if adjust in {"", "raw", "bfq", "\u4e0d\u590d\u6743", "涓嶅鏉?"}:
            adjust = "none"
        if bar_interval != "1d" and adjust in {"qfq", "hfq"}:
            adjust = "none"
        return adjust

    def _normalize_production_params(self, row: dict, params: dict[str, Any] | None) -> dict:
        params = dict(params or {})
        config = self._normalize_strategy_config(row.get("config") or row.get("config_json") or {})
        target_security_type = self._normalize_security_type(
            params.get("security_type") or params.get("target_security_type") or config["target_security_type"]
        )
        bar_interval = self._normalize_bar_interval(params.get("bar_interval") or params.get("interval") or config["bar_interval"])
        adjust = self._normalize_adjust(params.get("adjust") or config.get("adjust"), bar_interval)
        return {
            **params,
            "security_type": target_security_type,
            "target_security_type": target_security_type,
            "bar_interval": bar_interval,
            "interval": bar_interval,
            "adjust": adjust,
            "local_only": True,
            "data_policy": "local_snapshot_and_history_first",
            "requires_local_snapshot": True,
            "requires_local_history": True,
        }

    def _production_contract(
        self,
        *,
        strategy_code: str | None = None,
        security_type: str,
        bar_interval: str,
        adjust: str,
        local_coverage: dict,
        local_snapshot_summary: dict,
        min_coverage_ratio: float = 0,
    ) -> dict:
        return {
            "data_policy": "local_snapshot_and_history_first",
            "local_only": True,
            "local_only_required": True,
            "snapshot_table": "stock_price_snapshots",
            "history_table": "stock_daily_bars",
            "security_type": security_type,
            "bar_interval": bar_interval,
            "interval": bar_interval,
            "adjust": adjust,
            "blocked_without_snapshot": True,
            "blocked_without_history": True,
            "requires": ["local_realtime_snapshot", "local_historical_bars"],
            "strategy_code": strategy_code,
            "min_coverage_ratio": min_coverage_ratio,
            "local_snapshot_summary": local_snapshot_summary,
            "local_coverage": local_coverage,
            "local_coverage_ratio": local_coverage.get("coverage_ratio", 0),
            "snapshot_coverage_ratio": local_snapshot_summary.get("coverage_ratio", 0),
            "forbidden_sources": ["mock", "fallback"],
            "mock_or_fallback_blocked": True,
        }

    def _limit_up_return_requirements(self, security_type: str, bar_interval: str, min_coverage_ratio: float = 0) -> dict:
        qfq_coverage = market_data_repo.coverage_summary(interval="1d", security_type=security_type, adjust="qfq")
        none_coverage = market_data_repo.coverage_summary(interval="1d", security_type=security_type, adjust="none")
        snapshot_summary = market_data_repo.snapshot_summary(security_type=security_type)
        rule_summary = market_data_repo.limit_rule_summary()
        required_ratio = float(min_coverage_ratio or 0)

        def coverage_check(label: str, payload: dict, status: str) -> dict:
            synced = int(payload.get("synced_symbols") or 0)
            ratio = float(payload.get("coverage_ratio") or 0)
            ratio_ok = ratio >= required_ratio if required_ratio > 0 else True
            passed = synced > 0 and ratio_ok
            return {
                "name": label,
                "status": status,
                "passed": passed,
                "blocking": True,
                "synced_symbols": synced,
                "coverage_ratio": ratio,
                "message": f"{label} coverage missing or below required ratio" if not passed else f"{label} coverage ready",
            }

        rule_passed = bool(rule_summary.get("has_rules"))
        requested_interval = self._normalize_bar_interval(bar_interval)
        interval_coverage = (
            market_data_repo.coverage_summary(interval=requested_interval, security_type=security_type, adjust="none")
            if requested_interval != "1d"
            else None
        )
        checks = [
            coverage_check("qfq_history", qfq_coverage, "blocked_no_qfq_history"),
            coverage_check("none_history", none_coverage, "blocked_no_raw_history"),
            {
                "name": "limit_rule_calendar",
                "status": "blocked_no_limit_rules",
                "passed": rule_passed,
                "blocking": True,
                "rule_count": int(rule_summary.get("rule_count") or 0),
                "message": "limit rule calendar missing" if not rule_passed else "limit rule calendar ready",
            },
            self._source_quality_check(qfq_coverage, none_coverage, snapshot_summary),
        ]
        if interval_coverage is not None:
            checks.append(coverage_check(f"{requested_interval}_history", interval_coverage, "blocked_no_interval_history"))
        return {
            "strategy_code": "LIMIT_UP_RETURN",
            "requires": ["adjust=qfq daily bars", "adjust=none daily bars", "limit_rule_calendar", "non_mock_local_sources"],
            "qfq_coverage": qfq_coverage,
            "none_coverage": none_coverage,
            "snapshot_summary": snapshot_summary,
            "interval_coverage": interval_coverage,
            "limit_rule_summary": rule_summary,
            "checks": checks,
        }

    def _source_quality_check(self, *payloads: dict) -> dict:
        forbidden = self._forbidden_sources(*payloads)
        return {
            "name": "source_quality",
            "status": "blocked_mock_fallback_source",
            "passed": not forbidden,
            "blocking": True,
            "forbidden_sources": forbidden,
            "message": "mock/fallback sources are forbidden" if forbidden else "local non-mock sources ready",
        }

    def _forbidden_sources(self, *payloads: dict) -> list[str]:
        found: set[str] = set()
        for payload in payloads:
            sources = payload.get("sources")
            if sources is None and payload.get("source"):
                sources = [payload.get("source")]
            for source in sources or []:
                text = str(source or "").strip().lower()
                if not text:
                    continue
                parts = {part for part in text.replace(":", ",").split(",") if part}
                if text in {"mock", "fallback"} or parts.intersection({"mock", "fallback"}):
                    found.add(text)
        return sorted(found)

    def _has_forbidden_sources(self, *payloads: dict) -> bool:
        return bool(self._forbidden_sources(*payloads))

    def _market_data_freshness(self, *, security_type: str, bar_interval: str, adjust: str) -> dict:
        summary = market_data_repo.latest_market_data_freshness(
            security_type=security_type,
            interval=bar_interval,
            adjust=adjust,
        )
        latest_snapshot_time = summary.get("latest_snapshot_time")
        latest_trade_date = summary.get("latest_trade_date")
        snapshot_dt = self._parse_datetime_value(latest_snapshot_time)
        trade_date = self._parse_date_value(latest_trade_date)
        now = datetime.now()
        today = date.today()
        snapshot_age_seconds = int((now - snapshot_dt).total_seconds()) if snapshot_dt else None
        if snapshot_age_seconds is not None and snapshot_age_seconds < 0:
            snapshot_age_seconds = 0
        daily_bar_lag_days = (today - trade_date).days if trade_date else None
        if daily_bar_lag_days is not None and daily_bar_lag_days < 0:
            daily_bar_lag_days = 0
        snapshot_max_age_seconds = self._positive_int_env("STRATEGY_SNAPSHOT_MAX_AGE_SECONDS")
        daily_bar_max_lag_days = self._positive_int_env("STRATEGY_DAILY_BAR_MAX_LAG_DAYS")
        return {
            "data_freshness": {
                **summary,
                "latest_snapshot_time": latest_snapshot_time,
                "snapshot_age_seconds": snapshot_age_seconds,
                "snapshot_max_age_seconds": snapshot_max_age_seconds,
                "latest_trade_date": latest_trade_date,
                "daily_bar_lag_days": daily_bar_lag_days,
                "daily_bar_max_lag_days": daily_bar_max_lag_days,
            },
            "latest_snapshot_time": latest_snapshot_time,
            "snapshot_age_seconds": snapshot_age_seconds,
            "snapshot_max_age_seconds": snapshot_max_age_seconds,
            "latest_trade_date": latest_trade_date,
            "daily_bar_lag_days": daily_bar_lag_days,
            "daily_bar_max_lag_days": daily_bar_max_lag_days,
        }

    def _positive_int_env(self, name: str) -> int | None:
        try:
            value = int(str(os.getenv(name) or "").strip())
        except ValueError:
            return None
        return value if value > 0 else None

    def _parse_datetime_value(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:19] if "H" in fmt else text[:10], fmt)
            except ValueError:
                continue
        return None

    def _parse_date_value(self, value: Any) -> date | None:
        if value in (None, ""):
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        try:
            return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            return None

    def _paper_trading_gate(self, row: dict, params: dict[str, Any]) -> dict:
        if row.get("code") != "LIMIT_UP_RETURN":
            return {"passed": True, "status": "passed", "message": "paper trading gate passed"}
        config = self._normalize_strategy_config(row.get("config") or row.get("config_json") or {})
        passed = self._bool_value(params.get("out_of_sample_passed", config.get("out_of_sample_passed")), default=False)
        return {
            "passed": passed,
            "status": "passed" if passed else "blocked_oos_backtest_required",
            "message": "out-of-sample backtest gate passed" if passed else "out-of-sample backtest must pass before LIMIT_UP_RETURN production paper trading",
            "strategy_code": row.get("code"),
        }

    def _normalize_strategy_config(self, value: Any) -> dict:
        config = value if isinstance(value, dict) else {}
        target_security_type = self._normalize_security_type(config.get("target_security_type") or config.get("security_type"))
        bar_interval = self._normalize_bar_interval(config.get("bar_interval") or config.get("interval"))
        adjust = self._normalize_adjust(config.get("adjust"), bar_interval)
        if adjust in {"", "raw", "bfq", "不复权"}:
            adjust = "none"
        allow_t0 = self._bool_value(config.get("allow_t0", config.get("t0_enabled")), default=target_security_type == "convertible_bond")
        return {
            **config,
            "target_security_type": target_security_type,
            "security_type": target_security_type,
            "bar_interval": bar_interval,
            "interval": bar_interval,
            "adjust": adjust,
            "allow_t0": allow_t0,
            "data_policy": config.get("data_policy") or "local_snapshot_and_history_first",
        }

    def _required_text(self, value: Any, field: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise AppError(f"missing {field}")
        return text

    def _bool_value(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    @contextmanager
    def _local_market_data_only(self, *, enabled: bool):
        if not enabled:
            yield
            return
        original = os.environ.get("MARKET_DATA_LOCAL_ONLY")
        os.environ["MARKET_DATA_LOCAL_ONLY"] = "1"
        try:
            yield
        finally:
            if original is None:
                os.environ.pop("MARKET_DATA_LOCAL_ONLY", None)
            else:
                os.environ["MARKET_DATA_LOCAL_ONLY"] = original
