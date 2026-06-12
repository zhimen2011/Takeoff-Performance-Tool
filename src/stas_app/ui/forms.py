"""Form value helpers shared by the desktop UI and tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from stas_app.models.report import QueueReportResult
from stas_app.models.request import PerformanceRequest
from stas_app.models.result import PerformanceCalculationResult


@dataclass(frozen=True)
class PerformanceFormValues:
    """Raw values collected from the desktop form."""

    aircraft_code: str
    airport_code: str
    runways: tuple[str, ...]
    anti_icing: str
    temperature_range: str
    wind_range: str
    qnh_ref: str
    thrust_option: str
    describe_qnh_ref: bool = True
    scenario_id: str = ""
    runway_condition: str = "DRY"
    contamination_depth: str = ""
    bleed: str = ""
    derate: str = ""
    manual_report_template_id: str = ""
    report_date_override: str = ""


DEFAULT_TEMPLATE_ORDER = (
    ("DRY", "DEFAULT"),
    ("DRY", "OFF"),
    ("WET", "DEFAULT"),
    ("WET", "OFF"),
)

DEPTH_REQUIRED_RUNWAY_CONDITIONS = {"2", "3", "5", "STANDING_WATER", "SLUSH", "DRY_SNOW"}
THRUST_NORMAL = "\u6b63\u5e38"
THRUST_DERATE_10 = "\u51cf\u63a8\u529b10%"
THRUST_DERATE_20 = "\u51cf\u63a8\u529b20%"
THRUST_BUMP = "1L1BUMP"
THRUST_OPTIONS_777F = (THRUST_NORMAL, THRUST_DERATE_10, THRUST_DERATE_20, THRUST_BUMP)
MANUAL_TEMPLATE_738_NORMAL = "738_normal"
MANUAL_TEMPLATE_777F_NORMAL = "777f_normal"
MANUAL_TEMPLATE_777F_DERATE = "777f_derate"
MANUAL_TEMPLATE_777F_BUMP = "777f_bump"


def build_performance_request(values: PerformanceFormValues) -> PerformanceRequest:
    """Convert desktop form values into a service-layer request."""

    thrust = request_thrust_option(values.aircraft_code, values.thrust_option)
    return PerformanceRequest(
        aircraft_code=values.aircraft_code.strip(),
        airport_code=values.airport_code.strip().upper(),
        runways=tuple(runway.strip().upper() for runway in values.runways if runway.strip()),
        scenario_id=values.scenario_id.strip(),
        runway_condition=_extract_option_code(values.runway_condition, default="DRY") or "DRY",
        contamination_depth=values.contamination_depth.strip(),
        bleed=_extract_option_code(values.bleed),
        anti_icing=_extract_anti_icing_code(values.anti_icing),
        derate=values.derate.strip(),
        temperature_range=values.temperature_range.strip(),
        wind_range=values.wind_range.strip(),
        qnh_ref=values.qnh_ref.strip(),
        describe_qnh_ref=bool(values.describe_qnh_ref),
        thrust_option=thrust,
        manual_report_template_id=values.manual_report_template_id.strip(),
        report_date_override=values.report_date_override.strip().upper(),
    )


def build_default_order_form_values(values: PerformanceFormValues) -> tuple[PerformanceFormValues, ...]:
    """Build the old template output order from the current form values."""

    default_bleed = default_bleed_for_aircraft(values.aircraft_code)
    scenarios: list[PerformanceFormValues] = []
    for index, (runway_condition, bleed_choice) in enumerate(DEFAULT_TEMPLATE_ORDER, start=1):
        bleed = default_bleed if bleed_choice == "DEFAULT" else bleed_choice
        scenarios.append(
            replace(
                values,
                scenario_id=f"job_{index:02d}_{runway_condition}_BLEED_{bleed}",
                runway_condition=runway_condition,
                contamination_depth="",
                bleed=bleed,
            )
        )
    return tuple(scenarios)


def export_order_items(values: tuple[PerformanceFormValues, ...] | list[PerformanceFormValues]) -> list[dict[str, str]]:
    """Export reusable queue fields while excluding aircraft, airport, runways and report format."""

    items: list[dict[str, str]] = []
    for value in values:
        request = build_performance_request(value)
        items.append(
            {
                "runway_condition": request.runway_condition,
                "contamination_depth": request.contamination_depth,
                "thrust_option": display_thrust_option(value.aircraft_code, value.thrust_option, request.derate),
                "derate": request.derate,
                "bleed": request.bleed,
                "anti_icing": request.anti_icing,
                "temperature_range": request.temperature_range,
                "wind_range": request.wind_range,
                "qnh_ref": request.qnh_ref,
                "describe_qnh_ref": "true" if request.describe_qnh_ref else "false",
            }
        )
    return items


def apply_order_items(
    base_values: PerformanceFormValues,
    items: list[dict[str, Any]],
) -> tuple[PerformanceFormValues, ...]:
    """Apply saved queue items to the current aircraft, airport, runway and report format."""

    scenarios: list[PerformanceFormValues] = []
    for index, item in enumerate(items, start=1):
        runway_condition = str(item.get("runway_condition", "DRY")).strip() or "DRY"
        derate = str(item.get("derate", "")).strip()
        thrust_option = str(item.get("thrust_option", "")).strip()
        if not thrust_option:
            thrust_option = thrust_option_from_legacy_derate(base_values.aircraft_code, derate)
        anti_icing = str(item.get("anti_icing", "0")).strip() or "0"
        bleed = str(item.get("bleed", "")).strip()
        temperature_range = str(item.get("temperature_range", base_values.temperature_range)).strip()
        wind_range = str(item.get("wind_range", base_values.wind_range)).strip()
        qnh_ref = str(item.get("qnh_ref", base_values.qnh_ref)).strip()
        describe_qnh_ref = _parse_bool(item.get("describe_qnh_ref"), default=base_values.describe_qnh_ref)
        scenarios.append(
            replace(
                base_values,
                scenario_id=(
                    f"job_{index:02d}_{runway_condition}_"
                    f"{_safe_scenario_token(display_thrust_option(base_values.aircraft_code, thrust_option, derate))}_"
                    f"AI{anti_icing}_BLEED_{bleed or 'DEFAULT'}"
                ),
                runway_condition=runway_condition,
                contamination_depth=str(item.get("contamination_depth", "")).strip(),
                thrust_option=thrust_option,
                derate="",
                bleed=bleed,
                anti_icing=anti_icing,
                temperature_range=temperature_range,
                wind_range=wind_range,
                qnh_ref=qnh_ref,
                describe_qnh_ref=describe_qnh_ref,
                manual_report_template_id=base_values.manual_report_template_id,
                report_date_override=base_values.report_date_override,
            )
        )
    return tuple(scenarios)


def default_bleed_for_aircraft(aircraft_code: str) -> str:
    """Return the aircraft default bleed state used by the old templates."""

    code = aircraft_code.strip().upper()
    if code in {"738", "737-800", "737800", "737-800W", "B738"}:
        return "AUTO"
    return "ON"


def format_scenario_label(index: int, values: PerformanceFormValues) -> str:
    """Return a compact label for the queue list."""

    request = build_performance_request(values)
    runway = format_runway_summary(request.runways)
    bleed = request.bleed or default_bleed_for_aircraft(request.aircraft_code)
    depth = f" depth={request.contamination_depth}mm" if request.contamination_depth else ""
    thrust_option = display_thrust_option(values.aircraft_code, values.thrust_option, request.derate)
    temperature = request.temperature_range or "-"
    wind = request.wind_range or "-"
    qnh = request.qnh_ref or "-"
    return (
        f"{index:02d}. {request.aircraft_code} {request.airport_code} {runway} "
        f"{request.runway_condition} \u63a8\u529b={thrust_option} \u5f15\u6c14={bleed} "
        f"\u9632\u51b0={request.anti_icing} \u6e29\u5ea6={temperature} \u98ce={wind} QNH={qnh}{depth}"
    )


def format_runway_summary(runways: tuple[str, ...], visible_count: int = 2) -> str:
    """Return a short runway summary for narrow queue-list rows."""

    normalized = tuple(runway.strip().upper() for runway in runways if runway.strip())
    if not normalized:
        return "RWY *"

    shown_count = max(1, visible_count)
    shown = "/".join(normalized[:shown_count])
    hidden_count = len(normalized) - shown_count
    if hidden_count > 0:
        shown = f"{shown}/+{hidden_count}"
    return f"RWY {shown}"


def format_result_summary(result: PerformanceCalculationResult) -> str:
    """Create a concise human-readable result summary for the UI."""

    lines: list[str] = []
    if result.succeeded:
        lines.append("计算完成")
    else:
        lines.append(f"计算失败: {result.error_message}")

    if result.stas_run:
        lines.append(f"输出目录: {result.stas_run.run_dir}")
        if result.stas_run.raw_output_path:
            lines.append(f"STAS 原始输出: {result.stas_run.raw_output_path}")
        if result.stas_run.metadata_path:
            lines.append(f"运行元数据: {result.stas_run.metadata_path}")

    if result.word_report:
        if result.word_report.succeeded and result.word_report.output_path:
            lines.append(f"\u4e34\u65f6\u8d77\u98de\u5206\u6790 Word: {result.word_report.output_path}")
        else:
            lines.append(f"\u4e34\u65f6\u8d77\u98de\u5206\u6790 Word \u5931\u8d25: {result.word_report.error_message}")

    if result.pdf_report:
        if result.pdf_report.succeeded and result.pdf_report.output_path:
            lines.append(f"\u4e34\u65f6\u8d77\u98de\u5206\u6790 PDF: {result.pdf_report.output_path}")
        else:
            lines.append(f"\u4e34\u65f6\u8d77\u98de\u5206\u6790 PDF \u5931\u8d25: {result.pdf_report.error_message}")

    if result.manual_word_report:
        if result.manual_word_report.succeeded and result.manual_word_report.output_path:
            lines.append(f"\u624b\u518c\u8d77\u98de\u5206\u6790 Word: {result.manual_word_report.output_path}")
        else:
            lines.append(f"\u624b\u518c\u8d77\u98de\u5206\u6790 Word \u5931\u8d25: {result.manual_word_report.error_message}")

    if result.manual_pdf_report:
        if result.manual_pdf_report.succeeded and result.manual_pdf_report.output_path:
            lines.append(f"\u624b\u518c\u8d77\u98de\u5206\u6790 PDF: {result.manual_pdf_report.output_path}")
        else:
            lines.append(f"\u624b\u518c\u8d77\u98de\u5206\u6790 PDF \u5931\u8d25: {result.manual_pdf_report.error_message}")

    for warning in result.warnings:
        lines.append(f"警告: {warning}")

    return "\n".join(lines) + "\n"


def format_queue_report_summary(report: QueueReportResult) -> str:
    """Create a concise human-readable queue report summary for the UI."""

    lines: list[str] = ["", "\u961f\u5217\u5408\u5e76\u62a5\u544a"]
    if report.succeeded:
        lines.append("\u961f\u5217\u5408\u5e76\u62a5\u544a\u5df2\u751f\u6210")
    else:
        lines.append(f"\u961f\u5217\u5408\u5e76\u62a5\u544a\u5931\u8d25: {report.error_message}")

    if report.run_dir:
        lines.append(f"\u961f\u5217\u8f93\u51fa\u76ee\u5f55: {report.run_dir}")
    if report.merged_output_path:
        lines.append(f"\u961f\u5217\u539f\u59cb\u5408\u5e76\u8f93\u51fa: {report.merged_output_path}")

    if report.word_report:
        if report.word_report.succeeded and report.word_report.output_path:
            lines.append(f"\u961f\u5217\u4e34\u65f6\u8d77\u98de\u5206\u6790 Word: {report.word_report.output_path}")
        else:
            lines.append(f"\u961f\u5217\u4e34\u65f6\u8d77\u98de\u5206\u6790 Word \u5931\u8d25: {report.word_report.error_message}")

    if report.pdf_report:
        if report.pdf_report.succeeded and report.pdf_report.output_path:
            lines.append(f"\u961f\u5217\u4e34\u65f6\u8d77\u98de\u5206\u6790 PDF: {report.pdf_report.output_path}")
        else:
            lines.append(f"\u961f\u5217\u4e34\u65f6\u8d77\u98de\u5206\u6790 PDF \u5931\u8d25: {report.pdf_report.error_message}")

    if report.manual_word_report:
        if report.manual_word_report.succeeded and report.manual_word_report.output_path:
            lines.append(f"\u961f\u5217\u624b\u518c\u8d77\u98de\u5206\u6790 Word: {report.manual_word_report.output_path}")
        else:
            lines.append(f"\u961f\u5217\u624b\u518c\u8d77\u98de\u5206\u6790 Word \u5931\u8d25: {report.manual_word_report.error_message}")

    if report.manual_pdf_report:
        if report.manual_pdf_report.succeeded and report.manual_pdf_report.output_path:
            lines.append(f"\u961f\u5217\u624b\u518c\u8d77\u98de\u5206\u6790 PDF: {report.manual_pdf_report.output_path}")
        else:
            lines.append(f"\u961f\u5217\u624b\u518c\u8d77\u98de\u5206\u6790 PDF \u5931\u8d25: {report.manual_pdf_report.error_message}")

    for warning in report.warnings:
        lines.append(f"\u8b66\u544a: {warning}")

    return "\n".join(lines) + "\n"


def runway_condition_requires_depth(runway_condition: str) -> bool:
    """Return whether a runway condition needs contamination depth input."""

    return (_extract_option_code(runway_condition, default="DRY") or "DRY").upper() in DEPTH_REQUIRED_RUNWAY_CONDITIONS


def contamination_depth_hint(runway_condition: str) -> str:
    """Return the operator hint for the selected runway condition."""

    code = (_extract_option_code(runway_condition, default="DRY") or "DRY").upper()
    if code in {"2", "STANDING_WATER", "3", "SLUSH"}:
        return "\u79ef\u6c34/\u96ea\u6d46\u9700\u8f93\u5165\u6df1\u5ea6\uff1a1.27-12.70 mm"
    if code in {"5", "DRY_SNOW"}:
        return "\u5e72\u96ea\u9700\u8f93\u5165\u6df1\u5ea6\uff1a1.27-101.60 mm"
    return "\u5f53\u524d\u9053\u9762\u6761\u4ef6\u4e0d\u9700\u8981\u6c61\u67d3\u6df1\u5ea6"


def request_thrust_option(aircraft_code: str, thrust_option: str) -> str | None:
    """Return the service-layer thrust option for an aircraft."""

    if not aircraft_supports_thrust_options(aircraft_code):
        return None
    token = thrust_option.strip()
    return token or THRUST_NORMAL


def display_thrust_option(aircraft_code: str, thrust_option: str, derate: str = "") -> str:
    """Return the operator-facing thrust label for a Scenario row."""

    if not aircraft_supports_thrust_options(aircraft_code):
        return THRUST_NORMAL

    token = thrust_option.strip()
    if token:
        return token
    return thrust_option_from_legacy_derate(aircraft_code, derate)


def thrust_option_from_legacy_derate(aircraft_code: str, derate: str) -> str:
    """Map legacy order-preset derate values into current thrust options."""

    if not aircraft_supports_thrust_options(aircraft_code):
        return THRUST_NORMAL

    token = derate.strip().rstrip("%")
    if token == "10":
        return THRUST_DERATE_10
    if token == "20":
        return THRUST_DERATE_20
    return THRUST_NORMAL


def aircraft_supports_thrust_options(aircraft_code: str) -> bool:
    """Return whether the desktop should expose thrust options for this aircraft."""

    return aircraft_code.strip().upper() in {"777F", "777", "B777F"}


def default_temperature_range(aircraft_code: str, anti_icing: str, thrust_option: str, configured_default: str) -> str:
    """Return the desktop default temperature range for the selected options."""

    if _extract_anti_icing_code(anti_icing) != "0":
        return "10:-10:2"
    if aircraft_code.upper() == "777F" and thrust_option.strip() == "1L1BUMP":
        return "45:31:1"
    return configured_default


def recommended_manual_report_template_id(aircraft_code: str, thrust_option: str) -> str:
    """Return the default manual report template id for aircraft and thrust."""

    if not aircraft_supports_thrust_options(aircraft_code):
        return MANUAL_TEMPLATE_738_NORMAL

    token = thrust_option.strip()
    if token == THRUST_BUMP:
        return MANUAL_TEMPLATE_777F_BUMP
    if token in {THRUST_DERATE_10, THRUST_DERATE_20}:
        return MANUAL_TEMPLATE_777F_DERATE
    return MANUAL_TEMPLATE_777F_NORMAL


def _extract_anti_icing_code(value: str) -> str:
    token = value.strip()
    if not token:
        return "0"
    return token.split(maxsplit=1)[0]


def _extract_option_code(value: str, default: str = "") -> str:
    token = value.strip()
    if not token:
        return default
    code = token.split(maxsplit=1)[0].strip()
    if code.upper() == "DEFAULT":
        return default
    return code


def _safe_scenario_token(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value).strip("_") or "NORMAL"


def _parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value

    token = str(value).strip().lower()
    if not token:
        return default
    if token in {"0", "false", "no", "off", "n"}:
        return False
    if token in {"1", "true", "yes", "on", "y"}:
        return True
    return default
