from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.storage.config_repository import ConfigError, load_app_config


class ConfigRepositoryTests(unittest.TestCase):
    def test_loads_config_and_resolves_relative_paths_against_base_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "app.toml"
            config_path.write_text(
                """
[paths]
aircraft_config_dir = "config/aircraft"
template_dir = "templates"
airport_runway_file = "runtime/stas/APTRWY.RWY"
airport_runway_master_file = "runtime/stas/APTRWY_MASTER.RWY"
stas_executable_path = "runtime/stas/STAS.exe"
stas_work_dir = "runtime/stas"
output_root = "output"
logo_path = "assets/logo.png"
manual_report_template_dir = "templates/reports/manual_takeoff"

[stas]
timeout_seconds = 30
input_filename = "INPUT"
output_filename = "OUTPUT"
error_filename = "ERROR"
executable_args = ["--fake", "success"]

[reports]
word_report_filename = "report.docx"
pdf_report_filename = "report.pdf"
manual_word_report_filename = "manual.docx"
manual_pdf_report_filename = "manual.pdf"
queue_word_report_filename = "queue_report.docx"
queue_pdf_report_filename = "queue_report.pdf"
queue_manual_word_report_filename = "queue_manual.docx"
queue_manual_pdf_report_filename = "queue_manual.pdf"
""".strip(),
                encoding="utf-8",
            )

            config = load_app_config(config_path, base_dir=root)

            self.assertEqual(config.aircraft_config_dir, root / "config" / "aircraft")
            self.assertEqual(config.template_dir, root / "templates")
            self.assertEqual(config.airport_runway_file, root / "runtime" / "stas" / "APTRWY.RWY")
            self.assertEqual(config.airport_runway_master_file, root / "runtime" / "stas" / "APTRWY_MASTER.RWY")
            self.assertEqual(config.stas_executable_path, root / "runtime" / "stas" / "STAS.exe")
            self.assertEqual(config.stas_work_dir, root / "runtime" / "stas")
            self.assertEqual(config.output_root, root / "output")
            self.assertEqual(config.logo_path, root / "assets" / "logo.png")
            self.assertEqual(config.manual_report_template_dir, root / "templates" / "reports" / "manual_takeoff")
            self.assertEqual(config.timeout_seconds, 30)
            self.assertEqual(config.executable_args, ("--fake", "success"))
            self.assertEqual(config.input_filename, "INPUT")
            self.assertEqual(config.output_filename, "OUTPUT")
            self.assertEqual(config.error_filename, "ERROR")
            self.assertEqual(config.word_report_filename, "report.docx")
            self.assertEqual(config.pdf_report_filename, "report.pdf")
            self.assertEqual(config.manual_word_report_filename, "manual.docx")
            self.assertEqual(config.manual_pdf_report_filename, "manual.pdf")
            self.assertEqual(config.queue_word_report_filename, "queue_report.docx")
            self.assertEqual(config.queue_pdf_report_filename, "queue_report.pdf")
            self.assertEqual(config.queue_manual_word_report_filename, "queue_manual.docx")
            self.assertEqual(config.queue_manual_pdf_report_filename, "queue_manual.pdf")

    def test_missing_paths_section_is_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "app.toml"
            config_path.write_text("[stas]\ntimeout_seconds = 30\n", encoding="utf-8")

            with self.assertRaisesRegex(ConfigError, "Missing \\[paths\\]"):
                load_app_config(config_path, base_dir=temp_dir)

    def test_invalid_timeout_is_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "app.toml"
            config_path.write_text(
                """
[paths]
aircraft_config_dir = "config/aircraft"
template_dir = "templates"
airport_runway_file = "runtime/stas/APTRWY.RWY"
stas_executable_path = "runtime/stas/STAS.exe"
stas_work_dir = "runtime/stas"
output_root = "output"

[stas]
timeout_seconds = 0
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "timeout_seconds"):
                load_app_config(config_path, base_dir=temp_dir)


if __name__ == "__main__":
    unittest.main()
