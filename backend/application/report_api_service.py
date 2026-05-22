"""Application service for research report API endpoints."""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta
from typing import Any

from backend.application.external_push import ExternalPushService
from backend.application.pagination import PaginationParams
from backend.core.errors import AppError, NotFoundError
from backend.repositories import paper_trading_repo, picks_repo, settings_repo


external_push_service = ExternalPushService()


class ReportApiService:
    REVIEWED_STATUSES = {"validated", "verified", "rejected", "reviewed", "done"}

    def list_reports(self, tenant_id: int, pagination: PaginationParams, symbol: str | None = None) -> dict:
        where = "WHERE code=?" if symbol else ""
        args = [symbol] if symbol else []
        picks = picks_repo.list_picks(
            where,
            args,
            limit=pagination.page_size,
            offset=(pagination.page - 1) * pagination.page_size,
            tenant_id=tenant_id,
        )
        latest = picks_repo.get_latest_research_map([row.get("id") for row in picks])
        items = [self._report_payload(report, tenant_id) for report in latest.values()]
        return {
            "items": items,
            "total": len(items),
            "page": pagination.page,
            "page_size": pagination.page_size,
            "tenant_id": tenant_id,
            "filters": {"symbol": symbol} if symbol else {},
        }

    def create_report(self, tenant_id: int, payload: dict) -> dict:
        symbol = str(payload.get("symbol") or "").strip()
        if not symbol:
            raise AppError("symbol is required")
        title = payload.get("title") or "Untitled research report"
        analysis_date = payload.get("analysis_date") or datetime.now().strftime("%Y-%m-%d")
        pick = self._find_or_create_report_pick(tenant_id, symbol, title)
        metrics = {
            "last_analysis_date": analysis_date,
            "technical_score": payload.get("technical_score", 0),
            "momentum_score": payload.get("momentum_score", 0),
            "risk_score": payload.get("risk_score", 0),
            "capital_score": payload.get("liquidity_score", 0),
            "timing_score": payload.get("timing_score", 0),
            "research_score": payload.get("total_score", 0),
            "research_summary": payload.get("content") or "",
            "action_suggestion": payload.get("action_suggestion", ""),
            "risk_warning": payload.get("risk_warning", ""),
            "data_snapshot": json.dumps(
                {
                    "tenant_id": tenant_id,
                    "title": title,
                    "report_type": payload.get("report_type", "manual"),
                    "source": payload.get("source", "manual"),
                },
                ensure_ascii=False,
            ),
        }
        picks_repo.upsert_research_report(
            pick["id"],
            pick.get("code", symbol),
            pick.get("pick_date", analysis_date),
            analysis_date,
            metrics,
        )
        reports = picks_repo.get_research_reports_by_pick(pick["id"], limit=50)
        report = next((item for item in reports if item.get("analysis_date") == analysis_date), reports[0] if reports else None)
        if not report:
            raise AppError("failed to persist research report")
        return self._report_payload(report, tenant_id)

    def get_report(self, tenant_id: int, report_id: str) -> dict:
        try:
            normalized_id = int(report_id)
        except (TypeError, ValueError) as exc:
            raise NotFoundError("report not found") from exc
        report = picks_repo.get_research_report_by_id(normalized_id)
        if not report:
            raise NotFoundError("report not found")
        return self._report_payload(report, tenant_id)

    def summary(self, tenant_id: int, period: str = "week") -> dict:
        normalized_period = period if period in {"week", "month"} else "week"
        start_date, end_date = self._period_window(normalized_period)
        rows = picks_repo.list_picks(
            "WHERE COALESCE(archived,0)=0 AND pick_date>=? AND pick_date<=?",
            [start_date, end_date],
            limit=1000,
            tenant_id=tenant_id,
        )
        groups: dict[str, dict] = {}
        total_return = 0.0
        return_count = 0
        high_risk_count = 0
        reviewed_count = 0
        deal_count = 0
        win_count = 0
        quality_counts = self._empty_quality_counts()
        attribution_buckets = self._empty_attribution_dimensions()

        for row in rows:
            strategy = row.get("strategy_name") or row.get("source") or "unknown"
            group = groups.setdefault(strategy, self._empty_group(strategy))
            group["total"] += 1
            status = row.get("review_status") or ""
            deal_status = row.get("deal_status") or ""
            risk = row.get("result_grade") or ""
            source = self._bucket_value(row.get("source"))
            risk_level = self._risk_bucket(row)
            return_pct = self._float_or_none(row.get("return_pct"))
            quality_bucket = self._quality_bucket(row)
            holding_bucket = self._holding_days_bucket(row.get("holding_days"))
            quality_counts[quality_bucket] += 1
            group["quality_counts"][quality_bucket] += 1

            if self._is_reviewed(status):
                reviewed_count += 1
                group["reviewed"] += 1
            if self._is_deal(deal_status):
                deal_count += 1
                group["deals"] += 1
            if self._is_high_risk(risk):
                high_risk_count += 1
                group["high_risk"] += 1
            if return_pct is not None:
                total_return += return_pct
                return_count += 1
                group["return_sum"] += return_pct
                group["return_count"] += 1
                if return_pct > 0:
                    win_count += 1
                    group["wins"] += 1
            self._add_attribution_row(
                attribution_buckets,
                strategy=strategy,
                source=source,
                risk_level=risk_level,
                data_quality=quality_bucket,
                holding_period=holding_bucket,
                status=status,
                deal_status=deal_status,
                return_pct=return_pct,
            )

        group_items = [self._finalize_group(group) for group in groups.values()]
        total = len(rows)
        attribution = self._finalize_attribution(attribution_buckets, total, total_return)
        feedback = self._strategy_feedback(group_items)
        return {
            "tenant_id": tenant_id,
            "period": normalized_period,
            "window": {"start_date": start_date, "end_date": end_date},
            "summary": {
                "total_picks": total,
                "reviewed_count": reviewed_count,
                "review_rate": round(reviewed_count / total, 4) if total else 0,
                "deal_count": deal_count,
                "win_count": win_count,
                "win_rate": round(win_count / return_count, 4) if return_count else 0,
                "average_return_pct": round(total_return / return_count, 4) if return_count else 0,
                "high_risk_count": high_risk_count,
                "high_risk_rate": round(high_risk_count / total, 4) if total else 0,
                "data_quality": self._finalize_quality_counts(quality_counts, total),
            },
            "groups": sorted(group_items, key=lambda item: item["total"], reverse=True),
            "attribution": attribution,
            "feedback": feedback,
            "drilldowns": {
                "picks": {"page": "picks", "filters": {"from_date": start_date, "to_date": end_date, "from_report_period": normalized_period}},
                "reviewed": {"page": "picks", "filters": {"reviewed": "1", "from_date": start_date, "to_date": end_date, "from_report_period": normalized_period}},
                "deals": {"page": "picks", "filters": {"deal_status": "dealt", "from_date": start_date, "to_date": end_date, "from_report_period": normalized_period}},
                "high_risk": {"page": "picks", "filters": {"risk_level": "high", "from_date": start_date, "to_date": end_date, "from_report_period": normalized_period}},
                "backtests": {"page": "strategies", "filters": {"from_report_period": normalized_period}},
            },
        }

    def export_summary(self, tenant_id: int, period: str = "week", export_format: str = "csv") -> dict:
        normalized_format = (export_format or "csv").lower()
        payload = self.summary(tenant_id, period)
        filename = f"report-summary-{payload['period']}.{normalized_format}"
        if normalized_format == "json":
            return {
                "filename": filename,
                "content_type": "application/json; charset=utf-8",
                "body": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        if normalized_format != "csv":
            raise AppError("unsupported report export format")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["section", "metric", "value"])
        for key, value in payload["summary"].items():
            writer.writerow(["summary", key, value])
        writer.writerow([])
        writer.writerow([
            "strategy",
            "total",
            "reviewed",
            "review_rate",
            "deals",
            "wins",
            "win_rate",
            "average_return_pct",
            "high_risk",
            "high_risk_rate",
            "primary",
            "fallback",
            "mock",
            "unknown",
        ])
        for item in payload["groups"]:
            writer.writerow([
                item["strategy"],
                item["total"],
                item["reviewed"],
                item["review_rate"],
                item["deals"],
                item["wins"],
                item["win_rate"],
                item["average_return_pct"],
                item["high_risk"],
                item["high_risk_rate"],
                item["data_quality"]["primary"],
                item["data_quality"]["fallback"],
                item["data_quality"]["mock"],
                item["data_quality"]["unknown"],
            ])
        writer.writerow([])
        writer.writerow(["section", "dimension", "key", "total", "total_share", "win_rate", "average_return_pct", "return_contribution_rate"])
        for dimension, items in payload["attribution"]["dimensions"].items():
            for item in items:
                writer.writerow([
                    "attribution",
                    dimension,
                    item["key"],
                    item["total"],
                    item["total_share"],
                    item["win_rate"],
                    item["average_return_pct"],
                    item["return_contribution_rate"],
                ])
        return {
            "filename": filename,
            "content_type": "text/csv; charset=utf-8",
            "body": output.getvalue(),
        }

    def daily_review(
        self,
        tenant_id: int,
        trade_date: str | None = None,
        *,
        account_id: int | None = None,
        push: bool = False,
        channels: list[str] | None = None,
        user_id: int | None = None,
        source: str = "api",
        evaluate_exits: bool = False,
    ) -> dict:
        normalized_date = self._normalize_trade_date(trade_date)
        from backend.application.paper_trading_service import PaperTradingService

        paper_service = PaperTradingService()
        resolved_account = paper_service.ensure_default_account(tenant_id, {"account_id": account_id} if account_id else {})
        resolved_account_id = int(account_id or resolved_account.get("id") or 0) or None
        mark_to_market = paper_service.mark_to_market(tenant_id, resolved_account_id)
        exit_evaluation = (
            paper_service.evaluate_exits(tenant_id, resolved_account_id, {"trade_date": normalized_date})
            if evaluate_exits and resolved_account_id
            else {"enabled": False, "orders": [], "skipped": [], "blocked": [], "reason": "not_requested"}
        )
        paper_summary = paper_trading_repo.summary(tenant_id, resolved_account_id)
        orders = self._filter_items_by_date(
            paper_trading_repo.list_orders(tenant_id, resolved_account_id, limit=300),
            normalized_date,
            "created_at",
            "updated_at",
        )
        fills = self._filter_items_by_date(
            paper_trading_repo.list_fills(tenant_id, resolved_account_id, limit=300),
            normalized_date,
            "filled_at",
            "created_at",
        )
        positions = paper_trading_repo.list_positions(tenant_id, resolved_account_id, active_only=True)
        signal_review_health = paper_trading_repo.signal_review_health(tenant_id)
        report_summary = self.summary(tenant_id, "week")
        paper_payload = self._daily_paper_payload(paper_summary, orders, fills, positions, exit_evaluation=exit_evaluation)
        attribution = report_summary.get("attribution") or {}
        message = self._daily_review_message(
            trade_date=normalized_date,
            paper=paper_payload,
            report_summary=report_summary.get("summary") or {},
            attribution=attribution,
            signal_review=signal_review_health,
        )
        notification = {
            "title": f"{normalized_date} 每日交易复盘",
            "body": message,
            "rule_id": "daily-review",
            "rule_name": "每日交易复盘",
            "scope": "reports.daily_review",
            "source": source,
            "entity": {"type": "daily_review", "tenant_id": tenant_id, "trade_date": normalized_date},
            "match": {"metric": "daily_review", "trade_date": normalized_date},
        }
        in_app_notification = self._persist_daily_review_notification(
            tenant_id,
            user_id,
            notification,
            enabled=bool(push or user_id),
        )
        push_result = self._dispatch_daily_review(
            tenant_id,
            user_id,
            notification,
            enabled=push,
            channels=channels,
        )
        return {
            "schema_version": "daily-review/v1",
            "tenant_id": int(tenant_id or 0),
            "trade_date": normalized_date,
            "account_id": resolved_account_id,
            "source": source,
            "mark_to_market": mark_to_market,
            "exit_evaluation": exit_evaluation,
            "signal_review": signal_review_health,
            "paper_trading": paper_payload,
            "report_summary": report_summary,
            "attribution": attribution,
            "message": message,
            "notification": in_app_notification,
            "push": push_result,
        }

    def _find_or_create_report_pick(self, tenant_id: int, symbol: str, title: str) -> dict:
        existing = picks_repo.list_picks("WHERE code=?", [symbol], limit=1, tenant_id=tenant_id)
        if existing:
            return existing[0]
        today = datetime.now().strftime("%Y-%m-%d")
        picks_repo.create_or_replace_pick(
            pick_date=today,
            code=symbol,
            name=title,
            pick_price=0,
            signal="research_report",
            source="api_report",
            source_channel="api_v1",
            reason_tag="research",
            note="created for research report",
            review_status="pending",
            review_comment="",
            content_title=title,
            content_ref="",
            result_grade="pending",
            inquiry_count=0,
            deal_status="pending",
            secondary_spread="no",
            strategy_name="2560",
            tenant_id=tenant_id,
        )
        pick = picks_repo.get_pick_by_unique(today, symbol, "api_report", tenant_id=tenant_id)
        if not pick:
            raise AppError("failed to create report pick")
        return pick

    def _normalize_trade_date(self, value: str | None) -> str:
        if not value:
            return date.today().isoformat()
        try:
            return date.fromisoformat(str(value)[:10]).isoformat()
        except (TypeError, ValueError) as exc:
            raise AppError("trade_date must be YYYY-MM-DD") from exc

    def _period_window(self, period: str) -> tuple[str, str]:
        today = date.today()
        days = 30 if period == "month" else 7
        baseline = date(2026, 5, 11)
        if today < baseline:
            today = baseline
        return (today - timedelta(days=days - 1)).isoformat(), today.isoformat()

    def _filter_items_by_date(self, items: list[dict], trade_date: str, *date_fields: str) -> list[dict]:
        filtered = []
        for item in items:
            if any(str(item.get(field) or "")[:10] == trade_date for field in date_fields):
                filtered.append(item)
        return filtered

    def _daily_paper_payload(self, summary: dict, orders: list[dict], fills: list[dict], positions: list[dict], *, exit_evaluation: dict | None = None) -> dict:
        buy_orders = [item for item in orders if str(item.get("side") or "").upper() == "BUY"]
        sell_orders = [item for item in orders if str(item.get("side") or "").upper() == "SELL"]
        symbols = sorted({str(item.get("symbol") or "").strip() for item in [*orders, *fills] if str(item.get("symbol") or "").strip()})
        exit_evaluation = exit_evaluation or {}
        exit_summary = {
            "enabled": bool(exit_evaluation.get("enabled")),
            "status": "evaluated" if exit_evaluation.get("enabled") else "skipped",
            "reason": exit_evaluation.get("reason") or "",
            "orders": len(exit_evaluation.get("orders") or []),
            "skipped": len(exit_evaluation.get("skipped") or []),
            "blocked": len(exit_evaluation.get("blocked") or []),
        }
        top_positions = sorted(
            positions,
            key=lambda item: float(item.get("market_value") or 0),
            reverse=True,
        )[:10]
        return {
            "summary": summary,
            "orders_count": len(orders),
            "fills_count": len(fills),
            "buy_orders": len(buy_orders),
            "sell_orders": len(sell_orders),
            "traded_symbols": symbols,
            "active_positions": len(positions),
            "exit_evaluation": exit_evaluation,
            "exit_summary": exit_summary,
            "top_positions": [
                {
                    "symbol": item.get("symbol"),
                    "quantity": item.get("quantity"),
                    "market_value": item.get("market_value"),
                    "unrealized_pnl": item.get("unrealized_pnl"),
                    "realized_pnl": item.get("realized_pnl"),
                }
                for item in top_positions
            ],
            "orders": orders[:50],
            "fills": fills[:50],
        }

    def _daily_review_message(self, *, trade_date: str, paper: dict, report_summary: dict, attribution: dict, signal_review: dict | None = None) -> str:
        account = paper.get("summary") or {}
        exit_evaluation = paper.get("exit_evaluation") or {}
        signal_review = signal_review or {}
        highlights = attribution.get("highlights") or {}
        positive = self._format_attribution_items(highlights.get("top_positive_contributors") or [])
        negative = self._format_attribution_items(highlights.get("top_negative_contributors") or [])
        symbols = ", ".join(paper.get("traded_symbols") or []) or "无"
        return "\n".join(
            [
                f"## {trade_date} 每日交易复盘",
                "",
                "### 交易账户",
                f"- 权益: {self._money(account.get('equity'))}",
                f"- 现金: {self._money(account.get('cash'))}",
                f"- 市值: {self._money(account.get('market_value'))}",
                f"- 总收益率: {self._ratio_pct(account.get('total_return_pct'))}",
                "",
                "### 当日交易",
                f"- 委托: {paper.get('orders_count', 0)} 笔，成交: {paper.get('fills_count', 0)} 笔",
                f"- 买入: {paper.get('buy_orders', 0)} 笔，卖出: {paper.get('sell_orders', 0)} 笔",
                f"- 自动卖出评估: {paper.get('exit_summary', {}).get('status', 'skipped')}，订单 {paper.get('exit_summary', {}).get('orders', 0)} 笔，阻断 {paper.get('exit_summary', {}).get('blocked', 0)} 笔，跳过 {paper.get('exit_summary', {}).get('skipped', 0)} 笔",
                f"- 交易标的: {symbols}",
                f"- 当前持仓: {paper.get('active_positions', 0)} 只",
                "",
                "### 复盘质量",
                f"- 样本: {report_summary.get('total_picks', 0)} 条",
                f"- 已复盘率: {self._ratio_pct(report_summary.get('review_rate'))}",
                f"- 胜率: {self._ratio_pct(report_summary.get('win_rate'))}",
                f"- 平均收益: {self._return_pct(report_summary.get('average_return_pct'))}",
                f"- 高风险占比: {self._ratio_pct(report_summary.get('high_risk_rate'))}",
                f"- 信号复盘链路完整率: {self._ratio_pct(signal_review.get('complete_rate'))}，未闭合 {signal_review.get('incomplete', 0)} 条",
                "",
                "### 归因",
                f"- 正贡献: {positive}",
                f"- 负贡献: {negative}",
            ]
        )

    def _format_attribution_items(self, items: list[dict]) -> str:
        if not items:
            return "无"
        return "；".join(
            f"{item.get('label') or item.get('key')}: {self._return_pct(item.get('total_return_pct'))}"
            for item in items[:3]
        )

    def _persist_daily_review_notification(self, tenant_id: int, user_id: int | None, notification: dict, *, enabled: bool) -> dict:
        if not enabled or user_id is None:
            return {"enabled": False, "status": "skipped", "reason": "no user notification target"}
        item = settings_repo.upsert_notification(
            tenant_id,
            user_id,
            {
                **notification,
                "type": "daily_review",
                "channel": "in_app",
                "severity": "info",
                "dedupe_key": f"daily-review:{tenant_id}:{user_id}:{notification['entity']['trade_date']}",
            },
        )
        return {"enabled": True, "status": "created", "item": item}

    def _dispatch_daily_review(
        self,
        tenant_id: int,
        user_id: int | None,
        notification: dict,
        *,
        enabled: bool,
        channels: list[str] | None,
    ) -> dict:
        if not enabled:
            return {"enabled": False, "status": "skipped", "reason": "push disabled", "deliveries": []}
        configs = settings_repo.list_external_push_channels(tenant_id, user_id, include_secrets=True)
        selected = {str(channel or "").strip().lower() for channel in (channels or []) if str(channel or "").strip()}
        candidates = [config for config in configs if config.get("enabled", True)]
        if selected:
            candidates = [config for config in candidates if self._matches_push_channel(config, selected)]
        if not candidates:
            return {
                "enabled": True,
                "status": "skipped",
                "reason": "no enabled external push channels matched",
                "channels": sorted(selected),
                "deliveries": [],
            }
        deliveries = [
            external_push_service.enqueue_dispatch(
                tenant_id,
                user_id,
                config,
                notification,
                delivery_key=f"daily-review:{tenant_id}:{user_id or 0}:{notification['entity']['trade_date']}:{config.get('id') or ''}",
            )
            for config in candidates
        ]
        ok_count = sum(1 for item in deliveries if item.get("ok"))
        return {
            "enabled": True,
            "status": "queued" if ok_count == len(deliveries) else "partial" if ok_count else "failed",
            "channels": sorted(selected) if selected else ["external"],
            "deliveries": deliveries,
            "queued": ok_count,
            "sent": 0,
            "failed": len(deliveries) - ok_count,
        }

    def _matches_push_channel(self, config: dict, selected: set[str]) -> bool:
        channel_id = str(config.get("id") or "").strip().lower()
        channel_type = str(config.get("type") or "").strip().lower().replace("_", "-")
        return (
            "all" in selected
            or "external" in selected
            or channel_id in selected
            or channel_type in selected
            or f"external:{channel_id}" in selected
            or f"{channel_type}:{channel_id}" in selected
        )

    def _money(self, value: Any) -> str:
        try:
            return f"{float(value or 0):,.2f}"
        except (TypeError, ValueError):
            return "0.00"

    def _ratio_pct(self, value: Any) -> str:
        try:
            return f"{float(value or 0) * 100:.2f}%"
        except (TypeError, ValueError):
            return "0.00%"

    def _return_pct(self, value: Any) -> str:
        try:
            return f"{float(value or 0):.2f}%"
        except (TypeError, ValueError):
            return "0.00%"

    def _report_payload(self, report: dict, tenant_id: int) -> dict:
        snapshot = self._decode_snapshot(report.get("data_snapshot"))
        return {
            "id": str(report.get("id")),
            "tenant_id": tenant_id,
            "pick_id": report.get("pick_id"),
            "symbol": report.get("code"),
            "title": snapshot.get("title") or f"Research report {report.get('code')}",
            "content": report.get("research_summary") or "",
            "report_type": snapshot.get("report_type") or "research",
            "source": snapshot.get("source") or "research_reports",
            "analysis_date": report.get("analysis_date"),
            "total_score": report.get("total_score"),
            "risk_warning": report.get("risk_warning") or "",
            "action_suggestion": report.get("action_suggestion") or "",
            "created_at": report.get("created_at"),
            "updated_at": report.get("updated_at"),
        }

    def _decode_snapshot(self, value) -> dict:
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}

    def _empty_group(self, strategy: str) -> dict:
        return {
            "strategy": strategy,
            "total": 0,
            "reviewed": 0,
            "deals": 0,
            "wins": 0,
            "high_risk": 0,
            "return_sum": 0.0,
            "return_count": 0,
            "quality_counts": self._empty_quality_counts(),
        }

    def _finalize_group(self, group: dict) -> dict:
        total = group["total"]
        return_count = group["return_count"]
        return {
            "strategy": group["strategy"],
            "total": total,
            "reviewed": group["reviewed"],
            "review_rate": round(group["reviewed"] / total, 4) if total else 0,
            "deals": group["deals"],
            "wins": group["wins"],
            "return_count": return_count,
            "win_rate": round(group["wins"] / return_count, 4) if return_count else 0,
            "average_return_pct": round(group["return_sum"] / return_count, 4) if return_count else 0,
            "high_risk": group["high_risk"],
            "high_risk_rate": round(group["high_risk"] / total, 4) if total else 0,
            "data_quality": self._finalize_quality_counts(group["quality_counts"], total),
            "drilldowns": {
                "picks": {"page": "picks", "filters": {"strategy_code": group["strategy"]}},
                "reviewed": {"page": "picks", "filters": {"strategy_code": group["strategy"], "reviewed": "1"}},
                "high_risk": {"page": "picks", "filters": {"strategy_code": group["strategy"], "risk_level": "high"}},
                "backtests": {"page": "strategies", "filters": {"strategy_code": group["strategy"]}},
            },
        }

    def _strategy_feedback(self, groups: list[dict]) -> dict:
        items = []
        for group in groups:
            strategy = group.get("strategy") or "unknown"
            total = int(group.get("total") or 0)
            if total <= 0:
                continue
            review_rate = float(group.get("review_rate") or 0)
            high_risk_rate = float(group.get("high_risk_rate") or 0)
            win_rate = float(group.get("win_rate") or 0)
            average_return = float(group.get("average_return_pct") or 0)
            quality = group.get("data_quality") or {}
            fallback_rate = float(quality.get("fallback_rate") or 0)
            mock_rate = float(quality.get("mock_rate") or 0)
            if review_rate < 0.6:
                items.append(self._feedback_item(strategy, "review_gap", "medium", "先补复盘样本", f"复盘率 {review_rate:.0%}，样本尚不足以反哺策略。", group))
            if fallback_rate + mock_rate > 0.3:
                items.append(self._feedback_item(strategy, "data_quality", "high", "先修数据口径再调参", f"fallback/mock 占比 {(fallback_rate + mock_rate):.0%}，策略表现可能被行情质量污染。", group))
            if high_risk_rate > 0.25:
                items.append(self._feedback_item(strategy, "risk_control", "high", "收紧风险过滤", f"高风险占比 {high_risk_rate:.0%}，建议复查风险标签、涨跌停和停牌过滤。", group))
            if group.get("return_count", 0) and win_rate < 0.4 and average_return <= 0:
                items.append(self._feedback_item(strategy, "threshold_tuning", "medium", "回测阈值并降低开仓频率", f"胜率 {win_rate:.0%}，平均收益 {average_return:.2f}%。", group))
        priority = {"high": 0, "medium": 1, "low": 2}
        return {"schema_version": "strategy-feedback/v1", "items": sorted(items, key=lambda item: priority.get(item["severity"], 3))}

    def _feedback_item(self, strategy: str, feedback_type: str, severity: str, action: str, reason: str, group: dict) -> dict:
        return {
            "strategy": strategy,
            "type": feedback_type,
            "severity": severity,
            "action": action,
            "reason": reason,
            "metrics": {
                "total": group.get("total", 0),
                "review_rate": group.get("review_rate", 0),
                "win_rate": group.get("win_rate", 0),
                "average_return_pct": group.get("average_return_pct", 0),
                "high_risk_rate": group.get("high_risk_rate", 0),
                "data_quality": group.get("data_quality") or {},
            },
            "drilldowns": {
                "picks": {"page": "picks", "filters": {"strategy_code": strategy}},
                "backtests": {"page": "strategies", "filters": {"strategy_code": strategy}},
            },
        }

    def _empty_attribution_dimensions(self) -> dict:
        return {
            "strategy": {},
            "source": {},
            "risk_level": {},
            "data_quality": {},
            "holding_period": {},
        }

    def _add_attribution_row(
        self,
        dimensions: dict,
        *,
        strategy: str,
        source: str,
        risk_level: str,
        data_quality: str,
        holding_period: str,
        status,
        deal_status,
        return_pct: float | None,
    ) -> None:
        for dimension, key in (
            ("strategy", strategy),
            ("source", source),
            ("risk_level", risk_level),
            ("data_quality", data_quality),
            ("holding_period", holding_period),
        ):
            bucket = dimensions[dimension].setdefault(key, self._empty_attribution_bucket(key))
            bucket["total"] += 1
            bucket["quality_counts"][data_quality] += 1
            if self._is_reviewed(status):
                bucket["reviewed"] += 1
            if self._is_deal(deal_status):
                bucket["deals"] += 1
            if self._is_high_risk(risk_level):
                bucket["high_risk"] += 1
            if return_pct is None:
                continue
            bucket["return_sum"] += return_pct
            bucket["return_count"] += 1
            if return_pct > 0:
                bucket["wins"] += 1
                bucket["positive_return_sum"] += return_pct
            elif return_pct < 0:
                bucket["losses"] += 1
                bucket["negative_return_sum"] += return_pct

    def _empty_attribution_bucket(self, key: str) -> dict:
        return {
            "key": key,
            "total": 0,
            "reviewed": 0,
            "deals": 0,
            "wins": 0,
            "losses": 0,
            "high_risk": 0,
            "return_sum": 0.0,
            "positive_return_sum": 0.0,
            "negative_return_sum": 0.0,
            "return_count": 0,
            "quality_counts": self._empty_quality_counts(),
        }

    def _finalize_attribution(self, dimensions: dict, total: int, total_return: float) -> dict:
        finalized = {}
        for dimension, buckets in dimensions.items():
            items = [
                self._finalize_attribution_bucket(dimension, key, bucket, total, total_return)
                for key, bucket in buckets.items()
            ]
            finalized[dimension] = sorted(
                items,
                key=lambda item: (item["total"], abs(item["total_return_pct"])),
                reverse=True,
            )
        strategy_items = finalized.get("strategy", [])
        return {
            "schema_version": "report-attribution/v1",
            "basis": {
                "population": "active_picks",
                "return_metric": "sum_return_pct",
                "dimensions": list(finalized.keys()),
            },
            "dimensions": finalized,
            "highlights": {
                "top_positive_contributors": [
                    item for item in sorted(strategy_items, key=lambda item: item["total_return_pct"], reverse=True) if item["total_return_pct"] > 0
                ][:5],
                "top_negative_contributors": [
                    item for item in sorted(strategy_items, key=lambda item: item["total_return_pct"]) if item["total_return_pct"] < 0
                ][:5],
                "largest_sources": finalized.get("source", [])[:5],
            },
        }

    def _finalize_attribution_bucket(self, dimension: str, key: str, bucket: dict, total: int, total_return: float) -> dict:
        bucket_total = bucket["total"]
        return_count = bucket["return_count"]
        return_sum = bucket["return_sum"]
        return {
            "key": key,
            "label": key,
            "total": bucket_total,
            "total_share": round(bucket_total / total, 4) if total else 0,
            "reviewed": bucket["reviewed"],
            "review_rate": round(bucket["reviewed"] / bucket_total, 4) if bucket_total else 0,
            "deals": bucket["deals"],
            "deal_rate": round(bucket["deals"] / bucket_total, 4) if bucket_total else 0,
            "wins": bucket["wins"],
            "losses": bucket["losses"],
            "win_rate": round(bucket["wins"] / return_count, 4) if return_count else 0,
            "average_return_pct": round(return_sum / return_count, 4) if return_count else 0,
            "total_return_pct": round(return_sum, 4),
            "positive_return_pct": round(bucket["positive_return_sum"], 4),
            "negative_return_pct": round(bucket["negative_return_sum"], 4),
            "return_contribution_rate": round(return_sum / total_return, 4) if total_return else 0,
            "high_risk": bucket["high_risk"],
            "high_risk_rate": round(bucket["high_risk"] / bucket_total, 4) if bucket_total else 0,
            "data_quality": self._finalize_quality_counts(bucket["quality_counts"], bucket_total),
            "drilldown": {"page": "picks", "filters": self._attribution_filters(dimension, key)},
            "explainability": {
                "metric": "return_pct",
                "covered_return_rows": return_count,
                "missing_return_rows": bucket_total - return_count,
            },
        }

    def _attribution_filters(self, dimension: str, key: str) -> dict:
        filters = {"from_report_attribution": dimension}
        if dimension == "strategy":
            filters["strategy_code"] = key
        elif dimension == "source":
            filters["source"] = key
        elif dimension == "risk_level":
            filters["risk_level"] = key
        elif dimension == "data_quality":
            filters["data_quality"] = key
        elif dimension == "holding_period":
            filters["holding_period"] = key
        return filters

    def _empty_quality_counts(self) -> dict:
        return {"primary": 0, "fallback": 0, "mock": 0, "unknown": 0}

    def _quality_bucket(self, row: dict) -> str:
        quality = str(row.get("data_quality") or "").strip().lower()
        source = str(row.get("market_data_source") or row.get("source_channel") or row.get("source") or "").strip().lower()
        fallback_value = row.get("fallback_used")
        fallback_used = fallback_value if isinstance(fallback_value, bool) else str(fallback_value or "").strip().lower() in {"1", "true", "yes", "y", "on"}
        if fallback_used:
            return "fallback"
        if quality == "fallback" or "fallback" in source:
            return "fallback"
        if quality == "mock" or "mock" in source:
            return "mock"
        if quality in {"primary", "real", "live"}:
            return "primary"
        return "unknown"

    def _bucket_value(self, value, default: str = "unknown") -> str:
        text = str(value or "").strip()
        return text or default

    def _risk_bucket(self, row: dict) -> str:
        value = self._bucket_value(row.get("result_grade"))
        return value.lower() if value.isascii() else value

    def _holding_days_bucket(self, value) -> str:
        try:
            days = int(value)
        except (TypeError, ValueError):
            return "unrealized"
        if days <= 3:
            return "0-3d"
        if days <= 7:
            return "4-7d"
        if days <= 20:
            return "8-20d"
        return "20d+"

    def _float_or_none(self, value) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _is_reviewed(self, status) -> bool:
        return str(status or "").strip().lower() in self.REVIEWED_STATUSES

    def _is_deal(self, deal_status) -> bool:
        return str(deal_status or "").strip().lower() in {"dealt", "filled", "done", "closed", "\u5df2\u6210\u4ea4"}

    def _is_high_risk(self, risk) -> bool:
        return str(risk or "").strip().lower() in {"high", "\u9ad8", "\u9ad8\u98ce\u9669"}

    def _finalize_quality_counts(self, counts: dict, total: int) -> dict:
        return {
            "primary": int(counts.get("primary", 0)),
            "fallback": int(counts.get("fallback", 0)),
            "mock": int(counts.get("mock", 0)),
            "unknown": int(counts.get("unknown", 0)),
            "primary_rate": round(counts.get("primary", 0) / total, 4) if total else 0,
            "fallback_rate": round(counts.get("fallback", 0) / total, 4) if total else 0,
            "mock_rate": round(counts.get("mock", 0) / total, 4) if total else 0,
            "unknown_rate": round(counts.get("unknown", 0) / total, 4) if total else 0,
        }
