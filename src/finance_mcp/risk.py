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
import yfinance as yf

from finance_mcp.market_data import MarketDataError

TRADING_DAYS_PER_YEAR = 252
MIN_RETURN_OBSERVATIONS = 20
DEFAULT_RISK_FREE_RATE = 0.04
RISK_FREE_RATE_TICKER = "^IRX"


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


def portfolio_metrics(
    weights: dict[str, float],
    returns_by_ticker: dict[str, pd.Series],
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> dict:
    """Weighted portfolio return and volatility.

    `weights` values are auto-normalized to sum to 1, so both percentages
    (0.6/0.4) and raw dollar amounts (6000/4000) produce the same result.
    Volatility uses the full covariance matrix (w . Sigma . w), not a naive
    weighted average of individual volatilities -- those differ whenever the
    holdings aren't perfectly correlated.
    """
    total_weight = sum(weights.values())
    normalized_weights = {ticker: w / total_weight for ticker, w in weights.items()}

    returns_df = pd.DataFrame(returns_by_ticker).dropna()
    weight_vector = pd.Series(normalized_weights).reindex(returns_df.columns)

    portfolio_returns = returns_df.dot(weight_vector)
    annualized_return = float(portfolio_returns.mean() * trading_days)

    annualized_covariance = returns_df.cov(ddof=1) * trading_days
    portfolio_variance = float(weight_vector @ annualized_covariance @ weight_vector)
    annualized_volatility = math.sqrt(portfolio_variance)

    return {
        "weights": normalized_weights,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
    }


def _fetch_price_series(ticker: str, period: str) -> pd.Series:
    """Raw, full-resolution close-price series, indexed by calendar date.

    Deliberately separate from `market_data.fetch_history`, which rounds
    values and downsamples long ranges for display -- feeding that
    display-shaped data into these statistics would silently corrupt them.

    yfinance timestamps each daily bar at midnight in *that ticker's own
    exchange timezone* (e.g. America/New_York for AAPL, Europe/Rome for an
    Italian listing) -- two tickers on different exchanges never share an
    index value even for the same trading day, which silently produces NaN
    when pandas aligns them for correlation/beta/portfolio math. Stripping
    the timezone and normalizing to a bare date fixes that.
    """
    symbol = ticker.strip().upper()
    if not symbol:
        raise MarketDataError("ticker must not be empty")

    df = yf.Ticker(symbol).history(period=period)
    if df.empty:
        raise MarketDataError(f"no historical data found for '{symbol}' (period={period})")

    prices = df["Close"]
    index = prices.index
    if index.tz is not None:
        index = index.tz_localize(None)
    prices = prices.set_axis(index.normalize())

    observations = len(prices) - 1
    if observations < MIN_RETURN_OBSERVATIONS:
        raise MarketDataError(
            f"'{symbol}' only has {observations} daily return observations over "
            f"period={period} -- need at least {MIN_RETURN_OBSERVATIONS} for these "
            "statistics to be meaningful; use a longer period"
        )
    return prices


def _resolve_risk_free_rate(risk_free_rate: float | None) -> tuple[float, str]:
    """Resolve the annual risk-free rate: explicit override > live fetch > fallback.

    A fallback is always labeled in the returned source string so it's never
    silently mistaken for a live rate.
    """
    if risk_free_rate is not None:
        return risk_free_rate, "explicit override"

    try:
        rate_pct = yf.Ticker(RISK_FREE_RATE_TICKER).fast_info.last_price
    except Exception:  # noqa: BLE001 -- same inconsistent yfinance failure boundary as market_data.py
        rate_pct = None

    if rate_pct is not None:
        return rate_pct / 100, f"live, {RISK_FREE_RATE_TICKER}"
    return DEFAULT_RISK_FREE_RATE, "fallback -- live fetch failed"


def fetch_risk_metrics(
    ticker: str,
    period: str = "1y",
    benchmark: str | None = None,
    risk_free_rate: float | None = None,
    confidence: float = 0.95,
) -> dict:
    """Fetch a ticker's price history and compute its full risk profile."""
    prices = _fetch_price_series(ticker, period)
    returns = daily_returns(prices)
    resolved_rate, rate_source = _resolve_risk_free_rate(risk_free_rate)

    result = {
        "ticker": ticker.strip().upper(),
        "period": period,
        "volatility": volatility(returns),
        "max_drawdown": max_drawdown(prices),
        "sharpe_ratio": sharpe_ratio(returns, resolved_rate),
        "risk_free_rate": resolved_rate,
        "risk_free_rate_source": rate_source,
        "var": historical_var(returns, confidence),
        "confidence": confidence,
        "benchmark": benchmark,
        "beta": None,
    }

    if benchmark:
        benchmark_returns = daily_returns(_fetch_price_series(benchmark, period))
        result["beta"] = beta(returns, benchmark_returns)

    return result


def fetch_correlation(tickers: list[str], period: str = "1y") -> pd.DataFrame:
    """Fetch price history for each ticker and compute their return correlation matrix.

    Any ticker with no data aborts the whole request (naming that ticker) --
    silently dropping a constituent would change what the resulting matrix
    actually represents.
    """
    returns_by_ticker = {}
    for raw in tickers:
        symbol = raw.strip().upper()
        returns_by_ticker[symbol] = daily_returns(_fetch_price_series(symbol, period))
    return correlation_matrix(returns_by_ticker)


def fetch_portfolio_metrics(holdings: dict[str, float], period: str = "1y") -> dict:
    """Fetch price history for each holding and compute weighted portfolio return/volatility.

    Same fail-whole-request rule as `fetch_correlation`, for the same reason:
    a silently-dropped holding would change the portfolio being measured.
    """
    returns_by_ticker = {}
    for raw_ticker in holdings:
        symbol = raw_ticker.strip().upper()
        returns_by_ticker[symbol] = daily_returns(_fetch_price_series(symbol, period))

    normalized_holdings = {ticker.strip().upper(): weight for ticker, weight in holdings.items()}
    return portfolio_metrics(normalized_holdings, returns_by_ticker)
