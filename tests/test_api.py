"""API endpoint tests. Uses a SQLite-backed Planner (real repos) so cook/history/variety
work end to end; the LLM is a fake. get_planner is dependency-overridden.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import toddler_dinner.web.server as server
from toddler_dinner.config import ChildProfile, Exclusions, HouseholdProfile, Profile, Sex
from toddler_dinner.core import Planner
from toddler_dinner.models import FoodGroup, Ingredient, InventoryItem, NutritionFacts, Recipe
from toddler_dinner.persistence.orm import Base
from toddler_dinner.persistence.repositories import (
    PgDinnerHistoryRepository,
    PgMenuRepository,
    PgRecipeRepository,
)


def _clean_recipe(title: str, ings=("chicken", "rice")) -> Recipe:
    return Recipe(
        title=title,
        ingredients=[Ingredient(name=n, quantity=1, unit="ea") for n in ings],
        steps=["cook"],
        nutrition=NutritionFacts(protein_g=8, sodium_mg=100),
        food_groups={FoodGroup.PROTEIN: 0.4, FoodGroup.GRAINS: 1.0, FoodGroup.VEGETABLES: 0.6},
        min_age_months=12,
    )


class _Inv:
    def list_items(self):
        return [InventoryItem(name="chicken", quantity=1, unit="ea"),
                InventoryItem(name="rice", quantity=1, unit="ea")]


class _LLM:
    def __init__(self):
        self.n = 0

    def complete(self, system, user):
        return ""

    def generate_recipe(self, prompt):
        self.n += 1
        return _clean_recipe(f"Fresh Dish {self.n}", ings=("chicken", "rice", "broccoli"))


@pytest.fixture
def planner():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    profile = Profile(
        child=ChildProfile(name="Mia", birthdate=date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5),
        household=HouseholdProfile(), exclusions=Exclusions(), variety_days=5, history_days=5,
    )
    return Planner(profile=profile, inventory=_Inv(), recipes=PgRecipeRepository(sf),
                   llm=_LLM(), menus=PgMenuRepository(sf), history=PgDinnerHistoryRepository(sf))


@pytest.fixture
def client(planner):
    server.app.dependency_overrides[server.get_planner] = lambda: planner
    yield TestClient(server.app)
    server.app.dependency_overrides.clear()


def test_tonight_cold_start_returns_message(client):
    # Empty cookbook -> Case 1: no auto-generate; nudge the user to "New Idea".
    r = client.post("/api/tonight").json()
    assert "recipe" not in r
    assert "message" in r


def test_save_then_tonight_matches_cookbook(client, planner):
    recipe = _clean_recipe("Chicken Rice")
    save = client.post("/api/recipe/save", json={"recipe": recipe.model_dump(mode="json")}).json()
    assert save["ok"] and save["id"]
    r = client.post("/api/tonight").json()
    assert r["source"] == "cookbook"
    assert r["recipe"]["title"] == "Chicken Rice"


def test_cooked_then_history_and_variety(client):
    recipe = _clean_recipe("Chicken Rice")
    # approve so it would normally be a cookbook match
    client.post("/api/recipe/save", json={"recipe": recipe.model_dump(mode="json")})
    # cook it today
    ck = client.post("/api/recipe/cooked", json={"recipe": recipe.model_dump(mode="json")}).json()
    assert ck["ok"]
    # history shows it with full recipe
    hist = client.get("/api/history").json()["entries"]
    assert len(hist) == 1
    assert hist[0]["recipe"]["title"] == "Chicken Rice"
    assert hist[0]["recipe"]["ingredients"]
    # variety: the only approved recipe was cooked today, so the fresh pool is empty ->
    # Case 2 relaxes the interval and re-draws it, flagged as a repeat (never silently LLMs).
    r = client.post("/api/tonight").json()
    assert r["source"] == "cookbook"
    assert r["recipe"]["title"] == "Chicken Rice"
    assert r["repeat"] is True


def test_cooked_twice_same_day_is_not_duplicated(client):
    """Regression (issue #1): clicking COOKED IT TODAY twice must not add duplicate cards."""
    recipe = _clean_recipe("Chicken Rice")
    body = {"recipe": recipe.model_dump(mode="json")}
    assert client.post("/api/recipe/cooked", json=body).json()["ok"]
    assert client.post("/api/recipe/cooked", json=body).json()["ok"]
    hist = client.get("/api/history").json()["entries"]
    assert len(hist) == 1


def test_plan_tomorrow_payload(client):
    recipe = _clean_recipe("Chicken Rice")
    client.post("/api/recipe/save", json={"recipe": recipe.model_dump(mode="json")})
    r = client.post("/api/plan-tomorrow").json()
    assert r["source"] == "plan"
    assert r["recipe"]["title"]
    assert "for_date" in r and "groceries" in r


def test_plan_tomorrow_empty_returns_message(client):
    # Empty cookbook -> Case 1 message, not an LLM fallback.
    r = client.post("/api/plan-tomorrow").json()
    assert "recipe" not in r and "message" in r


def test_new_idea_generates_fresh(client):
    r = client.post("/api/new-idea").json()
    assert r["source"] == "fresh"
    assert r["recipe"]["title"].startswith("Fresh Dish")


def test_feeling_lucky_draws_other_cookbook_recipe(client):
    for rc in (_clean_recipe("Chicken Rice"),
               _clean_recipe("Beef Stew", ings=("beef", "potato"))):
        client.post("/api/recipe/save", json={"recipe": rc.model_dump(mode="json")})
    # tonight wildcard excludes the on-screen recipe -> returns the OTHER cookbook dinner
    r = client.post("/api/feeling-lucky",
                    json={"mode": "tonight", "exclude": ["Chicken Rice"]}).json()
    assert r["source"] == "cookbook"
    assert r["recipe"]["title"] == "Beef Stew"
    # plan mode -> a plan payload
    p = client.post("/api/feeling-lucky",
                    json={"mode": "plan", "exclude": ["Chicken Rice"]}).json()
    assert p["source"] == "plan"


def test_feeling_lucky_empty_returns_message(client):
    r = client.post("/api/feeling-lucky", json={"mode": "tonight"}).json()
    assert "recipe" not in r and "message" in r


def test_history_empty_initially(client):
    assert client.get("/api/history").json()["entries"] == []
