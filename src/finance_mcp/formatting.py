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
