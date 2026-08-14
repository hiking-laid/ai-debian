"""Persistence: Postgres-backed repositories.

v1 provides an in-memory RecipeRepository so the flows and tests run before the DB/migrations
are wired. Swap for a SQLAlchemy-backed implementation without changing the core actions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from toddler_dinner.models import HistoryEntry, Menu, Recipe, ShoppingList, Sticker, SupermarketSnapshot


class RecipeRepository(ABC):
    @abstractmethod
    def approved_recipes(self) -> list[Recipe]:
        ...

    @abstractmethod
    def add_recipe(self, recipe: Recipe) -> Recipe:
        ...

    @abstractmethod
    def find_by_title(self, title: str) -> Recipe | None:
        ...

    @abstractmethod
    def approve(self, recipe: Recipe) -> Recipe:
        """Add to the cookbook (approved=True). Dedup by title."""
        ...

    @abstractmethod
    def mark_cooked(self, recipe: Recipe) -> Recipe:
        """Persist as cooked (cooked=True) if new; dedup by title. Returns the stored recipe."""
        ...


class MenuRepository(ABC):
    @abstractmethod
    def save_menu(self, menu: Menu) -> Menu:
        ...

    @abstractmethod
    def save_shopping_list(self, shopping_list: ShoppingList) -> ShoppingList:
        ...


class SnapshotRepository(ABC):
    @abstractmethod
    def latest(self, store: str) -> SupermarketSnapshot | None:
        ...

    @abstractmethod
    def save(self, snapshot: SupermarketSnapshot) -> SupermarketSnapshot:
        ...


class DinnerHistoryRepository(ABC):
    """Drives variety: which dinners were served recently."""

    @abstractmethod
    def recent_titles(self, within_days: int, on=None) -> list[str]:
        ...

    @abstractmethod
    def record(self, title: str, served_on, recipe_id: int | None = None) -> None:
        ...

    @abstractmethod
    def recent(self, days: int, on=None) -> list[HistoryEntry]:
        """Recent cooked dinners (most recent first) with their full recipes."""
        ...


class StickerRepository(ABC):
    """Post-cook handwritten notes pinned to a recipe / section / Method step."""

    @abstractmethod
    def list_for_recipe(self, recipe_id: int) -> list[Sticker]:
        ...

    @abstractmethod
    def create(
        self,
        recipe_id: int,
        content: str,
        target_section: str | None = None,
        target_step_index: int | None = None,
    ) -> Sticker:
        ...

    @abstractmethod
    def update(
        self,
        sticker_id: int,
        *,
        content: str | None = None,
        set_target: bool = False,
        target_section: str | None = None,
        target_step_index: int | None = None,
    ) -> Sticker | None:
        ...

    @abstractmethod
    def delete(self, sticker_id: int) -> bool:
        ...


class InMemoryRecipeRepository(RecipeRepository):
    def __init__(self, recipes: list[Recipe] | None = None) -> None:
        self._recipes = list(recipes or [])
        self._next_id = 1

    def approved_recipes(self) -> list[Recipe]:
        return [r for r in self._recipes if r.approved]

    def add_recipe(self, recipe: Recipe) -> Recipe:
        recipe.id = self._next_id
        self._next_id += 1
        self._recipes.append(recipe)
        return recipe

    def find_by_title(self, title: str) -> Recipe | None:
        t = title.lower()
        return next((r for r in self._recipes if r.title.lower() == t), None)

    def approve(self, recipe: Recipe) -> Recipe:
        existing = self.find_by_title(recipe.title)
        if existing:
            existing.approved = True
            return existing
        recipe.approved = True
        return self.add_recipe(recipe)

    def mark_cooked(self, recipe: Recipe) -> Recipe:
        existing = self.find_by_title(recipe.title)
        if existing:
            existing.cooked = True
            return existing
        recipe.cooked = True
        return self.add_recipe(recipe)


class InMemoryStickerRepository(StickerRepository):
    """In-memory stickers for tests. Stores the step *index* directly (no id translation)."""

    def __init__(self) -> None:
        self._items: list[Sticker] = []
        self._next_id = 1

    def list_for_recipe(self, recipe_id: int) -> list[Sticker]:
        return [s for s in self._items if s.recipe_id == recipe_id]

    def create(self, recipe_id, content, target_section=None, target_step_index=None) -> Sticker:
        s = Sticker(
            id=self._next_id, recipe_id=recipe_id, content=content,
            target_section=target_section, target_step_index=target_step_index,
        )
        self._next_id += 1
        self._items.append(s)
        return s

    def update(self, sticker_id, *, content=None, set_target=False,
               target_section=None, target_step_index=None) -> Sticker | None:
        s = next((x for x in self._items if x.id == sticker_id), None)
        if s is None:
            return None
        if content is not None:
            s.content = content
        if set_target:
            s.target_section = target_section
            s.target_step_index = target_step_index
        return s

    def delete(self, sticker_id) -> bool:
        before = len(self._items)
        self._items = [x for x in self._items if x.id != sticker_id]
        return len(self._items) < before
