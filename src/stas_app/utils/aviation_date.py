"""Aviation-style report date helpers."""

from __future__ import annotations

import calendar
import re


AVIATION_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
AVIATION_DATE_PATTERN = re.compile(r"^\d{2}-(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-\d{4}$")
DATED_LINE_PATTERN = re.compile(r"\bDATED\s+\d{1,2}-(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-\d{4}\b")


def format_aviation_date(day: int | str, month: int | str, year: int | str) -> str:
    """Return a validated ``DD-MMM-YYYY`` date string."""

    day_value = int(str(day).strip())
    year_value = int(str(year).strip())
    month_text = _normalize_month(month)
    month_number = AVIATION_MONTHS.index(month_text) + 1
    max_day = calendar.monthrange(year_value, month_number)[1]
    if day_value < 1 or day_value > max_day:
        raise ValueError(f"Invalid report date day for {month_text} {year_value}: {day_value}")
    return f"{day_value:02d}-{month_text}-{year_value:04d}"


def validate_aviation_date(value: str) -> str:
    """Return a normalized aviation date or raise ``ValueError``."""

    token = value.strip().upper()
    if not AVIATION_DATE_PATTERN.match(token):
        raise ValueError(f"Invalid report date format: {value}")

    day_text, month_text, year_text = token.split("-")
    return format_aviation_date(day_text, month_text, year_text)


def replace_report_date(text: str, report_date_override: str) -> str:
    """Replace all ``DATED DD-MMM-YYYY`` tokens in report text."""

    report_date = report_date_override.strip()
    if not report_date:
        return text
    normalized = validate_aviation_date(report_date)
    return DATED_LINE_PATTERN.sub(f"DATED {normalized}", text)


def _normalize_month(month: int | str) -> str:
    token = str(month).strip().upper()
    if token.isdigit():
        index = int(token)
        if index < 1 or index > 12:
            raise ValueError(f"Invalid report date month: {month}")
        return AVIATION_MONTHS[index - 1]
    if token not in AVIATION_MONTHS:
        raise ValueError(f"Invalid report date month: {month}")
    return token
