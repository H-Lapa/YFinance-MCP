# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Finance-MCP is a Python MCP (Model Context Protocol) server that gives an LLM client (Claude Desktop, Claude Code) live market data and risk/portfolio analytics backed by `yfinance` — instead of relying on the model's stale training-data knowledge of prices and financials, and instead of the model hand-deriving risk statistics itself. Market-data tools (`get_quote`, `get_historical_prices`, `get_company_info`, `search_ticker`) fetch and format what yfinance returns; risk/portfolio tools (`get_risk_metrics`, `get_correlation`, `get_portfolio_metrics`) go further and *compute* volatility, drawdown, Sharpe, VaR, correlation, and portfolio stats from raw price history — none of that is an API field, so correctness here matters more than it does for a formatting bug, and every methodology assumption is stated inline in the tool's response (see `risk.py` below).

## Commands

- Install deps: `uv sync`
- Run the test suite: `uv run pytest`
- Run a single test: `uv run pytest tests/test_market_data.py::test_name` (or `tests/test_risk.py::test_name`)
- Lint: `uv run ruff check .`
- Interactive manual testing (MCP Inspector, no Claude client needed): `uv run mcp dev src/finance_mcp/server.py`
- Run the server directly (stdio transport): `uv run finance-mcp`

## Architecture

Built on the official Python MCP SDK's high-level `MCPServer` API (`mcp>=2.0`; this class replaced the older `FastMCP` name — same decorator-based API, moved to `mcp.server.MCPServer`), served over stdio transport (the standard local transport for Claude Desktop/Claude Code).

The source is deliberately split by concern, not by convenience:

- `src/finance_mcp/server.py` — `MCPServer` instance and `@mcp.tool()` / `@mcp.prompt()` registrations only. No business logic lives here.
- `src/finance_mcp/market_data.py` — all `yfinance` calls and data-shaping logic for the market-data tools. Kept MCP-agnostic (no protocol/session objects) specifically so it can be unit tested with `yfinance` mocked, without spinning up the MCP layer.
- `src/finance_mcp/risk.py` — risk/portfolio statistics. Split into two layers: pure math functions (`volatility`, `max_drawdown`, `sharpe_ratio`, `historical_var`, `beta`, `correlation_matrix`, `portfolio_metrics`) that take plain pandas Series/dicts and do no I/O, plus a fetch layer (`fetch_risk_metrics`, `fetch_correlation`, `fetch_portfolio_metrics`) that calls yfinance and delegates to the pure functions. The pure functions are tested with small hand-computable synthetic series (that's what actually validates a formula, not just "doesn't crash") independent of any yfinance mocking.
- `src/finance_mcp/formatting.py` — converts pandas output into compact markdown for tool responses.

**`risk.py` deliberately does not reuse `market_data.fetch_history` for its raw prices.** That function rounds values to 2 decimals and downsamples long ranges to ~60 rows for *display* — feeding rounded/downsampled data into a volatility or Sharpe calculation would silently corrupt the statistic. `risk.py` has its own `_fetch_price_series` that pulls full-resolution, unrounded closes.

Risk/portfolio conventions, all stated explicitly in tool output rather than left implicit: simple (not log) daily returns; 252-trading-day annualization; sample std (`ddof=1`); historical-simulation VaR (empirical percentile, not a normal-distribution assumption); risk-free rate resolved as explicit override → live `^IRX` fetch → documented constant fallback, with the source always labeled; portfolio weights auto-normalize so dollar amounts and percentages behave identically; `get_correlation`/`get_portfolio_metrics` fail the whole request (naming the ticker) if any constituent has no data, rather than silently dropping it and changing what's being measured; `get_risk_metrics` requires at least 20 daily return observations, or it raises rather than returning a statistically meaningless number.

Two constraints drive most design decisions in this codebase and should be preserved when extending it:

1. **Stateless by design.** Every tool takes its full input (tickers, period, etc.) on each call — there is no persisted portfolio, no local DB. This was a deliberate scope decision, not an oversight; don't add persistence without revisiting that decision explicitly.
2. **Tool output feeds directly into the model's context window.** `yfinance` will happily return hundreds of rows of OHLCV history — tools must cap/resample before returning (e.g. historical price responses are capped to ~60 rows, auto-resampling to a coarser interval and noting that in the response rather than dumping the full series).

`yfinance`'s failure modes for a bad/delisted ticker are inconsistent: sometimes an empty DataFrame, sometimes a sparse `info` dict, sometimes a raw exception from its own response parsing (e.g. `fast_info` can raise `KeyError` deep inside instead of returning `None`). Every tool wraps these and normalizes to one clear, model-readable error message rather than leaking an internal exception string or letting malformed data flow through. Prefer `Ticker.fast_info` over `Ticker.info` for price-only lookups — `.info` is significantly heavier and slower.

Verified: `yfinance`'s internal warnings/errors (e.g. "No data found, symbol may be delisted") print to stderr, not stdout — important because stdio transport uses stdout exclusively for the JSON-RPC stream, and stdout contamination would corrupt the protocol.

The `analyze_stock` prompt is orchestration-only: it instructs the model to call the existing tools (`get_quote`, `get_historical_prices`, `get_company_info`) and does not contain its own data-fetching logic.

Tests mock `yfinance` (`pytest-mock`) so `pytest` runs offline and deterministically. Anything requiring a real network call against Yahoo Finance is a manual check via MCP Inspector, not part of the automated suite.
