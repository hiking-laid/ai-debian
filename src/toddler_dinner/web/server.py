"""Chat web UI: a thin single-page wrapper over the skill router + core actions."""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from toddler_dinner.app import build_planner
from toddler_dinner.core import Planner
from toddler_dinner.models import STICKER_SECTIONS, Recipe
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
    recipe: Recipe | None = None   # the card currently on screen (for edits / no-op keep)
    mode: str | None = None        # 'tonight' | 'plan' — which card the user is looking at


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    """Serve the SVG favicon for browsers that probe the site root for /favicon.ico."""
    return FileResponse(_STATIC / "favicon.svg", media_type="image/svg+xml")


def _note_from_params(params: dict) -> str | None:
    """Human-readable 'why' note for the card (e.g. what we're including/avoiding)."""
    bits = []
    if params.get("include"):
        bits.append("Including " + ", ".join(params["include"]))
    if params.get("exclude"):
        bits.append("Avoiding " + ", ".join(params["exclude"]))
    return " · ".join(bits) if bits else None


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


# --- Stickers (post-cook handwritten notes) ---------------------------------

_STICKER_MAX = 280


class StickerCreate(BaseModel):
    content: str
    target_section: str | None = None
    target_step_index: int | None = None


class StickerPatch(BaseModel):
    content: str | None = None
    set_target: bool = False           # when true, (re)assign the pin target below
    target_section: str | None = None
    target_step_index: int | None = None


def _clean_target(section: str | None, step_index: int | None) -> tuple[str | None, int | None]:
    """Normalise a pin target: a step wins over a section; unknown section -> general."""
    if step_index is not None:
        return None, step_index
    if section in STICKER_SECTIONS:
        return section, None
    return None, None


@app.get("/api/recipe/{recipe_id}/stickers")
def api_stickers_list(recipe_id: int, planner: Planner = Depends(get_planner)) -> dict:
    try:
        return {"stickers": planner.stickers.list_for_recipe(recipe_id)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@app.post("/api/recipe/{recipe_id}/stickers")
def api_stickers_create(
    recipe_id: int, body: StickerCreate, planner: Planner = Depends(get_planner)
) -> dict:
    try:
        content = body.content.strip()[:_STICKER_MAX]
        if not content:
            return {"error": "empty sticker"}
        section, step_index = _clean_target(body.target_section, body.target_step_index)
        sticker = planner.stickers.create(recipe_id, content, section, step_index)
        return {"sticker": sticker}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@app.patch("/api/stickers/{sticker_id}")
def api_stickers_update(
    sticker_id: int, body: StickerPatch, planner: Planner = Depends(get_planner)
) -> dict:
    try:
        content = None
        if body.content is not None:
            content = body.content.strip()[:_STICKER_MAX]
            if not content:
                return {"error": "empty sticker"}
        section, step_index = (None, None)
        if body.set_target:
            section, step_index = _clean_target(body.target_section, body.target_step_index)
        sticker = planner.stickers.update(
            sticker_id,
            content=content,
            set_target=body.set_target,
            target_section=section,
            target_step_index=step_index,
        )
        if sticker is None:
            return {"error": "sticker not found"}
        return {"sticker": sticker}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@app.delete("/api/stickers/{sticker_id}")
def api_stickers_delete(sticker_id: int, planner: Planner = Depends(get_planner)) -> dict:
    try:
        return {"ok": planner.stickers.delete(sticker_id)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


@app.post("/api/chat")
def api_chat(req: ChatRequest, planner: Planner = Depends(get_planner)) -> dict:
    """Free-text 'note to the kitchen'. Three outcomes:
    - navigate: same as the buttons (tonight / plan / another) — returns a card payload;
    - customize: build a recipe from the parent's request (optionally editing the current card),
      guardrail-check it, and return it on today's or tomorrow's card;
    - ignore: gibberish / not-about-dinner — no-op that keeps the current card.
    """
    decision = route(req.message.strip(), llm=planner.llm)
    params = decision.params or {}
    exclude = params.get("exclude")
    note = _note_from_params(params)

    def _source_for(mode: str) -> str:
        return "plan" if mode == "plan" else "fresh"

    def _out_mode() -> str:
        target = params.get("target")
        if target == "tomorrow":
            return "plan"
        if target == "today":
            return "tonight"
        return req.mode or "tonight"

    # --- ignore / unrecognised: no-op, keep the card on screen (a chef ignores nonsense) ---
    if decision.action is None:
        if req.recipe is not None:
            return {"recipe": req.recipe, "source": _source_for(req.mode or "tonight"),
                    "message": "Left your current dinner unchanged."}
        return {"message": "Sorry, I didn't catch that — try “add broccoli”, “make it "
                           "dairy-free”, or “plan tomorrow”."}

    try:
        if decision.action == Action.CUSTOMIZE:
            mode = _out_mode()
            try:
                recipe = planner.customize(
                    instructions=req.message,
                    base=req.recipe,
                    include=params.get("include"),
                    exclude=exclude,
                    on=(planner.today() + timedelta(days=1)) if mode == "plan" else None,
                )
            except ValueError as e:  # guardrail rejection -> keep the current card
                resp: dict = {"message": f"I couldn't do that safely: {e}"}
                if req.recipe is not None:
                    resp["recipe"] = req.recipe
                    resp["source"] = _source_for(mode)
                return resp
            if mode == "plan":
                payload = _plan_payload(planner.plan_for_recipe(recipe))
                if note:
                    payload["note"] = note
                return payload
            return {"recipe": recipe, "source": "fresh", "note": note}

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
