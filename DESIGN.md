# Toddler Dinner Planner — Design

> A personal tool that plans age-appropriate **dinners** for a toddler based on what's in the
> fridge, and produces a supermarket shopping list for the next day based on local store
> availability, specials, season, location, and budget.

## 1. Goals & Scope

- **Primary user:** one family, one toddler (age derived from birthdate; ~19 months at time of writing).
- **Meal:** dinner only.
- **Two jobs:**
  1. Suggest **tonight's dinner** from what's already in the fridge/shelf.
  2. Plan **tomorrow's dinner** + a **shopping list**, using local supermarket availability & specials.
- **First-class constraint:** age-appropriate **nutrition balance** and **safety**.
- **Personal tool:** no authentication, no multi-tenancy. Single hardcoded household via config.

### Non-goals (v1)
- Multi-user / accounts / cloud hosting.
- Growth-curve monitoring (percentile tracking). Explicitly deferred.
- Meals other than dinner.
- To-the-cent budget solving (budget is a soft optimization target).
- Automated fridge tracking (photo/barcode) — designed for, not built.

## 2. Key Decisions (with rationale)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Scope | Personal, single-family, no auth | Fastest path to a working tool; generalize later |
| 2 | Config vs code | Household/child profile in a **config file** | Change details without code edits |
| 3 | Recipe strategy | **Database-first**, LLM on demand | Validated & cheap by default; fresh ideas when wanted |
| 4 | Nutrition source | **NZ MoH / NHMRC** toddler guidance | Local relevance; portion/food-group based |
| 5 | Portion basis | Driven by **actual weight + age** | Sidesteps ethnic growth-curve debate; needs scale with body weight |
| 6 | Nutrition model | Hard safety rules + soft food-group targets; dinner ≈ ⅓ daily | Safety is deterministic; balance is portion-based |
| 7 | Fridge input | Manual **catalog** behind `InventoryProvider`; coarse per-item **status** (have/low/none), not quantities | Matching is name-presence; exact counts are effort nobody maintains |
| 8 | Supermarket data | **Deferred to future versions.** v1 outputs a groceries list only | Live scraping blocked by Cloudflare/anti-bot on Foodstuffs sites; not worth the fragility now |
| 9 | Shopping output | Flow 2 produces a **groceries list** (needed items − fridge), no live pricing/availability | User finds items/specials in-store themselves |
| 10 | ~~Snapshot reuse~~ | N/A in v1 (no scraping) | Revisit with future supermarket integration |
| 11 | Interface | CLI + **hybrid skill routing** + simple **chat web UI** | Flexible phrasing, scriptable core, minimal UI |
| 12 | LLM | Hosted API behind `LLMProvider`, key via env/config | Swappable to NAS Ollama later |
| 13 | Persistence | **Postgres (NAS)** + config file (inventory is a Postgres table) | Reuse existing infra; right tool per data type |
| 14 | Language | **Python** | User efficiency; strong Playwright/LLM/Postgres support |
| 15 | Packaging | Single container + thin compose | One-command startup; no browser needed in v1 |
| 16 | Exclusions | **Three-tier**: allergies + dietary = hard, dislikes = soft | Safety-critical vs flexible |

## 3. Architecture

Core is a set of **callable actions** ("skills"), reachable three ways:

```
                 ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
                 │     CLI      │   │  Chat Web UI │   │  Direct function │
                 │ (subcommands)│   │ (single page)│   │      calls       │
                 └──────┬───────┘   └──────┬───────┘   └────────┬─────────┘
                        │                  │                    │
                        └───────── Skill Router (intent) ───────┘
                          (fast-path keywords + LLM fallback)
                                          │
                     ┌────────────────────┴─────────────────────┐
                     │                Core Actions              │
                     │  tonight · plan_tomorrow · another_idea  │
                     └────┬───────────┬──────────┬─────────┬────┘
                          │           │          │         │
                 InventoryProvider  RecipeRepo  Validator  LLMProvider
                  (Postgres)        (Postgres)  (rules)    (hosted→Ollama)
                                        │
                                   PostgreSQL (NAS)
```

> Supermarket data (live availability/specials/pricing) is **deferred to future versions** — see
> §10. v1's Flow 2 produces a plain groceries list. The `SupermarketProvider` seam is retained
> as a placeholder for that future work.

### Provider interfaces (seams for later swaps)
- `InventoryProvider` — v1: Postgres catalog (per-item have/low/none). Later: photo/barcode input UI.
- `SupermarketProvider` — **placeholder seam; no v1 implementation** (see §10 future versions).
- `LLMProvider` — v1: hosted API (Copilot/OpenAI/Anthropic). Later: NAS Ollama.
- `RecipeRepository` — Postgres-backed store of validated recipes.

## 4. Flows

### Flow 1 — Tonight's dinner (fast, offline, no browser)
1. Read current inventory (Postgres catalog).
2. **Exact/strong DB match** → serve.
3. Else **partial match**: rank DB recipes by ingredient overlap; show closest + *what's missing*.
4. Else **no viable match** → LLM generates a recipe from available items → **Validator** checks
   safety + nutrition → on user approval, **save to DB as approved**.
5. Render menu.

> Step 4 makes normal use **self-grow the recipe DB**, healing the cold-start/sparse-DB case.

### Flow 2 — Plan tomorrow (on demand)
1. Propose tomorrow's menu (DB-first, LLM if desired) honoring nutrition + exclusions + season.
2. Compute a **groceries list**: ingredients required by the menu **minus what's already in the
   fridge**, consolidated by item with quantities.
3. Persist menu + groceries list in Postgres; **export the groceries list** to Markdown/CSV.
4. **You** take the list to the supermarket and find items/specials yourself.

> v1 does **not** fetch live availability, pricing, or specials. Budget optimisation and
> store-specific pricing are **future versions** (see §10). The list is quantity-only.

### Save vs Cooked (two independent actions)
- **Save to cookbook** → `approved=true`. Curates your **library**; makes "Tonight" fast/free by
  serving from approved recipes (DB-first) instead of always generating.
- **Cooked It** → persists the recipe (`cooked=true`) + a `dinner_history` entry for today. Your
  **diary** of what was actually served: feeds the history view *and* excludes the dish from
  suggestions for `variety_days`. A recipe can be both; repeats **dedup by title** (one row).

### History view (Recently Cooked)
Read-only cards for the last `history_days` cooked dinners (full recipe, for reusing leftover
veg), each with a single **Cooked It Today** to re-record it. Generative leftover-reuse
("use up my broccoli") is a future version.

## 5. Nutrition & Safety Model

- **Hard rules (universal, deterministic):** choking hazards (whole nuts, hard round foods, etc.),
  no honey, no added sugar, sodium ceiling, age-appropriate texture.
- **Hard exclusions (household):** allergies, dietary rules (cultural/religious/veg).
- **Soft targets:** food-group/portion balance from NZ MoH / NHMRC, scaled by the child's
  **current weight + age**; dinner targets ≈ ⅓ of daily needs.
- **Soft dislikes:** down-ranked, not banned; overridable.
- Every LLM-generated recipe passes the **Validator** before it can be served or stored.

## 6. Data Model

### Config file (human-edited)
- Child: `birthdate`, `sex`, `weight_kg`, activity level.
- Household: `location`, `timezone` (IANA, e.g. `Pacific/Auckland` — drives "today"/date windows).
- `exclusions`: `allergies[]` (hard), `dietary[]` (hard), `dislikes[]` (soft).
- Tuning: `dinner_daily_fraction`, `variety_days` (avoid repeats), `history_days` (history view).
- Secrets (env): LLM provider/key, Postgres DSN.

> **Timezone:** decision dates (tonight / cooked-today / plan-tomorrow / variety & history
> windows) use `household.timezone`. Stored audit timestamps (`created_at`, `generated_at`) stay
> in UTC (store UTC, display local).

### Inventory (catalog of stocked foods)
A persistent **catalog** of foods the household stocks, each carrying a coarse stock **`status`:
`have` / `low` / `none`** (not numeric quantity). Stored in Postgres (`inventory_items`, created by
an Alembic migration). On **initial deployment only** (empty table) the catalog is seeded from
`data/inventory.seed.yaml` — every food at `status = none` — to save typing the whole list in;
after that the DB is the source of truth and the file isn't re-read. A **future input UI** is how
the user flips statuses (have/low/none). Items stay listed even when `none`, so gaps are
visible and restockable; a genuinely new food is a rare manual add.
Per item: `name`, `category`, `location` (fridge/shelf/freezer), `status`, `best_before?`
(display-only), and optional unused `quantity`/`unit` (kept nullable for reversibility).

> **Why status, not quantity:** the matcher and groceries key off item **name** presence, never
> quantity; the only quantity consumer was a soft LLM prompt hint. Tracking exact counts is effort
> nobody maintains, so v1 tracks a coarse status instead. **Status → behaviour:** `have` = on-hand,
> may be the main ingredient; `low` = usable but not the main ingredient, never auto-bought;
> `none` = not on-hand, added to the buy list if a chosen recipe needs it (staples exempt).
> `best_before` is recorded for the user to eyeball; nothing automated reads it.

### PostgreSQL (NAS)
- `recipes`: ingredients+quantities, equipment, method steps, tips, per-serving nutrition,
  texture/age suitability, hazard flags, tags, `approved` (cookbook / auto-suggest), `cooked`
  (has been eaten — drives history but not auto-suggested).
- `recipe_stickers`: post-cook handwritten notes pinned to a recipe (general), a section, or a
  Method step (web detail view only). A step pin references `recipe_steps.id` with
  `ON DELETE SET NULL`, so removing a step gracefully demotes its stickers to general.
- `dinner_history`: recipe + date served (drives both **variety** exclusion and the **history**
  view). Populated by "Cooked It".
- `menus`: generated menus (tonight + planned).
- `shopping_lists`: items (`name`, `quantity`, `unit`), linked to a menu. **No pricing/specials in
  v1** (`est_unit_cost`, `est_total_cost`, `store`, `on_special`, budget totals are future).
- ~~`supermarket_snapshots`~~: **future versions only** (no scraping in v1).

**Persistence rule:** human-maintained state → file; machine-generated/derived state → Postgres
(with disposable file exports for convenience).

### ER diagram (normalized schema)

Implemented as SQLAlchemy ORM in `persistence/orm.py`; created via Alembic migrations.
`supermarket_snapshots` is omitted (future versions).

```dbml
// Toddler Dinner Planner — normalized schema (persistence/orm.py).
// Paste into https://dbdiagram.io to render. supermarket_snapshots omitted (future versions).

Table recipes {
  id int [pk, increment]
  title varchar(200)
  min_age_months int
  texture varchar(120) [null]
  source varchar(20)
  approved boolean // in the cookbook / auto-suggestable
  cooked boolean   // has been finalised/eaten (drives history)
  created_at timestamptz
}

Table ingredients {
  id int [pk, increment]
  recipe_id int [ref: > recipes.id, not null]
  name varchar(120)
  quantity float
  unit varchar(40)
  position int
}

Table recipe_steps {
  id int [pk, increment]
  recipe_id int [ref: > recipes.id, not null]
  position int
  text text
}

Table recipe_equipment {
  id int [pk, increment]
  recipe_id int [ref: > recipes.id, not null]
  position int
  text text
}

Table recipe_tips {
  id int [pk, increment]
  recipe_id int [ref: > recipes.id, not null]
  position int
  text text
}

Table recipe_nutrition {
  recipe_id int [pk, ref: - recipes.id] // 1:1 with recipes
  energy_kcal float [null]
  protein_g float [null]
  fat_g float [null]
  carbs_g float [null]
  fibre_g float [null]
  iron_mg float [null]
  calcium_mg float [null]
  sodium_mg float [null]
}

Table recipe_food_groups {
  id int [pk, increment]
  recipe_id int [ref: > recipes.id, not null]
  food_group varchar(30)
  servings float
}

Table recipe_tags {
  id int [pk, increment]
  recipe_id int [ref: > recipes.id, not null]
  tag varchar(60)
}

Table recipe_hazards {
  id int [pk, increment]
  recipe_id int [ref: > recipes.id, not null]
  flag varchar(60)
}

Table recipe_stickers {
  id int [pk, increment]
  recipe_id int [ref: > recipes.id, not null] // ON DELETE CASCADE
  content text // handwritten post-cook note (<=280 chars)
  target_section varchar(30) [null] // ingredients|equipment|method|tips, else general
  target_step_id int [ref: > recipe_steps.id, null] // ON DELETE SET NULL -> demotes to general
  created_at timestamptz
  updated_at timestamptz
}

Table menus {
  id int [pk, increment]
  for_date date
  generated_at timestamptz
  notes text [null]
}

Table menu_items {
  id int [pk, increment]
  menu_id int [ref: > menus.id, not null]
  recipe_id int [ref: > recipes.id, not null]
  servings float
}

Table shopping_lists {
  id int [pk, increment]
  menu_id int [ref: > menus.id, null]
  budget float [null, note: 'future']
  estimated_total float [null, note: 'future']
  generated_at timestamptz
}

Table shopping_items {
  id int [pk, increment]
  shopping_list_id int [ref: > shopping_lists.id, not null]
  name varchar(120)
  quantity float
  unit varchar(40)
  est_unit_cost float [null, note: 'future']
  est_total_cost float [null, note: 'future']
  store varchar(60) [null, note: 'future']
  on_special boolean [note: 'future']
}

Table dinner_history {
  recipe_id int [pk, ref: > recipes.id, not null] // composite PK part; ON DELETE CASCADE
  served_on date [pk] // composite PK part (household timezone)
  title varchar(200)
}

Table inventory_items {
  id int [pk, increment]
  name varchar(120) [unique] // catalog key; matching is name-presence
  status varchar(10) // have | low | none
  quantity float [null, note: 'optional, unused by matching/groceries']
  unit varchar(40) [null, note: 'optional, unused']
  best_before date [null, note: 'display-only']
  category varchar(30) [null]
  opened boolean
  location varchar(20) // fridge | shelf | freezer
}
```

## 7. Interface Details

- **Core actions:** plain functions with typed (Pydantic) inputs/outputs.
- **CLI:** thin subcommand wrapper (`tonight`, `another-idea`, `plan-tomorrow`, `mark-served`,
  `db upgrade`, `login-copilot`, `serve`).
- **Web UI — card/button interface (primary):** a single local page of **recipe cards** with
  action buttons (`Tonight's Dinner`, `Another Idea`, `Plan Tomorrow`), each card carrying its
  own `Save to Cookbook` / `Cooked It`. A `Recently Cooked` row shows the last `history_days`
  cooked dinners as read-only cards, each with `Cooked It Today`. Fine-dining styling
  (Cormorant Garamond + Inter, self-hosted for offline), deterministic emoji hero images
  (derived from the recipe — **zero storage**). No accounts.
- **Collapsed chat ("more options"):** a minimized text box for exceptions/nuance
  ("avoid pasta", "use up the broccoli") routed through the hybrid **skill router**
  (fast-path keywords + LLM intent-parse). Buttons cover the common actions so routing is only
  a fallback.

### JSON API (consumed by the card UI)

| Endpoint | Purpose |
|----------|---------|
| `POST /api/tonight` | DB-first suggestion; generates a fresh idea if nothing matches |
| `POST /api/another-idea` `{mode, exclude}` | Another option in the current mode (tonight idea / tomorrow plan) |
| `POST /api/plan-tomorrow` | Tomorrow's menu + groceries + date |
| `POST /api/recipe/save` `{recipe}` | Approve → cookbook (auto-suggestable) |
| `POST /api/recipe/cooked` `{recipe, on?}` | Record as cooked + a history entry |
| `GET /api/history?days=N` | Recent cooked dinners (full recipes) |
| `POST /api/chat` `{message, recipe?, mode?}` | Free-text "note to the kitchen": navigate (like the buttons), **customize** (build/edit a guardrail-checked recipe for today/tomorrow), or ignore gibberish (no-op) |

Each card **embeds its own recipe**, so Save/Cooked buttons POST that recipe back — no
server-side session state, no disambiguation.

## 8. Tech Stack

- **Language:** Python.
- **Web:** FastAPI (card/button UI + JSON API); self-hosted fonts.
- **CLI:** Typer.
- **DB:** PostgreSQL via SQLAlchemy + psycopg; Alembic for migrations.
- **Models/validation:** Pydantic.
- **LLM:** provider-agnostic client behind `LLMProvider` (Copilot/OpenAI/Anthropic).
- **Browser:** Playwright — **future versions only** (supermarket integration).

## 9. Packaging & Deployment

- **Single app container** (plain Python base — no browser needed in v1).
- **Postgres external** on the NAS; connect via DSN in env/config.
- **docker-compose.yml** for one app service: env file, web port mapping, volume mount for
  config files (edit without rebuild).

### Database initialization

Schema is defined by **Alembic migrations** (`migrations/versions/`, version-controlled) — the
canonical, repeatable init script. A generated `db/schema.sql` (pure DDL, regenerated via
`alembic upgrade head --sql`) is also committed for direct `psql` use. To initialize any DB
(e.g. the NAS Postgres):

```bash
# Recommended — apply migrations:
TDP_POSTGRES_DSN=postgresql+psycopg://tdp:pass@nas.local:5432/toddler_dinner \
  toddler-dinner db upgrade
#   ...or in the container:  docker compose run --rm app toddler-dinner db upgrade

# Alternative — apply raw DDL directly (no Python on the target):
psql "postgresql://tdp:pass@nas.local:5432/toddler_dinner" -f db/schema.sql
```

The migration stamps `alembic_version`, so a `psql`-applied schema is still recognized by future
`alembic upgrade` runs. `migrations/` + `alembic.ini` + `db/` ship in the Docker image.

## 10. Roadmap / Deferred

- **Future — Supermarket integration (was v1 Flow 2 scraping):** live availability, specials, and
  pricing from New World / Woolworths / Pak'nSave, budget optimisation, and store selection.
  Deferred because Foodstuffs sites are behind Cloudflare anti-bot (headless browsers get 403 from
  datacenter IPs) and DOM scraping is high-maintenance. Likely approaches when revisited:
  Playwright with a **persistent, human-established browser profile** run from a residential IP
  (e.g. the NAS), reverse-engineered JSON APIs, a third-party NZ price aggregator, or graceful
  degradation to manual/seasonal data. The `SupermarketProvider` seam and
  `supermarket_snapshots` / shopping-list pricing fields are reserved for this.
- **v2:** photo-based fridge inventory (`InventoryProvider` swap).
- **v2:** NAS Ollama as `LLMProvider`.
- **Later:** growth-curve monitoring module (separate concern; choose reference curve then).
- **Later:** richer web UI, additional meals.

## 11. Open Items (fill in during setup)

- Specific allergies / dietary rules (start empty in config).
- Chosen hosted LLM vendor/model (interface makes it swappable).
