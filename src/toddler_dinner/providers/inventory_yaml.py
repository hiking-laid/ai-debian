"""v1 InventoryProvider: reads a human-maintained YAML file."""

from __future__ import annotations

from pathlib import Path

import yaml

from toddler_dinner.interfaces import InventoryProvider
from toddler_dinner.models import InventoryItem


class YamlInventoryProvider(InventoryProvider):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def list_items(self) -> list[InventoryItem]:
        if not self.path.exists():
            return []
        raw = yaml.safe_load(self.path.read_text()) or []
        return [InventoryItem.model_validate(item) for item in raw]
