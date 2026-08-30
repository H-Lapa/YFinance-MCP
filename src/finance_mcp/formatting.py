"""Helpers for turning structured data into compact markdown for tool responses."""

from __future__ import annotations


def rows_to_markdown_table(rows: list[dict], columns: list[str]) -> str:
    """Render a list of dicts as a markdown table with a fixed column order.

    Missing keys render as an empty cell rather than raising, so callers can
    mix rows with different populated fields (e.g. success vs. error rows).
    """
    if not rows:
        return "(no data)"

    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, separator]
    for row in rows:
        cells = []
        for col in columns:
            value = row.get(col)
            cells.append("" if value in (None, "") else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


DISCLAIMER = "Not financial advice -- past performance does not guarantee future results."


def _currency_mismatch_note(currencies: dict[str, str | None]) -> str | None:
    """Build a warning line when `currencies` (ticker -> currency|None) spans
    more than one known currency, or None if they all match / are unknown.

    These tools combine *local-currency* returns -- mixing USD and EUR
    returns doesn't account for the FX exposure a real investor would also
    have, so a mismatch is surfaced explicitly rather than left implicit.
    """
    known = {currency for currency in currencies.values() if currency}
    if len(known) <= 1:
        return None

    listing = ", ".join(f"{ticker}: {currency or 'unknown'}" for ticker, currency in currencies.items())
    return (
        f"Note: holdings span multiple currencies ({listing}) -- these are local-currency "
        "returns and do not include FX exposure between them."
    )


def format_risk_metrics(result: dict) -> str:
    """Render a `risk.fetch_risk_metrics` result, naming every methodology
    assumption inline so a surprising number is at least legible about why."""
    lines = [
        f"# {result['ticker']} Risk Metrics (period={result['period']})",
        "",
        (
            f"Annualized volatility (252 trading days, simple daily returns): "
            f"{result['volatility'] * 100:.2f}%"
        ),
        f"Max drawdown: {result['max_drawdown'] * 100:.2f}%",
        (
            f"Sharpe ratio: {result['sharpe_ratio']:.2f} "
            f"(risk-free rate: {result['risk_free_rate'] * 100:.2f}%, {result['risk_free_rate_source']})"
        ),
        (
            f"Historical VaR ({result['confidence']:.0%} confidence, historical simulation, 1-day): "
            f"{result['var'] * 100:.2f}%"
        ),
    ]
    if result["benchmark"]:
        beta_text = f"{result['beta']:.2f}" if result["beta"] is not None else "N/A"
        lines.append(f"Beta vs {result['benchmark'].upper()}: {beta_text}")
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def format_dividends(result: dict) -> str:
    """Render a `market_data.fetch_dividends` result."""
    header = f"{result['ticker']} dividend history (period={result['period']})"
    if result["note"]:
        header += f"\n{result['note']}"
    summary = f"Trailing 12-month total: {result['trailing_12mo_total']:.2f}"
    table = rows_to_markdown_table(result["rows"], columns=["date", "amount"])
    return f"{header}\n\n{summary}\n\n{table}"


def format_correlation_matrix(result: dict) -> str:
    """Render a `risk.fetch_correlation` result: {"matrix": DataFrame, "currencies": dict}."""
    matrix = result["matrix"]
    tickers = list(matrix.columns)
    header = "| | " + " | ".join(tickers) + " |"
    separator = "| --- | " + " | ".join("---" for _ in tickers) + " |"
    lines = [
        "Pairwise correlation of daily returns (simple returns, Pearson correlation):",
        "",
        header,
        separator,
    ]
    for row_ticker in tickers:
        cells = [f"{matrix.loc[row_ticker, col]:.2f}" for col in tickers]
        lines.append(f"| {row_ticker} | " + " | ".join(cells) + " |")

    note = _currency_mismatch_note(result["currencies"])
    if note:
        lines.append("")
        lines.append(note)
    return "\n".join(lines)


def format_portfolio_metrics(result: dict) -> str:
    """Render a `risk.fetch_portfolio_metrics` result."""
    weights_lines = "\n".join(
        f"  {ticker}: {weight:.1%}" for ticker, weight in result["weights"].items()
    )
    lines = [
        "# Portfolio Metrics",
        "",
        "Weights (normalized to sum to 100%):",
        weights_lines,
        "",
        f"Annualized return (mean daily return x 252): {result['annualized_return'] * 100:.2f}%",
        (
            f"Annualized volatility (covariance-based, 252 trading days): "
            f"{result['annualized_volatility'] * 100:.2f}%"
        ),
    ]

    note = _currency_mismatch_note(result["currencies"])
    if note:
        lines.append("")
        lines.append(note)

    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)
