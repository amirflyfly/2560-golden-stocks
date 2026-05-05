"""Application service for pick API endpoints."""

from __future__ import annotations

from datetime import date

from backend.application.pagination import PaginationParams
from backend.core.errors import AppError
from backend.repositories import picks_repo


def _row_to_pick(row: dict, tenant_id: int) -> dict:
    return {
        "id": row.get("id"),
        "tenant_id": tenant_id,
        "symbol": row.get("code"),
        "stock_name": row.get("name"),
        "trade_date": row.get("pick_date"),
        "source": row.get("source"),
        "source_channel": row.get("source_channel"),
        "strategy_code": row.get("strategy_name"),
        "status": row.get("review_status") or "accepted",
        "deal_status": row.get("deal_status"),
        "risk_level": row.get("result_grade"),
        "watch_flag": bool(row.get("watch_flag")),
        "reason": row.get("reason_tag") or row.get("note") or "",
        "note": row.get("note") or "",
        "review_comment": row.get("review_comment") or "",
        "return_pct": row.get("return_pct"),
        "max_return_pct": row.get("max_return_pct"),
        "drawdown_pct": row.get("drawdown_pct"),
        "holding_days": row.get("holding_days"),
        "validation_result": row.get("validation_result") or "",
        "validation_note": row.get("validation_note") or "",
        "validated_at": row.get("validated_at") or "",
        "data_quality": row.get("data_quality") or "",
        "market_data_source": row.get("market_data_source") or "",
        "fallback_used": bool(row.get("fallback_used")),
        "created_at": row.get("created_at"),
    }


class PickApiService:
    def get_pick(self, tenant_id: int, pick_id: int) -> dict | None:
        row = picks_repo.get_pick_by_id(pick_id, tenant_id=tenant_id)
        return _row_to_pick(row, tenant_id) if row else None

    def list_picks(self, tenant_id: int, pagination: PaginationParams, filters: dict | None = None) -> dict:
        filters = filters or {}
        where = ["COALESCE(archived,0)=0"]
        args: list = []

        status = (filters.get("status") or "").strip()
        if status and status != "all":
            where.append("COALESCE(review_status,'accepted')=?")
            args.append(status)

        strategy_code = (filters.get("strategy_code") or filters.get("strategy") or "").strip()
        if strategy_code and strategy_code != "all":
            where.append("strategy_name=?")
            args.append(strategy_code)

        risk_level = (filters.get("risk_level") or filters.get("risk") or "").strip()
        if risk_level and risk_level != "all":
            where.append("result_grade=?")
            args.append(risk_level)

        source = (filters.get("source") or "").strip()
        if source and source != "all":
            where.append("source=?")
            args.append(source)

        symbol = (filters.get("symbol") or filters.get("code") or "").strip()
        if symbol:
            where.append("code=?")
            args.append(symbol)

        from_date = self._optional_date(filters.get("from_date"), "from_date")
        if from_date:
            where.append("pick_date>=?")
            args.append(from_date)

        to_date = self._optional_date(filters.get("to_date"), "to_date")
        if to_date:
            where.append("pick_date<=?")
            args.append(to_date)

        where_sql = "WHERE " + " AND ".join(where)
        rows = picks_repo.list_picks(where_sql, args, limit=pagination.page_size, offset=pagination.offset, tenant_id=tenant_id)
        total = picks_repo.count_picks(where_sql, args, tenant_id=tenant_id)
        return {
            "items": [_row_to_pick(row, tenant_id) for row in rows],
            "total": total,
            "page": pagination.page,
            "page_size": pagination.page_size,
            "tenant_id": tenant_id,
        }

    def create_pick(self, tenant_id: int, payload: dict) -> dict:
        symbol = (payload.get("symbol") or payload.get("code") or "").strip()
        if not symbol:
            raise AppError("missing symbol")

        trade_date = payload.get("trade_date") or payload.get("pick_date") or date.today().isoformat()
        source = payload.get("source") or "manual"
        strategy_code = payload.get("strategy_code") or payload.get("strategy_name") or source or "manual"
        reason = payload.get("reason") or payload.get("reason_tag") or ""
        note = payload.get("note") or payload.get("action_suggestion") or ""
        stock_name = payload.get("stock_name") or payload.get("name") or symbol

        pick_price = payload.get("pick_price") or payload.get("last_price") or payload.get("price")
        source_channel = payload.get("source_channel") or "api"
        review_status = payload.get("status") or "accepted"
        review_comment = payload.get("review_comment") or ""
        result_grade = payload.get("risk_level") or payload.get("result_grade") or "pending"
        inquiry_count = int(payload.get("inquiry_count") or 0)
        deal_status = payload.get("deal_status") or "pending"
        secondary_spread = payload.get("secondary_spread") or "unknown"
        market_data = payload.get("market_data") if isinstance(payload.get("market_data"), dict) else {}
        data_quality = payload.get("data_quality") or market_data.get("data_quality") or ""
        market_data_source = (
            payload.get("market_data_source")
            or payload.get("actual_provider")
            or market_data.get("actual_provider")
            or market_data.get("provider")
            or ""
        )
        fallback_used = bool(payload.get("fallback_used", market_data.get("fallback_used", False)))

        existing = picks_repo.get_pick_by_unique(trade_date, symbol, source, tenant_id=tenant_id)
        if existing:
            picks_repo.update_pick_api_fields(
                existing["id"],
                name=stock_name,
                pick_price=pick_price,
                signal=payload.get("signal") or "",
                source_channel=source_channel,
                reason_tag=reason,
                note=note,
                review_status=review_status,
                review_comment=review_comment,
                result_grade=result_grade,
                inquiry_count=inquiry_count,
                deal_status=deal_status,
                secondary_spread=secondary_spread,
                strategy_name=strategy_code,
                data_quality=data_quality,
                market_data_source=market_data_source,
                fallback_used=fallback_used,
                tenant_id=tenant_id,
            )
            pick_id = existing["id"]
        else:
            created_id = picks_repo.create_or_replace_pick(
                trade_date,
                symbol,
                stock_name,
                pick_price,
                payload.get("signal") or "",
                source,
                source_channel,
                reason,
                note,
                review_status,
                review_comment,
                payload.get("content_title") or "",
                payload.get("content_ref") or "",
                result_grade,
                inquiry_count,
                deal_status,
                secondary_spread,
                strategy_code,
                data_quality,
                market_data_source,
                fallback_used,
                tenant_id=tenant_id,
            )
            pick_id = int(created_id) if created_id else picks_repo.last_inserted_id()
        row = picks_repo.get_pick_by_id(pick_id, tenant_id=tenant_id) if pick_id else None
        if row:
            return _row_to_pick(row, tenant_id)
        return {
            "id": pick_id,
            "tenant_id": tenant_id,
            "symbol": symbol,
            "stock_name": stock_name,
            "trade_date": trade_date,
            "source": source,
            "strategy_code": strategy_code,
            "status": "accepted",
        }

    def update_review(self, tenant_id: int, pick_id: int, payload: dict) -> dict | None:
        row = picks_repo.get_pick_by_id(pick_id, tenant_id=tenant_id)
        if not row:
            return None
        current = _row_to_pick(row, tenant_id)
        review_status = payload.get("status") or payload.get("review_status") or current["status"] or "pending"
        result_grade = payload.get("risk_level") or payload.get("result_grade") or current["risk_level"] or "pending"
        deal_status = payload.get("deal_status") or current["deal_status"] or "pending"
        review_comment = payload.get("review_comment") if payload.get("review_comment") is not None else current["review_comment"]
        validation_result = payload.get("validation_result") if payload.get("validation_result") is not None else current["validation_result"]
        validation_note = payload.get("validation_note") if payload.get("validation_note") is not None else current["validation_note"]
        watch_flag = bool(payload.get("watch_flag", current["watch_flag"]))
        picks_repo.update_review_fields(
            pick_id,
            review_status=review_status,
            review_comment=review_comment or "",
            result_grade=result_grade,
            deal_status=deal_status,
            return_pct=self._optional_float(payload.get("return_pct"), current["return_pct"]),
            max_return_pct=self._optional_float(payload.get("max_return_pct"), current["max_return_pct"]),
            drawdown_pct=self._optional_float(payload.get("drawdown_pct"), current["drawdown_pct"]),
            holding_days=self._optional_int(payload.get("holding_days"), current["holding_days"]),
            validation_result=validation_result or "",
            validation_note=validation_note or "",
            watch_flag=watch_flag,
            tenant_id=tenant_id,
        )
        updated = picks_repo.get_pick_by_id(pick_id, tenant_id=tenant_id)
        return _row_to_pick(updated, tenant_id) if updated else None

    def batch_update_review(self, tenant_id: int, pick_ids: list[int], payload: dict) -> dict:
        if not pick_ids:
            raise AppError("missing pick ids")
        unique_ids = []
        seen = set()
        for raw_id in pick_ids:
            try:
                pick_id = int(raw_id)
            except (TypeError, ValueError) as exc:
                raise AppError("invalid pick id") from exc
            if pick_id > 0 and pick_id not in seen:
                seen.add(pick_id)
                unique_ids.append(pick_id)

        updated_items = []
        missing_ids = []
        for pick_id in unique_ids:
            item = self.update_review(tenant_id, pick_id, payload)
            if item is None:
                missing_ids.append(pick_id)
            else:
                updated_items.append(item)
        return {
            "tenant_id": tenant_id,
            "updated": len(updated_items),
            "missing_ids": missing_ids,
            "items": updated_items,
        }

    def get_timeline(self, tenant_id: int, pick_id: int) -> dict | None:
        row = picks_repo.get_pick_by_id(pick_id, tenant_id=tenant_id)
        if not row:
            return None
        pick = _row_to_pick(row, tenant_id)
        items = [
            {
                "event_type": "created",
                "title": "加入选股池",
                "description": pick.get("reason") or "候选标的入池",
                "at": pick.get("created_at") or pick.get("trade_date"),
            }
        ]
        if pick.get("watch_flag"):
            items.append({
                "event_type": "watching",
                "title": "进入观察",
                "description": pick.get("note") or pick.get("reason") or "",
                "at": pick.get("validated_at") or pick.get("created_at"),
            })
        if pick.get("status") and pick.get("status") != "accepted":
            items.append({
                "event_type": "review",
                "title": f"复盘状态：{pick.get('status')}",
                "description": pick.get("review_comment") or pick.get("validation_note") or "",
                "at": pick.get("validated_at") or pick.get("created_at"),
            })
        if pick.get("deal_status"):
            items.append({
                "event_type": "deal",
                "title": f"成交状态：{pick.get('deal_status')}",
                "description": f"收益 {pick.get('return_pct') if pick.get('return_pct') is not None else '-'}",
                "at": pick.get("validated_at") or pick.get("created_at"),
            })
        return {"tenant_id": tenant_id, "pick_id": pick_id, "items": items}

    def _optional_float(self, value, default):
        if value in (None, ""):
            return default
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise AppError("invalid numeric review field") from exc

    def _optional_int(self, value, default):
        if value in (None, ""):
            return default
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise AppError("invalid integer review field") from exc

    def _optional_date(self, value, field: str) -> str:
        if value in (None, ""):
            return ""
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError as exc:
            raise AppError(f"invalid {field}, expected YYYY-MM-DD") from exc
