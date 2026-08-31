# yfinance-mcp

yfinance-mcp is a Python [MCP](https://modelcontextprotocol.io) server that gives any MCP-compatible LLM client live stock market data and risk analytics, sources from [`yfinance`](https://github.com/ranaroussi/yfinance). This provides real prices and financials instead of a model's stale training data, and computed risk statistics instead of the model hand-deriving them itself.

The server offers two kinds of tools: **market data** tools that fetch and format what yfinance returns directly (quotes, prices, company info, dividends, financial statements), and **risk and portfolio analytics** tools that go further and compute volatility, drawdown, Sharpe ratio, VaR, correlation, and portfolio statistics from raw price history, since none of that is a plain API field.

The server is also stateless: every tool call carries its full input (tickers, weights, period, and so on) rather than relying on a persisted portfolio or local database.

> **Note:** This project was previously named Finance-MCP. The installed command and the Python package still use the old name, `finance-mcp`.

**Contents:** [Quick Start](#quick-start) · [Tools](#tools) · [Prompts](#prompts) · [Design Decisions](#design-decisions) · [Development](#development)

## Quick Start

```bash
uv sync
uv run finance-mcp
```

`uv sync` installs every dependency. See [Requirements](#requirements) for prerequisites.

`uv run finance-mcp` starts the server. It uses stdio transport. Point any MCP-compatible client at this command.

To try the tools without a client, see [MCP Inspector](#mcp-inspector-manual-testing).

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

## Prompts

| Prompt | Description |
| --- | --- |
| `analyze_stock(ticker)` | Orchestrates the tools above into a synthesized read on a stock |

## Design Decisions

These are the assumptions behind the risk and portfolio numbers. Know these choices before you rely on the numbers.

- **Returns.** The server uses simple daily returns. It does not use log returns.
- **Annualization.** The server assumes 252 trading days per year. Volatility and the Sharpe ratio use sample standard deviation (`ddof=1`).
- **VaR.** The server uses historical simulation. It takes the empirical percentile of past returns. It does not assume a normal distribution.
- **Risk-free rate.** By default, the server fetches the live 13-week T-bill rate (`^IRX`). You can override this rate in the tool call. If the live fetch fails, the server uses a documented constant instead. Each tool response states which source it used.
- **Minimum sample size.** `get_risk_metrics` needs at least 20 daily return observations in the chosen period. A shorter period raises a clear error. The tool does not return a statistically meaningless number.
- **Bad ticker in `get_correlation` or `get_portfolio_metrics`.** The tool fails the whole request and names the bad ticker. It does not silently drop the ticker, because that would change what the numbers measure.
- **Currency mismatch.** `get_correlation` and `get_portfolio_metrics` detect when tickers use different currencies. For example, AAPL trades in USD and a Milan-listed REY.MI trades in EUR. When this happens, the tool adds a note to the response. The returns stay in local currency. They do not include FX exposure between currencies. The server does not convert currencies. This is a deliberate choice, not a missing feature.
- **Financial statements.** `get_financials` returns the full statement. It does not return a curated list of key metrics. A bank's balance sheet and an industrial company's balance sheet diverge past the first few rows. A fixed line-item list would misrepresent some sectors.

## Development

### Project Layout

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

### Requirements

- Python 3.10 or later.
- [`uv`](https://docs.astral.sh/uv/). If you do not have uv, install it: `pip install uv`.
- Node.js 22.19.0 or later, with `npx` on PATH. You need this only for the MCP Inspector, below. You do not need it to run the server.

### Install

```bash
uv sync
```

This command creates `.venv/`. It installs the runtime and development dependencies: `mcp[cli]`, `yfinance`, `pandas`, `pytest`, `ruff`.

### Run tests and lint

```bash
uv run pytest          # full suite
uv run ruff check .    # lint
```

The test suite mocks all `yfinance` calls. It runs offline. There is no automated live-network test. Use the [MCP Inspector](#mcp-inspector-manual-testing) or the command below to do a manual smoke check with real data:

```bash
uv run python -c "from finance_mcp import server; print(server.get_quote(['AAPL']))"
```

### MCP Inspector (manual testing)

Test every tool and prompt without wiring up a client, using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) (requires Node.js 22.19.0+ on PATH):

```bash
uv run mcp dev src/finance_mcp/server.py
```

This opens a browser UI where you pick a tool, fill in its arguments, and inspect the raw JSON-RPC request/response. Try `get_quote(["AAPL"])` and an invalid ticker to check both the happy and error paths.
