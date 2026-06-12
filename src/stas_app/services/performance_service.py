"""High-level orchestration service for one STAS performance calculation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from stas_app.exporters.manual_takeoff_report import ManualTakeoffReportExporter
from stas_app.exporters.pdf_report import PDFReportExporter
from stas_app.exporters.word_report import WordReportExporter
from stas_app.models.config import (
    MANUAL_PDF_REPORT_FILENAME,
    MANUAL_WORD_REPORT_FILENAME,
    TEMPORARY_PDF_REPORT_FILENAME,
    TEMPORARY_WORD_REPORT_FILENAME,
)
from stas_app.models.report import ReportExportResult
from stas_app.models.request import PerformanceRequest
from stas_app.models.result import PerformanceCalculationResult, StasRunResult
from stas_app.models.runway import RunwayDataset
from stas_app.services.aircraft_registry import AircraftRegistry
from stas_app.services.input_builder import StasInputBuilder
from stas_app.services.stas_engine import StasEngine
from stas_app.services.validation import ValidationError, validate_performance_request


class WordReportExporterLike(Protocol):
    """Minimal interface needed from a Word report exporter."""

    def export(
        self,
        stas_output_path: str | Path,
        docx_path: str | Path,
        logo_path: str | Path | None = None,
        report_date_override: str = "",
    ) -> ReportExportResult:
        ...


class PDFReportExporterLike(Protocol):
    """Minimal interface needed from a PDF report exporter."""

    def export(self, docx_path: str | Path, pdf_path: str | Path) -> ReportExportResult:
        ...


class ManualWordReportExporterLike(Protocol):
    """Minimal interface needed from a manual takeoff Word report exporter."""

    def export(
        self,
        stas_output_path: str | Path,
        docx_path: str | Path,
        template_id: str,
        request: PerformanceRequest | None = None,
    ) -> ReportExportResult:
        ...

    def export_sections(
        self,
        sections: Sequence[str],
        docx_path: str | Path,
        template_id: str,
        requests: Sequence[PerformanceRequest] = (),
    ) -> ReportExportResult:
        ...


class StasEngineLike(Protocol):
    """Minimal interface needed from the STAS engine."""

    def run(self, request: PerformanceRequest, input_content: str) -> StasRunResult:
        ...


class RunwayRuntimeFilePreparerLike(Protocol):
    """Minimal interface for preparing STAS APTRWY.RWY before a calculation."""

    def prepare_for_airports(self, airport_codes: Sequence[str]) -> Path:
        ...


class RunwayProcedureEnricherLike(Protocol):
    """Minimal interface for creating a report-ready STAS output file."""

    def enrich_file(self, stas_output_path: str | Path, target_path: str | Path | None = None) -> Path:
        ...


class PerformanceService:
    """Coordinate validation, STAS execution, and report export."""

    def __init__(
        self,
        aircraft_registry: AircraftRegistry,
        runway_dataset: RunwayDataset,
        input_builder: StasInputBuilder,
        stas_engine: StasEngineLike | StasEngine,
        word_exporter: WordReportExporterLike | None = None,
        pdf_exporter: PDFReportExporterLike | None = None,
        manual_word_exporter: ManualWordReportExporterLike | None = None,
        logo_path: str | Path | None = None,
        word_report_filename: str = TEMPORARY_WORD_REPORT_FILENAME,
        pdf_report_filename: str = TEMPORARY_PDF_REPORT_FILENAME,
        manual_word_report_filename: str = MANUAL_WORD_REPORT_FILENAME,
        manual_pdf_report_filename: str = MANUAL_PDF_REPORT_FILENAME,
        runway_runtime_file_preparer: RunwayRuntimeFilePreparerLike | None = None,
        runway_procedure_enricher: RunwayProcedureEnricherLike | None = None,
    ) -> None:
        self.aircraft_registry = aircraft_registry
        self.runway_dataset = runway_dataset
        self.input_builder = input_builder
        self.stas_engine = stas_engine
        self.word_exporter = word_exporter or WordReportExporter()
        self.pdf_exporter = pdf_exporter or PDFReportExporter()
        self.manual_word_exporter = manual_word_exporter
        self.logo_path = Path(logo_path) if logo_path else None
        self.word_report_filename = self._ensure_simple_filename(word_report_filename, "Word report filename")
        self.pdf_report_filename = self._ensure_simple_filename(pdf_report_filename, "PDF report filename")
        self.manual_word_report_filename = self._ensure_simple_filename(
            manual_word_report_filename,
            "Manual Word report filename",
        )
        self.manual_pdf_report_filename = self._ensure_simple_filename(
            manual_pdf_report_filename,
            "Manual PDF report filename",
        )
        self.runway_runtime_file_preparer = runway_runtime_file_preparer
        self.runway_procedure_enricher = runway_procedure_enricher

    def calculate(self, request: PerformanceRequest) -> PerformanceCalculationResult:
        """Run one complete performance calculation and return a structured result."""

        try:
            validated_request = validate_performance_request(
                request=request,
                aircraft_registry=self.aircraft_registry,
                runway_dataset=self.runway_dataset,
            )
            aircraft = self.aircraft_registry.get(validated_request.aircraft_code)
            self._prepare_runtime_runway_file(validated_request)
            input_content = self.input_builder.build(validated_request, aircraft)
            stas_run = self.stas_engine.run(validated_request, input_content)
        except (ValidationError, FileNotFoundError, NotADirectoryError, OSError, ValueError, KeyError) as exc:
            return PerformanceCalculationResult(
                status="error",
                request=request,
                error_message=str(exc),
            )

        if not stas_run.succeeded:
            return PerformanceCalculationResult(
                status="error",
                request=validated_request,
                stas_run=stas_run,
                error_message=stas_run.error_message or "STAS calculation failed",
                warnings=stas_run.warnings,
            )

        stas_run, enrichment_warnings = self._prepare_report_output(stas_run)
        manual_template_id = validated_request.manual_report_template_id.strip()
        if manual_template_id:
            word_report = None
            pdf_report = None
            manual_word_report = self._export_manual_word_report(validated_request, stas_run)
            manual_pdf_report = self._export_manual_pdf_report(manual_word_report, stas_run)
        else:
            word_report = self._export_word_report(validated_request, stas_run)
            pdf_report = self._export_pdf_report(word_report, stas_run)
            manual_word_report = None
            manual_pdf_report = None
        warnings = (
            *stas_run.warnings,
            *enrichment_warnings,
            *self._build_report_warnings(word_report, pdf_report, manual_word_report, manual_pdf_report),
        )

        return PerformanceCalculationResult(
            status="success",
            request=validated_request,
            stas_run=stas_run,
            word_report=word_report,
            pdf_report=pdf_report,
            manual_word_report=manual_word_report,
            manual_pdf_report=manual_pdf_report,
            warnings=warnings,
        )

    def _export_word_report(self, request: PerformanceRequest, stas_run: StasRunResult) -> ReportExportResult:
        report_source_path = stas_run.report_source_path
        if report_source_path is None:
            return ReportExportResult(
                status="error",
                output_path=stas_run.run_dir / self.word_report_filename,
                error_message="STAS report output is missing; Word report was not generated",
            )

        target_path = stas_run.run_dir / self.word_report_filename
        try:
            return self.word_exporter.export(
                report_source_path,
                target_path,
                self.logo_path,
                request.report_date_override,
            )
        except Exception as exc:
            return ReportExportResult(
                status="error",
                output_path=target_path,
                error_message=f"Word report export failed: {exc}",
            )

    def _export_pdf_report(
        self,
        word_report: ReportExportResult,
        stas_run: StasRunResult,
    ) -> ReportExportResult | None:
        if not word_report.succeeded or word_report.output_path is None:
            return None

        target_path = stas_run.run_dir / self.pdf_report_filename
        try:
            return self.pdf_exporter.export(word_report.output_path, target_path)
        except Exception as exc:
            return ReportExportResult(
                status="error",
                output_path=target_path,
                error_message=f"PDF report export failed: {exc}",
            )

    def _export_manual_word_report(
        self,
        request: PerformanceRequest,
        stas_run: StasRunResult,
    ) -> ReportExportResult | None:
        template_id = request.manual_report_template_id.strip()
        if not template_id:
            return None

        target_path = stas_run.run_dir / self.manual_word_report_filename
        report_source_path = stas_run.report_source_path
        if report_source_path is None:
            return ReportExportResult(
                status="error",
                output_path=target_path,
                error_message="STAS report output is missing; manual Word report was not generated",
            )

        try:
            return self._manual_word_exporter().export(report_source_path, target_path, template_id, request)
        except Exception as exc:
            return ReportExportResult(
                status="error",
                output_path=target_path,
                error_message=f"Manual Word report export failed: {exc}",
            )

    def _export_manual_pdf_report(
        self,
        manual_word_report: ReportExportResult | None,
        stas_run: StasRunResult,
    ) -> ReportExportResult | None:
        if manual_word_report is None or not manual_word_report.succeeded or manual_word_report.output_path is None:
            return None

        target_path = stas_run.run_dir / self.manual_pdf_report_filename
        try:
            return self.pdf_exporter.export(manual_word_report.output_path, target_path)
        except Exception as exc:
            return ReportExportResult(
                status="error",
                output_path=target_path,
                error_message=f"Manual PDF report export failed: {exc}",
            )

    def _build_report_warnings(
        self,
        word_report: ReportExportResult,
        pdf_report: ReportExportResult | None,
        manual_word_report: ReportExportResult | None,
        manual_pdf_report: ReportExportResult | None,
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if word_report is not None and not word_report.succeeded:
            warnings.append(f"Temporary takeoff Word report was not generated: {word_report.error_message}")

        if pdf_report is not None and not pdf_report.succeeded:
            warnings.append(f"Temporary takeoff PDF report was not generated: {pdf_report.error_message}")

        if manual_word_report is not None and not manual_word_report.succeeded:
            warnings.append(f"Manual takeoff Word report was not generated: {manual_word_report.error_message}")

        if manual_pdf_report is not None and not manual_pdf_report.succeeded:
            warnings.append(f"Manual takeoff PDF report was not generated: {manual_pdf_report.error_message}")

        return tuple(warnings)

    def _manual_word_exporter(self) -> ManualWordReportExporterLike:
        if self.manual_word_exporter is None:
            self.manual_word_exporter = ManualTakeoffReportExporter()
        return self.manual_word_exporter

    def _prepare_runtime_runway_file(self, request: PerformanceRequest) -> None:
        if self.runway_runtime_file_preparer is None:
            return
        self.runway_runtime_file_preparer.prepare_for_airports((request.airport_code,))

    def _prepare_report_output(self, stas_run: StasRunResult) -> tuple[StasRunResult, tuple[str, ...]]:
        if self.runway_procedure_enricher is None or stas_run.raw_output_path is None:
            return stas_run, ()

        try:
            enriched_path = self.runway_procedure_enricher.enrich_file(stas_run.raw_output_path)
        except Exception as exc:
            return stas_run, (f"STAS special procedure text was not enriched: {exc}",)

        return replace(stas_run, report_output_path=enriched_path), ()

    def _ensure_simple_filename(self, filename: str, label: str) -> str:
        if Path(filename).name != filename:
            raise ValueError(f"{label} must not include path separators: {filename}")
        return filename
