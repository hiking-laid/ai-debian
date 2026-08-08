# Toddler Dinner Planner

A personal tool that plans age-appropriate **dinners** for a toddler based on what's in the
fridge, and produces a **groceries list** for the next dinner (menu ingredients minus what you
already have). Live supermarket pricing/availability is a future version.

See [DESIGN.md](DESIGN.md) for the full design and rationale.

## Quick start (container — recommended)

The container **auto-applies database migrations on startup** (via the entrypoint), so there's
nothing to run inside it.

```bash
cp .env.example .env                                  # set Postgres DSN + LLM provider
cp config/profile.example.yaml config/profile.yaml   # edit child/household/exclusions
cp data/inventory.example.yaml data/inventory.yaml    # edit fridge contents

docker compose up --build     # migrations run automatically, then the app serves
```

The app is at `http://localhost:${TDP_WEB_PORT:-8080}`. `config/` and `data/` are volume-mounted,
so edit them on the host without rebuilding. Postgres is external (e.g. your NAS) via
`TDP_POSTGRES_DSN`.

> **GitHub Copilot only:** authorize once via device flow. Run it in the container so the token
> is written to the mounted home volume:
> `docker compose run --rm app toddler-dinner login-copilot`

## Local development

```bash
# 1. Install (Python 3.11+)
pip install -e ".[dev]"

# 2. Configure
cp config/profile.example.yaml config/profile.yaml
cp data/inventory.example.yaml data/inventory.yaml
cp .env.example .env

# 3. Create/upgrade database tables (Alembic)
toddler-dinner db upgrade

# 4. (Copilot only) authorize once via device flow
toddler-dinner login-copilot

# 5. Use
toddler-dinner tonight            # Flow 1: suggest tonight's dinner from the fridge
toddler-dinner another-idea       # generate a fresh validated recipe from what's on hand
toddler-dinner plan-tomorrow      # Flow 2: dinner + groceries list (exports Markdown)
toddler-dinner serve              # chat web UI at http://localhost:8080

# Tests
pytest
```

## Container

```bash
docker compose up --build   # migrations auto-run on startup; app on TDP_WEB_PORT (default 8080)
```

## Status

**Implemented:** a card/button web UI over the whole flow — tonight's dinner (DB-first, with
cold-start generation), another idea (variety-steered), plan tomorrow (+ groceries), plus
**Save to Cookbook** and **Cooked It** with a **Recently Cooked** history. Backed by:
weight+age nutrition scaling & safety validation, multi-provider LLM (Copilot device-flow /
OpenAI / Anthropic), a normalized PostgreSQL layer (SQLAlchemy + Alembic), history-backed
variety, and profile-timezone-aware dates.

**TODO:** encode real NZ MoH / NHMRC + WHO figures in `nutrition/reference.py` (currently
sensible placeholders — see `TODO.md` 🔴). **Live supermarket integration** and **bilingual
UI** are deferred to future versions (DESIGN.md §10).
