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
