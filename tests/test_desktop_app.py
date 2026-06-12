from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(SRC_DIR))

from run_desktop import dearpygui_missing_message, is_missing_dearpygui_error, runtime_base_dir
from stas_app.models.report import ReportExportResult
from stas_app.models.request import PerformanceRequest
from stas_app.models.result import PerformanceCalculationResult, StasRunResult
from stas_app.models.runway import AirportRunways, Runway, RunwayDataset
from stas_app.services.aircraft_registry import AircraftRegistry
from stas_app.ui.forms import (
    PerformanceFormValues,
    apply_order_items,
    build_default_order_form_values,
    build_performance_request,
    contamination_depth_hint,
    default_temperature_range,
    display_thrust_option,
    export_order_items,
    format_result_summary,
    format_runway_summary,
    format_scenario_label,
    request_thrust_option,
    THRUST_DERATE_20,
    THRUST_NORMAL,
    runway_condition_requires_depth,
)
from stas_app.ui.desktop_app import (
    AIRPORT_IMPORT_FILE_DIALOG,
    MANUAL_TEMPLATE_COMBO,
    MANUAL_TEMPLATE_NONE_LABEL,
    REPORT_DATE_DAY_COMBO,
    REPORT_DATE_MONTH_COMBO,
    REPORT_DATE_OVERRIDE_CHECKBOX,
    REPORT_DATE_YEAR_INPUT,
    SINGLE_POINT_AIRCRAFT_COMBO,
    SINGLE_POINT_AIRPORT_COMBO,
    SINGLE_POINT_ANTI_ICING_COMBO,
    SINGLE_POINT_ASSUMED_TEMP_INPUT,
    SINGLE_POINT_ATM_MODE_COMBO,
    SINGLE_POINT_BLEED_COMBO,
    SINGLE_POINT_CONTAMINATION_DEPTH_INPUT,
    SINGLE_POINT_FLAP_COMBO,
    SINGLE_POINT_IMPROVED_CLIMB_CHECKBOX,
    SINGLE_POINT_OAT_INPUT,
    SINGLE_POINT_QNH_INPUT,
    SINGLE_POINT_RESULT_TEXT,
    SINGLE_POINT_RUNWAY_CONDITION_COMBO,
    SINGLE_POINT_RUNWAY_DISTANCE_TEXT,
    SINGLE_POINT_RUNWAY_GROUP,
    SINGLE_POINT_RUNWAY_MIN_TORA_ENABLED_CHECKBOX,
    SINGLE_POINT_RUNWAY_MIN_TORA_INPUT,
    SINGLE_POINT_THRUST_COMBO,
    SINGLE_POINT_WEIGHT_INPUT,
    SINGLE_POINT_WIND_INPUT,
    STASDesktopApp,
    filter_runways_for_display,
    is_supported_airport_import_path,
)


class FakeDpg:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values
        self.configured: dict[str, dict[str, object]] = {}

    def does_item_exist(self, tag: str) -> bool:
        return tag in self.values

    def get_value(self, tag: str) -> object:
        return self.values[tag]

    def set_value(self, tag: str, value: object) -> None:
        self.values[tag] = value

    def configure_item(self, tag: str, **kwargs: object) -> None:
        self.configured.setdefault(tag, {}).update(kwargs)

    def delete_item(self, tag: str, **kwargs: object) -> None:
        return None

    def add_text(self, text: str, **kwargs: object) -> None:
        return None

    def add_checkbox(self, **kwargs: object) -> None:
        tag = str(kwargs["tag"])
        self.values[tag] = bool(kwargs.get("default_value", False))


class FakeFileDialog:
    def __enter__(self) -> "FakeFileDialog":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeDpgWithFileDialog(FakeDpg):
    def __init__(self) -> None:
        super().__init__({})
        self.extensions: list[str] = []

    def file_dialog(self, **kwargs: object) -> FakeFileDialog:
        self.values[str(kwargs["tag"])] = True
        return FakeFileDialog()

    def add_file_extension(self, extension: str, **kwargs: object) -> None:
        self.extensions.append(extension)


class DesktopAppHelperTests(unittest.TestCase):
    def test_build_performance_request_normalizes_form_values(self) -> None:
        request = build_performance_request(
            PerformanceFormValues(
                aircraft_code=" 777F ",
                airport_code=" egnx ",
                runways=(" 09 ", "27"),
                anti_icing="1 发动机开启",
                temperature_range=" 10:-10:2 ",
                wind_range=" -10,0,10 ",
                qnh_ref=" 1013.25 ",
                thrust_option="1L1BUMP",
                report_date_override=" 04-apr-2026 ",
            )
        )

        self.assertEqual(
            request,
            PerformanceRequest(
                aircraft_code="777F",
                airport_code="EGNX",
                runways=("09", "27"),
                anti_icing="1",
                temperature_range="10:-10:2",
                wind_range="-10,0,10",
                qnh_ref="1013.25",
                thrust_option="1L1BUMP",
                report_date_override="04-APR-2026",
            ),
        )

    def test_build_performance_request_ignores_738_display_thrust(self) -> None:
        request = build_performance_request(
            PerformanceFormValues(
                aircraft_code="738",
                airport_code="EGNX",
                runways=(),
                anti_icing="0 关闭",
                temperature_range="",
                wind_range="",
                qnh_ref="",
                thrust_option=THRUST_NORMAL,
            )
        )

        self.assertIsNone(request.thrust_option)
        self.assertEqual(request.anti_icing, "0")

    def test_build_performance_request_extracts_gui_scenario_options(self) -> None:
        request = build_performance_request(
            PerformanceFormValues(
                aircraft_code="738",
                airport_code="HNL",
                runways=("08L",),
                anti_icing="7 ENG_WING_OPT",
                temperature_range="",
                wind_range="",
                qnh_ref="",
                thrust_option=THRUST_NORMAL,
                runway_condition="SLUSH Slush",
                contamination_depth="6",
                bleed="OFF Off",
            )
        )

        self.assertEqual(request.runway_condition, "SLUSH")
        self.assertEqual(request.contamination_depth, "6")
        self.assertEqual(request.bleed, "OFF")
        self.assertEqual(request.anti_icing, "7")
        self.assertEqual(request.derate, "")

    def test_default_order_form_values_matches_old_template_order(self) -> None:
        queue = build_default_order_form_values(
            PerformanceFormValues(
                aircraft_code="738",
                airport_code="HNL",
                runways=("08L",),
                anti_icing="0 OFF",
                temperature_range="65:50:5",
                wind_range="-10,0,10",
                qnh_ref="1013",
                thrust_option=THRUST_NORMAL,
            )
        )

        requests = [build_performance_request(item) for item in queue]

        self.assertEqual(
            [(item.runway_condition, item.bleed) for item in requests],
            [("DRY", "AUTO"), ("DRY", "OFF"), ("WET", "AUTO"), ("WET", "OFF")],
        )
        self.assertIn(f"01. 738 HNL RWY 08L DRY 推力={THRUST_NORMAL} 引气=AUTO 防冰=0", format_scenario_label(1, queue[0]))
        self.assertIn("温度=65:50:5 风=-10,0,10 QNH=1013", format_scenario_label(1, queue[0]))
        self.assertNotIn("手册=", format_scenario_label(1, queue[0]))

    def test_format_runway_summary_keeps_queue_labels_narrow(self) -> None:
        self.assertEqual(format_runway_summary(("10L",)), "RWY 10L")
        self.assertEqual(format_runway_summary(("10L", "10R")), "RWY 10L/10R")
        self.assertEqual(format_runway_summary(("10L", "10R", "28L", "28R", "D4-15L")), "RWY 10L/10R/+3")
        self.assertEqual(format_runway_summary(()), "RWY *")

    def test_order_export_excludes_aircraft_airport_runway_report_format_and_saves_conditions(self) -> None:
        original = (
            PerformanceFormValues(
                aircraft_code="777F",
                airport_code="ZGGG",
                runways=("02L",),
                anti_icing="1 发动机",
                temperature_range="45:31:1",
                wind_range="-5,0,15",
                qnh_ref="1008",
                thrust_option=THRUST_DERATE_20,
                describe_qnh_ref=False,
                runway_condition="DRY",
                bleed="ON",
                manual_report_template_id="777f_derate",
            ),
        )
        exported = export_order_items(original)
        loaded = apply_order_items(
            PerformanceFormValues(
                aircraft_code="777F",
                airport_code="ZBAA",
                runways=("18L",),
                anti_icing="0 关",
                temperature_range="SHOULD_NOT_USE",
                wind_range="SHOULD_NOT_USE",
                qnh_ref="SHOULD_NOT_USE",
                thrust_option=THRUST_NORMAL,
                manual_report_template_id="777f_normal",
            ),
            exported,
        )
        request = build_performance_request(loaded[0])

        self.assertEqual(
            exported,
            [
                {
                    "runway_condition": "DRY",
                    "contamination_depth": "",
                    "thrust_option": THRUST_DERATE_20,
                    "derate": "",
                    "bleed": "ON",
                    "anti_icing": "1",
                    "temperature_range": "45:31:1",
                    "wind_range": "-5,0,15",
                    "qnh_ref": "1008",
                    "describe_qnh_ref": "false",
                }
            ],
        )
        self.assertEqual(request.airport_code, "ZBAA")
        self.assertEqual(request.runways, ("18L",))
        self.assertEqual(request.thrust_option, THRUST_DERATE_20)
        self.assertEqual(request.derate, "")
        self.assertEqual(request.bleed, "ON")
        self.assertEqual(request.anti_icing, "1")
        self.assertEqual(request.temperature_range, "45:31:1")
        self.assertEqual(request.wind_range, "-5,0,15")
        self.assertEqual(request.qnh_ref, "1008")
        self.assertFalse(request.describe_qnh_ref)
        self.assertEqual(request.manual_report_template_id, "777f_normal")

    def test_legacy_order_without_saved_conditions_uses_current_form_conditions(self) -> None:
        loaded = apply_order_items(
            PerformanceFormValues(
                aircraft_code="777F",
                airport_code="ZBAA",
                runways=("18L",),
                anti_icing="0 关",
                temperature_range="60:30:5",
                wind_range="-10,0,10",
                qnh_ref="1013",
                thrust_option=THRUST_NORMAL,
            ),
            [{"runway_condition": "DRY", "contamination_depth": "", "thrust_option": THRUST_NORMAL, "bleed": "ON", "anti_icing": "0"}],
        )
        request = build_performance_request(loaded[0])

        self.assertEqual(request.temperature_range, "60:30:5")
        self.assertEqual(request.wind_range, "-10,0,10")
        self.assertEqual(request.qnh_ref, "1013")
        self.assertTrue(request.describe_qnh_ref)

    def test_build_performance_request_keeps_qnh_describe_choice(self) -> None:
        request = build_performance_request(
            PerformanceFormValues(
                aircraft_code="738",
                airport_code="EGNX",
                runways=("09",),
                anti_icing="0 OFF",
                temperature_range="",
                wind_range="",
                qnh_ref="1012",
                thrust_option=THRUST_NORMAL,
                describe_qnh_ref=False,
            )
        )

        self.assertFalse(request.describe_qnh_ref)

    def test_airport_import_file_dialog_includes_lowercase_rwy(self) -> None:
        fake_dpg = FakeDpgWithFileDialog()
        app = STASDesktopApp.__new__(STASDesktopApp)
        app.dpg = fake_dpg

        app._build_airport_import_file_dialog()

        self.assertTrue(fake_dpg.does_item_exist(AIRPORT_IMPORT_FILE_DIALOG))
        self.assertIn(".RWY", fake_dpg.extensions)
        self.assertIn(".rwy", fake_dpg.extensions)
        self.assertIn(".STX", fake_dpg.extensions)
        self.assertIn(".stx", fake_dpg.extensions)

    def test_airport_import_path_suffix_is_case_insensitive(self) -> None:
        self.assertTrue(is_supported_airport_import_path("IMPORT.RWY"))
        self.assertTrue(is_supported_airport_import_path("IMPORT.rwy"))
        self.assertTrue(is_supported_airport_import_path("IMPORT.StX"))
        self.assertFalse(is_supported_airport_import_path("IMPORT.txt"))

    def test_single_point_flap_defaults_when_aircraft_changes(self) -> None:
        fake_dpg = FakeDpg({SINGLE_POINT_FLAP_COMBO: "FLAP 5"})
        app = STASDesktopApp.__new__(STASDesktopApp)
        app.dpg = fake_dpg

        app._configure_single_point_flap_combo("777F", force_default=True)

        self.assertEqual(fake_dpg.get_value(SINGLE_POINT_FLAP_COMBO), "FLAP 15")
        self.assertEqual(fake_dpg.configured[SINGLE_POINT_FLAP_COMBO]["items"], ["FLAP 5", "FLAP 15", "FLAP 20"])

    def test_reset_single_point_page_restores_defaults_and_clears_results(self) -> None:
        fake_dpg = FakeDpg(
            {
                SINGLE_POINT_AIRCRAFT_COMBO: "777F",
                SINGLE_POINT_AIRPORT_COMBO: "ZBAA",
                SINGLE_POINT_RUNWAY_GROUP: True,
                SINGLE_POINT_RUNWAY_MIN_TORA_ENABLED_CHECKBOX: True,
                SINGLE_POINT_RUNWAY_MIN_TORA_INPUT: "3000",
                SINGLE_POINT_WEIGHT_INPUT: "190000",
                SINGLE_POINT_OAT_INPUT: "30",
                SINGLE_POINT_WIND_INPUT: "10",
                SINGLE_POINT_QNH_INPUT: "1000",
                SINGLE_POINT_RUNWAY_CONDITION_COMBO: "WET 湿跑道",
                SINGLE_POINT_CONTAMINATION_DEPTH_INPUT: "3",
                SINGLE_POINT_IMPROVED_CLIMB_CHECKBOX: False,
                SINGLE_POINT_ATM_MODE_COMBO: "指定假设温度",
                SINGLE_POINT_ASSUMED_TEMP_INPUT: "55",
                SINGLE_POINT_ANTI_ICING_COMBO: "3 发动机+机翼",
                SINGLE_POINT_BLEED_COMBO: "OFF 关",
                SINGLE_POINT_THRUST_COMBO: "1L1BUMP",
                SINGLE_POINT_FLAP_COMBO: "FLAP 20",
                SINGLE_POINT_RESULT_TEXT: "old result",
                SINGLE_POINT_RUNWAY_DISTANCE_TEXT: "old distance",
            }
        )
        app = STASDesktopApp.__new__(STASDesktopApp)
        app.dpg = fake_dpg
        app.context = SimpleNamespace(
            aircraft_registry=AircraftRegistry.from_directory(ROOT_DIR / "config" / "aircraft"),
            runway_dataset=RunwayDataset.from_airports(
                [AirportRunways("ZBAA", (Runway("18L", "RWYU", tora_m=3200),))]
            ),
        )
        app.aircraft_codes = ("738", "777F")
        app.airport_codes = ("ZBAA",)
        app.single_point_runway_checkbox_tags = {}
        app.last_single_point_result = object()
        app.last_single_point_elapsed_seconds = 1.0
        app.last_single_point_display_section = "ATM"
        app.primary_button_theme = None
        app.secondary_button_theme = None

        app.reset_single_point_page()

        self.assertEqual(fake_dpg.get_value(SINGLE_POINT_AIRCRAFT_COMBO), "738")
        self.assertEqual(fake_dpg.get_value(SINGLE_POINT_FLAP_COMBO), "FLAP 5")
        self.assertEqual(fake_dpg.get_value(SINGLE_POINT_WEIGHT_INPUT), "")
        self.assertEqual(fake_dpg.get_value(SINGLE_POINT_OAT_INPUT), "25")
        self.assertEqual(fake_dpg.get_value(SINGLE_POINT_WIND_INPUT), "0")
        self.assertEqual(fake_dpg.get_value(SINGLE_POINT_RUNWAY_MIN_TORA_ENABLED_CHECKBOX), False)
        self.assertEqual(fake_dpg.get_value(SINGLE_POINT_IMPROVED_CLIMB_CHECKBOX), True)
        self.assertEqual(fake_dpg.get_value(SINGLE_POINT_ATM_MODE_COMBO), "最大假设温度")
        self.assertEqual(fake_dpg.get_value(SINGLE_POINT_ASSUMED_TEMP_INPUT), "")
        self.assertEqual(fake_dpg.get_value(SINGLE_POINT_RESULT_TEXT), "")
        self.assertEqual(fake_dpg.get_value(SINGLE_POINT_RUNWAY_DISTANCE_TEXT), "")
        self.assertIsNone(app.last_single_point_result)
        self.assertIsNone(app.last_single_point_elapsed_seconds)
        self.assertEqual(app.last_single_point_display_section, "FULL")

    def test_runway_bulk_selection_buttons_update_current_airport_checkboxes(self) -> None:
        fake_dpg = FakeDpg({"rwy_18l": False, "rwy_36r": True, "missing": True})
        app = STASDesktopApp.__new__(STASDesktopApp)
        app.dpg = fake_dpg
        app.runway_checkbox_tags = {"18L": "rwy_18l", "36R": "rwy_36r", "09": "missing_tag"}

        app._set_runway_selection("all")
        self.assertTrue(fake_dpg.values["rwy_18l"])
        self.assertTrue(fake_dpg.values["rwy_36r"])

        app._set_runway_selection("none")
        self.assertFalse(fake_dpg.values["rwy_18l"])
        self.assertFalse(fake_dpg.values["rwy_36r"])

        app._set_runway_selection("invert")
        self.assertTrue(fake_dpg.values["rwy_18l"])
        self.assertTrue(fake_dpg.values["rwy_36r"])

    def test_runway_filter_uses_minimum_tora(self) -> None:
        runways = (
            Runway("18L", "RWYU", tora_m=3200, is_intersection=False),
            Runway("A1-18L", "RWYU", tora_m=3100, is_intersection=True),
            Runway("B2-18L", "RWYU", tora_m=2400, is_intersection=True),
        )

        self.assertEqual(
            tuple(runway.identifier for runway in filter_runways_for_display(runways, minimum_tora_m=2500)),
            ("18L", "A1-18L"),
        )
        self.assertEqual(
            tuple(runway.identifier for runway in filter_runways_for_display(runways)),
            ("18L", "A1-18L", "B2-18L"),
        )

    def test_manual_template_none_option_disables_manual_report(self) -> None:
        fake_dpg = FakeDpg({MANUAL_TEMPLATE_COMBO: MANUAL_TEMPLATE_NONE_LABEL})
        app = STASDesktopApp.__new__(STASDesktopApp)
        app.dpg = fake_dpg
        app.manual_template_id_by_label = {
            MANUAL_TEMPLATE_NONE_LABEL: "",
            "738 正常": "738_normal",
        }

        self.assertEqual(app._selected_manual_template_id(), "")

        fake_dpg.set_value(MANUAL_TEMPLATE_COMBO, "738 正常")
        self.assertEqual(app._selected_manual_template_id(), "738_normal")

    def test_selected_report_date_override_uses_aviation_month(self) -> None:
        fake_dpg = FakeDpg(
            {
                REPORT_DATE_OVERRIDE_CHECKBOX: True,
                REPORT_DATE_DAY_COMBO: "19",
                REPORT_DATE_MONTH_COMBO: "MAY",
                REPORT_DATE_YEAR_INPUT: 2026,
            }
        )
        app = STASDesktopApp.__new__(STASDesktopApp)
        app.dpg = fake_dpg

        self.assertEqual(app._selected_report_date_override(), "19-MAY-2026")

        fake_dpg.set_value(REPORT_DATE_OVERRIDE_CHECKBOX, False)
        self.assertEqual(app._selected_report_date_override(), "")

    def test_queue_items_use_current_report_date_override(self) -> None:
        fake_dpg = FakeDpg(
            {
                MANUAL_TEMPLATE_COMBO: MANUAL_TEMPLATE_NONE_LABEL,
                REPORT_DATE_OVERRIDE_CHECKBOX: True,
                REPORT_DATE_DAY_COMBO: "04",
                REPORT_DATE_MONTH_COMBO: "APR",
                REPORT_DATE_YEAR_INPUT: 2026,
            }
        )
        app = STASDesktopApp.__new__(STASDesktopApp)
        app.dpg = fake_dpg
        app.manual_template_id_by_label = {MANUAL_TEMPLATE_NONE_LABEL: ""}
        values = PerformanceFormValues(
            aircraft_code="738",
            airport_code="ZBAA",
            runways=("18L",),
            anti_icing="0 OFF",
            temperature_range="",
            wind_range="",
            qnh_ref="",
            thrust_option=THRUST_NORMAL,
            report_date_override="19-MAY-2026",
        )

        updated = app._with_current_report_template(values)

        self.assertEqual(updated.report_date_override, "04-APR-2026")

    def test_legacy_derate_order_loads_as_777f_thrust_option(self) -> None:
        loaded = apply_order_items(
            PerformanceFormValues(
                aircraft_code="777F",
                airport_code="ZBAA",
                runways=("18L",),
                anti_icing="0 OFF",
                temperature_range="",
                wind_range="",
                qnh_ref="",
                thrust_option=THRUST_NORMAL,
            ),
            [{"runway_condition": "DRY", "contamination_depth": "", "derate": "20", "bleed": "ON", "anti_icing": "0"}],
        )
        request = build_performance_request(loaded[0])

        self.assertEqual(loaded[0].thrust_option, THRUST_DERATE_20)
        self.assertEqual(request.thrust_option, THRUST_DERATE_20)
        self.assertEqual(request.derate, "")

    def test_738_legacy_derate_order_is_forced_to_normal_thrust(self) -> None:
        loaded = apply_order_items(
            PerformanceFormValues(
                aircraft_code="738",
                airport_code="ZBAA",
                runways=("18L",),
                anti_icing="0 OFF",
                temperature_range="",
                wind_range="",
                qnh_ref="",
                thrust_option=THRUST_NORMAL,
            ),
            [{"runway_condition": "DRY", "contamination_depth": "", "derate": "20", "bleed": "AUTO", "anti_icing": "0"}],
        )
        request = build_performance_request(loaded[0])

        self.assertEqual(display_thrust_option("738", loaded[0].thrust_option), THRUST_NORMAL)
        self.assertIsNone(request.thrust_option)
        self.assertEqual(request.derate, "")

    def test_request_thrust_option_keeps_777f_and_ignores_738(self) -> None:
        self.assertEqual(request_thrust_option("777F", "1L1BUMP"), "1L1BUMP")
        self.assertIsNone(request_thrust_option("738", THRUST_NORMAL))

    def test_default_temperature_uses_anti_icing_and_777f_bump_rules(self) -> None:
        self.assertEqual(default_temperature_range("738", "1 发动机开启", "", "65:50:5"), "10:-10:2")
        self.assertEqual(default_temperature_range("777F", "0 关闭", "1L1BUMP", "65:45:5"), "45:31:1")
        self.assertEqual(default_temperature_range("738", "0 关闭", "", "65:50:5"), "65:50:5")

    def test_runway_condition_depth_helpers_follow_contamination_rules(self) -> None:
        self.assertTrue(runway_condition_requires_depth("STANDING_WATER 积水"))
        self.assertTrue(runway_condition_requires_depth("SLUSH 雪浆"))
        self.assertTrue(runway_condition_requires_depth("DRY_SNOW 干雪"))
        self.assertFalse(runway_condition_requires_depth("DRY 干跑道"))
        self.assertFalse(runway_condition_requires_depth("WET 湿跑道"))
        self.assertIn("1.27-12.70 mm", contamination_depth_hint("STANDING_WATER 积水"))
        self.assertIn("1.27-101.60 mm", contamination_depth_hint("DRY_SNOW 干雪"))

    def test_format_result_summary_includes_success_paths_and_warnings(self) -> None:
        run_dir = Path("output/run")
        result = PerformanceCalculationResult(
            status="success",
            request=PerformanceRequest("738", "EGNX"),
            stas_run=StasRunResult(
                status="success",
                run_dir=run_dir,
                input_path=run_dir / "STASINP",
                raw_output_path=run_dir / "STASOUT.out",
                metadata_path=run_dir / "run_metadata.json",
            ),
            word_report=ReportExportResult(status="success", output_path=run_dir / "STASOUT.docx"),
            pdf_report=ReportExportResult(status="error", output_path=run_dir / "STASOUT.pdf", error_message="pdf failed"),
            warnings=("PDF report was not generated",),
        )

        summary = format_result_summary(result)

        self.assertIn("计算完成", summary)
        self.assertIn("STASOUT.out", summary)
        self.assertIn("STASOUT.docx", summary)
        self.assertIn("临时起飞分析 PDF 失败: pdf failed", summary)
        self.assertIn("警告: PDF report was not generated", summary)

    def test_run_desktop_identifies_missing_dearpygui_dependency(self) -> None:
        self.assertTrue(is_missing_dearpygui_error(ModuleNotFoundError(name="dearpygui")))
        self.assertTrue(is_missing_dearpygui_error(ModuleNotFoundError(name="dearpygui.dearpygui")))
        self.assertFalse(is_missing_dearpygui_error(ModuleNotFoundError(name="pythoncom")))
        self.assertIn("python -m pip install dearpygui", dearpygui_missing_message())

    def test_run_desktop_uses_repository_root_when_not_frozen(self) -> None:
        self.assertEqual(runtime_base_dir(), ROOT_DIR)


if __name__ == "__main__":
    unittest.main()
