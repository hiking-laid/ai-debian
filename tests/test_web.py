"""Web server tests via FastAPI TestClient. get_planner is overridden with a fake in-memory
planner (no DB / LLM / network). The chat endpoint (/api/chat) returns structured card payloads.
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
    """Fake LLM: routes to the given action/params (for the router), generates a fixed recipe."""

    def __init__(self, action="another_idea", params=None, fail=False, recipe=None):
        import json
        self._json = json.dumps({"action": action, "params": params or {}})
        self._fail = fail
        self._recipe = recipe

    def complete(self, system, user):
        return self._json

    def generate_recipe(self, prompt):
        if self._fail:
            raise RuntimeError("model exploded")
        return self._recipe or _clean_recipe("Fresh Bowl")


def _make_planner(llm) -> Planner:
    profile = Profile(
        child=ChildProfile(name="Mia", birthdate=date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5),
        household=HouseholdProfile(), exclusions=Exclusions(), variety_days=5,
    )
    return Planner(profile=profile, inventory=_Inv(), recipes=InMemoryRecipeRepository(), llm=llm)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    server.app.dependency_overrides.clear()


def _client(planner) -> TestClient:
    server.app.dependency_overrides[server.get_planner] = lambda: planner
    return TestClient(server.app)


def _chat(client, msg) -> dict:
    return client.post("/api/chat", json={"message": msg}).json()


def test_index_served():
    assert _client(_make_planner(_LLM())).get("/").status_code == 200


def test_chat_exclude_returns_card_with_note():
    # "skip the broccoli" has no fast-path keyword -> LLM router -> another_idea + exclude.
    planner = _make_planner(_LLM(action="another_idea", params={"exclude": ["broccoli"]}))
    d = _chat(_client(planner), "please skip the broccoli")
    assert d["source"] == "fresh"
    assert d["recipe"]["title"] == "Fresh Bowl"     # rendered as a card, not text
    assert d["note"] == "Avoiding broccoli"          # the 'why' note


def test_chat_tonight_matches_cookbook_card():
    planner = _make_planner(_LLM())
    planner.recipes.add_recipe(_clean_recipe("Chicken Rice"))
    d = _chat(_client(planner), "what's for dinner tonight?")   # fast-path tonight
    assert d["source"] == "cookbook"
    assert d["recipe"]["title"] == "Chicken Rice"


def test_chat_plan_returns_plan_card():
    planner = _make_planner(_LLM())
    d = _chat(_client(planner), "plan tomorrow's dinner")       # fast-path plan
    assert d["source"] == "plan"
    assert d["recipe"]["title"] == "Fresh Bowl"
    assert "for_date" in d and "groceries" in d


def test_chat_unrecognized_returns_message():
    planner = _make_planner(_LLM(action="make_coffee"))         # unknown -> unmatched
    d = _chat(_client(planner), "tell me a joke")
    assert "recipe" not in d
    assert "didn't catch" in d["message"].lower()


def test_chat_errors_caught_not_500():
    planner = _make_planner(_LLM(action="another_idea", fail=True))
    resp = _client(planner).post("/api/chat", json={"message": "skip the broccoli"})
    assert resp.status_code == 200
    assert "error" in resp.json()


# --- issue #2: free-form 'note to the kitchen' -------------------------------

def test_chat_customize_include_returns_card_with_note():
    planner = _make_planner(_LLM(action="customize",
                                 params={"include": ["broccoli"], "target": "today"}))
    d = _chat(_client(planner), "add some broccoli please")
    assert d["source"] == "fresh"
    assert d["recipe"]["title"] == "Fresh Bowl"
    assert d["note"] == "Including broccoli"


def test_chat_customize_tomorrow_returns_plan_card():
    planner = _make_planner(_LLM(action="customize", params={"target": "tomorrow"}))
    d = _chat(_client(planner), "use my chicken kumara mash for tomorrow")
    assert d["source"] == "plan"
    assert d["recipe"]["title"] == "Fresh Bowl"
    assert "for_date" in d and "groceries" in d


def test_chat_gibberish_keeps_current_card():
    planner = _make_planner(_LLM(action=None))     # unrecognised -> no-op
    base = _clean_recipe("On Screen Dish").model_dump(mode="json")
    d = _client(planner).post("/api/chat",
                              json={"message": "asdfghjkl", "recipe": base, "mode": "tonight"}).json()
    assert d["recipe"]["title"] == "On Screen Dish"   # card preserved
    assert "message" in d                             # gentle no-op note


def test_chat_customize_guardrail_rejection_keeps_card():
    unsafe = _clean_recipe("Honey Bowl", ings=("honey", "oats"))   # honey -> hard violation
    planner = _make_planner(_LLM(action="customize", params={"include": ["honey"]},
                                 recipe=unsafe))
    base = _clean_recipe("Safe Dish").model_dump(mode="json")
    d = _client(planner).post("/api/chat",
                              json={"message": "add honey", "recipe": base, "mode": "tonight"}).json()
    assert "couldn't do that safely" in d["message"].lower()
    assert d["recipe"]["title"] == "Safe Dish"        # original card kept, not the unsafe one
