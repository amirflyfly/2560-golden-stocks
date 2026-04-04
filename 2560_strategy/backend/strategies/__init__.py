"""Multi-strategy framework.

Base classes and registry for trading strategies.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from datetime import datetime


class BaseStrategy(ABC):
    """Base class for all trading strategies."""
    
    def __init__(self):
        self.code = self.get_code()
        self.name = self.get_name()
        self.description = self.get_description()
    
    @abstractmethod
    def get_code(self) -> str:
        """Return unique strategy code."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return strategy display name."""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Return strategy description."""
        pass
    
    @abstractmethod
    def scan(self, date: str = None) -> List[Dict[str, Any]]:
        """Scan stocks and return picks for the given date.
        
        Returns list of dicts with keys:
        - code: str
        - name: str
        - pick_price: float
        - signal: str
        - reason_tag: str (optional)
        - note: str (optional)
        """
        pass
    
    def is_trading_day(self, date: str = None) -> bool:
        """Check if the given date is a trading day."""
        from strategy_2560 import is_trading_day_today
        if date is None:
            return is_trading_day_today()
        # For specific date, use akshare
        try:
            import akshare as ak
            df = ak.tool_trade_date_hist_sina()
            # Check if date is in trading days
            return date in df['trade_date'].values
        except Exception as e:
            print(f"Failed to check trading day: {e}")
            # Default to True for testing purposes
            return True


class StrategyRegistry:
    """Registry for managing multiple strategies."""
    
    def __init__(self):
        self._strategies: Dict[str, BaseStrategy] = {}
    
    def register(self, strategy: BaseStrategy):
        """Register a strategy."""
        self._strategies[strategy.code] = strategy
    
    def get(self, code: str) -> BaseStrategy:
        """Get strategy by code."""
        return self._strategies.get(code)
    
    def list_all(self) -> List[BaseStrategy]:
        """List all registered strategies."""
        return list(self._strategies.values())
    
    def list_active(self) -> List[BaseStrategy]:
        """List active strategies from database."""
        from backend.repositories import strategy_repo
        active_codes = [s['code'] for s in strategy_repo.list_strategies(active_only=True)]
        return [s for s in self._strategies.values() if s.code in active_codes]


# Global registry instance
registry = StrategyRegistry()


def register_strategy(strategy_class):
    """Decorator to register a strategy class."""
    strategy = strategy_class()
    registry.register(strategy)
    return strategy_class
