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
    for _ in range(3):
        planner.another_idea()
    # families (distinct, in order): chicken, beef, salmon, lentil
    assert "Make chicken the main protein" in llm.prompts[0]
    assert "Make beef the main protein" in llm.prompts[1]
    assert "Make salmon the main protein" in llm.prompts[2]


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
