"""Domain models (Pydantic) shared across the app."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StorageLocation(str, Enum):
    FRIDGE = "fridge"
    SHELF = "shelf"
    FREEZER = "freezer"


class FoodGroup(str, Enum):
    VEGETABLES = "vegetables"
    FRUIT = "fruit"
    GRAINS = "grains"        # breads, cereals, rice, pasta, starchy veg
    DAIRY = "dairy"          # milk, cheese, yoghurt
    PROTEIN = "protein"      # meat, poultry, fish, eggs, legumes


class InventoryItem(BaseModel):
    """A single item the household currently has. Human-maintained (YAML in v1)."""

    name: str
    quantity: float
    unit: str
    best_before: date | None = None
    category: str | None = None
    opened: bool = False
    location: StorageLocation = StorageLocation.FRIDGE


class NutritionFacts(BaseModel):
    """Per-serving nutrition for a recipe (subset relevant to toddler targets)."""

    energy_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None
    fibre_g: float | None = None
    iron_mg: float | None = None
    calcium_mg: float | None = None
    sodium_mg: float | None = None


class Ingredient(BaseModel):
    name: str
    quantity: float
    unit: str


class Recipe(BaseModel):
    """A validated toddler dinner recipe (stored in Postgres)."""

    id: int | None = None
    title: str
    ingredients: list[Ingredient]
    steps: list[str]
    nutrition: NutritionFacts = Field(default_factory=NutritionFacts)
    texture: str | None = None  # e.g. "soft mash", "small soft pieces"
    min_age_months: int = 12
    hazard_flags: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # Servings of each food group this dinner contributes (best-effort, set by seed/LLM).
    food_groups: dict[FoodGroup, float] = Field(default_factory=dict)
    approved: bool = False   # in the cookbook / eligible for auto-suggestion
    cooked: bool = False     # has been finalised/eaten at least once (drives history)
    source: str = "seed"  # seed | llm | manual


class MenuItem(BaseModel):
    recipe: Recipe
    servings: float = 1.0


class Menu(BaseModel):
    """A generated menu for a given date (tonight or planned)."""

    id: int | None = None
    for_date: date
    items: list[MenuItem]
    generated_at: datetime = Field(default_factory=_utcnow)
    notes: str | None = None


class HistoryEntry(BaseModel):
    """A cooked/served dinner on a date, with its (full) recipe for the history view."""

    served_on: date
    recipe: Recipe


class ShoppingItem(BaseModel):
    name: str
    quantity: float
    unit: str
    est_unit_cost: float | None = None
    est_total_cost: float | None = None
    store: str | None = None
    on_special: bool = False


class ShoppingList(BaseModel):
    """Machine-generated; persisted in Postgres alongside its menu."""

    id: int | None = None
    menu_id: int | None = None
    items: list[ShoppingItem]
    budget: float | None = None
    estimated_total: float | None = None
    generated_at: datetime = Field(default_factory=_utcnow)


class SupermarketProduct(BaseModel):
    name: str
    unit: str | None = None
    price: float | None = None
    on_special: bool = False
    available: bool = True


class SupermarketSnapshot(BaseModel):
    """Timestamped per-store availability + specials (persisted in Postgres)."""

    id: int | None = None
    store: str
    captured_at: datetime = Field(default_factory=_utcnow)
    products: list[SupermarketProduct] = Field(default_factory=list)
