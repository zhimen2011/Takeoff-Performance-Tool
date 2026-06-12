"""Request models for STAS performance calculation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PerformanceRequest:
    """User inputs needed to build one STAS takeoff input file."""

    aircraft_code: str
    airport_code: str
    runways: tuple[str, ...] = field(default_factory=tuple)
    scenario_id: str = ""
    runway_condition: str = "DRY"
    contamination_depth: str = ""
    bleed: str = ""
    anti_icing: str = "0"
    derate: str = ""
    temperature_range: str = ""
    wind_range: str = ""
    qnh_ref: str = ""
    describe_qnh_ref: bool = True
    thrust_option: str | None = None
    manual_report_template_id: str = ""
    report_date_override: str = ""
