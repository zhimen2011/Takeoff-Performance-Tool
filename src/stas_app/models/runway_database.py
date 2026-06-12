"""Raw airport-block models for APTRWY master databases."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunwayFileProfile:
    """Basic format metadata detected from an APTRWY file."""

    encoding: str = "utf-8"
    line_ending: str = "\n"
    airport_record_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class AirportBlock:
    """One airport's complete raw block from an APTRWY file."""

    icao: str
    record_type: str
    raw_lines: tuple[str, ...]
    runway_ids: tuple[str, ...] = ()

    @property
    def raw_text(self) -> str:
        return "\n".join(self.raw_lines).rstrip("\n")


@dataclass(frozen=True)
class RunwayMasterDatabase:
    """Parsed APTRWY master database preserving complete airport blocks."""

    preamble_lines: tuple[str, ...]
    airports: dict[str, AirportBlock]
    airport_order: tuple[str, ...]
    profile: RunwayFileProfile

    def airport_codes(self) -> tuple[str, ...]:
        return tuple(self.airport_order)

    def selected_blocks_in_master_order(self, airport_codes: tuple[str, ...]) -> tuple[AirportBlock, ...]:
        requested = {code.strip().upper() for code in airport_codes if code.strip()}
        return tuple(self.airports[icao] for icao in self.airport_order if icao in requested)
