"""Core actions ("skills"). Reachable via CLI, chat web UI, or direct calls."""

from __future__ import annotations

import random
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
    StockStatus,
)
from toddler_dinner.nutrition import age_in_months, validate_recipe
from toddler_dinner.persistence import (
    DinnerHistoryRepository,
    MenuRepository,
    RecipeRepository,
    StickerRepository,
)


@dataclass
class MatchResult:
    """Outcome of trying to match a recipe to what's in the fridge."""

    recipe: Recipe | None
    missing: list[str]
    kind: str  # "exact" | "partial" | "none"


@dataclass
class DrawResult:
    """Outcome of drawing an existing dinner from the cookbook (issue #13 buttons).

    empty  -> Case 1: no valid recipe at all (caller should point the user at 'New Idea').
    repeat -> Case 2: valid recipes existed but all were within the variety window, so the
              interval was relaxed and a recent dinner was drawn anyway.
    """

    recipe: Recipe | None
    missing: list[str] = field(default_factory=list)
    repeat: bool = False
    empty: bool = False


def _ingredient_overlap(recipe: Recipe, have: set[str]) -> tuple[int, list[str]]:
    needed = {ing.name.lower() for ing in recipe.ingredients}
    # Pantry staples (water, salt, oil, ...) are assumed on hand -> never counted as missing.
    missing = sorted(
        n for n in needed
        if not _is_staple(n) and not any(n in h or h in n for h in have)
    )
    return len(needed) - len(missing), missing


def match_from_inventory(recipes: list[Recipe], items: list[InventoryItem]) -> MatchResult:
    """Flow 1 matching cascade: exact -> partial -> none."""

    have = {i.name.lower() for i in items if i.status != StockStatus.NONE}
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
    # 'none' means out of stock -> not on hand for matching/groceries.
    return {i.name.lower() for i in items if i.status != StockStatus.NONE}


def _inventory_for_prompt(items: list[InventoryItem]) -> str:
    """On-hand items as a name list for the LLM: skip 'none', flag 'low' as not-the-main."""
    parts: list[str] = []
    for i in items:
        if i.status == StockStatus.NONE:
            continue
        if i.status == StockStatus.LOW:
            parts.append(f"{i.name} (low — not as the main ingredient)")
        else:
            parts.append(i.name)
    return ", ".join(parts)


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


# Rotating cooking styles/cuisines to diversify generated dinners beyond the main protein.
_COOKING_STYLES = (
    "simple one-pot", "stir-fry", "oven-baked", "steamed", "soup or stew",
    "mild curry", "pasta-based", "rice bowl", "mash", "fritter or patty",
)


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
        stickers: StickerRepository | None = None,
    ) -> None:
        self.profile = profile
        self.inventory = inventory
        self.recipes = recipes
        self.llm = llm
        self.supermarket = supermarket
        self.menus = menus
        self.history = history
        self.stickers = stickers
        # In-memory recent-dinner titles for variety when no history repo is wired (tests).
        self.recent_dinner_titles: list[str] = []
        # Variety steering for generation: recently suggested titles + a randomized protein
        # rotation (shuffled so the featured protein isn't a fixed, code-driven sequence).
        self.recent_suggestions: list[str] = []
        self._protein_rotation: list[str] = []
        self._last_featured: str | None = None

    def _next_featured(self, families: list[str]) -> str | None:
        """Pick the main protein to feature: a shuffled rotation so no family repeats until all
        have been used, and the first pick isn't a deterministic (always-chicken) choice."""
        if not families:
            return None
        if not self._protein_rotation:
            order = list(families)
            random.shuffle(order)
            # Avoid butting the same family across cycle boundaries.
            if len(order) > 1 and order[0] == self._last_featured:
                order.append(order.pop(0))
            self._protein_rotation = order
        featured = self._protein_rotation.pop(0)
        self._last_featured = featured
        return featured

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

    def draw_from_cookbook(
        self,
        *,
        for_date: date | None = None,
        fridge_aware: bool = True,
        exclude_titles: list[str] | None = None,
    ) -> DrawResult:
        """Draw an existing dinner from the cookbook (issue #13).

        fridge_aware=True  -> random among the recipes needing the fewest groceries (Tonight /
                              Plan Tomorrow). fridge_aware=False -> pure random 'Feeling Lucky'
                              wildcard, ignoring the fridge. Variety is measured from `for_date`,
                              so planning tomorrow naturally excludes today's dinner.
        """
        for_date = for_date or self.today()
        ex = {t.lower() for t in (exclude_titles or [])}
        valid = [
            r
            for r in self.recipes.approved_recipes()
            if r.title.lower() not in ex and validate_recipe(r, self.profile, for_date).ok
        ]
        if not valid:
            return DrawResult(recipe=None, empty=True)          # Case 1

        recent = self._recent_cooked_titles(for_date)
        pool = [r for r in valid if r.title.lower() not in recent]
        repeat = False
        if not pool:
            pool, repeat = valid, True                          # Case 2: relax the interval

        items = self.inventory.list_items()
        if fridge_aware:
            # Random tie-break among the recipes with the best fridge overlap (fewest missing).
            tiers: dict[int, list[tuple[Recipe, list[str]]]] = {}
            for r in pool:
                miss = [i.name for i in missing_ingredients(r, items)]
                tiers.setdefault(len(miss), []).append((r, miss))
            recipe, missing = random.choice(tiers[min(tiers)])
        else:
            recipe = random.choice(pool)
            missing = [i.name for i in missing_ingredients(recipe, items)]
        return DrawResult(recipe=recipe, missing=missing, repeat=repeat)

    def another_idea(self, exclude: list[str] | None = None) -> Recipe:
        """Generate a fresh recipe via LLM, validate, and (on approval) store it.

        Variety-steered: rotates the featured main-protein family across calls and instructs the
        model to differ from recently suggested dinners (kept in-memory), so repeated clicks
        don't converge on the same dish.
        """
        if self.llm is None:
            raise RuntimeError("No LLM provider configured.")
        items = self.inventory.list_items()
        have = _inventory_for_prompt(items)

        # Distinct protein families available, in inventory order; rotate which one to feature.
        families = list(
            dict.fromkeys(
                _protein_family(i.name)
                for i in items
                if (i.category or "").lower() in ("protein", "legume")
                and i.status == StockStatus.HAVE
            )
        )
        featured = self._next_featured(families)
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
        # A randomly chosen cooking style breaks the LLM out of converging on the same dish when
        # the fridge (and thus the prompt) is otherwise identical across calls.
        style = random.choice(_COOKING_STYLES)
        prompt += f" Lean towards a {style} style this time, if it suits the ingredients."

        recipe = self.llm.generate_recipe(prompt)
        result = validate_recipe(recipe, self.profile)
        if not result.ok:
            raise ValueError(f"Generated recipe failed safety rules: {result.hard_violations}")

        self.recent_suggestions.append(recipe.title)
        self.recent_suggestions = self.recent_suggestions[-10:]
        return recipe  # caller confirms, then persist_approved()

    def persist_approved(self, recipe: Recipe) -> Recipe:
        recipe.source = "llm"
        return self.approve(recipe)

    def customize(
        self,
        instructions: str,
        base: Recipe | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        on: date | None = None,
    ) -> Recipe:
        """Free-form 'note to the kitchen': turn an arbitrary parent request into a recipe.

        Reuses the recipe-maker system prompt (via `generate_recipe`) with a built instruction
        that carries the current card (when editing), the parent's words verbatim, and any
        include/avoid hints. The result is guardrail-checked with `validate_recipe`; a hard
        violation raises ValueError so the caller can keep the current card unchanged.

        Not persisted here — the returned recipe is shown on the card; the user saves it via
        the card's own 'Save to Cookbook' button if they want to keep it.
        """
        if self.llm is None:
            raise RuntimeError("No LLM provider configured.")
        items = self.inventory.list_items()
        have = _inventory_for_prompt(items)

        parts: list[str] = []
        if base is not None:
            ings = ", ".join(f"{i.quantity}{i.unit} {i.name}" for i in base.ingredients)
            parts.append(
                f"Start from this current toddler dinner and change only what the request asks, "
                f"keeping the rest: title '{base.title}'; ingredients [{ings}]; steps {base.steps}."
            )
        else:
            parts.append(
                f"Create one toddler dinner (child age {self.child_age_months(on)} months)."
            )
        parts.append(f"Parent's request, in their own words: {instructions!r}.")
        parts.append(
            "If the parent supplied their own full recipe, keep it essentially as they wrote it — "
            "same dish and ingredients — only adjusting for toddler safety, texture, and clear steps."
        )
        if include:
            parts.append(f"These ingredients MUST appear in the recipe: {', '.join(include)}.")
        if exclude:
            parts.append(f"Do NOT include: {', '.join(exclude)}.")
        if have:
            parts.append(f"Prefer these on-hand items where it makes sense: {have}.")
        parts.append(f"Respect exclusions {self.profile.exclusions.model_dump()}.")
        parts.append(
            "If the request is not about food, is empty, or makes no sense, ignore it and return "
            "the current recipe unchanged (or a simple safe toddler dinner if there is none)."
        )

        recipe = self.llm.generate_recipe(" ".join(parts))
        recipe.source = "manual"
        result = validate_recipe(recipe, self.profile, on)
        if not result.ok:
            raise ValueError("; ".join(result.hard_violations))
        return recipe

    def plan_for_recipe(self, recipe: Recipe, for_date: date | None = None) -> PlanResult:
        """Wrap an already-chosen recipe as a tomorrow-style plan (menu + groceries), without
        persisting it — used to render a customised recipe on the 'tomorrow' card."""
        for_date = for_date or (self.today() + timedelta(days=1))
        items = self.inventory.list_items()
        have = _have_names(items)
        already_have = [ing.name for ing in recipe.ingredients if _in_fridge(ing.name, have)]
        menu = Menu(for_date=for_date, items=[MenuItem(recipe=recipe)])
        return PlanResult(
            menu=menu, groceries=groceries_for(recipe, items), already_have=already_have
        )

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

    def build_plan(
        self, recipe: Recipe, for_date: date, items: list[InventoryItem] | None = None
    ) -> PlanResult:
        """Assemble (and, for a saved recipe, persist) a single-dinner plan + its groceries."""
        items = items if items is not None else self.inventory.list_items()
        have = _have_names(items)
        already_have = [ing.name for ing in recipe.ingredients if _in_fridge(ing.name, have)]
        menu = Menu(for_date=for_date, items=[MenuItem(recipe=recipe)])
        groceries = groceries_for(recipe, items)
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
