"""Generate the STAS runtime APTRWY.RWY file from a master runway database."""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from stas_app.models.runway_database import AirportBlock
from stas_app.parsers.runway_database_parser import parse_runway_master_file
from stas_app.services.runway_intersection_generator import generate_intersections_for_airport_block


class RunwayRuntimeFileService:
    """Copy selected complete airport blocks from APTRWY_MASTER.RWY to APTRWY.RWY."""

    def __init__(
        self,
        master_file: str | Path,
        runtime_file: str | Path,
        backup_dir: str | Path | None = None,
    ) -> None:
        self.master_file = Path(master_file)
        self.runtime_file = Path(runtime_file)
        self.backup_dir = Path(backup_dir) if backup_dir else self.runtime_file.parent / "backups"

    def prepare_for_airports(self, airport_codes: Iterable[str]) -> Path:
        requested_codes = tuple(dict.fromkeys(code.strip().upper() for code in airport_codes if code.strip()))
        if not requested_codes:
            raise ValueError("至少需要一个机场才能生成 STAS 跑道文件")

        database = parse_runway_master_file(self.master_file)
        missing = tuple(code for code in requested_codes if code not in database.airports)
        if missing:
            raise ValueError(f"主跑道库缺少机场: {', '.join(missing)}")

        blocks = tuple(
            generate_intersections_for_airport_block(block)
            for block in database.selected_blocks_in_master_order(requested_codes)
        )
        if not blocks:
            raise ValueError("未能从主跑道库提取机场数据")

        content = self._render_runtime_file(database.preamble_lines, blocks)
        self.runtime_file.parent.mkdir(parents=True, exist_ok=True)
        self._backup_runtime_file()
        temp_path = self.runtime_file.with_name(f"{self.runtime_file.name}.tmp")
        temp_path.write_text(content, encoding=database.profile.encoding, newline=database.profile.line_ending)
        temp_path.replace(self.runtime_file)
        return self.runtime_file

    def _render_runtime_file(self, preamble_lines: tuple[str, ...], blocks: tuple[AirportBlock, ...]) -> str:
        lines: list[str] = []
        lines.extend(preamble_lines)
        while lines and not lines[-1].strip():
            lines.pop()
        if lines:
            lines.append("")

        for index, block in enumerate(blocks):
            if index > 0:
                lines.append("")
            lines.extend(block.raw_lines)

        return "\n".join(lines).rstrip("\n") + "\n"

    def _backup_runtime_file(self) -> None:
        if not self.runtime_file.exists():
            return

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = self.backup_dir / f"{self.runtime_file.stem}_{timestamp}{self.runtime_file.suffix}"
        shutil.copy2(self.runtime_file, backup_path)
