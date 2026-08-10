"""Generation variety-steering tests (protein rotation + avoid-recent)."""

from __future__ import annotations

from datetime import date

from toddler_dinner.config import ChildProfile, Exclusions, HouseholdProfile, Profile, Sex
from toddler_dinner.core import Planner
from toddler_dinner.models import FoodGroup, Ingredient, InventoryItem, NutritionFacts, Recipe
from toddler_dinner.persistence import InMemoryRecipeRepository


class _Inv:
    def list_items(self):
        return [
            InventoryItem(name="chicken thigh", quantity=1, unit="ea", category="protein"),
            InventoryItem(name="chicken breast", quantity=1, unit="ea", category="protein"),
            InventoryItem(name="beef mince", quantity=1, unit="ea", category="protein"),
            InventoryItem(name="salmon fillet", quantity=1, unit="ea", category="protein"),
            InventoryItem(name="red lentils", quantity=1, unit="g", category="legume"),
            InventoryItem(name="rice", quantity=1, unit="g", category="grain"),
        ]


class _RecordingLLM:
    def __init__(self):
        self.prompts = []
        self.n = 0

    def complete(self, system, user):
        return ""

    def generate_recipe(self, prompt):
        self.prompts.append(prompt)
        self.n += 1
        return Recipe(
            title=f"Dish {self.n}",
            ingredients=[Ingredient(name="rice", quantity=1, unit="ea")],
            steps=["cook"],
            nutrition=NutritionFacts(protein_g=8, sodium_mg=100),
            food_groups={FoodGroup.PROTEIN: 0.4, FoodGroup.GRAINS: 1.0, FoodGroup.VEGETABLES: 0.6},
            min_age_months=12,
        )


def _planner():
    profile = Profile(
        child=ChildProfile(name="Mia", birthdate=date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5),
        household=HouseholdProfile(), exclusions=Exclusions(),
    )
    llm = _RecordingLLM()
    return Planner(profile=profile, inventory=_Inv(), recipes=InMemoryRecipeRepository(), llm=llm), llm


def test_protein_family_rotates_across_calls():
    planner, llm = _planner()
    families = ["chicken", "beef", "salmon", "lentil"]
    for _ in range(len(families)):
        planner.another_idea()
    # Featured protein is randomized, but a full cycle must feature each family exactly once
    # (no repeats, no deterministic always-chicken-first pattern).
    featured = [next(f for f in families if f"Make {f} the main protein" in p) for p in llm.prompts]
    assert sorted(featured) == sorted(families)


def test_recent_suggestions_are_avoided():
    planner, llm = _planner()
    planner.another_idea()  # -> "Dish 1"
    planner.another_idea()  # -> "Dish 2", should be told to avoid Dish 1
    assert "Dish 1" in llm.prompts[1]
    assert "clearly different" in llm.prompts[1]
    assert planner.recent_suggestions == ["Dish 1", "Dish 2"]


def test_user_exclude_still_passed():
    planner, llm = _planner()
    planner.another_idea(exclude=["pasta"])
    assert "pasta" in llm.prompts[0]


# --- issue #2: customize (free-form note to the kitchen) ---------------------

def test_customize_include_and_instructions_in_prompt():
    planner, llm = _planner()
    planner.customize(instructions="please add broccoli", include=["broccoli"])
    p = llm.prompts[0]
    assert "please add broccoli" in p
    assert "MUST appear" in p and "broccoli" in p


def test_customize_edits_from_base_recipe():
    planner, llm = _planner()
    base = Recipe(
        title="Chicken Rice",
        ingredients=[Ingredient(name="chicken", quantity=1, unit="ea")],
        steps=["cook"], min_age_months=12,
    )
    planner.customize(instructions="swap chicken for tofu", base=base)
    p = llm.prompts[0]
    assert "Start from this current toddler dinner" in p
    assert "Chicken Rice" in p            # base recipe carried into the prompt


def test_customize_guardrail_rejects_unsafe():
    import pytest
    profile = Profile(
        child=ChildProfile(name="Mia", birthdate=date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5),
        household=HouseholdProfile(), exclusions=Exclusions(),
    )

    class _UnsafeLLM:
        def complete(self, system, user):
            return ""

        def generate_recipe(self, prompt):
            return Recipe(
                title="Honey Toast",
                ingredients=[Ingredient(name="honey", quantity=1, unit="tsp")],
                steps=["spread"], min_age_months=12,
            )

    planner = Planner(profile=profile, inventory=_Inv(),
                      recipes=InMemoryRecipeRepository(), llm=_UnsafeLLM())
    with pytest.raises(ValueError):
        planner.customize(instructions="add honey", include=["honey"])
