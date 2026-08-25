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

docker compose up --build     # migrations run automatically, then the app serves
```

The app is at `http://localhost:${TDP_WEB_PORT:-8080}`. `config/` and `data/` are volume-mounted,
so edit them on the host without rebuilding. Postgres is external (e.g. your NAS) via
`TDP_POSTGRES_DSN`.

> **LLM credential (one-time).** The app **serves, migrates, and shows history** without an LLM,
> but recipe *generation* (tonight / another idea / plan) needs a provider. Pick one:
>
> - **GitHub Copilot** — authorize once via device flow; the `copilot-auth` volume starts empty,
>   so run it in the container to write the token there:
>   `docker compose run --rm app toddler-dinner login-copilot`
> - **OpenAI / Anthropic** — set `TDP_LLM_PROVIDER=openai` (or `anthropic`) and `TDP_LLM_API_KEY`
>   in `.env`. No extra step.

## Local development

```bash
# 1. Install (Python 3.11+)
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure
cp config/profile.example.yaml config/profile.yaml
cp .env.example .env

# 3. Create/upgrade database tables (Alembic)
toddler-dinner db upgrade

# 4. Seed the inventory catalog (initial deployment only; loads data/inventory.seed.yaml as 'none')
toddler-dinner inventory seed

# 5. (Copilot only) authorize once via device flow
toddler-dinner login-copilot

# 6. Use
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

## Deploy to the NAS (prebuilt image — no source needed)

Code is baked into a published image; `config/`, `data/`, and `.env` stay on the NAS as volumes.

1. **CI publishes the image.** Pushing to `main` (or a `v*` tag) runs
   `.github/workflows/publish.yml`, which builds a multi-arch image (incl. `linux/arm64`) and
   pushes it to `ghcr.io/aiden-liu/toddler_dinner_planner`. One-time setup: add a repo secret
   `GHCR_PAT` (a `write:packages` PAT from the **aiden-liu** account — a different owner than
   this repo, so the default `GITHUB_TOKEN` can't push there).
2. **On the NAS**, keep `docker-compose.prod.yml`, `.env`, `config/`, and `data/` in place, then:
   ```bash
   docker login ghcr.io -u aiden-liu        # once, only if the package is private
   docker compose -f docker-compose.prod.yml pull
   docker compose -f docker-compose.prod.yml up -d   # entrypoint auto-applies DB migrations
   ```

No more zip/unzip/replace — updates are `pull` + `up -d`.


## Status

**Implemented:** a card/button web UI over the whole flow — tonight's dinner (DB-first, with
cold-start generation), another idea (variety-steered), plan tomorrow (+ groceries), plus
**Save to Cookbook** and **Cooked It** with a **Recently Cooked** history. Backed by:
weight+age nutrition scaling & safety validation, multi-provider LLM (Copilot device-flow /
OpenAI / Anthropic), a normalized PostgreSQL layer (SQLAlchemy + Alembic), history-backed
variety, and profile-timezone-aware dates.

**TODO:** **Live supermarket integration** and **bilingual
UI** are deferred to future versions (DESIGN.md §10).
