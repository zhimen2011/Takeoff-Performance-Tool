"""Temporary takeoff report template models and registry."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TemporaryTakeoffReportTemplate:
    """One temporary takeoff report template."""

    id: str
    label: str
    filename: str


class TemporaryTakeoffTemplateRegistry:
    """Load temporary takeoff report templates from TOML."""

    def __init__(self, templates: tuple[TemporaryTakeoffReportTemplate, ...]) -> None:
        if not templates:
            raise ValueError("Temporary takeoff report template registry is empty")

        ids = [template.id for template in templates]
        duplicated = sorted({template_id for template_id in ids if ids.count(template_id) > 1})
        if duplicated:
            raise ValueError(f"Duplicated temporary takeoff report template ids: {', '.join(duplicated)}")

        self._templates = templates
        self._by_id = {template.id: template for template in templates}

    @classmethod
    def from_directory(cls, template_dir: str | Path) -> "TemporaryTakeoffTemplateRegistry":
        directory = Path(template_dir)
        return cls.from_file(directory / "temporary_templates.toml")

    @classmethod
    def from_file(cls, config_path: str | Path) -> "TemporaryTakeoffTemplateRegistry":
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Temporary takeoff report template config does not exist: {path}")

        with path.open("rb") as file:
            data = tomllib.load(file)

        raw_templates = data.get("templates")
        if not isinstance(raw_templates, list):
            raise ValueError("Temporary takeoff report template config must contain [[templates]] entries")

        templates: list[TemporaryTakeoffReportTemplate] = []
        for item in raw_templates:
            if not isinstance(item, dict):
                raise ValueError("Temporary takeoff report template entry must be a table")
            templates.append(
                TemporaryTakeoffReportTemplate(
                    id=_required_string(item, "id"),
                    label=_required_string(item, "label"),
                    filename=_required_string(item, "filename"),
                )
            )
        return cls(tuple(templates))

    def all(self) -> tuple[TemporaryTakeoffReportTemplate, ...]:
        return self._templates

    def get(self, template_id: str) -> TemporaryTakeoffReportTemplate:
        key = template_id.strip()
        if key not in self._by_id:
            raise ValueError(f"Unknown temporary takeoff report template: {template_id}")
        return self._by_id[key]


def _required_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Temporary takeoff report template value {key} must be a non-empty string")
    return value.strip()
