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


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate_annual: float,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualized Sharpe ratio: mean daily excess return over daily std, scaled by sqrt(trading_days).

    The annual risk-free rate is converted to a daily rate by simple division
    (risk_free_rate_annual / trading_days), not geometric compounding.
    """
    daily_risk_free = risk_free_rate_annual / trading_days
    excess_returns = returns - daily_risk_free
    return float(excess_returns.mean() / returns.std(ddof=1) * math.sqrt(trading_days))


def historical_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical (empirical) Value at Risk: the confidence-level percentile of past
    daily returns. Negative = a loss. No distribution is assumed -- this reflects
    only what actually happened in the sample, unlike a parametric/normal-distribution VaR.
    """
    return float(returns.quantile(1 - confidence))


def beta(asset_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Beta of an asset vs. a benchmark: cov(asset, benchmark) / var(benchmark).

    The two series are aligned on their shared index first (inner join) so
    dates present in only one series don't silently skew the result.
    """
    aligned = pd.concat([asset_returns, benchmark_returns], axis=1, join="inner")
    aligned.columns = ["asset", "benchmark"]
    covariance = aligned["asset"].cov(aligned["benchmark"])
    benchmark_variance = aligned["benchmark"].var(ddof=1)
    return float(covariance / benchmark_variance)


def correlation_matrix(returns_by_ticker: dict[str, pd.Series]) -> pd.DataFrame:
    """Pairwise correlation matrix of daily returns across tickers."""
    return pd.DataFrame(returns_by_ticker).corr()
