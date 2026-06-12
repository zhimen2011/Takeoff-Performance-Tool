"""Parse key takeoff performance rows from STASOUT text files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


RUNWAY_HEADER_PATTERN = re.compile(r"\bRUNWAY\s+(?P<runway>\S+)\s+(?P<airport>[A-Z0-9]{3,4})\b")
CONFIG_PATTERN = re.compile(
    r"\*\*\*\s+FLAPS\s+(?P<flaps>\S+)\s+\*\*\*\s+AIR COND\s+(?P<air_cond>.*?)\s+ANTI-ICE\s+(?P<anti_ice>.*?)(?:\s{2,}|$)"
)
CELL_PATTERN = re.compile(
    r"^(?P<weight>\d+(?:\.\d+)?)(?P<limit_code>[A-Z*]{0,2})/(?P<v1>\d+)-(?P<vr>\d+)-(?P<v2>\d+)$"
)
DATA_ROW_PATTERN = re.compile(r"^\s*(?P<temperature>-?\d+(?:\.\d+)?)\s+(?P<climb>\d+(?:\.\d+)?)\s+(?P<cells>.+?)\s*$")


def parse_stas_output(path: str | Path) -> list[dict[str, Any]]:
    """Parse STAS takeoff table rows into one record per temperature/wind cell."""

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_stas_output_text(text)


def parse_stas_output_text(text: str) -> list[dict[str, Any]]:
    """Parse STAS takeoff table rows from a text string."""

    rows: list[dict[str, Any]] = []
    context: dict[str, Any] = {}
    expect_units = False
    in_table = False
    temp_unit = ""
    weight_unit = ""
    wind_columns: list[float | int | str] = []

    for line in text.splitlines():
        runway_match = RUNWAY_HEADER_PATTERN.search(line)
        if runway_match:
            context["runway"] = runway_match.group("runway")
            context["airport_code"] = runway_match.group("airport")

        config_match = CONFIG_PATTERN.search(line)
        if config_match:
            context["flaps"] = config_match.group("flaps").strip()
            context["air_cond"] = config_match.group("air_cond").strip()
            context["anti_ice"] = config_match.group("anti_ice").strip()

        if "OAT" in line and "WIND COMPONENT" in line:
            expect_units = True
            in_table = False
            continue

        if expect_units:
            parts = line.split()
            if len(parts) >= 3:
                temp_unit = parts[0]
                weight_unit = parts[1]
                wind_columns = [_parse_number(token) for token in parts[2:]]
                in_table = True
            expect_units = False
            continue

        if not in_table:
            continue

        if not line.strip():
            in_table = False
            continue

        row_match = DATA_ROW_PATTERN.match(line)
        if not row_match:
            continue

        cells = row_match.group("cells").split()
        for index, cell in enumerate(cells):
            cell_match = CELL_PATTERN.match(cell)
            if not cell_match:
                continue

            scaled_weight = _parse_number(cell_match.group("weight"))
            scale, unit = _weight_scale(weight_unit)
            rows.append(
                {
                    **context,
                    "temperature": _parse_number(row_match.group("temperature")),
                    "temperature_unit": temp_unit,
                    "wind": wind_columns[index] if index < len(wind_columns) else "",
                    "climb_weight": _parse_number(row_match.group("climb")) * scale,
                    "mtow": scaled_weight * scale,
                    "weight_unit": unit,
                    "limit_code": cell_match.group("limit_code"),
                    "v1": int(cell_match.group("v1")),
                    "vr": int(cell_match.group("vr")),
                    "v2": int(cell_match.group("v2")),
                }
            )

    return rows


def _parse_number(value: str) -> float | int:
    number = float(value)
    if number.is_integer():
        return int(number)
    return number


def _weight_scale(weight_unit: str) -> tuple[int, str]:
    normalized = weight_unit.upper()
    if normalized == "100KG":
        return 100, "KG"
    if normalized == "100LB":
        return 100, "LB"
    return 1, weight_unit
