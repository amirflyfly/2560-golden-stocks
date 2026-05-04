"""Application service for research report API endpoints."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from backend.application.pagination import PaginationParams
from backend.core.errors import AppError, NotFoundError
from backend.repositories import picks_repo


class ReportApiService:
    REVIEWED_STATUSES = {"validated", "rejected", "reviewed", "done"}

    def list_reports(self, tenant_id: int, pagination: PaginationParams, symbol: str | None = None) -> dict:
        where = "WHERE code=?" if symbol else ""
        args = [symbol] if symbol else []
        picks = picks_repo.list_picks(
            where,
            args,
            limit=pagination.page_size,
            offset=(pagination.page - 1) * pagination.page_size,
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
        pick = self._find_or_create_report_pick(symbol, title)
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
        rows = picks_repo.list_picks("WHERE COALESCE(archived,0)=0", [], limit=1000)
        groups: dict[str, dict] = {}
        total_return = 0.0
        return_count = 0
        high_risk_count = 0
        reviewed_count = 0
        deal_count = 0
        win_count = 0
        quality_counts = self._empty_quality_counts()

        for row in rows:
            strategy = row.get("strategy_name") or row.get("source") or "unknown"
            group = groups.setdefault(strategy, self._empty_group(strategy))
            group["total"] += 1
            status = row.get("review_status") or ""
            deal_status = row.get("deal_status") or ""
            risk = row.get("result_grade") or ""
            return_pct = row.get("return_pct")
            quality_bucket = self._quality_bucket(row)
            quality_counts[quality_bucket] += 1
            group["quality_counts"][quality_bucket] += 1

            if status in self.REVIEWED_STATUSES:
                reviewed_count += 1
                group["reviewed"] += 1
            if deal_status in {"dealt", "已成交"}:
                deal_count += 1
                group["deals"] += 1
            if str(risk).lower() == "high":
                high_risk_count += 1
                group["high_risk"] += 1
            if return_pct is not None:
                numeric_return = float(return_pct)
                total_return += numeric_return
                return_count += 1
                group["return_sum"] += numeric_return
                group["return_count"] += 1
                if numeric_return > 0:
                    win_count += 1
                    group["wins"] += 1

        group_items = [self._finalize_group(group) for group in groups.values()]
        total = len(rows)
        return {
            "tenant_id": tenant_id,
            "period": normalized_period,
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
            "drilldowns": {
                "picks": {"page": "picks", "filters": {"from_report_period": normalized_period}},
                "reviewed": {"page": "picks", "filters": {"status": "reviewed", "from_report_period": normalized_period}},
                "deals": {"page": "picks", "filters": {"deal_status": "dealt", "from_report_period": normalized_period}},
                "high_risk": {"page": "picks", "filters": {"risk_level": "high", "from_report_period": normalized_period}},
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
        return {
            "filename": filename,
            "content_type": "text/csv; charset=utf-8",
            "body": output.getvalue(),
        }

    def _find_or_create_report_pick(self, symbol: str, title: str) -> dict:
        existing = picks_repo.list_picks("WHERE code=?", [symbol], limit=1)
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
        )
        pick = picks_repo.get_pick_by_unique(today, symbol, "api_report")
        if not pick:
            raise AppError("failed to create report pick")
        return pick

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
            "win_rate": round(group["wins"] / return_count, 4) if return_count else 0,
            "average_return_pct": round(group["return_sum"] / return_count, 4) if return_count else 0,
            "high_risk": group["high_risk"],
            "high_risk_rate": round(group["high_risk"] / total, 4) if total else 0,
            "data_quality": self._finalize_quality_counts(group["quality_counts"], total),
            "drilldowns": {
                "picks": {"page": "picks", "filters": {"strategy_code": group["strategy"]}},
                "reviewed": {"page": "picks", "filters": {"strategy_code": group["strategy"], "status": "reviewed"}},
                "high_risk": {"page": "picks", "filters": {"strategy_code": group["strategy"], "risk_level": "high"}},
                "backtests": {"page": "strategies", "filters": {"strategy_code": group["strategy"]}},
            },
        }

    def _empty_quality_counts(self) -> dict:
        return {"primary": 0, "fallback": 0, "mock": 0, "unknown": 0}

    def _quality_bucket(self, row: dict) -> str:
        quality = str(row.get("data_quality") or "").strip().lower()
        source = str(row.get("market_data_source") or row.get("source_channel") or row.get("source") or "").strip().lower()
        if row.get("fallback_used"):
            return "fallback"
        if quality == "fallback" or "fallback" in source:
            return "fallback"
        if quality == "mock" or "mock" in source:
            return "mock"
        if quality in {"primary", "real", "live"}:
            return "primary"
        return "unknown"

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
