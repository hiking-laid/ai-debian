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

- [ ] **Test & improve LLM assistance for exception cases** (the collapsed "more options" chat).
      Exercise free-text requests: "avoid broccoli", "use up the broccoli", "make it dairy-free",
      "something lighter", etc., and judge quality (a quick test on the current page felt
      unsatisfying).
      Known gaps to address:
      - The `/chat` path returns **plain text** (`recipe_text`), not a **recipe card** — make the
        exception flow render a card like the buttons do (consistent UX).
      - Verify the router reliably extracts params (`exclude`, `fresh`, `date`) and that
        `another_idea(exclude=...)` actually honours them in the generated recipe.
      - Consider surfacing *why* (e.g. "avoiding broccoli") and allowing follow-ups.

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
- [ ] Photo/barcode fridge inventory (`InventoryProvider` swap).
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

## Nice-to-have

- [ ] Expand the recipe-card emoji map for daily foods + revisit the fallback (currently 🍲).
- [ ] Tune soft food-group warnings so only `DINNER_EXPECTED_GROUPS` are flagged (reduce noise).
- [ ] Replace dietary/ingredient substring matching with a proper ingredient taxonomy.
- [ ] Remove/retire the unused `PlaywrightSupermarketProvider` stub, or keep as a documented
      placeholder for the future supermarket-integration work.
