"""Postgres-backed repositories + domain<->ORM mapping."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from toddler_dinner.models import (
    FoodGroup,
    HistoryEntry,
    Ingredient,
    InventoryItem,
    Menu,
    NutritionFacts,
    Recipe,
    ShoppingList,
    StockStatus,
    StorageLocation,
    Sticker,
)
from toddler_dinner.persistence import (
    DinnerHistoryRepository,
    InventoryRepository,
    MenuRepository,
    RecipeRepository,
    StickerRepository,
)
from toddler_dinner.persistence.orm import (
    DinnerHistoryORM,
    IngredientORM,
    InventoryItemORM,
    MenuItemORM,
    MenuORM,
    RecipeEquipmentORM,
    RecipeFoodGroupORM,
    RecipeHazardORM,
    RecipeNutritionORM,
    RecipeORM,
    RecipeStepORM,
    RecipeStickerORM,
    RecipeTagORM,
    RecipeTipORM,
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
        equipment=[e.text for e in row.equipment],
        steps=[s.text for s in row.steps],
        tips=[t.text for t in row.tips],
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
    row.equipment = [
        RecipeEquipmentORM(position=idx, text=text) for idx, text in enumerate(recipe.equipment)
    ]
    row.tips = [RecipeTipORM(position=idx, text=text) for idx, text in enumerate(recipe.tips)]
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


def orm_to_inventory_item(row: InventoryItemORM) -> InventoryItem:
    return InventoryItem(
        name=row.name,
        status=StockStatus(row.status),
        quantity=row.quantity,
        unit=row.unit,
        best_before=row.best_before,
        category=row.category,
        opened=row.opened,
        location=StorageLocation(row.location),
    )


def _apply_inventory_item(row: InventoryItemORM, item: InventoryItem) -> None:
    row.name = item.name
    row.status = item.status.value
    row.quantity = item.quantity
    row.unit = item.unit
    row.best_before = item.best_before
    row.category = item.category
    row.opened = item.opened
    row.location = item.location.value


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
        """The last `days` cooked dinners by **count**, most recent first (DESIGN: "the last
        history_days cooked dinners"). A count, not a date window, so the history view stays
        populated even when the last dinner was a while ago. `on` is accepted for interface
        parity but unused."""
        with self._sf() as s:
            rows = s.scalars(
                select(DinnerHistoryORM)
                .order_by(DinnerHistoryORM.served_on.desc(), DinnerHistoryORM.recipe_id.desc())
                .limit(days)
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


class PgStickerRepository(StickerRepository):
    """CRUD for post-cook stickers. Translates step index <-> recipe_steps.id."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def _step_ids(self, s: Session, recipe_id: int) -> list[int]:
        """Method step ids for a recipe, ordered by position (index -> id)."""
        return list(
            s.scalars(
                select(RecipeStepORM.id)
                .where(RecipeStepORM.recipe_id == recipe_id)
                .order_by(RecipeStepORM.position)
            ).all()
        )

    def _index_for_step_id(self, s: Session, recipe_id: int, step_id: int | None) -> int | None:
        if step_id is None:
            return None
        ids = self._step_ids(s, recipe_id)
        return ids.index(step_id) if step_id in ids else None

    def _step_id_for_index(self, s: Session, recipe_id: int, index: int | None) -> int | None:
        if index is None:
            return None
        ids = self._step_ids(s, recipe_id)
        return ids[index] if 0 <= index < len(ids) else None

    def _to_model(self, s: Session, row: RecipeStickerORM) -> Sticker:
        return Sticker(
            id=row.id,
            recipe_id=row.recipe_id,
            content=row.content,
            target_section=row.target_section,
            target_step_index=self._index_for_step_id(s, row.recipe_id, row.target_step_id),
            created_at=row.created_at,
        )

    def list_for_recipe(self, recipe_id: int) -> list[Sticker]:
        with self._sf() as s:
            rows = s.scalars(
                select(RecipeStickerORM)
                .where(RecipeStickerORM.recipe_id == recipe_id)
                .order_by(RecipeStickerORM.created_at, RecipeStickerORM.id)
            ).all()
            return [self._to_model(s, r) for r in rows]

    def create(
        self,
        recipe_id: int,
        content: str,
        target_section: str | None = None,
        target_step_index: int | None = None,
    ) -> Sticker:
        with self._sf() as s:
            row = RecipeStickerORM(
                recipe_id=recipe_id,
                content=content,
                target_section=target_section,
                target_step_id=self._step_id_for_index(s, recipe_id, target_step_index),
            )
            s.add(row)
            s.commit()
            s.refresh(row)
            return self._to_model(s, row)

    def update(
        self,
        sticker_id: int,
        *,
        content: str | None = None,
        set_target: bool = False,
        target_section: str | None = None,
        target_step_index: int | None = None,
    ) -> Sticker | None:
        with self._sf() as s:
            row = s.get(RecipeStickerORM, sticker_id)
            if row is None:
                return None
            if content is not None:
                row.content = content
            if set_target:
                row.target_section = target_section
                row.target_step_id = self._step_id_for_index(
                    s, row.recipe_id, target_step_index
                )
            s.commit()
            s.refresh(row)
            return self._to_model(s, row)

    def delete(self, sticker_id: int) -> bool:
        with self._sf() as s:
            row = s.get(RecipeStickerORM, sticker_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True


class PgInventoryRepository(InventoryRepository):
    """Postgres-backed inventory catalog. Also serves as the `InventoryProvider` read port."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def list_items(self) -> list[InventoryItem]:
        with self._sf() as s:
            rows = s.scalars(select(InventoryItemORM).order_by(InventoryItemORM.name)).all()
            return [orm_to_inventory_item(r) for r in rows]

    def upsert_many(self, items: list[InventoryItem]) -> int:
        """The editing UI's atomic **Save**: add new items *and* update existing ones (status or
        any field) in ONE transaction — a single COMMIT, only if something changed; any failure
        rolls the whole batch back. Returns the count inserted or updated."""
        changed = 0
        with self._sf() as s:
            for item in items:
                row = s.scalars(
                    select(InventoryItemORM).where(
                        func.lower(InventoryItemORM.name) == item.name.lower()
                    )
                ).first()
                if row is None:
                    row = InventoryItemORM()
                    _apply_inventory_item(row, item)
                    s.add(row)
                    changed += 1
                else:
                    _apply_inventory_item(row, item)
                    if s.is_modified(row):
                        changed += 1
            if changed:
                s.commit()
        return changed

    def set_status(self, name: str, status: StockStatus) -> InventoryItem | None:
        with self._sf() as s:
            row = s.scalars(
                select(InventoryItemORM).where(func.lower(InventoryItemORM.name) == name.lower())
            ).first()
            if row is None:
                return None
            row.status = status.value
            s.commit()
            s.refresh(row)
            return orm_to_inventory_item(row)

    def delete(self, name: str) -> bool:
        with self._sf() as s:
            row = s.scalars(
                select(InventoryItemORM).where(func.lower(InventoryItemORM.name) == name.lower())
            ).first()
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True
