"""Queue-level report generation for ordered STAS scenario results."""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from stas_app.exporters.manual_takeoff_report import (
    ManualTakeoffReportExporter,
    split_manual_takeoff_report_sections,
)
from stas_app.exporters.pdf_report import PDFReportExporter
from stas_app.exporters.word_report import WordReportExporter, split_stas_report_sections
from stas_app.models.config import (
    QUEUE_MANUAL_PDF_REPORT_FILENAME,
    QUEUE_MANUAL_WORD_REPORT_FILENAME,
    QUEUE_TEMPORARY_PDF_REPORT_FILENAME,
    QUEUE_TEMPORARY_WORD_REPORT_FILENAME,
)
from stas_app.models.report import QueueReportResult, ReportExportResult
from stas_app.models.request import PerformanceRequest
from stas_app.models.result import PerformanceCalculationResult


class QueueWordReportExporterLike(Protocol):
    """Minimal interface needed to export pre-split queue report sections."""

    def export_sections(
        self,
        sections: Sequence[str],
        docx_path: str | Path,
        logo_path: str | Path | None = None,
        report_date_override: str = "",
    ) -> ReportExportResult:
        ...


class QueuePDFReportExporterLike(Protocol):
    """Minimal interface needed to convert queue Word reports to PDF."""

    def export(self, docx_path: str | Path, pdf_path: str | Path) -> ReportExportResult:
        ...


class QueueManualWordReportExporterLike(Protocol):
    """Minimal interface needed to export manual takeoff queue report sections."""

    def export_sections(
        self,
        sections: Sequence[str],
        docx_path: str | Path,
        template_id: str,
        requests: Sequence[PerformanceRequest] = (),
    ) -> ReportExportResult:
        ...


class QueueReportExporter:
    """Build one merged Word/PDF report from an ordered scenario queue."""

    def __init__(
        self,
        output_root: str | Path,
        word_exporter: QueueWordReportExporterLike | None = None,
        pdf_exporter: QueuePDFReportExporterLike | None = None,
        manual_word_exporter: QueueManualWordReportExporterLike | None = None,
        logo_path: str | Path | None = None,
        merged_output_filename: str = "STAS_QUEUE.out",
        word_report_filename: str = QUEUE_TEMPORARY_WORD_REPORT_FILENAME,
        pdf_report_filename: str = QUEUE_TEMPORARY_PDF_REPORT_FILENAME,
        manual_word_report_filename: str = QUEUE_MANUAL_WORD_REPORT_FILENAME,
        manual_pdf_report_filename: str = QUEUE_MANUAL_PDF_REPORT_FILENAME,
    ) -> None:
        self.output_root = Path(output_root)
        self.word_exporter = word_exporter or WordReportExporter()
        self.pdf_exporter = pdf_exporter or PDFReportExporter()
        self.manual_word_exporter = manual_word_exporter or ManualTakeoffReportExporter()
        self.logo_path = Path(logo_path) if logo_path else None
        self.merged_output_filename = self._ensure_simple_filename(merged_output_filename, "Merged output filename")
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

    def export(self, results: Sequence[PerformanceCalculationResult]) -> QueueReportResult:
        """Export a merged queue report using only successful scenario outputs."""

        started = time.perf_counter()
        warnings: list[str] = []
        report_sections: list[str] = []
        report_requests: list[PerformanceRequest] = []
        manual_report_sections: list[str] = []
        manual_report_requests: list[PerformanceRequest] = []
        manual_template_ids: list[str] = []
        merged_output_blocks: list[str] = []

        for index, result in enumerate(results, start=1):
            collected = self._collect_result_output(index, result)
            if collected is None:
                warnings.append(self._skipped_result_message(index, result))
                continue

            header, raw_content, scenario_sections, scenario_manual_sections = collected
            merged_output_blocks.append(f"{header}\n{'-' * 79}\n{raw_content.rstrip()}")
            report_sections.extend(section.rstrip() for section in scenario_sections)
            report_requests.append(result.request)

            template_id = result.request.manual_report_template_id.strip()
            if template_id:
                manual_template_ids.append(template_id)
            manual_report_sections.extend(scenario_manual_sections)
            manual_report_requests.append(result.request)

        if not merged_output_blocks:
            return QueueReportResult(
                status="error",
                elapsed_seconds=time.perf_counter() - started,
                error_message="No successful scenario raw output was available for queue report",
                warnings=tuple(warnings),
            )

        manual_report_selected = bool(manual_template_ids)
        try:
            run_dir = self._create_queue_directory()
            merged_output_path = run_dir / self.merged_output_filename
            merged_output_path.write_text("\n\n".join(merged_output_blocks) + "\n", encoding="utf-8")

            if manual_report_selected:
                word_report = None
                pdf_report = None
                manual_word_report, manual_pdf_report, manual_template_id = self._export_manual_reports(
                    manual_report_sections,
                    manual_report_requests,
                    manual_template_ids,
                    run_dir,
                )
            else:
                word_report = self.word_exporter.export_sections(
                    report_sections,
                    run_dir / self.word_report_filename,
                    self.logo_path,
                    _shared_report_date_override(report_requests),
                )
                pdf_report = self._export_pdf_report(word_report, run_dir)
                manual_word_report = None
                manual_pdf_report = None
                manual_template_id = ""
        except Exception as exc:
            return QueueReportResult(
                status="error",
                elapsed_seconds=time.perf_counter() - started,
                error_message=f"Queue report export failed: {exc}",
                warnings=tuple(warnings),
            )

        warnings.extend(self._report_warnings(word_report, pdf_report, manual_word_report, manual_pdf_report))
        return QueueReportResult(
            status="success",
            run_dir=run_dir,
            merged_output_path=merged_output_path,
            word_report=word_report,
            pdf_report=pdf_report,
            manual_word_report=manual_word_report,
            manual_pdf_report=manual_pdf_report,
            manual_report_template_id=manual_template_id,
            elapsed_seconds=time.perf_counter() - started,
            warnings=tuple(warnings),
        )

    def _collect_result_output(
        self,
        index: int,
        result: PerformanceCalculationResult,
    ) -> tuple[str, str, list[str], list[str]] | None:
        if not result.succeeded or result.stas_run is None or result.stas_run.report_source_path is None:
            return None

        report_source_path = result.stas_run.report_source_path
        if not report_source_path.exists():
            return None

        raw_content = report_source_path.read_text(encoding="utf-8", errors="replace")
        if not raw_content.strip():
            return None

        sections = split_stas_report_sections(raw_content)
        if not sections:
            sections = [raw_content]
        manual_sections = split_manual_takeoff_report_sections(raw_content)
        if not manual_sections:
            manual_sections = [raw_content]

        return self._scenario_header(index, result, report_source_path), raw_content, sections, manual_sections

    def _scenario_header(self, index: int, result: PerformanceCalculationResult, report_source_path: Path) -> str:
        request = result.request
        scenario_id = request.scenario_id or f"scenario_{index:02d}"
        runways = ",".join(request.runways) or "*"
        contamination_depth = request.contamination_depth or "-"
        direct_derate = request.derate or "-"
        thrust_option = request.thrust_option or "NORMAL"
        bleed = request.bleed or "DEFAULT"
        return "\n".join(
            (
                f"SCENARIO {index:02d}: {scenario_id}",
                f"Aircraft: {request.aircraft_code}  Airport: {request.airport_code}  Runways: {runways}",
                (
                    f"Runway condition: {request.runway_condition}  Depth(mm): {contamination_depth}  "
                    f"Thrust option: {thrust_option}  Direct derate(%): {direct_derate}"
                ),
                f"Bleed: {bleed}  Anti-ice: {request.anti_icing}",
                f"Report source: {report_source_path}",
            )
        )

    def _skipped_result_message(self, index: int, result: PerformanceCalculationResult) -> str:
        scenario_id = result.request.scenario_id or f"scenario_{index:02d}"
        if not result.succeeded:
            reason = result.error_message or "calculation failed"
        elif result.stas_run is None or result.stas_run.report_source_path is None:
            reason = "STAS report output is missing"
        elif not result.stas_run.report_source_path.exists():
            reason = f"STAS report output does not exist: {result.stas_run.report_source_path}"
        else:
            reason = "STAS report output is empty"
        return f"Skipped scenario {index:02d} ({scenario_id}): {reason}"

    def _export_pdf_report(
        self,
        word_report: ReportExportResult,
        run_dir: Path,
    ) -> ReportExportResult | None:
        if not word_report.succeeded or word_report.output_path is None:
            return None

        return self.pdf_exporter.export(word_report.output_path, run_dir / self.pdf_report_filename)

    def _export_manual_reports(
        self,
        sections: Sequence[str],
        requests: Sequence[PerformanceRequest],
        template_ids: Sequence[str],
        run_dir: Path,
    ) -> tuple[ReportExportResult | None, ReportExportResult | None, str]:
        if not template_ids:
            return None, None, ""

        target_path = run_dir / self.manual_word_report_filename
        unique_template_ids = tuple(dict.fromkeys(template_ids))
        if len(template_ids) != len(requests) or len(unique_template_ids) != 1:
            word_report = ReportExportResult(
                status="error",
                output_path=target_path,
                error_message=(
                    "队列手册起飞分析只能用于同一机型、同一推力计算；"
                    "当前队列包含不同或缺失的手册模板"
                ),
            )
            return word_report, None, ""

        template_id = unique_template_ids[0]
        word_report = self.manual_word_exporter.export_sections(
            sections,
            target_path,
            template_id,
            requests,
        )
        pdf_report = self._export_manual_pdf_report(word_report, run_dir)
        return word_report, pdf_report, template_id

    def _export_manual_pdf_report(
        self,
        manual_word_report: ReportExportResult,
        run_dir: Path,
    ) -> ReportExportResult | None:
        if not manual_word_report.succeeded or manual_word_report.output_path is None:
            return None

        return self.pdf_exporter.export(manual_word_report.output_path, run_dir / self.manual_pdf_report_filename)

    def _report_warnings(
        self,
        word_report: ReportExportResult,
        pdf_report: ReportExportResult | None,
        manual_word_report: ReportExportResult | None,
        manual_pdf_report: ReportExportResult | None,
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if word_report is not None and not word_report.succeeded:
            warnings.append(f"Queue temporary takeoff Word report was not generated: {word_report.error_message}")
        if pdf_report is not None and not pdf_report.succeeded:
            warnings.append(f"Queue temporary takeoff PDF report was not generated: {pdf_report.error_message}")
        if manual_word_report is not None and not manual_word_report.succeeded:
            warnings.append(f"Queue manual takeoff Word report was not generated: {manual_word_report.error_message}")
        if manual_pdf_report is not None and not manual_pdf_report.succeeded:
            warnings.append(f"Queue manual takeoff PDF report was not generated: {manual_pdf_report.error_message}")
        return tuple(warnings)

    def _create_queue_directory(self) -> Path:
        self.output_root.mkdir(parents=True, exist_ok=True)
        base_name = f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_QUEUE"
        queue_dir = self.output_root / base_name
        suffix = 1
        while queue_dir.exists():
            suffix += 1
            queue_dir = self.output_root / f"{base_name}_{suffix}"
        queue_dir.mkdir(parents=True)
        return queue_dir

    def _ensure_simple_filename(self, filename: str, label: str) -> str:
        if Path(filename).name != filename:
            raise ValueError(f"{label} must not include path separators: {filename}")
        return filename


def _shared_report_date_override(requests: Sequence[PerformanceRequest]) -> str:
    for request in requests:
        token = request.report_date_override.strip()
        if token:
            return token
    return ""
