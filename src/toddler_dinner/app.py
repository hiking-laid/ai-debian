"""Wiring: build a Planner from config + env (single place to assemble providers)."""

from __future__ import annotations

from functools import lru_cache

from toddler_dinner.config import Secrets, load_profile
from toddler_dinner.core import Planner
from toddler_dinner.persistence.db import make_session_factory
from toddler_dinner.persistence.repositories import (
    PgDinnerHistoryRepository,
    PgInventoryRepository,
    PgMenuRepository,
    PgRecipeRepository,
    PgStickerRepository,
)
from toddler_dinner.providers.llm import build_llm_provider

DEFAULT_CONFIG = "config/profile.yaml"
DEFAULT_SEED = "data/inventory.seed.yaml"


@lru_cache(maxsize=None)
def _session_factory(dsn: str):
    """One engine + pool per DSN, reused across build_planner() calls."""
    return make_session_factory(dsn)


def build_planner(
    config_path: str = DEFAULT_CONFIG,
) -> Planner:
    profile = load_profile(config_path)
    secrets = Secrets()
    session_factory = _session_factory(secrets.postgres_dsn)
    inventory = PgInventoryRepository(session_factory)  # catalog now lives in Postgres
    recipes = PgRecipeRepository(session_factory)
    menus = PgMenuRepository(session_factory)
    history = PgDinnerHistoryRepository(session_factory)
    stickers = PgStickerRepository(session_factory)
    llm = build_llm_provider(secrets)
    return Planner(
        profile=profile,
        inventory=inventory,
        recipes=recipes,
        llm=llm,
        menus=menus,
        history=history,
        stickers=stickers,
    )


def seed_inventory_if_empty(seed_path: str = DEFAULT_SEED, *, force: bool = False) -> int:
    """Load the inventory seed file into the catalog on initial deployment only.

    No-op when the catalog already has items (so it never clobbers real stock) unless `force`.
    Returns the number of items seeded (0 if skipped or the seed file is absent).
    """
    from pathlib import Path

    from toddler_dinner.providers.inventory_yaml import YamlInventoryProvider

    repo = PgInventoryRepository(_session_factory(Secrets().postgres_dsn))
    if not force and repo.list_items():
        return 0
    path = Path(seed_path)
    if not path.exists():
        return 0
    items = YamlInventoryProvider(path).list_items()
    return repo.upsert_many(items)  # one transaction, one commit
