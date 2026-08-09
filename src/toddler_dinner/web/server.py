"""Chat web UI: a thin single-page wrapper over the skill router + core actions."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from toddler_dinner.app import build_planner
from toddler_dinner.core import Planner
from toddler_dinner.models import Recipe
from toddler_dinner.routing import Action, route

app = FastAPI(title="Toddler Dinner Planner")

_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@lru_cache(maxsize=1)
def get_planner() -> Planner:
    """Build the Planner once (reusing one DB engine/pool) and reuse it across requests."""
    return build_planner()


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


def _note_from_params(params: dict) -> str | None:
    """Human-readable 'why' note for the card (e.g. what we're avoiding)."""
    if params.get("exclude"):
        return "Avoiding " + ", ".join(params["exclude"])
    return None


# --- Structured JSON API (for the card/button UI) ---------------------------

class RecipeBody(BaseModel):
    recipe: Recipe


class CookBody(BaseModel):
    recipe: Recipe
    on: date | None = None


class AnotherBody(BaseModel):
    mode: str = "tonight"   # 'tonight' | 'plan'
    exclude: list[str] | None = None


def _plan_payload(plan) -> dict:
    return {
        "recipe": plan.menu.items[0].recipe,
        "groceries": plan.groceries.items,
        "already_have": plan.already_have,
        "for_date": plan.menu.for_date,
        "source": "plan",
    }


@app.post("/api/tonight")
def api_tonight(planner: Planner = Depends(get_planner)) -> dict:
    """DB-first suggestion; falls back to a fresh generated idea if nothing matches."""
    try:
        r = planner.tonight()
        if r.recipe:
            return {"recipe": r.recipe, "source": "cookbook", "kind": r.kind, "missing": r.missing}
        recipe = planner.another_idea()
        return {"recipe": recipe, "source": "fresh", "kind": "none", "missing": []}
    except Exception as e:  # noqa: BLE001 - return a friendly error, never a 500
        return {"error": str(e)}


@app.post("/api/another-idea")
def api_another(body: AnotherBody, planner: Planner = Depends(get_planner)) -> dict:
    """Another option within the current mode (tonight idea, or another tomorrow plan)."""
    try:
        if body.mode == "plan":
            return _plan_payload(planner.plan_tomorrow(use_llm=True))
        return {"recipe": planner.another_idea(exclude=body.exclude), "source": "fresh"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@app.post("/api/plan-tomorrow")
def api_plan(planner: Planner = Depends(get_planner)) -> dict:
    try:
        return _plan_payload(planner.plan_tomorrow(use_llm=True))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@app.post("/api/recipe/save")
def api_save(body: RecipeBody, planner: Planner = Depends(get_planner)) -> dict:
    """Add the card's recipe to the cookbook (approved -> auto-suggestable)."""
    try:
        saved = planner.approve(body.recipe)
        return {"ok": True, "id": saved.id, "title": saved.title}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@app.post("/api/recipe/cooked")
def api_cooked(body: CookBody, planner: Planner = Depends(get_planner)) -> dict:
    """Record the card's recipe as cooked today (stores recipe + a history entry)."""
    try:
        stored = planner.cook(body.recipe, on=body.on)
        return {"ok": True, "title": stored.title}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@app.get("/api/history")
def api_history(days: int | None = None, planner: Planner = Depends(get_planner)) -> dict:
    """Recent cooked dinners (full recipes) for the history view."""
    try:
        return {"entries": planner.recent_cooked(days)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@app.post("/api/chat")
def api_chat(req: ChatRequest, planner: Planner = Depends(get_planner)) -> dict:
    """Free-text 'exceptions' box: route the message, then return a **card payload** (not text),
    so the UI renders it like a button result. Honours extracted params (e.g. `exclude`).
    """
    decision = route(req.message.strip(), llm=planner.llm)
    if decision.action is None:
        return {"message": "Sorry, I didn't catch that — try “avoid broccoli”, "
                           "“make it dairy-free”, or “plan tomorrow”."}
    params = decision.params or {}
    exclude = params.get("exclude")
    note = _note_from_params(params)
    try:
        if decision.action == Action.PLAN_TOMORROW:
            payload = _plan_payload(planner.plan_tomorrow(use_llm=params.get("fresh", True)))
            if note:
                payload["note"] = note
            return payload
        if decision.action == Action.TONIGHT and not exclude:
            r = planner.tonight()
            if r.recipe:
                return {"recipe": r.recipe, "source": "cookbook", "kind": r.kind,
                        "missing": r.missing}
            return {"recipe": planner.another_idea(), "source": "fresh"}
        # another_idea, or a tonight request that carries an exclusion -> generate
        return {"recipe": planner.another_idea(exclude=exclude), "source": "fresh", "note": note}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
