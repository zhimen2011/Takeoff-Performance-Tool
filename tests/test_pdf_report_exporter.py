from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.exporters.pdf_report import PDFReportExporter


class PDFReportExporterTests(unittest.TestCase):
    def test_missing_docx_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "STASOUT.pdf"

            result = PDFReportExporter().export(Path(temp_dir) / "missing.docx", target)

            self.assertFalse(result.succeeded)
            self.assertIn("does not exist", result.error_message)

    def test_non_windows_returns_error_without_com_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "STASOUT.docx"
            target = Path(temp_dir) / "STASOUT.pdf"
            source.write_text("not a real docx", encoding="utf-8")

            with patch("sys.platform", "linux"):
                result = PDFReportExporter().export(source, target)

            self.assertFalse(result.succeeded)
            self.assertIn("requires Windows", result.error_message)

    def test_success_path_can_be_simulated_without_word_com(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "STASOUT.docx"
            target = Path(temp_dir) / "STASOUT.pdf"
            source.write_text("not a real docx", encoding="utf-8")

            with patch.object(PDFReportExporter, "_convert", side_effect=lambda _src, dst: dst.write_text("pdf", encoding="utf-8")):
                result = PDFReportExporter().export(source, target)

            self.assertTrue(result.succeeded, result.error_message)
            self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()

