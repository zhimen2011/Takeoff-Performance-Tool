"""Factory functions that wire application services from configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from stas_app.exporters.manual_takeoff_report import ManualTakeoffReportExporter
from stas_app.exporters.word_report import WordReportExporter
from stas_app.models.manual_report import ManualTakeoffReportTemplate
from stas_app.models.config import AppConfig
from stas_app.models.runway import AirportRunways, Runway, RunwayDataset
from stas_app.models.runway_database import AirportBlock, RunwayMasterDatabase
from stas_app.parsers.runway_database_parser import parse_runway_master_file
from stas_app.parsers.runway_parser import parse_runway_line_metrics
from stas_app.services.aircraft_registry import AircraftRegistry
from stas_app.services.input_builder import StasInputBuilder
from stas_app.services.performance_service import (
    PDFReportExporterLike,
    PerformanceService,
    WordReportExporterLike,
)
from stas_app.services.runway_intersection_generator import generate_intersections_for_database
from stas_app.services.runway_import_service import RunwayImportService
from stas_app.services.runway_runtime_file import RunwayRuntimeFileService
from stas_app.services.runway_procedure_enricher import RunwayProcedureEnricher
from stas_app.services.single_point_input_builder import SinglePointInputBuilder
from stas_app.services.single_point_service import SinglePointTakeoffService
from stas_app.services.stas_engine import StasEngine, StasEngineConfig


@dataclass(frozen=True)
class ApplicationContext:
    """Services and lookup data needed by application entry points."""

    config: AppConfig
    aircraft_registry: AircraftRegistry
    runway_dataset: RunwayDataset
    performance_service: PerformanceService
    runway_import_service: RunwayImportService
    manual_report_exporter: ManualTakeoffReportExporter
    manual_report_templates: tuple[ManualTakeoffReportTemplate, ...]
    single_point_service: SinglePointTakeoffService


def create_performance_service(
    config: AppConfig,
    word_exporter: WordReportExporterLike | None = None,
    pdf_exporter: PDFReportExporterLike | None = None,
) -> PerformanceService:
    """Build a complete PerformanceService from application config."""

    return create_application_context(config, word_exporter, pdf_exporter).performance_service


def create_application_context(
    config: AppConfig,
    word_exporter: WordReportExporterLike | None = None,
    pdf_exporter: PDFReportExporterLike | None = None,
) -> ApplicationContext:
    """Build services plus lookup data from application config."""

    aircraft_registry = AircraftRegistry.from_directory(config.aircraft_config_dir)
    runway_dataset = _runway_dataset_for_ui(config)
    runway_runtime_file_preparer = _runway_runtime_file_preparer(config)
    runway_import_service = RunwayImportService(
        _runway_master_target_file(config),
        seed_file=config.airport_runway_file,
    )
    manual_report_exporter = ManualTakeoffReportExporter(config.manual_report_template_dir)
    temporary_report_exporter = word_exporter or WordReportExporter(config.manual_report_template_dir)
    input_builder = StasInputBuilder(
        template_dir=config.template_dir,
        airport_file=_airport_file_for_stas(config),
    )
    single_point_input_builder = SinglePointInputBuilder(
        template_dir=config.template_dir,
        airport_file=_airport_file_for_stas(config),
    )
    stas_engine = StasEngine(
        StasEngineConfig(
            executable_path=config.stas_executable_path,
            work_dir=config.stas_work_dir,
            output_root=config.output_root,
            executable_args=config.executable_args,
            input_filename=config.input_filename,
            output_filename=config.output_filename,
            error_filename=config.error_filename,
            timeout_seconds=config.timeout_seconds,
        )
    )

    performance_service = PerformanceService(
        aircraft_registry=aircraft_registry,
        runway_dataset=runway_dataset,
        input_builder=input_builder,
        stas_engine=stas_engine,
        word_exporter=temporary_report_exporter,
        pdf_exporter=pdf_exporter,
        manual_word_exporter=manual_report_exporter,
        logo_path=config.logo_path,
        word_report_filename=config.word_report_filename,
        pdf_report_filename=config.pdf_report_filename,
        manual_word_report_filename=config.manual_word_report_filename,
        manual_pdf_report_filename=config.manual_pdf_report_filename,
        runway_runtime_file_preparer=runway_runtime_file_preparer,
        runway_procedure_enricher=RunwayProcedureEnricher(config.airport_runway_file),
    )
    single_point_service = SinglePointTakeoffService(
        aircraft_registry=aircraft_registry,
        runway_dataset=runway_dataset,
        input_builder=single_point_input_builder,
        stas_engine=stas_engine,
        stas_work_dir=config.stas_work_dir,
        runway_runtime_file_preparer=runway_runtime_file_preparer,
        runway_procedure_file=config.airport_runway_file,
    )
    return ApplicationContext(
        config=config,
        aircraft_registry=aircraft_registry,
        runway_dataset=runway_dataset,
        performance_service=performance_service,
        runway_import_service=runway_import_service,
        manual_report_exporter=manual_report_exporter,
        manual_report_templates=manual_report_exporter.templates(),
        single_point_service=single_point_service,
    )


def _airport_file_for_stas(config: AppConfig) -> Path:
    """Use a path that STAS can resolve from its own working directory."""

    airport_file = Path(config.airport_runway_file).resolve()
    work_dir = Path(config.stas_work_dir).resolve()
    try:
        return airport_file.relative_to(work_dir)
    except ValueError:
        return airport_file


def _runway_source_file_for_ui(config: AppConfig) -> Path:
    return _runway_existing_master_file(config) or config.airport_runway_file


def _runway_dataset_for_ui(config: AppConfig) -> RunwayDataset:
    database = generate_intersections_for_database(parse_runway_master_file(_runway_source_file_for_ui(config)))
    return _runway_dataset_from_database(database)


def _runway_dataset_from_database(database: RunwayMasterDatabase) -> RunwayDataset:
    return RunwayDataset.from_airports(
        AirportRunways(
            icao=block.icao,
            runways=_runways_from_airport_block(block),
        )
        for block in (database.airports[icao] for icao in database.airport_order)
    )


def _runways_from_airport_block(block: AirportBlock) -> tuple[Runway, ...]:
    runways: list[Runway] = []
    seen: set[str] = set()
    for index, line in enumerate(block.raw_lines[:-1]):
        stripped = line.strip()
        if not stripped.startswith("RWY"):
            continue

        runway_line = block.raw_lines[index + 1]
        match = re.search(r"'([^']+)'", runway_line)
        if not match:
            continue

        runway_id = match.group(1).strip()
        if not runway_id or runway_id in seen:
            continue

        metrics = parse_runway_line_metrics(runway_line, match)
        runways.append(
            Runway(
                identifier=runway_id,
                record_type=stripped.split()[0],
                tora_m=metrics.tora_m,
                toda_m=metrics.toda_m,
                asda_m=metrics.asda_m,
                slope_percent=metrics.slope_percent,
                is_intersection=_looks_like_intersection_runway(runway_id),
            )
        )
        seen.add(runway_id)
    return tuple(runways)


def _looks_like_intersection_runway(runway_id: str) -> bool:
    return "-" in runway_id or "/" in runway_id


def _runway_runtime_file_preparer(config: AppConfig) -> RunwayRuntimeFileService | None:
    master_file = _runway_existing_master_file(config)
    if master_file is None:
        return None
    if master_file.resolve() == config.airport_runway_file.resolve():
        return None
    return RunwayRuntimeFileService(master_file, config.airport_runway_file)


def _runway_master_target_file(config: AppConfig) -> Path:
    if config.airport_runway_master_file is not None:
        return config.airport_runway_master_file

    return config.airport_runway_file.with_name("APTRWY_MASTER.RWY")


def _runway_existing_master_file(config: AppConfig) -> Path | None:
    master_file = _runway_master_target_file(config)
    if master_file.exists():
        return master_file
    return None
