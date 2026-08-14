"""SQLAlchemy ORM models — normalized schema (see DESIGN.md §6).

Fully relational (no JSON blobs) so the data is queryable for future analysis.
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

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    min_age_months: Mapped[int] = mapped_column(Integer, default=12)
    texture: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="seed")
    approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    cooked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

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

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, default=0)

    recipe: Mapped[RecipeORM] = relationship(back_populates="ingredients")


class RecipeStepORM(Base):
    __tablename__ = "recipe_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)

    recipe: Mapped[RecipeORM] = relationship(back_populates="steps")


class RecipeEquipmentORM(Base):
    __tablename__ = "recipe_equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)

    recipe: Mapped[RecipeORM] = relationship(back_populates="equipment")


class RecipeTipORM(Base):
    __tablename__ = "recipe_tips"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)

    recipe: Mapped[RecipeORM] = relationship(back_populates="tips")


class RecipeStickerORM(Base):
    """Post-cook handwritten note pinned to a recipe / section / Method step."""

    __tablename__ = "recipe_stickers"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    target_section: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Deleting the pinned step demotes the sticker to general (SET NULL), never deletes it.
    target_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipe_steps.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class RecipeNutritionORM(Base):
    __tablename__ = "recipe_nutrition"

    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True
    )
    energy_kcal: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fibre_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    iron_mg: Mapped[float | None] = mapped_column(Float, nullable=True)
    calcium_mg: Mapped[float | None] = mapped_column(Float, nullable=True)
    sodium_mg: Mapped[float | None] = mapped_column(Float, nullable=True)

    recipe: Mapped[RecipeORM] = relationship(back_populates="nutrition")


class RecipeFoodGroupORM(Base):
    __tablename__ = "recipe_food_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    food_group: Mapped[str] = mapped_column(String(30))
    servings: Mapped[float] = mapped_column(Float)

    recipe: Mapped[RecipeORM] = relationship(back_populates="food_groups")


class RecipeTagORM(Base):
    __tablename__ = "recipe_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    tag: Mapped[str] = mapped_column(String(60))

    recipe: Mapped[RecipeORM] = relationship(back_populates="tags")


class RecipeHazardORM(Base):
    __tablename__ = "recipe_hazards"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    flag: Mapped[str] = mapped_column(String(60))

    recipe: Mapped[RecipeORM] = relationship(back_populates="hazards")


class MenuORM(Base):
    __tablename__ = "menus"

    id: Mapped[int] = mapped_column(primary_key=True)
    for_date: Mapped[date] = mapped_column(Date, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list[MenuItemORM]] = relationship(
        back_populates="menu", cascade="all, delete-orphan"
    )


class MenuItemORM(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id", ondelete="CASCADE"), index=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), index=True)
    servings: Mapped[float] = mapped_column(Float, default=1.0)

    menu: Mapped[MenuORM] = relationship(back_populates="items")
    recipe: Mapped[RecipeORM] = relationship()


class ShoppingListORM(Base):
    __tablename__ = "shopping_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    menu_id: Mapped[int | None] = mapped_column(
        ForeignKey("menus.id", ondelete="SET NULL"), nullable=True, index=True
    )
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    items: Mapped[list[ShoppingItemORM]] = relationship(
        back_populates="shopping_list", cascade="all, delete-orphan"
    )


class ShoppingItemORM(Base):
    __tablename__ = "shopping_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    shopping_list_id: Mapped[int] = mapped_column(
        ForeignKey("shopping_lists.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(40))
    # Pricing columns are nullable — reserved for the future supermarket integration.
    est_unit_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    est_total_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    store: Mapped[str | None] = mapped_column(String(60), nullable=True)
    on_special: Mapped[bool] = mapped_column(Boolean, default=False)

    shopping_list: Mapped[ShoppingListORM] = relationship(back_populates="items")


class DinnerHistoryORM(Base):
    __tablename__ = "dinner_history"

    # One dinner per recipe per day: (recipe_id, served_on) is the primary key, so cooking the
    # same recipe twice in a day is an idempotent upsert rather than a duplicate row.
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True
    )
    served_on: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
