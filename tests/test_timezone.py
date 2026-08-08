"""Timezone: decision dates come from profile.household.timezone, not UTC."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from toddler_dinner.config import ChildProfile, Exclusions, HouseholdProfile, Profile, Sex
from toddler_dinner.core import Planner
from toddler_dinner.persistence import InMemoryRecipeRepository


class _Inv:
    def list_items(self):
        return []


def _planner(tz: str) -> Planner:
    profile = Profile(
        child=ChildProfile(name="Mia", birthdate=date(2024, 1, 15), sex=Sex.FEMALE, weight_kg=11.5),
        household=HouseholdProfile(location="X", timezone=tz), exclusions=Exclusions(),
    )
    return Planner(profile=profile, inventory=_Inv(), recipes=InMemoryRecipeRepository())


def test_today_uses_profile_timezone():
    p = _planner("Pacific/Kiritimati")  # UTC+14, far from UTC
    assert p.today() == datetime.now(ZoneInfo("Pacific/Kiritimati")).date()


def test_today_new_zealand():
    p = _planner("Pacific/Auckland")
    assert p.today() == datetime.now(ZoneInfo("Pacific/Auckland")).date()


def test_bad_timezone_falls_back_to_utc():
    p = _planner("Not/AZone")
    assert p.today() == datetime.now(ZoneInfo("UTC")).date()
