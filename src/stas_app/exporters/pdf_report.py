"""PDF report generation through Microsoft Word COM automation."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from stas_app.models.report import ReportExportResult


class PDFReportExporter:
    """Convert a Word document to PDF when Microsoft Word COM is available."""

    WORD_PDF_FORMAT = 17

    def export(self, docx_path: str | Path, pdf_path: str | Path) -> ReportExportResult:
        started = time.perf_counter()
        source_path = Path(docx_path)
        target_path = Path(pdf_path)

        if not source_path.exists():
            return ReportExportResult(
                status="error",
                output_path=target_path,
                elapsed_seconds=time.perf_counter() - started,
                error_message=f"Word document does not exist: {source_path}",
            )

        if not sys.platform.startswith("win"):
            return ReportExportResult(
                status="error",
                output_path=target_path,
                elapsed_seconds=time.perf_counter() - started,
                error_message="PDF conversion requires Windows and Microsoft Word",
            )

        try:
            self._convert(source_path, target_path)
        except ImportError as exc:
            return ReportExportResult(
                status="error",
                output_path=target_path,
                elapsed_seconds=time.perf_counter() - started,
                error_message=f"PDF conversion requires comtypes and pythoncom: {exc}",
            )
        except Exception as exc:
            return ReportExportResult(
                status="error",
                output_path=target_path,
                elapsed_seconds=time.perf_counter() - started,
                error_message=f"PDF conversion failed: {exc}",
            )

        return ReportExportResult(
            status="success",
            output_path=target_path,
            elapsed_seconds=time.perf_counter() - started,
        )

    def _convert(self, source_path: Path, target_path: Path) -> None:
        import comtypes.client
        import pythoncom

        target_path.parent.mkdir(parents=True, exist_ok=True)

        pythoncom.CoInitialize()
        word = None
        document = None
        try:
            word = comtypes.client.CreateObject("Word.Application")
            word.Visible = False
            word.DisplayAlerts = False

            document = word.Documents.Open(str(source_path.resolve()))
            document.SaveAs(str(target_path.resolve()), FileFormat=self.WORD_PDF_FORMAT)
        finally:
            try:
                if document:
                    document.Close(SaveChanges=False)
                if word:
                    word.Quit()
            finally:
                pythoncom.CoUninitialize()

