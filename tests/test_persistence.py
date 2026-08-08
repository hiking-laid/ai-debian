"""Repository tests on in-memory SQLite (ORM uses only generic types, so the same repos
run on SQLite here and on Postgres in production — the live schema is verified via Alembic).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from toddler_dinner.models import FoodGroup, Ingredient, MenuItem, Menu, NutritionFacts, Recipe, ShoppingItem, ShoppingList
from toddler_dinner.persistence.orm import Base
from toddler_dinner.persistence.repositories import (
    PgDinnerHistoryRepository,
    PgMenuRepository,
    PgRecipeRepository,
)


@pytest.fixture
def sf():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _recipe(title="Chicken Rice Bowl", approved=True) -> Recipe:
    return Recipe(
        title=title,
        ingredients=[
            Ingredient(name="chicken", quantity=300, unit="g"),
            Ingredient(name="rice", quantity=200, unit="g"),
        ],
        steps=["cook chicken", "boil rice", "combine"],
        nutrition=NutritionFacts(protein_g=9, sodium_mg=110),
        texture="small soft pieces",
        min_age_months=12,
        hazard_flags=[],
        tags=["quick", "poultry"],
        food_groups={FoodGroup.PROTEIN: 1.0, FoodGroup.GRAINS: 1.0},
        approved=approved,
        source="seed",
    )


def test_recipe_round_trip_preserves_all_fields(sf):
    repo = PgRecipeRepository(sf)
    saved = repo.add_recipe(_recipe())
    assert saved.id is not None

    got = repo.approved_recipes()
    assert len(got) == 1
    r = got[0]
    assert r.title == "Chicken Rice Bowl"
    assert [(i.name, i.quantity, i.unit) for i in r.ingredients] == [
        ("chicken", 300, "g"), ("rice", 200, "g")
    ]
    assert r.steps == ["cook chicken", "boil rice", "combine"]
    assert r.nutrition.protein_g == 9 and r.nutrition.sodium_mg == 110
    assert r.texture == "small soft pieces"
    assert r.tags == ["quick", "poultry"]
    assert r.food_groups == {FoodGroup.PROTEIN: 1.0, FoodGroup.GRAINS: 1.0}


def test_only_approved_recipes_returned(sf):
    repo = PgRecipeRepository(sf)
    repo.add_recipe(_recipe("Approved", approved=True))
    repo.add_recipe(_recipe("Draft", approved=False))
    titles = [r.title for r in repo.approved_recipes()]
    assert titles == ["Approved"]


def test_menu_and_shopping_list_persist(sf):
    recipes = PgRecipeRepository(sf)
    menus = PgMenuRepository(sf)
    saved_recipe = recipes.add_recipe(_recipe())

    menu = Menu(for_date=date(2025, 1, 1), items=[MenuItem(recipe=saved_recipe)])
    menu = menus.save_menu(menu)
    assert menu.id is not None

    sl = ShoppingList(menu_id=menu.id, items=[ShoppingItem(name="chicken", quantity=300, unit="g")])
    sl = menus.save_shopping_list(sl)
    assert sl.id is not None


def test_dinner_history_variety_window(sf):
    hist = PgDinnerHistoryRepository(sf)
    today = date(2025, 6, 10)
    hist.record("Old Dinner", today - timedelta(days=10))
    hist.record("Recent Dinner", today - timedelta(days=2))

    within5 = hist.recent_titles(within_days=5, on=today)
    assert "Recent Dinner" in within5
    assert "Old Dinner" not in within5

    within30 = hist.recent_titles(within_days=30, on=today)
    assert set(within30) == {"Old Dinner", "Recent Dinner"}


def test_planner_variety_uses_history(sf):
    from datetime import date as _date

    from toddler_dinner.config import ChildProfile, Exclusions, HouseholdProfile, Profile, Sex
    from toddler_dinner.core import Planner

    recipes = PgRecipeRepository(sf)
    menus = PgMenuRepository(sf)
    hist = PgDinnerHistoryRepository(sf)
    recipes.add_recipe(_recipe("Only Option"))

    class Inv:
        def list_items(self):
            return []

    profile = Profile(
        child=ChildProfile(name="Mia", birthdate=_date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5),
        household=HouseholdProfile(), exclusions=Exclusions(), variety_days=5,
    )
    planner = Planner(profile=profile, inventory=Inv(), recipes=recipes, menus=menus, history=hist)

    # First plan works and gets persisted.
    plan = planner.plan_tomorrow()
    assert plan.menu.items[0].recipe.title == "Only Option"
    assert plan.menu.id is not None  # persisted

    # Mark it served today -> variety should now exclude it tomorrow.
    planner.record_served(plan.menu.items[0].recipe, served_on=date.today())
    with pytest.raises(ValueError):
        planner.plan_tomorrow()


def test_plan_tomorrow_does_not_persist_unapproved_recipe(sf):
    """Flow 2 with a fresh LLM recipe must NOT persist it (only approved recipes are stored),
    and must not crash."""
    from datetime import date as _date

    from toddler_dinner.config import ChildProfile, Exclusions, HouseholdProfile, Profile, Sex
    from toddler_dinner.core import Planner
    from toddler_dinner.models import FoodGroup, Ingredient, NutritionFacts

    recipes = PgRecipeRepository(sf)
    menus = PgMenuRepository(sf)

    class Inv:
        def list_items(self):
            return []

    class LLM:
        def generate_recipe(self, prompt):
            return Recipe(
                title="LLM Bowl",
                ingredients=[Ingredient(name="tofu", quantity=100, unit="g")],
                steps=["cook"],
                nutrition=NutritionFacts(protein_g=8, sodium_mg=50),
                food_groups={FoodGroup.PROTEIN: 0.5, FoodGroup.GRAINS: 1.0, FoodGroup.VEGETABLES: 0.5},
                min_age_months=12,
            )

        def complete(self, system, user):
            return ""

    profile = Profile(
        child=ChildProfile(name="Mia", birthdate=_date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5),
        household=HouseholdProfile(), exclusions=Exclusions(), variety_days=5,
    )
    planner = Planner(profile=profile, inventory=Inv(), recipes=recipes, llm=LLM(), menus=menus)

    plan = planner.plan_tomorrow(use_llm=True)  # empty DB -> LLM recipe
    assert plan.menu.items[0].recipe.title == "LLM Bowl"
    assert plan.menu.items[0].recipe.id is None  # not persisted (unapproved)
    assert plan.menu.id is None                  # menu not persisted either
    assert recipes.approved_recipes() == []      # nothing saved to the recipes table


# --- Stage 1: cooked flag, dedup, history.recent ----------------------------

def test_find_by_title(sf):
    repo = PgRecipeRepository(sf)
    assert repo.find_by_title("nope") is None
    repo.add_recipe(_recipe("Salmon Mash"))
    assert repo.find_by_title("salmon mash").title == "Salmon Mash"  # case-insensitive


def test_approve_dedup_by_title(sf):
    repo = PgRecipeRepository(sf)
    saved = repo.approve(_recipe("Chicken Rice", approved=False))
    assert saved.id is not None and saved.approved is True
    again = repo.approve(_recipe("chicken rice", approved=False))  # same title, different case
    assert again.id == saved.id            # reused the row
    assert len(repo.approved_recipes()) == 1


def test_mark_cooked_persists_not_approved_and_dedups(sf):
    repo = PgRecipeRepository(sf)
    c = repo.mark_cooked(_recipe("Beef Pie", approved=False))
    assert c.id is not None and c.cooked is True and c.approved is False
    assert repo.approved_recipes() == []   # cooked but not approved -> never auto-suggested
    c2 = repo.mark_cooked(_recipe("beef pie"))
    assert c2.id == c.id                    # reused the row


def test_cook_then_approve_same_recipe(sf):
    repo = PgRecipeRepository(sf)
    cooked = repo.mark_cooked(_recipe("Kumara Bowl"))
    approved = repo.approve(_recipe("Kumara Bowl"))
    assert approved.id == cooked.id
    assert approved.approved is True and approved.cooked is True  # both flags on one row


def test_history_recent_returns_full_recipes(sf):
    recipes = PgRecipeRepository(sf)
    hist = PgDinnerHistoryRepository(sf)
    r = recipes.mark_cooked(_recipe("Lentil Risotto"))
    today = date(2025, 6, 10)
    hist.record(r.title, today, r.id)
    hist.record("Legacy Title Only", today - timedelta(days=20), None)  # outside window
    entries = hist.recent(5, on=today)
    assert len(entries) == 1
    assert entries[0].served_on == today
    assert entries[0].recipe.title == "Lentil Risotto"
    assert [i.name for i in entries[0].recipe.ingredients] == ["chicken", "rice"]


def test_inmemory_approve_and_cook_dedup():
    from toddler_dinner.persistence import InMemoryRecipeRepository
    repo = InMemoryRecipeRepository()
    a = repo.approve(_recipe("Dish A", approved=False))
    assert a.approved and a.id is not None
    a2 = repo.approve(_recipe("dish a"))
    assert a2.id == a.id
    c = repo.mark_cooked(_recipe("Dish B", approved=False))
    assert c.cooked and not c.approved


# --- Stage 2: Planner approve / cook / recent_cooked ------------------------

def _planner_with_repos(sf):
    from datetime import date as _date

    from toddler_dinner.config import ChildProfile, Exclusions, HouseholdProfile, Profile, Sex
    from toddler_dinner.core import Planner

    profile = Profile(
        child=ChildProfile(name="Mia", birthdate=_date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5),
        household=HouseholdProfile(), exclusions=Exclusions(), variety_days=5, history_days=5,
    )

    class Inv:
        def list_items(self):
            return []

    return Planner(
        profile=profile, inventory=Inv(),
        recipes=PgRecipeRepository(sf), menus=PgMenuRepository(sf), history=PgDinnerHistoryRepository(sf),
    )


def test_planner_cook_records_history_and_recent(sf):
    planner = _planner_with_repos(sf)
    stored = planner.cook(_recipe("Cooked Dish", approved=False))
    assert stored.id is not None and stored.cooked is True and stored.approved is False

    entries = planner.recent_cooked()
    assert len(entries) == 1
    assert entries[0].recipe.title == "Cooked Dish"
    assert [i.name for i in entries[0].recipe.ingredients] == ["chicken", "rice"]  # full recipe
    # cooked-but-unapproved is NOT auto-suggestable
    assert planner.recipes.approved_recipes() == []


def test_planner_approve_makes_suggestable(sf):
    planner = _planner_with_repos(sf)
    planner.approve(_recipe("Fav Dish", approved=False))
    assert [r.title for r in planner.recipes.approved_recipes()] == ["Fav Dish"]


def test_planner_cook_then_approve_one_row(sf):
    planner = _planner_with_repos(sf)
    cooked = planner.cook(_recipe("Both Dish", approved=False))
    approved = planner.approve(_recipe("both dish", approved=False))  # same title
    assert approved.id == cooked.id
    assert len(planner.recent_cooked()) == 1
    assert [r.title for r in planner.recipes.approved_recipes()] == ["Both Dish"]
