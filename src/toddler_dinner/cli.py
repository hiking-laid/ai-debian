"""CLI: thin subcommand wrapper over the core actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import typer

from toddler_dinner.app import build_planner
from toddler_dinner.core import Planner
from toddler_dinner.export import recipe_text

app = typer.Typer(help="Toddler Dinner Planner")


@dataclass
class State:
    config: str = "config/profile.yaml"


@app.callback()
def main(
    ctx: typer.Context,
    config: str = typer.Option("config/profile.yaml", help="Profile YAML path."),
) -> None:
    """Toddler Dinner Planner — global options apply to all commands."""
    ctx.obj = State(config=config)


def _planner(ctx: typer.Context) -> Planner:
    """Build the planner with friendly errors instead of raw tracebacks."""
    state: State = ctx.obj
    try:
        return build_planner(state.config)
    except FileNotFoundError as e:
        typer.secho(
            f"Config not found ({e}). Copy the example:\n"
            "  cp config/profile.example.yaml config/profile.yaml",
            fg="red", err=True,
        )
        raise typer.Exit(1)
    except Exception as e:  # noqa: BLE001 - surface DB/LLM wiring failures cleanly
        typer.secho(f"Startup failed: {e}", fg="red", err=True)
        raise typer.Exit(1)


def _suggest_fresh(planner: Planner) -> None:
    """Generate an LLM recipe, show it in full, and offer to save (human-approval gate)."""
    try:
        recipe = planner.another_idea()
    except (RuntimeError, ValueError) as e:
        typer.secho(f"Couldn't generate a recipe: {e}", fg="red", err=True)
        raise typer.Exit(1)
    typer.echo(recipe_text(recipe))
    if typer.confirm("\nApprove and save to the recipe database?"):
        planner.persist_approved(recipe)
        typer.echo("Saved.")


@app.command()
def tonight(
    ctx: typer.Context,
    fresh: bool = typer.Option(False, "--fresh", help="Force a fresh LLM idea even if the DB matches."),
) -> None:
    """Suggest tonight's dinner from the fridge (generates a fresh idea if nothing matches)."""
    planner = _planner(ctx)
    if not fresh:
        result = planner.tonight()
        if result.kind == "exact" and result.recipe:
            typer.echo(recipe_text(result.recipe))
            return
        if result.kind == "partial" and result.recipe:
            typer.echo(recipe_text(result.recipe))
            typer.echo(f"\n(You're missing: {', '.join(result.missing)})")
            return
        typer.echo("Your cookbook has no match yet — here's a fresh idea:\n")
    _suggest_fresh(planner)


@app.command("another-idea")
def another_idea(ctx: typer.Context) -> None:
    """Generate a fresh validated recipe from what's on hand."""
    _suggest_fresh(_planner(ctx))


@app.command("plan-tomorrow")
def plan_tomorrow(
    ctx: typer.Context,
    fresh: bool = typer.Option(False, "--fresh", help="Allow an LLM recipe if the DB has nothing suitable."),
    export_dir: str = typer.Option("data/exports", help="Where to write the groceries export."),
) -> None:
    """Plan tomorrow's dinner and export a groceries list (Flow 2)."""
    from toddler_dinner.export import groceries_markdown

    planner = _planner(ctx)
    try:
        plan = planner.plan_tomorrow(use_llm=fresh)
    except ValueError as e:
        typer.secho(f"{e}", fg="red", err=True)
        raise typer.Exit(1)
    recipe = plan.menu.items[0].recipe
    typer.echo(f"Dinner for {plan.menu.for_date}: {recipe.title}")
    if plan.groceries.items:
        typer.echo("Groceries to buy:")
        for g in plan.groceries.items:
            typer.echo(f"  - {g.name} ({g.quantity:g} {g.unit})")
    else:
        typer.echo("Groceries: nothing needed — all in the fridge.")

    out = Path(export_dir) / f"groceries-{plan.menu.for_date}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(groceries_markdown(plan))
    typer.echo(f"Exported: {out}")


@app.command("mark-served")
def mark_served(
    ctx: typer.Context,
    title: str = typer.Argument(..., help="The dinner that was served (drives variety)."),
    on: str = typer.Option(None, "--date", help="ISO date served; default today."),
) -> None:
    """Record a dinner as served so it's avoided within the variety window."""
    served_on = date.fromisoformat(on) if on else date.today()
    planner = _planner(ctx)
    planner.record_served_title(title, served_on)
    typer.echo(f"Recorded '{title}' as served on {served_on}.")


@app.command("login-copilot")
def login_copilot() -> None:
    """Authorize GitHub Copilot via device flow (opens a code to enter in the browser)."""
    from toddler_dinner.providers.llm.github_auth import (
        DEFAULT_TOKEN_PATH,
        DeviceCode,
        device_login,
        save_oauth_token,
    )

    def prompt(device: DeviceCode) -> None:
        typer.echo(f"\n  1. Open: {device.verification_uri}")
        typer.echo(f"  2. Enter code: {device.user_code}\n")
        typer.echo("Waiting for authorization...")

    token = device_login(on_prompt=prompt)
    save_oauth_token(token)
    typer.echo(f"Authorized. OAuth token saved to {DEFAULT_TOKEN_PATH} (0600).")


db_app = typer.Typer(help="Database management (Alembic migrations).")
app.add_typer(db_app, name="db")


@db_app.command("upgrade")
def db_upgrade(revision: str = "head") -> None:
    """Apply database migrations up to the given revision (default: head)."""
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), revision)
    typer.echo(f"Database upgraded to {revision}.")


inv_app = typer.Typer(help="Inventory catalog (Postgres).")
app.add_typer(inv_app, name="inventory")


@inv_app.command("seed")
def inventory_seed(
    path: str = typer.Option("data/inventory.seed.yaml", help="Seed YAML path."),
    force: bool = typer.Option(False, "--force", help="Seed even if the catalog is non-empty."),
) -> None:
    """Load the inventory seed into the catalog — initial deployment only (skips if non-empty)."""
    from toddler_dinner.app import seed_inventory_if_empty

    try:
        n = seed_inventory_if_empty(path, force=force)
        typer.echo(f"Seeded {n} inventory items." if n else "Catalog already populated; skipped.")
    except Exception as e:  # noqa: BLE001 - surface DB wiring failures cleanly
        typer.secho(f"Seed failed: {e}", fg="red", err=True)
        raise typer.Exit(1)


@app.command()
def serve(port: int = 8080) -> None:
    """Run the chat web UI."""
    import uvicorn

    uvicorn.run("toddler_dinner.web.server:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    app()
