"""Wiring: build a Planner from config + env (single place to assemble providers)."""

from __future__ import annotations

from functools import lru_cache

from toddler_dinner.config import Secrets, load_profile
from toddler_dinner.core import Planner
from toddler_dinner.persistence.db import make_session_factory
from toddler_dinner.persistence.repositories import (
    PgDinnerHistoryRepository,
    PgMenuRepository,
    PgRecipeRepository,
)
from toddler_dinner.providers.inventory_yaml import YamlInventoryProvider
from toddler_dinner.providers.llm import build_llm_provider

DEFAULT_CONFIG = "config/profile.yaml"
DEFAULT_INVENTORY = "data/inventory.yaml"


@lru_cache(maxsize=None)
def _session_factory(dsn: str):
    """One engine + pool per DSN, reused across build_planner() calls."""
    return make_session_factory(dsn)


def build_planner(
    config_path: str = DEFAULT_CONFIG,
    inventory_path: str = DEFAULT_INVENTORY,
) -> Planner:
    profile = load_profile(config_path)
    secrets = Secrets()
    inventory = YamlInventoryProvider(inventory_path)
    session_factory = _session_factory(secrets.postgres_dsn)
    recipes = PgRecipeRepository(session_factory)
    menus = PgMenuRepository(session_factory)
    history = PgDinnerHistoryRepository(session_factory)
    llm = build_llm_provider(secrets)
    return Planner(
        profile=profile,
        inventory=inventory,
        recipes=recipes,
        llm=llm,
        menus=menus,
        history=history,
    )
