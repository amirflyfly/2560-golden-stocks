"""AkShare market data provider adapter."""

from __future__ import annotations

from datetime import datetime

from .provider import DailyBar, HealthCheckResult, QuoteSnapshot, StockInfo
from .utils import infer_exchange, normalize_bar_interval, parse_date, to_decimal, to_int


class AkShareMarketDataProvider:
    name = "akshare"

    def __init__(self):
        self._ak = None

    def _ensure_client(self):
        if self._ak is None:
            import akshare as ak
            self._ak = ak

    def get_stock_list(self) -> list[StockInfo]:
        self._ensure_client()
        df = self._ak.stock_info_a_code_name()
        items: list[StockInfo] = []
        for _, row in df.iterrows():
            symbol = str(row.get("代码") or row.get("code") or "").strip()
            name = str(row.get("名称") or row.get("name") or "").strip()
            if symbol:
                items.append(StockInfo(symbol=symbol, name=name, exchange=infer_exchange(symbol)))
        return items

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq", interval: str = "1d") -> list[DailyBar]:
        self._ensure_client()
        normalized_interval = normalize_bar_interval(interval)
        if normalized_interval != "1d":
            return self._get_minute_bars(symbol, start_date, end_date, adjust=adjust, interval=normalized_interval)
        provider_adjust = "" if str(adjust or "").lower() in {"none", "raw", "bfq"} else adjust
        df = self._ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust=provider_adjust,
        )
        bars: list[DailyBar] = []
        for _, row in df.iterrows():
            bars.append(
                DailyBar(
                    symbol=symbol,
                    trade_date=parse_date(row.get("日期")),
                    open=to_decimal(row.get("开盘")),
                    high=to_decimal(row.get("最高")),
                    low=to_decimal(row.get("最低")),
                    close=to_decimal(row.get("收盘")),
                    volume=to_int(row.get("成交量")),
                    amount=to_decimal(row.get("成交额")),
                    turnover_rate=to_decimal(row.get("换手率")),
                    source=self.name,
                    interval="1d",
                )
            )
        return bars

    def _get_minute_bars(self, symbol: str, start_date: str, end_date: str, *, adjust: str, interval: str) -> list[DailyBar]:
        if interval not in {"5m", "15m", "30m", "1h"}:
            raise RuntimeError(f"akshare minute bars do not support interval={interval}")
        provider_adjust = "" if str(adjust or "").lower() in {"none", "raw", "bfq", "qfq"} else adjust
        period = "60" if interval == "1h" else interval.removesuffix("m")
        df = self._ak.stock_zh_a_hist_min_em(
            symbol=symbol,
            start_date=f"{start_date} 09:30:00",
            end_date=f"{end_date} 15:00:00",
            period=period,
            adjust=provider_adjust,
        )
        bars: list[DailyBar] = []
        start = parse_date(start_date)
        end = parse_date(end_date)
        for _, row in df.iterrows():
            trade_time = self._parse_datetime(row.get("时间") or row.get("datetime") or row.get("date"))
            if not trade_time or not start <= trade_time.date() <= end:
                continue
            bars.append(
                DailyBar(
                    symbol=symbol,
                    trade_date=trade_time.date(),
                    trade_time=trade_time,
                    interval=interval,
                    open=to_decimal(row.get("开盘") or row.get("open")),
                    high=to_decimal(row.get("最高") or row.get("high")),
                    low=to_decimal(row.get("最低") or row.get("low")),
                    close=to_decimal(row.get("收盘") or row.get("close")),
                    volume=to_int(row.get("成交量") or row.get("volume")),
                    amount=to_decimal(row.get("成交额") or row.get("amount")),
                    source=self.name,
                )
            )
        return bars

    def _parse_datetime(self, value) -> datetime | None:
        if isinstance(value, datetime):
            return value
        text = str(value or "").strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:19] if " " in fmt else text[:10], fmt)
            except ValueError:
                continue
        return None

    def get_quote_snapshots(self, symbols: list[str]) -> list[QuoteSnapshot]:
        self._ensure_client()
        wanted = {str(symbol or "").strip() for symbol in symbols if str(symbol or "").strip()}
        if not wanted:
            return []
        df = self._ak.stock_zh_a_spot_em()
        snapshots: list[QuoteSnapshot] = []
        for _, row in df.iterrows():
            symbol = str(row.get("代码") or row.get("code") or "").strip()
            if symbol not in wanted:
                continue
            snapshots.append(
                QuoteSnapshot(
                    symbol=symbol,
                    trade_time=datetime.now(),
                    last_price=to_decimal(row.get("最新价") or row.get("price")),
                    open=to_decimal(row.get("今开") or row.get("open")),
                    high=to_decimal(row.get("最高") or row.get("high")),
                    low=to_decimal(row.get("最低") or row.get("low")),
                    prev_close=to_decimal(row.get("昨收") or row.get("pre_close")),
                    volume=to_int(row.get("成交量") or row.get("volume")),
                    amount=to_decimal(row.get("成交额") or row.get("amount")),
                    bid_price=to_decimal(row.get("买一") or row.get("bid1")),
                    ask_price=to_decimal(row.get("卖一") or row.get("ask1")),
                    source=self.name,
                )
            )
        return snapshots

    def get_trading_dates(self, start_date: str, end_date: str) -> list[str]:
        self._ensure_client()
        df = self._ak.tool_trade_date_hist_sina()
        start = parse_date(start_date)
        end = parse_date(end_date)
        dates = []
        for value in df["trade_date"].tolist():
            item = parse_date(value)
            if start <= item <= end:
                dates.append(item.isoformat())
        return dates

    def health_check(self) -> HealthCheckResult:
        try:
            self._ensure_client()
            return HealthCheckResult(provider=self.name, ok=True)
        except Exception as exc:
            return HealthCheckResult(provider=self.name, ok=False, message=str(exc))
