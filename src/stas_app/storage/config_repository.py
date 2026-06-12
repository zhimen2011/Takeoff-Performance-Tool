"""Read application configuration from TOML files."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from stas_app.models.config import (
    MANUAL_PDF_REPORT_FILENAME,
    MANUAL_WORD_REPORT_FILENAME,
    QUEUE_MANUAL_PDF_REPORT_FILENAME,
    QUEUE_MANUAL_WORD_REPORT_FILENAME,
    QUEUE_TEMPORARY_PDF_REPORT_FILENAME,
    QUEUE_TEMPORARY_WORD_REPORT_FILENAME,
    TEMPORARY_PDF_REPORT_FILENAME,
    TEMPORARY_WORD_REPORT_FILENAME,
    AppConfig,
)


class ConfigError(ValueError):
    """Raised when application configuration is missing or malformed."""


def load_app_config(config_path: str | Path, base_dir: str | Path | None = None) -> AppConfig:
    """Load application config and resolve relative paths against base_dir."""

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Application config does not exist: {path}")

    with path.open("rb") as file:
        data = tomllib.load(file)

    root = (Path(base_dir) if base_dir is not None else Path.cwd()).resolve()
    paths = _table(data, "paths", required=True)
    stas = _table(data, "stas", required=False)
    reports = _table(data, "reports", required=False)

    return AppConfig(
        aircraft_config_dir=_path(paths, "aircraft_config_dir", root),
        template_dir=_path(paths, "template_dir", root),
        airport_runway_file=_path(paths, "airport_runway_file", root),
        stas_executable_path=_path(paths, "stas_executable_path", root),
        stas_work_dir=_path(paths, "stas_work_dir", root),
        output_root=_path(paths, "output_root", root),
        airport_runway_master_file=_optional_path(paths, "airport_runway_master_file", root),
        manual_report_template_dir=_path_value(paths, "manual_report_template_dir", root, "templates/reports/manual_takeoff"),
        logo_path=_optional_path(paths, "logo_path", root),
        timeout_seconds=_positive_int(stas, "timeout_seconds", 1200),
        executable_args=_string_tuple(stas, "executable_args", ()),
        input_filename=_string_value(stas, "input_filename", "STASINP"),
        output_filename=_string_value(stas, "output_filename", "STASOUT.out"),
        error_filename=_string_value(stas, "error_filename", "STASERR"),
        word_report_filename=_string_value(reports, "word_report_filename", TEMPORARY_WORD_REPORT_FILENAME),
        pdf_report_filename=_string_value(reports, "pdf_report_filename", TEMPORARY_PDF_REPORT_FILENAME),
        manual_word_report_filename=_string_value(reports, "manual_word_report_filename", MANUAL_WORD_REPORT_FILENAME),
        manual_pdf_report_filename=_string_value(reports, "manual_pdf_report_filename", MANUAL_PDF_REPORT_FILENAME),
        queue_word_report_filename=_string_value(reports, "queue_word_report_filename", QUEUE_TEMPORARY_WORD_REPORT_FILENAME),
        queue_pdf_report_filename=_string_value(reports, "queue_pdf_report_filename", QUEUE_TEMPORARY_PDF_REPORT_FILENAME),
        queue_manual_word_report_filename=_string_value(
            reports,
            "queue_manual_word_report_filename",
            QUEUE_MANUAL_WORD_REPORT_FILENAME,
        ),
        queue_manual_pdf_report_filename=_string_value(
            reports,
            "queue_manual_pdf_report_filename",
            QUEUE_MANUAL_PDF_REPORT_FILENAME,
        ),
    )


def _table(data: dict[str, Any], name: str, required: bool) -> dict[str, Any]:
    value = data.get(name)
    if value is None:
        if required:
            raise ConfigError(f"Missing [{name}] section in application config")
        return {}

    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] section must be a table")

    return value


def _path(data: dict[str, Any], key: str, base_dir: Path) -> Path:
    value = _required_string(data, key)
    return _resolve_path(value, base_dir)


def _path_value(data: dict[str, Any], key: str, base_dir: Path, default: str) -> Path:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Config value paths.{key} must be a non-empty string")
    return _resolve_path(value, base_dir)


def _optional_path(data: dict[str, Any], key: str, base_dir: Path) -> Path | None:
    value = data.get(key)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ConfigError(f"Config value paths.{key} must be a string")
    return _resolve_path(value, base_dir)


def _resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Config value paths.{key} is required")
    return value


def _string_value(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Config value {key} must be a non-empty string")
    return value


def _string_tuple(data: dict[str, Any], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = data.get(key, default)
    if not isinstance(value, list | tuple):
        raise ConfigError(f"Config value {key} must be a list of strings")

    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ConfigError(f"Config value {key} must be a list of strings")
        items.append(item)
    return tuple(items)


def _positive_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or value <= 0:
        raise ConfigError(f"Config value {key} must be a positive integer")
    return value
