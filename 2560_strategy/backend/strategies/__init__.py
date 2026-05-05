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
        self._aliases = {
            "first_limit_up": "FIRST_LIMIT_UP",
            "first_board": "FIRST_LIMIT_UP",
            "limit_up_return": "LIMIT_UP_RETURN",
            "limitup_return": "LIMIT_UP_RETURN",
            "convertible_bond": "CONVERTIBLE_BOND_LOW_PREMIUM",
            "convertible_bond_low_premium": "CONVERTIBLE_BOND_LOW_PREMIUM",
            "cb_low_premium": "CONVERTIBLE_BOND_LOW_PREMIUM",
        }
    
    def register(self, strategy: BaseStrategy):
        """Register a strategy."""
        self._strategies[strategy.code] = strategy
    
    def get(self, code: str) -> BaseStrategy:
        """Get strategy by code."""
        text = str(code or "").strip()
        return (
            self._strategies.get(text)
            or self._strategies.get(self._aliases.get(text, ""))
            or self._strategies.get(text.upper())
        )
    
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


# Import builtin strategies that should be registered at package import time.
from backend.strategies.strategy_2560 import Strategy2560  # noqa: E402,F401
from backend.strategies.strategy_limit_up_return import StrategyLimitUpReturn  # noqa: E402,F401
from backend.strategies.strategy_first_limit_up import StrategyFirstLimitUp  # noqa: E402,F401
from backend.strategies.strategy_convertible_bond import ConvertibleBondLowPremiumStrategy  # noqa: E402,F401
