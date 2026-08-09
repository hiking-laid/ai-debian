"""Reference data for toddler nutrition.

Values are transcribed from cited primary sources (URLs inline next to each constant):
- NZ Ministry of Health healthy-eating guidelines — food-group serving guidance.
- WHO Child Growth Standards — weight-for-age median (P50), used to scale portions to the
  actual child rather than the average child.
- NHMRC (AU/NZ) Nutrient Reference Values — sodium upper limit.

Data is isolated in this module so figures can be updated without touching logic. Serving
figures are for the AVERAGE child at a given age; the nutrition logic scales them per-child by
weight-for-age (see nutrition.scale_factor).
"""

from __future__ import annotations

from toddler_dinner.models import FoodGroup

# --- NZ food-group daily servings for a toddler (ages ~1-3), for the AVERAGE child -----------
# These are scaled per-child by weight-for-age (see nutrition.scale_factor).
# Source: 
# 0-2 years: https://www.health.govt.nz/publications/healthy-eating-guidelines-for-new-zealand-babies-and-toddlers-0-2-years-old
# 2-18 years: https://www.health.govt.nz/publications/food-and-nutrition-guidelines-for-healthy-children-and-young-people-aged-2-18-years-a-background
NZ_DAILY_SERVINGS: dict[FoodGroup, float] = {
    FoodGroup.VEGETABLES: 2.5,
    FoodGroup.FRUIT: 1.0,
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
# Source: https://www.nhmrc.gov.au/about-us/publications/nutrient-reference-values-australia-and-new-zealand-including-recommended-dietary-intakes
# [page_213](nutrient-reference-dietary-intakes-australia-new-zealand.pdf#page=213)
DAILY_SODIUM_CEILING_MG: float = 1000.0

# --- WHO weight-for-age median (P50), kg, by age in months. Anchor points; interpolated. ----
# Approximate WHO Child Growth Standards medians.
# Source: https://www.who.int/tools/child-growth-standards/standards/weight-for-age
WHO_MEDIAN_WEIGHT_KG: dict[str, dict[int, float]] = {
    "female": {
        12: 8.9, 13: 9.2, 14: 9.4, 15: 9.6, 16: 9.8, 17: 10.0, 18: 10.2, 19: 10.4, 20: 10.65, 21: 10.9, 22: 11.1, 23: 11.3, 24: 11.5,
        25: 11.7, 26: 11.9, 27: 12.1, 28: 12.3, 29: 12.5, 30: 12.7, 31: 12.9, 32: 13.1, 33: 13.3, 34: 13.5, 35: 13.7, 36: 13.9,
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
