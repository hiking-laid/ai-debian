"""SupermarketProvider placeholder — DEFERRED TO FUTURE VERSIONS.

Live supermarket data (availability / specials / pricing) is out of scope for v1. Flow 2 only
produces a plain groceries list (menu ingredients minus fridge contents); the user finds items
in-store themselves.

This stub is kept only to reserve the `SupermarketProvider` seam. When revisited, note that
Foodstuffs sites (New World / Pak'nSave) are behind Cloudflare anti-bot and block headless
browsers from datacenter IPs — see DESIGN.md §10 and TODO.md (Future versions) for candidate
approaches. Playwright/Chromium are NOT a dependency until then.
"""

from __future__ import annotations

from toddler_dinner.interfaces import SupermarketProvider
from toddler_dinner.models import SupermarketSnapshot


class PlaywrightSupermarketProvider(SupermarketProvider):
    def fetch_snapshot(
        self, chain: str, store_name: str, store_url: str | None = None
    ) -> SupermarketSnapshot:
        # Deferred to future versions (see module docstring). Not implemented in v1.
        raise NotImplementedError(
            "Supermarket integration is deferred to a future version; v1 outputs a "
            "groceries list only."
        )
