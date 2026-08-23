# Finance-MCP

A Python [MCP](https://modelcontextprotocol.io) server that gives an LLM client (Claude Desktop, Claude Code) live stock market data via [`yfinance`](https://github.com/ranaroussi/yfinance) — real prices and fundamentals instead of the model's stale training-data knowledge.

**v1 scope:** market data lookups only. Portfolio-level risk analytics (volatility, Sharpe ratio, VaR, benchmark comparison) are a planned v2, not implemented yet.

## Tools

| Tool | Description |
| --- | --- |
| `get_quote(tickers)` | Current price, day change, volume, market cap, 52-week range for one or more tickers |
| `get_historical_prices(ticker, period, interval)` | OHLCV history for a ticker (auto-downsampled if the range is large) |
| `get_company_info(ticker)` | Sector, industry, business summary, P/E, dividend yield, beta |
| `search_ticker(query)` | Resolve a company name to its ticker symbol(s) |

## Prompts

| Prompt | Description |
| --- | --- |
| `analyze_stock(ticker)` | Orchestrates the tools above into a synthesized read on a stock |

## Requirements

- Python ≥3.10
- [`uv`](https://docs.astral.sh/uv/) — install with `pip install uv` if you don't have it
- Node.js/`npx` on PATH — only needed for the MCP Inspector (`mcp dev`), not for running the server itself

## Install

```bash
uv sync
```

This creates `.venv/` and installs runtime + dev dependencies (`mcp[cli]`, `yfinance`, `pandas`, `pytest`, `ruff`).

## Local testing with MCP Inspector

The fastest way to exercise every tool/prompt without wiring up Claude at all:

```bash
uv run mcp dev src/finance_mcp/server.py
```

This launches the MCP Inspector — a browser UI where you pick a tool, fill in its arguments, and see both the exact request sent and the raw response returned. Good first stop after any change: try `get_quote` with `["AAPL"]` and with an invalid ticker to confirm both the happy path and the error path look right.

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

Restart Claude Desktop afterward. The four tools and `analyze_stock` prompt should appear under the 🔌 icon in a new chat.

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
├── market_data.py  # yfinance calls + data shaping (MCP-agnostic, unit tested)
└── formatting.py   # dict/DataFrame -> compact markdown
tests/
└── test_market_data.py
```

See [CLAUDE.md](CLAUDE.md) for the design constraints (stateless, context-size discipline, yfinance error handling) behind this structure.

## Roadmap (v2)

- Single-asset risk metrics: volatility, max drawdown, Sharpe/Sortino, VaR
- Portfolio-level aggregation: given a set of holdings, compute combined return, volatility, correlation matrix
- Benchmark comparison: alpha, beta, tracking error vs. an index
