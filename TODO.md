# TODO

Tracked work items. Critical items are safety-relevant and must be resolved before the tool
is used to make real feeding decisions.

## 🔴 CRITICAL

- [ ] **Replace placeholder nutrition data with verified primary-source figures.**
  `src/toddler_dinner/nutrition/reference.py` currently contains **best-effort placeholder
  numbers, NOT transcribed from official sources.** They must be replaced with exact values
  from:
  - NZ Ministry of Health — "Eating for Healthy Toddlers" / "Eating and Activity Guidelines"
    (food-group serving guidance, ages 1–3).
  - WHO Child Growth Standards — weight-for-age median (P50), by sex.
  - Verified toddler sodium ceiling (NZ/AU guidance).
  Cite the exact document + page inline next to each constant. Until done, the tool must not be
  treated as giving authoritative portion/nutrition advice.

  **Plan / effort (est. ~half a day of transcription once sources are in hand + your review):**
  - _WHO weight-for-age medians_ — ~1 hr, low risk (unambiguous P50 tables; placeholders close).
  - _Sodium/salt upper limit_ — ~30 min (AU/NZ NHMRC NRV Upper Level for 1–3 yr).
  - _NZ food-group servings_ — ~0.5–1 day, **the crux**: NZ MoH toddler guidance is often
    portion-size/frequency based, not decimal servings-per-group — may need a small **model
    adjustment** in `reference.py`/`nutrition` to match how it's actually published.
  - _Citations + sanity pass_ — ~2–3 hr.

  **Dependencies before starting:**
  1. Supply the source docs: the **NZ MoH toddler guide** (PDF/table) and confirm the **WHO
     Child Growth Standards P50** edition. (Can't be reliably fetched from the dev sandbox; do
     not fabricate citations.)
  2. **Clinical sign-off** on the final numbers (you / a Plunket–Well Child nurse or dietitian)
     — transcription can be faithful, but this is feeding advice for a real child.

  **After real numbers land:** add value-specific tests (e.g. "19-month median-weight girl →
  these dinner targets"). Code is already isolated in `nutrition/reference.py`; 90 tests in place.

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

- [x] #1 — Nutrition tables + weight/age portion scaling (logic done; **data is placeholder — see CRITICAL above**)
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
