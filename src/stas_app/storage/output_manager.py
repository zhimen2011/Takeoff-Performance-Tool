"""Manage per-run output directories and metadata files."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from stas_app.models.request import PerformanceRequest


SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


class OutputManager:
    """Create isolated output directories for STAS runs."""

    def __init__(self, output_root: str | Path) -> None:
        self.output_root = Path(output_root)

    def create_run_directory(self, request: PerformanceRequest, timestamp: datetime | None = None) -> Path:
        self.output_root.mkdir(parents=True, exist_ok=True)

        current_time = timestamp or datetime.now()
        base_name = "_".join(
            part
            for part in [
                current_time.strftime("%Y-%m-%d_%H%M%S"),
                self._safe_part(request.scenario_id) if request.scenario_id else "",
                self._safe_part(request.airport_code or "UNKNOWN"),
                self._safe_part(request.aircraft_code or "AIRCRAFT"),
            ]
            if part
        )

        run_dir = self.output_root / base_name
        suffix = 1
        while run_dir.exists():
            suffix += 1
            run_dir = self.output_root / f"{base_name}_{suffix}"

        run_dir.mkdir(parents=True)
        return run_dir

    def write_metadata(self, run_dir: str | Path, metadata: dict[str, Any]) -> Path:
        metadata_path = Path(run_dir) / "run_metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return metadata_path

    def _safe_part(self, value: str) -> str:
        cleaned = SAFE_NAME_PATTERN.sub("-", value.strip().upper()).strip("-")
        return cleaned or "UNKNOWN"
