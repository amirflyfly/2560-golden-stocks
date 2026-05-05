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
        rows = picks_repo.list_picks("WHERE COALESCE(archived,0)=0", [], limit=1000, tenant_id=tenant_id)
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
            "attribution": attribution,
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
        if row.get("fallback_used"):
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
