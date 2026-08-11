from datetime import date

from toddler_dinner.config import (
    ChildProfile,
    Exclusions,
    HouseholdProfile,
    Profile,
    Sex,
)
from toddler_dinner.core import match_from_inventory
from toddler_dinner.models import FoodGroup, Ingredient, InventoryItem, NutritionFacts, Recipe
from toddler_dinner.nutrition import (
    age_in_months,
    daily_food_group_targets,
    median_weight_for_age,
    scale_factor,
    validate_recipe,
)


def _profile(**child_kw) -> Profile:
    base = dict(birthdate=date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5)
    base.update(child_kw)
    return Profile(
        child=ChildProfile(**base),
        household=HouseholdProfile(),
        exclusions=Exclusions(),
    )


def _profile_with(exclusions: Exclusions, **child_kw) -> Profile:
    base = dict(birthdate=date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5)
    base.update(child_kw)
    return Profile(
        child=ChildProfile(**base),
        household=HouseholdProfile(),
        exclusions=exclusions,
    )


def _recipe(title: str, ings: list[str], **kw) -> Recipe:
    return Recipe(
        title=title,
        ingredients=[Ingredient(name=n, quantity=1, unit="ea") for n in ings],
        steps=["cook"],
        nutrition=kw.pop("nutrition", NutritionFacts(protein_g=8.0)),
        food_groups=kw.pop(
            "food_groups",
            {FoodGroup.VEGETABLES: 0.8, FoodGroup.PROTEIN: 0.4, FoodGroup.GRAINS: 1.2},
        ),
        approved=True,
        **kw,
    )


# --- matching ---------------------------------------------------------------

def test_exact_match():
    recipes = [_recipe("chicken rice", ["chicken", "rice"])]
    items = [
        InventoryItem(name="chicken", quantity=1, unit="ea"),
        InventoryItem(name="rice", quantity=1, unit="ea"),
    ]
    result = match_from_inventory(recipes, items)
    assert result.kind == "exact"
    assert result.recipe.title == "chicken rice"


def test_partial_match_reports_missing():
    recipes = [_recipe("chicken rice broccoli", ["chicken", "rice", "broccoli"])]
    items = [InventoryItem(name="chicken", quantity=1, unit="ea"),
             InventoryItem(name="rice", quantity=1, unit="ea")]
    result = match_from_inventory(recipes, items)
    assert result.kind == "partial"
    assert "broccoli" in result.missing


def test_no_match():
    recipes = [_recipe("fish stew", ["fish", "tomato"])]
    items = [InventoryItem(name="chicken", quantity=1, unit="ea")]
    result = match_from_inventory(recipes, items)
    assert result.kind in ("partial", "none")


def test_pantry_staples_not_reported_as_missing():
    # water/salt/oil are assumed on hand -> an otherwise-complete recipe is an exact match,
    # and they never appear in the 'missing' list.
    recipes = [_recipe("chicken rice", ["chicken", "rice", "water", "salt", "olive oil"])]
    items = [InventoryItem(name="chicken", quantity=1, unit="ea"),
             InventoryItem(name="rice", quantity=1, unit="ea")]
    result = match_from_inventory(recipes, items)
    assert result.kind == "exact"
    assert result.missing == []


def test_partial_missing_excludes_staples():
    recipes = [_recipe("veg mash", ["kumara", "broccoli", "water"])]
    items = [InventoryItem(name="kumara", quantity=1, unit="ea")]
    result = match_from_inventory(recipes, items)
    assert result.kind == "partial"
    assert "broccoli" in result.missing
    assert "water" not in result.missing   # staple, never flagged as missing


# --- validation -------------------------------------------------------------

def test_allergy_is_hard_violation():
    r = _recipe("egg omelette", ["egg", "milk"])
    res = validate_recipe(r, _profile_with(Exclusions(allergies=["egg"])))
    assert not res.ok
    assert any("egg" in v for v in res.hard_violations)


def test_dietary_rule_vegetarian_blocks_meat():
    r = _recipe("chicken pasta", ["chicken", "pasta"])
    res = validate_recipe(r, _profile_with(Exclusions(dietary=["vegetarian"])))
    assert not res.ok
    assert any("vegetarian" in v for v in res.hard_violations)


def test_dislike_is_soft_only():
    r = _recipe("broccoli bake", ["broccoli"])
    res = validate_recipe(r, _profile_with(Exclusions(dislikes=["broccoli"])))
    assert res.ok  # not banned
    assert any("broccoli" in w for w in res.soft_warnings)


def test_sodium_ceiling_is_hard():
    r = _recipe("salty stew", ["chicken"], nutrition=NutritionFacts(sodium_mg=900))
    res = validate_recipe(r, _profile())  # dinner ceiling = 1000 * 0.33 ≈ 330mg
    assert not res.ok
    assert any("sodium" in v for v in res.hard_violations)


# --- scaling ----------------------------------------------------------------

def test_age_in_months():
    assert age_in_months(date(2024, 1, 15), on=date(2025, 8, 15)) == 19


def test_median_weight_interpolates():
    w18 = median_weight_for_age(18, "female")
    w19 = median_weight_for_age(19, "female")
    assert 10.2 <= w18 <= 10.3
    assert w18 < w19 < median_weight_for_age(21, "female")


def test_unknown_sex_raises():
    import pytest

    with pytest.raises(ValueError):
        median_weight_for_age(19, "other")


def test_heavier_child_gets_larger_portions():
    on = date(2025, 8, 15)  # child is 19 months
    light = _profile(weight_kg=median_weight_for_age(19, "female"))
    heavy = _profile(weight_kg=median_weight_for_age(19, "female") * 1.15)
    assert scale_factor(heavy, on) > scale_factor(light, on)
    veg_light = daily_food_group_targets(light, on)[FoodGroup.VEGETABLES]
    veg_heavy = daily_food_group_targets(heavy, on)[FoodGroup.VEGETABLES]
    assert veg_heavy > veg_light


def test_scale_factor_is_clamped():
    on = date(2025, 8, 15)
    huge = _profile(weight_kg=median_weight_for_age(19, "female") * 5)
    assert scale_factor(huge, on) <= 1.30
