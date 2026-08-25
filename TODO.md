# TODO

Tracked work items. Critical items are safety-relevant and must be resolved before the tool
is used to make real feeding decisions.

## ✅ Resolved

- [x] **#15 — Database discipline: table + column comments.** Every ORM table and column in
  `persistence/orm.py` carries a `comment=` (→ Postgres `COMMENT ON TABLE/COLUMN`), so the schema
  self-documents in `psql \d+` and generated DDL. **Applying to a live DB needs a migration:**
  `alembic revision --autogenerate` picks up the comments (emits `create_table_comment` /
  `alter_column(..., comment=...)`); fold this into the same pending migration pass as #20, then
  regenerate `db/schema.sql`.

- [x] **Nutrition reference data transcribed from cited primary sources.**
  `src/toddler_dinner/nutrition/reference.py` now carries inline source citations:
  - NZ Ministry of Health healthy-eating guidelines — food-group servings.
  - WHO Child Growth Standards — weight-for-age median (P50).
  - NHMRC (AU/NZ) Nutrient Reference Values — sodium upper limit.
  (Male weight-for-age table left at 3-month anchors — interpolated; fill to monthly if desired.)

## 📅 Scheduled — tomorrow

- [x] **LLM assistance for exception cases** (the collapsed "note to the kitchen" chat) — issue #2.
      The box now handles arbitrary requests beyond the three buttons: it classifies free text into
      **navigate / customize / ignore**, and for `customize` builds a recipe via the recipe-maker
      LLM (optionally editing the on-screen card), guardrail-checks it (`validate_recipe`), and
      renders it on **today's or tomorrow's** card. Not auto-saved — the card's own "Save to
      Cookbook" button preserves it. Gibberish is a **no-op** that keeps the current card.
      Delivered:
      - `/api/chat` returns a **recipe card** (not plain text), honouring `include` / `exclude`
        and `target` (today/tomorrow); edit signals ("add", "swap", "make it …") suppress the
        navigation fast path so "add broccoli to tonight's dinner" edits instead of re-suggesting.
      - Surfaces *why* via a note ("Including broccoli", "Avoiding milk, cheese…").

## Roadmap (from DESIGN.md)

- [x] #1 — Nutrition tables + weight/age portion scaling (logic done; **data transcribed from cited sources**)
- [x] #2 — Postgres repositories + Alembic migrations (normalized schema; verified live on Azure PG)
- [x] #3 — Hosted LLM calls (Copilot / OpenAI / Anthropic; see note below)
- [x] #4 — Flow 2: generate a **groceries list** (menu ingredients − fridge), export to Markdown/CSV.
      Single dinner, name-presence subtraction, configurable `variety_days` (default 5), no budget.
      Logic works in-memory; persistence lands with #2.
- [x] #5 — **Card/Button UI + cooking history** (delivered): buttons for
      tonight/another-idea/plan-tomorrow; recipe cards with per-card Save / Cooked It; read-only
      last-N-days history cards each with "Cooked It Today"; collapsed chat for nuance.
      `cooked` flag + migration; JSON endpoints (`/api/*`); deterministic emoji hero images
      (zero storage); mode-aware "Another"; **variety_days applied consistently** across
      tonight/another-idea/plan; profile **timezone** for decision dates; self-hosted fonts;
      practical beginner-friendly recipe steps.

### Future versions (deferred)

- [ ] **Bilingual UI (Chinese / English).** UI strings are easy (small i18n dict + toggle). The real
      work is recipe content: keep the engine **English-canonical** (matching, validation, staples,
      protein rotation, storage all key off English), and add a **display layer** — generate both
      languages in one LLM call (`title_zh`, `ingredients[].name_zh`, `steps_zh`), store both
      (translations table or `*_zh` columns), toggle picks which to render. Needs a **CJK font**
      (e.g. Noto Serif SC; a few MB, self-hosted for offline). Additive migration when revisited.
- [ ] **Supermarket integration** (was the Playwright scraping task). Live availability, specials,
      pricing, budget optimisation, and store selection for New World / Woolworths / Pak'nSave.
      Deferred: Foodstuffs sites are behind Cloudflare anti-bot (headless browsers get 403 from
      datacenter IPs); DOM scraping is high-maintenance. Candidate approaches when revisited:
      Playwright with a persistent human-established browser profile on a residential IP (NAS),
      reverse-engineered JSON APIs, a third-party NZ price aggregator, or graceful degradation.
      The `SupermarketProvider` seam + `supermarket_snapshots` + shopping-list pricing fields are
      reserved for this. (Playwright/Chromium NOT needed until then.)
- [ ] Photo/barcode fridge inventory (`InventoryProvider` swap). **Superseded/expanded** by the
      inventory work below (issues #14, #19, #20 + the input-method design).
- [ ] NAS Ollama as an `LLMProvider`.
- [ ] Growth-curve monitoring module.
- [ ] Richer web UI; meals beyond dinner.

### Note on #3 (LLM providers)
- GitHub **Copilot** works via **device-flow OAuth** (run `toddler-dinner login-copilot`), which
  yields a `ghu_` user token that is exchanged for a short-lived Copilot token. A plain PAT does
  NOT work (confirmed: 404 at the exchange). Verified live end-to-end (chat + recipe generation).
  Still rides undocumented internal endpoints — availability/ToS are the user's responsibility.
- `generate_recipe` relies on `extract_json` to tolerate fenced/prose-wrapped output; if a model
  is unreliable, consider provider structured-output modes.

## 🧊 Inventory rework (issues #14 / #19 / #20 + status model)

Re-processed via starburst + steelman + grill. The earlier quantity/unit "re-confirm with
steppers" design was **superseded**: a steelman surfaced that nothing deterministic reads
`quantity`/`unit` — the matcher and groceries key off `{name}`, and the only consumer is the LLM
prompt string (a soft, unverified hint). Guided by "stay minimal until proof of need," the model
is now a **coarse per-item status**, not quantities.

### LOCKED decisions (status model)
1. **Matcher stays coarse — not quantity-aware.** The real question is "do I have broccoli," not
   "how many grams." No unit reconciliation, no taxonomy.
2. **Per-item `status`: `have` / `low` / `none`.** Replaces numeric quantity as the tracked signal.
3. **`quantity` + `unit` → optional & unused** on `InventoryItem` (kept nullable for reversibility,
   not captured in the input loop, not required by any code path).
4. **Catalog model.** Inventory is a persistent list of foods the household stocks; items stay
   listed even when `none` (so you can see the gap and restock). A genuinely new food is a rare
   **manual add**. Default status on add / seed = `have`.
5. **Status → behaviour:**
   - `have` — on-hand; sent to the LLM plainly; may be the **main** ingredient.
   - `low` — still on-hand for tonight's match; annotated to the LLM as **not the main** ingredient;
     never auto-added to the buy list.
   - `none` — **not** on-hand (excluded from the match set & the LLM's "what you have"); if a chosen
     recipe needs it, it goes on the **need-to-buy** list, **unless** it's a pantry staple
     (existing `PANTRY_STAPLES` / `_is_staple` already exempts water, salt, pepper, oil, …).
6. **`best_before` — kept, display-only.** No code reads it; surfaced as a column in the #14 drawer
   for the user to eyeball weekly / before planning tomorrow. No automation.
7. **Seed file** `data/inventory.seed.yaml` (items `{name, category, location, status, best_before?}`,
   dropping `quantity`/`unit`) — **every item ships as `status: none`**. Loaded into the table on
   **initial deployment only** (empty catalog); after that the DB is source of truth and the file
   isn't re-read. Purpose: lift the workload of typing the whole catalog in — you just flip what you
   actually have.
8. **No automation (Q5 closed by deferral).** No staleness timers, re-confirm prompts, or
   notifications. The read-only drawer (status + `best_before`) is the manual review surface.
   The user self-manages freshness by glancing at it.

### Build plan — 3 units, in order
1. **✅ Logic slice (no DB) — DONE.** `InventoryItem` gained `status` (+ optional qty/unit); matcher
   treats `have`/`low` as on-hand and excludes `none`; the 2 LLM prompt sites
   (`another_idea`, `customize`) send names only and annotate `low`; groceries buy `none`
   (staples still exempt); added `data/inventory.seed.yaml` (all `none`); tests added.
2. **◐ #20 — DB catalog — CODE DONE, migration pending.** `inventory_items` table
   (`InventoryItemORM`, unique name, `status`, nullable `quantity`/`unit`, `best_before`) +
   `InventoryRepository` (extends `InventoryProvider`) + `PgInventoryRepository` (list /
   upsert_many / set_status / delete) + `InMemoryInventoryRepository`; `build_planner` cut YAML→DB;
   tests added.
   **Seeding = initial deployment only** via `toddler-dinner inventory seed` (loads
   `data/inventory.seed.yaml`, all `none`, skips if the catalog is non-empty); wired into
   `docker-entrypoint.sh` after migrations. A future input UI is how the user flips statuses.
   **Migration must be generated in a real env (not hand-written):**
   - [ ] `alembic revision --autogenerate -m "inventory_items catalog"` (grounded in
     `InventoryItemORM`); confirm it creates `inventory_items` + the unique `name` index and nothing
     else. **Create-table only — no data seed in the migration** (seeding is the YAML loader above).
   - [ ] Re-run `alembic revision --autogenerate` and confirm an **empty** diff (proves the migration
     matches the ORM).
   - [ ] Regenerate `db/schema.sql` (`alembic upgrade head --sql`) — already stale (missing the last
     3 migrations), so regenerate wholesale, don't hand-patch.
   - Note: until this migration exists + is applied, the app can't read inventory (table absent) —
     expected WIP; the test suite is unaffected (uses in-memory fakes).
3. **#14 — read-only drawer (after the migration).** `GET /api/inventory` + top-right hamburger →
   right slide-in drawer, grouped by location, showing **status + best_before**, over a blurred
   backdrop; Esc/backdrop/X to close; a11y. Backed by the `list_items()` read port.

### Deferred (future discussion — the old #19)
- **Status editing UI** (tap-to-cycle `have`→`low`→`none`, add new item). Until then, status is set
  by editing the YAML/DB directly; the #14 drawer stays genuinely read-only.
- **Photo→vision capture** as a draft-into-review accelerator — needs a new vision capability
  (`LLMProvider` is text-only today: `complete`, `generate_recipe`).
- Any automation/nudging, if manual review ever proves insufficient.

## Nice-to-have

- [ ] Expand the recipe-card emoji map for daily foods + revisit the fallback (currently 🍲).
- [ ] Tune soft food-group warnings so only `DINNER_EXPECTED_GROUPS` are flagged (reduce noise).
- [ ] Replace dietary/ingredient substring matching with a proper ingredient taxonomy.
- [ ] Remove/retire the unused `PlaywrightSupermarketProvider` stub, or keep as a documented
      placeholder for the future supermarket-integration work.
