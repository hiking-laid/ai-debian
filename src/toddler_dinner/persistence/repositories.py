"""Postgres-backed repositories + domain<->ORM mapping."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from toddler_dinner.models import (
    FoodGroup,
    HistoryEntry,
    Ingredient,
    Menu,
    NutritionFacts,
    Recipe,
    ShoppingList,
)
from toddler_dinner.persistence import DinnerHistoryRepository, MenuRepository, RecipeRepository
from toddler_dinner.persistence.orm import (
    DinnerHistoryORM,
    IngredientORM,
    MenuItemORM,
    MenuORM,
    RecipeFoodGroupORM,
    RecipeHazardORM,
    RecipeNutritionORM,
    RecipeORM,
    RecipeStepORM,
    RecipeTagORM,
    ShoppingItemORM,
    ShoppingListORM,
)

# --- mapping ----------------------------------------------------------------

_NUTRITION_FIELDS = (
    "energy_kcal", "protein_g", "fat_g", "carbs_g",
    "fibre_g", "iron_mg", "calcium_mg", "sodium_mg",
)


def orm_to_recipe(row: RecipeORM) -> Recipe:
    nutrition = NutritionFacts()
    if row.nutrition is not None:
        nutrition = NutritionFacts(**{f: getattr(row.nutrition, f) for f in _NUTRITION_FIELDS})
    return Recipe(
        id=row.id,
        title=row.title,
        ingredients=[Ingredient(name=i.name, quantity=i.quantity, unit=i.unit) for i in row.ingredients],
        steps=[s.text for s in row.steps],
        nutrition=nutrition,
        texture=row.texture,
        min_age_months=row.min_age_months,
        hazard_flags=[h.flag for h in row.hazards],
        tags=[t.tag for t in row.tags],
        food_groups={FoodGroup(fg.food_group): fg.servings for fg in row.food_groups},
        approved=row.approved,
        cooked=row.cooked,
        source=row.source,
    )


def recipe_to_orm(recipe: Recipe) -> RecipeORM:
    row = RecipeORM(
        title=recipe.title,
        min_age_months=recipe.min_age_months,
        texture=recipe.texture,
        source=recipe.source,
        approved=recipe.approved,
    )
    row.ingredients = [
        IngredientORM(name=ing.name, quantity=ing.quantity, unit=ing.unit, position=idx)
        for idx, ing in enumerate(recipe.ingredients)
    ]
    row.steps = [RecipeStepORM(position=idx, text=text) for idx, text in enumerate(recipe.steps)]
    if any(getattr(recipe.nutrition, f) is not None for f in _NUTRITION_FIELDS):
        row.nutrition = RecipeNutritionORM(
            **{f: getattr(recipe.nutrition, f) for f in _NUTRITION_FIELDS}
        )
    row.food_groups = [
        RecipeFoodGroupORM(food_group=fg.value, servings=serv)
        for fg, serv in recipe.food_groups.items()
    ]
    row.tags = [RecipeTagORM(tag=t) for t in recipe.tags]
    row.hazards = [RecipeHazardORM(flag=f) for f in recipe.hazard_flags]
    return row


# --- repositories -----------------------------------------------------------

class PgRecipeRepository(RecipeRepository):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def approved_recipes(self) -> list[Recipe]:
        with self._sf() as s:
            rows = s.scalars(select(RecipeORM).where(RecipeORM.approved.is_(True))).all()
            return [orm_to_recipe(r) for r in rows]

    def add_recipe(self, recipe: Recipe) -> Recipe:
        with self._sf() as s:
            row = recipe_to_orm(recipe)
            s.add(row)
            s.commit()
            s.refresh(row)
            return orm_to_recipe(row)

    def find_by_title(self, title: str) -> Recipe | None:
        with self._sf() as s:
            row = s.scalars(
                select(RecipeORM).where(func.lower(RecipeORM.title) == title.lower())
            ).first()
            return orm_to_recipe(row) if row else None

    def _set_flag(self, recipe: Recipe, *, approved: bool | None = None,
                  cooked: bool | None = None) -> Recipe:
        """Dedup by title: flip flags on the existing row, or insert a new one."""
        with self._sf() as s:
            row = s.scalars(
                select(RecipeORM).where(func.lower(RecipeORM.title) == recipe.title.lower())
            ).first()
            if row is None:
                row = recipe_to_orm(recipe)
                s.add(row)
            if approved is not None:
                row.approved = approved
            if cooked is not None:
                row.cooked = cooked
            s.commit()
            s.refresh(row)
            return orm_to_recipe(row)

    def approve(self, recipe: Recipe) -> Recipe:
        return self._set_flag(recipe, approved=True)

    def mark_cooked(self, recipe: Recipe) -> Recipe:
        return self._set_flag(recipe, cooked=True)


class PgMenuRepository(MenuRepository):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def save_menu(self, menu: Menu) -> Menu:
        with self._sf() as s:
            row = MenuORM(for_date=menu.for_date, notes=menu.notes)
            row.items = [
                MenuItemORM(recipe_id=item.recipe.id, servings=item.servings)
                for item in menu.items
            ]
            s.add(row)
            s.commit()
            menu.id = row.id
            return menu

    def save_shopping_list(self, shopping_list: ShoppingList) -> ShoppingList:
        with self._sf() as s:
            row = ShoppingListORM(
                menu_id=shopping_list.menu_id,
                budget=shopping_list.budget,
                estimated_total=shopping_list.estimated_total,
            )
            row.items = [
                ShoppingItemORM(
                    name=i.name, quantity=i.quantity, unit=i.unit,
                    est_unit_cost=i.est_unit_cost, est_total_cost=i.est_total_cost,
                    store=i.store, on_special=i.on_special,
                )
                for i in shopping_list.items
            ]
            s.add(row)
            s.commit()
            shopping_list.id = row.id
            return shopping_list


class PgDinnerHistoryRepository(DinnerHistoryRepository):
    """Drives variety: recent dinner titles + recording what was served."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def recent_titles(self, within_days: int, on: date | None = None) -> list[str]:
        on = on or date.today()
        cutoff = on - timedelta(days=within_days)
        with self._sf() as s:
            rows = s.scalars(
                select(DinnerHistoryORM.title).where(DinnerHistoryORM.served_on >= cutoff)
            ).all()
            return list(rows)

    def record(self, title: str, served_on: date, recipe_id: int | None = None) -> None:
        """Upsert one dinner-history row keyed by (recipe_id, served_on).

        Recording the same recipe again for the same day is a no-op update (refreshes the
        title), never a duplicate row. A recipe_id is required by the composite key; when it's
        missing it is resolved from the title.
        """
        with self._sf() as s:
            if recipe_id is None:
                recipe_id = s.scalar(
                    select(RecipeORM.id).where(func.lower(RecipeORM.title) == title.lower())
                )
            if recipe_id is None:
                raise ValueError(
                    f"Cannot record dinner history for {title!r}: no matching recipe. "
                    "Save/cook the recipe first so it has an id."
                )
            s.merge(DinnerHistoryORM(recipe_id=recipe_id, served_on=served_on, title=title))
            s.commit()

    def recent(self, days: int, on: date | None = None) -> list[HistoryEntry]:
        on = on or date.today()
        cutoff = on - timedelta(days=days)
        with self._sf() as s:
            rows = s.scalars(
                select(DinnerHistoryORM)
                .where(DinnerHistoryORM.served_on >= cutoff)
                .order_by(DinnerHistoryORM.served_on.desc(), DinnerHistoryORM.recipe_id.desc())
            ).all()
            entries: list[HistoryEntry] = []
            for row in rows:
                recipe: Recipe | None = None
                if row.recipe_id is not None:
                    rec = s.get(RecipeORM, row.recipe_id)
                    if rec is not None:
                        recipe = orm_to_recipe(rec)
                if recipe is None:  # title-only history entry (e.g. legacy mark-served)
                    recipe = Recipe(title=row.title, ingredients=[], steps=[])
                entries.append(HistoryEntry(served_on=row.served_on, recipe=recipe))
            return entries
