from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any


class DateUtils:
    @staticmethod
    def today() -> str:
        return datetime.now().strftime('%Y-%m-%d')
    
    @staticmethod
    def now() -> str:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    @staticmethod
    def days_ago(days: int) -> str:
        return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    @staticmethod
    def weeks_ago(weeks: int) -> str:
        return (datetime.now() - timedelta(weeks=weeks)).strftime('%Y-%m-%d')
    
    @staticmethod
    def months_ago(months: int) -> str:
        today = datetime.now()
        month = today.month - months
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        return datetime(year, month, today.day).strftime('%Y-%m-%d')
    
    @staticmethod
    def parse_date(date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None
    
    @staticmethod
    def format_date(dt: datetime, fmt: str = '%Y-%m-%d') -> str:
        return dt.strftime(fmt)


class NumberUtils:
    @staticmethod
    def safe_float(value: Any, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def safe_int(value: Any, default: int = 0) -> int:
        if value is None:
            return default
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def format_percent(value: float, decimals: int = 2) -> str:
        return f'{value:.{decimals}f}%'
    
    @staticmethod
    def format_currency(value: float, decimals: int = 2) -> str:
        return f'¥{value:,.{decimals}f}'
    
    @staticmethod
    def format_number(value: float, decimals: int = 2) -> str:
        return f'{value:,.{decimals}f}'


class StringUtils:
    @staticmethod
    def truncate(text: str, max_length: int = 50, suffix: str = '...') -> str:
        if not text:
            return ''
        if len(text) <= max_length:
            return text
        return text[:max_length - len(suffix)] + suffix
    
    @staticmethod
    def safe_str(value: Any, default: str = '') -> str:
        if value is None:
            return default
        return str(value).strip()
    
    @staticmethod
    def is_empty(value: Any) -> bool:
        if value is None:
            return True
        return str(value).strip() == ''


class ListUtils:
    @staticmethod
    def chunk(lst: List[Any], size: int) -> List[List[Any]]:
        return [lst[i:i + size] for i in range(0, len(lst), size)]
    
    @staticmethod
    def flatten(lst: List[List[Any]]) -> List[Any]:
        return [item for sublist in lst for item in sublist]
    
    @staticmethod
    def unique(lst: List[Any]) -> List[Any]:
        seen = set()
        return [x for x in lst if not (x in seen or seen.add(x))]
    
    @staticmethod
    def group_by(lst: List[Dict], key: str) -> Dict[Any, List[Dict]]:
        result = {}
        for item in lst:
            k = item.get(key)
            if k not in result:
                result[k] = []
            result[k].append(item)
        return result


class DictUtils:
    @staticmethod
    def get_nested(d: Dict, *keys, default=None):
        for key in keys:
            if not isinstance(d, dict):
                return default
            d = d.get(key, default)
        return d
    
    @staticmethod
    def safe_get(d: Dict, key: str, default: Any = None) -> Any:
        if d is None:
            return default
        return d.get(key, default)
    
    @staticmethod
    def omit(d: Dict, *keys) -> Dict:
        return {k: v for k, v in d.items() if k not in keys}
    
    @staticmethod
    def pick(d: Dict, *keys) -> Dict:
        return {k: d[k] for k in keys if k in d}
