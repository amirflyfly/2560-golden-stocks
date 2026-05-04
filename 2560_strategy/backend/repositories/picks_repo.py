"""Picks repository.

Provides a compatibility layer over the legacy SQLite picks table and the
refactored MySQL picks table. The public function signatures stay stable so the
existing API/services can migrate without a broad rewrite.
"""

from __future__ import annotations

import os
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text

from backend.core.config import get_settings
from backend.db.models.strategy import Pick, ResearchReport, Strategy
from backend.db.session import session_scope
from backend.repositories.db import execute as sqlite_execute
from backend.repositories.db import execute_many as sqlite_execute_many
from backend.repositories.db import q as sqlite_q
from backend.repositories.db import q1 as sqlite_q1


DEFAULT_TENANT_ID = int(os.getenv("PICKS_DEFAULT_TENANT_ID", "1"))
_MYSQL_LAST_INSERTED_PICK_ID: int | None = None
_MYSQL_RESEARCH_REPORTS_SUPPORTED: bool | None = None
_MYSQL_COMPAT_SELECT = """
SELECT
    p.id AS id,
    p.tenant_id AS tenant_id,
    p.symbol AS code,
    p.stock_name AS name,
    p.trade_date AS pick_date,
    p.source AS source,
    p.source_channel AS source_channel,
    COALESCE(s.code, JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.strategy_name')), '') AS strategy_name,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.reason_tag')), p.reason, '') AS reason_tag,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.note')), '') AS note,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.pick_price')), '') AS pick_price,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.signal')), '') AS `signal`,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.content_title')), '') AS content_title,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.content_ref')), '') AS content_ref,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.ma25')), '') AS ma25,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.vol_ratio')), '') AS vol_ratio,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.inquiry_count')), '') AS inquiry_count,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.secondary_spread')), '') AS secondary_spread,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.last_price')), '') AS last_price,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.quote_time')), '') AS quote_time,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.first_board_time')), '') AS first_board_time,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.theme_reason')), '') AS theme_reason,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.second_board_expectation')), '') AS second_board_expectation,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.second_board_score')), '') AS second_board_score,
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.legacy_payload_json, '$.prediction_reason')), '') AS prediction_reason,
    p.status AS review_status,
    p.review_comment AS review_comment,
    p.risk_level AS result_grade,
    p.deal_status AS deal_status,
    p.return_pct AS return_pct,
    p.max_return_pct AS max_return_pct,
    p.drawdown_pct AS drawdown_pct,
    p.holding_days AS holding_days,
    p.watch_flag AS watch_flag,
    p.validation_result AS validation_result,
    p.validation_note AS validation_note,
    p.validated_at AS validated_at,
    p.data_quality AS data_quality,
    p.market_data_source AS market_data_source,
    p.fallback_used AS fallback_used,
    p.created_at AS created_at,
    p.updated_at AS updated_at,
    CASE WHEN p.deleted_at IS NULL THEN 0 ELSE 1 END AS archived,
    p.legacy_payload_json AS legacy_payload_json
FROM picks p
LEFT JOIN strategies s ON s.id = p.strategy_id
WHERE p.tenant_id = :tenant_id
"""


def _repo_backend() -> str:
    forced = (os.getenv("PICKS_REPOSITORY_BACKEND") or "auto").strip().lower()
    if forced in {"sqlite", "mysql"}:
        return forced
    settings = get_settings()
    environment = (settings.environment or "").strip().lower()
    if environment in {"prod", "production"}:
        return "mysql"
    return "sqlite"


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _coerce_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value))


def _coerce_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _coerce_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return value


_UNSET = object()


def _merge_legacy_payload(existing: dict[str, Any] | None = None, **updates: Any) -> dict[str, Any]:
    payload = dict(existing or {})
    for key, value in updates.items():
        if value is _UNSET:
            continue
        if value is None:
            payload.pop(key, None)
            continue
        payload[key] = _normalize_scalar(value)
    return payload


def _build_mysql_pick_dict(row: dict[str, Any]) -> dict[str, Any]:
    normalized = {key: _normalize_scalar(value) for key, value in row.items()}
    legacy_payload = normalized.get("legacy_payload_json")
    if isinstance(legacy_payload, str) and legacy_payload.strip():
        try:
            normalized["legacy_payload_json"] = json.loads(legacy_payload)
        except json.JSONDecodeError:
            normalized["legacy_payload_json"] = {}
    normalized["watch_flag"] = _coerce_bool(normalized.get("watch_flag"))
    normalized["fallback_used"] = _coerce_bool(normalized.get("fallback_used"))
    normalized["archived"] = 1 if _coerce_bool(normalized.get("archived")) else 0
    return normalized


def _mysql_text(sql: str, args: list[Any] | tuple[Any, ...] | None = None):
    args = list(args or [])
    params: dict[str, Any] = {}
    parts: list[str] = []
    for index, chunk in enumerate(sql.split("?")):
        parts.append(chunk)
        if index < len(args):
            name = f"p{index}"
            parts.append(f":{name}")
            params[name] = args[index]
    return text("".join(parts)), params


def _mysql_select_all(sql: str, args: list[Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    query, params = _mysql_text(sql, args)
    params.setdefault("tenant_id", DEFAULT_TENANT_ID)
    with session_scope() as session:
        rows = session.execute(query, params).mappings().all()
    return [_build_mysql_pick_dict(dict(row)) for row in rows]


def _mysql_select_one(sql: str, args: list[Any] | tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    rows = _mysql_select_all(sql, args)
    return rows[0] if rows else None


def _compat_select_sql(where_sql: str = "", order_by: str = " ORDER BY pick_date DESC, id DESC") -> str:
    where_sql = f" {where_sql.strip()}" if where_sql and where_sql.strip() else ""
    return f"SELECT * FROM ({_MYSQL_COMPAT_SELECT}) AS picks_compat{where_sql}{order_by}"


def _resolve_strategy_id(session, strategy_name: str | None) -> int | None:
    strategy_code = (strategy_name or "").strip()
    if not strategy_code:
        return None
    strategy = session.execute(
        select(Strategy).where(
            Strategy.tenant_id == DEFAULT_TENANT_ID,
            Strategy.code == strategy_code,
            Strategy.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    return strategy.id if strategy else None


def _get_pick_model(session, rid: int) -> Pick | None:
    return session.execute(
        select(Pick).where(Pick.id == int(rid), Pick.tenant_id == DEFAULT_TENANT_ID)
    ).scalar_one_or_none()


def _get_pick_model_by_unique(session, pick_date: Any, code: str, source: str) -> Pick | None:
    trade_date = _coerce_date(pick_date)
    return session.execute(
        select(Pick).where(
            Pick.tenant_id == DEFAULT_TENANT_ID,
            Pick.trade_date == trade_date,
            Pick.symbol == code,
            Pick.source == source,
        )
    ).scalar_one_or_none()


def _hydrate_pick_model(
    pick: Pick,
    *,
    pick_date: Any | None = None,
    code: str | None = None,
    name: str | None = None,
    source: str | None = None,
    source_channel: str | None = None,
    reason_tag: str | None = None,
    note: str | None = None,
    pick_price: Any | None = None,
    signal: str | None = None,
    content_title: str | None = None,
    content_ref: str | None = None,
    review_status: str | None = None,
    review_comment: str | None = None,
    result_grade: str | None = None,
    inquiry_count: Any | None = None,
    deal_status: str | None = None,
    secondary_spread: Any | None = None,
    strategy_name: str | None = None,
    data_quality: str | None = None,
    market_data_source: str | None = None,
    fallback_used: bool | None = None,
    return_pct: Any | None = None,
    max_return_pct: Any | None = None,
    drawdown_pct: Any | None = None,
    holding_days: Any | None = None,
    validation_result: str | None = None,
    validation_note: str | None = None,
    watch_flag: bool | None = None,
    archived: bool | None = None,
    legacy_updates: dict[str, Any] | None = None,
) -> None:
    if pick_date is not None:
        pick.trade_date = _coerce_date(pick_date)
    if code is not None:
        pick.symbol = code
    if name is not None:
        pick.stock_name = name
    if source is not None:
        pick.source = source
    if source_channel is not None:
        pick.source_channel = source_channel
    if reason_tag is not None or note is not None:
        pick.reason = (reason_tag if reason_tag not in (None, "") else note) or ""
    if review_status is not None:
        pick.status = review_status
    if review_comment is not None:
        pick.review_comment = review_comment
    if result_grade is not None:
        pick.risk_level = result_grade
    if deal_status is not None:
        pick.deal_status = deal_status
    if data_quality is not None:
        pick.data_quality = data_quality
    if market_data_source is not None:
        pick.market_data_source = market_data_source
    if fallback_used is not None:
        pick.fallback_used = bool(fallback_used)
    if return_pct is not None:
        pick.return_pct = _coerce_decimal(return_pct)
    if max_return_pct is not None:
        pick.max_return_pct = _coerce_decimal(max_return_pct)
    if drawdown_pct is not None:
        pick.drawdown_pct = _coerce_decimal(drawdown_pct)
    if holding_days is not None:
        pick.holding_days = int(holding_days) if holding_days not in ("", None) else None
    if validation_result is not None:
        pick.validation_result = validation_result
    if validation_note is not None:
        pick.validation_note = validation_note
    if watch_flag is not None:
        pick.watch_flag = bool(watch_flag)
    if archived is not None:
        pick.deleted_at = datetime.now() if archived else None

    payload_updates = {
        "reason_tag": reason_tag if reason_tag is not None else _UNSET,
        "note": note if note is not None else _UNSET,
        "pick_price": pick_price if pick_price is not None else _UNSET,
        "signal": signal if signal is not None else _UNSET,
        "content_title": content_title if content_title is not None else _UNSET,
        "content_ref": content_ref if content_ref is not None else _UNSET,
        "inquiry_count": inquiry_count if inquiry_count is not None else _UNSET,
        "secondary_spread": secondary_spread if secondary_spread is not None else _UNSET,
        "strategy_name": strategy_name if strategy_name is not None else _UNSET,
    }
    if legacy_updates:
        payload_updates.update(legacy_updates)
    pick.legacy_payload_json = _merge_legacy_payload(pick.legacy_payload_json, **payload_updates)


def _mysql_research_reports_supported() -> bool:
    global _MYSQL_RESEARCH_REPORTS_SUPPORTED
    if _MYSQL_RESEARCH_REPORTS_SUPPORTED is True:
        return True
    if _MYSQL_RESEARCH_REPORTS_SUPPORTED is False:
        raise RuntimeError("MySQL research_reports table is required but unavailable")
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1 FROM research_reports LIMIT 1"))
        _MYSQL_RESEARCH_REPORTS_SUPPORTED = True
    except Exception as exc:
        _MYSQL_RESEARCH_REPORTS_SUPPORTED = False
        raise RuntimeError("MySQL research_reports table is required but unavailable") from exc
    return True


def get_pick_by_id(rid):
    if _repo_backend() == "sqlite":
        return sqlite_q1("SELECT * FROM picks WHERE id=?", (rid,))
    return _mysql_select_one(_compat_select_sql("WHERE id=?") + " LIMIT 1", [int(rid)])


def get_pick_by_unique(pick_date, code, source):
    if _repo_backend() == "sqlite":
        return sqlite_q1(
            "SELECT * FROM picks WHERE pick_date=? AND code=? AND source=?",
            (pick_date, code, source),
        )
    return _mysql_select_one(
        _compat_select_sql("WHERE pick_date=? AND code=? AND source=?", order_by="") + " LIMIT 1",
        [pick_date, code, source],
    )


def list_picks(where_sql="", args=None, limit=None, offset=None):
    args = args or []
    if _repo_backend() == "sqlite":
        sql = f"SELECT * FROM picks {where_sql} ORDER BY pick_date DESC, id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            args = list(args) + [int(limit)]
        if offset is not None:
            sql += " OFFSET ?"
            args = list(args) + [int(offset)]
        return sqlite_q(sql, args)

    sql = _compat_select_sql(where_sql)
    bound_args = list(args)
    if limit is not None:
        sql += " LIMIT ?"
        bound_args.append(int(limit))
    if offset is not None:
        sql += " OFFSET ?"
        bound_args.append(int(offset))
    return _mysql_select_all(sql, bound_args)


def create_or_replace_pick(
    pick_date,
    code,
    name,
    pick_price,
    signal,
    source,
    source_channel,
    reason_tag,
    note,
    review_status,
    review_comment,
    content_title,
    content_ref,
    result_grade,
    inquiry_count,
    deal_status,
    secondary_spread,
    strategy_name="2560",
    data_quality="",
    market_data_source="",
    fallback_used=False,
):
    global _MYSQL_LAST_INSERTED_PICK_ID
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            """INSERT OR REPLACE INTO picks
            (pick_date, code, name, pick_price, signal, source, source_channel, reason_tag, note,
             review_status, review_comment, content_title, content_ref, archived,
             result_grade, inquiry_count, deal_status, secondary_spread, strategy_name,
             data_quality, market_data_source, fallback_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pick_date,
                code,
                name,
                pick_price,
                signal,
                source,
                source_channel,
                reason_tag,
                note,
                review_status,
                review_comment,
                content_title,
                content_ref,
                result_grade,
                inquiry_count,
                deal_status,
                secondary_spread,
                strategy_name,
                data_quality,
                market_data_source,
                1 if fallback_used else 0,
            ),
        )

    with session_scope() as session:
        pick = _get_pick_model_by_unique(session, pick_date, code, source)
        if pick is None:
            pick = Pick(
                tenant_id=DEFAULT_TENANT_ID,
                symbol=code,
                trade_date=_coerce_date(pick_date),
                source=source,
                status=review_status or "accepted",
                created_by=None,
                strategy_id=_resolve_strategy_id(session, strategy_name),
            )
            session.add(pick)
        else:
            pick.strategy_id = _resolve_strategy_id(session, strategy_name)
        _hydrate_pick_model(
            pick,
            pick_date=pick_date,
            code=code,
            name=name,
            source=source,
            source_channel=source_channel,
            reason_tag=reason_tag,
            note=note,
            pick_price=pick_price,
            signal=signal,
            content_title=content_title,
            content_ref=content_ref,
            review_status=review_status or "accepted",
            review_comment=review_comment or "",
            result_grade=result_grade,
            inquiry_count=inquiry_count,
            deal_status=deal_status,
            secondary_spread=secondary_spread,
            strategy_name=strategy_name,
            data_quality=data_quality or "",
            market_data_source=market_data_source or "",
            fallback_used=bool(fallback_used),
            archived=False,
        )
        session.flush()
        _MYSQL_LAST_INSERTED_PICK_ID = pick.id
    return 1


def update_pick(
    rid,
    pick_date,
    code,
    name,
    pick_price,
    signal,
    source_channel,
    reason_tag,
    note,
    review_status,
    review_comment,
    content_title,
    content_ref,
    result_grade,
    inquiry_count,
    deal_status,
    secondary_spread,
    strategy_name="2560",
):
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            """UPDATE picks SET
                pick_date=?, code=?, name=?, pick_price=?, signal=?,
                source_channel=?, reason_tag=?, note=?, review_status=?, review_comment=?,
                content_title=?, content_ref=?, result_grade=?, inquiry_count=?, deal_status=?, secondary_spread=?, strategy_name=?
               WHERE id=?""",
            (
                pick_date,
                code,
                name,
                pick_price,
                signal,
                source_channel,
                reason_tag,
                note,
                review_status,
                review_comment,
                content_title,
                content_ref,
                result_grade,
                inquiry_count,
                deal_status,
                secondary_spread,
                strategy_name,
                rid,
            ),
        )

    with session_scope() as session:
        pick = _get_pick_model(session, rid)
        if pick is None:
            return 0
        pick.strategy_id = _resolve_strategy_id(session, strategy_name)
        _hydrate_pick_model(
            pick,
            pick_date=pick_date,
            code=code,
            name=name,
            source_channel=source_channel,
            reason_tag=reason_tag,
            note=note,
            pick_price=pick_price,
            signal=signal,
            content_title=content_title,
            content_ref=content_ref,
            review_status=review_status,
            review_comment=review_comment,
            result_grade=result_grade,
            inquiry_count=inquiry_count,
            deal_status=deal_status,
            secondary_spread=secondary_spread,
            strategy_name=strategy_name,
        )
        session.flush()
    return 1


def update_pick_api_fields(
    rid,
    *,
    name,
    pick_price,
    signal,
    source_channel,
    reason_tag,
    note,
    review_status,
    review_comment,
    result_grade,
    inquiry_count,
    deal_status,
    secondary_spread,
    strategy_name="2560",
    data_quality="",
    market_data_source="",
    fallback_used=False,
):
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            """UPDATE picks SET
                name=?, pick_price=?, signal=?, source_channel=?, reason_tag=?, note=?,
                review_status=?, review_comment=?, result_grade=?, inquiry_count=?,
                deal_status=?, secondary_spread=?, strategy_name=?,
                data_quality=?, market_data_source=?, fallback_used=?
               WHERE id=?""",
            (
                name,
                pick_price,
                signal,
                source_channel,
                reason_tag,
                note,
                review_status,
                review_comment,
                result_grade,
                inquiry_count,
                deal_status,
                secondary_spread,
                strategy_name,
                data_quality,
                market_data_source,
                1 if fallback_used else 0,
                rid,
            ),
        )

    with session_scope() as session:
        pick = _get_pick_model(session, rid)
        if pick is None:
            return 0
        pick.strategy_id = _resolve_strategy_id(session, strategy_name)
        _hydrate_pick_model(
            pick,
            name=name,
            pick_price=pick_price,
            signal=signal,
            source_channel=source_channel,
            reason_tag=reason_tag,
            note=note,
            review_status=review_status,
            review_comment=review_comment,
            result_grade=result_grade,
            inquiry_count=inquiry_count,
            deal_status=deal_status,
            secondary_spread=secondary_spread,
            strategy_name=strategy_name,
            data_quality=data_quality,
            market_data_source=market_data_source,
            fallback_used=bool(fallback_used),
        )
        session.flush()
    return 1


def update_review_fields(
    rid,
    *,
    review_status,
    review_comment,
    result_grade,
    deal_status,
    return_pct,
    max_return_pct,
    drawdown_pct,
    holding_days,
    validation_result,
    validation_note,
    watch_flag,
):
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            """UPDATE picks SET
                review_status=?, review_comment=?, result_grade=?, deal_status=?,
                return_pct=?, max_return_pct=?, drawdown_pct=?, holding_days=?,
                validation_result=?, validation_note=?, watch_flag=?, validated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                review_status,
                review_comment,
                result_grade,
                deal_status,
                return_pct,
                max_return_pct,
                drawdown_pct,
                holding_days,
                validation_result,
                validation_note,
                1 if watch_flag else 0,
                rid,
            ),
        )

    with session_scope() as session:
        pick = _get_pick_model(session, rid)
        if pick is None:
            return 0
        _hydrate_pick_model(
            pick,
            review_status=review_status,
            review_comment=review_comment,
            result_grade=result_grade,
            deal_status=deal_status,
            return_pct=return_pct,
            max_return_pct=max_return_pct,
            drawdown_pct=drawdown_pct,
            holding_days=holding_days,
            validation_result=validation_result,
            validation_note=validation_note,
            watch_flag=watch_flag,
        )
        pick.validated_at = datetime.now()
        session.flush()
    return 1


def set_archived(rid, archived: bool):
    if _repo_backend() == "sqlite":
        return sqlite_execute("UPDATE picks SET archived=? WHERE id=?", (1 if archived else 0, rid))
    with session_scope() as session:
        pick = _get_pick_model(session, rid)
        if pick is None:
            return 0
        pick.deleted_at = datetime.now() if archived else None
        session.flush()
    return 1


def set_watch_flag(rid, watch_flag: bool, prediction_reason: str = ""):
    if _repo_backend() == "sqlite":
        return sqlite_execute(
            'UPDATE picks SET watch_flag=?, prediction_reason=CASE WHEN ?!="" THEN ? ELSE COALESCE(prediction_reason, "") END WHERE id=?',
            (1 if watch_flag else 0, prediction_reason, prediction_reason, rid),
        )
    with session_scope() as session:
        pick = _get_pick_model(session, rid)
        if pick is None:
            return 0
        legacy_updates = {}
        if prediction_reason:
            legacy_updates["prediction_reason"] = prediction_reason
        _hydrate_pick_model(pick, watch_flag=watch_flag, legacy_updates=legacy_updates)
        session.flush()
    return 1


def batch_set_watch_flag(ids, watch_flag: bool):
    if _repo_backend() == "sqlite":
        return sqlite_execute_many("UPDATE picks SET watch_flag=? WHERE id=?", [(1 if watch_flag else 0, i) for i in ids]) if ids else 0
    ids = [int(i) for i in ids or []]
    if not ids:
        return 0
    with session_scope() as session:
        picks = session.execute(
            select(Pick).where(Pick.tenant_id == DEFAULT_TENANT_ID, Pick.id.in_(ids))
        ).scalars().all()
        for pick in picks:
            pick.watch_flag = bool(watch_flag)
        session.flush()
        return len(picks)


def delete_pick(rid):
    if _repo_backend() == "sqlite":
        return sqlite_execute("DELETE FROM picks WHERE id=?", (rid,))
    with session_scope() as session:
        pick = _get_pick_model(session, rid)
        if pick is None:
            return 0
        session.delete(pick)
        session.flush()
    return 1


def batch_set_archived(ids, archived: bool):
    if _repo_backend() == "sqlite":
        return sqlite_execute_many("UPDATE picks SET archived=? WHERE id=?", [(1 if archived else 0, i) for i in ids]) if ids else 0
    ids = [int(i) for i in ids or []]
    if not ids:
        return 0
    now = datetime.now()
    with session_scope() as session:
        picks = session.execute(
            select(Pick).where(Pick.tenant_id == DEFAULT_TENANT_ID, Pick.id.in_(ids))
        ).scalars().all()
        for pick in picks:
            pick.deleted_at = now if archived else None
        session.flush()
        return len(picks)


def batch_delete(ids):
    if _repo_backend() == "sqlite":
        return sqlite_execute_many("DELETE FROM picks WHERE id=?", [(i,) for i in ids]) if ids else 0
    ids = [int(i) for i in ids or []]
    if not ids:
        return 0
    with session_scope() as session:
        picks = session.execute(
            select(Pick).where(Pick.tenant_id == DEFAULT_TENANT_ID, Pick.id.in_(ids))
        ).scalars().all()
        count = len(picks)
        for pick in picks:
            session.delete(pick)
        session.flush()
    return count


def batch_set_review_status(ids, status):
    if _repo_backend() == "sqlite":
        return sqlite_execute_many("UPDATE picks SET review_status=? WHERE id=?", [(status, i) for i in ids]) if ids else 0
    ids = [int(i) for i in ids or []]
    if not ids:
        return 0
    with session_scope() as session:
        picks = session.execute(
            select(Pick).where(Pick.tenant_id == DEFAULT_TENANT_ID, Pick.id.in_(ids))
        ).scalars().all()
        for pick in picks:
            pick.status = status
        session.flush()
        return len(picks)


def batch_set_result_grade(ids, grade):
    if _repo_backend() == "sqlite":
        return sqlite_execute_many("UPDATE picks SET result_grade=? WHERE id=?", [(grade, i) for i in ids]) if ids else 0
    ids = [int(i) for i in ids or []]
    if not ids:
        return 0
    with session_scope() as session:
        picks = session.execute(
            select(Pick).where(Pick.tenant_id == DEFAULT_TENANT_ID, Pick.id.in_(ids))
        ).scalars().all()
        for pick in picks:
            pick.risk_level = grade
        session.flush()
        return len(picks)


def batch_set_deal_status(ids, deal_status):
    if _repo_backend() == "sqlite":
        return sqlite_execute_many("UPDATE picks SET deal_status=? WHERE id=?", [(deal_status, i) for i in ids]) if ids else 0
    ids = [int(i) for i in ids or []]
    if not ids:
        return 0
    with session_scope() as session:
        picks = session.execute(
            select(Pick).where(Pick.tenant_id == DEFAULT_TENANT_ID, Pick.id.in_(ids))
        ).scalars().all()
        for pick in picks:
            pick.deal_status = deal_status
        session.flush()
        return len(picks)


def batch_set_secondary_spread(ids, secondary_spread):
    if _repo_backend() == "sqlite":
        return sqlite_execute_many("UPDATE picks SET secondary_spread=? WHERE id=?", [(secondary_spread, i) for i in ids]) if ids else 0
    ids = [int(i) for i in ids or []]
    if not ids:
        return 0
    with session_scope() as session:
        picks = session.execute(
            select(Pick).where(Pick.tenant_id == DEFAULT_TENANT_ID, Pick.id.in_(ids))
        ).scalars().all()
        for pick in picks:
            pick.legacy_payload_json = _merge_legacy_payload(
                pick.legacy_payload_json,
                secondary_spread=secondary_spread,
            )
        session.flush()
        return len(picks)


def last_inserted_id():
    if _repo_backend() == "sqlite":
        row = sqlite_q1("SELECT id FROM picks ORDER BY id DESC LIMIT 1")
        return row["id"] if row else None
    return _MYSQL_LAST_INSERTED_PICK_ID


def count_picks(where_sql="", args=None):
    args = args or []
    if _repo_backend() == "sqlite":
        row = sqlite_q1(f"SELECT COUNT(*) AS cnt FROM picks {where_sql}", args)
        return int(row["cnt"]) if row and row.get("cnt") is not None else 0
    row = _mysql_select_one(f"SELECT COUNT(*) AS cnt FROM ({_MYSQL_COMPAT_SELECT}) AS picks_compat {where_sql}", args)
    return int(row["cnt"]) if row and row.get("cnt") is not None else 0


def list_watch_picks(limit=30):
    if _repo_backend() == "sqlite":
        return sqlite_q(
            "SELECT * FROM picks WHERE COALESCE(archived,0)=0 AND COALESCE(watch_flag,0)=1 ORDER BY COALESCE(second_board_score,0) DESC, pick_date DESC, id DESC LIMIT ?",
            (int(limit),),
        )
    return _mysql_select_all(
        _compat_select_sql(
            "WHERE COALESCE(archived,0)=0 AND COALESCE(watch_flag,0)=1",
            order_by=" ORDER BY CAST(COALESCE(NULLIF(second_board_score,''), '0') AS SIGNED) DESC, pick_date DESC, id DESC",
        )
        + " LIMIT ?",
        [int(limit)],
    )


def list_recent_for_analysis(limit=20):
    if _repo_backend() == "sqlite":
        return sqlite_q(
            "SELECT * FROM picks WHERE COALESCE(archived,0)=0 ORDER BY pick_date DESC, id DESC LIMIT ?",
            (int(limit),),
        )
    return _mysql_select_all(
        _compat_select_sql("WHERE COALESCE(archived,0)=0") + " LIMIT ?",
        [int(limit)],
    )


def upsert_research_report(pick_id, code, pick_date, analysis_date, metrics):
    mysql_params = (
        float(metrics.get("technical_score", 0) or 0),
        float(metrics.get("sentiment_score", 0) or 0),
        float(metrics.get("risk_score", 0) or 0),
        float(metrics.get("capital_score", 0) or 0),
        float(metrics.get("price_position", 0) or 0),
        float(metrics.get("research_score", 0) or 0),
        metrics.get("research_summary", ""),
        metrics.get("final_action", "key watch" if int(metrics.get("watch_flag", 0) or 0) else "watch"),
        metrics.get("confidence", ""),
        metrics.get("data_snapshot", ""),
    )
    if _repo_backend() == "sqlite":
        exists = sqlite_q1("SELECT id FROM research_reports WHERE pick_id=? AND analysis_date=?", (pick_id, analysis_date))
        params = (
            float(metrics.get("technical_score", 0) or 0),
            float(metrics.get("sentiment_score", 0) or 0),
            float(metrics.get("risk_score", 0) or 0),
            float(metrics.get("capital_score", 0) or 0),
            float(metrics.get("price_position", 0) or 0),
            float(metrics.get("research_score", 0) or 0),
            metrics.get("research_summary", ""),
            metrics.get("final_action", "重点观察" if int(metrics.get("watch_flag", 0) or 0) else "继续观察"),
            metrics.get("confidence", ""),
            metrics.get("data_snapshot", ""),
        )
        if exists:
            return sqlite_execute(
                """UPDATE research_reports SET technical_score=?, momentum_score=?, risk_score=?, liquidity_score=?,
                   timing_score=?, total_score=?, research_summary=?, action_suggestion=?, risk_warning=?,
                   data_snapshot=?, updated_at=CURRENT_TIMESTAMP WHERE pick_id=? AND analysis_date=?""",
                params + (pick_id, analysis_date),
            )
        return sqlite_execute(
            """INSERT INTO research_reports
            (pick_id, code, pick_date, analysis_date, technical_score, momentum_score, risk_score,
             liquidity_score, timing_score, total_score, research_summary, action_suggestion,
             risk_warning, data_snapshot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pick_id, code, pick_date) + (analysis_date,) + params,
        )
    _mysql_research_reports_supported()
    now = datetime.now()
    with session_scope() as session:
        report = session.execute(
            select(ResearchReport).where(
                ResearchReport.pick_id == int(pick_id),
                ResearchReport.analysis_date == str(analysis_date),
            )
        ).scalar_one_or_none()
        if report is None:
            report = ResearchReport(
                pick_id=int(pick_id),
                code=code or "",
                pick_date=str(pick_date or ""),
                analysis_date=str(analysis_date or ""),
                created_at=now,
                updated_at=now,
            )
            session.add(report)
        report.technical_score = mysql_params[0]
        report.momentum_score = mysql_params[1]
        report.risk_score = mysql_params[2]
        report.liquidity_score = mysql_params[3]
        report.timing_score = mysql_params[4]
        report.total_score = mysql_params[5]
        report.research_summary = mysql_params[6]
        report.action_suggestion = mysql_params[7]
        report.risk_warning = mysql_params[8]
        report.data_snapshot = mysql_params[9]
        report.updated_at = now
        session.flush()
    return 1


def update_research_snapshot(rid, metrics):
    pick = get_pick_by_id(rid)
    if not pick:
        return 0
    analysis_date = metrics.get("last_analysis_date") or pick.get("pick_date")
    if _repo_backend() == "sqlite":
        upsert_research_report(rid, pick.get("code", ""), pick.get("pick_date", ""), analysis_date, metrics)
        prediction_reason = metrics.get("research_summary", "")
        second_board_score = int(round(float(metrics.get("research_score", 0) or 0)))
        second_board_expectation = "高" if second_board_score >= 75 else "中" if second_board_score >= 55 else "低"
        return sqlite_execute(
            "UPDATE picks SET watch_flag=?, prediction_reason=?, second_board_score=?, second_board_expectation=? WHERE id=?",
            (int(metrics.get("watch_flag", 0) or 0), prediction_reason, second_board_score, second_board_expectation, rid),
        )

    second_board_score = int(round(float(metrics.get("research_score", 0) or 0)))
    second_board_expectation = "high" if second_board_score >= 75 else "medium" if second_board_score >= 55 else "low"
    upsert_research_report(rid, pick.get("code", ""), pick.get("pick_date", ""), analysis_date, metrics)
    with session_scope() as session:
        model = _get_pick_model(session, rid)
        if model is None:
            return 0
        model.watch_flag = bool(metrics.get("watch_flag", 0) or 0)
        model.legacy_payload_json = _merge_legacy_payload(
            model.legacy_payload_json,
            prediction_reason=metrics.get("research_summary", ""),
            second_board_score=second_board_score,
            second_board_expectation=second_board_expectation,
        )
        session.flush()
    return 1


def get_latest_research_map(ids):
    ids = [int(i) for i in ids if i]
    if not ids:
        return {}
    if _repo_backend() == "sqlite":
        placeholders = ",".join(["?"] * len(ids))
        rows = sqlite_q(
            f"""SELECT rr.* FROM research_reports rr
                INNER JOIN (
                    SELECT pick_id, MAX(analysis_date) AS max_analysis_date
                    FROM research_reports
                    WHERE pick_id IN ({placeholders})
                    GROUP BY pick_id
                ) latest ON latest.pick_id = rr.pick_id AND latest.max_analysis_date = rr.analysis_date""",
            ids,
        )
        return {row["pick_id"]: row for row in rows}
    _mysql_research_reports_supported()
    query = """
        SELECT rr.* FROM research_reports rr
        INNER JOIN (
            SELECT pick_id, MAX(analysis_date) AS max_analysis_date
            FROM research_reports
            WHERE pick_id IN ({placeholders})
            GROUP BY pick_id
        ) latest ON latest.pick_id = rr.pick_id AND latest.max_analysis_date = rr.analysis_date
    """.format(placeholders=", ".join(f":pick_{index}" for index, _ in enumerate(ids)))
    params = {f"pick_{index}": pick_id for index, pick_id in enumerate(ids)}
    with session_scope() as session:
        rows = session.execute(text(query), params).mappings().all()
    return {int(row["pick_id"]): {key: _normalize_scalar(value) for key, value in dict(row).items()} for row in rows}


def get_research_reports_by_pick(rid, limit=20):
    if _repo_backend() == "sqlite":
        return sqlite_q(
            "SELECT * FROM research_reports WHERE pick_id=? ORDER BY analysis_date DESC, id DESC LIMIT ?",
            (rid, int(limit)),
        )
    _mysql_research_reports_supported()
    with session_scope() as session:
        rows = session.execute(
            text(
                "SELECT * FROM research_reports WHERE pick_id=:pick_id ORDER BY analysis_date DESC, id DESC LIMIT :limit"
            ),
            {"pick_id": int(rid), "limit": int(limit)},
        ).mappings().all()
    return [{key: _normalize_scalar(value) for key, value in dict(row).items()} for row in rows]


def get_research_report_by_id(report_id):
    if _repo_backend() == "sqlite":
        return sqlite_q1("SELECT * FROM research_reports WHERE id=?", (int(report_id),))
    _mysql_research_reports_supported()
    with session_scope() as session:
        report = session.execute(
            select(ResearchReport).where(ResearchReport.id == int(report_id))
        ).scalar_one_or_none()
        if report is None:
            return None
        return {
            "id": report.id,
            "pick_id": report.pick_id,
            "code": report.code,
            "pick_date": report.pick_date,
            "analysis_date": report.analysis_date,
            "technical_score": _normalize_scalar(report.technical_score),
            "momentum_score": _normalize_scalar(report.momentum_score),
            "risk_score": _normalize_scalar(report.risk_score),
            "liquidity_score": _normalize_scalar(report.liquidity_score),
            "timing_score": _normalize_scalar(report.timing_score),
            "total_score": _normalize_scalar(report.total_score),
            "research_summary": report.research_summary,
            "action_suggestion": report.action_suggestion,
            "risk_warning": report.risk_warning,
            "data_snapshot": report.data_snapshot,
            "created_at": _normalize_scalar(report.created_at),
            "updated_at": _normalize_scalar(report.updated_at),
        }
