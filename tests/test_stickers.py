"""Sticker feature tests: web API CRUD (in-memory planner) + Pg step index<->id translation."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

import toddler_dinner.web.server as server
from toddler_dinner.config import ChildProfile, Exclusions, HouseholdProfile, Profile, Sex
from toddler_dinner.core import Planner
from toddler_dinner.models import Ingredient, InventoryItem, Recipe
from toddler_dinner.persistence import InMemoryRecipeRepository, InMemoryStickerRepository


class _Inv:
    def list_items(self):
        return [InventoryItem(name="rice", quantity=1, unit="ea")]


def _make_planner() -> Planner:
    profile = Profile(
        child=ChildProfile(name="Mia", birthdate=date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5),
        household=HouseholdProfile(), exclusions=Exclusions(), variety_days=5,
    )
    return Planner(
        profile=profile, inventory=_Inv(),
        recipes=InMemoryRecipeRepository(), stickers=InMemoryStickerRepository(),
    )


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    server.app.dependency_overrides.clear()


def _client(planner) -> TestClient:
    server.app.dependency_overrides[server.get_planner] = lambda: planner
    return TestClient(server.app)


def test_sticker_crud_lifecycle():
    c = _client(_make_planner())
    rid = 7

    # create a general sticker
    s = c.post(f"/api/recipe/{rid}/stickers", json={"content": "too bland"}).json()["sticker"]
    assert s["target_section"] is None and s["target_step_index"] is None
    assert s["content"] == "too bland"

    # create one pinned to Method step 0
    s2 = c.post(f"/api/recipe/{rid}/stickers",
                json={"content": "less water", "target_step_index": 0}).json()["sticker"]
    assert s2["target_step_index"] == 0

    # list returns both
    listed = c.get(f"/api/recipe/{rid}/stickers").json()["stickers"]
    assert {x["content"] for x in listed} == {"too bland", "less water"}

    # edit content
    up = c.patch(f"/api/stickers/{s['id']}", json={"content": "quite bland"}).json()["sticker"]
    assert up["content"] == "quite bland"

    # re-pin the general one to the Tips section
    rt = c.patch(f"/api/stickers/{s['id']}",
                 json={"set_target": True, "target_section": "tips"}).json()["sticker"]
    assert rt["target_section"] == "tips"

    # delete
    assert c.request("DELETE", f"/api/stickers/{s2['id']}").json()["ok"] is True
    left = c.get(f"/api/recipe/{rid}/stickers").json()["stickers"]
    assert len(left) == 1 and left[0]["content"] == "quite bland"


def test_sticker_empty_rejected():
    c = _client(_make_planner())
    r = c.post("/api/recipe/1/stickers", json={"content": "   "}).json()
    assert "error" in r


def test_sticker_unknown_section_becomes_general():
    c = _client(_make_planner())
    s = c.post("/api/recipe/1/stickers",
               json={"content": "note", "target_section": "bogus"}).json()["sticker"]
    assert s["target_section"] is None and s["target_step_index"] is None


def test_sticker_step_wins_over_section():
    c = _client(_make_planner())
    s = c.post("/api/recipe/1/stickers",
               json={"content": "note", "target_section": "tips", "target_step_index": 2}).json()["sticker"]
    assert s["target_section"] is None and s["target_step_index"] == 2


def test_patch_missing_sticker_returns_error():
    c = _client(_make_planner())
    assert "error" in c.patch("/api/stickers/999", json={"content": "x"}).json()


# --- Pg repository: step index <-> recipe_steps.id translation (no DB) --------

class _FakeStep:
    def __init__(self, sid, pos):
        self.id, self.position = sid, pos


def test_pg_repo_translates_index_and_step_id(monkeypatch):
    from toddler_dinner.persistence.repositories import PgStickerRepository
    from toddler_dinner.models import Sticker

    repo = PgStickerRepository.__new__(PgStickerRepository)  # skip __init__ (no session factory)

    # steps for recipe: index 0->id 41, 1->id 42, 2->id 43
    monkeypatch.setattr(repo, "_step_ids", lambda s, rid: [41, 42, 43])

    assert repo._step_id_for_index(None, 1, 2) == 43
    assert repo._step_id_for_index(None, 1, None) is None
    assert repo._step_id_for_index(None, 1, 9) is None      # out of range -> general

    assert repo._index_for_step_id(None, 1, 43) == 2
    assert repo._index_for_step_id(None, 1, None) is None
    assert repo._index_for_step_id(None, 1, 999) is None    # deleted step -> general
