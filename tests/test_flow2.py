"""Flow 2 (plan tomorrow -> groceries list) tests."""

from __future__ import annotations

from datetime import date, timedelta

from toddler_dinner.config import ChildProfile, Exclusions, HouseholdProfile, Profile, Sex
from toddler_dinner.core import Planner, groceries_for, missing_ingredients
from toddler_dinner.export import groceries_csv, groceries_markdown
from toddler_dinner.models import FoodGroup, Ingredient, InventoryItem, NutritionFacts, Recipe
from toddler_dinner.persistence import InMemoryRecipeRepository
from toddler_dinner.providers.inventory_yaml import YamlInventoryProvider


def _profile() -> Profile:
    return Profile(
        child=ChildProfile(name="Mia", birthdate=date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5),
        household=HouseholdProfile(location="New Zealand"),
        exclusions=Exclusions(),
        variety_days=5,
    )


def _recipe(title: str, ings: list[tuple[str, float, str]]) -> Recipe:
    return Recipe(
        title=title,
        ingredients=[Ingredient(name=n, quantity=q, unit=u) for n, q, u in ings],
        steps=["cook it"],
        nutrition=NutritionFacts(protein_g=8, sodium_mg=100),
        food_groups={FoodGroup.PROTEIN: 0.4, FoodGroup.GRAINS: 1.0, FoodGroup.VEGETABLES: 0.8},
        approved=True,
    )


class _ListInventory:
    def __init__(self, items): self._items = items
    def list_items(self): return self._items


def _planner(recipes, items):
    return Planner(
        profile=_profile(),
        inventory=_ListInventory(items),
        recipes=InMemoryRecipeRepository(recipes),
    )


# --- subtraction logic ------------------------------------------------------

def test_missing_ingredients_name_presence():
    r = _recipe("bowl", [("chicken", 300, "g"), ("rice", 200, "g"), ("broccoli", 1, "head")])
    fridge = [InventoryItem(name="rice", quantity=500, unit="g"),
              InventoryItem(name="olive oil", quantity=1, unit="bottle")]
    missing = [i.name for i in missing_ingredients(r, fridge)]
    assert missing == ["chicken", "broccoli"]


def test_groceries_uses_recipe_quantities():
    r = _recipe("bowl", [("chicken", 300, "g"), ("rice", 200, "g")])
    fridge = [InventoryItem(name="rice", quantity=500, unit="g")]
    gl = groceries_for(r, fridge)
    assert [(g.name, g.quantity, g.unit) for g in gl.items] == [("chicken", 300, "g")]


# --- plan_tomorrow ----------------------------------------------------------

def test_plan_tomorrow_picks_fewest_groceries():
    fridge = [InventoryItem(name="rice", quantity=500, unit="g"),
              InventoryItem(name="carrot", quantity=3, unit="each")]
    needs_more = _recipe("fish stew", [("fish", 1, "ea"), ("tomato", 2, "ea"), ("rice", 1, "cup")])
    needs_less = _recipe("carrot rice", [("carrot", 1, "ea"), ("rice", 1, "cup")])
    p = _planner([needs_more, needs_less], fridge)
    plan = p.plan_tomorrow()
    assert plan.menu.items[0].recipe.title == "carrot rice"  # fewest missing
    assert plan.menu.for_date == p.today() + timedelta(days=1)
    assert plan.groceries.items == []  # both ingredients already in fridge


def test_plan_tomorrow_respects_variety():
    fridge = [InventoryItem(name="rice", quantity=500, unit="g")]
    a = _recipe("chicken rice", [("chicken", 1, "ea"), ("rice", 1, "cup")])
    p = _planner([a], fridge)
    p.recent_dinner_titles = ["chicken rice"]  # served recently
    try:
        p.plan_tomorrow()  # only option was recently served -> no candidate
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_plan_tomorrow_empty_db_raises_without_llm():
    p = _planner([], [InventoryItem(name="rice", quantity=1, unit="cup")])
    try:
        p.plan_tomorrow()
        assert False
    except ValueError:
        pass


# --- exports ----------------------------------------------------------------

def test_markdown_and_csv_export():
    fridge = [InventoryItem(name="rice", quantity=500, unit="g")]
    r = _recipe("bowl", [("chicken", 300, "g"), ("rice", 200, "g")])
    p = _planner([r], fridge)
    plan = p.plan_tomorrow()
    md = groceries_markdown(plan)
    assert "Groceries to buy" in md
    assert "- [ ] chicken" in md
    assert "- [ ] rice" not in md  # rice is in the fridge, not a grocery line
    csv_out = groceries_csv(plan)
    assert "chicken,300.0,g" in csv_out


def test_flow2_end_to_end_with_yaml_inventory(tmp_path):
    inv = tmp_path / "inv.yaml"
    inv.write_text("- name: rice\n  quantity: 500\n  unit: g\n")
    r = _recipe("chicken rice", [("chicken", 300, "g"), ("rice", 200, "g")])
    planner = Planner(
        profile=_profile(),
        inventory=YamlInventoryProvider(inv),
        recipes=InMemoryRecipeRepository([r]),
    )
    plan = planner.plan_tomorrow()
    assert [g.name for g in plan.groceries.items] == ["chicken"]
    assert "rice" in plan.already_have


def test_groceries_excludes_pantry_staples():
    r = _recipe("bowl", [("chicken", 300, "g"), ("water", 120, "ml"),
                         ("salt", 1, "pinch"), ("olive oil", 1, "tbsp")])
    gl = groceries_for(r, [])  # empty fridge
    names = [g.name for g in gl.items]
    assert names == ["chicken"]  # water/salt/oil filtered out


# --- draw_from_cookbook (issue #13 button engine) ---------------------------

def test_draw_fridge_aware_prefers_fewest_missing():
    in_fridge = _recipe("Chicken Rice", [("chicken", 1, "ea"), ("rice", 1, "ea")])
    needs_shop = _recipe("Beef Stew", [("beef", 1, "ea"), ("potato", 1, "ea")])
    items = [InventoryItem(name="chicken", quantity=1, unit="ea"),
             InventoryItem(name="rice", quantity=1, unit="ea")]
    p = _planner([in_fridge, needs_shop], items)
    # Fridge-aware random still always lands on the fully-stocked recipe (fewest-missing tier).
    for _ in range(20):
        d = p.draw_from_cookbook(fridge_aware=True)
        assert d.recipe.title == "Chicken Rice"
        assert d.missing == [] and d.repeat is False and d.empty is False


def test_draw_wildcard_ignores_fridge_and_honours_exclude():
    a = _recipe("Chicken Rice", [("chicken", 1, "ea"), ("rice", 1, "ea")])
    b = _recipe("Beef Stew", [("beef", 1, "ea"), ("potato", 1, "ea")])
    p = _planner([a, b], [InventoryItem(name="chicken", quantity=1, unit="ea")])
    # Excluding the on-screen recipe -> the wildcard returns the other one.
    for _ in range(20):
        d = p.draw_from_cookbook(fridge_aware=False, exclude_titles=["Chicken Rice"])
        assert d.recipe.title == "Beef Stew"


def test_draw_case1_empty_cookbook():
    p = _planner([], [])
    d = p.draw_from_cookbook(fridge_aware=True)
    assert d.recipe is None and d.empty is True


def test_draw_case2_relaxes_variety_with_repeat_flag():
    r = _recipe("Chicken Rice", [("chicken", 1, "ea"), ("rice", 1, "ea")])
    p = _planner([r], [InventoryItem(name="chicken", quantity=1, unit="ea")])
    p.record_served(r)  # only recipe is now within the variety window
    d = p.draw_from_cookbook(fridge_aware=True)
    assert d.recipe.title == "Chicken Rice"   # drawn anyway
    assert d.repeat is True and d.empty is False
