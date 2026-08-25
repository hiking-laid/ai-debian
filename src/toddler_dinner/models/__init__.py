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


class StockStatus(str, Enum):
    HAVE = "have"    # on hand; may be the main ingredient
    LOW = "low"      # still usable, but not as the main ingredient; never auto-bought
    NONE = "none"    # out; bought if a chosen recipe needs it (staples exempt)


class FoodGroup(str, Enum):
    VEGETABLES = "vegetables"
    FRUIT = "fruit"
    GRAINS = "grains"        # breads, cereals, rice, pasta, starchy veg
    DAIRY = "dairy"          # milk, cheese, yoghurt
    PROTEIN = "protein"      # meat, poultry, fish, eggs, legumes


class InventoryItem(BaseModel):
    """A food the household stocks, with a coarse stock status. Human-maintained (YAML in v1)."""

    name: str
    status: StockStatus = StockStatus.HAVE
    quantity: float | None = None  # optional, unused by matching/groceries; kept for reversibility
    unit: str | None = None
    best_before: date | None = None  # display-only; nothing automated reads it
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
    equipment: list[str] = Field(default_factory=list)
    steps: list[str]  # the "Method": one action per step
    tips: list[str] = Field(default_factory=list)
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


# Sections a sticker may be pinned to (besides a specific Method step, or nothing = general).
STICKER_SECTIONS = ("ingredients", "equipment", "method", "tips")


class Sticker(BaseModel):
    """A post-cook handwritten note pinned to a recipe (general), a section, or a Method step.

    API-facing shape: the step target is a 0-based *index* into the recipe's Method; the DB stores
    it as a `recipe_steps.id` (resolved by the repository) so it survives step reordering.
    """

    id: int | None = None
    recipe_id: int
    content: str
    target_section: str | None = None      # one of STICKER_SECTIONS, else None
    target_step_index: int | None = None   # 0-based position within Method, else None
    created_at: datetime = Field(default_factory=_utcnow)


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
