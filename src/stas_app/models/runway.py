"""Structured runway data parsed from APTRWY.RWY files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Runway:
    """A runway entry belonging to one airport."""

    identifier: str
    record_type: str
    tora_m: float | None = None
    toda_m: float | None = None
    asda_m: float | None = None
    slope_percent: float | None = None
    is_intersection: bool = False


@dataclass(frozen=True)
class AirportRunways:
    """Runway list for one ICAO airport."""

    icao: str
    runways: tuple[Runway, ...]

    @property
    def runway_ids(self) -> tuple[str, ...]:
        return tuple(runway.identifier for runway in self.runways)


@dataclass(frozen=True)
class RunwayDataset:
    """Parsed airport/runway lookup data."""

    airports: dict[str, AirportRunways]

    def airport_codes(self) -> tuple[str, ...]:
        return tuple(sorted(self.airports))

    def airport_exists(self, airport_code: str) -> bool:
        return airport_code.strip().upper() in self.airports

    def get_airport(self, airport_code: str) -> AirportRunways | None:
        return self.airports.get(airport_code.strip().upper())

    def get_runway_ids(self, airport_code: str) -> tuple[str, ...]:
        airport = self.get_airport(airport_code)
        if airport is None:
            return ()
        return airport.runway_ids

    def get_runway(self, airport_code: str, runway_id: str) -> Runway | None:
        airport = self.get_airport(airport_code)
        if airport is None:
            return None

        target = runway_id.strip().upper()
        for runway in airport.runways:
            if runway.identifier.strip().upper() == target:
                return runway
        return None

    @classmethod
    def from_airports(cls, airports: Iterable[AirportRunways]) -> "RunwayDataset":
        return cls({airport.icao: airport for airport in airports})
