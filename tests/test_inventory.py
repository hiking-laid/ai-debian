"""Inventory catalog: repository CRUD + ORM<->model mapping (no live DB needed)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from toddler_dinner.models import InventoryItem, StockStatus, StorageLocation
from toddler_dinner.persistence import InMemoryInventoryRepository
from toddler_dinner.persistence.orm import InventoryItemORM
from toddler_dinner.persistence.repositories import _apply_inventory_item, orm_to_inventory_item
from toddler_dinner.providers.inventory_yaml import YamlInventoryProvider

_SEED = Path(__file__).resolve().parents[1] / "data" / "inventory.seed.yaml"


# --- InMemoryInventoryRepository (CRUD port) --------------------------------

def test_upsert_many_dedups_by_name_case_insensitive():
    repo = InMemoryInventoryRepository()
    repo.upsert_many([InventoryItem(name="broccoli", status=StockStatus.HAVE)])
    # same name (case-insensitive) -> update, not a second row
    repo.upsert_many([InventoryItem(name="Broccoli", status=StockStatus.LOW, category="vegetable")])
    items = repo.list_items()
    assert len(items) == 1
    assert items[0].status == StockStatus.LOW
    assert items[0].category == "vegetable"


def test_set_status_and_missing_item():
    repo = InMemoryInventoryRepository([InventoryItem(name="rice", status=StockStatus.HAVE)])
    updated = repo.set_status("rice", StockStatus.NONE)
    assert updated is not None and updated.status == StockStatus.NONE
    assert repo.set_status("unknown", StockStatus.LOW) is None  # not in catalog


def test_delete():
    repo = InMemoryInventoryRepository([InventoryItem(name="milk")])
    assert repo.delete("MILK") is True
    assert repo.list_items() == []
    assert repo.delete("milk") is False  # already gone


def test_upsert_many_inserts_and_updates():
    repo = InMemoryInventoryRepository([InventoryItem(name="rice", status=StockStatus.HAVE)])
    n = repo.upsert_many([
        InventoryItem(name="rice", status=StockStatus.LOW),        # updates existing
        InventoryItem(name="broccoli", status=StockStatus.NONE),   # inserts new
    ])
    assert n == 2
    got = {i.name: i.status for i in repo.list_items()}
    assert got == {"rice": StockStatus.LOW, "broccoli": StockStatus.NONE}


# --- ORM <-> model mapping --------------------------------------------------

def test_inventory_mapping_round_trip():
    item = InventoryItem(
        name="tofu (firm)",
        status=StockStatus.LOW,
        best_before=date(2026, 8, 18),
        category="protein",
        location=StorageLocation.FRIDGE,
    )
    row = InventoryItemORM()
    _apply_inventory_item(row, item)
    assert row.status == "low"           # enum stored as its string value
    assert row.location == "fridge"
    back = orm_to_inventory_item(row)
    assert back.name == "tofu (firm)"
    assert back.status is StockStatus.LOW
    assert back.location is StorageLocation.FRIDGE
    assert back.best_before == date(2026, 8, 18)
    assert back.quantity is None and back.unit is None


# --- seed file --------------------------------------------------------------

def test_seed_file_loads_and_is_all_none():
    items = YamlInventoryProvider(_SEED).list_items()
    assert items, "seed file should not be empty"
    assert all(i.status is StockStatus.NONE for i in items)  # ships nothing on hand
    assert all(i.quantity is None and i.unit is None for i in items)
