"""Mootdx market data provider adapter.

This adapter keeps mootdx isolated from business code. The exact upstream API can
vary by mootdx version, so calls are intentionally defensive and normalized here.
"""

from __future__ import annotations

from .provider import DailyBar, HealthCheckResult, StockInfo
from .utils import infer_exchange, parse_date, to_decimal, to_int


class MootdxMarketDataProvider:
    name = "mootdx"

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
        df = self._quotes_client.stocks(market=0)
        items: list[StockInfo] = []
        for _, row in df.iterrows():
            symbol = str(row.get("code") or row.get("代码") or "").strip()
            name = str(row.get("name") or row.get("名称") or "").strip()
            if symbol:
                items.append(StockInfo(symbol=symbol, name=name, exchange=infer_exchange(symbol)))
        return items

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq") -> list[DailyBar]:
        self._ensure_client()
        if not hasattr(self._quotes_client, "bars"):
            raise RuntimeError("current mootdx client does not expose bars()")
        market = 1 if infer_exchange(symbol) == "SH" else 0
        df = self._quotes_client.bars(symbol=symbol, market=market, frequency=9)
        bars: list[DailyBar] = []
        start = parse_date(start_date)
        end = parse_date(end_date)
        for _, row in df.iterrows():
            trade_date = parse_date(row.get("datetime") or row.get("date") or row.get("日期"))
            if not start <= trade_date <= end:
                continue
            bars.append(
                DailyBar(
                    symbol=symbol,
                    trade_date=trade_date,
                    open=to_decimal(row.get("open") or row.get("开盘")),
                    high=to_decimal(row.get("high") or row.get("最高")),
                    low=to_decimal(row.get("low") or row.get("最低")),
                    close=to_decimal(row.get("close") or row.get("收盘")),
                    volume=to_int(row.get("vol") or row.get("volume") or row.get("成交量")),
                    amount=to_decimal(row.get("amount") or row.get("成交额")),
                    turnover_rate=to_decimal(row.get("turnover_rate") or row.get("换手率")),
                    source=self.name,
                )
            )
        return bars

    def get_trading_dates(self, start_date: str, end_date: str) -> list[str]:
        bars = self.get_daily_bars("000001", start_date, end_date)
        return [bar.trade_date.isoformat() for bar in bars]

    def health_check(self) -> HealthCheckResult:
        try:
            self._ensure_client()
            return HealthCheckResult(provider=self.name, ok=True)
        except Exception as exc:
            return HealthCheckResult(provider=self.name, ok=False, message=str(exc))
