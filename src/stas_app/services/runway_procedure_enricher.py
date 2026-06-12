"""Enrich STAS output ENG-OUT PROCEDURE text from the runtime runway file."""

from __future__ import annotations

from dataclasses import dataclass
import re
import textwrap
from pathlib import Path

from stas_app.parsers.runway_database_parser import parse_runway_master_file


SPECIAL_PROCEDURE_MARKER = "*** SEE SPECIAL PROCEDURE FOR THIS RUNWAY ***"
NO_EMERGENCY_TURN_TITLE = "*** NO EMERGENCY TURN ***"
NO_EMERGENCY_TURN_MARKER = "NO EMERGENCY TURN"
RUNWAY_HEADER_PATTERN = re.compile(r"\bELEVATION\b.*\bRUNWAY\s+(\S+)\s+([A-Z0-9]{4})\b")
RUNWAY_ID_PATTERN = re.compile(r"'([^']+)'")
AVIATION_DATE_SUFFIX_PATTERN = re.compile(r"\s*\d{2}\s+[A-Z]{3}\s+\d{4}\s*$")
REPORT_PROCEDURE_INDENT = "      "
REPORT_PROCEDURE_WIDTH = 100


@dataclass(frozen=True)
class RunwayProcedure:
    """Complete procedure text for one runway."""

    title: str
    detail: str = ""

    def report_lines(self) -> tuple[str, ...]:
        lines = [f"{REPORT_PROCEDURE_INDENT}{self.title}"]
        if self.detail:
            lines.extend(
                textwrap.wrap(
                    self.detail,
                    width=REPORT_PROCEDURE_WIDTH,
                    initial_indent=REPORT_PROCEDURE_INDENT,
                    subsequent_indent=REPORT_PROCEDURE_INDENT,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
            )
        return tuple(lines)


class RunwayProcedureEnricher:
    """Create an enriched STAS output file with full special procedure text."""

    def __init__(self, runway_file: str | Path) -> None:
        self.runway_file = Path(runway_file)

    def enrich_file(self, stas_output_path: str | Path, target_path: str | Path | None = None) -> Path:
        """Write an enriched STAS output file and return its path."""

        source_path = Path(stas_output_path)
        if target_path:
            enriched_path = Path(target_path)
        else:
            enriched_path = source_path.with_name(f"{source_path.stem}.enriched{source_path.suffix}")
        content = source_path.read_text(encoding="utf-8", errors="replace")
        enriched_path.write_text(self.enrich_text(content), encoding="utf-8")
        return enriched_path

    def enrich_text(self, stas_output: str) -> str:
        """Return STAS output with complete special procedure text where available."""

        procedures = extract_runway_procedures(self.runway_file)
        if not procedures:
            return stas_output

        output_lines: list[str] = []
        lines = stas_output.splitlines()
        current_key: tuple[str, str] | None = None
        index = 0

        while index < len(lines):
            line = lines[index]
            runway_match = RUNWAY_HEADER_PATTERN.search(line)
            if runway_match:
                current_key = (runway_match.group(2).upper(), runway_match.group(1).strip().upper())

            if "ENG-OUT PROCEDURE:" in line and current_key in procedures:
                output_lines.append(line)
                output_lines.extend(procedures[current_key].report_lines())
                index += 1
                while index < len(lines) and not RUNWAY_HEADER_PATTERN.search(lines[index]):
                    index += 1
                continue

            output_lines.append(line)
            index += 1

        trailing_newline = "\n" if stas_output.endswith(("\n", "\r\n")) else ""
        return "\n".join(output_lines) + trailing_newline


def extract_runway_procedures(runway_file: str | Path) -> dict[tuple[str, str], RunwayProcedure]:
    """Extract complete special procedures keyed by ``(ICAO, runway_id)``."""

    database = parse_runway_master_file(runway_file)
    procedures: dict[tuple[str, str], RunwayProcedure] = {}
    for airport in database.airports.values():
        for record_lines in _iter_runway_record_lines(airport.raw_lines):
            runway_id = _parse_runway_id(record_lines)
            if not runway_id:
                continue

            procedure = _extract_special_procedure(record_lines)
            if procedure is not None:
                procedures[(airport.icao.upper(), runway_id.upper())] = procedure

    return procedures


def extract_runway_display_procedures(runway_file: str | Path) -> dict[tuple[str, str], RunwayProcedure]:
    """Extract procedure text for UI display, including no-turn runway records."""

    database = parse_runway_master_file(runway_file)
    procedures: dict[tuple[str, str], RunwayProcedure] = {}
    for airport in database.airports.values():
        for record_lines in _iter_runway_record_lines(airport.raw_lines):
            runway_id = _parse_runway_id(record_lines)
            if not runway_id:
                continue

            procedure = _extract_display_procedure(record_lines)
            if procedure is not None:
                procedures[(airport.icao.upper(), runway_id.upper())] = procedure

    return procedures


def _iter_runway_record_lines(lines: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    records: list[tuple[str, ...]] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip().startswith("RWY"):
            index += 1
            continue

        end = index + 1
        while end < len(lines) and not lines[end].strip().startswith("RWY"):
            end += 1
        records.append(tuple(lines[index:end]))
        index = end

    return tuple(records)


def _parse_runway_id(record_lines: tuple[str, ...]) -> str:
    if len(record_lines) < 2:
        return ""

    match = RUNWAY_ID_PATTERN.search(record_lines[1])
    return match.group(1).strip() if match else ""


def _extract_special_procedure(record_lines: tuple[str, ...]) -> RunwayProcedure | None:
    text_index = _text_line_index(record_lines)
    if text_index is None:
        return None

    text = _clean_quoted_text(record_lines[text_index])
    if not text or NO_EMERGENCY_TURN_MARKER in text.upper():
        return None
    if SPECIAL_PROCEDURE_MARKER not in text:
        return None

    title, inline_detail = _split_special_procedure_text(text)
    h_detail = _continuous_h_text(record_lines, text_index + 1)
    detail = " ".join(part for part in (inline_detail, h_detail) if part).strip()
    if NO_EMERGENCY_TURN_MARKER in detail.upper():
        return None
    return RunwayProcedure(title=title, detail=detail)


def _extract_display_procedure(record_lines: tuple[str, ...]) -> RunwayProcedure | None:
    text_index = _text_line_index(record_lines)
    if text_index is None:
        return None

    text = _clean_quoted_text(record_lines[text_index])
    if not text:
        return None

    if NO_EMERGENCY_TURN_MARKER in text.upper():
        return RunwayProcedure(title=NO_EMERGENCY_TURN_TITLE)

    if SPECIAL_PROCEDURE_MARKER not in text:
        return None

    title, inline_detail = _split_special_procedure_text(text)
    h_detail = _continuous_h_display_text(record_lines, text_index + 1)
    detail = "\n".join(part for part in (inline_detail, h_detail) if part).strip()
    if NO_EMERGENCY_TURN_MARKER in detail.upper():
        return RunwayProcedure(title=NO_EMERGENCY_TURN_TITLE)
    return RunwayProcedure(title=title, detail=detail)


def _text_line_index(record_lines: tuple[str, ...]) -> int | None:
    for index, line in enumerate(record_lines[2:], start=2):
        stripped = line.strip()
        if stripped.startswith("'") and "'" in stripped[1:]:
            return index
    return None


def _clean_quoted_text(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("'") and stripped.endswith("'") and len(stripped) >= 2:
        return AVIATION_DATE_SUFFIX_PATTERN.sub("", stripped[1:-1]).rstrip()

    match = RUNWAY_ID_PATTERN.search(stripped)
    text = match.group(1) if match else stripped
    return AVIATION_DATE_SUFFIX_PATTERN.sub("", text).rstrip()


def _split_special_procedure_text(text: str) -> tuple[str, str]:
    marker_index = text.find(SPECIAL_PROCEDURE_MARKER)
    title = text[: marker_index + len(SPECIAL_PROCEDURE_MARKER)].strip()
    detail = text[marker_index + len(SPECIAL_PROCEDURE_MARKER) :].strip()
    return title, detail


def _continuous_h_text(record_lines: tuple[str, ...], start_index: int) -> str:
    parts: list[str] = []
    index = start_index
    while index < len(record_lines):
        stripped = record_lines[index].strip()
        if not stripped.startswith("H "):
            break
        parts.append(stripped[2:].strip())
        index += 1
    return " ".join(parts)


def _continuous_h_display_text(record_lines: tuple[str, ...], start_index: int) -> str:
    parts: list[str] = []
    index = start_index
    while index < len(record_lines):
        stripped = record_lines[index].strip()
        if not stripped.startswith("H "):
            break
        parts.append(stripped[2:].strip())
        index += 1
    return "\n".join(parts)
