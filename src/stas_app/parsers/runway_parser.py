"""Parser for Boeing STAS APTRWY.RWY airport/runway data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from stas_app.models.runway import AirportRunways, Runway, RunwayDataset


AIRPORT_RECORD_TYPES = {"AIRPORT1", "AIRPORT2"}
RUNWAY_RECORD_PREFIX = "RWY"


@dataclass(frozen=True)
class RunwayLineMetrics:
    """Distance and slope values parsed from one APTRWY runway line."""

    tora_m: float | None = None
    toda_m: float | None = None
    asda_m: float | None = None
    slope_percent: float | None = None


class APTRWYRunwayParser:
    """Parse APTRWY.RWY data into airport/runway lookup structures."""

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)

    def parse(self) -> RunwayDataset:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Runway data file does not exist: {self.file_path}")

        lines = self._load_effective_lines()
        airports: dict[str, AirportRunways] = {}

        index = 0
        current_icao: str | None = None
        current_runways: list[Runway] = []

        while index < len(lines):
            line = lines[index]

            if line in AIRPORT_RECORD_TYPES:
                self._store_airport(airports, current_icao, current_runways)
                current_runways = []

                index += 1
                if index >= len(lines):
                    break

                current_icao = self._parse_airport_code(line, lines[index])
                index += 1
                continue

            if line.startswith(RUNWAY_RECORD_PREFIX):
                index = self._parse_runway_record(lines, index, current_icao, current_runways)
                continue

            index += 1

        self._store_airport(airports, current_icao, current_runways)
        return RunwayDataset(airports)

    def _load_effective_lines(self) -> list[str]:
        with self.file_path.open("r", encoding="utf-8") as file:
            return [
                line.strip()
                for line in file
                if line.strip()
                and not line.strip().startswith("#")
                and not line.strip().startswith("H")
            ]

    def _parse_airport_code(self, record_type: str, airport_line: str) -> str | None:
        if record_type == "AIRPORT1":
            fields = re.findall(r"'([^']*)'", airport_line)
            if not fields:
                return None
            return fields[0].strip().upper()

        return airport_line[:4].strip().upper()

    def _parse_runway_record(
        self,
        lines: list[str],
        index: int,
        current_icao: str | None,
        current_runways: list[Runway],
    ) -> int:
        record_type = lines[index].split()[0]
        index += 1

        if index >= len(lines):
            return index

        runway_line = lines[index]
        runway_match = re.search(r"'([^']+)'", runway_line)
        if current_icao and runway_match:
            runway_id = runway_match.group(1).strip()
            if runway_id:
                metrics = parse_runway_line_metrics(runway_line, runway_match)
                current_runways.append(
                    Runway(
                        identifier=runway_id,
                        record_type=record_type,
                        tora_m=metrics.tora_m,
                        toda_m=metrics.toda_m,
                        asda_m=metrics.asda_m,
                        slope_percent=metrics.slope_percent,
                        is_intersection=self._looks_like_intersection_runway(runway_id),
                    )
                )

        obstacle_count = self._parse_obstacle_count(runway_line, runway_match)

        index += 1 + obstacle_count

        if record_type in {"RWYU", "RWYV"} and index < len(lines) and "'" in lines[index]:
            index += 1

        if record_type in {"RWYT", "RWYV"} and index < len(lines) and re.match(r"^\d", lines[index]):
            index += 1

        return index

    def _parse_obstacle_count(self, runway_line: str, runway_match: re.Match[str] | None) -> int:
        if not runway_match:
            return 0

        remaining = runway_line[runway_match.end() :].strip()
        fields = remaining.split()
        if len(fields) < 9:
            return 0

        try:
            return max(0, int(fields[8]))
        except ValueError:
            return 0

    def _looks_like_intersection_runway(self, runway_id: str) -> bool:
        return "-" in runway_id or "/" in runway_id

    def _store_airport(
        self,
        airports: dict[str, AirportRunways],
        icao: str | None,
        runways: list[Runway],
    ) -> None:
        if not icao:
            return

        existing = airports.get(icao)
        if existing is None:
            airports[icao] = AirportRunways(icao=icao, runways=tuple(runways))
            return

        seen = set(existing.runway_ids)
        merged = list(existing.runways)
        for runway in runways:
            if runway.identifier not in seen:
                merged.append(runway)
                seen.add(runway.identifier)

        airports[icao] = AirportRunways(icao=icao, runways=tuple(merged))


def parse_runway_file(file_path: str | Path) -> RunwayDataset:
    """Parse an APTRWY.RWY file."""

    return APTRWYRunwayParser(file_path).parse()


def parse_runway_line_metrics(runway_line: str, runway_match: re.Match[str] | None) -> RunwayLineMetrics:
    """Parse TORA, TODA, ASDA and slope from an APTRWY runway data line."""

    if not runway_match:
        return RunwayLineMetrics()

    fields = runway_line[runway_match.end() :].split()
    return RunwayLineMetrics(
        tora_m=_parse_float_field(fields, 1),
        toda_m=_parse_float_field(fields, 2),
        asda_m=_parse_float_field(fields, 3),
        slope_percent=_parse_float_field(fields, 5),
    )


def _parse_float_field(fields: list[str], index: int) -> float | None:
    if len(fields) <= index:
        return None

    try:
        return float(fields[index])
    except ValueError:
        return None
