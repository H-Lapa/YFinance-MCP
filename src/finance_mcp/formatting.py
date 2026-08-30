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
