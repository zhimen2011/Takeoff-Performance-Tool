"""Manual takeoff report template models and registry."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from stas_app.models.request import PerformanceRequest


@dataclass(frozen=True)
class ManualTakeoffReportTemplate:
    """One selectable manual takeoff report template."""

    id: str
    label: str
    filename: str
    aircraft_codes: tuple[str, ...]
    thrust_options: tuple[str, ...]

    @property
    def normalized_aircraft_codes(self) -> tuple[str, ...]:
        return tuple(_normalize_token(code) for code in self.aircraft_codes)

    @property
    def normalized_thrust_options(self) -> tuple[str, ...]:
        return tuple(_normalize_token(option) for option in self.thrust_options)


class ManualTakeoffTemplateRegistry:
    """Load and validate manual takeoff report templates."""

    def __init__(self, templates: tuple[ManualTakeoffReportTemplate, ...]) -> None:
        if not templates:
            raise ValueError("Manual takeoff report template registry is empty")

        ids = [template.id for template in templates]
        duplicated = sorted({template_id for template_id in ids if ids.count(template_id) > 1})
        if duplicated:
            raise ValueError(f"Duplicated manual takeoff report template ids: {', '.join(duplicated)}")

        self._templates = templates
        self._by_id = {template.id: template for template in templates}

    @classmethod
    def from_directory(cls, template_dir: str | Path) -> "ManualTakeoffTemplateRegistry":
        directory = Path(template_dir)
        return cls.from_file(directory / "templates.toml")

    @classmethod
    def from_file(cls, config_path: str | Path) -> "ManualTakeoffTemplateRegistry":
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Manual takeoff report template config does not exist: {path}")

        with path.open("rb") as file:
            data = tomllib.load(file)

        raw_templates = data.get("templates")
        if not isinstance(raw_templates, list):
            raise ValueError("Manual takeoff report template config must contain [[templates]] entries")

        templates: list[ManualTakeoffReportTemplate] = []
        for item in raw_templates:
            if not isinstance(item, dict):
                raise ValueError("Manual takeoff report template entry must be a table")
            templates.append(
                ManualTakeoffReportTemplate(
                    id=_required_string(item, "id"),
                    label=_required_string(item, "label"),
                    filename=_required_string(item, "filename"),
                    aircraft_codes=_string_tuple(item, "aircraft_codes"),
                    thrust_options=_string_tuple(item, "thrust_options"),
                )
            )
        return cls(tuple(templates))

    def all(self) -> tuple[ManualTakeoffReportTemplate, ...]:
        return self._templates

    def get(self, template_id: str) -> ManualTakeoffReportTemplate:
        key = template_id.strip()
        if key not in self._by_id:
            raise ValueError(f"Unknown manual takeoff report template: {template_id}")
        return self._by_id[key]

    def validate_request(self, template_id: str, request: PerformanceRequest) -> str:
        """Return an error message when a request is incompatible, otherwise empty."""

        template = self.get(template_id)
        aircraft_code = _normalize_token(request.aircraft_code)
        thrust_option = _normalize_token(request.thrust_option or "")

        if aircraft_code not in template.normalized_aircraft_codes:
            return (
                f"手册起飞分析模板“{template.label}”不适用于机型 {request.aircraft_code or '-'}"
            )

        if thrust_option not in template.normalized_thrust_options:
            display_thrust = request.thrust_option or "正常"
            return (
                f"手册起飞分析模板“{template.label}”不适用于推力选项 {display_thrust}"
            )

        return ""


def _required_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Manual takeoff report template value {key} must be a non-empty string")
    return value.strip()


def _string_tuple(data: dict[str, object], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"Manual takeoff report template value {key} must be a non-empty list")

    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"Manual takeoff report template value {key} must be a list of strings")
        result.append(item.strip())
    return tuple(result)


def _normalize_token(value: str) -> str:
    return value.strip().upper().replace(" ", "")
