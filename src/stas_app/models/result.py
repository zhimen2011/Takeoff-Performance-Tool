"""Result models for STAS execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from stas_app.models.report import ReportExportResult
from stas_app.models.request import PerformanceRequest


@dataclass(frozen=True)
class StasRunResult:
    """Structured result returned after invoking the external STAS program."""

    status: str
    run_dir: Path
    input_path: Path
    raw_output_path: Path | None = None
    report_output_path: Path | None = None
    stas_error_path: Path | None = None
    metadata_path: Path | None = None
    return_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    stas_error: str = ""
    elapsed_seconds: float = 0.0
    error_message: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        return self.status == "success"

    @property
    def report_source_path(self) -> Path | None:
        """Output file that report exporters should read."""

        return self.report_output_path or self.raw_output_path


@dataclass(frozen=True)
class PerformanceCalculationResult:
    """Complete result returned by the high-level performance service."""

    status: str
    request: PerformanceRequest
    stas_run: StasRunResult | None = None
    word_report: ReportExportResult | None = None
    pdf_report: ReportExportResult | None = None
    manual_word_report: ReportExportResult | None = None
    manual_pdf_report: ReportExportResult | None = None
    error_message: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        return self.status == "success"
