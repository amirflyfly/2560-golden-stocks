"""Formatting and parsing helpers (pure functions)."""


def num(v, default=0.0):
    try:
        return float(v or 0)
    except Exception:
        return default


def int_num(v, default=0):
    try:
        return int(float(v or 0))
    except Exception:
        return default
