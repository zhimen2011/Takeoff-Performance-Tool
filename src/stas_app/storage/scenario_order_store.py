"""Persist reusable Scenario order presets for the desktop UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ORDER_FIELDS = (
    "runway_condition",
    "contamination_depth",
    "thrust_option",
    "derate",
    "bleed",
    "anti_icing",
    "temperature_range",
    "wind_range",
    "qnh_ref",
    "describe_qnh_ref",
)
OPTIONAL_QUEUE_CONDITION_FIELDS = ("temperature_range", "wind_range", "qnh_ref", "describe_qnh_ref")


class ScenarioOrderStore:
    """Read and write airport-independent Scenario order presets."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load_all(self) -> dict[str, list[dict[str, str]]]:
        if not self.path.exists():
            return {}

        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}

        orders: dict[str, list[dict[str, str]]] = {}
        for name, items in data.items():
            if not isinstance(name, str) or not isinstance(items, list):
                continue
            clean_items = [self._clean_item(item) for item in items if isinstance(item, dict)]
            orders[name] = clean_items
        return orders

    def save_order(self, name: str, items: list[dict[str, str]]) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("队列方案名称不能为空")

        orders = self.load_all()
        orders[clean_name] = [self._clean_item(item) for item in items]
        self._write_all(orders)

    def delete_order(self, name: str) -> None:
        clean_name = name.strip()
        orders = self.load_all()
        if clean_name in orders:
            del orders[clean_name]
            self._write_all(orders)

    def _write_all(self, orders: dict[str, list[dict[str, str]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(orders, ensure_ascii=False, indent=2), encoding="utf-8")

    def _clean_item(self, item: dict[str, Any]) -> dict[str, str]:
        clean_item: dict[str, str] = {}
        for field in ORDER_FIELDS:
            if field in OPTIONAL_QUEUE_CONDITION_FIELDS and field not in item:
                continue
            clean_item[field] = str(item.get(field, "")).strip()
        return clean_item
