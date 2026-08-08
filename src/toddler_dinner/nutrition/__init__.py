"""Nutrition targets + safety validation.

Two layers:
- HARD rules: universal toddler safety + household allergies/dietary rules + sodium ceiling.
  Deterministic. Never bypassed.
- SOFT targets: food-group/portion balance (NZ MoH / NHMRC), scaled by weight + age via the
  WHO weight-for-age median (see reference.py).

Portion scaling rationale: energy/portion needs track body size, not age alone. A child above
the median weight-for-age needs proportionally more, so we scale the average NZ serving counts
by (actual weight / WHO median weight-for-age). See DESIGN.md for the deferred-monitoring caveat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from toddler_dinner.config import Profile
from toddler_dinner.models import FoodGroup, Recipe
from toddler_dinner.nutrition.reference import (
    DAILY_SODIUM_CEILING_MG,
    DIETARY_RULE_EXCLUSIONS,
    DINNER_EXPECTED_GROUPS,
    NZ_DAILY_SERVINGS,
    WHO_MEDIAN_WEIGHT_KG,
)

# Clamp the scale factor so a bad weight entry can't produce a wild portion.
SCALE_MIN = 0.85
SCALE_MAX = 1.30

# Universal toddler choking / unsafe items (non-exhaustive placeholder).
UNSAFE_KEYWORDS = {
    "honey",
    "whole nuts",
    "whole grapes",
    "popcorn",
    "hard candy",
    "raw carrot sticks",
}


def age_in_months(birthdate: date, on: date | None = None) -> int:
    on = on or date.today()
    return (on.year - birthdate.year) * 12 + (on.month - birthdate.month)


def median_weight_for_age(age_months: int, sex: str) -> float:
    """Linear-interpolated WHO median weight-for-age (kg), clamped to the 12-36m table."""
    if sex not in WHO_MEDIAN_WEIGHT_KG:
        raise ValueError(f"unknown sex: {sex!r} (expected one of {sorted(WHO_MEDIAN_WEIGHT_KG)})")
    table = WHO_MEDIAN_WEIGHT_KG[sex]
    ages = sorted(table)
    if age_months <= ages[0]:
        return table[ages[0]]
    if age_months >= ages[-1]:
        return table[ages[-1]]
    lo = max(a for a in ages if a <= age_months)
    hi = min(a for a in ages if a >= age_months)
    if lo == hi:
        return table[lo]
    frac = (age_months - lo) / (hi - lo)
    return table[lo] + frac * (table[hi] - table[lo])


def scale_factor(profile: Profile, on: date | None = None) -> float:
    """actual_weight / WHO median weight-for-age, clamped to [SCALE_MIN, SCALE_MAX]."""
    age_m = age_in_months(profile.child.birthdate, on)
    median = median_weight_for_age(age_m, profile.child.sex.value)
    raw = profile.child.weight_kg / median if median else 1.0
    return max(SCALE_MIN, min(SCALE_MAX, raw))


def daily_food_group_targets(profile: Profile, on: date | None = None) -> dict[FoodGroup, float]:
    """Per-child daily servings = average NZ servings x scale_factor."""
    sf = scale_factor(profile, on)
    return {group: round(base * sf, 2) for group, base in NZ_DAILY_SERVINGS.items()}


def dinner_food_group_targets(profile: Profile, on: date | None = None) -> dict[FoodGroup, float]:
    """Dinner's share of the daily targets (~1/3 by default)."""
    frac = profile.dinner_daily_fraction
    return {g: round(v * frac, 2) for g, v in daily_food_group_targets(profile, on).items()}


@dataclass
class ValidationResult:
    ok: bool
    hard_violations: list[str] = field(default_factory=list)
    soft_warnings: list[str] = field(default_factory=list)


def validate_recipe(recipe: Recipe, profile: Profile, on: date | None = None) -> ValidationResult:
    hard: list[str] = []
    soft: list[str] = []

    excl = profile.exclusions
    age_months = age_in_months(profile.child.birthdate, on)
    ingredient_names = {ing.name.lower() for ing in recipe.ingredients}

    def present(term: str) -> bool:
        t = term.lower()
        return any(t in name for name in ingredient_names)

    # HARD: universal unsafe items
    for kw in UNSAFE_KEYWORDS:
        if present(kw):
            hard.append(f"unsafe/choking-hazard ingredient: {kw}")

    # HARD: household allergies
    for allergen in excl.allergies:
        if present(allergen):
            hard.append(f"allergen present: {allergen}")

    # HARD: dietary rules mapped to concrete ingredient exclusions
    for rule in excl.dietary:
        for banned in DIETARY_RULE_EXCLUSIONS.get(rule.lower(), set()):
            if present(banned):
                hard.append(f"dietary rule '{rule}' violated by: {banned}")

    # HARD: age suitability
    if age_months < recipe.min_age_months:
        hard.append(f"recipe min age {recipe.min_age_months}m > child age {age_months}m")

    # HARD: sodium ceiling for the dinner share (only enforced if sodium is recorded)
    dinner_sodium_ceiling = DAILY_SODIUM_CEILING_MG * profile.dinner_daily_fraction
    if recipe.nutrition.sodium_mg is not None and recipe.nutrition.sodium_mg > dinner_sodium_ceiling:
        hard.append(
            f"sodium {recipe.nutrition.sodium_mg:.0f}mg exceeds dinner ceiling "
            f"{dinner_sodium_ceiling:.0f}mg"
        )

    # SOFT: dislikes down-rank, not banned
    for dislike in excl.dislikes:
        if present(dislike):
            soft.append(f"contains disliked item: {dislike}")

    # SOFT: food-group balance vs scaled dinner targets
    targets = dinner_food_group_targets(profile, on)
    provided = recipe.food_groups
    if provided:
        for group in DINNER_EXPECTED_GROUPS:
            if provided.get(group, 0) <= 0:
                soft.append(f"dinner provides no {group.value}")
        for group, target in targets.items():
            got = provided.get(group, 0)
            if got + 1e-9 < target * 0.5:
                soft.append(
                    f"low {group.value}: {got} servings vs ~{target} dinner target"
                )
    else:
        soft.append("recipe has no food-group data; cannot check balance")

    return ValidationResult(ok=not hard, hard_violations=hard, soft_warnings=soft)
