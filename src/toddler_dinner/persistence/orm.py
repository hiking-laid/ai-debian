"""SQLAlchemy ORM models — normalized schema (see DESIGN.md §6).

Fully relational (no JSON blobs) so the data is queryable for future analysis. Every table and
column carries a `comment=` (issue #15, database discipline) — these become Postgres
`COMMENT ON TABLE/COLUMN`, so the schema is self-documenting in `psql`/`\d+` and generated DDL.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class RecipeORM(Base):
    __tablename__ = "recipes"
    __table_args__ = {"comment": "Validated toddler dinner recipes; the cookbook + generation store."}

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    title: Mapped[str] = mapped_column(
        String(200), index=True, comment="Dish name; deduped case-insensitively."
    )
    min_age_months: Mapped[int] = mapped_column(
        Integer, default=12, comment="Minimum toddler age (months) the recipe suits."
    )
    texture: Mapped[str | None] = mapped_column(
        String(120), nullable=True, comment="Texture note, e.g. 'soft mash' (optional)."
    )
    source: Mapped[str] = mapped_column(
        String(20), default="seed", comment="Origin of the recipe: seed | llm | manual."
    )
    approved: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True, comment="In the cookbook / auto-suggestable."
    )
    cooked: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True,
        comment="Has been eaten (drives history); not auto-suggested on its own.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, comment="Row creation timestamp (UTC)."
    )

    ingredients: Mapped[list[IngredientORM]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="IngredientORM.position"
    )
    steps: Mapped[list[RecipeStepORM]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeStepORM.position"
    )
    equipment: Mapped[list[RecipeEquipmentORM]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeEquipmentORM.position"
    )
    tips: Mapped[list[RecipeTipORM]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeTipORM.position"
    )
    nutrition: Mapped[RecipeNutritionORM | None] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", uselist=False
    )
    food_groups: Mapped[list[RecipeFoodGroupORM]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    tags: Mapped[list[RecipeTagORM]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    hazards: Mapped[list[RecipeHazardORM]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class IngredientORM(Base):
    __tablename__ = "ingredients"
    __table_args__ = {"comment": "Recipe ingredients with quantity + unit, ordered by position."}

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True,
        comment="Owning recipe (FK, cascade delete).",
    )
    name: Mapped[str] = mapped_column(String(120), comment="Ingredient name.")
    quantity: Mapped[float] = mapped_column(Float, comment="Amount to use.")
    unit: Mapped[str] = mapped_column(String(40), comment="Unit for the amount, e.g. g / each / cup.")
    position: Mapped[int] = mapped_column(
        Integer, default=0, comment="Display order within the recipe."
    )

    recipe: Mapped[RecipeORM] = relationship(back_populates="ingredients")


class RecipeStepORM(Base):
    __tablename__ = "recipe_steps"
    __table_args__ = {"comment": "Method steps (one action per row), ordered by position."}

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True,
        comment="Owning recipe (FK, cascade delete).",
    )
    position: Mapped[int] = mapped_column(Integer, default=0, comment="Step order.")
    text: Mapped[str] = mapped_column(Text, comment="Step instruction text.")

    recipe: Mapped[RecipeORM] = relationship(back_populates="steps")


class RecipeEquipmentORM(Base):
    __tablename__ = "recipe_equipment"
    __table_args__ = {"comment": "Equipment needed for the recipe, ordered by position."}

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True,
        comment="Owning recipe (FK, cascade delete).",
    )
    position: Mapped[int] = mapped_column(Integer, default=0, comment="Display order.")
    text: Mapped[str] = mapped_column(Text, comment="Equipment item.")

    recipe: Mapped[RecipeORM] = relationship(back_populates="equipment")


class RecipeTipORM(Base):
    __tablename__ = "recipe_tips"
    __table_args__ = {"comment": "Cooking tips for the recipe, ordered by position."}

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True,
        comment="Owning recipe (FK, cascade delete).",
    )
    position: Mapped[int] = mapped_column(Integer, default=0, comment="Display order.")
    text: Mapped[str] = mapped_column(Text, comment="Tip text.")

    recipe: Mapped[RecipeORM] = relationship(back_populates="tips")


class RecipeStickerORM(Base):
    """Post-cook handwritten note pinned to a recipe / section / Method step."""

    __tablename__ = "recipe_stickers"
    __table_args__ = {
        "comment": "Post-cook handwritten notes pinned to a recipe / section / Method step."
    }

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True,
        comment="Owning recipe (FK, cascade delete).",
    )
    content: Mapped[str] = mapped_column(Text, comment="Handwritten note (<=280 chars).")
    target_section: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
        comment="Pinned section: ingredients|equipment|method|tips, else general (optional).",
    )
    # Deleting the pinned step demotes the sticker to general (SET NULL), never deletes it.
    target_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipe_steps.id", ondelete="SET NULL"), nullable=True,
        comment="Pinned Method step (FK; SET NULL on delete demotes the note to general).",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, comment="Row creation timestamp (UTC)."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
        comment="Last update timestamp (UTC).",
    )


class RecipeNutritionORM(Base):
    __tablename__ = "recipe_nutrition"
    __table_args__ = {"comment": "Per-serving nutrition for a recipe (1:1 with recipes)."}

    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True,
        comment="Owning recipe (PK + FK, cascade delete).",
    )
    energy_kcal: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Energy (kcal) per serving."
    )
    protein_g: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Protein (g) per serving."
    )
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Fat (g) per serving.")
    carbs_g: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Carbohydrate (g) per serving."
    )
    fibre_g: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Fibre (g) per serving."
    )
    iron_mg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Iron (mg) per serving."
    )
    calcium_mg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Calcium (mg) per serving."
    )
    sodium_mg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Sodium (mg) per serving."
    )

    recipe: Mapped[RecipeORM] = relationship(back_populates="nutrition")


class RecipeFoodGroupORM(Base):
    __tablename__ = "recipe_food_groups"
    __table_args__ = {
        "comment": "Food-group servings a recipe contributes (soft nutrition targets)."
    }

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True,
        comment="Owning recipe (FK, cascade delete).",
    )
    food_group: Mapped[str] = mapped_column(
        String(30), comment="Food group: vegetables|fruit|grains|dairy|protein."
    )
    servings: Mapped[float] = mapped_column(Float, comment="Servings of that food group.")

    recipe: Mapped[RecipeORM] = relationship(back_populates="food_groups")


class RecipeTagORM(Base):
    __tablename__ = "recipe_tags"
    __table_args__ = {"comment": "Free-form tags on a recipe."}

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True,
        comment="Owning recipe (FK, cascade delete).",
    )
    tag: Mapped[str] = mapped_column(String(60), comment="Tag label.")

    recipe: Mapped[RecipeORM] = relationship(back_populates="tags")


class RecipeHazardORM(Base):
    __tablename__ = "recipe_hazards"
    __table_args__ = {"comment": "Safety hazard flags on a recipe (e.g. choking risk)."}

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True,
        comment="Owning recipe (FK, cascade delete).",
    )
    flag: Mapped[str] = mapped_column(String(60), comment="Hazard flag label.")

    recipe: Mapped[RecipeORM] = relationship(back_populates="hazards")


class MenuORM(Base):
    __tablename__ = "menus"
    __table_args__ = {"comment": "Generated menus (tonight + planned)."}

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    for_date: Mapped[date] = mapped_column(
        Date, index=True, comment="Date the menu is for (household timezone)."
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, comment="When the menu was generated (UTC)."
    )
    notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Optional free-text notes."
    )

    items: Mapped[list[MenuItemORM]] = relationship(
        back_populates="menu", cascade="all, delete-orphan"
    )


class MenuItemORM(Base):
    __tablename__ = "menu_items"
    __table_args__ = {"comment": "Recipes placed on a menu, with servings."}

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    menu_id: Mapped[int] = mapped_column(
        ForeignKey("menus.id", ondelete="CASCADE"), index=True,
        comment="Owning menu (FK, cascade delete).",
    )
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id"), index=True, comment="Referenced recipe (FK)."
    )
    servings: Mapped[float] = mapped_column(Float, default=1.0, comment="Number of servings.")

    menu: Mapped[MenuORM] = relationship(back_populates="items")
    recipe: Mapped[RecipeORM] = relationship()


class ShoppingListORM(Base):
    __tablename__ = "shopping_lists"
    __table_args__ = {
        "comment": "Groceries lists linked to a menu. budget/estimated_total reserved for "
        "future supermarket integration."
    }

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    menu_id: Mapped[int | None] = mapped_column(
        ForeignKey("menus.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Source menu (FK; SET NULL on delete; optional).",
    )
    budget: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Budget cap (future; unused in v1)."
    )
    estimated_total: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Estimated total cost (future; unused in v1)."
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, comment="When the list was generated (UTC)."
    )

    items: Mapped[list[ShoppingItemORM]] = relationship(
        back_populates="shopping_list", cascade="all, delete-orphan"
    )


class ShoppingItemORM(Base):
    __tablename__ = "shopping_items"
    __table_args__ = {
        "comment": "Items on a shopping list. Cost/store/on_special reserved for future "
        "supermarket integration."
    }

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    shopping_list_id: Mapped[int] = mapped_column(
        ForeignKey("shopping_lists.id", ondelete="CASCADE"), index=True,
        comment="Owning shopping list (FK, cascade delete).",
    )
    name: Mapped[str] = mapped_column(String(120), comment="Item name.")
    quantity: Mapped[float] = mapped_column(Float, comment="Quantity to buy.")
    unit: Mapped[str] = mapped_column(String(40), comment="Unit for the quantity.")
    est_unit_cost: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Estimated unit cost (future; unused in v1)."
    )
    est_total_cost: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Estimated total cost (future; unused in v1)."
    )
    store: Mapped[str | None] = mapped_column(
        String(60), nullable=True, comment="Store name (future; unused in v1)."
    )
    on_special: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Whether it's on special (future; unused in v1)."
    )

    shopping_list: Mapped[ShoppingListORM] = relationship(back_populates="items")


class DinnerHistoryORM(Base):
    __tablename__ = "dinner_history"
    __table_args__ = {
        "comment": "What was served and when; drives variety exclusion + the history view. "
        "(recipe_id, served_on) is the primary key, so re-recording a dinner the same day "
        "is an idempotent upsert, not a duplicate."
    }

    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True,
        comment="Served recipe (PK part + FK, cascade delete).",
    )
    served_on: Mapped[date] = mapped_column(
        Date, primary_key=True, index=True, comment="Date served (PK part; household timezone)."
    )
    title: Mapped[str] = mapped_column(
        String(200), comment="Recipe title snapshot at serve time."
    )


class InventoryItemORM(Base):
    __tablename__ = "inventory_items"
    __table_args__ = {
        "comment": "Household catalog of stocked foods; matching keys off the unique name, "
        "not amounts. Seeded (all 'none') on initial deployment; a future UI edits it."
    }

    id: Mapped[int] = mapped_column(primary_key=True, comment="Surrogate primary key.")
    name: Mapped[str] = mapped_column(
        String(120), unique=True, index=True,
        comment="Food name; unique catalog key (case-insensitive dedup in the repo).",
    )
    status: Mapped[str] = mapped_column(
        String(10), default="have", comment="Coarse stock status: have | low | none."
    )
    quantity: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Optional amount; unused by matching/groceries."
    )
    unit: Mapped[str | None] = mapped_column(
        String(40), nullable=True, comment="Optional unit; unused by matching/groceries."
    )
    best_before: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="Optional best-before date; display-only."
    )
    category: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="Food category, e.g. protein / vegetable."
    )
    opened: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Whether the item is opened (carried, unused)."
    )
    location: Mapped[str] = mapped_column(
        String(20), default="fridge", comment="Storage location: fridge | shelf | freezer."
    )
