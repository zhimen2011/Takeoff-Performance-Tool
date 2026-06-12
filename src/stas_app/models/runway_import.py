"""Models for importing airport blocks into APTRWY_MASTER.RWY."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


RUNWAY_IMPORT_SKIP_EXISTING = "skip_existing"
RUNWAY_IMPORT_OVERWRITE_EXISTING = "overwrite_existing"

RUNWAY_IMPORT_ACTION_ADD = "add"
RUNWAY_IMPORT_ACTION_OVERWRITE = "overwrite"
RUNWAY_IMPORT_ACTION_SKIP = "skip"


@dataclass(frozen=True)
class RunwayImportAirport:
    """One airport shown in an import preview."""

    icao: str
    runway_ids: tuple[str, ...]
    exists_in_master: bool
    action: str

    @property
    def runway_count(self) -> int:
        return len(self.runway_ids)


@dataclass(frozen=True)
class RunwayImportPreview:
    """Preview of how an external RWY file would be merged."""

    source_file: Path
    master_file: Path
    mode: str
    airports: tuple[RunwayImportAirport, ...]

    @property
    def add_count(self) -> int:
        return sum(1 for airport in self.airports if airport.action == RUNWAY_IMPORT_ACTION_ADD)

    @property
    def overwrite_count(self) -> int:
        return sum(1 for airport in self.airports if airport.action == RUNWAY_IMPORT_ACTION_OVERWRITE)

    @property
    def skip_count(self) -> int:
        return sum(1 for airport in self.airports if airport.action == RUNWAY_IMPORT_ACTION_SKIP)

    @property
    def write_count(self) -> int:
        return self.add_count + self.overwrite_count


@dataclass(frozen=True)
class RunwayImportResult:
    """Result after importing airport blocks into the master file."""

    preview: RunwayImportPreview
    master_file: Path
    backup_path: Path | None
    written: bool

    @property
    def imported_codes(self) -> tuple[str, ...]:
        return tuple(
            airport.icao
            for airport in self.preview.airports
            if airport.action in {RUNWAY_IMPORT_ACTION_ADD, RUNWAY_IMPORT_ACTION_OVERWRITE}
        )
