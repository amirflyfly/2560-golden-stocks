"""AkShare market data provider adapter."""

from __future__ import annotations

from .provider import DailyBar, HealthCheckResult, StockInfo
from .utils import infer_exchange, parse_date, to_decimal, to_int


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

    def get_daily_bars(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq") -> list[DailyBar]:
        self._ensure_client()
        df = self._ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust=adjust,
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
                )
            )
        return bars

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
