"""Mootdx market data provider adapter.

This adapter keeps mootdx isolated from business code. The exact upstream API can
vary by mootdx version, so calls are intentionally defensive and normalized here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .provider import AuctionSnapshot, DailyBar, HealthCheckResult, MarketDataCapabilities, QuoteSnapshot, StockInfo, derived_l1_capabilities
from .utils import clean_security_name, infer_exchange, infer_security_type, normalize_bar_interval, parse_date, to_decimal, to_int


CODE_KEYS = ("code", "symbol", "\u4ee3\u7801")
NAME_KEYS = ("name", "\u540d\u79f0")
MOOTDX_FREQUENCIES = {
    "5m": 0,
    "15m": 1,
    "30m": 2,
    "1h": 3,
    "1d": 9,
    "1m": 8,
}


class MootdxMarketDataProvider:
    name = "mootdx"
    _auction_note = "mootdx quote API does not expose full 9:20-9:25 order withdrawal and seal details"

    def __init__(self):
        self._quotes_client = None

    def _ensure_client(self):
        if self._quotes_client is None:
            try:
                from mootdx.quotes import Quotes
            except ImportError as exc:
                raise RuntimeError("mootdx is not installed; run pip install -U mootdx") from exc
            self._quotes_client = Quotes.factory(market="std")

    def get_stock_list(self) -> list[StockInfo]:
        self._ensure_client()
        if not hasattr(self._quotes_client, "stocks"):
            raise RuntimeError("current mootdx client does not expose stocks()")

        frames = []
        errors: list[str] = []
        for market, exchange in ((0, "SZ"), (1, "SH")):
            try:
                frames.append((exchange, self._quotes_client.stocks(market=market)))
            except Exception as exc:
                errors.append(f"market={market}: {exc}")
        if not frames:
            message = "; ".join(errors) if errors else "no stock list returned"
            raise RuntimeError(f"mootdx stocks() failed: {message}")

        items: list[StockInfo] = []
        seen: set[str] = set()
        for _exchange, frame in frames:
            for row in self._iter_rows(frame):
                symbol = str(self._row_value(row, *CODE_KEYS) or "").strip()
                if not symbol or symbol in seen:
                    continue
                name = clean_security_name(self._row_value(row, *NAME_KEYS) or symbol)
                security_type = infer_security_type(symbol, name)
                if security_type == "other":
                    continue
                items.append(StockInfo(symbol=symbol, name=name or symbol, exchange=infer_exchange(symbol), security_type=security_type))
                seen.add(symbol)
        return items

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq", interval: str = "1d") -> list[DailyBar]:
        self._ensure_client()
        normalized_interval = normalize_bar_interval(interval)
        normalized_adjust = str(adjust or "qfq").strip().lower()
        if normalized_adjust in {"qfq", "hfq"}:
            raise RuntimeError("mootdx daily bars are unadjusted in this adapter; use adjust=none or an adjusted fallback provider")
        if not hasattr(self._quotes_client, "bars"):
            raise RuntimeError("current mootdx client does not expose bars()")
        frequency = MOOTDX_FREQUENCIES.get(normalized_interval)
        if frequency is None:
            raise RuntimeError(f"mootdx bars do not support interval={normalized_interval}")
        bars: list[DailyBar] = []
        start = parse_date(start_date)
        end = parse_date(end_date)
        for row in self._iter_bar_rows(symbol, frequency=frequency, interval=normalized_interval):
            trade_time = self._parse_bar_datetime(row)
            trade_date = trade_time.date()
            if not start <= trade_date <= end:
                continue
            bars.append(
                DailyBar(
                    symbol=symbol,
                    trade_date=trade_date,
                    trade_time=trade_time,
                    interval=normalized_interval,
                    open=to_decimal(self._row_value(row, "open", "\u5f00\u76d8")),
                    high=to_decimal(self._row_value(row, "high", "\u6700\u9ad8")),
                    low=to_decimal(self._row_value(row, "low", "\u6700\u4f4e")),
                    close=to_decimal(self._row_value(row, "close", "\u6536\u76d8")),
                    volume=to_int(self._row_value(row, "vol", "volume", "\u6210\u4ea4\u91cf")),
                    amount=to_decimal(self._row_value(row, "amount", "\u6210\u4ea4\u989d")),
                    turnover_rate=to_decimal(self._row_value(row, "turnover_rate", "\u6362\u624b\u7387")),
                    source=self.name,
                )
            )
        return sorted(bars, key=lambda item: (item.trade_time or datetime.combine(item.trade_date, datetime.min.time()), item.symbol))

    def get_quote_snapshots(self, symbols: list[str]) -> list[QuoteSnapshot]:
        self._ensure_client()
        if not hasattr(self._quotes_client, "quotes"):
            raise RuntimeError("current mootdx client does not expose quotes()")
        wanted = [str(symbol or "").strip() for symbol in symbols if str(symbol or "").strip()]
        if not wanted:
            return []
        try:
            df = self._quotes_client.quotes(symbol=wanted)
        except Exception:
            frames = []
            for symbol in wanted:
                item = self._quotes_client.quotes(symbol=symbol)
                if item is not None:
                    frames.append(item)
            if not frames:
                return []
            try:
                import pandas as pd

                df = pd.concat(frames, ignore_index=True)
            except Exception:
                df = frames[0]

        snapshots: list[QuoteSnapshot] = []
        for row in self._iter_rows(df):
            symbol = self._row_value(row, *CODE_KEYS) or ""
            symbol = str(symbol).strip()
            if not symbol:
                continue
            snapshots.append(
                QuoteSnapshot(
                    symbol=symbol,
                    trade_time=self._parse_trade_time(row),
                    last_price=to_decimal(self._row_value(row, "price", "\u73b0\u4ef7", "\u6700\u65b0\u4ef7", "close")),
                    open=to_decimal(self._row_value(row, "open", "\u5f00\u76d8")),
                    high=to_decimal(self._row_value(row, "high", "\u6700\u9ad8")),
                    low=to_decimal(self._row_value(row, "low", "\u6700\u4f4e")),
                    prev_close=to_decimal(self._row_value(row, "last_close", "pre_close", "\u6628\u6536")),
                    volume=to_int(self._row_value(row, "vol", "volume", "\u6210\u4ea4\u91cf")),
                    amount=to_decimal(self._row_value(row, "amount", "\u6210\u4ea4\u989d")),
                    bid_price=to_decimal(self._row_value(row, "bid1", "bid1_price", "\u4e70\u4e00")),
                    ask_price=to_decimal(self._row_value(row, "ask1", "ask1_price", "\u5356\u4e00")),
                    source=self.name,
                )
            )
        return snapshots

    def get_auction_snapshots(self, symbols: list[str], trade_date: str | None = None) -> list[AuctionSnapshot]:
        snapshots = []
        quote_snapshots = self.get_quote_snapshots(symbols)
        requested_date = parse_date(trade_date or datetime.now())
        capabilities = self.get_capabilities().to_dict()
        for item in quote_snapshots:
            trade_time = item.trade_time if isinstance(item.trade_time, datetime) else self._parse_datetime_text(item.trade_time)
            if trade_time.date() != requested_date:
                trade_time = datetime.combine(requested_date, trade_time.time())
            snapshots.append(
                AuctionSnapshot(
                    symbol=item.symbol,
                    trade_date=requested_date,
                    auction_time=trade_time,
                    indicative_price=item.open or item.last_price,
                    matched_volume=item.volume,
                    matched_amount=item.amount,
                    prev_close=item.prev_close,
                    bid_price=item.bid_price,
                    ask_price=item.ask_price,
                    order_book={
                        "source_quality": "derived_l1",
                        "data_quality": "derived_l1",
                        "provider": self.name,
                        "order_book_depth": 1,
                        "note": self._auction_note,
                    },
                    source_quality="derived_l1",
                    capabilities=capabilities,
                    source=self.name,
                )
            )
        return snapshots

    def get_capabilities(self) -> MarketDataCapabilities:
        return derived_l1_capabilities(self.name, note=self._auction_note)

    def get_trading_dates(self, start_date: str, end_date: str) -> list[str]:
        bars = self.get_daily_bars("000001", start_date, end_date, adjust="none")
        return [bar.trade_date.isoformat() for bar in bars]

    def health_check(self) -> HealthCheckResult:
        try:
            self._ensure_client()
            return HealthCheckResult(provider=self.name, ok=True)
        except Exception as exc:
            return HealthCheckResult(provider=self.name, ok=False, message=str(exc))

    def _row_value(self, row: Any, *keys: str):
        for key in keys:
            try:
                value = row.get(key)
            except AttributeError:
                value = row.get(key) if isinstance(row, dict) else None
            if value not in (None, ""):
                return value
        return None

    def _iter_rows(self, frame: Any):
        if frame is None:
            return
        if hasattr(frame, "iterrows"):
            for _, row in frame.iterrows():
                yield row
            return
        if isinstance(frame, dict):
            yield frame
            return
        for row in frame:
            yield row

    def _parse_trade_time(self, row) -> datetime:
        raw = self._row_value(row, "datetime", "time", "\u65f6\u95f4", "date", "\u65e5\u671f")
        if raw:
            text = str(raw).strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
                try:
                    return datetime.strptime(text, fmt)
                except ValueError:
                    continue
        return datetime.now()

    def _parse_bar_datetime(self, row) -> datetime:
        raw = self._row_value(row, "datetime", "time", "\u65f6\u95f4", "date", "\u65e5\u671f")
        if raw:
            text = str(raw).strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
                try:
                    return datetime.strptime(text[:19] if " " in fmt else text[:10], fmt)
                except ValueError:
                    continue
        trade_date = parse_date(raw or datetime.now())
        return datetime.combine(trade_date, datetime.min.time())

    def _parse_datetime_text(self, value) -> datetime:
        text = str(value or "").strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(text[:19] if " " in fmt or "T" in fmt else text[:10], fmt)
            except ValueError:
                continue
        return datetime.now()

    def _iter_bar_rows(self, symbol: str, *, frequency: int, interval: str):
        max_pages = 1 if interval == "1d" else 4
        start = 0
        for _ in range(max_pages):
            df = self._quotes_client.bars(symbol=symbol, frequency=frequency, start=start, offset=800)
            rows = list(self._iter_rows(df))
            if not rows:
                break
            for row in rows:
                yield row
            if len(rows) < 800:
                break
            start += len(rows)
