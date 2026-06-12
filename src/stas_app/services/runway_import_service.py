"""Import external RWY airport blocks into APTRWY_MASTER.RWY."""

from __future__ import annotations

from pathlib import Path

from stas_app.models.runway_database import AirportBlock, RunwayMasterDatabase
from stas_app.models.runway_import import (
    RUNWAY_IMPORT_ACTION_ADD,
    RUNWAY_IMPORT_ACTION_OVERWRITE,
    RUNWAY_IMPORT_ACTION_SKIP,
    RUNWAY_IMPORT_OVERWRITE_EXISTING,
    RUNWAY_IMPORT_SKIP_EXISTING,
    RunwayImportAirport,
    RunwayImportPreview,
    RunwayImportResult,
)
from stas_app.parsers.runway_database_parser import parse_runway_master_file
from stas_app.storage.runway_master_repository import RunwayMasterRepository, merged_runway_database
from stas_app.services.runway_intersection_generator import generate_intersections_for_airport_block


class RunwayImportService:
    """Preview and import airport data into the APTRWY master database."""

    def __init__(
        self,
        master_file: str | Path,
        seed_file: str | Path | None = None,
        backup_dir: str | Path | None = None,
    ) -> None:
        self.repository = RunwayMasterRepository(master_file, seed_file=seed_file, backup_dir=backup_dir)

    @property
    def master_file(self) -> Path:
        return self.repository.master_file

    def preview_import(self, source_file: str | Path, mode: str = RUNWAY_IMPORT_SKIP_EXISTING) -> RunwayImportPreview:
        """Return what would be added, overwritten, or skipped from an external RWY file."""

        mode = self._normalize_mode(mode)
        source_path = Path(source_file)
        source_database = parse_runway_master_file(source_path)
        if not source_database.airport_order:
            raise ValueError(f"导入文件中没有可识别的机场: {source_path}")

        base_database = self.repository.load_or_seed()
        airports = tuple(
            self._preview_airport(source_database.airports[icao], base_database, mode)
            for icao in source_database.airport_order
        )
        return RunwayImportPreview(
            source_file=source_path,
            master_file=self.repository.master_file,
            mode=mode,
            airports=airports,
        )

    def import_airports(self, source_file: str | Path, mode: str = RUNWAY_IMPORT_SKIP_EXISTING) -> RunwayImportResult:
        """Merge importable airport blocks into APTRWY_MASTER.RWY."""

        mode = self._normalize_mode(mode)
        source_path = Path(source_file)
        source_database = parse_runway_master_file(source_path)
        if not source_database.airport_order:
            raise ValueError(f"导入文件中没有可识别的机场: {source_path}")

        base_database = self.repository.load_or_seed()
        preview = RunwayImportPreview(
            source_file=source_path,
            master_file=self.repository.master_file,
            mode=mode,
            airports=tuple(
                self._preview_airport(source_database.airports[icao], base_database, mode)
                for icao in source_database.airport_order
            ),
        )
        imported_blocks = tuple(
            source_database.airports[airport.icao]
            for airport in preview.airports
            if airport.action in {RUNWAY_IMPORT_ACTION_ADD, RUNWAY_IMPORT_ACTION_OVERWRITE}
        )
        if not imported_blocks:
            return RunwayImportResult(
                preview=preview,
                master_file=self.repository.master_file,
                backup_path=None,
                written=False,
            )

        if not base_database.airport_order and not base_database.preamble_lines:
            base_database = self._empty_database_like_source(source_database)

        merged = merged_runway_database(base_database, imported_blocks, mode)
        backup_path = self.repository.save(merged)
        return RunwayImportResult(
            preview=preview,
            master_file=self.repository.master_file,
            backup_path=backup_path,
            written=True,
        )

    def _preview_airport(
        self,
        block: AirportBlock,
        base_database: RunwayMasterDatabase,
        mode: str,
    ) -> RunwayImportAirport:
        exists = block.icao in base_database.airports
        preview_block = generate_intersections_for_airport_block(block)
        if exists and mode == RUNWAY_IMPORT_SKIP_EXISTING:
            action = RUNWAY_IMPORT_ACTION_SKIP
        elif exists:
            action = RUNWAY_IMPORT_ACTION_OVERWRITE
        else:
            action = RUNWAY_IMPORT_ACTION_ADD

        return RunwayImportAirport(
            icao=block.icao,
            runway_ids=preview_block.runway_ids,
            exists_in_master=exists,
            action=action,
        )

    def _empty_database_like_source(self, source_database: RunwayMasterDatabase) -> RunwayMasterDatabase:
        return RunwayMasterDatabase(
            preamble_lines=source_database.preamble_lines,
            airports={},
            airport_order=(),
            profile=source_database.profile,
        )

    def _normalize_mode(self, mode: str) -> str:
        if mode in {RUNWAY_IMPORT_SKIP_EXISTING, RUNWAY_IMPORT_OVERWRITE_EXISTING}:
            return mode
        raise ValueError(f"未知机场导入模式: {mode}")
