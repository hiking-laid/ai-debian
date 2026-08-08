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
from toddler_dinner.export import recipe_text
from toddler_dinner.models import Recipe
from toddler_dinner.routing import Action, route

app = FastAPI(title="Toddler Dinner Planner")

_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@lru_cache(maxsize=1)
def get_planner() -> Planner:
    """Build the Planner once (reusing one DB engine/pool) and reuse it across requests."""
    return build_planner()


# Last generated-but-unsaved suggestion (single-user tool). Lets the chat approve-and-save,
# giving web parity with the CLI's confirm prompt without auto-approving.
_pending: dict[str, Recipe] = {}
_SAVE_TRIGGERS = {"save", "save it", "yes", "yes please", "approve", "keep", "keep it"}


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    action: str | None = None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


def _suggest_and_stash(planner: Planner, exclude: list[str] | None = None) -> str:
    recipe = planner.another_idea(exclude=exclude)
    _pending["last"] = recipe
    return recipe_text(recipe) + "\n\nReply 'save' to add it to your cookbook."


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, planner: Planner = Depends(get_planner)) -> ChatResponse:
    msg = req.message.strip()

    # 1. Approve + save a pending suggestion if the user confirms.
    if _pending.get("last") and msg.lower() in _SAVE_TRIGGERS:
        recipe = _pending.pop("last")
        planner.persist_approved(recipe)
        return ChatResponse(reply=f"Saved '{recipe.title}' to your cookbook.")

    decision = route(msg, llm=planner.llm)
    try:
        if decision.action == Action.TONIGHT:
            r = planner.tonight()
            if r.recipe:
                detail = recipe_text(r.recipe)
                if r.kind == "partial" and r.missing:
                    detail += f"\n\n(You're missing: {', '.join(r.missing)})"
                return ChatResponse(reply=detail, action=Action.TONIGHT.value)
            # Cold start / no DB match: generate an idea straight from the fridge.
            reply = _suggest_and_stash(planner)
            return ChatResponse(
                reply="Your cookbook has no match yet — here's a fresh idea:\n\n" + reply,
                action=Action.TONIGHT.value,
            )
        if decision.action == Action.ANOTHER_IDEA:
            reply = _suggest_and_stash(planner, exclude=decision.params.get("exclude"))
            return ChatResponse(reply=reply, action=Action.ANOTHER_IDEA.value)
        if decision.action == Action.PLAN_TOMORROW:
            plan = planner.plan_tomorrow(use_llm=decision.params.get("fresh", True))
            recipe = plan.menu.items[0].recipe
            goods = ", ".join(f"{g.name} ({g.quantity:g}{g.unit})" for g in plan.groceries.items)
            reply = (
                f"Dinner for {plan.menu.for_date}:\n\n"
                + recipe_text(recipe)
                + f"\n\nGroceries to buy: {goods or 'nothing, all in the fridge'}"
            )
            return ChatResponse(reply=reply, action=Action.PLAN_TOMORROW.value)
    except Exception as e:  # noqa: BLE001 - never surface a 500 to the chat box
        action = decision.action.value if decision.action else None
        return ChatResponse(reply=f"Sorry, that didn't work: {e}", action=action)

    return ChatResponse(reply="Sorry, I didn't understand that.", action=None)


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
