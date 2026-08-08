"""Provider interfaces (abstract seams) — swap implementations without touching core."""

from __future__ import annotations

from abc import ABC, abstractmethod

from toddler_dinner.models import (
    InventoryItem,
    Recipe,
    SupermarketSnapshot,
)


class InventoryProvider(ABC):
    """Source of current fridge/shelf contents. v1: YAML file. Later: photo/barcode."""

    @abstractmethod
    def list_items(self) -> list[InventoryItem]:
        ...


class SupermarketProvider(ABC):
    """Source of local store availability + specials. v1: Playwright scrape."""

    @abstractmethod
    def fetch_snapshot(self, chain: str, store_name: str, store_url: str | None = None) -> SupermarketSnapshot:
        ...


class LLMProvider(ABC):
    """Generative model behind an interface. v1: hosted API. Later: NAS Ollama."""

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        ...

    @abstractmethod
    def generate_recipe(self, prompt: str) -> Recipe:
        ...
