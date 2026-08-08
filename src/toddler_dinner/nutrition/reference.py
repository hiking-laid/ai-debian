"""Reference data for toddler nutrition (approximate — verify against current sources).

⚠️  CRITICAL — PLACEHOLDER DATA. The numeric values below are best-effort approximations,
    NOT transcribed from official NZ MoH / WHO publications. Do NOT treat portion or nutrition
    output as authoritative until these are replaced with verified primary-source figures.
    See TODO.md (CRITICAL) and DESIGN.md Open Items.

Sources to encode precisely (see DESIGN.md Open Items):
- NZ Ministry of Health "Eating and Activity Guidelines" / "Eating for Healthy Toddlers"
  (food-group serving guidance for ages 1-3).
- WHO Child Growth Standards — weight-for-age median (P50), used to scale portions to the
  actual child rather than the average child.

All numbers below are best-effort placeholders at sensible values; they are isolated here so
they can be replaced with exact published figures without touching logic.
"""

from __future__ import annotations

from toddler_dinner.models import FoodGroup

# --- NZ food-group daily servings for a toddler (ages ~1-3), for the AVERAGE child -----------
# These are scaled per-child by weight-for-age (see nutrition.scale_factor).
NZ_DAILY_SERVINGS: dict[FoodGroup, float] = {
    FoodGroup.VEGETABLES: 2.5,
    FoodGroup.FRUIT: 2.0,
    FoodGroup.GRAINS: 4.0,
    FoodGroup.DAIRY: 1.5,
    FoodGroup.PROTEIN: 1.0,
}

# Groups a typical savoury dinner is expected to contribute at least something toward.
DINNER_EXPECTED_GROUPS: tuple[FoodGroup, ...] = (
    FoodGroup.VEGETABLES,
    FoodGroup.PROTEIN,
    FoodGroup.GRAINS,
)

# --- Hard safety ceilings (do NOT scale with weight) ----------------------------------------
# Toddler daily sodium ceiling (mg). NZ/AU guidance is roughly <1000 mg/day for 1-3 years.
DAILY_SODIUM_CEILING_MG: float = 1000.0

# --- WHO weight-for-age median (P50), kg, by age in months. Anchor points; interpolated. ----
# Approximate WHO Child Growth Standards medians.
WHO_MEDIAN_WEIGHT_KG: dict[str, dict[int, float]] = {
    "female": {
        12: 8.9, 15: 9.6, 18: 10.2, 21: 10.9, 24: 11.5,
        27: 12.1, 30: 12.7, 33: 13.3, 36: 13.9,
    },
    "male": {
        12: 9.6, 15: 10.3, 18: 10.9, 21: 11.5, 24: 12.2,
        27: 12.7, 30: 13.3, 33: 13.8, 36: 14.3,
    },
}

# --- Dietary-rule mapping: rule -> ingredient substrings that are HARD-excluded --------------
DIETARY_RULE_EXCLUSIONS: dict[str, set[str]] = {
    "vegetarian": {"chicken", "beef", "pork", "lamb", "ham", "bacon", "fish",
                   "salmon", "tuna", "prawn", "shrimp", "meat", "sausage"},
    "vegan": {"chicken", "beef", "pork", "lamb", "ham", "bacon", "fish", "salmon",
              "tuna", "prawn", "shrimp", "meat", "sausage", "milk", "cheese",
              "yoghurt", "yogurt", "butter", "cream", "egg", "honey", "gelatin"},
    "pescatarian": {"chicken", "beef", "pork", "lamb", "ham", "bacon", "meat", "sausage"},
    "halal": {"pork", "ham", "bacon", "gelatin", "lard", "alcohol", "wine"},
    "kosher": {"pork", "ham", "bacon", "prawn", "shrimp", "shellfish", "crab", "lobster"},
    "dairy_free": {"milk", "cheese", "yoghurt", "yogurt", "butter", "cream"},
    "gluten_free": {"wheat", "barley", "rye", "bread", "pasta", "flour", "couscous"},
}
