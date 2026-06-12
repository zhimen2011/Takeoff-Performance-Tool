"""Result models for report export operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ReportExportResult:
    """Structured result for one report export step."""

    status: str
    output_path: Path | None = None
    elapsed_seconds: float = 0.0
    error_message: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        return self.status == "success"


@dataclass(frozen=True)
class QueueReportResult:
    """Structured result for a queue-level merged report export."""

    status: str
    run_dir: Path | None = None
    merged_output_path: Path | None = None
    word_report: ReportExportResult | None = None
    pdf_report: ReportExportResult | None = None
    manual_word_report: ReportExportResult | None = None
    manual_pdf_report: ReportExportResult | None = None
    manual_report_template_id: str = ""
    elapsed_seconds: float = 0.0
    error_message: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def succeeded(self) -> bool:
        return self.status == "success"
