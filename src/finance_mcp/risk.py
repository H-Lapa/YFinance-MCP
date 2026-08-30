"""Risk statistics computed from price/return series.

The pure math functions in this module take pandas Series of prices or
returns and contain no yfinance/network calls, so they can be unit tested
with small, hand-computable synthetic series -- that's what actually
validates a formula is implemented correctly, as opposed to merely not
crashing. The yfinance-calling fetch layer (added later) delegates to these.

Convention used throughout: simple (arithmetic) daily returns, sample
standard deviation (ddof=1), and 252-trading-day annualization.
"""

from __future__ import annotations

import math

import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def daily_returns(prices: pd.Series) -> pd.Series:
    """Simple (arithmetic) day-over-day returns, e.g. 0.01 for a 1% gain."""
    return prices.pct_change().dropna()


def volatility(returns: pd.Series, trading_days: int = TRADING_DAYS_PER_YEAR) -> float:
    """Annualized volatility: sample std of daily returns, scaled by sqrt(trading_days)."""
    return float(returns.std(ddof=1) * math.sqrt(trading_days))


def max_drawdown(prices: pd.Series) -> float:
    """Largest peak-to-trough decline over the series, as a negative fraction (e.g. -0.23 = -23%)."""
    return float((prices / prices.cummax() - 1).min())
