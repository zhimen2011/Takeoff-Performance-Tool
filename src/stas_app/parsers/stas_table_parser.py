"""Parse STAS variable-output table files."""

from __future__ import annotations

import re
from pathlib import Path


STAS_NULL_THRESHOLD = 8.0e20
HEADER_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]*\(\d+\)")


def parse_stas_table(path: str | Path) -> list[dict[str, float]]:
    """Parse a STASTBL file into rows keyed by normalized SCAP variable name."""

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_stas_table_text(text)


def parse_stas_table_text(text: str) -> list[dict[str, float]]:
    """Parse STASTBL text into one dictionary per data row."""

    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    header_index = _find_header_index(lines)
    if header_index is None:
        return []

    headers = [_normalize_variable(token) for token in HEADER_PATTERN.findall(lines[header_index])]
    rows: list[dict[str, float]] = []
    for line in lines[header_index + 1 :]:
        values = line.split()
        if len(values) < len(headers):
            continue

        try:
            row = {header: float(value) for header, value in zip(headers, values)}
        except ValueError:
            continue
        rows.append(row)

    return rows


def is_stas_null(value: float | None) -> bool:
    """Return whether a SCAP value is the STAS null sentinel."""

    return value is None or abs(value) >= STAS_NULL_THRESHOLD


def _find_header_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if HEADER_PATTERN.search(line):
            return index
    return None


def _normalize_variable(value: str) -> str:
    name, _, raw_index = value.partition("(")
    index = raw_index.rstrip(")")
    return f"{name.upper()}({int(index):03d})"
