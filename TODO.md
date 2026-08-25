# TODO

Tracked work items. Critical items are safety-relevant and must be resolved before the tool
is used to make real feeding decisions.

## ✅ Resolved

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

## 🧊 Inventory rework (issues #14 / #19 / #20 + input-method design)

Brainstormed via starburst + grill. #19 was split; the input-method half is designed below and
awaits a ticket. **Next step: close the open cadence/nudging fork, then raise the sibling issue.**

### Ticket status
- **#20 — backend table persistence (raised).** `inventory_items` table + ORM + Alembic
      migration; `InventoryRepository` CRUD port + Postgres adapter (also satisfies the existing
      `InventoryProvider.list_items()` read port); cut `build_planner` YAML→DB; one-off YAML→table
      import; tests; README + DESIGN updates. Excludes HTTP CRUD endpoints + input UX.
- **#14 — Show Inventory drawer (refined).** Read-only viewer: top-right hamburger → right
      slide-in drawer, grouped by location, over a blurred backdrop; Esc/backdrop/X to close; a11y.
      Reads via a new `GET /api/inventory` (backed by the read port, so it works before *and* after
      the #20 DB cutover). Note: display design leans on the input-method discussion below.
- **#19 (sibling, NOT yet raised) — inventory input method.** Design captured below; raise once
      the cadence/nudging fork is closed.

### Input-method design — LOCKED decisions
1. **Backbone = periodic full-state snapshot / re-confirm that overwrites.** Nothing inferred is
   trusted state — avoids compounding drift of an incremental/inferred model.
2. **Auto-depletion is OUT of the authoritative path.** `cook()` must not silently mutate counts;
   at most a future *non-authoritative* "might be low, check" nudge inside a refresh.
3. **Capture mechanism = pre-filled re-confirm review (A).** App shows the last snapshot; user
   walks the fridge and edits only deltas. Reuses the #14 drawer + #20 CRUD; no AI failure mode.
   Photo→vision (B) is a *deferred accelerator* that only drafts into A's review screen
   (photo proposes, human disposes).
4. **Refresh unit = per-location.** Fridge / shelf / freezer each independently snapshotted +
   `last_confirmed` timestamped; confirming a location overwrites only that location's set.
   Moving an item between locations is just an edit reassigning its `location`.
5. **Device = iPad, touch-first, used at the fridge** (full/near-full width in this mode, big tap
   targets, no keyboard reliance). Detailed interface deferred.
6. **Effort ∝ changes, not item count.** Default is "nothing changed"; one **Confirm** stamps the
   timestamp on everything untouched. Rationale: the matcher is **presence-based**
   (`match_from_inventory` keys off `{name}`; quantity/unit are stored but unused by the draw or
   groceries logic today).
7. **Keep `quantity` + `unit` as the stored format** (aligned with existing `InventoryItem`/YAML,
   so #20's schema is untouched and quantity-aware features stay open) — but **input via taps, not
   typing**: −/＋ steppers in the item's own unit + optional quick-set chips. (Status-only In/Low/Out
   was considered and dropped to stay aligned with the current format.)
8. **Units are per-item, natural, and pinned in a catalog — decided once, never at input time.**
   Rule: use the unit you can assess by eye without a tool — `1 head` of broccoli, not `0.4 kg`
   (fake precision no one maintains). Countable→count (head/each), packaged→package
   (can/bottle/loaf/L), genuinely bulk→weight (g/kg) — exactly the units the existing YAML uses.
   The "broccoli count or weight?" question is answered once at catalog-seed time.

### New components / dependencies this design requires
- **Per-item catalog with canonical natural units** (NEW). Dictionary of every item the household
  stocks, each pinned to one natural unit + category. Powers name autocomplete, removes unit choice
  from the input loop, seeds from `data/inventory.example.yaml`. A build dependency, not free.
- **Per-item `last_confirmed` timestamp + per-location staleness** surfaced in the #14 drawer.

### Accepted residual weaknesses
- **Half-used bulk** (half a mince pack, leftover rice) stays fuzzy even in natural units.
  Acceptable while matching is presence-only; the soft spot if we go quantity-aware.
- Photo/vision path needs a **new vision capability** — `LLMProvider` is text-only today
  (`complete`, `generate_recipe`).

### OPEN forks (resume here)
- **Q5 — cadence & nudging (in progress).** Recommendation on the table: **staleness-driven +
  point-of-use, in-app, no external notifications** (app has no push infra). Each location gets a
  freshness horizon (fridge short, freezer long); the #14 drawer shows per-location freshness; just
  before a fridge-aware draw a stale location triggers a gentle, skippable re-confirm prompt — so
  accuracy is demanded in proportion to use. **Awaiting user accept/reject of this philosophy.**
- Catalog seeding & maintenance: initial seed source, adding a brand-new item mid-refresh.
- Interface details (deferred by user).

## Nice-to-have

- [ ] Expand the recipe-card emoji map for daily foods + revisit the fallback (currently 🍲).
- [ ] Tune soft food-group warnings so only `DINNER_EXPECTED_GROUPS` are flagged (reduce noise).
- [ ] Replace dietary/ingredient substring matching with a proper ingredient taxonomy.
- [ ] Remove/retire the unused `PlaywrightSupermarketProvider` stub, or keep as a documented
      placeholder for the future supermarket-integration work.
