# Finance-MCP

A Python [MCP](https://modelcontextprotocol.io) server that gives an LLM client (Claude Desktop, Claude Code) live stock market data via [`yfinance`](https://github.com/ranaroussi/yfinance) — real prices and fundamentals instead of the model's stale training-data knowledge.

Market data tools fetch and format what yfinance returns. Risk/portfolio tools go a step further: yfinance only gives raw prices, so volatility, drawdown, Sharpe, VaR, correlation, and portfolio stats are all computed in this codebase — every methodology assumption behind those numbers is stated inline in the tool's response (and summarized below), not left implicit.

## Tools

| Tool | Description |
| --- | --- |
| `get_quote(tickers)` | Current price, day change, volume, market cap, 52-week range for one or more tickers |
| `get_historical_prices(ticker, period, interval)` | OHLCV history for a ticker (auto-downsampled if the range is large) |
| `get_company_info(ticker)` | Sector, industry, business summary, P/E, dividend yield, beta |
| `search_ticker(query)` | Resolve a company name to its ticker symbol(s) |
| `get_dividends(ticker, period)` | Dividend payment history plus trailing-12-month total |
| `get_financials(ticker, statement, period)` | Full income statement / balance sheet / cash flow, annual or quarterly |
| `get_risk_metrics(ticker, period, benchmark=None, risk_free_rate=None, confidence=0.95)` | Volatility, max drawdown, Sharpe ratio, historical VaR; beta vs. `benchmark` if given |
| `get_correlation(tickers, period)` | Pairwise correlation matrix of daily returns across tickers |
| `get_portfolio_metrics(holdings, period)` | Weighted annualized return/volatility for a set of holdings (`{ticker: weight}`, auto-normalized) |

### Notable design decisions

- **Returns**: simple (arithmetic) daily returns throughout, not log returns.
- **Annualization**: 252 trading days/year; volatility and Sharpe use sample std (`ddof=1`).
- **VaR**: historical simulation (empirical percentile of past returns), not parametric — no normal-distribution assumption.
- **Risk-free rate**: live-fetched from `^IRX` (13-week T-bill) when not explicitly passed; falls back to a documented constant if the live fetch fails. The tool response always states which source was used.
- **Minimum sample size**: `get_risk_metrics` requires at least 20 daily return observations in the chosen period; shorter periods raise a clear error instead of returning a statistically meaningless number.
- **Bad ticker in `get_correlation` / `get_portfolio_metrics`**: fails the whole request, naming the ticker, rather than silently dropping it and changing what's being measured.
- **Currency mismatch**: `get_correlation` and `get_portfolio_metrics` detect when tickers are denominated in different currencies (e.g. AAPL/USD vs. a Milan-listed REY.MI/EUR) and add an explicit note — these are local-currency returns and don't include FX exposure between currencies. No conversion is performed; this is a deliberate warn-don't-convert choice, not a TODO.
- **Financial statements are full pass-through**, not a curated "key metrics" subset — a bank's balance sheet diverges structurally from an industrial's past the first few rows, so a fixed line-item list would silently misrepresent whole sectors.

## Prompts

| Prompt | Description |
| --- | --- |
| `analyze_stock(ticker)` | Orchestrates the tools above into a synthesized read on a stock |

## Requirements

- Python ≥3.10
- [`uv`](https://docs.astral.sh/uv/) — install with `pip install uv` if you don't have it
- Node.js ≥22.19.0/`npx` on PATH — only needed for the MCP Inspector (`mcp dev`), not for running the server itself

## Install

```bash
uv sync
```

This creates `.venv/` and installs runtime + dev dependencies (`mcp[cli]`, `yfinance`, `pandas`, `pytest`, `ruff`).

## Local testing with MCP Inspector

The fastest way to exercise every tool/prompt without wiring up Claude at all. Requires **Node.js ≥22.19.0** on PATH (`node --version` to check) — the Inspector itself is a Node package pulled on demand via `npx`, nothing to install ahead of time.

```bash
uv run mcp dev src/finance_mcp/server.py
```

This prints a URL like `http://127.0.0.1:6274?MCP_INSPECTOR_API_TOKEN=...` and opens it in your browser — a UI where you pick a tool, fill in its arguments, and see both the exact JSON-RPC request sent and the raw response returned in the Messages panel. Good first stop after any change: try `get_quote` with `["AAPL"]` and with an invalid ticker to confirm both the happy path and the error path look right. Stop it with Ctrl+C in the terminal it's running in when you're done.

<details>
<summary>Troubleshooting: "Cannot find native binding" or "styleText" errors</summary>

Both are caused by a stale `npx` cache left over from a Node.js version upgrade (npm's optional-dependency resolution installs platform/version-specific native binaries the first time it runs a package, and they don't get refreshed automatically). Fix:

```bash
npm cache clean --force
```

If that alone doesn't fix it, find and delete the specific cached install under `%LOCALAPPDATA%\npm-cache\_npx\<hash>\` (the one whose `package.json` mentions `@modelcontextprotocol/inspector`), then rerun `uv run mcp dev ...` to force a clean reinstall.
</details>

## Running tests

```bash
uv run pytest          # full suite
uv run ruff check .    # lint
```

`yfinance` calls are mocked in the test suite, so it runs offline. There's no automated live-network test — use the Inspector (above) or the snippet below for a real-data smoke check:

```bash
uv run python -c "from finance_mcp import server; print(server.get_quote(['AAPL']))"
```

## Connect to Claude Desktop

**Option A — automatic:**

```bash
uv run mcp install src/finance_mcp/server.py --name finance-mcp
```

**Option B — manual:** add this to your `claude_desktop_config.json` (on Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "finance-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "D:\\Programming Projects\\Finance-MCP",
        "run",
        "finance-mcp"
      ]
    }
  }
}
```

Restart Claude Desktop afterward. The tools and `analyze_stock` prompt should appear under the 🔌 icon in a new chat.

## Connect to Claude Code

**Option A — CLI:**

```bash
claude mcp add finance-mcp -- uv --directory "D:\Programming Projects\Finance-MCP" run finance-mcp
```

**Option B — project-scoped `.mcp.json`** (checked into the repo, shared with anyone who opens this project):

```json
{
  "mcpServers": {
    "finance-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "D:\\Programming Projects\\Finance-MCP",
        "run",
        "finance-mcp"
      ]
    }
  }
}
```

Verify with `/mcp` inside Claude Code — `finance-mcp` should show as connected.

## Project layout

```
src/finance_mcp/
├── server.py       # MCPServer instance, tool/prompt registration only
├── market_data.py  # yfinance calls + data shaping for market-data tools (MCP-agnostic, unit tested)
├── risk.py         # risk/portfolio math (pure functions) + its own yfinance fetch layer
└── formatting.py   # dict/DataFrame -> compact markdown
tests/
├── test_market_data.py
├── test_risk.py
└── test_formatting.py
```

See [CLAUDE.md](CLAUDE.md) for the design constraints (stateless, context-size discipline, yfinance error handling, why `risk.py` doesn't reuse `market_data.fetch_history`) behind this structure.
