"""Application-level configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


TEMPORARY_WORD_REPORT_FILENAME = "\u4e34\u65f6\u8d77\u98de\u5206\u6790.docx"
TEMPORARY_PDF_REPORT_FILENAME = "\u4e34\u65f6\u8d77\u98de\u5206\u6790.pdf"
MANUAL_WORD_REPORT_FILENAME = "\u624b\u518c\u8d77\u98de\u5206\u6790.docx"
MANUAL_PDF_REPORT_FILENAME = "\u624b\u518c\u8d77\u98de\u5206\u6790.pdf"
QUEUE_TEMPORARY_WORD_REPORT_FILENAME = "\u961f\u5217_\u4e34\u65f6\u8d77\u98de\u5206\u6790.docx"
QUEUE_TEMPORARY_PDF_REPORT_FILENAME = "\u961f\u5217_\u4e34\u65f6\u8d77\u98de\u5206\u6790.pdf"
QUEUE_MANUAL_WORD_REPORT_FILENAME = "\u961f\u5217_\u624b\u518c\u8d77\u98de\u5206\u6790.docx"
QUEUE_MANUAL_PDF_REPORT_FILENAME = "\u961f\u5217_\u624b\u518c\u8d77\u98de\u5206\u6790.pdf"


@dataclass(frozen=True)
class AppConfig:
    """Paths and runtime options needed to build the application services."""

    aircraft_config_dir: Path
    template_dir: Path
    airport_runway_file: Path
    stas_executable_path: Path
    stas_work_dir: Path
    output_root: Path
    airport_runway_master_file: Path | None = None
    manual_report_template_dir: Path = Path("templates/reports/manual_takeoff")
    logo_path: Path | None = None
    timeout_seconds: int = 1200
    executable_args: tuple[str, ...] = field(default_factory=tuple)
    input_filename: str = "STASINP"
    output_filename: str = "STASOUT.out"
    error_filename: str = "STASERR"
    word_report_filename: str = TEMPORARY_WORD_REPORT_FILENAME
    pdf_report_filename: str = TEMPORARY_PDF_REPORT_FILENAME
    manual_word_report_filename: str = MANUAL_WORD_REPORT_FILENAME
    manual_pdf_report_filename: str = MANUAL_PDF_REPORT_FILENAME
    queue_word_report_filename: str = QUEUE_TEMPORARY_WORD_REPORT_FILENAME
    queue_pdf_report_filename: str = QUEUE_TEMPORARY_PDF_REPORT_FILENAME
    queue_manual_word_report_filename: str = QUEUE_MANUAL_WORD_REPORT_FILENAME
    queue_manual_pdf_report_filename: str = QUEUE_MANUAL_PDF_REPORT_FILENAME
