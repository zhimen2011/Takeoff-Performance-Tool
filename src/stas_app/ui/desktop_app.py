"""DearPyGui desktop application for STAS performance calculations."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import os
import queue
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any

from stas_app.exporters.queue_report import QueueReportExporter
from stas_app.exporters.word_report import WordReportExporter
from stas_app.models.report import QueueReportResult
from stas_app.models.result import PerformanceCalculationResult
from stas_app.models.runway import Runway
from stas_app.models.single_point import SinglePointCalculationResult
from stas_app.models.runway_import import (
    RUNWAY_IMPORT_ACTION_ADD,
    RUNWAY_IMPORT_ACTION_OVERWRITE,
    RUNWAY_IMPORT_ACTION_SKIP,
    RUNWAY_IMPORT_OVERWRITE_EXISTING,
    RUNWAY_IMPORT_SKIP_EXISTING,
    RunwayImportPreview,
)
from stas_app.services.app_factory import ApplicationContext, create_application_context
from stas_app.storage.config_repository import load_app_config
from stas_app.storage.scenario_order_store import ScenarioOrderStore
from stas_app.ui.forms import (
    PerformanceFormValues,
    apply_order_items,
    build_default_order_form_values,
    build_performance_request,
    aircraft_supports_thrust_options,
    contamination_depth_hint,
    default_temperature_range,
    export_order_items,
    format_queue_report_summary,
    format_scenario_label,
    format_result_summary,
    recommended_manual_report_template_id,
    THRUST_NORMAL,
    runway_condition_requires_depth,
)
from stas_app.ui.single_point_forms import (
    ATM_MODE_FIXED_LABEL,
    ATM_MODE_MAX_LABEL,
    SinglePointFormValues,
    build_single_point_request,
    format_single_point_result,
    format_single_point_runway_distance,
)
from stas_app.utils.aviation_date import AVIATION_MONTHS, format_aviation_date


ANTI_ICING_OPTIONS = ("0 关闭", "1 发动机开启", "3 发动机+机翼开启")

ANTI_ICING_OPTIONS_BY_AIRCRAFT = {
    "777F": (
        "0 关",
        "1 发动机",
        "3 发动机+机翼",
        "8 发动机自动",
        "10 发动机+机翼自动",
        "11 发动机开+机翼自动",
    ),
    "738": (
        "0 关",
        "1 发动机",
        "3 发动机+机翼 标准",
        "7 发动机+机翼 可选",
    ),
}
RUNWAY_CONDITION_OPTIONS = (
    "DRY 干跑道",
    "WET 湿跑道",
    "STANDING_WATER 积水",
    "SLUSH 雪浆",
    "COMPACTED_SNOW 压实雪",
    "DRY_SNOW 干雪",
    "WET_ICE 湿冰",
    "ADVISORY_WET 湿跑道-咨询",
)
BLEED_OPTIONS_BY_AIRCRAFT = {
    "777F": ("DEFAULT 默认", "ON 开", "OFF 关", "APU_TO_PACK APU供气"),
    "738": ("DEFAULT 默认", "AUTO 自动", "OFF 关", "V1MCG_OFF V1MCG时关"),
}

SINGLE_POINT_FLAP_OPTIONS_BY_AIRCRAFT = {
    "777F": ("FLAP 5", "FLAP 15", "FLAP 20"),
    "738": ("FLAP 1", "FLAP 5", "FLAP 10", "FLAP 15", "FLAP 25"),
}
SINGLE_POINT_DEFAULT_FLAP_BY_AIRCRAFT = {
    "777F": "FLAP 15",
    "738": "FLAP 5",
}

MAIN_WINDOW = "stas_main_window"
MESSAGE_MODAL = "stas_message_modal"
PERFORMANCE_PAGE_GROUP = "stas_performance_page_group"
SINGLE_POINT_PAGE_GROUP = "stas_single_point_page_group"
AIRCRAFT_COMBO = "stas_aircraft_combo"
AIRPORT_COMBO = "stas_airport_combo"
RUNWAY_GROUP = "stas_runway_group"
RUNWAY_MIN_TORA_ENABLED_CHECKBOX = "stas_runway_min_tora_enabled_checkbox"
RUNWAY_MIN_TORA_INPUT = "stas_runway_min_tora_input"
AIRPORT_IMPORT_PATH_INPUT = "stas_airport_import_path_input"
AIRPORT_IMPORT_MODE_COMBO = "stas_airport_import_mode_combo"
AIRPORT_IMPORT_PREVIEW_TEXT = "stas_airport_import_preview_text"
AIRPORT_IMPORT_FILE_DIALOG = "stas_airport_import_file_dialog"
ANTI_ICING_COMBO = "stas_anti_icing_combo"
RUNWAY_CONDITION_COMBO = "stas_runway_condition_combo"
CONTAMINATION_DEPTH_INPUT = "stas_contamination_depth_input"
CONTAMINATION_DEPTH_HINT = "stas_contamination_depth_hint"
BLEED_COMBO = "stas_bleed_combo"
THRUST_COMBO = "stas_thrust_combo"
MANUAL_TEMPLATE_COMBO = "stas_manual_template_combo"
REPORT_DATE_OVERRIDE_CHECKBOX = "stas_report_date_override_checkbox"
REPORT_DATE_GROUP = "stas_report_date_group"
REPORT_DATE_DAY_COMBO = "stas_report_date_day_combo"
REPORT_DATE_MONTH_COMBO = "stas_report_date_month_combo"
REPORT_DATE_YEAR_INPUT = "stas_report_date_year_input"
AIRPORT_IMPORT_SKIP_LABEL = "跳过已存在机场"
AIRPORT_IMPORT_OVERWRITE_LABEL = "覆盖已存在机场"
TEMPERATURE_INPUT = "stas_temperature_input"
WIND_INPUT = "stas_wind_input"
QNH_INPUT = "stas_qnh_input"
QNH_DESCRIBE_CHECKBOX = "stas_qnh_describe_checkbox"
ORDER_NAME_INPUT = "stas_order_name_input"
ORDER_PRESET_COMBO = "stas_order_preset_combo"
SCENARIO_QUEUE_LIST = "stas_scenario_queue_list"
RESULT_TEXT = "stas_result_text"
STATUS_TEXT = "stas_status_text"
CALCULATE_BUTTON = "stas_calculate_button"
CALCULATE_QUEUE_BUTTON = "stas_calculate_queue_button"
SINGLE_POINT_AIRCRAFT_COMBO = "stas_single_point_aircraft_combo"
SINGLE_POINT_AIRPORT_COMBO = "stas_single_point_airport_combo"
SINGLE_POINT_RUNWAY_GROUP = "stas_single_point_runway_group"
SINGLE_POINT_RUNWAY_MIN_TORA_ENABLED_CHECKBOX = "stas_single_point_runway_min_tora_enabled_checkbox"
SINGLE_POINT_RUNWAY_MIN_TORA_INPUT = "stas_single_point_runway_min_tora_input"
SINGLE_POINT_WEIGHT_INPUT = "stas_single_point_weight_input"
SINGLE_POINT_OAT_INPUT = "stas_single_point_oat_input"
SINGLE_POINT_WIND_INPUT = "stas_single_point_wind_input"
SINGLE_POINT_QNH_INPUT = "stas_single_point_qnh_input"
SINGLE_POINT_ANTI_ICING_COMBO = "stas_single_point_anti_icing_combo"
SINGLE_POINT_THRUST_COMBO = "stas_single_point_thrust_combo"
SINGLE_POINT_BLEED_COMBO = "stas_single_point_bleed_combo"
SINGLE_POINT_FLAP_COMBO = "stas_single_point_flap_combo"
SINGLE_POINT_IMPROVED_CLIMB_CHECKBOX = "stas_single_point_improved_climb_checkbox"
SINGLE_POINT_RUNWAY_CONDITION_COMBO = "stas_single_point_runway_condition_combo"
SINGLE_POINT_CONTAMINATION_DEPTH_INPUT = "stas_single_point_contamination_depth_input"
SINGLE_POINT_CONTAMINATION_DEPTH_HINT = "stas_single_point_contamination_depth_hint"
SINGLE_POINT_ATM_MODE_COMBO = "stas_single_point_atm_mode_combo"
SINGLE_POINT_ASSUMED_TEMP_INPUT = "stas_single_point_assumed_temp_input"
SINGLE_POINT_CALCULATE_BUTTON = "stas_single_point_calculate_button"
SINGLE_POINT_RESULT_TEXT = "stas_single_point_result_text"
SINGLE_POINT_RUNWAY_DISTANCE_TEXT = "stas_single_point_runway_distance_text"
SINGLE_POINT_FULL_RESULT_BUTTON = "stas_single_point_full_result_button"
SINGLE_POINT_ATM_RESULT_BUTTON = "stas_single_point_atm_result_button"
RESULT_TEMPORARY_REPORT_COMBO = "stas_result_temporary_report_combo"
RESULT_MANUAL_REPORT_COMBO = "stas_result_manual_report_combo"
MANUAL_TEMPLATE_NONE_LABEL = "不生成手册格式"
TEMPORARY_REPORT_MENU_LABEL = "临时报告"
MANUAL_REPORT_MENU_LABEL = "手册报告"
REPORT_MENU_WORD_ACTION = "打开 Word"
REPORT_MENU_PDF_ACTION = "打开 PDF"
SUPPORTED_AIRPORT_IMPORT_SUFFIXES = {".rwy", ".stx"}
AIRPORT_IMPORT_MODE_BY_LABEL = {
    AIRPORT_IMPORT_SKIP_LABEL: RUNWAY_IMPORT_SKIP_EXISTING,
    AIRPORT_IMPORT_OVERWRITE_LABEL: RUNWAY_IMPORT_OVERWRITE_EXISTING,
}
AIRPORT_IMPORT_ACTION_LABELS = {
    RUNWAY_IMPORT_ACTION_ADD: "新增",
    RUNWAY_IMPORT_ACTION_OVERWRITE: "覆盖",
    RUNWAY_IMPORT_ACTION_SKIP: "跳过",
}


def filter_runways_for_display(
    runways: tuple[Runway, ...],
    minimum_tora_m: float | None = None,
) -> tuple[Runway, ...]:
    """Return runways visible under the UI filter controls."""

    visible: list[Runway] = []
    for runway in runways:
        if minimum_tora_m is not None and (runway.tora_m is None or runway.tora_m < minimum_tora_m):
            continue
        visible.append(runway)
    return tuple(visible)


def is_supported_airport_import_path(path: str | Path) -> bool:
    """Return whether an airport import file extension is supported by the UI."""

    return Path(path).suffix.lower() in SUPPORTED_AIRPORT_IMPORT_SUFFIXES


def load_desktop_context(config_path: str | Path = "config/app.local.toml", base_dir: str | Path = ".") -> ApplicationContext:
    """Load application config and build services for the desktop UI."""

    config = load_app_config(config_path, base_dir=base_dir)
    return create_application_context(config)


def launch_desktop_app(config_path: str | Path = "config/app.local.toml", base_dir: str | Path = ".") -> None:
    """Launch the DearPyGui desktop application."""

    dpg = _load_dearpygui()
    dpg.create_context()
    try:
        _bind_chinese_font(dpg)
        try:
            context = load_desktop_context(config_path, base_dir)
        except Exception as exc:
            _show_startup_error(dpg, exc)
            return

        STASDesktopApp(dpg, context).run()
    finally:
        dpg.destroy_context()


class STASDesktopApp:
    """Desktop UI shell that delegates calculations to PerformanceService."""

    def __init__(self, dpg: ModuleType, context: ApplicationContext) -> None:
        self.dpg = dpg
        self.context = context
        self.last_result: PerformanceCalculationResult | None = None
        self.last_results: tuple[PerformanceCalculationResult, ...] = ()
        self.last_queue_report: QueueReportResult | None = None
        self.last_single_point_result: SinglePointCalculationResult | None = None
        self.last_single_point_elapsed_seconds: float | None = None
        self.last_single_point_display_section = "FULL"
        self.last_single_point_aircraft_code = ""
        self.ui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.runway_checkbox_tags: dict[str, str] = {}
        self.single_point_runway_checkbox_tags: dict[str, str] = {}
        self.order_store = ScenarioOrderStore(context.config.output_root / "scenario_orders.json")
        self.queue_report_exporter = self._create_queue_report_exporter()
        self.scenario_queue: list[PerformanceFormValues] = []
        self.selected_scenario_index: int | None = None
        self.is_calculating = False
        self.last_airport_import_preview: RunwayImportPreview | None = None
        self.primary_button_theme: Any = None
        self.secondary_button_theme: Any = None
        self.danger_button_theme: Any = None

        self.manual_template_id_by_label = {MANUAL_TEMPLATE_NONE_LABEL: ""}
        self.manual_template_id_by_label.update({template.label: template.id for template in context.manual_report_templates})
        self.manual_template_label_by_id = {template.id: template.label for template in context.manual_report_templates}
        self.aircraft_codes = self.context.aircraft_registry.supported_codes()
        self.airport_codes = self.context.runway_dataset.airport_codes()

        self._build_layout()
        self._load_initial_values()

    def run(self) -> None:
        """Run the DearPyGui event loop and process worker-thread results."""

        dpg = self.dpg
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window(MAIN_WINDOW, True)

        while dpg.is_dearpygui_running():
            self._drain_ui_queue()
            dpg.render_dearpygui_frame()

    def _build_layout(self) -> None:
        dpg = self.dpg
        self._build_button_themes()
        dpg.create_viewport(title="STAS Takeoff Performance Tool", width=1220, height=900, min_width=1080, min_height=780)

        with dpg.window(label="STAS Takeoff Performance Tool", tag=MAIN_WINDOW):
            with dpg.group(horizontal=True):
                self._add_button("报告/队列计算", 128, self.show_performance_page, self.primary_button_theme)
                self._add_button("单点计算", 104, self.show_single_point_page, self.secondary_button_theme)

            dpg.add_separator()
            with dpg.group(tag=PERFORMANCE_PAGE_GROUP):
                with dpg.group(horizontal=True):
                    with dpg.child_window(width=400, height=-38, border=True):
                        self._build_input_section()

                    with dpg.child_window(width=-1, height=-38, border=True):
                        self._build_report_output_section()
                        dpg.add_separator()
                        self._build_saved_order_section()
                        dpg.add_separator()
                        self._build_queue_section()
                        dpg.add_separator()
                        self._build_result_section()

            with dpg.group(tag=SINGLE_POINT_PAGE_GROUP, show=False):
                self._build_single_point_page()

            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_text("就绪", tag=STATUS_TEXT)

        self._build_airport_import_file_dialog()

    def show_performance_page(self) -> None:
        if self.dpg.does_item_exist(PERFORMANCE_PAGE_GROUP):
            self.dpg.configure_item(PERFORMANCE_PAGE_GROUP, show=True)
        if self.dpg.does_item_exist(SINGLE_POINT_PAGE_GROUP):
            self.dpg.configure_item(SINGLE_POINT_PAGE_GROUP, show=False)
        self._set_status("报告/队列计算")

    def show_single_point_page(self) -> None:
        if self.dpg.does_item_exist(PERFORMANCE_PAGE_GROUP):
            self.dpg.configure_item(PERFORMANCE_PAGE_GROUP, show=False)
        if self.dpg.does_item_exist(SINGLE_POINT_PAGE_GROUP):
            self.dpg.configure_item(SINGLE_POINT_PAGE_GROUP, show=True)
        self._set_status("单点计算")

    def _build_single_point_page(self) -> None:
        dpg = self.dpg
        with dpg.child_window(width=-1, height=430, border=True):
            self._build_single_point_input_section()

        dpg.add_spacer(height=8)
        with dpg.child_window(width=-1, height=-38, border=True):
            self._build_single_point_result_section()

    def _build_single_point_input_section(self) -> None:
        self._build_single_point_input_grid()

    def _build_single_point_input_grid(self) -> None:
        dpg = self.dpg
        with dpg.group(horizontal=True):
            dpg.add_text("单点计算")
            dpg.add_spacer(width=16)
            self._add_button("计算", 82, self.calculate_single_point, self.primary_button_theme, tag=SINGLE_POINT_CALCULATE_BUTTON)
            self._add_button("重置", 72, self.reset_single_point_page)
        dpg.add_separator()

        with dpg.group(horizontal=True):
            with dpg.group(width=360):
                dpg.add_text("ARPT")
                dpg.add_combo(
                    list(self.airport_codes),
                    tag=SINGLE_POINT_AIRPORT_COMBO,
                    width=-1,
                    callback=self._on_single_point_airport_changed,
                )

                dpg.add_spacer(height=4)
                dpg.add_text("RWY 过滤")
                with dpg.group(horizontal=True):
                    dpg.add_checkbox(
                        label="最小 TORA",
                        tag=SINGLE_POINT_RUNWAY_MIN_TORA_ENABLED_CHECKBOX,
                        callback=self._on_single_point_runway_filter_enabled_changed,
                    )
                    dpg.add_input_text(
                        tag=SINGLE_POINT_RUNWAY_MIN_TORA_INPUT,
                        hint="m",
                        width=-1,
                        enabled=False,
                        callback=self._on_single_point_runway_filter_changed,
                    )

                dpg.add_spacer(height=4)
                dpg.add_text("RWY")
                with dpg.child_window(tag=SINGLE_POINT_RUNWAY_GROUP, width=-1, height=170, border=True):
                    dpg.add_text("请先选择机场")

            dpg.add_spacer(width=12)
            with dpg.group(width=285):
                dpg.add_text("PROFILE")
                dpg.add_combo(
                    list(self.aircraft_codes),
                    tag=SINGLE_POINT_AIRCRAFT_COMBO,
                    width=-1,
                    callback=self._on_single_point_aircraft_changed,
                )

                dpg.add_spacer(height=4)
                dpg.add_text("TOW KG")
                dpg.add_input_text(tag=SINGLE_POINT_WEIGHT_INPUT, width=-1)

                dpg.add_spacer(height=4)
                dpg.add_text("OAT C")
                dpg.add_input_text(tag=SINGLE_POINT_OAT_INPUT, width=-1, default_value="25")

                dpg.add_spacer(height=4)
                dpg.add_text("WIND KT")
                dpg.add_input_text(tag=SINGLE_POINT_WIND_INPUT, width=-1, default_value="0")

                dpg.add_spacer(height=4)
                dpg.add_text("QNH")
                dpg.add_input_text(tag=SINGLE_POINT_QNH_INPUT, width=-1)

                dpg.add_spacer(height=4)
                dpg.add_text("COND")
                dpg.add_combo(
                    list(RUNWAY_CONDITION_OPTIONS),
                    default_value=RUNWAY_CONDITION_OPTIONS[0],
                    tag=SINGLE_POINT_RUNWAY_CONDITION_COMBO,
                    width=-1,
                    callback=self._on_single_point_runway_condition_changed,
                )
                dpg.add_input_text(tag=SINGLE_POINT_CONTAMINATION_DEPTH_INPUT, hint="污染深度 mm", width=-1)
                dpg.add_text("", tag=SINGLE_POINT_CONTAMINATION_DEPTH_HINT, wrap=260)

            dpg.add_spacer(width=12)
            with dpg.group(width=285):
                dpg.add_text("FLAP")
                dpg.add_combo([], tag=SINGLE_POINT_FLAP_COMBO, width=-1)

                dpg.add_spacer(height=4)
                dpg.add_checkbox(label="使用改进爬升", tag=SINGLE_POINT_IMPROVED_CLIMB_CHECKBOX, default_value=True)

                dpg.add_spacer(height=4)
                dpg.add_text("A/I")
                dpg.add_combo(list(ANTI_ICING_OPTIONS), default_value=ANTI_ICING_OPTIONS[0], tag=SINGLE_POINT_ANTI_ICING_COMBO, width=-1)

                dpg.add_spacer(height=4)
                dpg.add_text("THRUST")
                dpg.add_combo([], tag=SINGLE_POINT_THRUST_COMBO, width=-1, enabled=False)

                dpg.add_spacer(height=4)
                dpg.add_text("A/C")
                dpg.add_combo([], tag=SINGLE_POINT_BLEED_COMBO, width=-1)

                dpg.add_spacer(height=4)
                dpg.add_text("ATM")
                dpg.add_combo(
                    [ATM_MODE_MAX_LABEL, ATM_MODE_FIXED_LABEL],
                    default_value=ATM_MODE_MAX_LABEL,
                    tag=SINGLE_POINT_ATM_MODE_COMBO,
                    width=-1,
                    callback=self._on_single_point_atm_mode_changed,
                )
                dpg.add_input_text(
                    tag=SINGLE_POINT_ASSUMED_TEMP_INPUT,
                    hint="指定假设温度 C",
                    width=-1,
                    enabled=False,
                )

    def _build_single_point_result_section(self) -> None:
        self._build_single_point_result_panel()

    def _build_single_point_result_panel(self) -> None:
        dpg = self.dpg
        dpg.add_text("单点计算结果")
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            self._add_button("FULL", 82, self.show_single_point_full_result, self.primary_button_theme, tag=SINGLE_POINT_FULL_RESULT_BUTTON)
            self._add_button("ATM", 82, self.show_single_point_atm_result, self.secondary_button_theme, tag=SINGLE_POINT_ATM_RESULT_BUTTON)
            self._add_button("输出目录", 96, self.open_single_point_output_dir, self.secondary_button_theme)
            self._add_button("重置", 72, self.reset_single_point_page)
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True):
            with dpg.child_window(width=720, height=-1, border=True):
                dpg.add_input_text(
                    tag=SINGLE_POINT_RESULT_TEXT,
                    multiline=True,
                    readonly=True,
                    width=-1,
                    height=-1,
                )
            with dpg.child_window(width=-1, height=-1, border=True):
                dpg.add_input_text(
                    tag=SINGLE_POINT_RUNWAY_DISTANCE_TEXT,
                    multiline=True,
                    readonly=True,
                    width=-1,
                    height=-1,
                )

    def _build_input_section(self) -> None:
        dpg = self.dpg
        dpg.add_text("飞行参数")
        dpg.add_separator()

        dpg.add_text("机型")
        dpg.add_combo(list(self.aircraft_codes), tag=AIRCRAFT_COMBO, width=-1, callback=self._on_aircraft_changed)

        dpg.add_spacer(height=6)
        dpg.add_text("机场")
        dpg.add_combo(list(self.airport_codes), tag=AIRPORT_COMBO, width=-1, callback=self._on_airport_changed)

        dpg.add_spacer(height=6)
        dpg.add_text("跑道过滤")
        with dpg.group(horizontal=True):
            dpg.add_checkbox(
                label="启用",
                tag=RUNWAY_MIN_TORA_ENABLED_CHECKBOX,
                callback=self._on_runway_filter_enabled_changed,
            )
            dpg.add_input_text(
                tag=RUNWAY_MIN_TORA_INPUT,
                hint="最小 TORA m",
                width=-1,
                enabled=False,
                callback=self._on_runway_filter_changed,
            )

        dpg.add_spacer(height=6)
        dpg.add_text("跑道")
        with dpg.child_window(tag=RUNWAY_GROUP, width=-1, height=94, border=True):
            dpg.add_text("请先选择机场")
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            self._add_button("全选", 70, self.select_all_runways, self.secondary_button_theme)
            self._add_button("全不选", 82, self.clear_runway_selection, self.secondary_button_theme)
            self._add_button("反选", 70, self.invert_runway_selection, self.secondary_button_theme)

        dpg.add_spacer(height=8)
        dpg.add_separator()
        with dpg.collapsing_header(label="机场跑道数据管理", default_open=False):
            self._build_airport_import_section()

        dpg.add_spacer(height=8)
        dpg.add_separator()
        dpg.add_text("基础计算条件")

        dpg.add_spacer(height=4)
        dpg.add_text("QNH")
        dpg.add_input_text(tag=QNH_INPUT, width=-1)
        dpg.add_checkbox(label="输出中标注 QNHREF", tag=QNH_DESCRIBE_CHECKBOX, default_value=True)

        dpg.add_spacer(height=4)
        dpg.add_text("温度范围")
        dpg.add_input_text(tag=TEMPERATURE_INPUT, width=-1)

        dpg.add_spacer(height=4)
        dpg.add_text("风速范围")
        dpg.add_input_text(tag=WIND_INPUT, width=-1)

        dpg.add_spacer(height=8)
        dpg.add_separator()
        dpg.add_text("当前输出顺序项")

        dpg.add_spacer(height=4)
        dpg.add_text("防冰（顺序项）")
        dpg.add_combo(
            list(ANTI_ICING_OPTIONS),
            default_value=ANTI_ICING_OPTIONS[0],
            tag=ANTI_ICING_COMBO,
            width=-1,
            callback=self._on_defaults_changed,
        )

        dpg.add_spacer(height=4)
        dpg.add_text("推力（顺序项）")
        dpg.add_combo([], tag=THRUST_COMBO, width=-1, callback=self._on_defaults_changed, enabled=False)

        dpg.add_spacer(height=4)
        dpg.add_text("引气 / 空调（顺序项）")
        dpg.add_combo([], tag=BLEED_COMBO, width=-1)

        dpg.add_spacer(height=4)
        dpg.add_text("道面条件（顺序项）")
        dpg.add_combo(
            list(RUNWAY_CONDITION_OPTIONS),
            default_value=RUNWAY_CONDITION_OPTIONS[0],
            tag=RUNWAY_CONDITION_COMBO,
            width=-1,
            callback=self._on_runway_condition_changed,
        )

        dpg.add_spacer(height=4)
        dpg.add_text("污染深度 mm（随道面条件）")
        dpg.add_input_text(tag=CONTAMINATION_DEPTH_INPUT, width=-1)
        dpg.add_text("", tag=CONTAMINATION_DEPTH_HINT, wrap=360)

    def _build_airport_import_section(self) -> None:
        dpg = self.dpg
        dpg.add_text("机场数据导入")
        dpg.add_text("支持 .RWY / .rwy / .stx，文件后缀大小写不敏感", wrap=360)
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            self._add_button("选择文件...", 104, self.open_airport_import_dialog, self.primary_button_theme)
            dpg.add_input_text(
                tag=AIRPORT_IMPORT_PATH_INPUT,
                hint="尚未选择机场数据文件",
                width=-1,
                readonly=True,
            )
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            self._add_button("预览", 58, self.preview_airport_import, self.secondary_button_theme)
            dpg.add_combo(
                list(AIRPORT_IMPORT_MODE_BY_LABEL),
                default_value=AIRPORT_IMPORT_SKIP_LABEL,
                tag=AIRPORT_IMPORT_MODE_COMBO,
                width=130,
            )
            self._add_button("导入", 58, self.import_airport_data, self.primary_button_theme)
        dpg.add_spacer(height=4)
        dpg.add_input_text(
            tag=AIRPORT_IMPORT_PREVIEW_TEXT,
            multiline=True,
            readonly=True,
            width=-1,
            height=72,
        )

    def _build_report_output_section(self) -> None:
        dpg = self.dpg
        dpg.add_text("报告输出")
        dpg.add_spacer(height=4)
        dpg.add_text("手册起飞分析格式")
        dpg.add_combo(
            list(self.manual_template_id_by_label),
            default_value=MANUAL_TEMPLATE_NONE_LABEL,
            tag=MANUAL_TEMPLATE_COMBO,
            width=-1,
        )
        today = date.today()
        dpg.add_spacer(height=6)
        dpg.add_checkbox(
            label="自定义报告日期",
            tag=REPORT_DATE_OVERRIDE_CHECKBOX,
            default_value=False,
            callback=self._on_report_date_override_changed,
        )
        with dpg.group(horizontal=True, tag=REPORT_DATE_GROUP, show=False):
            dpg.add_combo(
                [f"{day:02d}" for day in range(1, 32)],
                default_value=f"{today.day:02d}",
                tag=REPORT_DATE_DAY_COMBO,
                width=56,
            )
            dpg.add_combo(
                list(AVIATION_MONTHS),
                default_value=AVIATION_MONTHS[today.month - 1],
                tag=REPORT_DATE_MONTH_COMBO,
                width=68,
            )
            dpg.add_input_int(
                tag=REPORT_DATE_YEAR_INPUT,
                default_value=today.year,
                width=86,
                min_value=1900,
                max_value=2100,
                min_clamped=True,
                max_clamped=True,
                step=0,
                step_fast=0,
            )
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True):
            self._add_button("加入当前顺序项", 132, self.add_current_scenario, self.secondary_button_theme)
            self._add_button("加入默认四项", 112, self.load_default_scenario_order, self.secondary_button_theme)
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            self._add_button("只算当前", 96, self.calculate_performance, self.primary_button_theme, tag=CALCULATE_BUTTON)
            self._add_button("重置", 64, self.reset_form)

    def _build_saved_order_section(self) -> None:
        dpg = self.dpg
        dpg.add_text("已保存队列方案（不含机型/机场/跑道/报告格式）")
        dpg.add_input_text(tag=ORDER_NAME_INPUT, hint="输入顺序名称", width=-1)
        dpg.add_combo([], tag=ORDER_PRESET_COMBO, width=-1)
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            self._add_button("保存队列", 92, self.save_current_order, self.primary_button_theme)
            self._add_button("加载队列", 92, self.load_selected_order, self.secondary_button_theme)
            self._add_button("删除方案", 92, self.delete_selected_order, self.danger_button_theme)

    def _build_queue_section(self) -> None:
        dpg = self.dpg
        dpg.add_text("当前输出顺序")
        dpg.add_listbox([], tag=SCENARIO_QUEUE_LIST, num_items=6, width=-1, callback=self._on_scenario_selected)

        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            self._add_button("上移", 56, self.move_selected_scenario_up)
            self._add_button("下移", 56, self.move_selected_scenario_down)
            self._add_button("删除", 76, self.remove_selected_scenario, self.danger_button_theme)
            self._add_button("清空队列", 100, self.clear_scenario_queue, self.danger_button_theme)
            self._add_button("执行队列", 96, self.calculate_scenario_queue, self.primary_button_theme, tag=CALCULATE_QUEUE_BUTTON)

    def _build_result_section(self) -> None:
        dpg = self.dpg
        dpg.add_text("计算结果")
        with dpg.group(horizontal=True):
            dpg.add_button(label="原始输出", width=96, callback=self.open_raw_output)
            dpg.add_combo(
                [REPORT_MENU_WORD_ACTION, REPORT_MENU_PDF_ACTION],
                default_value=TEMPORARY_REPORT_MENU_LABEL,
                tag=RESULT_TEMPORARY_REPORT_COMBO,
                width=112,
                callback=self._on_result_report_menu_selected,
                user_data=TEMPORARY_REPORT_MENU_LABEL,
            )
            dpg.add_combo(
                [REPORT_MENU_WORD_ACTION, REPORT_MENU_PDF_ACTION],
                default_value=MANUAL_REPORT_MENU_LABEL,
                tag=RESULT_MANUAL_REPORT_COMBO,
                width=112,
                callback=self._on_result_report_menu_selected,
                user_data=MANUAL_REPORT_MENU_LABEL,
            )
            self._add_button("输出目录", 96, self.open_output_dir, self.secondary_button_theme)
            dpg.add_button(label="清除结果", width=96, callback=self.clear_results)

        dpg.add_spacer(height=8)
        dpg.add_input_text(
            tag=RESULT_TEXT,
            multiline=True,
            readonly=True,
            width=-1,
            height=-1,
        )

    def _add_button(
        self,
        label: str,
        width: int,
        callback: Any,
        theme: Any | None = None,
        tag: str | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {}
        if tag is not None:
            kwargs["tag"] = tag

        button = self.dpg.add_button(label=label, width=width, callback=callback, **kwargs)
        if theme is not None:
            self.dpg.bind_item_theme(button, theme)
        return button

    def _build_airport_import_file_dialog(self) -> None:
        dpg = self.dpg
        try:
            with dpg.file_dialog(
                label="选择机场数据文件",
                directory_selector=False,
                show=False,
                callback=self._on_airport_import_file_selected,
                tag=AIRPORT_IMPORT_FILE_DIALOG,
                modal=True,
                width=840,
                height=540,
            ):
                dpg.add_file_extension(".RWY", color=(80, 180, 120, 255), custom_text="RWY airport data")
                dpg.add_file_extension(".rwy", color=(80, 180, 120, 255), custom_text="RWY airport data")
                dpg.add_file_extension(".STX", color=(80, 180, 120, 255), custom_text="STX airport data")
                dpg.add_file_extension(".stx", color=(80, 180, 120, 255), custom_text="STX airport data")
                dpg.add_file_extension(".*", custom_text="All files")
        except Exception:
            return

    def _create_queue_report_exporter(self) -> QueueReportExporter:
        config = self.context.config
        return QueueReportExporter(
            config.output_root,
            word_exporter=WordReportExporter(config.manual_report_template_dir),
            manual_word_exporter=self.context.manual_report_exporter,
            logo_path=config.logo_path,
            word_report_filename=config.queue_word_report_filename,
            pdf_report_filename=config.queue_pdf_report_filename,
            manual_word_report_filename=config.queue_manual_word_report_filename,
            manual_pdf_report_filename=config.queue_manual_pdf_report_filename,
        )

    def _build_button_themes(self) -> None:
        dpg = self.dpg
        try:
            with dpg.theme() as primary_theme:
                with dpg.theme_component(dpg.mvButton):
                    dpg.add_theme_color(dpg.mvThemeCol_Button, (32, 112, 182), category=dpg.mvThemeCat_Core)
                    dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (46, 132, 210), category=dpg.mvThemeCat_Core)
                    dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (24, 90, 150), category=dpg.mvThemeCat_Core)

            with dpg.theme() as secondary_theme:
                with dpg.theme_component(dpg.mvButton):
                    dpg.add_theme_color(dpg.mvThemeCol_Button, (72, 82, 96), category=dpg.mvThemeCat_Core)
                    dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (88, 100, 118), category=dpg.mvThemeCat_Core)
                    dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (56, 66, 78), category=dpg.mvThemeCat_Core)

            with dpg.theme() as danger_theme:
                with dpg.theme_component(dpg.mvButton):
                    dpg.add_theme_color(dpg.mvThemeCol_Button, (170, 64, 54), category=dpg.mvThemeCat_Core)
                    dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (198, 78, 66), category=dpg.mvThemeCat_Core)
                    dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (138, 50, 44), category=dpg.mvThemeCat_Core)
        except Exception:
            self.primary_button_theme = None
            self.secondary_button_theme = None
            self.danger_button_theme = None
            return

        self.primary_button_theme = primary_theme
        self.secondary_button_theme = secondary_theme
        self.danger_button_theme = danger_theme

    def _load_initial_values(self) -> None:
        if self.aircraft_codes:
            self.dpg.set_value(AIRCRAFT_COMBO, self.aircraft_codes[0])
        self._on_aircraft_changed()
        self._on_runway_condition_changed()
        self._load_single_point_initial_values()
        self._render_scenario_queue()
        self._refresh_order_presets()
        self._append_result("请选择机场、跑道和计算参数。\n")

    def _load_single_point_initial_values(self) -> None:
        if not self.dpg.does_item_exist(SINGLE_POINT_AIRCRAFT_COMBO):
            return
        if self.aircraft_codes:
            self.dpg.set_value(SINGLE_POINT_AIRCRAFT_COMBO, self.aircraft_codes[0])
        if self.airport_codes:
            self.dpg.set_value(SINGLE_POINT_AIRPORT_COMBO, self.airport_codes[0])
        self._on_single_point_aircraft_changed()
        self._on_single_point_airport_changed()
        self._on_single_point_runway_condition_changed()
        self._on_single_point_atm_mode_changed()

    def _on_aircraft_changed(self, sender: str | None = None, app_data: Any = None, user_data: Any = None) -> None:
        dpg = self.dpg
        aircraft_code = dpg.get_value(AIRCRAFT_COMBO)
        if not aircraft_code and self.aircraft_codes:
            aircraft_code = self.aircraft_codes[0]
            dpg.set_value(AIRCRAFT_COMBO, aircraft_code)

        aircraft = self.context.aircraft_registry.get(aircraft_code)
        thrust_value = dpg.get_value(THRUST_COMBO) or ""
        self._configure_aircraft_specific_combos(aircraft.code)

        if aircraft.supports_thrust_options:
            thrust_values = tuple(option.label for option in aircraft.thrust_options)
            if thrust_value not in thrust_values:
                thrust_value = thrust_values[0] if thrust_values else ""
            dpg.configure_item(THRUST_COMBO, items=list(thrust_values), enabled=True)
            dpg.set_value(THRUST_COMBO, thrust_value)
        else:
            thrust_value = THRUST_NORMAL
            dpg.configure_item(THRUST_COMBO, items=[THRUST_NORMAL], enabled=False)
            dpg.set_value(THRUST_COMBO, THRUST_NORMAL)

        dpg.set_value(
            TEMPERATURE_INPUT,
            default_temperature_range(aircraft.code, dpg.get_value(ANTI_ICING_COMBO), thrust_value, aircraft.default_temperature_range),
        )
        dpg.set_value(WIND_INPUT, aircraft.default_wind_range)
        dpg.set_value(QNH_INPUT, aircraft.default_qnh)
        dpg.set_value(QNH_DESCRIBE_CHECKBOX, True)
        self._set_recommended_manual_template()

    def _on_single_point_aircraft_changed(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        dpg = self.dpg
        aircraft_code = dpg.get_value(SINGLE_POINT_AIRCRAFT_COMBO)
        if not aircraft_code and self.aircraft_codes:
            aircraft_code = self.aircraft_codes[0]
            dpg.set_value(SINGLE_POINT_AIRCRAFT_COMBO, aircraft_code)

        aircraft = self.context.aircraft_registry.get(aircraft_code)
        aircraft_key = aircraft.code.strip().upper()
        aircraft_changed = aircraft_key != getattr(self, "last_single_point_aircraft_code", "")
        self._configure_single_point_aircraft_specific_combos(aircraft.code)
        self._configure_single_point_flap_combo(aircraft.code, force_default=aircraft_changed)
        thrust_value = dpg.get_value(SINGLE_POINT_THRUST_COMBO) or ""

        if aircraft.supports_thrust_options:
            thrust_values = tuple(option.label for option in aircraft.thrust_options)
            if thrust_value not in thrust_values:
                thrust_value = thrust_values[0] if thrust_values else ""
            dpg.configure_item(SINGLE_POINT_THRUST_COMBO, items=list(thrust_values), enabled=True)
            dpg.set_value(SINGLE_POINT_THRUST_COMBO, thrust_value)
        else:
            dpg.configure_item(SINGLE_POINT_THRUST_COMBO, items=[THRUST_NORMAL], enabled=False)
            dpg.set_value(SINGLE_POINT_THRUST_COMBO, THRUST_NORMAL)

        dpg.set_value(SINGLE_POINT_QNH_INPUT, aircraft.default_qnh)
        self.last_single_point_aircraft_code = aircraft_key

    def _on_single_point_airport_changed(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        airport = (self.dpg.get_value(SINGLE_POINT_AIRPORT_COMBO) or "").strip().upper()
        self.dpg.set_value(SINGLE_POINT_AIRPORT_COMBO, airport)
        self._render_single_point_runways()

    def _on_single_point_runway_filter_changed(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        self._render_single_point_runways()

    def _on_single_point_runway_filter_enabled_changed(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        enabled = bool(self.dpg.get_value(SINGLE_POINT_RUNWAY_MIN_TORA_ENABLED_CHECKBOX))
        self.dpg.configure_item(SINGLE_POINT_RUNWAY_MIN_TORA_INPUT, enabled=enabled)
        self._render_single_point_runways()

    def _on_single_point_runway_condition_changed(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        runway_condition = self.dpg.get_value(SINGLE_POINT_RUNWAY_CONDITION_COMBO) or ""
        requires_depth = runway_condition_requires_depth(runway_condition)
        if not requires_depth:
            self.dpg.set_value(SINGLE_POINT_CONTAMINATION_DEPTH_INPUT, "")
        self.dpg.configure_item(SINGLE_POINT_CONTAMINATION_DEPTH_INPUT, enabled=requires_depth)
        if self.dpg.does_item_exist(SINGLE_POINT_CONTAMINATION_DEPTH_HINT):
            self.dpg.set_value(SINGLE_POINT_CONTAMINATION_DEPTH_HINT, contamination_depth_hint(runway_condition))

    def _on_single_point_atm_mode_changed(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        mode = self.dpg.get_value(SINGLE_POINT_ATM_MODE_COMBO) or ATM_MODE_MAX_LABEL
        self.dpg.configure_item(SINGLE_POINT_ASSUMED_TEMP_INPUT, enabled=mode == ATM_MODE_FIXED_LABEL)

    def _on_defaults_changed(self, sender: str | None = None, app_data: Any = None, user_data: Any = None) -> None:
        aircraft = self.context.aircraft_registry.get(self.dpg.get_value(AIRCRAFT_COMBO))
        self.dpg.set_value(
            TEMPERATURE_INPUT,
            default_temperature_range(
                aircraft.code,
                self.dpg.get_value(ANTI_ICING_COMBO),
                self.dpg.get_value(THRUST_COMBO) or "",
                aircraft.default_temperature_range,
            ),
        )
        self._set_recommended_manual_template()

    def _on_report_date_override_changed(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        if not self.dpg.does_item_exist(REPORT_DATE_GROUP):
            return

        enabled = bool(self.dpg.get_value(REPORT_DATE_OVERRIDE_CHECKBOX))
        self.dpg.configure_item(REPORT_DATE_GROUP, show=enabled)

    def _on_runway_condition_changed(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        runway_condition = self.dpg.get_value(RUNWAY_CONDITION_COMBO) or ""
        requires_depth = runway_condition_requires_depth(runway_condition)
        if not requires_depth:
            self.dpg.set_value(CONTAMINATION_DEPTH_INPUT, "")

        self.dpg.configure_item(CONTAMINATION_DEPTH_INPUT, enabled=requires_depth)
        if self.dpg.does_item_exist(CONTAMINATION_DEPTH_HINT):
            self.dpg.set_value(CONTAMINATION_DEPTH_HINT, contamination_depth_hint(runway_condition))

    def _on_airport_changed(self, sender: str | None = None, app_data: Any = None, user_data: Any = None) -> None:
        airport = (self.dpg.get_value(AIRPORT_COMBO) or "").strip().upper()
        self.dpg.set_value(AIRPORT_COMBO, airport)
        self._render_current_airport_runway_options()

    def _on_runway_filter_changed(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        self._render_current_airport_runway_options()

    def _on_runway_filter_enabled_changed(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        enabled = bool(self.dpg.get_value(RUNWAY_MIN_TORA_ENABLED_CHECKBOX))
        self.dpg.configure_item(RUNWAY_MIN_TORA_INPUT, enabled=enabled)
        self._render_current_airport_runway_options()

    def reset_form(self) -> None:
        self.dpg.set_value(AIRPORT_COMBO, "")
        self.dpg.set_value(RUNWAY_MIN_TORA_ENABLED_CHECKBOX, False)
        self.dpg.set_value(RUNWAY_MIN_TORA_INPUT, "")
        self.dpg.configure_item(RUNWAY_MIN_TORA_INPUT, enabled=False)
        self.dpg.set_value(RUNWAY_CONDITION_COMBO, RUNWAY_CONDITION_OPTIONS[0])
        self.dpg.set_value(CONTAMINATION_DEPTH_INPUT, "")
        self.dpg.set_value(QNH_DESCRIBE_CHECKBOX, True)
        self._on_runway_condition_changed()
        self.clear_scenario_queue()
        self._render_runway_options(())
        self._on_aircraft_changed()
        self.clear_results()
        self._append_result("参数已重置。\n")
        self._set_status("就绪")

    def open_airport_import_dialog(self) -> None:
        if self.dpg.does_item_exist(AIRPORT_IMPORT_FILE_DIALOG):
            if hasattr(self.dpg, "show_item"):
                self.dpg.show_item(AIRPORT_IMPORT_FILE_DIALOG)
            else:
                self.dpg.configure_item(AIRPORT_IMPORT_FILE_DIALOG, show=True)
            return

        self._show_message("选择文件", "当前界面环境无法打开文件选择器，请检查 DearPyGui 文件选择器是否可用。")

    def preview_airport_import(self) -> None:
        source_path = self._airport_import_source_path()
        if source_path is None:
            self._show_message("无法预览", "请先选择外部 .RWY / .rwy / .stx 文件。")
            return

        try:
            preview = self.context.runway_import_service.preview_import(source_path, self._selected_airport_import_mode())
        except Exception as exc:
            self.last_airport_import_preview = None
            self._set_airport_import_preview_text(f"预览失败: {exc}")
            self._show_message("预览失败", str(exc))
            return

        self.last_airport_import_preview = preview
        self._set_airport_import_preview_text(self._format_airport_import_preview(preview))
        self._set_status("机场导入预览完成")

    def import_airport_data(self) -> None:
        source_path = self._airport_import_source_path()
        if source_path is None:
            self._show_message("无法导入", "请先选择外部 .RWY / .rwy / .stx 文件。")
            return

        try:
            result = self.context.runway_import_service.import_airports(source_path, self._selected_airport_import_mode())
        except Exception as exc:
            self._show_message("导入失败", str(exc))
            self._append_result(f"机场导入失败: {exc}\n")
            return

        self.last_airport_import_preview = result.preview
        self._set_airport_import_preview_text(self._format_airport_import_preview(result.preview))
        if not result.written:
            self._show_message("无需导入", "没有需要写入主库的机场；可能全部为已存在机场并选择了跳过。")
            self._append_result("机场导入未写入：没有需要新增或覆盖的机场。\n")
            return

        try:
            selected_airport = result.imported_codes[0] if result.imported_codes else ""
            self._reload_context_after_airport_import(selected_airport)
        except Exception as exc:
            self._show_message("导入已完成", f"主库已写入，但刷新界面失败: {exc}")
            self._append_result(f"机场导入完成，但刷新界面失败: {exc}\n")
            return

        backup_text = f"，备份: {result.backup_path}" if result.backup_path else ""
        message = (
            f"机场导入完成：新增 {result.preview.add_count}，"
            f"覆盖 {result.preview.overwrite_count}，跳过 {result.preview.skip_count}{backup_text}"
        )
        self._append_result(message + "\n")
        self._set_status("机场导入完成")
        self._show_message("导入完成", message)

    def calculate_performance(self) -> None:
        if self.is_calculating:
            return

        request = build_performance_request(self._collect_form_values())
        self.last_queue_report = None
        self.clear_results()
        self._append_result("开始计算...\n")
        self._set_calculating(True)

        def run_calculation() -> None:
            started = time.perf_counter()
            try:
                result = self.context.performance_service.calculate(request)
            except Exception as exc:
                elapsed = time.perf_counter() - started
                self.ui_queue.put(("calculation_error", (exc, elapsed)))
                return

            elapsed = time.perf_counter() - started
            self.ui_queue.put(("calculation_result", (result, elapsed)))

        threading.Thread(target=run_calculation, daemon=True).start()

    def calculate_single_point(self) -> None:
        if self.is_calculating:
            return

        try:
            request = build_single_point_request(self._collect_single_point_form_values())
        except Exception as exc:
            self._show_message("单点计算失败", str(exc))
            self._append_single_point_result(f"单点计算失败: {exc}\n")
            return

        self.last_single_point_result = None
        self.clear_single_point_result()
        self._append_single_point_result("开始单点计算...\n")
        self._set_calculating(True)

        def run_single_point() -> None:
            started = time.perf_counter()
            try:
                result = self.context.single_point_service.calculate(request)
            except Exception as exc:
                elapsed = time.perf_counter() - started
                self.ui_queue.put(("single_point_error", (exc, elapsed)))
                return

            elapsed = time.perf_counter() - started
            self.ui_queue.put(("single_point_result", (result, elapsed)))

        threading.Thread(target=run_single_point, daemon=True).start()

    def calculate_scenario_queue(self) -> None:
        if self.is_calculating:
            return

        if not self.scenario_queue:
            self._show_message("队列为空", "请先加入当前顺序项、加载保存方案，或点击加入默认四项。")
            return

        requests = [
            build_performance_request(self._with_current_report_template(values))
            for values in self.scenario_queue
        ]
        self.last_queue_report = None
        self.clear_results()
        self._append_result(f"开始执行队列：{len(requests)} 条\n")
        self._set_calculating(True)

        def run_queue() -> None:
            started = time.perf_counter()
            results: list[PerformanceCalculationResult] = []
            try:
                for index, request in enumerate(requests, start=1):
                    self.ui_queue.put(
                        ("queue_progress", f"正在计算 {index}/{len(requests)}：{request.scenario_id or request.runway_condition}\n")
                    )
                    results.append(self.context.performance_service.calculate(request))
            except Exception as exc:
                elapsed = time.perf_counter() - started
                self.ui_queue.put(("calculation_error", (exc, elapsed)))
                return

            queue_report = self.queue_report_exporter.export(tuple(results))
            elapsed = time.perf_counter() - started
            self.ui_queue.put(("queue_result", (tuple(results), queue_report, elapsed)))

        threading.Thread(target=run_queue, daemon=True).start()

    def add_current_scenario(self) -> None:
        values = self._collect_form_values()
        if not values.scenario_id:
            values = self._with_scenario_id(values, len(self.scenario_queue) + 1)
        self.scenario_queue.append(values)
        self.selected_scenario_index = len(self.scenario_queue) - 1
        self._render_scenario_queue()

    def load_default_scenario_order(self) -> None:
        self.scenario_queue = list(build_default_order_form_values(self._collect_form_values()))
        self.selected_scenario_index = 0 if self.scenario_queue else None
        self._render_scenario_queue()

    def save_current_order(self) -> None:
        name = (self.dpg.get_value(ORDER_NAME_INPUT) or self.dpg.get_value(ORDER_PRESET_COMBO) or "").strip()
        if not self.scenario_queue:
            self._show_message("队列为空", "当前没有可保存的顺序。")
            return

        try:
            self.order_store.save_order(name, export_order_items(self.scenario_queue))
        except Exception as exc:
            self._show_message("保存失败", str(exc))
            return

        self._refresh_order_presets(selected=name)
        self._show_message("保存完成", f"队列方案已保存：{name}")

    def load_selected_order(self) -> None:
        name = (self.dpg.get_value(ORDER_PRESET_COMBO) or self.dpg.get_value(ORDER_NAME_INPUT) or "").strip()
        orders = self.order_store.load_all()
        if name not in orders:
            self._show_message("加载失败", "请选择一个已保存的队列方案。")
            return

        self.scenario_queue = list(apply_order_items(self._collect_form_values(), orders[name]))
        self.selected_scenario_index = 0 if self.scenario_queue else None
        self._render_scenario_queue()
        self.dpg.set_value(ORDER_NAME_INPUT, name)
        self._show_message("加载完成", f"已加载队列方案：{name}")

    def delete_selected_order(self) -> None:
        name = (self.dpg.get_value(ORDER_PRESET_COMBO) or self.dpg.get_value(ORDER_NAME_INPUT) or "").strip()
        if not name:
            self._show_message("删除失败", "请选择一个队列方案。")
            return

        self.order_store.delete_order(name)
        self._refresh_order_presets()
        self._show_message("删除完成", f"队列方案已删除：{name}")

    def move_selected_scenario_up(self) -> None:
        index = self.selected_scenario_index
        if index is None or index <= 0:
            return
        self.scenario_queue[index - 1], self.scenario_queue[index] = self.scenario_queue[index], self.scenario_queue[index - 1]
        self.selected_scenario_index = index - 1
        self._render_scenario_queue()

    def move_selected_scenario_down(self) -> None:
        index = self.selected_scenario_index
        if index is None or index >= len(self.scenario_queue) - 1:
            return
        self.scenario_queue[index + 1], self.scenario_queue[index] = self.scenario_queue[index], self.scenario_queue[index + 1]
        self.selected_scenario_index = index + 1
        self._render_scenario_queue()

    def remove_selected_scenario(self) -> None:
        index = self.selected_scenario_index
        if index is None or not 0 <= index < len(self.scenario_queue):
            return
        del self.scenario_queue[index]
        self.selected_scenario_index = min(index, len(self.scenario_queue) - 1) if self.scenario_queue else None
        self._render_scenario_queue()

    def clear_scenario_queue(self) -> None:
        self.scenario_queue = []
        self.selected_scenario_index = None
        if self.dpg.does_item_exist(SCENARIO_QUEUE_LIST):
            self._render_scenario_queue()

    def _collect_form_values(self) -> PerformanceFormValues:
        dpg = self.dpg
        runway_condition = dpg.get_value(RUNWAY_CONDITION_COMBO) or ""
        contamination_depth = ""
        if runway_condition_requires_depth(runway_condition):
            contamination_depth = dpg.get_value(CONTAMINATION_DEPTH_INPUT) or ""
        return PerformanceFormValues(
            aircraft_code=dpg.get_value(AIRCRAFT_COMBO) or "",
            airport_code=dpg.get_value(AIRPORT_COMBO) or "",
            runways=self._selected_runways(),
            anti_icing=dpg.get_value(ANTI_ICING_COMBO) or "",
            temperature_range=dpg.get_value(TEMPERATURE_INPUT) or "",
            wind_range=dpg.get_value(WIND_INPUT) or "",
            qnh_ref=dpg.get_value(QNH_INPUT) or "",
            describe_qnh_ref=(
                bool(dpg.get_value(QNH_DESCRIBE_CHECKBOX))
                if dpg.does_item_exist(QNH_DESCRIBE_CHECKBOX)
                else True
            ),
            thrust_option=dpg.get_value(THRUST_COMBO) or "",
            runway_condition=runway_condition,
            contamination_depth=contamination_depth,
            bleed=dpg.get_value(BLEED_COMBO) or "",
            derate="",
            manual_report_template_id=self._selected_manual_template_id(),
            report_date_override=self._selected_report_date_override(),
        )

    def _collect_single_point_form_values(self) -> SinglePointFormValues:
        dpg = self.dpg
        runway_condition = dpg.get_value(SINGLE_POINT_RUNWAY_CONDITION_COMBO) or ""
        contamination_depth = ""
        if runway_condition_requires_depth(runway_condition):
            contamination_depth = dpg.get_value(SINGLE_POINT_CONTAMINATION_DEPTH_INPUT) or ""
        return SinglePointFormValues(
            aircraft_code=dpg.get_value(SINGLE_POINT_AIRCRAFT_COMBO) or "",
            airport_code=dpg.get_value(SINGLE_POINT_AIRPORT_COMBO) or "",
            runway=self._selected_single_point_runway(),
            takeoff_weight_kg=dpg.get_value(SINGLE_POINT_WEIGHT_INPUT) or "",
            actual_temperature_c=dpg.get_value(SINGLE_POINT_OAT_INPUT) or "",
            wind_kt=dpg.get_value(SINGLE_POINT_WIND_INPUT) or "",
            qnh_ref=dpg.get_value(SINGLE_POINT_QNH_INPUT) or "",
            anti_icing=dpg.get_value(SINGLE_POINT_ANTI_ICING_COMBO) or "",
            thrust_option=dpg.get_value(SINGLE_POINT_THRUST_COMBO) or "",
            flap_setting=dpg.get_value(SINGLE_POINT_FLAP_COMBO) or "",
            improved_climb=bool(dpg.get_value(SINGLE_POINT_IMPROVED_CLIMB_CHECKBOX)),
            runway_condition=runway_condition,
            contamination_depth=contamination_depth,
            bleed=dpg.get_value(SINGLE_POINT_BLEED_COMBO) or "",
            derate="",
            atm_mode=dpg.get_value(SINGLE_POINT_ATM_MODE_COMBO) or ATM_MODE_MAX_LABEL,
            assumed_temperature_c=dpg.get_value(SINGLE_POINT_ASSUMED_TEMP_INPUT) or "",
        )

    def _handle_calculation_result(self, result: PerformanceCalculationResult, elapsed_seconds: float) -> None:
        self.last_result = result
        self._set_calculating(False)
        self._append_result(format_result_summary(result))
        self._append_result(f"总耗时: {elapsed_seconds:.2f} 秒\n")
        if result.succeeded:
            self._set_status(f"计算完成，用时 {elapsed_seconds:.2f} 秒")
            self._show_message("计算完成", "计算完成，结果已写入输出目录。")
        else:
            self._set_status("计算失败")
            self._show_message("计算失败", result.error_message or "计算失败")

    def _handle_single_point_result(
        self,
        result: SinglePointCalculationResult,
        elapsed_seconds: float,
    ) -> None:
        self.last_single_point_result = result
        self._set_calculating(False)
        self.last_single_point_elapsed_seconds = elapsed_seconds
        self.last_single_point_display_section = "FULL"
        self._render_single_point_result()
        if result.succeeded:
            self._set_status(f"单点计算完成，用时 {elapsed_seconds:.2f} 秒")
            self._show_message("单点计算完成", "单点计算完成，FULL 和 ATM 结果已生成。")
        else:
            self._set_status("单点计算失败")
            self._show_message("单点计算失败", result.error_message or "单点计算失败")

    def _handle_queue_result(
        self,
        results: tuple[PerformanceCalculationResult, ...],
        queue_report: QueueReportResult,
        elapsed_seconds: float,
    ) -> None:
        self.last_results = results
        self.last_result = results[-1] if results else None
        self.last_queue_report = queue_report
        self._set_calculating(False)

        failures = 0
        for index, result in enumerate(results, start=1):
            title = result.request.scenario_id or f"scenario_{index:02d}"
            self._append_result(f"\n[{index:02d}] {title}\n")
            self._append_result(format_result_summary(result))
            if not result.succeeded:
                failures += 1

        self._append_result(f"\n队列总耗时: {elapsed_seconds:.2f} 秒\n")
        self._append_result(format_queue_report_summary(queue_report))
        if failures:
            self._set_status(f"队列完成，失败 {failures} 条")
            self._show_message("队列完成", f"{len(results) - failures} 条成功，{failures} 条失败。")
        else:
            self._set_status(f"队列完成：{len(results)} 条")
            self._show_message("队列完成", "队列内所有计算已完成。")

    def _handle_calculation_error(self, exc: Exception, elapsed_seconds: float) -> None:
        self._set_calculating(False)
        self.last_result = None
        self.last_queue_report = None
        self._append_result(f"计算异常: {exc}\n")
        self._append_result(f"总耗时: {elapsed_seconds:.2f} 秒\n")
        self._set_status("计算异常")
        self._show_message("计算异常", str(exc))

    def _handle_single_point_error(self, exc: Exception, elapsed_seconds: float) -> None:
        self._set_calculating(False)
        self.last_single_point_result = None
        self._append_single_point_result(f"单点计算异常: {exc}\n")
        self._append_single_point_result(f"总耗时: {elapsed_seconds:.2f} 秒\n")
        self._set_status("单点计算异常")
        self._show_message("单点计算异常", str(exc))

    def clear_results(self) -> None:
        self.dpg.set_value(RESULT_TEXT, "")

    def reset_single_point_page(self) -> None:
        dpg = self.dpg
        if not dpg.does_item_exist(SINGLE_POINT_AIRCRAFT_COMBO):
            return

        self.last_single_point_aircraft_code = ""
        if self.aircraft_codes:
            dpg.set_value(SINGLE_POINT_AIRCRAFT_COMBO, self.aircraft_codes[0])
        if self.airport_codes:
            dpg.set_value(SINGLE_POINT_AIRPORT_COMBO, self.airport_codes[0])

        dpg.set_value(SINGLE_POINT_RUNWAY_MIN_TORA_ENABLED_CHECKBOX, False)
        dpg.set_value(SINGLE_POINT_RUNWAY_MIN_TORA_INPUT, "")
        dpg.configure_item(SINGLE_POINT_RUNWAY_MIN_TORA_INPUT, enabled=False)
        dpg.set_value(SINGLE_POINT_WEIGHT_INPUT, "")
        dpg.set_value(SINGLE_POINT_OAT_INPUT, "25")
        dpg.set_value(SINGLE_POINT_WIND_INPUT, "0")
        dpg.set_value(SINGLE_POINT_RUNWAY_CONDITION_COMBO, RUNWAY_CONDITION_OPTIONS[0])
        dpg.set_value(SINGLE_POINT_CONTAMINATION_DEPTH_INPUT, "")
        dpg.set_value(SINGLE_POINT_IMPROVED_CLIMB_CHECKBOX, True)
        dpg.set_value(SINGLE_POINT_ATM_MODE_COMBO, ATM_MODE_MAX_LABEL)
        dpg.set_value(SINGLE_POINT_ASSUMED_TEMP_INPUT, "")

        self._on_single_point_aircraft_changed()
        self._reset_single_point_aircraft_options()
        self._on_single_point_airport_changed()
        self._on_single_point_runway_condition_changed()
        self._on_single_point_atm_mode_changed()
        self.clear_single_point_result()
        self._set_status("单点计算已重置")

    def _reset_single_point_aircraft_options(self) -> None:
        aircraft = self.context.aircraft_registry.get(self.dpg.get_value(SINGLE_POINT_AIRCRAFT_COMBO))
        anti_icing_options = self._aircraft_options(ANTI_ICING_OPTIONS_BY_AIRCRAFT, aircraft.code)
        bleed_options = self._aircraft_options(BLEED_OPTIONS_BY_AIRCRAFT, aircraft.code)
        self.dpg.set_value(SINGLE_POINT_ANTI_ICING_COMBO, anti_icing_options[0])
        self.dpg.set_value(SINGLE_POINT_BLEED_COMBO, bleed_options[0])
        self.dpg.set_value(
            SINGLE_POINT_FLAP_COMBO,
            self._aircraft_default(SINGLE_POINT_DEFAULT_FLAP_BY_AIRCRAFT, aircraft.code),
        )
        if aircraft.supports_thrust_options:
            thrust_values = tuple(option.label for option in aircraft.thrust_options)
            self.dpg.set_value(SINGLE_POINT_THRUST_COMBO, thrust_values[0] if thrust_values else "")
        else:
            self.dpg.set_value(SINGLE_POINT_THRUST_COMBO, THRUST_NORMAL)

    def clear_single_point_result(self) -> None:
        self.last_single_point_result = None
        self.last_single_point_elapsed_seconds = None
        self.last_single_point_display_section = "FULL"
        if self.dpg.does_item_exist(SINGLE_POINT_RESULT_TEXT):
            self.dpg.set_value(SINGLE_POINT_RESULT_TEXT, "")
        if self.dpg.does_item_exist(SINGLE_POINT_RUNWAY_DISTANCE_TEXT):
            self.dpg.set_value(SINGLE_POINT_RUNWAY_DISTANCE_TEXT, "")
        self._bind_single_point_result_button_themes()

    def show_single_point_full_result(self) -> None:
        self.last_single_point_display_section = "FULL"
        self._render_single_point_result()

    def show_single_point_atm_result(self) -> None:
        self.last_single_point_display_section = "ATM"
        self._render_single_point_result()

    def _render_single_point_result(self) -> None:
        if not self.dpg.does_item_exist(SINGLE_POINT_RESULT_TEXT):
            return
        self._bind_single_point_result_button_themes()
        if self.last_single_point_result is None:
            self.dpg.set_value(SINGLE_POINT_RESULT_TEXT, "")
            if self.dpg.does_item_exist(SINGLE_POINT_RUNWAY_DISTANCE_TEXT):
                self.dpg.set_value(SINGLE_POINT_RUNWAY_DISTANCE_TEXT, "")
            return
        text = format_single_point_result(self.last_single_point_result, self.last_single_point_display_section)
        if self.last_single_point_elapsed_seconds is not None:
            text += f"总耗时: {self.last_single_point_elapsed_seconds:.2f} 秒\n"
        self.dpg.set_value(SINGLE_POINT_RESULT_TEXT, text)
        if self.dpg.does_item_exist(SINGLE_POINT_RUNWAY_DISTANCE_TEXT):
            self.dpg.set_value(
                SINGLE_POINT_RUNWAY_DISTANCE_TEXT,
                format_single_point_runway_distance(
                    self.last_single_point_result,
                    self.last_single_point_display_section,
                ),
            )

    def _bind_single_point_result_button_themes(self) -> None:
        if self.dpg.does_item_exist(SINGLE_POINT_FULL_RESULT_BUTTON):
            theme = self.primary_button_theme if self.last_single_point_display_section == "FULL" else self.secondary_button_theme
            self.dpg.bind_item_theme(SINGLE_POINT_FULL_RESULT_BUTTON, theme)
        if self.dpg.does_item_exist(SINGLE_POINT_ATM_RESULT_BUTTON):
            theme = self.primary_button_theme if self.last_single_point_display_section == "ATM" else self.secondary_button_theme
            self.dpg.bind_item_theme(SINGLE_POINT_ATM_RESULT_BUTTON, theme)

    def _on_result_report_menu_selected(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        menu_label = str(user_data or "")
        action = str(app_data or "")

        if menu_label == TEMPORARY_REPORT_MENU_LABEL:
            if action == REPORT_MENU_WORD_ACTION:
                self.open_word_report()
            elif action == REPORT_MENU_PDF_ACTION:
                self.open_pdf_report()
            self.dpg.set_value(RESULT_TEMPORARY_REPORT_COMBO, TEMPORARY_REPORT_MENU_LABEL)
            return

        if menu_label == MANUAL_REPORT_MENU_LABEL:
            if action == REPORT_MENU_WORD_ACTION:
                self.open_manual_word_report()
            elif action == REPORT_MENU_PDF_ACTION:
                self.open_manual_pdf_report()
            self.dpg.set_value(RESULT_MANUAL_REPORT_COMBO, MANUAL_REPORT_MENU_LABEL)

    def open_output_dir(self) -> None:
        if self.last_queue_report and self.last_queue_report.run_dir:
            self._open_path(self.last_queue_report.run_dir)
            return
        if self.last_result and self.last_result.stas_run:
            self._open_path(self.last_result.stas_run.run_dir)
            return
        self._open_path(self.context.config.output_root)

    def open_single_point_output_dir(self) -> None:
        if self.last_single_point_result and self.last_single_point_result.atm_run:
            self._open_path(self.last_single_point_result.atm_run.run_dir)
            return
        if self.last_single_point_result and self.last_single_point_result.full_run:
            self._open_path(self.last_single_point_result.full_run.run_dir)
            return
        self._open_path(self.context.config.output_root)

    def open_raw_output(self) -> None:
        path = self.last_queue_report.merged_output_path if self.last_queue_report else None
        if path is None:
            path = self.last_result.stas_run.raw_output_path if self.last_result and self.last_result.stas_run else None
        self._open_existing_file(path, "原始输出不存在，请先完成计算")

    def open_word_report(self) -> None:
        path = (
            self.last_queue_report.word_report.output_path
            if self.last_queue_report and self.last_queue_report.word_report
            else None
        )
        if path is None:
            path = self.last_result.word_report.output_path if self.last_result and self.last_result.word_report else None
        self._open_existing_file(path, "临时起飞分析 Word 不存在或生成失败")

    def open_pdf_report(self) -> None:
        path = (
            self.last_queue_report.pdf_report.output_path
            if self.last_queue_report and self.last_queue_report.pdf_report
            else None
        )
        if path is None:
            path = self.last_result.pdf_report.output_path if self.last_result and self.last_result.pdf_report else None
        self._open_existing_file(path, "临时起飞分析 PDF 不存在或生成失败")

    def open_manual_word_report(self) -> None:
        path = (
            self.last_queue_report.manual_word_report.output_path
            if self.last_queue_report and self.last_queue_report.manual_word_report
            else None
        )
        if path is None:
            path = (
                self.last_result.manual_word_report.output_path
                if self.last_result and self.last_result.manual_word_report
                else None
            )
        self._open_existing_file(path, "手册起飞分析 Word 不存在或生成失败")

    def open_manual_pdf_report(self) -> None:
        path = (
            self.last_queue_report.manual_pdf_report.output_path
            if self.last_queue_report and self.last_queue_report.manual_pdf_report
            else None
        )
        if path is None:
            path = (
                self.last_result.manual_pdf_report.output_path
                if self.last_result and self.last_result.manual_pdf_report
                else None
            )
        self._open_existing_file(path, "手册起飞分析 PDF 不存在或生成失败")

    def select_all_runways(self) -> None:
        self._set_runway_selection("all")

    def clear_runway_selection(self) -> None:
        self._set_runway_selection("none")

    def invert_runway_selection(self) -> None:
        self._set_runway_selection("invert")

    def _render_current_airport_runway_options(self) -> None:
        airport = (self.dpg.get_value(AIRPORT_COMBO) or "").strip().upper()
        airport_runways = self.context.runway_dataset.get_airport(airport)
        if airport_runways is None:
            self._render_runway_options(())
            return

        try:
            minimum_tora = self._minimum_tora_filter()
        except ValueError as exc:
            self._render_runway_options((), empty_message=str(exc))
            self._set_status(str(exc))
            return

        self._render_runway_options(
            filter_runways_for_display(
                airport_runways.runways,
                minimum_tora_m=minimum_tora,
            ),
            empty_message="没有符合过滤条件的跑道",
        )

    def _minimum_tora_filter(self) -> float | None:
        if not bool(self.dpg.get_value(RUNWAY_MIN_TORA_ENABLED_CHECKBOX)):
            return None

        value = (self.dpg.get_value(RUNWAY_MIN_TORA_INPUT) or "").strip()
        if not value:
            raise ValueError("启用最小 TORA 过滤后请输入数值")

        try:
            minimum = float(value)
        except ValueError as exc:
            raise ValueError("最小 TORA 请输入数字") from exc

        if minimum < 0:
            raise ValueError("最小 TORA 不能小于 0")
        return minimum

    def _render_runway_options(self, runways: tuple[Runway, ...], empty_message: str = "请先选择机场") -> None:
        dpg = self.dpg
        dpg.delete_item(RUNWAY_GROUP, children_only=True)
        self.runway_checkbox_tags = {}

        if not runways:
            dpg.add_text(empty_message, parent=RUNWAY_GROUP)
            return

        for index, runway in enumerate(runways):
            tag = f"stas_runway_checkbox_{index}"
            self.runway_checkbox_tags[runway.identifier] = tag
            dpg.add_checkbox(label=self._runway_display_label(runway), tag=tag, parent=RUNWAY_GROUP)

    def _runway_display_label(self, runway: Runway) -> str:
        return runway.identifier

    def _set_runway_selection(self, mode: str) -> None:
        if not self.runway_checkbox_tags:
            self._set_status("请先选择机场")
            return

        for tag in self.runway_checkbox_tags.values():
            if not self.dpg.does_item_exist(tag):
                continue
            if mode == "all":
                value = True
            elif mode == "none":
                value = False
            elif mode == "invert":
                value = not bool(self.dpg.get_value(tag))
            else:
                raise ValueError(f"未知跑道选择模式: {mode}")
            self.dpg.set_value(tag, value)

    def _selected_runways(self) -> tuple[str, ...]:
        selected: list[str] = []
        for runway, tag in self.runway_checkbox_tags.items():
            if self.dpg.does_item_exist(tag) and self.dpg.get_value(tag):
                selected.append(runway)
        return tuple(selected)

    def _on_airport_import_file_selected(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        selected_path = self._extract_file_dialog_path(app_data)
        if not selected_path:
            return

        self.dpg.set_value(AIRPORT_IMPORT_PATH_INPUT, selected_path)
        self.preview_airport_import()

    def _extract_file_dialog_path(self, app_data: Any) -> str:
        if isinstance(app_data, dict):
            path = app_data.get("file_path_name")
            if path:
                return str(path)

            current_path = app_data.get("current_path")
            file_name = app_data.get("file_name")
            if current_path and file_name:
                return str(Path(str(current_path)) / str(file_name))

        return ""

    def _airport_import_source_path(self) -> Path | None:
        value = (self.dpg.get_value(AIRPORT_IMPORT_PATH_INPUT) or "").strip()
        if not value:
            return None
        path = Path(value).expanduser()
        if not is_supported_airport_import_path(path):
            return None
        return path

    def _selected_airport_import_mode(self) -> str:
        label = self.dpg.get_value(AIRPORT_IMPORT_MODE_COMBO) or AIRPORT_IMPORT_SKIP_LABEL
        return AIRPORT_IMPORT_MODE_BY_LABEL.get(str(label), RUNWAY_IMPORT_SKIP_EXISTING)

    def _set_airport_import_preview_text(self, text: str) -> None:
        if self.dpg.does_item_exist(AIRPORT_IMPORT_PREVIEW_TEXT):
            self.dpg.set_value(AIRPORT_IMPORT_PREVIEW_TEXT, text)

    def _format_airport_import_preview(self, preview: RunwayImportPreview) -> str:
        lines = [
            f"源文件: {preview.source_file}",
            f"主库: {preview.master_file}",
            f"机场: {len(preview.airports)}  新增: {preview.add_count}  覆盖: {preview.overwrite_count}  跳过: {preview.skip_count}",
        ]
        for airport in preview.airports[:40]:
            action = AIRPORT_IMPORT_ACTION_LABELS.get(airport.action, airport.action)
            exists = "已存在" if airport.exists_in_master else "新机场"
            runways = ",".join(airport.runway_ids) if airport.runway_ids else "-"
            lines.append(f"{airport.icao} [{exists}] {action} 跑道{airport.runway_count}: {runways}")

        if len(preview.airports) > 40:
            lines.append(f"... 还有 {len(preview.airports) - 40} 个机场未显示")

        return "\n".join(lines)

    def _reload_context_after_airport_import(self, selected_airport: str = "") -> None:
        current_airport = (self.dpg.get_value(AIRPORT_COMBO) or "").strip().upper()
        self.context = create_application_context(self.context.config)
        self.queue_report_exporter = self._create_queue_report_exporter()
        self.aircraft_codes = self.context.aircraft_registry.supported_codes()
        self.airport_codes = self.context.runway_dataset.airport_codes()
        self.dpg.configure_item(AIRCRAFT_COMBO, items=list(self.aircraft_codes))
        self.dpg.configure_item(AIRPORT_COMBO, items=list(self.airport_codes))

        target_airport = selected_airport.strip().upper() or current_airport
        if target_airport not in self.airport_codes:
            target_airport = current_airport if current_airport in self.airport_codes else ""

        self.dpg.set_value(AIRPORT_COMBO, target_airport)
        self._on_airport_changed()
        if self.dpg.does_item_exist(SINGLE_POINT_AIRCRAFT_COMBO):
            self.dpg.configure_item(SINGLE_POINT_AIRCRAFT_COMBO, items=list(self.aircraft_codes))
            self.dpg.configure_item(SINGLE_POINT_AIRPORT_COMBO, items=list(self.airport_codes))
            if target_airport in self.airport_codes:
                self.dpg.set_value(SINGLE_POINT_AIRPORT_COMBO, target_airport)
            self._on_single_point_aircraft_changed()
            self._on_single_point_airport_changed()

    def _configure_aircraft_specific_combos(self, aircraft_code: str) -> None:
        anti_icing_options = self._aircraft_options(ANTI_ICING_OPTIONS_BY_AIRCRAFT, aircraft_code)
        anti_icing_value = self.dpg.get_value(ANTI_ICING_COMBO) or ""
        if anti_icing_value not in anti_icing_options:
            anti_icing_value = anti_icing_options[0]
        self.dpg.configure_item(ANTI_ICING_COMBO, items=list(anti_icing_options))
        self.dpg.set_value(ANTI_ICING_COMBO, anti_icing_value)

        bleed_options = self._aircraft_options(BLEED_OPTIONS_BY_AIRCRAFT, aircraft_code)
        bleed_value = self.dpg.get_value(BLEED_COMBO) or ""
        if bleed_value not in bleed_options:
            bleed_value = bleed_options[0]
        self.dpg.configure_item(BLEED_COMBO, items=list(bleed_options))
        self.dpg.set_value(BLEED_COMBO, bleed_value)

    def _configure_single_point_aircraft_specific_combos(self, aircraft_code: str) -> None:
        anti_icing_options = self._aircraft_options(ANTI_ICING_OPTIONS_BY_AIRCRAFT, aircraft_code)
        anti_icing_value = self.dpg.get_value(SINGLE_POINT_ANTI_ICING_COMBO) or ""
        if anti_icing_value not in anti_icing_options:
            anti_icing_value = anti_icing_options[0]
        self.dpg.configure_item(SINGLE_POINT_ANTI_ICING_COMBO, items=list(anti_icing_options))
        self.dpg.set_value(SINGLE_POINT_ANTI_ICING_COMBO, anti_icing_value)

        bleed_options = self._aircraft_options(BLEED_OPTIONS_BY_AIRCRAFT, aircraft_code)
        bleed_value = self.dpg.get_value(SINGLE_POINT_BLEED_COMBO) or ""
        if bleed_value not in bleed_options:
            bleed_value = bleed_options[0]
        self.dpg.configure_item(SINGLE_POINT_BLEED_COMBO, items=list(bleed_options))
        self.dpg.set_value(SINGLE_POINT_BLEED_COMBO, bleed_value)

    def _configure_single_point_flap_combo(self, aircraft_code: str, force_default: bool = False) -> None:
        flap_options = self._aircraft_options(SINGLE_POINT_FLAP_OPTIONS_BY_AIRCRAFT, aircraft_code)
        default_flap = self._aircraft_default(SINGLE_POINT_DEFAULT_FLAP_BY_AIRCRAFT, aircraft_code)
        current = self.dpg.get_value(SINGLE_POINT_FLAP_COMBO) or ""
        if force_default or current not in flap_options:
            current = default_flap
        self.dpg.configure_item(SINGLE_POINT_FLAP_COMBO, items=list(flap_options))
        self.dpg.set_value(SINGLE_POINT_FLAP_COMBO, current)

    def _render_single_point_runways(self) -> None:
        airport = (self.dpg.get_value(SINGLE_POINT_AIRPORT_COMBO) or "").strip().upper()
        airport_runways = self.context.runway_dataset.get_airport(airport)
        if airport_runways is None:
            self._render_single_point_runway_options(())
            return

        try:
            minimum_tora = self._single_point_minimum_tora_filter()
        except ValueError as exc:
            self._render_single_point_runway_options((), empty_message=str(exc))
            self._set_status(str(exc))
            return

        self._render_single_point_runway_options(
            filter_runways_for_display(
                airport_runways.runways,
                minimum_tora_m=minimum_tora,
            ),
            empty_message="没有符合过滤条件的跑道",
        )

    def _single_point_minimum_tora_filter(self) -> float | None:
        if not bool(self.dpg.get_value(SINGLE_POINT_RUNWAY_MIN_TORA_ENABLED_CHECKBOX)):
            return None

        value = (self.dpg.get_value(SINGLE_POINT_RUNWAY_MIN_TORA_INPUT) or "").strip()
        if not value:
            raise ValueError("启用最小 TORA 过滤后请输入数值")

        try:
            minimum = float(value)
        except ValueError as exc:
            raise ValueError("最小 TORA 请输入数字") from exc

        if minimum < 0:
            raise ValueError("最小 TORA 不能小于 0")
        return minimum

    def _render_single_point_runway_options(self, runways: tuple[Runway, ...], empty_message: str = "请先选择机场") -> None:
        dpg = self.dpg
        if not dpg.does_item_exist(SINGLE_POINT_RUNWAY_GROUP):
            return

        current = self._selected_single_point_runway()
        dpg.delete_item(SINGLE_POINT_RUNWAY_GROUP, children_only=True)
        self.single_point_runway_checkbox_tags = {}

        if not runways:
            dpg.add_text(empty_message, parent=SINGLE_POINT_RUNWAY_GROUP)
            return

        selected = current if current in {runway.identifier for runway in runways} else runways[0].identifier
        for index, runway in enumerate(runways):
            tag = f"stas_single_point_runway_checkbox_{index}"
            self.single_point_runway_checkbox_tags[runway.identifier] = tag
            dpg.add_checkbox(
                label=self._runway_display_label(runway),
                tag=tag,
                parent=SINGLE_POINT_RUNWAY_GROUP,
                default_value=runway.identifier == selected,
                callback=self._on_single_point_runway_selected,
                user_data=runway.identifier,
            )

    def _on_single_point_runway_selected(
        self,
        sender: str | None = None,
        app_data: Any = None,
        user_data: Any = None,
    ) -> None:
        selected_runway = str(user_data or "")
        if not selected_runway:
            return
        for runway, tag in self.single_point_runway_checkbox_tags.items():
            if self.dpg.does_item_exist(tag):
                self.dpg.set_value(tag, runway == selected_runway)

    def _selected_single_point_runway(self) -> str:
        for runway, tag in self.single_point_runway_checkbox_tags.items():
            if self.dpg.does_item_exist(tag) and self.dpg.get_value(tag):
                return runway
        return ""

    def _aircraft_options(self, options_by_aircraft: dict[str, tuple[str, ...]], aircraft_code: str) -> tuple[str, ...]:
        code = aircraft_code.strip().upper()
        if code in {"777F", "B777F"}:
            return options_by_aircraft["777F"]
        return options_by_aircraft["738"]

    def _aircraft_default(self, options_by_aircraft: dict[str, str], aircraft_code: str) -> str:
        code = aircraft_code.strip().upper()
        if code in {"777F", "B777F"}:
            return options_by_aircraft["777F"]
        return options_by_aircraft["738"]

    def _set_recommended_manual_template(self) -> None:
        if not self.dpg.does_item_exist(MANUAL_TEMPLATE_COMBO):
            return

        current_label = self.dpg.get_value(MANUAL_TEMPLATE_COMBO) or MANUAL_TEMPLATE_NONE_LABEL
        if current_label == MANUAL_TEMPLATE_NONE_LABEL:
            self.dpg.set_value(MANUAL_TEMPLATE_COMBO, MANUAL_TEMPLATE_NONE_LABEL)
            return

        template_id = recommended_manual_report_template_id(
            self.dpg.get_value(AIRCRAFT_COMBO) or "",
            self.dpg.get_value(THRUST_COMBO) or "",
        )
        label = self.manual_template_label_by_id.get(template_id)
        if label:
            self.dpg.set_value(MANUAL_TEMPLATE_COMBO, label)

    def _selected_manual_template_id(self) -> str:
        label = self.dpg.get_value(MANUAL_TEMPLATE_COMBO) or ""
        return self.manual_template_id_by_label.get(label, label).strip()

    def _selected_report_date_override(self) -> str:
        if not self.dpg.does_item_exist(REPORT_DATE_OVERRIDE_CHECKBOX):
            return ""
        if not self.dpg.get_value(REPORT_DATE_OVERRIDE_CHECKBOX):
            return ""

        day = self.dpg.get_value(REPORT_DATE_DAY_COMBO) or "01"
        month = self.dpg.get_value(REPORT_DATE_MONTH_COMBO) or AVIATION_MONTHS[0]
        year = self.dpg.get_value(REPORT_DATE_YEAR_INPUT) or date.today().year
        try:
            return format_aviation_date(day, month, year)
        except ValueError:
            return f"{str(day).strip().zfill(2)}-{str(month).strip().upper()}-{str(year).strip()}"

    def _refresh_order_presets(self, selected: str = "") -> None:
        if not self.dpg.does_item_exist(ORDER_PRESET_COMBO):
            return

        names = tuple(sorted(self.order_store.load_all()))
        self.dpg.configure_item(ORDER_PRESET_COMBO, items=list(names))
        if selected and selected in names:
            self.dpg.set_value(ORDER_PRESET_COMBO, selected)
            self.dpg.set_value(ORDER_NAME_INPUT, selected)
        elif names:
            current = self.dpg.get_value(ORDER_PRESET_COMBO)
            value = current if current in names else names[0]
            self.dpg.set_value(ORDER_PRESET_COMBO, value)
        else:
            self.dpg.set_value(ORDER_PRESET_COMBO, "")

    def _render_scenario_queue(self) -> None:
        labels = [format_scenario_label(index, values) for index, values in enumerate(self.scenario_queue, start=1)]
        if not labels:
            self.dpg.configure_item(SCENARIO_QUEUE_LIST, items=["<empty>"])
            self.dpg.set_value(SCENARIO_QUEUE_LIST, "<empty>")
            return

        if self.selected_scenario_index is None or self.selected_scenario_index >= len(labels):
            self.selected_scenario_index = 0

        self.dpg.configure_item(SCENARIO_QUEUE_LIST, items=labels)
        self.dpg.set_value(SCENARIO_QUEUE_LIST, labels[self.selected_scenario_index])

    def _on_scenario_selected(self, sender: str | None = None, app_data: Any = None, user_data: Any = None) -> None:
        if not self.scenario_queue:
            self.selected_scenario_index = None
            return

        selected = self.dpg.get_value(SCENARIO_QUEUE_LIST)
        labels = [format_scenario_label(index, values) for index, values in enumerate(self.scenario_queue, start=1)]
        try:
            self.selected_scenario_index = labels.index(selected)
        except ValueError:
            self.selected_scenario_index = None

    def _with_scenario_id(self, values: PerformanceFormValues, index: int) -> PerformanceFormValues:
        request = build_performance_request(values)
        runway_condition = request.runway_condition or "DRY"
        bleed = request.bleed or "DEFAULT"
        thrust = values.thrust_option if aircraft_supports_thrust_options(values.aircraft_code) else THRUST_NORMAL
        return PerformanceFormValues(
            aircraft_code=values.aircraft_code,
            airport_code=values.airport_code,
            runways=values.runways,
            anti_icing=values.anti_icing,
            temperature_range=values.temperature_range,
            wind_range=values.wind_range,
            qnh_ref=values.qnh_ref,
            describe_qnh_ref=values.describe_qnh_ref,
            thrust_option=values.thrust_option,
            scenario_id=f"job_{index:02d}_{runway_condition}_{self._safe_scenario_token(thrust)}_BLEED_{bleed}",
            runway_condition=values.runway_condition,
            contamination_depth=values.contamination_depth,
            bleed=values.bleed,
            derate="",
            manual_report_template_id=values.manual_report_template_id,
            report_date_override=values.report_date_override,
        )

    def _with_current_report_template(self, values: PerformanceFormValues) -> PerformanceFormValues:
        return replace(
            values,
            manual_report_template_id=self._selected_manual_template_id(),
            report_date_override=self._selected_report_date_override(),
        )

    def _safe_scenario_token(self, value: str) -> str:
        return "".join(character if character.isalnum() else "_" for character in value).strip("_") or "NORMAL"

    def _open_existing_file(self, path: Path | None, missing_message: str) -> None:
        if path and path.exists():
            self._open_path(path)
        else:
            self._show_message("提示", missing_message)
            self._append_result(f"提示: {missing_message}\n")

    def _open_path(self, path: Path) -> None:
        path = Path(path)
        if not path.exists():
            message = f"路径不存在: {path}"
            self._show_message("提示", message)
            self._append_result(f"提示: {message}\n")
            return

        try:
            os.startfile(path)
        except OSError as exc:
            message = f"无法打开路径: {exc}"
            self._show_message("提示", message)
            self._append_result(f"提示: {message}\n")

    def _append_result(self, message: str) -> None:
        current = self.dpg.get_value(RESULT_TEXT) or ""
        self.dpg.set_value(RESULT_TEXT, current + message)

    def _append_single_point_result(self, message: str) -> None:
        if not self.dpg.does_item_exist(SINGLE_POINT_RESULT_TEXT):
            return
        current = self.dpg.get_value(SINGLE_POINT_RESULT_TEXT) or ""
        self.dpg.set_value(SINGLE_POINT_RESULT_TEXT, current + message)

    def _set_status(self, status: str) -> None:
        self.dpg.set_value(STATUS_TEXT, status)

    def _set_calculating(self, calculating: bool) -> None:
        self.is_calculating = calculating
        self.dpg.configure_item(CALCULATE_BUTTON, enabled=not calculating)
        if self.dpg.does_item_exist(CALCULATE_QUEUE_BUTTON):
            self.dpg.configure_item(CALCULATE_QUEUE_BUTTON, enabled=not calculating)
        if self.dpg.does_item_exist(SINGLE_POINT_CALCULATE_BUTTON):
            self.dpg.configure_item(SINGLE_POINT_CALCULATE_BUTTON, enabled=not calculating)
        self._set_status("计算中..." if calculating else "就绪")

    def _drain_ui_queue(self) -> None:
        while True:
            try:
                event, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                return

            if event == "calculation_result":
                result, elapsed_seconds = payload
                self._handle_calculation_result(result, elapsed_seconds)
            elif event == "single_point_result":
                result, elapsed_seconds = payload
                self._handle_single_point_result(result, elapsed_seconds)
            elif event == "queue_result":
                results, queue_report, elapsed_seconds = payload
                self._handle_queue_result(results, queue_report, elapsed_seconds)
            elif event == "queue_progress":
                self._append_result(payload)
            elif event == "calculation_error":
                exc, elapsed_seconds = payload
                self._handle_calculation_error(exc, elapsed_seconds)
            elif event == "single_point_error":
                exc, elapsed_seconds = payload
                self._handle_single_point_error(exc, elapsed_seconds)

    def _show_message(self, title: str, message: str) -> None:
        dpg = self.dpg
        if dpg.does_item_exist(MESSAGE_MODAL):
            dpg.delete_item(MESSAGE_MODAL)

        with dpg.window(label=title, modal=True, show=True, tag=MESSAGE_MODAL, width=460, height=170):
            dpg.add_text(message, wrap=420)
            dpg.add_spacer(height=10)
            dpg.add_button(label="关闭", width=80, callback=lambda: dpg.delete_item(MESSAGE_MODAL))


def _load_dearpygui() -> ModuleType:
    import dearpygui.dearpygui as dpg

    return dpg


def _bind_chinese_font(dpg: ModuleType) -> None:
    font_path = _find_chinese_font()
    if font_path is None:
        return

    try:
        with dpg.font_registry():
            with dpg.font(str(font_path), 18) as default_font:
                pass
        dpg.bind_font(default_font)
    except Exception:
        return


def _find_chinese_font() -> Path | None:
    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = (
        windows_dir / "Fonts" / "msyh.ttc",
        windows_dir / "Fonts" / "simhei.ttf",
        windows_dir / "Fonts" / "simsun.ttc",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    )
    return next((path for path in candidates if path.exists()), None)


def _show_startup_error(dpg: ModuleType, exc: Exception) -> None:
    dpg.create_viewport(title="STAS Startup Error", width=640, height=260)
    with dpg.window(label="启动失败", tag=MAIN_WINDOW):
        dpg.add_text("无法加载配置或初始化服务。")
        dpg.add_text(str(exc), wrap=590)
        dpg.add_spacer(height=12)
        dpg.add_button(label="关闭", width=90, callback=lambda: dpg.stop_dearpygui())

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window(MAIN_WINDOW, True)
    dpg.start_dearpygui()
