"""Parser for APTRWY master files that preserves complete airport blocks."""

from __future__ import annotations

import re
from pathlib import Path

from stas_app.models.runway_database import AirportBlock, RunwayFileProfile, RunwayMasterDatabase
from stas_app.parsers.runway_parser import AIRPORT_RECORD_TYPES


def parse_runway_master_file(file_path: str | Path) -> RunwayMasterDatabase:
    """Parse an APTRWY master file into raw airport blocks."""

    return APTRWYMasterParser(file_path).parse()


class APTRWYMasterParser:
    """Extract complete raw airport blocks from APTRWY master data."""

    def __init__(self, file_path: str | Path, encoding: str = "utf-8") -> None:
        self.file_path = Path(file_path)
        self.encoding = encoding

    def parse(self) -> RunwayMasterDatabase:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Runway master file does not exist: {self.file_path}")

        raw_text = self.file_path.read_text(encoding=self.encoding)
        line_ending = "\r\n" if "\r\n" in raw_text else "\n"
        lines = raw_text.splitlines()
        starts = [index for index, line in enumerate(lines) if line.strip() in AIRPORT_RECORD_TYPES]
        if not starts:
            return RunwayMasterDatabase(
                preamble_lines=tuple(lines),
                airports={},
                airport_order=(),
                profile=RunwayFileProfile(
                    encoding=self.encoding,
                    line_ending=line_ending,
                    airport_record_types=(),
                ),
            )

        preamble = tuple(lines[: starts[0]])
        airports: dict[str, AirportBlock] = {}
        airport_order: list[str] = []
        record_types: list[str] = []

        for position, start in enumerate(starts):
            end = starts[position + 1] if position + 1 < len(starts) else len(lines)
            block_lines = tuple(lines[start:end])
            record_type = block_lines[0].strip()
            icao = self._parse_airport_code(record_type, block_lines)
            if not icao:
                continue

            block = AirportBlock(
                icao=icao,
                record_type=record_type,
                raw_lines=block_lines,
                runway_ids=self._parse_runway_ids(block_lines),
            )
            if icao not in airports:
                airport_order.append(icao)
            airports[icao] = block
            if record_type not in record_types:
                record_types.append(record_type)

        return RunwayMasterDatabase(
            preamble_lines=preamble,
            airports=airports,
            airport_order=tuple(airport_order),
            profile=RunwayFileProfile(
                encoding=self.encoding,
                line_ending=line_ending,
                airport_record_types=tuple(record_types),
            ),
        )

    def _parse_airport_code(self, record_type: str, block_lines: tuple[str, ...]) -> str:
        if len(block_lines) < 2:
            return ""

        airport_line = block_lines[1].strip()
        if record_type == "AIRPORT1":
            fields = re.findall(r"'([^']*)'", airport_line)
            return fields[0].strip().upper() if fields else ""

        if record_type == "AIRPORT2":
            return airport_line[:4].strip().upper()

        return ""

    def _parse_runway_ids(self, block_lines: tuple[str, ...]) -> tuple[str, ...]:
        runway_ids: list[str] = []
        seen: set[str] = set()
        for line_index, line in enumerate(block_lines):
            stripped = line.strip()
            if not stripped.startswith("RWY"):
                continue
            index = line_index + 1
            if index >= len(block_lines):
                continue
            match = re.search(r"'([^']+)'", block_lines[index])
            if not match:
                continue
            runway_id = match.group(1).strip()
            if runway_id and runway_id not in seen:
                runway_ids.append(runway_id)
                seen.add(runway_id)
        return tuple(runway_ids)
