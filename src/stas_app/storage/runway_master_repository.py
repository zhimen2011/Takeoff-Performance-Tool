"""Read, merge, back up, and write APTRWY_MASTER.RWY."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from stas_app.models.runway_database import AirportBlock, RunwayFileProfile, RunwayMasterDatabase
from stas_app.models.runway_import import RUNWAY_IMPORT_OVERWRITE_EXISTING
from stas_app.parsers.runway_database_parser import parse_runway_master_file


class RunwayMasterRepository:
    """Persistence helper for the APTRWY master runway database."""

    def __init__(
        self,
        master_file: str | Path,
        seed_file: str | Path | None = None,
        backup_dir: str | Path | None = None,
    ) -> None:
        self.master_file = Path(master_file)
        self.seed_file = Path(seed_file) if seed_file else None
        self.backup_dir = Path(backup_dir) if backup_dir else self.master_file.parent / "backups"

    def load_or_seed(self) -> RunwayMasterDatabase:
        """Load the master file, or seed from the current runtime APTRWY.RWY if needed."""

        if self.master_file.exists():
            return parse_runway_master_file(self.master_file)

        if self.seed_file and self.seed_file.exists():
            return parse_runway_master_file(self.seed_file)

        return RunwayMasterDatabase(
            preamble_lines=(),
            airports={},
            airport_order=(),
            profile=RunwayFileProfile(),
        )

    def save(self, database: RunwayMasterDatabase) -> Path | None:
        """Write the full master database and return a backup path when one was created."""

        self.master_file.parent.mkdir(parents=True, exist_ok=True)
        backup_path = self._backup_master_file()
        temp_path = self.master_file.with_name(f"{self.master_file.name}.tmp")
        temp_path.write_text(
            self._render_database(database),
            encoding=database.profile.encoding,
            newline=database.profile.line_ending,
        )
        temp_path.replace(self.master_file)
        return backup_path

    def _render_database(self, database: RunwayMasterDatabase) -> str:
        lines: list[str] = []
        lines.extend(database.preamble_lines)
        while lines and not lines[-1].strip():
            lines.pop()
        if lines:
            lines.append("")

        for index, icao in enumerate(database.airport_order):
            block = database.airports[icao]
            if index > 0:
                lines.append("")
            lines.extend(block.raw_lines)

        return "\n".join(lines).rstrip("\n") + "\n"

    def _backup_master_file(self) -> Path | None:
        if not self.master_file.exists():
            return None

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = self.backup_dir / f"{self.master_file.stem}_{timestamp}{self.master_file.suffix}"
        shutil.copy2(self.master_file, backup_path)
        return backup_path


def merged_runway_database(
    base: RunwayMasterDatabase,
    imported_blocks: tuple[AirportBlock, ...],
    mode: str,
) -> RunwayMasterDatabase:
    """Merge imported airport blocks into a base database."""

    airports = dict(base.airports)
    airport_order = list(base.airport_order)

    for block in imported_blocks:
        exists = block.icao in airports
        if exists and mode != RUNWAY_IMPORT_OVERWRITE_EXISTING:
            continue

        airports[block.icao] = block
        if not exists:
            airport_order.append(block.icao)

    return RunwayMasterDatabase(
        preamble_lines=base.preamble_lines,
        airports=airports,
        airport_order=tuple(airport_order),
        profile=base.profile,
    )
