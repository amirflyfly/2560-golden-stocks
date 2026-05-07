"""Local market data cache repository."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, case, func, or_, select

from backend.core.config import get_settings
from backend.db.models.market import LimitRuleCalendar, MarketSyncRun, MarketSyncRunItem, MarketSyncState, Stock, StockAuctionSnapshot, StockDailyBar, StockPriceSnapshot
from backend.db.session import session_scope
from backend.infrastructure.market_data.provider import AuctionSnapshot, DailyBar, QuoteSnapshot, StockInfo
from backend.infrastructure.market_data.utils import clean_security_name, infer_board_type, infer_exchange, infer_limit_rate, infer_security_type, is_risk_warning_name, normalize_bar_interval
from backend.repositories.db import execute_many as sqlite_execute_many
from backend.repositories.db import q as sqlite_q
from backend.repositories.db import q1 as sqlite_q1


def _repo_backend() -> str:
    forced = (os.getenv("MARKET_DATA_REPOSITORY_BACKEND") or "auto").strip().lower()
    if forced in {"sqlite", "mysql"}:
        return forced
    settings = get_settings()
    return "mysql" if (settings.environment or "").strip().lower() in {"prod", "production"} else "sqlite"


def _date_text(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")


def _decimal_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _decimal_value(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _int_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _normalized_adjust(value: str | None = None) -> str:
    if value is None:
        return "qfq"
    text = str(value).strip().lower()
    if not text:
        return "none"
    if text in {"raw", "bfq", "不复权"}:
        return "none"
    return text


def _dt_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if " " in fmt or "T" in fmt else text[:10], fmt)
        except ValueError:
            continue
    return None


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "st", "suspended", "delisting"}


def _bar_interval(bar: DailyBar | dict) -> str:
    value = getattr(bar, "interval", None) if not isinstance(bar, dict) else bar.get("interval")
    return normalize_bar_interval(value)


def _bar_trade_time(bar: DailyBar | dict) -> str:
    value = getattr(bar, "trade_time", None) if not isinstance(bar, dict) else bar.get("trade_time")
    if value:
        text = _dt_text(value)
        if text:
            return text
    trade_date = getattr(bar, "trade_date", None) if not isinstance(bar, dict) else bar.get("trade_date")
    return f"{_date_text(trade_date)}T00:00:00"


def _public_stock(item: StockInfo | dict) -> dict:
    if isinstance(item, StockInfo):
        data = item.to_dict()
    else:
        data = dict(item)
    symbol = str(data.get("symbol") or data.get("code") or "").strip()
    exchange = str(data.get("exchange") or infer_exchange(symbol) or "").strip().upper()
    name = clean_security_name(data.get("name") or symbol)
    inferred_type = infer_security_type(symbol, name)
    provided_type = str(data.get("security_type") or "").strip().lower()
    security_type = provided_type if provided_type and provided_type != "stock" else inferred_type
    is_st = _bool_value(data.get("is_st")) or is_risk_warning_name(name)
    board_type = str(data.get("board_type") or infer_board_type(symbol, exchange=exchange, security_type=security_type)).strip().lower()
    limit_profile = data.get("limit_rule_profile") if isinstance(data.get("limit_rule_profile"), dict) else _loads_json(data.get("limit_rule_profile"))
    if not limit_profile:
        inferred_rate = infer_limit_rate(symbol, name, exchange=exchange, security_type=security_type, is_st=is_st)
        limit_profile = {
            "source": "inferred",
            "limit_rate": float(inferred_rate) if inferred_rate is not None else None,
            "board_type": board_type,
            "risk_warning": is_st,
        }
    return {
        "symbol": symbol,
        "exchange": exchange,
        "name": name,
        "market": str(data.get("market") or "A").strip() or "A",
        "security_type": security_type,
        "industry": str(data.get("industry") or "").strip() or None,
        "status": str(data.get("status") or "active").strip() or "active",
        "listing_date": _date_text(data.get("listing_date")) if data.get("listing_date") else None,
        "is_st": is_st,
        "board_type": board_type,
        "limit_rule_profile": limit_profile,
        "is_suspended": _bool_value(data.get("is_suspended") or data.get("suspended")) or str(data.get("status") or "").lower() in {"suspended", "halted"},
        "is_delisting": _bool_value(data.get("is_delisting")) or "退" in name or str(data.get("status") or "").lower() in {"delisting", "retiring"},
    }


def upsert_stocks(items: list[StockInfo | dict]) -> int:
    stocks = [_public_stock(item) for item in items]
    stocks = [item for item in stocks if item["symbol"]]
    if not stocks:
        return 0
    if _repo_backend() == "sqlite":
        return sqlite_execute_many(
            """INSERT INTO stocks
            (symbol, exchange, name, market, security_type, listing_date, status, is_st, board_type,
             limit_rule_profile, is_suspended, is_delisting, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol) DO UPDATE SET
                exchange=excluded.exchange,
                name=excluded.name,
                market=excluded.market,
                security_type=excluded.security_type,
                listing_date=excluded.listing_date,
                status=excluded.status,
                is_st=excluded.is_st,
                board_type=excluded.board_type,
                limit_rule_profile=CASE
                    WHEN excluded.limit_rule_profile IS NULL OR excluded.limit_rule_profile='' OR excluded.limit_rule_profile='{}'
                    THEN stocks.limit_rule_profile
                    ELSE excluded.limit_rule_profile
                END,
                is_suspended=excluded.is_suspended,
                is_delisting=excluded.is_delisting,
                updated_at=CURRENT_TIMESTAMP""",
            [
                (
                    item["symbol"],
                    item["exchange"],
                    item["name"],
                    item["market"],
                    item["security_type"],
                    item.get("listing_date"),
                    item["status"],
                    1 if item.get("is_st") else 0,
                    item.get("board_type") or "",
                    json.dumps(item.get("limit_rule_profile") or {}, ensure_ascii=False),
                    1 if item.get("is_suspended") else 0,
                    1 if item.get("is_delisting") else 0,
                )
                for item in stocks
            ],
        )

    count = 0
    with session_scope() as session:
        for item in stocks:
            model = session.execute(select(Stock).where(Stock.symbol == item["symbol"])).scalar_one_or_none()
            if model is None:
                session.add(
                    Stock(
                        symbol=item["symbol"],
                        exchange=item["exchange"],
                        name=item["name"],
                        market=item["market"],
                        security_type=item["security_type"],
                        listing_date=_parse_date(item.get("listing_date")),
                        status=item["status"],
                        is_st=bool(item.get("is_st")),
                        board_type=item.get("board_type"),
                        limit_rule_profile=item.get("limit_rule_profile") or {},
                        is_suspended=bool(item.get("is_suspended")),
                        is_delisting=bool(item.get("is_delisting")),
                    )
                )
            else:
                model.exchange = item["exchange"]
                model.name = item["name"]
                model.market = item["market"]
                model.security_type = item["security_type"]
                model.listing_date = _parse_date(item.get("listing_date"))
                model.status = item["status"]
                model.is_st = bool(item.get("is_st"))
                model.board_type = item.get("board_type")
                model.limit_rule_profile = item.get("limit_rule_profile") or model.limit_rule_profile or {}
                model.is_suspended = bool(item.get("is_suspended"))
                model.is_delisting = bool(item.get("is_delisting"))
            count += 1
    return count


def upsert_daily_bars(bars: list[DailyBar], *, adjust: str = "qfq") -> int:
    normalized = [bar for bar in bars if bar.symbol and bar.trade_date and bar.source]
    if not normalized:
        return 0
    normalized_adjust = _normalized_adjust(adjust)
    upsert_stocks(
        [
            {
                "symbol": bar.symbol,
                "exchange": infer_exchange(bar.symbol),
                "name": bar.symbol,
                "market": "A",
                "security_type": infer_security_type(bar.symbol, bar.symbol),
            }
            for bar in normalized
        ]
    )

    if _repo_backend() == "sqlite":
        return sqlite_execute_many(
            """INSERT INTO stock_daily_bars
            (symbol, trade_date, trade_time, interval, adjust, open, high, low, close, volume, amount, turnover_rate, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol, trade_date, trade_time, interval, source, adjust) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                amount=excluded.amount,
                turnover_rate=excluded.turnover_rate,
                updated_at=CURRENT_TIMESTAMP""",
            [
                (
                    bar.symbol,
                    _date_text(bar.trade_date),
                    _bar_trade_time(bar),
                    _bar_interval(bar),
                    normalized_adjust,
                    _decimal_float(bar.open),
                    _decimal_float(bar.high),
                    _decimal_float(bar.low),
                    _decimal_float(bar.close),
                    bar.volume,
                    _decimal_float(bar.amount),
                    _decimal_float(bar.turnover_rate),
                    bar.source,
                )
                for bar in normalized
            ],
        )

    count = 0
    with session_scope() as session:
        for bar in normalized:
            model = session.execute(
                select(StockDailyBar).where(
                    StockDailyBar.symbol == bar.symbol,
                    StockDailyBar.trade_date == bar.trade_date,
                    StockDailyBar.trade_time == _parse_datetime(_bar_trade_time(bar)),
                    StockDailyBar.interval == _bar_interval(bar),
                    StockDailyBar.source == bar.source,
                    StockDailyBar.adjust == normalized_adjust,
                )
            ).scalar_one_or_none()
            if model is None:
                session.add(
                    StockDailyBar(
                        symbol=bar.symbol,
                        trade_date=bar.trade_date,
                        trade_time=_parse_datetime(_bar_trade_time(bar)) or datetime.combine(bar.trade_date, datetime.min.time()),
                        interval=_bar_interval(bar),
                        adjust=normalized_adjust,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                        amount=bar.amount,
                        turnover_rate=bar.turnover_rate,
                        source=bar.source,
                    )
                )
            else:
                model.adjust = normalized_adjust
                model.trade_time = _parse_datetime(_bar_trade_time(bar)) or model.trade_time
                model.interval = _bar_interval(bar)
                model.open = bar.open
                model.high = bar.high
                model.low = bar.low
                model.close = bar.close
                model.volume = bar.volume
                model.amount = bar.amount
                model.turnover_rate = bar.turnover_rate
            count += 1
    return count


def _snapshot_payload(item: QuoteSnapshot | dict) -> dict:
    data = item.to_dict() if isinstance(item, QuoteSnapshot) else dict(item)
    symbol = str(data.get("symbol") or data.get("code") or "").strip()
    return {
        "symbol": symbol,
        "trade_time": _dt_text(data.get("trade_time")),
        "last_price": data.get("last_price"),
        "open": data.get("open"),
        "high": data.get("high"),
        "low": data.get("low"),
        "prev_close": data.get("prev_close"),
        "volume": data.get("volume"),
        "amount": data.get("amount"),
        "bid_price": data.get("bid_price"),
        "ask_price": data.get("ask_price"),
        "source": str(data.get("source") or "unknown").strip() or "unknown",
    }


def upsert_quote_snapshots(items: list[QuoteSnapshot | dict]) -> int:
    snapshots = [_snapshot_payload(item) for item in items]
    snapshots = [item for item in snapshots if item["symbol"]]
    if not snapshots:
        return 0
    upsert_stocks(
        [
            {
                "symbol": item["symbol"],
                "exchange": infer_exchange(item["symbol"]),
                "name": item["symbol"],
                "market": "A",
                "security_type": infer_security_type(item["symbol"], item["symbol"]),
            }
            for item in snapshots
        ]
    )
    if _repo_backend() == "sqlite":
        return sqlite_execute_many(
            """INSERT INTO stock_price_snapshots
            (symbol, trade_time, last_price, open, high, low, prev_close, volume, amount, bid_price, ask_price, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol) DO UPDATE SET
                trade_time=excluded.trade_time,
                last_price=excluded.last_price,
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                prev_close=excluded.prev_close,
                volume=excluded.volume,
                amount=excluded.amount,
                bid_price=excluded.bid_price,
                ask_price=excluded.ask_price,
                source=excluded.source,
                updated_at=CURRENT_TIMESTAMP""",
            [
                (
                    item["symbol"],
                    item["trade_time"],
                    item["last_price"],
                    item["open"],
                    item["high"],
                    item["low"],
                    item["prev_close"],
                    item["volume"],
                    item["amount"],
                    item["bid_price"],
                    item["ask_price"],
                    item["source"],
                )
                for item in snapshots
            ],
        )

    count = 0
    with session_scope() as session:
        for item in snapshots:
            model = session.execute(
                select(StockPriceSnapshot).where(StockPriceSnapshot.symbol == item["symbol"])
            ).scalar_one_or_none()
            if model is None:
                session.add(
                    StockPriceSnapshot(
                        symbol=item["symbol"],
                        trade_time=_parse_datetime(item["trade_time"]),
                        last_price=_decimal_value(item["last_price"]),
                        open=_decimal_value(item["open"]),
                        high=_decimal_value(item["high"]),
                        low=_decimal_value(item["low"]),
                        prev_close=_decimal_value(item["prev_close"]),
                        volume=_int_value(item["volume"]),
                        amount=_decimal_value(item["amount"]),
                        bid_price=_decimal_value(item["bid_price"]),
                        ask_price=_decimal_value(item["ask_price"]),
                        source=item["source"],
                    )
                )
            else:
                model.trade_time = _parse_datetime(item["trade_time"])
                model.last_price = _decimal_value(item["last_price"])
                model.open = _decimal_value(item["open"])
                model.high = _decimal_value(item["high"])
                model.low = _decimal_value(item["low"])
                model.prev_close = _decimal_value(item["prev_close"])
                model.volume = _int_value(item["volume"])
                model.amount = _decimal_value(item["amount"])
                model.bid_price = _decimal_value(item["bid_price"])
                model.ask_price = _decimal_value(item["ask_price"])
                model.source = item["source"]
            count += 1
    return count


def _auction_payload(item: AuctionSnapshot | dict) -> dict:
    data = item.to_dict() if isinstance(item, AuctionSnapshot) else dict(item)
    symbol = str(data.get("symbol") or data.get("code") or "").strip()
    trade_date = _date_text(data.get("trade_date") or str(data.get("auction_time") or "")[:10])
    auction_time = _dt_text(data.get("auction_time") or data.get("trade_time"))
    order_book = data.get("order_book")
    if order_book in (None, ""):
        order_book = data.get("order_book_json")
    if isinstance(order_book, str):
        order_book = _loads_json(order_book)
    return {
        "symbol": symbol,
        "trade_date": trade_date,
        "auction_time": auction_time,
        "phase": str(data.get("phase") or "call_auction_0920_0925").strip() or "call_auction_0920_0925",
        "prev_close": data.get("prev_close"),
        "indicative_price": data.get("indicative_price") or data.get("auction_price") or data.get("open") or data.get("last_price"),
        "matched_volume": data.get("matched_volume") or data.get("volume"),
        "matched_amount": data.get("matched_amount") or data.get("amount"),
        "unmatched_buy_volume": data.get("unmatched_buy_volume"),
        "unmatched_sell_volume": data.get("unmatched_sell_volume"),
        "bid_price": data.get("bid_price"),
        "bid_volume": data.get("bid_volume"),
        "ask_price": data.get("ask_price"),
        "ask_volume": data.get("ask_volume"),
        "order_book": order_book if isinstance(order_book, (dict, list)) else {},
        "withdrawal_buy_volume": data.get("withdrawal_buy_volume"),
        "withdrawal_sell_volume": data.get("withdrawal_sell_volume"),
        "withdrawal_buy_amount": data.get("withdrawal_buy_amount"),
        "withdrawal_sell_amount": data.get("withdrawal_sell_amount"),
        "seal_price": data.get("seal_price"),
        "seal_volume": data.get("seal_volume"),
        "seal_amount": data.get("seal_amount"),
        "seal_side": str(data.get("seal_side") or "").strip().lower(),
        "source": str(data.get("source") or "unknown").strip() or "unknown",
    }


def upsert_auction_snapshots(items: list[AuctionSnapshot | dict]) -> int:
    snapshots = [_auction_payload(item) for item in items]
    snapshots = [item for item in snapshots if item["symbol"] and item["trade_date"] and item["auction_time"]]
    if not snapshots:
        return 0
    upsert_stocks(
        [
            {
                "symbol": item["symbol"],
                "exchange": infer_exchange(item["symbol"]),
                "name": item["symbol"],
                "market": "A",
                "security_type": infer_security_type(item["symbol"], item["symbol"]),
            }
            for item in snapshots
        ]
    )
    if _repo_backend() == "sqlite":
        return sqlite_execute_many(
            """INSERT INTO stock_auction_snapshots
            (symbol, trade_date, auction_time, phase, prev_close, indicative_price,
             matched_volume, matched_amount, unmatched_buy_volume, unmatched_sell_volume,
             bid_price, bid_volume, ask_price, ask_volume, order_book_json,
             withdrawal_buy_volume, withdrawal_sell_volume, withdrawal_buy_amount, withdrawal_sell_amount,
             seal_price, seal_volume, seal_amount, seal_side, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(symbol, trade_date, auction_time, source) DO UPDATE SET
                phase=excluded.phase,
                prev_close=excluded.prev_close,
                indicative_price=excluded.indicative_price,
                matched_volume=excluded.matched_volume,
                matched_amount=excluded.matched_amount,
                unmatched_buy_volume=excluded.unmatched_buy_volume,
                unmatched_sell_volume=excluded.unmatched_sell_volume,
                bid_price=excluded.bid_price,
                bid_volume=excluded.bid_volume,
                ask_price=excluded.ask_price,
                ask_volume=excluded.ask_volume,
                order_book_json=excluded.order_book_json,
                withdrawal_buy_volume=excluded.withdrawal_buy_volume,
                withdrawal_sell_volume=excluded.withdrawal_sell_volume,
                withdrawal_buy_amount=excluded.withdrawal_buy_amount,
                withdrawal_sell_amount=excluded.withdrawal_sell_amount,
                seal_price=excluded.seal_price,
                seal_volume=excluded.seal_volume,
                seal_amount=excluded.seal_amount,
                seal_side=excluded.seal_side,
                updated_at=CURRENT_TIMESTAMP""",
            [
                (
                    item["symbol"],
                    item["trade_date"],
                    item["auction_time"],
                    item["phase"],
                    _decimal_float(_decimal_value(item["prev_close"])),
                    _decimal_float(_decimal_value(item["indicative_price"])),
                    _int_value(item["matched_volume"]),
                    _decimal_float(_decimal_value(item["matched_amount"])),
                    _int_value(item["unmatched_buy_volume"]),
                    _int_value(item["unmatched_sell_volume"]),
                    _decimal_float(_decimal_value(item["bid_price"])),
                    _int_value(item["bid_volume"]),
                    _decimal_float(_decimal_value(item["ask_price"])),
                    _int_value(item["ask_volume"]),
                    json.dumps(item.get("order_book") or {}, ensure_ascii=False),
                    _int_value(item["withdrawal_buy_volume"]),
                    _int_value(item["withdrawal_sell_volume"]),
                    _decimal_float(_decimal_value(item["withdrawal_buy_amount"])),
                    _decimal_float(_decimal_value(item["withdrawal_sell_amount"])),
                    _decimal_float(_decimal_value(item["seal_price"])),
                    _int_value(item["seal_volume"]),
                    _decimal_float(_decimal_value(item["seal_amount"])),
                    item["seal_side"],
                    item["source"],
                )
                for item in snapshots
            ],
        )

    count = 0
    with session_scope() as session:
        for item in snapshots:
            auction_time = _parse_datetime(item["auction_time"])
            trade_date = _parse_date(item["trade_date"])
            if auction_time is None or trade_date is None:
                continue
            model = session.execute(
                select(StockAuctionSnapshot).where(
                    StockAuctionSnapshot.symbol == item["symbol"],
                    StockAuctionSnapshot.trade_date == trade_date,
                    StockAuctionSnapshot.auction_time == auction_time,
                    StockAuctionSnapshot.source == item["source"],
                )
            ).scalar_one_or_none()
            if model is None:
                model = StockAuctionSnapshot(
                    symbol=item["symbol"],
                    trade_date=trade_date,
                    auction_time=auction_time,
                    source=item["source"],
                )
                session.add(model)
            model.phase = item["phase"]
            model.prev_close = _decimal_value(item["prev_close"])
            model.indicative_price = _decimal_value(item["indicative_price"])
            model.matched_volume = _int_value(item["matched_volume"])
            model.matched_amount = _decimal_value(item["matched_amount"])
            model.unmatched_buy_volume = _int_value(item["unmatched_buy_volume"])
            model.unmatched_sell_volume = _int_value(item["unmatched_sell_volume"])
            model.bid_price = _decimal_value(item["bid_price"])
            model.bid_volume = _int_value(item["bid_volume"])
            model.ask_price = _decimal_value(item["ask_price"])
            model.ask_volume = _int_value(item["ask_volume"])
            model.order_book = item.get("order_book") or {}
            model.withdrawal_buy_volume = _int_value(item["withdrawal_buy_volume"])
            model.withdrawal_sell_volume = _int_value(item["withdrawal_sell_volume"])
            model.withdrawal_buy_amount = _decimal_value(item["withdrawal_buy_amount"])
            model.withdrawal_sell_amount = _decimal_value(item["withdrawal_sell_amount"])
            model.seal_price = _decimal_value(item["seal_price"])
            model.seal_volume = _int_value(item["seal_volume"])
            model.seal_amount = _decimal_value(item["seal_amount"])
            model.seal_side = item["seal_side"]
            count += 1
    return count


def coverage_summary(
    source: str | None = None,
    *,
    interval: str | None = None,
    security_type: str | None = None,
    adjust: str | None = None,
) -> dict:
    normalized_source = (source or "").strip() or None
    normalized_interval = normalize_bar_interval(interval) if interval else None
    normalized_security_type = str(security_type or "").strip().lower() or None
    normalized_adjust = _normalized_adjust(adjust) if adjust is not None else None
    if _repo_backend() == "sqlite":
        where = ["1=1"]
        params: list[Any] = []
        if normalized_source:
            where.append("b.source=?")
            params.append(normalized_source)
        if normalized_interval:
            where.append("b.interval=?")
            params.append(normalized_interval)
        if normalized_adjust:
            where.append("(b.adjust=? OR b.adjust='' OR b.adjust IS NULL)")
            params.append(normalized_adjust)
        if normalized_security_type:
            where.append("s.security_type=?")
            params.append(normalized_security_type)
        bars = sqlite_q1(
            f"""SELECT COUNT(*) AS bar_count, COUNT(DISTINCT b.symbol) AS synced_symbols,
                MIN(b.trade_date) AS first_trade_date, MAX(b.trade_date) AS last_trade_date,
                GROUP_CONCAT(DISTINCT b.source) AS sources
            FROM stock_daily_bars b
            LEFT JOIN stocks s ON s.symbol=b.symbol
            WHERE {' AND '.join(where)}""",
            tuple(params),
        ) or {}
        stock_where = []
        stock_params: list[Any] = []
        if normalized_security_type:
            stock_where.append("security_type=?")
            stock_params.append(normalized_security_type)
        stock_where_sql = "WHERE " + " AND ".join(stock_where) if stock_where else ""
        stocks = sqlite_q1(f"SELECT COUNT(*) AS security_count FROM stocks {stock_where_sql}", tuple(stock_params)) or {}
        stock_total = sqlite_q1("SELECT SUM(CASE WHEN security_type='stock' THEN 1 ELSE 0 END) AS stock_count FROM stocks") or {}
        type_rows = sqlite_q("SELECT COALESCE(security_type, 'other') AS security_type, COUNT(*) AS cnt FROM stocks GROUP BY COALESCE(security_type, 'other') ORDER BY cnt DESC")
        target_security_count = int(stocks.get("security_count") or 0)
        synced_symbols = int(bars.get("synced_symbols") or 0)
        coverage_ratio = round(synced_symbols / target_security_count, 4) if target_security_count else 0
        return {
            "backend": _repo_backend(),
            "security_count": target_security_count,
            "stock_count": int(stock_total.get("stock_count") or 0),
            "synced_symbols": synced_symbols,
            "bar_count": int(bars.get("bar_count") or 0),
            "first_trade_date": bars.get("first_trade_date"),
            "last_trade_date": bars.get("last_trade_date"),
            "sources": [item for item in str(bars.get("sources") or "").split(",") if item],
            "security_type_counts": {str(row.get("security_type") or "other"): int(row.get("cnt") or 0) for row in type_rows},
            "source": normalized_source or "",
            "interval": normalized_interval or "",
            "adjust": normalized_adjust or "",
            "security_type": normalized_security_type or "",
            "target_security_count": target_security_count,
            "coverage_ratio": coverage_ratio,
            "local_coverage_ratio": coverage_ratio,
        }

    with session_scope() as session:
        bars_query = select(
            func.count(StockDailyBar.id),
            func.count(func.distinct(StockDailyBar.symbol)),
            func.min(StockDailyBar.trade_date),
            func.max(StockDailyBar.trade_date),
            func.group_concat(func.distinct(StockDailyBar.source)),
        ).select_from(StockDailyBar).outerjoin(Stock, Stock.symbol == StockDailyBar.symbol)
        if normalized_source:
            bars_query = bars_query.where(StockDailyBar.source == normalized_source)
        if normalized_interval:
            bars_query = bars_query.where(StockDailyBar.interval == normalized_interval)
        if normalized_adjust:
            bars_query = bars_query.where(StockDailyBar.adjust == normalized_adjust)
        if normalized_security_type:
            bars_query = bars_query.where(Stock.security_type == normalized_security_type)
        bar_count, synced_symbols, first_trade_date, last_trade_date, sources = session.execute(bars_query).one()
        security_count_query = select(func.count(Stock.id))
        if normalized_security_type:
            security_count_query = security_count_query.where(Stock.security_type == normalized_security_type)
        security_count = session.execute(security_count_query).scalar_one()
        stock_count = session.execute(select(func.count(Stock.id)).where(Stock.security_type == "stock")).scalar_one()
        type_rows = session.execute(select(Stock.security_type, func.count(Stock.id)).group_by(Stock.security_type)).all()
        target_security_count = int(security_count or 0)
        synced_symbol_count = int(synced_symbols or 0)
        coverage_ratio = round(synced_symbol_count / target_security_count, 4) if target_security_count else 0
        return {
            "backend": _repo_backend(),
            "security_count": target_security_count,
            "stock_count": int(stock_count or 0),
            "synced_symbols": synced_symbol_count,
            "bar_count": int(bar_count or 0),
            "first_trade_date": _date_text(first_trade_date) if first_trade_date else None,
            "last_trade_date": _date_text(last_trade_date) if last_trade_date else None,
            "sources": [item for item in str(sources or "").split(",") if item],
            "security_type_counts": {str(security_type or "other"): int(count or 0) for security_type, count in type_rows},
            "source": normalized_source or "",
            "interval": normalized_interval or "",
            "adjust": normalized_adjust or "",
            "security_type": normalized_security_type or "",
            "target_security_count": target_security_count,
            "coverage_ratio": coverage_ratio,
            "local_coverage_ratio": coverage_ratio,
        }


def list_limit_rules(
    *,
    exchange: str | None = None,
    board_type: str | None = None,
    security_type: str | None = None,
    risk_warning: bool | None = None,
    active_only: bool = True,
) -> dict:
    normalized_exchange = str(exchange or "").strip().upper()
    normalized_board = str(board_type or "").strip().lower()
    normalized_security_type = str(security_type or "").strip().lower()
    if _repo_backend() == "sqlite":
        where = []
        params: list[Any] = []
        if normalized_exchange:
            where.append("exchange=?")
            params.append(normalized_exchange)
        if normalized_board:
            where.append("board_type=?")
            params.append(normalized_board)
        if normalized_security_type:
            where.append("security_type=?")
            params.append(normalized_security_type)
        if risk_warning is not None:
            where.append("risk_warning=?")
            params.append(1 if risk_warning else 0)
        if active_only:
            where.append("status='active'")
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        rows = sqlite_q(
            f"""SELECT * FROM limit_rule_calendar
            {where_sql}
            ORDER BY exchange ASC, board_type ASC, security_type ASC, risk_warning ASC, effective_from ASC""",
            tuple(params),
        )
        return {"items": [_limit_rule_item(row) for row in rows], "total": len(rows), "backend": _repo_backend()}

    with session_scope() as session:
        query = select(LimitRuleCalendar)
        if normalized_exchange:
            query = query.where(LimitRuleCalendar.exchange == normalized_exchange)
        if normalized_board:
            query = query.where(LimitRuleCalendar.board_type == normalized_board)
        if normalized_security_type:
            query = query.where(LimitRuleCalendar.security_type == normalized_security_type)
        if risk_warning is not None:
            query = query.where(LimitRuleCalendar.risk_warning.is_(bool(risk_warning)))
        if active_only:
            query = query.where(LimitRuleCalendar.status == "active")
        rows = session.execute(
            query.order_by(
                LimitRuleCalendar.exchange.asc(),
                LimitRuleCalendar.board_type.asc(),
                LimitRuleCalendar.security_type.asc(),
                LimitRuleCalendar.risk_warning.asc(),
                LimitRuleCalendar.effective_from.asc(),
            )
        ).scalars().all()
        return {"items": [_limit_rule_item(_public_model_limit_rule(row)) for row in rows], "total": len(rows), "backend": _repo_backend()}


def limit_rule_summary() -> dict:
    payload = list_limit_rules(active_only=True)
    items = payload.get("items") or []
    profiles = {
        f"{item.get('exchange')}:{item.get('board_type')}:{item.get('security_type')}:{int(bool(item.get('risk_warning')))}"
        for item in items
    }
    return {
        "backend": _repo_backend(),
        "rule_count": len(items),
        "profile_count": len(profiles),
        "has_rules": bool(items),
        "profiles": sorted(profiles),
    }


def resolve_limit_rule(
    symbol: str,
    *,
    name: str | None = None,
    exchange: str | None = None,
    board_type: str | None = None,
    security_type: str | None = None,
    risk_warning: bool | None = None,
    trade_date: str | date | None = None,
    listing_date: str | date | None = None,
) -> dict:
    normalized_symbol = str(symbol or "").strip()
    effective_date = _parse_date(trade_date) or date.today()
    stock = None
    if normalized_symbol:
        if _repo_backend() == "sqlite":
            stock = sqlite_q1("SELECT * FROM stocks WHERE symbol=?", (normalized_symbol,))
        else:
            with session_scope() as session:
                row = session.execute(select(Stock).where(Stock.symbol == normalized_symbol)).scalar_one_or_none()
                if row is not None:
                    stock = {
                        "symbol": row.symbol,
                        "name": row.name,
                        "exchange": row.exchange,
                        "board_type": row.board_type,
                        "security_type": row.security_type,
                        "is_st": row.is_st,
                        "listing_date": row.listing_date,
                    }
    stock = stock or {}
    resolved_name = name or stock.get("name") or normalized_symbol
    resolved_exchange = str(exchange or stock.get("exchange") or infer_exchange(normalized_symbol)).strip().upper()
    resolved_security_type = str(security_type or stock.get("security_type") or infer_security_type(normalized_symbol, resolved_name)).strip().lower()
    resolved_risk_warning = bool(risk_warning if risk_warning is not None else _bool_value(stock.get("is_st")) or is_risk_warning_name(resolved_name))
    resolved_board = str(board_type or stock.get("board_type") or infer_board_type(normalized_symbol, exchange=resolved_exchange, security_type=resolved_security_type)).strip().lower()
    resolved_listing_date = _parse_date(listing_date or stock.get("listing_date"))
    row = _find_limit_rule_row(
        exchange=resolved_exchange,
        board_type=resolved_board,
        security_type=resolved_security_type,
        risk_warning=resolved_risk_warning,
        trade_date=effective_date,
    )
    if row:
        item = _limit_rule_item(row)
        no_limit = bool(
            resolved_listing_date
            and int(item.get("no_limit_first_days") or 0) > 0
            and 0 <= (effective_date - resolved_listing_date).days < int(item.get("no_limit_first_days") or 0)
        )
        return {
            **item,
            "symbol": normalized_symbol,
            "name": resolved_name,
            "confirmed": True,
            "rule_source": "calendar",
            "no_price_limit": no_limit,
        }
    inferred_rate = infer_limit_rate(
        normalized_symbol,
        resolved_name,
        exchange=resolved_exchange,
        security_type=resolved_security_type,
        is_st=resolved_risk_warning,
        trade_date=effective_date,
    )
    return {
        "symbol": normalized_symbol,
        "name": resolved_name,
        "exchange": resolved_exchange,
        "board_type": resolved_board,
        "security_type": resolved_security_type,
        "risk_warning": resolved_risk_warning,
        "effective_from": None,
        "effective_to": None,
        "limit_up_rate": float(inferred_rate) if inferred_rate is not None else None,
        "limit_down_rate": float(inferred_rate) if inferred_rate is not None else None,
        "no_limit_first_days": 0,
        "status": "inferred" if inferred_rate is not None else "missing",
        "confirmed": False,
        "rule_source": "inferred" if inferred_rate is not None else "missing",
        "no_price_limit": False,
    }


def _find_limit_rule_row(
    *,
    exchange: str,
    board_type: str,
    security_type: str,
    risk_warning: bool,
    trade_date: date,
) -> dict | None:
    if _repo_backend() == "sqlite":
        row = sqlite_q1(
            """SELECT * FROM limit_rule_calendar
            WHERE exchange=? AND board_type=? AND security_type=? AND risk_warning=?
              AND effective_from<=?
              AND (effective_to IS NULL OR effective_to='' OR effective_to>=?)
              AND status='active'
            ORDER BY effective_from DESC
            LIMIT 1""",
            (exchange, board_type, security_type, 1 if risk_warning else 0, trade_date.isoformat(), trade_date.isoformat()),
        )
        return row
    with session_scope() as session:
        row = session.execute(
            select(LimitRuleCalendar)
            .where(
                LimitRuleCalendar.exchange == exchange,
                LimitRuleCalendar.board_type == board_type,
                LimitRuleCalendar.security_type == security_type,
                LimitRuleCalendar.risk_warning.is_(risk_warning),
                LimitRuleCalendar.effective_from <= trade_date,
                or_(LimitRuleCalendar.effective_to.is_(None), LimitRuleCalendar.effective_to >= trade_date),
                LimitRuleCalendar.status == "active",
            )
            .order_by(LimitRuleCalendar.effective_from.desc())
            .limit(1)
        ).scalar_one_or_none()
        return _public_model_limit_rule(row) if row is not None else None


def get_symbol_coverage(symbol: str, *, source: str | None = None, adjust: str | None = "qfq", interval: str | None = "1d") -> dict:
    normalized_symbol = str(symbol or "").strip()
    if not normalized_symbol:
        return _coverage_item({"symbol": "", "bar_count": 0})
    normalized_source = (source or "").strip()
    normalized_adjust = _normalized_adjust(adjust)
    normalized_interval = normalize_bar_interval(interval)
    if _repo_backend() == "sqlite":
        where = ["symbol=?"]
        params: list[Any] = [normalized_symbol]
        if normalized_source:
            where.append("source=?")
            params.append(normalized_source)
        if normalized_adjust:
            where.append("(adjust=? OR adjust='' OR adjust IS NULL)")
            params.append(normalized_adjust)
        if normalized_interval:
            where.append("(interval=? OR interval='' OR interval IS NULL)")
            params.append(normalized_interval)
        row = sqlite_q1(
            f"""SELECT symbol,
                COUNT(id) AS bar_count,
                MIN(trade_date) AS first_trade_date,
                MAX(trade_date) AS last_trade_date,
                MAX(trade_time) AS last_trade_time,
                MAX(updated_at) AS last_updated_at,
                GROUP_CONCAT(DISTINCT source) AS sources,
                GROUP_CONCAT(DISTINCT adjust) AS adjusts,
                GROUP_CONCAT(DISTINCT interval) AS intervals
            FROM stock_daily_bars
            WHERE {' AND '.join(where)}
            GROUP BY symbol""",
            tuple(params),
        ) or {"symbol": normalized_symbol, "bar_count": 0}
        return _coverage_item(row)

    with session_scope() as session:
        query = select(
            StockDailyBar.symbol.label("symbol"),
            func.count(StockDailyBar.id).label("bar_count"),
            func.min(StockDailyBar.trade_date).label("first_trade_date"),
            func.max(StockDailyBar.trade_date).label("last_trade_date"),
            func.max(StockDailyBar.trade_time).label("last_trade_time"),
            func.max(StockDailyBar.updated_at).label("last_updated_at"),
            func.group_concat(func.distinct(StockDailyBar.source)).label("sources"),
            func.group_concat(func.distinct(StockDailyBar.adjust)).label("adjusts"),
            func.group_concat(func.distinct(StockDailyBar.interval)).label("intervals"),
        ).where(StockDailyBar.symbol == normalized_symbol)
        if normalized_source:
            query = query.where(StockDailyBar.source == normalized_source)
        if normalized_adjust:
            query = query.where(StockDailyBar.adjust == normalized_adjust)
        if normalized_interval:
            query = query.where(StockDailyBar.interval == normalized_interval)
        row = session.execute(query.group_by(StockDailyBar.symbol)).mappings().first()
        return _coverage_item(dict(row) if row else {"symbol": normalized_symbol, "bar_count": 0})


def latest_daily_bar_dates(symbols: list[str], *, source: str | None = None, adjust: str | None = "qfq") -> dict[str, str]:
    normalized_symbols = [str(symbol or "").strip() for symbol in symbols if str(symbol or "").strip()]
    if not normalized_symbols:
        return {}
    normalized_source = (source or "").strip()
    normalized_adjust = _normalized_adjust(adjust)
    if _repo_backend() == "sqlite":
        placeholders = ",".join("?" for _ in normalized_symbols)
        where = [f"symbol IN ({placeholders})"]
        params: list[Any] = list(normalized_symbols)
        if normalized_source:
            where.append("source=?")
            params.append(normalized_source)
        if normalized_adjust:
            where.append("(adjust=? OR adjust='' OR adjust IS NULL)")
            params.append(normalized_adjust)
        rows = sqlite_q(
            f"""SELECT symbol, MAX(trade_date) AS last_trade_date
            FROM stock_daily_bars
            WHERE {' AND '.join(where)}
            GROUP BY symbol""",
            tuple(params),
        )
        return {str(row.get("symbol")): str(row.get("last_trade_date")) for row in rows if row.get("last_trade_date")}

    with session_scope() as session:
        query = select(StockDailyBar.symbol, func.max(StockDailyBar.trade_date)).where(StockDailyBar.symbol.in_(normalized_symbols))
        if normalized_source:
            query = query.where(StockDailyBar.source == normalized_source)
        if normalized_adjust:
            query = query.where(StockDailyBar.adjust == normalized_adjust)
        rows = session.execute(query.group_by(StockDailyBar.symbol)).all()
        return {symbol: _date_text(last_date) for symbol, last_date in rows if last_date}


def snapshot_summary(source: str | None = None, *, security_type: str | None = None) -> dict:
    normalized_source = (source or "").strip() or None
    normalized_security_type = str(security_type or "").strip().lower() or None
    if _repo_backend() == "sqlite":
        where = ["1=1"]
        params: list[Any] = []
        if normalized_source:
            where.append("p.source=?")
            params.append(normalized_source)
        if normalized_security_type:
            where.append("s.security_type=?")
            params.append(normalized_security_type)
        row = sqlite_q1(
            f"""SELECT COUNT(*) AS snapshot_count, MAX(p.trade_time) AS latest_trade_time,
                GROUP_CONCAT(DISTINCT p.source) AS sources
            FROM stock_price_snapshots p
            LEFT JOIN stocks s ON s.symbol=p.symbol
            WHERE {' AND '.join(where)}""",
            tuple(params),
        ) or {}
        stock_where = []
        stock_params: list[Any] = []
        if normalized_security_type:
            stock_where.append("security_type=?")
            stock_params.append(normalized_security_type)
        stock_where_sql = "WHERE " + " AND ".join(stock_where) if stock_where else ""
        stocks = sqlite_q1(f"SELECT COUNT(*) AS security_count FROM stocks {stock_where_sql}", tuple(stock_params)) or {}
        snapshot_count = int(row.get("snapshot_count") or 0)
        target_security_count = int(stocks.get("security_count") or 0)
        coverage_ratio = round(snapshot_count / target_security_count, 4) if target_security_count else 0
        return {
            "backend": _repo_backend(),
            "snapshot_count": snapshot_count,
            "latest_trade_time": row.get("latest_trade_time"),
            "sources": [item for item in str(row.get("sources") or "").split(",") if item],
            "source": normalized_source or "",
            "security_type": normalized_security_type or "",
            "security_count": target_security_count,
            "target_security_count": target_security_count,
            "coverage_ratio": coverage_ratio,
            "local_snapshot_coverage_ratio": coverage_ratio,
        }

    with session_scope() as session:
        query = select(
            func.count(StockPriceSnapshot.id),
            func.max(StockPriceSnapshot.trade_time),
            func.group_concat(func.distinct(StockPriceSnapshot.source)),
        ).select_from(StockPriceSnapshot).outerjoin(Stock, Stock.symbol == StockPriceSnapshot.symbol)
        if normalized_source:
            query = query.where(StockPriceSnapshot.source == normalized_source)
        if normalized_security_type:
            query = query.where(Stock.security_type == normalized_security_type)
        snapshot_count, latest_trade_time, sources = session.execute(query).one()
        security_count_query = select(func.count(Stock.id))
        if normalized_security_type:
            security_count_query = security_count_query.where(Stock.security_type == normalized_security_type)
        target_security_count = int(session.execute(security_count_query).scalar_one() or 0)
        snapshot_count_int = int(snapshot_count or 0)
        coverage_ratio = round(snapshot_count_int / target_security_count, 4) if target_security_count else 0
        return {
            "backend": _repo_backend(),
            "snapshot_count": snapshot_count_int,
            "latest_trade_time": _dt_text(latest_trade_time),
            "sources": [item for item in str(sources or "").split(",") if item],
            "source": normalized_source or "",
            "security_type": normalized_security_type or "",
            "security_count": target_security_count,
            "target_security_count": target_security_count,
            "coverage_ratio": coverage_ratio,
            "local_snapshot_coverage_ratio": coverage_ratio,
        }


def list_latest_snapshots(
    *,
    keyword: str | None = None,
    source: str | None = None,
    security_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    normalized_keyword = (keyword or "").strip()
    normalized_source = (source or "").strip()
    normalized_security_type = str(security_type or "").strip().lower()
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 200))
    offset = (safe_page - 1) * safe_page_size
    if _repo_backend() == "sqlite":
        where = []
        params: list[Any] = []
        if normalized_security_type:
            where.append("s.security_type=?")
            params.append(normalized_security_type)
        if normalized_keyword:
            where.append("(p.symbol LIKE ? OR s.name LIKE ?)")
            like = f"%{normalized_keyword}%"
            params.extend([like, like])
        if normalized_source:
            where.append("p.source=?")
            params.append(normalized_source)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        total = sqlite_q1(
            f"""SELECT COUNT(*) AS cnt
            FROM stock_price_snapshots p
            LEFT JOIN stocks s ON s.symbol=p.symbol
            {where_sql}""",
            tuple(params),
        ) or {}
        rows = sqlite_q(
            f"""SELECT p.symbol, COALESCE(s.name, p.symbol) AS name, s.exchange, s.security_type,
                s.status, s.is_suspended, s.is_delisting, p.trade_time,
                p.last_price, p.open, p.high, p.low, p.prev_close, p.volume, p.amount,
                p.bid_price, p.ask_price, p.source, p.updated_at
            FROM stock_price_snapshots p
            LEFT JOIN stocks s ON s.symbol=p.symbol
            {where_sql}
            ORDER BY COALESCE(p.trade_time, p.updated_at) DESC, p.symbol ASC
            LIMIT ? OFFSET ?""",
            tuple(params + [safe_page_size, offset]),
        )
        return {
            "items": [_snapshot_item(item) for item in rows],
            "total": int(total.get("cnt") or 0),
            "page": safe_page,
            "page_size": safe_page_size,
            "summary": snapshot_summary(normalized_source, security_type=normalized_security_type or None),
        }

    with session_scope() as session:
        query = (
            select(StockPriceSnapshot, Stock.name, Stock.exchange, Stock.security_type, Stock.status, Stock.is_suspended, Stock.is_delisting)
            .outerjoin(Stock, Stock.symbol == StockPriceSnapshot.symbol)
        )
        count_query = (
            select(func.count(StockPriceSnapshot.id))
            .select_from(StockPriceSnapshot)
            .outerjoin(Stock, Stock.symbol == StockPriceSnapshot.symbol)
        )
        if normalized_security_type:
            query = query.where(Stock.security_type == normalized_security_type)
            count_query = count_query.where(Stock.security_type == normalized_security_type)
        if normalized_keyword:
            predicate = or_(StockPriceSnapshot.symbol.like(f"%{normalized_keyword}%"), Stock.name.like(f"%{normalized_keyword}%"))
            query = query.where(predicate)
            count_query = count_query.where(predicate)
        if normalized_source:
            query = query.where(StockPriceSnapshot.source == normalized_source)
            count_query = count_query.where(StockPriceSnapshot.source == normalized_source)
        rows = session.execute(
            query.order_by(StockPriceSnapshot.trade_time.desc(), StockPriceSnapshot.symbol.asc()).limit(safe_page_size).offset(offset)
        ).all()
        return {
            "items": [
                _snapshot_item(
                    _public_model_snapshot(
                        snapshot,
                        name,
                        exchange,
                        security_type,
                        status=status,
                        is_suspended=is_suspended,
                        is_delisting=is_delisting,
                    )
                )
                for snapshot, name, exchange, security_type, status, is_suspended, is_delisting in rows
            ],
            "total": int(session.execute(count_query).scalar_one() or 0),
            "page": safe_page,
            "page_size": safe_page_size,
            "summary": snapshot_summary(normalized_source, security_type=normalized_security_type or None),
        }


def get_latest_snapshot(symbol: str, *, source: str | None = None) -> dict | None:
    normalized_symbol = str(symbol or "").strip()
    if not normalized_symbol:
        return None
    normalized_source = (source or "").strip()
    if _repo_backend() == "sqlite":
        where = ["p.symbol=?"]
        params: list[Any] = [normalized_symbol]
        if normalized_source:
            where.append("p.source=?")
            params.append(normalized_source)
        row = sqlite_q1(
            f"""SELECT p.symbol, COALESCE(s.name, p.symbol) AS name, s.exchange, s.security_type,
                s.status, s.is_suspended, s.is_delisting, p.trade_time,
                p.last_price, p.open, p.high, p.low, p.prev_close, p.volume, p.amount,
                p.bid_price, p.ask_price, p.source, p.updated_at
            FROM stock_price_snapshots p
            LEFT JOIN stocks s ON s.symbol=p.symbol
            WHERE {' AND '.join(where)}
            ORDER BY COALESCE(p.trade_time, p.updated_at) DESC
            LIMIT 1""",
            tuple(params),
        )
        return _snapshot_item(row) if row else None

    with session_scope() as session:
        query = (
            select(StockPriceSnapshot, Stock.name, Stock.exchange, Stock.security_type, Stock.status, Stock.is_suspended, Stock.is_delisting)
            .outerjoin(Stock, Stock.symbol == StockPriceSnapshot.symbol)
            .where(StockPriceSnapshot.symbol == normalized_symbol)
        )
        if normalized_source:
            query = query.where(StockPriceSnapshot.source == normalized_source)
        row = session.execute(query.order_by(StockPriceSnapshot.trade_time.desc()).limit(1)).first()
        if not row:
            return None
        snapshot, name, exchange, security_type, status, is_suspended, is_delisting = row
        return _snapshot_item(
            _public_model_snapshot(
                snapshot,
                name,
                exchange,
                security_type,
                status=status,
                is_suspended=is_suspended,
                is_delisting=is_delisting,
            )
        )


def auction_snapshot_summary(source: str | None = None, *, security_type: str | None = None) -> dict:
    normalized_source = (source or "").strip() or None
    normalized_security_type = str(security_type or "").strip().lower() or None
    if _repo_backend() == "sqlite":
        where = ["1=1"]
        params: list[Any] = []
        if normalized_source:
            where.append("a.source=?")
            params.append(normalized_source)
        if normalized_security_type:
            where.append("s.security_type=?")
            params.append(normalized_security_type)
        row = sqlite_q1(
            f"""SELECT COUNT(*) AS snapshot_count, MAX(a.auction_time) AS latest_auction_time,
                GROUP_CONCAT(DISTINCT a.source) AS sources
            FROM stock_auction_snapshots a
            LEFT JOIN stocks s ON s.symbol=a.symbol
            WHERE {' AND '.join(where)}""",
            tuple(params),
        ) or {}
        return {
            "backend": _repo_backend(),
            "snapshot_count": int(row.get("snapshot_count") or 0),
            "latest_auction_time": row.get("latest_auction_time"),
            "sources": [item for item in str(row.get("sources") or "").split(",") if item],
            "source": normalized_source or "",
            "security_type": normalized_security_type or "",
        }

    with session_scope() as session:
        query = select(
            func.count(StockAuctionSnapshot.id),
            func.max(StockAuctionSnapshot.auction_time),
            func.group_concat(func.distinct(StockAuctionSnapshot.source)),
        ).select_from(StockAuctionSnapshot).outerjoin(Stock, Stock.symbol == StockAuctionSnapshot.symbol)
        if normalized_source:
            query = query.where(StockAuctionSnapshot.source == normalized_source)
        if normalized_security_type:
            query = query.where(Stock.security_type == normalized_security_type)
        snapshot_count, latest_auction_time, sources = session.execute(query).one()
        return {
            "backend": _repo_backend(),
            "snapshot_count": int(snapshot_count or 0),
            "latest_auction_time": _dt_text(latest_auction_time),
            "sources": [item for item in str(sources or "").split(",") if item],
            "source": normalized_source or "",
            "security_type": normalized_security_type or "",
        }


def get_latest_auction_snapshot(
    symbol: str,
    *,
    trade_date: str | None = None,
    source: str | None = None,
    phase: str | None = "call_auction_0920_0925",
) -> dict | None:
    normalized_symbol = str(symbol or "").strip()
    if not normalized_symbol:
        return None
    normalized_source = (source or "").strip()
    normalized_phase = str(phase or "").strip()
    normalized_trade_date = str(trade_date or "").strip()
    if _repo_backend() == "sqlite":
        where = ["a.symbol=?"]
        params: list[Any] = [normalized_symbol]
        if normalized_trade_date:
            where.append("a.trade_date=?")
            params.append(normalized_trade_date)
        if normalized_source:
            where.append("a.source=?")
            params.append(normalized_source)
        if normalized_phase:
            where.append("a.phase=?")
            params.append(normalized_phase)
        row = sqlite_q1(
            f"""SELECT a.*, COALESCE(s.name, a.symbol) AS name, s.exchange, s.security_type,
                s.status, s.is_suspended, s.is_delisting
            FROM stock_auction_snapshots a
            LEFT JOIN stocks s ON s.symbol=a.symbol
            WHERE {' AND '.join(where)}
            ORDER BY a.trade_date DESC, a.auction_time DESC
            LIMIT 1""",
            tuple(params),
        )
        return _auction_item(row) if row else None

    with session_scope() as session:
        query = (
            select(StockAuctionSnapshot, Stock.name, Stock.exchange, Stock.security_type, Stock.status, Stock.is_suspended, Stock.is_delisting)
            .outerjoin(Stock, Stock.symbol == StockAuctionSnapshot.symbol)
            .where(StockAuctionSnapshot.symbol == normalized_symbol)
        )
        if normalized_trade_date:
            parsed_trade_date = _parse_date(normalized_trade_date)
            if parsed_trade_date:
                query = query.where(StockAuctionSnapshot.trade_date == parsed_trade_date)
        if normalized_source:
            query = query.where(StockAuctionSnapshot.source == normalized_source)
        if normalized_phase:
            query = query.where(StockAuctionSnapshot.phase == normalized_phase)
        row = session.execute(query.order_by(StockAuctionSnapshot.trade_date.desc(), StockAuctionSnapshot.auction_time.desc()).limit(1)).first()
        if not row:
            return None
        auction, name, exchange, security_type, status, is_suspended, is_delisting = row
        return _auction_item(
            _public_model_auction(
                auction,
                name,
                exchange,
                security_type,
                status=status,
                is_suspended=is_suspended,
                is_delisting=is_delisting,
            )
        )


def list_stocks(*, keyword: str | None = None, limit: int = 20, security_type: str | None = None) -> dict:
    normalized_keyword = (keyword or "").strip()
    normalized_security_type = str(security_type or "").strip().lower()
    safe_limit = max(1, min(int(limit or 20), 20000))
    if _repo_backend() == "sqlite":
        where_parts = []
        params: list[Any] = []
        if normalized_security_type:
            where_parts.append("security_type=?")
            params.append(normalized_security_type)
        if normalized_keyword:
            where_parts.append("(symbol LIKE ? OR name LIKE ?)")
            like = f"%{normalized_keyword}%"
            params.extend([like, like])
        where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        rows = sqlite_q(
            f"""SELECT symbol, name, exchange, market, security_type, industry, listing_date, status,
                is_st, board_type, limit_rule_profile, is_suspended, is_delisting
            FROM stocks
            {where}
            ORDER BY symbol ASC
            LIMIT ?""",
            tuple(params + [safe_limit]),
        )
        total = sqlite_q1(f"SELECT COUNT(*) AS cnt FROM stocks {where}", tuple(params)) or {}
        return {"items": rows, "total": int(total.get("cnt") or 0), "source": "local", "backend": _repo_backend()}

    with session_scope() as session:
        query = select(Stock)
        count_query = select(func.count(Stock.id))
        if normalized_security_type:
            query = query.where(Stock.security_type == normalized_security_type)
            count_query = count_query.where(Stock.security_type == normalized_security_type)
        if normalized_keyword:
            predicate = or_(Stock.symbol.like(f"%{normalized_keyword}%"), Stock.name.like(f"%{normalized_keyword}%"))
            query = query.where(predicate)
            count_query = count_query.where(predicate)
        rows = session.execute(query.order_by(Stock.symbol.asc()).limit(safe_limit)).scalars().all()
        return {
            "items": [
                _public_stock(
                    {
                        "symbol": row.symbol,
                        "name": row.name,
                        "exchange": row.exchange,
                        "market": row.market,
                        "security_type": row.security_type,
                        "industry": row.industry,
                        "listing_date": row.listing_date,
                        "status": row.status,
                        "is_st": row.is_st,
                        "board_type": row.board_type,
                        "limit_rule_profile": row.limit_rule_profile,
                        "is_suspended": row.is_suspended,
                        "is_delisting": row.is_delisting,
                    }
                )
                for row in rows
            ],
            "total": int(session.execute(count_query).scalar_one() or 0),
            "source": "local",
            "backend": _repo_backend(),
        }


def get_daily_bars(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    source: str | None = None,
    adjust: str | None = "qfq",
    interval: str | None = "1d",
) -> list[dict]:
    normalized_symbol = str(symbol or "").strip()
    if not normalized_symbol:
        return []
    normalized_source = (source or "").strip()
    normalized_adjust = _normalized_adjust(adjust)
    normalized_interval = normalize_bar_interval(interval)
    if _repo_backend() == "sqlite":
        where = ["symbol=?", "trade_date>=?", "trade_date<=?"]
        params: list[Any] = [normalized_symbol, start_date, end_date]
        if normalized_source:
            where.append("source=?")
            params.append(normalized_source)
        where.append("(adjust=? OR adjust='' OR adjust IS NULL)")
        params.append(normalized_adjust)
        where.append("(interval=? OR interval='' OR interval IS NULL)")
        params.append(normalized_interval)
        rows = sqlite_q(
            f"""SELECT symbol, trade_date, trade_time, interval, adjust, open, high, low, close, volume, amount, turnover_rate, source
            FROM stock_daily_bars
            WHERE {' AND '.join(where)}
            ORDER BY trade_time ASC, trade_date ASC""",
            tuple(params),
        )
        return [_daily_bar_item(row) for row in rows]

    with session_scope() as session:
        query = select(StockDailyBar).where(
            StockDailyBar.symbol == normalized_symbol,
            StockDailyBar.trade_date >= start_date,
            StockDailyBar.trade_date <= end_date,
            StockDailyBar.adjust == normalized_adjust,
            StockDailyBar.interval == normalized_interval,
        )
        if normalized_source:
            query = query.where(StockDailyBar.source == normalized_source)
        rows = session.execute(query.order_by(StockDailyBar.trade_time.asc(), StockDailyBar.trade_date.asc())).scalars().all()
        return [_daily_bar_item(_public_model_bar(row)) for row in rows]


def list_trading_dates(start_date: str, end_date: str, *, source: str | None = None) -> list[str]:
    normalized_source = (source or "").strip()
    if _repo_backend() == "sqlite":
        where = ["trade_date>=?", "trade_date<=?"]
        params: list[Any] = [start_date, end_date]
        if normalized_source:
            where.append("source=?")
            params.append(normalized_source)
        rows = sqlite_q(
            f"""SELECT DISTINCT trade_date
            FROM stock_daily_bars
            WHERE {' AND '.join(where)}
            ORDER BY trade_date ASC""",
            tuple(params),
        )
        return [str(row.get("trade_date")) for row in rows if row.get("trade_date")]

    with session_scope() as session:
        query = select(StockDailyBar.trade_date).where(
            StockDailyBar.trade_date >= start_date,
            StockDailyBar.trade_date <= end_date,
        )
        if normalized_source:
            query = query.where(StockDailyBar.source == normalized_source)
        rows = session.execute(query.distinct().order_by(StockDailyBar.trade_date.asc())).scalars().all()
        return [_date_text(item) for item in rows]


def create_sync_run(
    tenant_id: int,
    *,
    mode: str,
    source: str,
    adjust: str,
    requested_symbols: int,
    interval: str = "1d",
    payload: dict | None = None,
) -> dict:
    now = datetime.now()
    run_no = f"sync-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    normalized_payload = payload or {}
    normalized_interval = normalize_bar_interval(interval)
    if _repo_backend() == "sqlite":
        sqlite_execute_many(
            """INSERT INTO market_sync_runs
            (tenant_id, run_no, mode, source, adjust, interval, status, requested_symbols, started_at, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            [
                (
                    int(tenant_id or 0),
                    run_no,
                    str(mode or "incremental"),
                    str(source or "auto"),
                    _normalized_adjust(adjust),
                    normalized_interval,
                    int(requested_symbols or 0),
                    now.isoformat(timespec="seconds"),
                    json.dumps(normalized_payload, ensure_ascii=False),
                )
            ],
        )
        row = sqlite_q1("SELECT * FROM market_sync_runs WHERE run_no=?", (run_no,)) or {}
        return _sync_run_item(row)

    with session_scope() as session:
        row = MarketSyncRun(
            tenant_id=int(tenant_id or 0),
            run_no=run_no,
            mode=str(mode or "incremental"),
            source=str(source or "auto"),
            adjust=_normalized_adjust(adjust),
            interval=normalized_interval,
            status="running",
            requested_symbols=int(requested_symbols or 0),
            started_at=now,
            payload_json=normalized_payload,
        )
        session.add(row)
        session.flush()
        return _sync_run_item(_public_model_sync_run(row))


def record_sync_run_item(
    run_id: int | None,
    tenant_id: int,
    *,
    symbol: str,
    status: str,
    start_date: str | None,
    end_date: str | None,
    bars: int = 0,
    persisted_bars: int = 0,
    source: str = "auto",
    adjust: str = "qfq",
    interval: str = "1d",
    error: str | None = None,
) -> dict | None:
    if not run_id:
        return None
    now = datetime.now()
    if _repo_backend() == "sqlite":
        sqlite_execute_many(
            """INSERT INTO market_sync_run_items
            (tenant_id, run_id, symbol, status, start_date, end_date, bars, persisted_bars, source, adjust, interval, error, started_at, finished_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            [
                (
                    int(tenant_id or 0),
                    int(run_id),
                    str(symbol or ""),
                    str(status or "unknown"),
                    start_date,
                    end_date,
                    int(bars or 0),
                    int(persisted_bars or 0),
                    str(source or "auto"),
                    _normalized_adjust(adjust),
                    normalize_bar_interval(interval),
                    str(error or ""),
                    now.isoformat(timespec="seconds"),
                    now.isoformat(timespec="seconds"),
                )
            ],
        )
        row = sqlite_q1(
            """SELECT * FROM market_sync_run_items
            WHERE tenant_id=? AND run_id=? AND symbol=?
            ORDER BY id DESC LIMIT 1""",
            (int(tenant_id or 0), int(run_id), str(symbol or "")),
        )
        return _sync_run_detail_item(row) if row else None

    with session_scope() as session:
        item = MarketSyncRunItem(
            tenant_id=int(tenant_id or 0),
            run_id=int(run_id),
            symbol=str(symbol or ""),
            status=str(status or "unknown"),
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            bars=int(bars or 0),
            persisted_bars=int(persisted_bars or 0),
            source=str(source or "auto"),
            adjust=_normalized_adjust(adjust),
            interval=normalize_bar_interval(interval),
            error=str(error or "") or None,
            started_at=now,
            finished_at=now,
        )
        session.add(item)
        session.flush()
        return _sync_run_detail_item(_public_model_sync_run_item(item))


def finish_sync_run(run_id: int | None, *, status: str, result: dict | None = None) -> dict | None:
    if not run_id:
        return None
    normalized_result = result or {}
    finished_at = datetime.now()
    if _repo_backend() == "sqlite":
        sqlite_execute_many(
            """UPDATE market_sync_runs
            SET status=?, synced_symbols=?, failed_symbols=?, persisted_bars=?,
                finished_at=?, result_json=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
            [
                (
                    str(status or "completed"),
                    int(normalized_result.get("synced_symbols") or 0),
                    int(normalized_result.get("failed_symbols") or 0),
                    int(normalized_result.get("persisted_bars") or 0),
                    finished_at.isoformat(timespec="seconds"),
                    json.dumps(normalized_result, ensure_ascii=False),
                    int(run_id),
                )
            ],
        )
        row = sqlite_q1("SELECT * FROM market_sync_runs WHERE id=?", (int(run_id),))
        return _sync_run_item(row) if row else None

    with session_scope() as session:
        row = session.get(MarketSyncRun, int(run_id))
        if row is None:
            return None
        row.status = str(status or "completed")
        row.synced_symbols = int(normalized_result.get("synced_symbols") or 0)
        row.failed_symbols = int(normalized_result.get("failed_symbols") or 0)
        row.persisted_bars = int(normalized_result.get("persisted_bars") or 0)
        row.finished_at = finished_at
        row.result_json = normalized_result
        session.flush()
        return _sync_run_item(_public_model_sync_run(row))


def upsert_sync_state(
    tenant_id: int,
    *,
    symbol: str,
    source: str,
    adjust: str,
    interval: str = "1d",
    coverage: dict | None = None,
    status: str = "success",
    error: str | None = None,
) -> dict:
    now = datetime.now()
    normalized_symbol = str(symbol or "").strip()
    normalized_source = str(source or "auto").strip() or "auto"
    normalized_adjust = _normalized_adjust(adjust)
    normalized_interval = normalize_bar_interval(interval)
    coverage = coverage or get_symbol_coverage(normalized_symbol, source=None, adjust=normalized_adjust, interval=normalized_interval)
    first_trade_date = coverage.get("first_trade_date")
    last_trade_date = coverage.get("last_trade_date")
    has_error = bool(error)
    if _repo_backend() == "sqlite":
        sqlite_execute_many(
            """INSERT INTO market_sync_states
            (tenant_id, symbol, source, adjust, interval, coverage_start_date, coverage_end_date,
             last_success_trade_date, last_synced_at, status, error_count, last_error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(tenant_id, symbol, source, adjust, interval) DO UPDATE SET
                coverage_start_date=excluded.coverage_start_date,
                coverage_end_date=excluded.coverage_end_date,
                last_success_trade_date=CASE WHEN excluded.last_error='' THEN excluded.last_success_trade_date ELSE market_sync_states.last_success_trade_date END,
                last_synced_at=excluded.last_synced_at,
                status=excluded.status,
                error_count=CASE WHEN excluded.last_error='' THEN market_sync_states.error_count ELSE market_sync_states.error_count + 1 END,
                last_error=excluded.last_error,
                updated_at=CURRENT_TIMESTAMP""",
            [
                (
                    int(tenant_id or 0),
                    normalized_symbol,
                    normalized_source,
                    normalized_adjust,
                    normalized_interval,
                    first_trade_date,
                    last_trade_date,
                    last_trade_date if not has_error else None,
                    now.isoformat(timespec="seconds"),
                    status,
                    1 if has_error else 0,
                    str(error or ""),
                )
            ],
        )
        row = sqlite_q1(
            """SELECT st.*, s.name, s.exchange, s.market
            FROM market_sync_states st
            LEFT JOIN stocks s ON s.symbol=st.symbol
            WHERE st.tenant_id=? AND st.symbol=? AND st.source=? AND st.adjust=? AND st.interval=?""",
            (int(tenant_id or 0), normalized_symbol, normalized_source, normalized_adjust, normalized_interval),
        )
        return _sync_state_item(row or {})

    with session_scope() as session:
        row = session.execute(
            select(MarketSyncState).where(
                MarketSyncState.tenant_id == int(tenant_id or 0),
                MarketSyncState.symbol == normalized_symbol,
                MarketSyncState.source == normalized_source,
                MarketSyncState.adjust == normalized_adjust,
                MarketSyncState.interval == normalized_interval,
            )
        ).scalar_one_or_none()
        if row is None:
            row = MarketSyncState(
                tenant_id=int(tenant_id or 0),
                symbol=normalized_symbol,
                source=normalized_source,
                adjust=normalized_adjust,
                interval=normalized_interval,
                error_count=0,
            )
            session.add(row)
        row.coverage_start_date = _parse_date(first_trade_date)
        row.coverage_end_date = _parse_date(last_trade_date)
        row.last_success_trade_date = _parse_date(last_trade_date) if not has_error else row.last_success_trade_date
        row.last_synced_at = now
        row.status = status
        if has_error:
            row.error_count = int(row.error_count or 0) + 1
            row.last_error = str(error or "")
        else:
            row.last_error = None
        session.flush()
        stock = session.execute(select(Stock).where(Stock.symbol == normalized_symbol)).scalar_one_or_none()
        payload = _public_model_sync_state(row)
        if stock:
            payload.update({"name": stock.name, "exchange": stock.exchange, "market": stock.market})
        return _sync_state_item(payload)


def sync_state_summary(tenant_id: int, *, source: str | None = None, adjust: str | None = None, interval: str | None = None) -> dict:
    normalized_source = (source or "").strip()
    normalized_adjust = _normalized_adjust(adjust) if adjust is not None else ""
    normalized_interval = normalize_bar_interval(interval) if interval else ""
    if _repo_backend() == "sqlite":
        where = ["tenant_id=?"]
        params: list[Any] = [int(tenant_id or 0)]
        if normalized_source:
            where.append("source=?")
            params.append(normalized_source)
        if normalized_adjust:
            where.append("adjust=?")
            params.append(normalized_adjust)
        if normalized_interval:
            where.append("interval=?")
            params.append(normalized_interval)
        row = sqlite_q1(
            f"""SELECT COUNT(*) AS state_count,
                SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_count,
                SUM(CASE WHEN status!='success' THEN 1 ELSE 0 END) AS non_success_count,
                MIN(coverage_start_date) AS first_trade_date,
                MAX(coverage_end_date) AS last_trade_date,
                MIN(last_synced_at) AS first_synced_at,
                MAX(last_synced_at) AS last_synced_at
            FROM market_sync_states
            WHERE {' AND '.join(where)}""",
            tuple(params),
        ) or {}
        return _sync_state_summary_item(row, tenant_id, normalized_source, normalized_adjust, normalized_interval)

    with session_scope() as session:
        query = select(
            func.count(MarketSyncState.id),
            func.sum(case((MarketSyncState.status == "success", 1), else_=0)),
            func.sum(case((MarketSyncState.status != "success", 1), else_=0)),
            func.min(MarketSyncState.coverage_start_date),
            func.max(MarketSyncState.coverage_end_date),
            func.min(MarketSyncState.last_synced_at),
            func.max(MarketSyncState.last_synced_at),
        ).where(MarketSyncState.tenant_id == int(tenant_id or 0))
        if normalized_source:
            query = query.where(MarketSyncState.source == normalized_source)
        if normalized_adjust:
            query = query.where(MarketSyncState.adjust == normalized_adjust)
        if normalized_interval:
            query = query.where(MarketSyncState.interval == normalized_interval)
        row = session.execute(query).one()
        return _sync_state_summary_item(
            {
                "state_count": row[0],
                "success_count": row[1],
                "non_success_count": row[2],
                "first_trade_date": row[3],
                "last_trade_date": row[4],
                "first_synced_at": row[5],
                "last_synced_at": row[6],
            },
            tenant_id,
            normalized_source,
            normalized_adjust,
            normalized_interval,
        )


def list_sync_states(
    tenant_id: int,
    *,
    keyword: str | None = None,
    source: str | None = None,
    adjust: str | None = None,
    interval: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    normalized_keyword = (keyword or "").strip()
    normalized_source = (source or "").strip()
    normalized_adjust = _normalized_adjust(adjust) if adjust is not None else ""
    normalized_interval = normalize_bar_interval(interval) if interval else ""
    normalized_status = (status or "").strip()
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 200))
    offset = (safe_page - 1) * safe_page_size
    if _repo_backend() == "sqlite":
        where = ["st.tenant_id=?"]
        params: list[Any] = [int(tenant_id or 0)]
        if normalized_keyword:
            where.append("(st.symbol LIKE ? OR s.name LIKE ?)")
            like = f"%{normalized_keyword}%"
            params.extend([like, like])
        if normalized_source:
            where.append("st.source=?")
            params.append(normalized_source)
        if normalized_adjust:
            where.append("st.adjust=?")
            params.append(normalized_adjust)
        if normalized_interval:
            where.append("st.interval=?")
            params.append(normalized_interval)
        if normalized_status:
            where.append("st.status=?")
            params.append(normalized_status)
        where_sql = " AND ".join(where)
        total = sqlite_q1(
            f"""SELECT COUNT(*) AS cnt
            FROM market_sync_states st
            LEFT JOIN stocks s ON s.symbol=st.symbol
            WHERE {where_sql}""",
            tuple(params),
        ) or {}
        rows = sqlite_q(
            f"""SELECT st.*, s.name, s.exchange, s.market
            FROM market_sync_states st
            LEFT JOIN stocks s ON s.symbol=st.symbol
            WHERE {where_sql}
            ORDER BY COALESCE(st.coverage_end_date, '') ASC, st.symbol ASC
            LIMIT ? OFFSET ?""",
            tuple(params + [safe_page_size, offset]),
        )
        return {
            "items": [_sync_state_item(row) for row in rows],
            "total": int(total.get("cnt") or 0),
            "page": safe_page,
            "page_size": safe_page_size,
            "summary": sync_state_summary(tenant_id, source=normalized_source, adjust=normalized_adjust or None, interval=normalized_interval or None),
        }

    with session_scope() as session:
        query = select(MarketSyncState, Stock.name, Stock.exchange, Stock.market).outerjoin(Stock, Stock.symbol == MarketSyncState.symbol).where(
            MarketSyncState.tenant_id == int(tenant_id or 0),
        )
        count_query = select(func.count(MarketSyncState.id)).where(
            MarketSyncState.tenant_id == int(tenant_id or 0),
        )
        if normalized_keyword:
            predicate = or_(MarketSyncState.symbol.like(f"%{normalized_keyword}%"), Stock.name.like(f"%{normalized_keyword}%"))
            query = query.where(predicate)
            count_query = count_query.outerjoin(Stock, Stock.symbol == MarketSyncState.symbol).where(predicate)
        if normalized_source:
            query = query.where(MarketSyncState.source == normalized_source)
            count_query = count_query.where(MarketSyncState.source == normalized_source)
        if normalized_adjust:
            query = query.where(MarketSyncState.adjust == normalized_adjust)
            count_query = count_query.where(MarketSyncState.adjust == normalized_adjust)
        if normalized_interval:
            query = query.where(MarketSyncState.interval == normalized_interval)
            count_query = count_query.where(MarketSyncState.interval == normalized_interval)
        if normalized_status:
            query = query.where(MarketSyncState.status == normalized_status)
            count_query = count_query.where(MarketSyncState.status == normalized_status)
        rows = session.execute(
            query.order_by(MarketSyncState.coverage_end_date.asc(), MarketSyncState.symbol.asc()).limit(safe_page_size).offset(offset)
        ).all()
        items = []
        for state, name, exchange, market in rows:
            payload = _public_model_sync_state(state)
            payload.update({"name": name or state.symbol, "exchange": exchange or infer_exchange(state.symbol), "market": market or "A"})
            items.append(_sync_state_item(payload))
        return {
            "items": items,
            "total": int(session.execute(count_query).scalar_one() or 0),
            "page": safe_page,
            "page_size": safe_page_size,
            "summary": sync_state_summary(tenant_id, source=normalized_source, adjust=normalized_adjust or None, interval=normalized_interval or None),
        }


def list_sync_runs(tenant_id: int, *, page: int = 1, page_size: int = 20) -> dict:
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 100))
    offset = (safe_page - 1) * safe_page_size
    if _repo_backend() == "sqlite":
        total = sqlite_q1("SELECT COUNT(*) AS cnt FROM market_sync_runs WHERE tenant_id=?", (int(tenant_id or 0),)) or {}
        rows = sqlite_q(
            """SELECT * FROM market_sync_runs
            WHERE tenant_id=?
            ORDER BY COALESCE(started_at, created_at) DESC
            LIMIT ? OFFSET ?""",
            (int(tenant_id or 0), safe_page_size, offset),
        )
        return {"items": [_sync_run_item(row) for row in rows], "total": int(total.get("cnt") or 0), "page": safe_page, "page_size": safe_page_size}

    with session_scope() as session:
        rows = session.execute(
            select(MarketSyncRun)
            .where(MarketSyncRun.tenant_id == int(tenant_id or 0))
            .order_by(MarketSyncRun.started_at.desc())
            .limit(safe_page_size)
            .offset(offset)
        ).scalars().all()
        total = session.execute(select(func.count(MarketSyncRun.id)).where(MarketSyncRun.tenant_id == int(tenant_id or 0))).scalar_one()
        return {"items": [_sync_run_item(_public_model_sync_run(row)) for row in rows], "total": int(total or 0), "page": safe_page, "page_size": safe_page_size}


def list_coverage(
    *,
    keyword: str | None = None,
    source: str | None = None,
    security_type: str | None = "stock",
    interval: str | None = None,
    adjust: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    normalized_keyword = (keyword or "").strip()
    normalized_source = (source or "").strip()
    normalized_security_type = str(security_type or "").strip().lower()
    normalized_interval = normalize_bar_interval(interval) if interval else None
    normalized_adjust = _normalized_adjust(adjust) if adjust is not None else None
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 200))
    offset = (safe_page - 1) * safe_page_size
    if _repo_backend() == "sqlite":
        where = []
        params: list[Any] = []
        if normalized_security_type:
            where.append("s.security_type=?")
            params.append(normalized_security_type)
        if normalized_keyword:
            where.append("(s.symbol LIKE ? OR s.name LIKE ?)")
            like = f"%{normalized_keyword}%"
            params.extend([like, like])
        join_conditions = []
        join_params: list[Any] = []
        if normalized_source:
            join_conditions.append("b.source=?")
            join_params.append(normalized_source)
        if normalized_interval:
            join_conditions.append("b.interval=?")
            join_params.append(normalized_interval)
        if normalized_adjust:
            join_conditions.append("(b.adjust=? OR b.adjust='' OR b.adjust IS NULL)")
            join_params.append(normalized_adjust)
        join_filter = "AND " + " AND ".join(join_conditions) if join_conditions else ""
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        total = sqlite_q1(f"SELECT COUNT(*) AS cnt FROM stocks s {where_sql}", tuple(params)) or {}
        items = sqlite_q(
            f"""SELECT s.symbol, s.name, s.exchange, s.market, s.security_type,
                COUNT(b.id) AS bar_count,
                MIN(b.trade_date) AS first_trade_date,
                MAX(b.trade_date) AS last_trade_date,
                MAX(b.trade_time) AS last_trade_time,
                MAX(b.updated_at) AS last_updated_at,
                GROUP_CONCAT(DISTINCT b.source) AS sources,
                GROUP_CONCAT(DISTINCT b.adjust) AS adjusts,
                GROUP_CONCAT(DISTINCT b.interval) AS intervals
            FROM stocks s
            LEFT JOIN stock_daily_bars b ON b.symbol=s.symbol {join_filter}
            {where_sql}
            GROUP BY s.symbol, s.name, s.exchange, s.market, s.security_type
            ORDER BY COALESCE(MAX(b.trade_date), '') ASC, s.symbol ASC
            LIMIT ? OFFSET ?""",
            tuple(join_params + params + [safe_page_size, offset]),
        )
        return {
            "items": [_coverage_item(item) for item in items],
            "total": int(total.get("cnt") or 0),
            "page": safe_page,
            "page_size": safe_page_size,
            "summary": coverage_summary(normalized_source, interval=normalized_interval, security_type=normalized_security_type or None, adjust=normalized_adjust),
        }

    with session_scope() as session:
        stats_query = select(
            StockDailyBar.symbol.label("symbol"),
            func.count(StockDailyBar.id).label("bar_count"),
            func.min(StockDailyBar.trade_date).label("first_trade_date"),
            func.max(StockDailyBar.trade_date).label("last_trade_date"),
            func.max(StockDailyBar.trade_time).label("last_trade_time"),
            func.max(StockDailyBar.updated_at).label("last_updated_at"),
            func.group_concat(func.distinct(StockDailyBar.source)).label("sources"),
            func.group_concat(func.distinct(StockDailyBar.adjust)).label("adjusts"),
            func.group_concat(func.distinct(StockDailyBar.interval)).label("intervals"),
        )
        if normalized_source:
            stats_query = stats_query.where(StockDailyBar.source == normalized_source)
        if normalized_interval:
            stats_query = stats_query.where(StockDailyBar.interval == normalized_interval)
        if normalized_adjust:
            stats_query = stats_query.where(StockDailyBar.adjust == normalized_adjust)
        stats = stats_query.group_by(StockDailyBar.symbol).subquery()
        query = (
            select(
                Stock.symbol,
                Stock.name,
                Stock.exchange,
                Stock.market,
                Stock.security_type,
                stats.c.bar_count,
                stats.c.first_trade_date,
                stats.c.last_trade_date,
                stats.c.last_trade_time,
                stats.c.last_updated_at,
                stats.c.sources,
                stats.c.adjusts,
                stats.c.intervals,
            )
            .outerjoin(stats, stats.c.symbol == Stock.symbol)
        )
        count_query = select(func.count(Stock.id))
        if normalized_security_type:
            query = query.where(Stock.security_type == normalized_security_type)
            count_query = count_query.where(Stock.security_type == normalized_security_type)
        if normalized_keyword:
            predicate = or_(Stock.symbol.like(f"%{normalized_keyword}%"), Stock.name.like(f"%{normalized_keyword}%"))
            query = query.where(predicate)
            count_query = count_query.where(predicate)
        rows = session.execute(
            query.order_by(stats.c.last_trade_date.asc(), Stock.symbol.asc()).limit(safe_page_size).offset(offset)
        ).mappings().all()
        items = [_coverage_item(dict(row)) for row in rows]
        return {
            "items": items,
            "total": int(session.execute(count_query).scalar_one() or 0),
            "page": safe_page,
            "page_size": safe_page_size,
            "summary": coverage_summary(normalized_source, interval=normalized_interval, security_type=normalized_security_type or None, adjust=normalized_adjust),
        }


def _coverage_item(row: dict) -> dict:
    bar_count = int(row.get("bar_count") or 0)
    return {
        "symbol": row.get("symbol") or "",
        "name": row.get("name") or "",
        "exchange": row.get("exchange") or "",
        "market": row.get("market") or "",
        "security_type": row.get("security_type") or "stock",
        "bar_count": bar_count,
        "first_trade_date": _date_text(row.get("first_trade_date")) if row.get("first_trade_date") else None,
        "last_trade_date": _date_text(row.get("last_trade_date")) if row.get("last_trade_date") else None,
        "last_trade_time": _dt_text(row.get("last_trade_time")),
        "last_updated_at": _dt_text(row.get("last_updated_at")),
        "sources": [item for item in str(row.get("sources") or "").split(",") if item],
        "adjusts": [item for item in str(row.get("adjusts") or "").split(",") if item],
        "intervals": [item for item in str(row.get("intervals") or "").split(",") if item],
        "synced": bar_count > 0,
    }


def _limit_rule_item(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "exchange": str(row.get("exchange") or "").upper(),
        "board_type": str(row.get("board_type") or "main").lower(),
        "security_type": str(row.get("security_type") or "stock").lower(),
        "risk_warning": _bool_value(row.get("risk_warning")),
        "effective_from": _date_text(row.get("effective_from")) if row.get("effective_from") else None,
        "effective_to": _date_text(row.get("effective_to")) if row.get("effective_to") else None,
        "limit_up_rate": _decimal_float(_decimal_value(row.get("limit_up_rate"))),
        "limit_down_rate": _decimal_float(_decimal_value(row.get("limit_down_rate"))),
        "no_limit_first_days": int(row.get("no_limit_first_days") or 0),
        "status": row.get("status") or "active",
        "notes": row.get("notes") or "",
        "updated_at": _dt_text(row.get("updated_at")),
    }


def _daily_bar_item(row: dict) -> dict:
    return {
        "symbol": row.get("symbol") or "",
        "trade_date": _date_text(row.get("trade_date")),
        "trade_time": _dt_text(row.get("trade_time")),
        "interval": row.get("interval") or "1d",
        "adjust": row.get("adjust") or "qfq",
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "volume": row.get("volume"),
        "amount": row.get("amount"),
        "turnover_rate": row.get("turnover_rate"),
        "source": row.get("source") or "local",
    }


def _snapshot_item(row: dict) -> dict:
    return {
        "symbol": row.get("symbol") or "",
        "name": row.get("name") or row.get("symbol") or "",
        "exchange": row.get("exchange") or "",
        "security_type": row.get("security_type") or "other",
        "status": row.get("status") or "",
        "is_suspended": _bool_value(row.get("is_suspended")),
        "is_delisting": _bool_value(row.get("is_delisting")),
        "trade_time": _dt_text(row.get("trade_time")),
        "last_price": row.get("last_price"),
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "prev_close": row.get("prev_close"),
        "volume": row.get("volume"),
        "amount": row.get("amount"),
        "bid_price": row.get("bid_price"),
        "ask_price": row.get("ask_price"),
        "source": row.get("source") or "local",
        "updated_at": _dt_text(row.get("updated_at")),
    }


def _auction_item(row: dict) -> dict:
    return {
        "symbol": row.get("symbol") or "",
        "name": row.get("name") or row.get("symbol") or "",
        "exchange": row.get("exchange") or "",
        "security_type": row.get("security_type") or "other",
        "status": row.get("status") or "",
        "is_suspended": _bool_value(row.get("is_suspended")),
        "is_delisting": _bool_value(row.get("is_delisting")),
        "trade_date": _date_text(row.get("trade_date")) if row.get("trade_date") else None,
        "auction_time": _dt_text(row.get("auction_time")),
        "trade_time": _dt_text(row.get("auction_time")),
        "phase": row.get("phase") or "call_auction_0920_0925",
        "prev_close": row.get("prev_close"),
        "indicative_price": row.get("indicative_price"),
        "matched_volume": row.get("matched_volume"),
        "matched_amount": row.get("matched_amount"),
        "volume": row.get("matched_volume"),
        "amount": row.get("matched_amount"),
        "unmatched_buy_volume": row.get("unmatched_buy_volume"),
        "unmatched_sell_volume": row.get("unmatched_sell_volume"),
        "bid_price": row.get("bid_price"),
        "bid_volume": row.get("bid_volume"),
        "ask_price": row.get("ask_price"),
        "ask_volume": row.get("ask_volume"),
        "order_book": row.get("order_book") if isinstance(row.get("order_book"), (dict, list)) else _loads_json(row.get("order_book_json")),
        "withdrawal_buy_volume": row.get("withdrawal_buy_volume"),
        "withdrawal_sell_volume": row.get("withdrawal_sell_volume"),
        "withdrawal_buy_amount": row.get("withdrawal_buy_amount"),
        "withdrawal_sell_amount": row.get("withdrawal_sell_amount"),
        "seal_price": row.get("seal_price"),
        "seal_volume": row.get("seal_volume"),
        "seal_amount": row.get("seal_amount"),
        "seal_side": row.get("seal_side") or "",
        "source": row.get("source") or "local",
        "updated_at": _dt_text(row.get("updated_at")),
        "data_model": "auction_snapshot",
    }


def _loads_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return {}
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return {}


def _sync_state_item(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "tenant_id": int(row.get("tenant_id") or 0),
        "symbol": row.get("symbol") or "",
        "name": row.get("name") or row.get("symbol") or "",
        "exchange": row.get("exchange") or infer_exchange(row.get("symbol") or ""),
        "market": row.get("market") or "A",
        "source": row.get("source") or "auto",
        "adjust": row.get("adjust") or "qfq",
        "interval": row.get("interval") or "1d",
        "coverage_start_date": _date_text(row.get("coverage_start_date")) if row.get("coverage_start_date") else None,
        "coverage_end_date": _date_text(row.get("coverage_end_date")) if row.get("coverage_end_date") else None,
        "last_success_trade_date": _date_text(row.get("last_success_trade_date")) if row.get("last_success_trade_date") else None,
        "last_synced_at": _dt_text(row.get("last_synced_at")),
        "status": row.get("status") or "pending",
        "error_count": int(row.get("error_count") or 0),
        "last_error": row.get("last_error") or "",
        "created_at": _dt_text(row.get("created_at")),
        "updated_at": _dt_text(row.get("updated_at")),
    }


def _sync_state_summary_item(row: dict, tenant_id: int, source: str, adjust: str, interval: str = "") -> dict:
    return {
        "tenant_id": int(tenant_id or 0),
        "backend": _repo_backend(),
        "source": source or "",
        "adjust": adjust or "",
        "interval": interval or "",
        "state_count": int(row.get("state_count") or 0),
        "success_count": int(row.get("success_count") or 0),
        "non_success_count": int(row.get("non_success_count") or 0),
        "first_trade_date": _date_text(row.get("first_trade_date")) if row.get("first_trade_date") else None,
        "last_trade_date": _date_text(row.get("last_trade_date")) if row.get("last_trade_date") else None,
        "first_synced_at": _dt_text(row.get("first_synced_at")),
        "last_synced_at": _dt_text(row.get("last_synced_at")),
    }


def _sync_run_item(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "tenant_id": int(row.get("tenant_id") or 0),
        "run_no": row.get("run_no") or "",
        "mode": row.get("mode") or "incremental",
        "source": row.get("source") or "auto",
        "adjust": row.get("adjust") or "qfq",
        "interval": row.get("interval") or "1d",
        "status": row.get("status") or "running",
        "requested_symbols": int(row.get("requested_symbols") or 0),
        "synced_symbols": int(row.get("synced_symbols") or 0),
        "failed_symbols": int(row.get("failed_symbols") or 0),
        "persisted_bars": int(row.get("persisted_bars") or 0),
        "started_at": _dt_text(row.get("started_at")),
        "finished_at": _dt_text(row.get("finished_at")),
        "payload": _loads_json(row.get("payload_json")),
        "result": _loads_json(row.get("result_json")),
        "created_at": _dt_text(row.get("created_at")),
        "updated_at": _dt_text(row.get("updated_at")),
    }


def _sync_run_detail_item(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "tenant_id": int(row.get("tenant_id") or 0),
        "run_id": row.get("run_id"),
        "symbol": row.get("symbol") or "",
        "status": row.get("status") or "unknown",
        "start_date": _date_text(row.get("start_date")) if row.get("start_date") else None,
        "end_date": _date_text(row.get("end_date")) if row.get("end_date") else None,
        "bars": int(row.get("bars") or 0),
        "persisted_bars": int(row.get("persisted_bars") or 0),
        "source": row.get("source") or "auto",
        "adjust": row.get("adjust") or "qfq",
        "interval": row.get("interval") or "1d",
        "error": row.get("error") or "",
        "started_at": _dt_text(row.get("started_at")),
        "finished_at": _dt_text(row.get("finished_at")),
    }


def _public_model_bar(row: StockDailyBar) -> dict:
    return {
        "symbol": row.symbol,
        "trade_date": row.trade_date,
        "trade_time": row.trade_time,
        "interval": row.interval,
        "adjust": row.adjust,
        "open": _decimal_float(row.open),
        "high": _decimal_float(row.high),
        "low": _decimal_float(row.low),
        "close": _decimal_float(row.close),
        "volume": row.volume,
        "amount": _decimal_float(row.amount),
        "turnover_rate": _decimal_float(row.turnover_rate),
        "source": row.source,
    }


def _public_model_snapshot(
    row: StockPriceSnapshot,
    name: str | None = None,
    exchange: str | None = None,
    security_type: str | None = None,
    *,
    status: str | None = None,
    is_suspended: bool | None = None,
    is_delisting: bool | None = None,
) -> dict:
    return {
        "symbol": row.symbol,
        "name": name or row.symbol,
        "exchange": exchange or infer_exchange(row.symbol),
        "security_type": security_type or infer_security_type(row.symbol, name or row.symbol),
        "status": status or "",
        "is_suspended": bool(is_suspended),
        "is_delisting": bool(is_delisting),
        "trade_time": row.trade_time,
        "last_price": _decimal_float(row.last_price),
        "open": _decimal_float(row.open),
        "high": _decimal_float(row.high),
        "low": _decimal_float(row.low),
        "prev_close": _decimal_float(row.prev_close),
        "volume": row.volume,
        "amount": _decimal_float(row.amount),
        "bid_price": _decimal_float(row.bid_price),
        "ask_price": _decimal_float(row.ask_price),
        "source": row.source,
        "updated_at": row.updated_at,
    }


def _public_model_auction(
    row: StockAuctionSnapshot,
    name: str | None = None,
    exchange: str | None = None,
    security_type: str | None = None,
    *,
    status: str | None = None,
    is_suspended: bool | None = None,
    is_delisting: bool | None = None,
) -> dict:
    return {
        "symbol": row.symbol,
        "name": name or row.symbol,
        "exchange": exchange or infer_exchange(row.symbol),
        "security_type": security_type or infer_security_type(row.symbol, name or row.symbol),
        "status": status or "",
        "is_suspended": bool(is_suspended),
        "is_delisting": bool(is_delisting),
        "trade_date": row.trade_date,
        "auction_time": row.auction_time,
        "phase": row.phase,
        "prev_close": _decimal_float(row.prev_close),
        "indicative_price": _decimal_float(row.indicative_price),
        "matched_volume": row.matched_volume,
        "matched_amount": _decimal_float(row.matched_amount),
        "unmatched_buy_volume": row.unmatched_buy_volume,
        "unmatched_sell_volume": row.unmatched_sell_volume,
        "bid_price": _decimal_float(row.bid_price),
        "bid_volume": row.bid_volume,
        "ask_price": _decimal_float(row.ask_price),
        "ask_volume": row.ask_volume,
        "order_book": row.order_book or {},
        "withdrawal_buy_volume": row.withdrawal_buy_volume,
        "withdrawal_sell_volume": row.withdrawal_sell_volume,
        "withdrawal_buy_amount": _decimal_float(row.withdrawal_buy_amount),
        "withdrawal_sell_amount": _decimal_float(row.withdrawal_sell_amount),
        "seal_price": _decimal_float(row.seal_price),
        "seal_volume": row.seal_volume,
        "seal_amount": _decimal_float(row.seal_amount),
        "seal_side": row.seal_side or "",
        "source": row.source,
        "updated_at": row.updated_at,
    }


def _public_model_limit_rule(row: LimitRuleCalendar) -> dict:
    return {
        "id": row.id,
        "exchange": row.exchange,
        "board_type": row.board_type,
        "security_type": row.security_type,
        "risk_warning": row.risk_warning,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "limit_up_rate": _decimal_float(row.limit_up_rate),
        "limit_down_rate": _decimal_float(row.limit_down_rate),
        "no_limit_first_days": row.no_limit_first_days,
        "status": row.status,
        "notes": row.notes,
        "updated_at": row.updated_at,
    }


def _public_model_sync_state(row: MarketSyncState) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "symbol": row.symbol,
        "source": row.source,
        "adjust": row.adjust,
        "interval": row.interval,
        "coverage_start_date": row.coverage_start_date,
        "coverage_end_date": row.coverage_end_date,
        "last_success_trade_date": row.last_success_trade_date,
        "last_synced_at": row.last_synced_at,
        "status": row.status,
        "error_count": row.error_count,
        "last_error": row.last_error,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _public_model_sync_run(row: MarketSyncRun) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "run_no": row.run_no,
        "mode": row.mode,
        "source": row.source,
        "adjust": row.adjust,
        "interval": row.interval,
        "status": row.status,
        "requested_symbols": row.requested_symbols,
        "synced_symbols": row.synced_symbols,
        "failed_symbols": row.failed_symbols,
        "persisted_bars": row.persisted_bars,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "payload_json": row.payload_json or {},
        "result_json": row.result_json or {},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _public_model_sync_run_item(row: MarketSyncRunItem) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "run_id": row.run_id,
        "symbol": row.symbol,
        "status": row.status,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "bars": row.bars,
        "persisted_bars": row.persisted_bars,
        "source": row.source,
        "adjust": row.adjust,
        "interval": row.interval,
        "error": row.error,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
    }
