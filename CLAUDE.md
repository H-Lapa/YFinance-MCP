# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Finance-MCP is a Python MCP (Model Context Protocol) server that gives an LLM client (Claude Desktop, Claude Code) live market-data tools backed by `yfinance` — quotes, historical prices, company fundamentals — instead of relying on the model's stale training-data knowledge of prices and financials. Current scope is market-data lookups only; risk/portfolio analytics (volatility, Sharpe, VaR, correlation, beta, portfolio aggregation) are planned as individual follow-up tools, each added as its own small, self-contained change — see the Roadmap in README.md.

## Commands

- Install deps: `uv sync`
- Run the test suite: `uv run pytest`
- Run a single test: `uv run pytest tests/test_market_data.py::test_name`
- Lint: `uv run ruff check .`
- Interactive manual testing (MCP Inspector, no Claude client needed): `uv run mcp dev src/finance_mcp/server.py`
- Run the server directly (stdio transport): `uv run finance-mcp`

## Architecture

Built on the official Python MCP SDK's high-level `MCPServer` API (`mcp>=2.0`; this class replaced the older `FastMCP` name — same decorator-based API, moved to `mcp.server.MCPServer`), served over stdio transport (the standard local transport for Claude Desktop/Claude Code).

The source is deliberately split by concern, not by convenience:

- `src/finance_mcp/server.py` — `MCPServer` instance and `@mcp.tool()` / `@mcp.prompt()` registrations only. No business logic lives here.
- `src/finance_mcp/market_data.py` — all `yfinance` calls and data-shaping logic. Kept MCP-agnostic (no protocol/session objects) specifically so it can be unit tested with `yfinance` mocked, without spinning up the MCP layer.
- `src/finance_mcp/formatting.py` — converts pandas output into compact markdown for tool responses.

Two constraints drive most design decisions in this codebase and should be preserved when extending it:

1. **Stateless by design.** Every tool takes its full input (tickers, period, etc.) on each call — there is no persisted portfolio, no local DB. This was a deliberate scope decision, not an oversight; don't add persistence without revisiting that decision explicitly.
2. **Tool output feeds directly into the model's context window.** `yfinance` will happily return hundreds of rows of OHLCV history — tools must cap/resample before returning (e.g. historical price responses are capped to ~60 rows, auto-resampling to a coarser interval and noting that in the response rather than dumping the full series).

`yfinance`'s failure modes for a bad/delisted ticker are inconsistent: sometimes an empty DataFrame, sometimes a sparse `info` dict, sometimes a raw exception from its own response parsing (e.g. `fast_info` can raise `KeyError` deep inside instead of returning `None`). Every tool wraps these and normalizes to one clear, model-readable error message rather than leaking an internal exception string or letting malformed data flow through. Prefer `Ticker.fast_info` over `Ticker.info` for price-only lookups — `.info` is significantly heavier and slower.

Verified: `yfinance`'s internal warnings/errors (e.g. "No data found, symbol may be delisted") print to stderr, not stdout — important because stdio transport uses stdout exclusively for the JSON-RPC stream, and stdout contamination would corrupt the protocol.

The `analyze_stock` prompt is orchestration-only: it instructs the model to call the existing tools (`get_quote`, `get_historical_prices`, `get_company_info`) and does not contain its own data-fetching logic.

Tests mock `yfinance` (`pytest-mock`) so `pytest` runs offline and deterministically. Anything requiring a real network call against Yahoo Finance is a manual check via MCP Inspector, not part of the automated suite.
