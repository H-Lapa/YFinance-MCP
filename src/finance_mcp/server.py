"""FastMCP registration layer. Business logic lives in market_data.py."""

from __future__ import annotations

from mcp.server import MCPServer

from finance_mcp import market_data
from finance_mcp.formatting import rows_to_markdown_table

mcp = MCPServer("finance-mcp")


@mcp.tool()
def get_quote(tickers: list[str]) -> str:
    """Get current price, day change, volume, market cap, and 52-week range
    for one or more stock tickers (e.g. ["AAPL", "MSFT"])."""
    quotes = market_data.fetch_quotes(tickers)
    return rows_to_markdown_table(quotes, columns=market_data.QUOTE_FIELDS)


@mcp.tool()
def get_historical_prices(ticker: str, period: str = "1mo", interval: str = "1d") -> str:
    """Get historical OHLCV price data for a single ticker.

    period: one of 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
    interval: one of 1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo
    (intraday intervals are only available for short periods)
    """
    result = market_data.fetch_history(ticker, period=period, interval=interval)
    table = rows_to_markdown_table(
        result["rows"], columns=["date", "open", "high", "low", "close", "volume"]
    )
    header = f"{result['ticker']} historical prices (period={result['period']}, interval={result['interval']})"
    if result["note"]:
        header += f"\n{result['note']}"
    return f"{header}\n\n{table}"


@mcp.tool()
def get_company_info(ticker: str) -> str:
    """Get sector, industry, business summary, and key stats (P/E, market cap,
    dividend yield, beta) for a single ticker."""
    info = market_data.fetch_company_info(ticker)
    lines = [
        f"# {info['name']} ({info['ticker']})",
        f"Sector: {info['sector'] or 'N/A'} | Industry: {info['industry'] or 'N/A'}",
        (
            f"Market Cap: {info['market_cap'] or 'N/A'} | P/E: {info['pe_ratio'] or 'N/A'} | "
            f"Dividend Yield: {info['dividend_yield'] or 'N/A'} | Beta: {info['beta'] or 'N/A'}"
        ),
        "",
        info["summary"] or "(no business summary available)",
    ]
    return "\n".join(lines)


@mcp.tool()
def search_ticker(query: str) -> str:
    """Search for a ticker symbol by company name, e.g. 'Apple' -> AAPL."""
    matches = market_data.search_tickers(query)
    return rows_to_markdown_table(matches, columns=["ticker", "name", "exchange", "type"])


@mcp.prompt()
def analyze_stock(ticker: str) -> str:
    """Generate a synthesized analysis of a stock using the quote, history, and company info tools."""
    symbol = ticker.strip().upper()
    return (
        f"Analyze {symbol} as an investment. Call get_quote, get_historical_prices "
        f"(use a period like '3mo' or '1y'), and get_company_info for {symbol}, then summarize: "
        "(1) where the current price sits relative to its 52-week range, "
        "(2) the recent price trend from the historical data, and "
        "(3) relevant business/sector context from the company info. "
        "Keep the summary concise and clearly note this is not financial advice."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
