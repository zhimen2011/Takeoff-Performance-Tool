"""Aircraft-specific Scenario field mappings for STAS POPT/CONF values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from stas_app.models.request import PerformanceRequest


NOT_APPLICABLE = "9.E20"
NUMERIC_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")
INCH_TO_MM = 25.4


@dataclass(frozen=True)
class ResolvedScenarioOptions:
    """Values written into the Scenario-driven STAS input template."""

    runway_condition: str
    contamination_depth: str
    bleed_status: str
    anti_icing: str
    derated: str


RUNWAY_CONDITION_VALUES = {
    "0": "0",
    "DRY": "0",
    "1": "1",
    "WET": "1",
    "ADVISORY_WET_WITH_DRY_CHECK": "1",
    "2": "2",
    "STANDING_WATER": "2",
    "WATER": "2",
    "3": "3",
    "SLUSH": "3",
    "4": "4",
    "COMPACTED_SNOW": "4",
    "PACKED_SNOW": "4",
    "5": "5",
    "DRY_SNOW": "5",
    "SNOW": "5",
    "8": "8",
    "WET_ICE": "8",
    "11": "11",
    "ADVISORY_WET": "11",
    "WET_ADVISORY": "11",
}

RUNWAY_CONDITIONS_REQUIRING_DEPTH = {"2", "3", "5"}
DEPTH_LIMITS_MM = {
    "2": (0.05 * INCH_TO_MM, 0.5 * INCH_TO_MM),
    "3": (0.05 * INCH_TO_MM, 0.5 * INCH_TO_MM),
    "5": (0.05 * INCH_TO_MM, 4.0 * INCH_TO_MM),
}


AIRCRAFT_OPTION_VALUES = {
    "777F": {
        "bleed": {
            "default": "ON",
            "values": {
                "1": "1",
                "ON": "1",
                "2": "2",
                "OFF": "2",
                "6": "6",
                "APU": "6",
                "APU_TO_PACK": "6",
                "APU_PACK": "6",
            },
        },
        "anti_icing": {
            "default": "OFF",
            "values": {
                "0": "0",
                "OFF": "0",
                "1": "1",
                "ENG": "1",
                "ENGINE": "1",
                "ENGINE_ON": "1",
                "3": "3",
                "ENG_WING": "3",
                "ENGINE_WING": "3",
                "ENGINE_AND_WING": "3",
                "8": "8",
                "ENG_AUTO": "8",
                "ENGINE_AUTO": "8",
                "10": "10",
                "ENG_WING_AUTO": "10",
                "ENGINE_WING_AUTO": "10",
                "ENGINE_AND_WING_AUTO": "10",
                "11": "11",
                "ENGINE_ON_WING_AUTO": "11",
            },
        },
    },
    "738": {
        "bleed": {
            "default": "AUTO",
            "values": {
                "0": "0",
                "AUTO": "0",
                "ON": "0",
                "2": "2",
                "OFF": "2",
                "5": "5",
                "V1MCG_OFF": "5",
                "AUTO_OFF_FOR_V1MCG": "5",
            },
        },
        "anti_icing": {
            "default": "OFF",
            "values": {
                "0": "0",
                "OFF": "0",
                "1": "1",
                "ENG": "1",
                "ENGINE": "1",
                "3": "3",
                "ENG_WING": "3",
                "ENGINE_WING": "3",
                "ENGINE_AND_WING": "3",
                "ENG_WING_STD": "3",
                "STANDARD": "3",
                "7": "7",
                "ENG_WING_OPT": "7",
                "OPTIONAL": "7",
                "ENGINE_WING_OPTIONAL": "7",
            },
        },
    },
}


def resolve_scenario_options(
    request: PerformanceRequest,
    aircraft_code: str,
    thrust_option_derated: str,
) -> ResolvedScenarioOptions:
    """Resolve one user Scenario into aircraft-specific template values."""

    aircraft_key = _aircraft_key(aircraft_code)
    if aircraft_key not in AIRCRAFT_OPTION_VALUES:
        raise ValueError(f"Scenario mappings are not configured for aircraft: {aircraft_code}")

    runway_condition = _resolve_runway_condition(request.runway_condition)
    return ResolvedScenarioOptions(
        runway_condition=runway_condition,
        contamination_depth=_resolve_contamination_depth(runway_condition, request.contamination_depth),
        bleed_status=_resolve_aircraft_option(aircraft_key, "bleed", request.bleed),
        anti_icing=_resolve_aircraft_option(aircraft_key, "anti_icing", request.anti_icing),
        derated=_resolve_derate(request.derate, thrust_option_derated),
    )


def _resolve_aircraft_option(aircraft_key: str, field_name: str, value: Any) -> str:
    config = AIRCRAFT_OPTION_VALUES[aircraft_key][field_name]
    token = _option_key(value, default=config["default"])
    try:
        return config["values"][token]
    except KeyError as exc:
        valid_values = ", ".join(sorted(config["values"]))
        raise ValueError(f"Unsupported {field_name} for {aircraft_key}: {value}. Valid values: {valid_values}") from exc


def _resolve_runway_condition(value: Any) -> str:
    token = _option_key(value, default="DRY")
    try:
        return RUNWAY_CONDITION_VALUES[token]
    except KeyError as exc:
        valid_values = ", ".join(sorted(RUNWAY_CONDITION_VALUES))
        raise ValueError(f"Unsupported runway_condition: {value}. Valid values: {valid_values}") from exc


def _resolve_contamination_depth(runway_condition: str, value: Any) -> str:
    token = "" if value is None else str(value).strip()
    if not token:
        if runway_condition in RUNWAY_CONDITIONS_REQUIRING_DEPTH:
            raise ValueError(
                "contamination_depth is required for STANDING_WATER, SLUSH, and DRY_SNOW runway conditions"
            )
        return NOT_APPLICABLE

    if not NUMERIC_PATTERN.match(token):
        raise ValueError(f"Invalid contamination_depth value: {value}")
    if runway_condition not in RUNWAY_CONDITIONS_REQUIRING_DEPTH:
        raise ValueError("contamination_depth is only supported for STANDING_WATER, SLUSH, and DRY_SNOW")

    depth = float(token)
    minimum, maximum = DEPTH_LIMITS_MM[runway_condition]
    if not minimum <= depth <= maximum:
        raise ValueError(
            f"contamination_depth {token} mm is outside the supported range "
            f"{minimum:.2f}-{maximum:.2f} mm for runway condition POPT(14)={runway_condition}"
        )
    return _format_number(token)


def _resolve_derate(value: Any, thrust_option_derated: str) -> str:
    token = "" if value is None else str(value).strip()
    if not token:
        token = str(thrust_option_derated).strip() or "0"

    normalized = _option_key(token)
    if normalized in {"NONE", "OFF", "NORMAL"}:
        return "0"

    token = token.rstrip("%").strip()
    if not NUMERIC_PATTERN.match(token):
        raise ValueError(f"Invalid derate value: {value}")
    return _format_number(token)


def _option_key(value: Any, default: str = "") -> str:
    token = "" if value is None else str(value).strip()
    if not token:
        token = default
    token = token.strip().upper()
    token = re.sub(r"[\s\-/]+", "_", token)
    token = re.sub(r"_+", "_", token).strip("_")
    return token


def _format_number(value: str) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return str(number)


def _aircraft_key(aircraft_code: str) -> str:
    code = aircraft_code.strip().upper()
    if code in {"777F", "B777F"}:
        return "777F"
    if code in {"738", "737-800", "737800", "737-800W", "B738"}:
        return "738"
    return code
