"""CLI unit tests via Typer's CliRunner. build_planner is patched to a fake in-memory
planner, so no DB / LLM / network is touched.
"""

from __future__ import annotations

from datetime import date

import pytest
from typer.testing import CliRunner

import toddler_dinner.cli as cli
from toddler_dinner.config import ChildProfile, Exclusions, HouseholdProfile, Profile, Sex
from toddler_dinner.core import Planner
from toddler_dinner.models import FoodGroup, Ingredient, InventoryItem, NutritionFacts, Recipe
from toddler_dinner.persistence import InMemoryRecipeRepository

runner = CliRunner()


def _clean_recipe(title: str, ings=("chicken", "rice")) -> Recipe:
    return Recipe(
        title=title,
        ingredients=[Ingredient(name=n, quantity=1, unit="ea") for n in ings],
        steps=["cook"],
        nutrition=NutritionFacts(protein_g=8, sodium_mg=100),
        food_groups={FoodGroup.PROTEIN: 0.4, FoodGroup.GRAINS: 1.0, FoodGroup.VEGETABLES: 0.6},
        min_age_months=12,
        approved=True,
    )


class _Inv:
    def list_items(self):
        return [
            InventoryItem(name="chicken", quantity=1, unit="ea"),
            InventoryItem(name="rice", quantity=1, unit="ea"),
        ]


class _LLM:
    def generate_recipe(self, prompt):
        return _clean_recipe("Fresh Bowl")

    def complete(self, system, user):
        return ""


@pytest.fixture
def planner(monkeypatch):
    profile = Profile(
        child=ChildProfile(name="Mia", birthdate=date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5),
        household=HouseholdProfile(), exclusions=Exclusions(), variety_days=5,
    )
    p = Planner(profile=profile, inventory=_Inv(), recipes=InMemoryRecipeRepository(), llm=_LLM())
    monkeypatch.setattr(cli, "build_planner", lambda config, inventory: p)
    return p


def test_tonight_exact_match(planner):
    planner.recipes.add_recipe(_clean_recipe("Chicken Rice"))
    result = runner.invoke(cli.app, ["tonight"])
    assert result.exit_code == 0
    assert "Chicken Rice" in result.stdout  # full recipe shown


def test_tonight_cold_start_generates(planner):
    # empty cookbook -> generates a fresh idea directly (unified with web)
    result = runner.invoke(cli.app, ["tonight"], input="n\n")
    assert result.exit_code == 0
    assert "here's a fresh idea" in result.stdout
    assert "Fresh Bowl" in result.stdout
    assert "Method:" in result.stdout  # full cooking procedure


def test_tonight_fresh_generates_and_saves(planner):
    result = runner.invoke(cli.app, ["tonight", "--fresh"], input="y\n")
    assert result.exit_code == 0
    assert "Fresh Bowl" in result.stdout
    assert "Saved." in result.stdout
    assert [r.title for r in planner.recipes.approved_recipes()] == ["Fresh Bowl"]


def test_another_idea_declined_not_saved(planner):
    result = runner.invoke(cli.app, ["another-idea"], input="n\n")
    assert result.exit_code == 0
    assert "Fresh Bowl" in result.stdout
    assert planner.recipes.approved_recipes() == []


def test_plan_tomorrow_exports(planner, tmp_path):
    planner.recipes.add_recipe(_clean_recipe("Chicken Rice"))
    result = runner.invoke(
        cli.app, ["plan-tomorrow", "--export-dir", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "Dinner for" in result.stdout
    exports = list(tmp_path.glob("groceries-*.md"))
    assert len(exports) == 1
    assert "Groceries to buy" in exports[0].read_text()


def test_plan_tomorrow_empty_db_friendly_error(planner):
    result = runner.invoke(cli.app, ["plan-tomorrow"])
    assert result.exit_code == 1
    assert "No suitable dinner" in result.stderr


def test_mark_served_records_for_variety(planner):
    result = runner.invoke(cli.app, ["mark-served", "Pasta Night"])
    assert result.exit_code == 0
    assert "Recorded 'Pasta Night'" in result.stdout
    assert "Pasta Night" in planner.recent_dinner_titles


def test_mark_served_with_explicit_date(planner):
    result = runner.invoke(cli.app, ["mark-served", "Fish Pie", "--date", "2025-01-02"])
    assert result.exit_code == 0
    assert "served on 2025-01-02" in result.stdout


def test_db_upgrade_invokes_alembic(monkeypatch):
    calls = {}
    import alembic.command as ac

    monkeypatch.setattr(ac, "upgrade", lambda cfg, rev: calls.setdefault("rev", rev))
    result = runner.invoke(cli.app, ["db", "upgrade"])
    assert result.exit_code == 0
    assert calls["rev"] == "head"
    assert "Database upgraded" in result.stdout
