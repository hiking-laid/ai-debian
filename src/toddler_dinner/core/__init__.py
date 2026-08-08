"""Core actions ("skills"). Reachable via CLI, chat web UI, or direct calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from toddler_dinner.config import Profile
from toddler_dinner.interfaces import (
    InventoryProvider,
    LLMProvider,
    SupermarketProvider,
)
from toddler_dinner.models import (
    HistoryEntry,
    InventoryItem,
    Menu,
    MenuItem,
    Recipe,
    ShoppingItem,
    ShoppingList,
)
from toddler_dinner.nutrition import age_in_months, validate_recipe
from toddler_dinner.persistence import (
    DinnerHistoryRepository,
    MenuRepository,
    RecipeRepository,
)


@dataclass
class MatchResult:
    """Outcome of trying to match a recipe to what's in the fridge."""

    recipe: Recipe | None
    missing: list[str]
    kind: str  # "exact" | "partial" | "none"


def _ingredient_overlap(recipe: Recipe, have: set[str]) -> tuple[int, list[str]]:
    needed = {ing.name.lower() for ing in recipe.ingredients}
    missing = sorted(n for n in needed if not any(n in h or h in n for h in have))
    return len(needed) - len(missing), missing


def match_from_inventory(recipes: list[Recipe], items: list[InventoryItem]) -> MatchResult:
    """Flow 1 matching cascade: exact -> partial -> none."""

    have = {i.name.lower() for i in items}
    best: MatchResult | None = None
    for recipe in recipes:
        matched, missing = _ingredient_overlap(recipe, have)
        if not missing:
            return MatchResult(recipe=recipe, missing=[], kind="exact")
        # track the closest partial (fewest missing)
        if best is None or len(missing) < len(best.missing):
            best = MatchResult(recipe=recipe, missing=missing, kind="partial")
    return best or MatchResult(recipe=None, missing=[], kind="none")


# --- Flow 2 helpers -------------------------------------------------------------

# Pantry staples assumed always on hand — never listed as groceries or counted as "missing".
PANTRY_STAPLES = ("water", "salt", "pepper", "oil", "olive oil", "cooking oil")


def _is_staple(name: str) -> bool:
    n = name.lower()
    return any(s in n for s in PANTRY_STAPLES)


def _have_names(items: list[InventoryItem]) -> set[str]:
    return {i.name.lower() for i in items}


def _in_fridge(ingredient_name: str, have: set[str]) -> bool:
    """Name-presence match (v1): any bidirectional substring hit counts as 'have it'."""
    n = ingredient_name.lower()
    return any(n in h or h in n for h in have)


def missing_ingredients(recipe: Recipe, items: list[InventoryItem]) -> list:
    """Recipe ingredients not covered by the fridge (name-presence, quantity-agnostic in v1).
    Pantry staples (water, salt, oil, ...) are excluded — you're assumed to have them."""
    have = _have_names(items)
    return [
        ing for ing in recipe.ingredients
        if not _in_fridge(ing.name, have) and not _is_staple(ing.name)
    ]


def groceries_for(recipe: Recipe, items: list[InventoryItem]) -> ShoppingList:
    """Groceries list = the shortfall (missing ingredients), quantities straight from the recipe."""
    return ShoppingList(
        items=[
            ShoppingItem(name=ing.name, quantity=ing.quantity, unit=ing.unit)
            for ing in missing_ingredients(recipe, items)
        ]
    )


@dataclass
class PlanResult:
    """Flow 2 output: a menu for a date plus the groceries needed to cook it."""

    menu: Menu
    groceries: ShoppingList
    already_have: list[str] = field(default_factory=list)


# Coarse protein families so rotation treats "chicken thigh"/"chicken breast" as one.
_PROTEIN_FAMILIES = (
    "chicken", "beef", "lamb", "pork", "salmon", "tuna", "hoki", "fish",
    "tofu", "egg", "lentil", "chickpea", "bean",
)


def _protein_family(name: str) -> str:
    n = name.lower()
    for fam in _PROTEIN_FAMILIES:
        if fam in n:
            return fam
    return n


class Planner:
    """Bundles providers + repos so actions have a single entry point."""

    def __init__(
        self,
        profile: Profile,
        inventory: InventoryProvider,
        recipes: RecipeRepository,
        llm: LLMProvider | None = None,
        supermarket: SupermarketProvider | None = None,
        menus: MenuRepository | None = None,
        history: DinnerHistoryRepository | None = None,
    ) -> None:
        self.profile = profile
        self.inventory = inventory
        self.recipes = recipes
        self.llm = llm
        self.supermarket = supermarket
        self.menus = menus
        self.history = history
        # In-memory recent-dinner titles for variety when no history repo is wired (tests).
        self.recent_dinner_titles: list[str] = []
        # Variety steering for generation: recently suggested titles + a protein rotation cursor.
        self.recent_suggestions: list[str] = []
        self._variety_counter = 0

    def _tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.profile.household.timezone)
        except Exception:  # noqa: BLE001 - bad tz in config falls back to UTC
            return ZoneInfo("UTC")

    def today(self) -> date:
        """Current local date in the household timezone (not UTC)."""
        return datetime.now(self._tz()).date()

    def child_age_months(self, on: date | None = None) -> int:
        return age_in_months(self.profile.child.birthdate, on or self.today())

    def _recent_cooked_titles(self, on: date | None = None) -> set[str]:
        """Titles cooked within variety_days — excluded from all suggestion flows."""
        on = on or self.today()
        if self.history is not None:
            return {t.lower() for t in self.history.recent_titles(self.profile.variety_days, on)}
        return {t.lower() for t in self.recent_dinner_titles}

    # --- Flow 1 -----------------------------------------------------------------
    def tonight(self) -> MatchResult:
        """Suggest tonight's dinner from the fridge (DB-first cascade), skipping dinners
        cooked within variety_days so it doesn't repeat a recent meal."""
        items = self.inventory.list_items()
        recent = self._recent_cooked_titles()
        pool = [r for r in self.recipes.approved_recipes() if r.title.lower() not in recent]
        return match_from_inventory(pool, items)

    def another_idea(self, exclude: list[str] | None = None) -> Recipe:
        """Generate a fresh recipe via LLM, validate, and (on approval) store it.

        Variety-steered: rotates the featured main-protein family across calls and instructs the
        model to differ from recently suggested dinners (kept in-memory), so repeated clicks
        don't converge on the same dish.
        """
        if self.llm is None:
            raise RuntimeError("No LLM provider configured.")
        items = self.inventory.list_items()
        have = ", ".join(f"{i.quantity}{i.unit} {i.name}" for i in items)

        # Distinct protein families available, in inventory order; rotate which one to feature.
        families = list(
            dict.fromkeys(
                _protein_family(i.name)
                for i in items
                if (i.category or "").lower() in ("protein", "legume")
            )
        )
        featured = families[self._variety_counter % len(families)] if families else None
        avoid = list(exclude or []) + self.recent_suggestions[-6:] + list(self._recent_cooked_titles())

        prompt = (
            f"Create one toddler dinner (child age {self.child_age_months()} months) using "
            f"mainly these on-hand items: {have}."
        )
        if featured:
            prompt += f" Make {featured} the main protein."
        if avoid:
            prompt += (
                f" Make it clearly different from these recent dinners: {', '.join(avoid)}. "
                "Vary the main protein, cooking style, and cuisine."
            )
        prompt += f" Respect exclusions {self.profile.exclusions.model_dump()}."

        recipe = self.llm.generate_recipe(prompt)
        result = validate_recipe(recipe, self.profile)
        if not result.ok:
            raise ValueError(f"Generated recipe failed safety rules: {result.hard_violations}")

        self._variety_counter += 1
        self.recent_suggestions.append(recipe.title)
        self.recent_suggestions = self.recent_suggestions[-10:]
        return recipe  # caller confirms, then persist_approved()

    def persist_approved(self, recipe: Recipe) -> Recipe:
        recipe.source = "llm"
        return self.approve(recipe)

    # --- save / cook / history --------------------------------------------------
    def approve(self, recipe: Recipe) -> Recipe:
        """Add a recipe to the cookbook (approved -> eligible for auto-suggestion). Dedup by title."""
        return self.recipes.approve(recipe)

    def cook(self, recipe: Recipe, on: date | None = None) -> Recipe:
        """Record a dinner as cooked today: persist the recipe (cooked=True) + a history entry."""
        on = on or self.today()
        stored = self.recipes.mark_cooked(recipe)
        if self.history is not None:
            self.history.record(stored.title, on, stored.id)
        else:
            self.recent_dinner_titles.append(stored.title)
        return stored

    def recent_cooked(self, days: int | None = None) -> list[HistoryEntry]:
        """Recent cooked dinners (full recipes) for the history view."""
        if self.history is None:
            return []
        return self.history.recent(days or self.profile.history_days, on=self.today())

    # --- Flow 2 -----------------------------------------------------------------
    def plan_tomorrow(self, for_date: date | None = None, use_llm: bool = False) -> PlanResult:
        """Plan a single dinner for `for_date` (default tomorrow) + its groceries list.

        DB-first: pick a validated, non-recently-served recipe that needs the fewest groceries.
        Falls back to an LLM-generated recipe when `use_llm` and nothing suitable is in the DB.
        """
        for_date = for_date or (self.today() + timedelta(days=1))
        items = self.inventory.list_items()
        recent = self._recent_cooked_titles(for_date)

        candidates = [
            r
            for r in self.recipes.approved_recipes()
            if r.title.lower() not in recent and validate_recipe(r, self.profile, for_date).ok
        ]
        if candidates:
            # Prefer the recipe requiring the fewest extra groceries (best fridge overlap).
            recipe = min(candidates, key=lambda r: len(missing_ingredients(r, items)))
        elif use_llm:
            recipe = self.another_idea()  # generates + validates (raises on hard failure)
        else:
            raise ValueError(
                "No suitable dinner in the recipe DB (all recent, empty, or invalid). "
                "Retry with use_llm=True for a fresh idea."
            )

        have = _have_names(items)
        already_have = [ing.name for ing in recipe.ingredients if _in_fridge(ing.name, have)]
        menu = Menu(for_date=for_date, items=[MenuItem(recipe=recipe)])
        groceries = groceries_for(recipe, items)
        # Persist the plan only for an approved (already-saved) recipe. A freshly generated
        # recipe is just a suggestion — it is NOT stored until you approve it (via 'save' /
        # another-idea). So no unapproved recipes ever land in the DB.
        if self.menus is not None and recipe.id is not None:
            menu = self.menus.save_menu(menu)
            groceries.menu_id = menu.id
            groceries = self.menus.save_shopping_list(groceries)
        return PlanResult(menu=menu, groceries=groceries, already_have=already_have)

    def record_served(self, recipe: Recipe, served_on: date | None = None) -> None:
        """Log a dinner as served (drives variety). Uses history repo if wired, else in-memory."""
        self.record_served_title(recipe.title, served_on, recipe.id)

    def record_served_title(
        self, title: str, served_on: date | None = None, recipe_id: int | None = None
    ) -> None:
        served_on = served_on or self.today()
        if self.history is not None:
            self.history.record(title, served_on, recipe_id)
        else:
            self.recent_dinner_titles.append(title)
