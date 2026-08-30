"""yfinance-backed market data lookups.

Kept free of any MCP/protocol objects so it can be unit tested (with yfinance
mocked) without spinning up the MCP layer. `server.py` is the only module that
knows about FastMCP.
"""

from __future__ import annotations

import math

import pandas as pd
import yfinance as yf

MAX_HISTORY_ROWS = 60

QUOTE_FIELDS = [
    "ticker",
    "price",
    "change",
    "change_pct",
    "volume",
    "market_cap",
    "year_high",
    "year_low",
    "error",
]


class MarketDataError(Exception):
    """Raised when yfinance has no usable data for a single-ticker request."""


def fetch_quotes(tickers: list[str]) -> list[dict]:
    """Fetch current quote data for each ticker.

    Unlike the single-ticker lookups, this never raises for an individual bad
    ticker -- it embeds an "error" field in that ticker's row instead, so one
    bad symbol in a batch doesn't blow up the whole request.
    """
    results = []
    for raw in tickers:
        symbol = raw.strip().upper()
        row = dict.fromkeys(QUOTE_FIELDS)
        row["ticker"] = symbol
        row["error"] = ""

        if not symbol:
            row["error"] = "empty ticker"
            results.append(row)
            continue

        try:
            fast_info = yf.Ticker(symbol).fast_info
            last_price = fast_info.last_price
        except Exception:  # noqa: BLE001 -- yfinance raises inconsistent exception types/shapes
            # yfinance's failure modes for a bad/delisted ticker range from empty data to raw
            # KeyErrors from its own response parsing, so we normalize all of them to one message
            # rather than leaking an internal attribute name to the caller.
            row["error"] = "no data found for ticker"
            results.append(row)
            continue

        if last_price is None:
            row["error"] = "no data found for ticker"
            results.append(row)
            continue

        previous_close = getattr(fast_info, "previous_close", None)
        change = None
        change_pct = None
        if previous_close:
            change = last_price - previous_close
            change_pct = (change / previous_close) * 100

        row.update(
            price=round(last_price, 2),
            change=round(change, 2) if change is not None else None,
            change_pct=round(change_pct, 2) if change_pct is not None else None,
            volume=getattr(fast_info, "last_volume", None),
            market_cap=getattr(fast_info, "market_cap", None),
            year_high=getattr(fast_info, "year_high", None),
            year_low=getattr(fast_info, "year_low", None),
        )
        results.append(row)

    return results


def _downsample(
    data: pd.DataFrame | pd.Series, max_rows: int
) -> tuple[pd.DataFrame | pd.Series, str | None]:
    """Stride-sample down to at most `max_rows` rows if `data` exceeds it.

    Works on either a DataFrame or a Series (both support `.iloc[::stride]`
    and `len()`), so it's shared between any tool whose response would
    otherwise dump an unbounded time series into the model's context window.
    Returns (possibly-unchanged data, note-or-None) rather than mutating in
    place, so a caller that doesn't downsample can't forget to check.
    """
    total_rows = len(data)
    if total_rows <= max_rows:
        return data, None

    stride = math.ceil(total_rows / max_rows)
    sampled = data.iloc[::stride]
    note = (
        f"Showing every {stride}-th row ({len(sampled)} of {total_rows} total) to keep the "
        "response compact. Request a shorter period for full resolution."
    )
    return sampled, note


def fetch_history(ticker: str, period: str = "1mo", interval: str = "1d") -> dict:
    """Fetch OHLCV history for a single ticker, downsampled to stay response-size safe."""
    symbol = ticker.strip().upper()
    if not symbol:
        raise MarketDataError("ticker must not be empty")

    df = yf.Ticker(symbol).history(period=period, interval=interval)
    if df.empty:
        raise MarketDataError(
            f"no historical data found for '{symbol}' (period={period}, interval={interval}) "
            "-- check the ticker symbol and that the period/interval combination is valid"
        )

    df, note = _downsample(df, MAX_HISTORY_ROWS)

    return {
        "ticker": symbol,
        "period": period,
        "interval": interval,
        "note": note,
        "rows": _history_to_rows(df),
    }


def _history_to_rows(df: pd.DataFrame) -> list[dict]:
    rows = []
    for idx, row in df.iterrows():
        date = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        volume = row.get("Volume")
        rows.append(
            {
                "date": date,
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(volume) if pd.notna(volume) else None,
            }
        )
    return rows


def fetch_company_info(ticker: str) -> dict:
    """Fetch sector/industry/summary/key-stats for a single ticker."""
    symbol = ticker.strip().upper()
    if not symbol:
        raise MarketDataError("ticker must not be empty")

    info = yf.Ticker(symbol).info
    name = info.get("longName") or info.get("shortName")
    if not name:
        raise MarketDataError(f"no company info found for '{symbol}' -- check the ticker symbol")

    summary = info.get("longBusinessSummary") or ""
    if len(summary) > 800:
        summary = summary[:800].rsplit(" ", 1)[0] + "..."

    return {
        "ticker": symbol,
        "name": name,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "summary": summary,
    }


def search_tickers(query: str, max_results: int = 5) -> list[dict]:
    """Resolve a company name (or partial symbol) to matching ticker symbols."""
    cleaned = query.strip()
    if not cleaned:
        raise MarketDataError("query must not be empty")

    search = yf.Search(cleaned, max_results=max_results)
    quotes = search.quotes or []
    if not quotes:
        raise MarketDataError(f"no tickers found matching '{query}'")

    return [
        {
            "ticker": q.get("symbol"),
            "name": q.get("shortname") or q.get("longname"),
            "exchange": q.get("exchange"),
            "type": q.get("quoteType"),
        }
        for q in quotes
    ]


_DIVIDEND_PERIOD_DAYS = {
    "1y": 365,
    "2y": 730,
    "5y": 1825,
    "10y": 3650,
    "max": None,
}


def fetch_dividends(ticker: str, period: str = "5y") -> dict:
    """Fetch dividend payment history for a single ticker.

    yfinance's `.dividends` always returns the *full* history (no period
    argument), so filtering happens here. Same timezone-stripping as
    `risk._fetch_price_series` and for the same reason: yfinance timestamps
    these per the ticker's own exchange timezone.
    """
    symbol = ticker.strip().upper()
    if not symbol:
        raise MarketDataError("ticker must not be empty")
    if period not in _DIVIDEND_PERIOD_DAYS:
        raise MarketDataError(f"invalid period '{period}' -- must be one of {sorted(_DIVIDEND_PERIOD_DAYS)}")

    dividends = yf.Ticker(symbol).dividends
    if dividends.empty:
        raise MarketDataError(f"no dividend history found for '{symbol}' -- it may not pay dividends")

    index = dividends.index
    if index.tz is not None:
        index = index.tz_localize(None)
    dividends = dividends.set_axis(index.normalize())

    now = pd.Timestamp.now().normalize()
    trailing_12mo_total = float(dividends[dividends.index >= now - pd.Timedelta(days=365)].sum())

    days = _DIVIDEND_PERIOD_DAYS[period]
    if days is not None:
        dividends = dividends[dividends.index >= now - pd.Timedelta(days=days)]
        if dividends.empty:
            raise MarketDataError(
                f"no dividend payments for '{symbol}' in the last {period} -- try a longer period"
            )

    dividends, note = _downsample(dividends, MAX_HISTORY_ROWS)

    return {
        "ticker": symbol,
        "period": period,
        "note": note,
        "trailing_12mo_total": trailing_12mo_total,
        "rows": [
            {"date": date.strftime("%Y-%m-%d"), "amount": round(float(amount), 4)}
            for date, amount in dividends.items()
        ],
    }


_FINANCIAL_STATEMENT_ATTRS = {
    ("income", "annual"): "financials",
    ("income", "quarterly"): "quarterly_financials",
    ("balance_sheet", "annual"): "balance_sheet",
    ("balance_sheet", "quarterly"): "quarterly_balance_sheet",
    ("cashflow", "annual"): "cashflow",
    ("cashflow", "quarterly"): "quarterly_cashflow",
}


def fetch_financials(ticker: str, statement: str = "income", period: str = "annual") -> pd.DataFrame:
    """Fetch a financial statement for a single ticker.

    Returns the full statement exactly as yfinance provides it (every line
    item, every available period) rather than a curated "key metrics"
    subset. A fixed list of line items to extract would silently go missing
    or misleading for whole sectors -- a bank's balance sheet diverges
    structurally from an industrial's past the first few rows (loans vs.
    inventory, etc.), confirmed by comparing JPM against AAPL live.
    """
    symbol = ticker.strip().upper()
    if not symbol:
        raise MarketDataError("ticker must not be empty")

    key = (statement, period)
    if key not in _FINANCIAL_STATEMENT_ATTRS:
        valid_statements = sorted({s for s, _ in _FINANCIAL_STATEMENT_ATTRS})
        valid_periods = sorted({p for _, p in _FINANCIAL_STATEMENT_ATTRS})
        raise MarketDataError(
            f"invalid statement/period combination: statement={statement!r}, period={period!r} "
            f"-- statement must be one of {valid_statements}, period must be one of {valid_periods}"
        )

    df = getattr(yf.Ticker(symbol), _FINANCIAL_STATEMENT_ATTRS[key])
    if df.empty:
        raise MarketDataError(f"no {statement} data found for '{symbol}'")
    return df
