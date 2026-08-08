"""Integration test for the nutrition pipeline (TODO #1): scaling + validation together.

Uses a birthdate computed as 19 months before today so the child is a real 19-month-old
regardless of when the suite runs.
"""

from __future__ import annotations

from datetime import date

from toddler_dinner.config import ChildProfile, Exclusions, HouseholdProfile, Profile, Sex
from toddler_dinner.models import FoodGroup, Ingredient, NutritionFacts, Recipe
from toddler_dinner.nutrition import (
    age_in_months,
    daily_food_group_targets,
    dinner_food_group_targets,
    median_weight_for_age,
    scale_factor,
    validate_recipe,
)


def _months_ago(n: int) -> date:
    today = date.today()
    total = today.year * 12 + (today.month - 1) - n
    y, m = divmod(total, 12)
    return date(y, m + 1, min(today.day, 28))


def _profile(weight_kg: float, exclusions: Exclusions | None = None) -> Profile:
    return Profile(
        child=ChildProfile(
            name="Mia", birthdate=_months_ago(19), sex=Sex.FEMALE, weight_kg=weight_kg
        ),
        household=HouseholdProfile(location="New Zealand"),
        exclusions=exclusions or Exclusions(),
    )


def _recipe(title, ings, food_groups, sodium_mg=100, min_age=12) -> Recipe:
    return Recipe(
        title=title,
        ingredients=[Ingredient(name=n, quantity=1, unit="ea") for n in ings],
        steps=["cook"],
        nutrition=NutritionFacts(protein_g=8, sodium_mg=sodium_mg),
        food_groups=food_groups,
        min_age_months=min_age,
        approved=True,
    )


def test_child_is_nineteen_months():
    p = _profile(10.4)
    assert age_in_months(p.child.birthdate) == 19


def test_average_child_uses_unscaled_nz_servings():
    median = median_weight_for_age(19, "female")
    p = _profile(median)
    assert abs(scale_factor(p) - 1.0) < 0.02
    daily = daily_food_group_targets(p)
    assert daily[FoodGroup.GRAINS] == 4.0
    assert daily[FoodGroup.PROTEIN] == 1.0


def test_above_average_child_gets_proportionally_more():
    median = median_weight_for_age(19, "female")
    avg = _profile(median)
    heavy = _profile(median * 1.12)
    assert scale_factor(heavy) > scale_factor(avg)
    d_avg = dinner_food_group_targets(avg)
    d_heavy = dinner_food_group_targets(heavy)
    for group in d_avg:
        assert d_heavy[group] > d_avg[group]


def test_full_validation_matrix():
    median = median_weight_for_age(19, "female")
    p = _profile(
        median * 1.12,
        Exclusions(allergies=["egg"], dietary=["pescatarian"], dislikes=["mushroom"]),
    )
    good_groups = {
        FoodGroup.PROTEIN: 0.4,
        FoodGroup.GRAINS: 1.2,
        FoodGroup.VEGETABLES: 0.8,
    }

    # good savoury dinner -> serve
    good = _recipe("salmon rice broccoli", ["salmon", "rice", "broccoli"], good_groups)
    assert validate_recipe(good, p).ok

    # allergen -> hard block
    egg = _recipe("egg omelette", ["egg"], {FoodGroup.PROTEIN: 0.4})
    res = validate_recipe(egg, p)
    assert not res.ok and any("allergen" in v for v in res.hard_violations)

    # dietary rule -> hard block
    chicken = _recipe("chicken pasta", ["chicken", "pasta"], good_groups)
    res = validate_recipe(chicken, p)
    assert not res.ok and any("pescatarian" in v for v in res.hard_violations)

    # sodium ceiling (dinner ceiling ~330mg) -> hard block
    salty = _recipe("salty stew", ["fish"], good_groups, sodium_mg=800)
    res = validate_recipe(salty, p)
    assert not res.ok and any("sodium" in v for v in res.hard_violations)

    # disliked ingredient -> serve, soft warning only
    mushroom = _recipe("mushroom risotto", ["mushroom", "rice"], good_groups)
    res = validate_recipe(mushroom, p)
    assert res.ok and any("mushroom" in w for w in res.soft_warnings)
