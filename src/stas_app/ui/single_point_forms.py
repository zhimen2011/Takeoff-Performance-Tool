"""Form helpers for the single-point takeoff UI."""

from __future__ import annotations

from dataclasses import dataclass

from stas_app.models.single_point import (
    ATM_MODE_FIXED,
    ATM_MODE_MAX,
    SinglePointCalculationResult,
    SinglePointSectionResult,
    SinglePointTakeoffRequest,
)
from stas_app.ui.forms import request_thrust_option


ATM_MODE_MAX_LABEL = "最大假设温度"
ATM_MODE_FIXED_LABEL = "指定假设温度"
ATM_MODE_BY_LABEL = {
    ATM_MODE_MAX_LABEL: ATM_MODE_MAX,
    ATM_MODE_FIXED_LABEL: ATM_MODE_FIXED,
}
ATM_MODE_LABEL_BY_VALUE = {value: label for label, value in ATM_MODE_BY_LABEL.items()}


@dataclass(frozen=True)
class SinglePointFormValues:
    """Raw values collected from the single-point desktop form."""

    aircraft_code: str
    airport_code: str
    runway: str
    takeoff_weight_kg: str
    actual_temperature_c: str
    wind_kt: str
    qnh_ref: str
    anti_icing: str
    thrust_option: str
    flap_setting: str = ""
    improved_climb: bool = True
    runway_condition: str = "DRY"
    contamination_depth: str = ""
    bleed: str = ""
    derate: str = ""
    atm_mode: str = ATM_MODE_MAX_LABEL
    assumed_temperature_c: str = ""


def build_single_point_request(values: SinglePointFormValues) -> SinglePointTakeoffRequest:
    """Convert desktop form values into a service-layer single-point request."""

    atm_mode = ATM_MODE_BY_LABEL.get(values.atm_mode.strip(), values.atm_mode.strip().upper() or ATM_MODE_MAX)
    return SinglePointTakeoffRequest(
        aircraft_code=values.aircraft_code.strip(),
        airport_code=values.airport_code.strip().upper(),
        runway=values.runway.strip().upper(),
        takeoff_weight_kg=_required_float(values.takeoff_weight_kg, "起飞重量"),
        actual_temperature_c=_required_float(values.actual_temperature_c, "实际温度"),
        wind_kt=_required_float(values.wind_kt, "风分量"),
        qnh_ref=_optional_float(values.qnh_ref, "QNH"),
        runway_condition=_extract_option_code(values.runway_condition, default="DRY") or "DRY",
        contamination_depth=values.contamination_depth.strip(),
        bleed=_extract_option_code(values.bleed),
        anti_icing=_extract_option_code(values.anti_icing, default="0") or "0",
        derate=values.derate.strip(),
        thrust_option=request_thrust_option(values.aircraft_code, values.thrust_option),
        flap_setting=_extract_flap_setting(values.flap_setting),
        improved_climb=bool(values.improved_climb),
        atm_mode=atm_mode,
        assumed_temperature_c=_optional_float(values.assumed_temperature_c, "假设温度"),
    )


def format_single_point_result(result: SinglePointCalculationResult, section_label: str = "FULL") -> str:
    """Create a concise human-readable single-point result summary."""

    if not result.succeeded:
        return f"单点计算失败: {result.error_message}\n"

    section_key, section = _selected_section(result, section_label)
    if section is None:
        return f"{section_key or 'FULL'} 结果不存在\n"

    lines: list[str] = ["单点计算完成"]
    if section.notice:
        lines.insert(0, section.notice)
    lines.extend(_format_section(section, result))

    has_following_details = result.full_table_path or result.atm_table_path or result.warnings
    if has_following_details and result.engine_failure_procedure_title:
        lines.extend(["", ""])

    if result.full_table_path:
        lines.append(f"FULL STASTBL: {result.full_table_path}")
    if result.atm_table_path:
        lines.append(f"ATM STASTBL: {result.atm_table_path}")

    for warning in result.warnings:
        lines.append(f"警告: {warning}")

    return "\n".join(lines) + "\n"


def format_single_point_runway_distance(result: SinglePointCalculationResult, section_label: str = "FULL") -> str:
    """Create the right-side Runway Distance text for the current single-point result."""

    if not result.succeeded:
        return ""

    _, section = _selected_section(result, section_label)
    if section is None:
        return ""

    return "\n".join(_format_runway_distance(section)) + "\n"


def _selected_section(
    result: SinglePointCalculationResult,
    section_label: str,
) -> tuple[str, SinglePointSectionResult | None]:
    section_key = section_label.strip().upper()
    section = result.atm if section_key == "ATM" else result.full
    return section_key, section


def _format_section(section: SinglePointSectionResult, result: SinglePointCalculationResult) -> list[str]:
    temperature_label = "ATM TEMP" if section.label == "ATM" else "OAT"
    thrust_label = "D-TO" if section.label == "ATM" else "TO"
    vref_label = _vref_label(result.request.aircraft_code)
    lines = ["", section.label]
    if result.request.flap_setting:
        lines.append(f"FLAP {result.request.flap_setting}")
    takeoff_weight_kg = section.takeoff_weight_kg
    if takeoff_weight_kg is None:
        takeoff_weight_kg = result.request.takeoff_weight_kg
    lines.append(f"TOGW: {_format_weight(takeoff_weight_kg)} KG")
    if section.temperature_c is not None:
        lines.append(f"{temperature_label}: {_format_temperature(section.temperature_c)}")
    lines.append(f"V1: {_format_int(section.v1)} KT")
    lines.append(f"VR: {_format_int(section.vr)} KT")
    lines.append(f"V2: {_format_int(section.v2)} KT")
    lines.append(f"{vref_label}: {_format_int(section.vref30)} KT")
    if section.takeoff_thrust is not None:
        lines.append(f"{thrust_label}: {section.takeoff_thrust:.1f}")
    if section.reduction_percent is not None and section.label == "ATM":
        lines.append(f"REDUCTION: {section.reduction_percent:.1f}%")
    lines.append(f"ACCEL HT: {_format_accel_height(section.accel_height_ft)}")
    if result.engine_failure_procedure_title:
        lines.append("")
        lines.append(f"Engine Failure Procedure: {result.engine_failure_procedure_title}")
        if result.engine_failure_procedure_detail:
            lines.append(result.engine_failure_procedure_detail)
    return lines


def _format_runway_distance(section: SinglePointSectionResult) -> list[str]:
    lines = ["Runway Distance"]
    lines.append(f"AE-GO: {_format_int(section.ae_go_m)} M")
    lines.append(f"EO-GO: {_format_int(section.eo_go_m)} M")
    lines.append(f"ACCEL-STOP: {_format_int(section.accel_stop_m)} M")
    lines.append(f"TORA: {_format_distance(section.tora_m)} M")
    lines.append(f"TODA: {_format_distance(section.toda_m)} M")
    lines.append(f"ASDA: {_format_distance(section.asda_m)} M")
    lines.append(f"SLOPE: {_format_slope(section.slope_percent)}")
    return lines


def _format_temperature(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _format_int(value: int | None) -> str:
    return "-" if value is None else str(value)


def _format_accel_height(value: int | None) -> str:
    return "-" if value is None else f"{value} ft AGL"


def _format_weight(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _format_distance(value: float | None) -> str:
    if value is None:
        return "-"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _format_slope(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}%"


def _vref_label(aircraft_code: str) -> str:
    code = aircraft_code.strip().upper()
    if code in {"738", "737-800", "737800", "737-800W", "B738"}:
        return "VREF"
    return "VREF30"


def _required_float(value: str, field_name: str) -> float:
    token = value.strip()
    if not token:
        raise ValueError(f"{field_name}不能为空")
    return _parse_float(token, field_name)


def _optional_float(value: str, field_name: str) -> float | None:
    token = value.strip()
    if not token:
        return None
    return _parse_float(token, field_name)


def _parse_float(value: str, field_name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name}必须是数字") from exc


def _extract_option_code(value: str, default: str = "") -> str:
    token = value.strip()
    if not token:
        return default
    code = token.split(maxsplit=1)[0].strip()
    if code.upper() == "DEFAULT":
        return default
    return code


def _extract_flap_setting(value: str) -> str:
    token = value.strip().upper()
    if token.startswith("FLAP "):
        return token.split(maxsplit=1)[1].strip()
    if token.startswith("FLAP"):
        return token[4:].strip()
    return token
