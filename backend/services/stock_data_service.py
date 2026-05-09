"""Stock data service for multiple data sources with unified interface."""

import os
import pickle
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import List

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - local test fallback
    pd = None


PROXY_ENV_KEYS = [
    'http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY',
    'all_proxy', 'ALL_PROXY', 'no_proxy', 'NO_PROXY'
]


REAL_DATA_MIN_DATE = '1990-01-01'


class SimpleTable(list):
    @property
    def empty(self):
        return len(self) == 0

    @property
    def columns(self):
        return list(self[0].keys()) if self else []

    def head(self, count):
        return SimpleTable(self[:count])

    def iterrows(self):
        for index, row in enumerate(self):
            yield index, row


def fallback_stock_table():
    rows = []
    if pd is not None:
        return pd.DataFrame(rows)
    return SimpleTable(rows)


def ensure_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


@contextmanager
def proxy_disabled():
    original = {}
    for key in PROXY_ENV_KEYS:
        if key in os.environ:
            original[key] = os.environ.pop(key)

    try:
        try:
            from akshare.utils.context import set_proxies as ak_set_proxies
            ak_set_proxies(None)
        except Exception:
            pass

        try:
            import requests
            original_merge = requests.sessions.Session.merge_environment_settings

            def merge_environment_settings(self, url, proxies, stream, verify, cert):
                settings = original_merge(self, url, proxies, stream, verify, cert)
                settings['proxies'] = {}
                return settings

            requests.sessions.Session.merge_environment_settings = merge_environment_settings
        except Exception:
            original_merge = None

        yield
    finally:
        try:
            import requests
            if 'original_merge' in locals() and original_merge is not None:
                requests.sessions.Session.merge_environment_settings = original_merge
        except Exception:
            pass

        for key, value in original.items():
            os.environ[key] = value


class StockDataSource:
    def __init__(self):
        self.name = "BaseDataSource"

    def get_stock_list(self):
        raise NotImplementedError

    def get_stock_hist(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq", interval: str = "1d"):
        raise NotImplementedError

    def get_trading_dates(self, start_date: str, end_date: str) -> List[str]:
        raise NotImplementedError


class LocalMarketDataSource(StockDataSource):
    def __init__(self):
        super().__init__()
        self.name = "LocalMarketData"

    def get_stock_list(self):
        from backend.repositories import market_data_repo

        try:
            payload = market_data_repo.list_stocks(limit=500)
        except Exception:
            payload = {"items": []}
        rows = [
            {"代码": item.get("symbol"), "名称": item.get("name") or item.get("symbol")}
            for item in payload.get("items", [])
        ]
        if pd is not None:
            return pd.DataFrame(rows)
        return SimpleTable(rows)

    def get_stock_hist(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq", interval: str = "1d"):
        from backend.repositories import market_data_repo

        try:
            bars = market_data_repo.get_daily_bars(symbol, start_date, end_date, adjust=adjust, interval=interval)
        except Exception:
            bars = []
        rows = [
            {
                "date": bar.get("trade_date"),
                "open": bar.get("open"),
                "close": bar.get("close"),
                "high": bar.get("high"),
                "low": bar.get("low"),
                "volume": bar.get("volume"),
                "amount": bar.get("amount"),
                "turnover": bar.get("turnover_rate"),
                "source": bar.get("source"),
                "adjust": bar.get("adjust"),
                "interval": bar.get("interval"),
            }
            for bar in bars
        ]
        if pd is not None:
            return pd.DataFrame(rows)
        return SimpleTable(rows)

    def get_trading_dates(self, start_date: str, end_date: str) -> List[str]:
        from backend.repositories import market_data_repo

        try:
            return market_data_repo.list_trading_dates(start_date, end_date)
        except Exception:
            return []


class AkShareDataSource(StockDataSource):
    def __init__(self):
        super().__init__()
        self.name = "AkShare"
        self._ak = None

    def _ensure_akshare(self):
        if self._ak is None:
            with proxy_disabled():
                import akshare as ak
                self._ak = ak

    def _to_sina_symbol(self, symbol: str) -> str:
        if symbol.startswith(('sh', 'sz', 'bj')):
            return symbol
        if symbol.startswith(('600', '601', '603', '605', '688', '689', '900')):
            return f'sh{symbol}'
        if symbol.startswith(('000', '001', '002', '003', '200', '300', '301')):
            return f'sz{symbol}'
        if symbol.startswith(('430', '830', '831', '832', '833', '835', '836', '837', '838', '839', '870', '871', '872', '873', '874', '875', '876', '877', '878', '879', '880', '881', '882', '883', '884', '885', '886', '887', '888', '889')):
            return f'bj{symbol}'
        return f'sz{symbol}'

    def get_stock_list(self):
        self._ensure_akshare()

        with proxy_disabled():
            try:
                df = self._ak.stock_info_a_code_name()
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return df
            except Exception as e:
                print(f"stock_info_a_code_name failed: {e}")

            try:
                df2 = self._ak.stock_zh_a_spot_em()
                if isinstance(df2, pd.DataFrame) and not df2.empty:
                    return df2[[c for c in df2.columns if c in ('代码', '名称', 'code', 'name')]]
            except Exception as e:
                print(f"stock_zh_a_spot_em failed: {e}")

            try:
                sh = self._ak.stock_info_sh_name_code()
            except Exception:
                sh = pd.DataFrame()
            try:
                sz = self._ak.stock_info_sz_name_code()
            except Exception:
                sz = pd.DataFrame()

        if isinstance(sh, pd.DataFrame) and not sh.empty:
            sh = sh.rename(columns={'证券代码': '代码', '证券简称': '名称'})
        if isinstance(sz, pd.DataFrame) and not sz.empty:
            sz = sz.rename(columns={'A股代码': '代码', 'A股简称': '名称'})

        merged = pd.concat([d for d in [sh, sz] if isinstance(d, pd.DataFrame)], ignore_index=True)
        if not merged.empty and '代码' in merged.columns and '名称' in merged.columns:
            merged = merged[['代码', '名称']].dropna().drop_duplicates()
            return merged

        return fallback_stock_table()

    def _get_hist_from_eastmoney(self, symbol: str, start_date: str, end_date: str, adjust: str):
        start_str = start_date.replace('-', '')
        end_str = end_date.replace('-', '')
        provider_adjust = '' if str(adjust or '').lower() in {'none', 'raw', 'bfq'} else adjust
        with proxy_disabled():
            return self._ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                adjust=provider_adjust,
                start_date=start_str,
                end_date=end_str
            )

    def _get_hist_from_sina(self, symbol: str, start_date: str, end_date: str, adjust: str):
        sina_adjust = adjust if adjust in ('', 'qfq', 'hfq') else ''
        with proxy_disabled():
            return self._ak.stock_zh_a_daily(
                symbol=self._to_sina_symbol(symbol),
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust=sina_adjust,
            )

    def get_stock_hist(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq", interval: str = "1d"):
        if str(interval or "1d").strip().lower() not in {"1d", "day", "daily"}:
            return pd.DataFrame()
        self._ensure_akshare()

        errors = []
        for loader in (self._get_hist_from_eastmoney, self._get_hist_from_sina):
            try:
                df = loader(symbol, start_date, end_date, adjust)
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return df
            except Exception as e:
                errors.append(str(e))

        if errors:
            print(f"Failed to get historical data for {symbol}: {' | '.join(errors)}")
        return pd.DataFrame()

    def get_trading_dates(self, start_date: str, end_date: str) -> List[str]:
        self._ensure_akshare()

        try:
            with proxy_disabled():
                cal = self._ak.tool_trade_date_hist_sina()
            trade_dates = cal[cal['trade_date'] >= start_date]['trade_date'].tolist()
            trade_dates = [d for d in trade_dates if d <= end_date]
            return trade_dates
        except Exception as e:
            print(f"Failed to get trading dates: {e}")
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            trade_dates = []
            current = start
            while current <= end:
                if current.weekday() < 5:
                    trade_dates.append(current.strftime('%Y-%m-%d'))
                current += timedelta(days=1)
            return trade_dates


class StockDataService:
    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = cache_dir
        ensure_directory(self.cache_dir)
        self.data_sources = {
            "local": LocalMarketDataSource(),
            "akshare": AkShareDataSource(),
        }
        self.default_source = "local"
        self.external_fallback_sources = ["akshare"]

    def _data_source_or_raise(self, source: str) -> StockDataSource:
        data_source = self.data_sources.get(source)
        if data_source is None:
            raise ValueError(f"unsupported stock data source: {source}")
        return data_source

    def get_stock_list(self, source: str = None):
        if source is None:
            local_list = self.data_sources["local"].get_stock_list()
            if local_list is not None and not local_list.empty:
                return local_list
            if os.getenv("MARKET_DATA_LOCAL_ONLY", "").strip() == "1":
                return local_list
            source = "akshare"
        source = source or self.default_source
        cache_key = f"stock_list_{source}"
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")

        if os.path.exists(cache_file):
            mtime = os.path.getmtime(cache_file)
            if datetime.now().timestamp() - mtime < 86400:
                try:
                    with open(cache_file, 'rb') as f:
                        return pickle.load(f)
                except Exception:
                    pass

        data_source = self._data_source_or_raise(source)
        stock_list = data_source.get_stock_list()

        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(stock_list, f)
        except Exception as e:
            print(f"Failed to save stock list cache: {e}")

        return stock_list

    def _looks_like_mock_cache(self, df) -> bool:
        if df is None or df.empty or 'date' not in df.columns:
            return False

        temp_df = df.copy()
        temp_df['date'] = pd.to_datetime(temp_df['date'], errors='coerce')
        temp_df = temp_df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
        if len(temp_df) < 5:
            return False

        weekday_series = temp_df['date'].dt.weekday
        if ((weekday_series == 5) | (weekday_series == 6)).any():
            return True

        if 'close' in temp_df.columns:
            pct = pd.to_numeric(temp_df['close'], errors='coerce').pct_change().dropna().round(6)
            if len(pct) >= 5 and pct.nunique() <= 2:
                return True

        return False

    def _is_cache_usable(self, df, source: str) -> bool:
        if df is None or df.empty:
            return False
        if source == 'akshare' and self._looks_like_mock_cache(df):
            return False
        return True

    def get_stock_hist(self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq", source: str = None, interval: str = "1d"):
        interval = str(interval or "1d").strip().lower() or "1d"
        if source is None:
            local_df = self.data_sources["local"].get_stock_hist(symbol, start_date, end_date, adjust, interval=interval)
            local_df = self._normalize_data(local_df)
            if self._is_cache_usable(local_df, "local"):
                return local_df
            if os.getenv("MARKET_DATA_LOCAL_ONLY", "").strip() == "1":
                return local_df
            for fallback_source in self.external_fallback_sources:
                df = self.get_stock_hist(symbol, start_date, end_date, adjust=adjust, source=fallback_source, interval=interval)
                if self._is_cache_usable(df, fallback_source):
                    self._persist_hist_to_local(symbol, df, adjust=adjust, source=fallback_source, interval=interval)
                    return df
            return local_df

        source = source or self.default_source
        cache_key = f"stock_hist_{symbol}_{start_date}_{end_date}_{adjust}_{interval}_{source}"
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")

        if os.path.exists(cache_file):
            mtime = os.path.getmtime(cache_file)
            if datetime.now().timestamp() - mtime < 7 * 86400:
                try:
                    with open(cache_file, 'rb') as f:
                        df = pickle.load(f)
                        if self._is_cache_usable(df, source):
                            return df
                except Exception:
                    pass

        data_source = self._data_source_or_raise(source)
        df = data_source.get_stock_hist(symbol, start_date, end_date, adjust, interval=interval)
        df = self._normalize_data(df)

        if self._is_cache_usable(df, source):
            try:
                with open(cache_file, 'wb') as f:
                    pickle.dump(df, f)
            except Exception as e:
                print(f"Failed to save stock hist cache: {e}")

        return df

    def get_trading_dates(self, start_date: str, end_date: str, source: str = None) -> List[str]:
        if source is None:
            local_dates = self.data_sources["local"].get_trading_dates(start_date, end_date)
            if local_dates:
                return local_dates
            if os.getenv("MARKET_DATA_LOCAL_ONLY", "").strip() == "1":
                return local_dates
            source = "akshare"
        source = source or self.default_source
        cache_key = f"trading_dates_{start_date}_{end_date}_{source}"
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.pkl")

        if os.path.exists(cache_file):
            mtime = os.path.getmtime(cache_file)
            if datetime.now().timestamp() - mtime < 30 * 86400:
                try:
                    with open(cache_file, 'rb') as f:
                        return pickle.load(f)
                except Exception:
                    pass

        data_source = self._data_source_or_raise(source)
        dates = data_source.get_trading_dates(start_date, end_date)

        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(dates, f)
        except Exception as e:
            print(f"Failed to save trading dates cache: {e}")

        return dates

    def _normalize_data(self, df):
        if df is None or df.empty:
            return df

        mapping = {
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
            '振幅': 'amplitude',
            '涨跌幅': 'pct_chg',
            '涨跌额': 'chg_amt',
            '换手率': 'turnover'
        }

        for old_col, new_col in mapping.items():
            if old_col in df.columns:
                df = df.rename(columns={old_col: new_col})

        essential_cols = ['date', 'open', 'close', 'high', 'low', 'volume']
        for col in essential_cols:
            if col not in df.columns:
                df[col] = 0

        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date'])
            df = df[df['date'] >= pd.Timestamp(REAL_DATA_MIN_DATE)]
            df['date'] = df['date'].dt.strftime('%Y-%m-%d')
            df = df.sort_values('date').drop_duplicates(subset=['date'])

        numeric_cols = ['open', 'close', 'high', 'low', 'volume', 'amount', 'amplitude', 'pct_chg', 'chg_amt', 'turnover']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df.reset_index(drop=True)

    def _persist_hist_to_local(self, symbol: str, df, *, adjust: str, source: str, interval: str = "1d"):
        if os.getenv("PYTEST_CURRENT_TEST"):
            return
        if df is None or getattr(df, "empty", True):
            return
        try:
            from backend.infrastructure.market_data.provider import DailyBar
            from backend.repositories import market_data_repo

            bars = []
            for _, row in df.iterrows():
                trade_date = row.get("date")
                if not trade_date:
                    continue
                if hasattr(trade_date, "strftime"):
                    parsed_date = trade_date.date() if hasattr(trade_date, "date") else trade_date
                else:
                    parsed_date = datetime.strptime(str(trade_date)[:10], "%Y-%m-%d").date()
                bars.append(
                    DailyBar(
                        symbol=symbol,
                        trade_date=parsed_date,
                        open=self._decimal_or_none(row.get("open")),
                        high=self._decimal_or_none(row.get("high")),
                        low=self._decimal_or_none(row.get("low")),
                        close=self._decimal_or_none(row.get("close")),
                        volume=self._int_or_none(row.get("volume")),
                        amount=self._decimal_or_none(row.get("amount")),
                        turnover_rate=self._decimal_or_none(row.get("turnover")),
                        source=source,
                        interval=interval or "1d",
                    )
                )
            market_data_repo.upsert_daily_bars(bars, adjust=adjust)
        except Exception as exc:
            print(f"Failed to persist local market data cache for {symbol}: {exc}")

    def _decimal_or_none(self, value):
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def _int_or_none(self, value):
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def add_data_source(self, name: str, data_source: StockDataSource):
        self.data_sources[name] = data_source

    def set_default_source(self, source: str):
        if source in self.data_sources:
            self.default_source = source
        else:
            print(f"Data source {source} not found, using default")

    def clear_cache(self):
        try:
            for file in os.listdir(self.cache_dir):
                if file.endswith('.pkl'):
                    os.remove(os.path.join(self.cache_dir, file))
            print("Cache cleared successfully")
        except Exception as e:
            print(f"Failed to clear cache: {e}")


stock_data_service = StockDataService()


def get_stock_data_service() -> StockDataService:
    return stock_data_service
