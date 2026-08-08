"""Web server tests via FastAPI TestClient. get_planner is overridden with a fake in-memory
planner (no DB / LLM / network). _pending is cleared between tests.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

import toddler_dinner.web.server as server
from toddler_dinner.config import ChildProfile, Exclusions, HouseholdProfile, Profile, Sex
from toddler_dinner.core import Planner
from toddler_dinner.models import FoodGroup, Ingredient, InventoryItem, NutritionFacts, Recipe
from toddler_dinner.persistence import InMemoryRecipeRepository


def _clean_recipe(title: str, ings=("chicken", "rice")) -> Recipe:
    return Recipe(
        title=title,
        ingredients=[Ingredient(name=n, quantity=1, unit="ea") for n in ings],
        steps=["Dice and cook", "Mash soft", "Cool to warm"],
        nutrition=NutritionFacts(protein_g=8, sodium_mg=100),
        food_groups={FoodGroup.PROTEIN: 0.4, FoodGroup.GRAINS: 1.0, FoodGroup.VEGETABLES: 0.6},
        min_age_months=12,
        approved=True,
    )


class _Inv:
    def list_items(self):
        return [InventoryItem(name="chicken", quantity=1, unit="ea"),
                InventoryItem(name="rice", quantity=1, unit="ea")]


class _LLM:
    """Fake LLM: routes everything to the given action, generates a fixed recipe."""

    def __init__(self, action="another_idea", params=None, fail=False):
        import json
        self._json = json.dumps({"action": action, "params": params or {}})
        self._fail = fail

    def complete(self, system, user):
        return self._json

    def generate_recipe(self, prompt):
        if self._fail:
            raise RuntimeError("model exploded")
        return _clean_recipe("Fresh Bowl")


def _make_planner(llm) -> Planner:
    profile = Profile(
        child=ChildProfile(name="Mia", birthdate=date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5),
        household=HouseholdProfile(), exclusions=Exclusions(), variety_days=5,
    )
    return Planner(profile=profile, inventory=_Inv(), recipes=InMemoryRecipeRepository(), llm=llm)


@pytest.fixture(autouse=True)
def _clear_pending():
    server._pending.clear()
    yield
    server._pending.clear()
    server.app.dependency_overrides.clear()


def _client(planner) -> TestClient:
    server.app.dependency_overrides[server.get_planner] = lambda: planner
    return TestClient(server.app)


def _say(client, msg):
    return client.post("/chat", json={"message": msg}).json()["reply"]


def test_index_served():
    planner = _make_planner(_LLM())
    client = _client(planner)
    assert client.get("/").status_code == 200


def test_tonight_exact_match():
    planner = _make_planner(_LLM())
    planner.recipes.add_recipe(_clean_recipe("Chicken Rice"))
    reply = _say(_client(planner), "what's for dinner tonight?")
    assert "Chicken Rice" in reply


def test_tonight_cold_start_generates_idea():
    # Empty cookbook: tonight should generate an idea directly (with steps), not punt.
    planner = _make_planner(_LLM(action="tonight"))
    reply = _say(_client(planner), "what's for dinner tonight?")
    assert "Fresh Bowl" in reply
    assert "Steps:" in reply  # full recipe detail, not just a title
    assert "fresh idea" in reply.lower()


def test_another_idea_suggests_and_can_be_saved():
    planner = _make_planner(_LLM(action="another_idea"))
    client = _client(planner)
    reply = _say(client, "give me something else, she's bored")
    assert "Fresh Bowl" in reply and "save" in reply.lower()
    assert planner.recipes.approved_recipes() == []  # not saved yet (approval gate)

    saved = _say(client, "save")
    assert "Saved 'Fresh Bowl'" in saved
    assert [r.title for r in planner.recipes.approved_recipes()] == ["Fresh Bowl"]


def test_plan_tomorrow_reply():
    planner = _make_planner(_LLM(action="plan_tomorrow"))
    planner.recipes.add_recipe(_clean_recipe("Chicken Rice"))
    reply = _say(_client(planner), "plan tomorrow's dinner")
    assert "Chicken Rice" in reply


def test_errors_are_caught_not_500():
    # LLM generation raises -> friendly reply, HTTP 200 (not a 500)
    planner = _make_planner(_LLM(action="another_idea", fail=True))
    client = _client(planner)
    resp = client.post("/chat", json={"message": "another idea please"})
    assert resp.status_code == 200
    assert "didn't work" in resp.json()["reply"]


def test_unrecognized_message():
    planner = _make_planner(_LLM(action="make_coffee"))  # unknown -> unmatched
    reply = _say(_client(planner), "tell me a joke")
    assert "didn't understand" in reply.lower()
