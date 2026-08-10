"""Hybrid skill routing: fast-path keywords (free/instant) + few-shot LLM fallback.

Maps a free-form request to a core Action (and, via the LLM, extracts simple parameters).
Common phrasings hit the keyword fast path; unusual phrasing falls back to the LLM.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum

from toddler_dinner.interfaces import LLMProvider


class Action(str, Enum):
    """The router's vocabulary. Callers match on these (typed contract)."""

    TONIGHT = "tonight"
    PLAN_TOMORROW = "plan_tomorrow"
    ANOTHER_IDEA = "another_idea"
    CUSTOMIZE = "customize"


# Fast-path keyword hints per action (substring match; first hit wins — fine for v1).
_FAST_PATH: dict[Action, tuple[str, ...]] = {
    Action.TONIGHT: ("tonight", "dinner now", "what's for dinner", "whats for dinner"),
    Action.PLAN_TOMORROW: ("tomorrow", "plan", "next day"),
    Action.ANOTHER_IDEA: ("another", "something else", "bored", "different", "new idea"),
}

# Edit signals: when present, the message is a recipe change (customize), so we skip the
# navigation fast path even if it also mentions "tonight"/"tomorrow" and let the LLM classify
# (e.g. "add broccoli to tonight's dinner" must edit the card, not just re-suggest tonight).
_CUSTOMIZE_HINTS: tuple[str, ...] = (
    "add ", "include", "swap", "replace", "instead", "without", "remove", "extra ",
    "more ", "less ", "make it", "dairy-free", "dairy free", "gluten-free", "gluten free",
    "use my", "here's my", "here is my",
)

# Few-shot examples steer the LLM classifier and show the params it may extract.
_FEWSHOT: list[tuple[str, dict]] = [
    ("what's for dinner tonight?", {"action": "tonight", "params": {}}),
    ("what can I cook right now with what's in the fridge",
     {"action": "tonight", "params": {}}),
    ("she won't eat pasta again, give me a different idea",
     {"action": "another_idea", "params": {"exclude": ["pasta"]}}),
    ("plan tomorrow's dinner and a shopping list",
     {"action": "plan_tomorrow", "params": {}}),
    ("plan a fresh new dinner for tomorrow",
     {"action": "plan_tomorrow", "params": {"fresh": True}}),
    ("add some broccoli to tonight's dinner",
     {"action": "customize", "params": {"include": ["broccoli"], "target": "today"}}),
    ("make tonight's recipe dairy-free",
     {"action": "customize", "params": {"exclude": ["milk", "cheese", "butter", "yoghurt"],
                                        "target": "today"}}),
    ("swap the chicken for tofu and add spinach",
     {"action": "customize", "params": {"include": ["tofu", "spinach"], "exclude": ["chicken"]}}),
    ("here is my recipe: chicken and kumara mash, use it for tomorrow",
     {"action": "customize", "params": {"target": "tomorrow"}}),
    ("asdfghjkl", {"action": None, "params": {}}),
    ("tell me a joke", {"action": None, "params": {}}),
]

_SYSTEM = (
    "You are an intent router for a toddler-dinner app. Classify the request into exactly one "
    f"action from: {', '.join(a.value for a in Action)}. Use `customize` when the parent wants a "
    "specific recipe change or a supplied recipe (include/avoid an ingredient, swap something, "
    "change the style, make it dairy-free, or paste their own recipe). Optionally extract params: "
    "`include` (list of foods that must appear), `exclude` (list of foods to avoid), "
    "`target` ('today' or 'tomorrow'), `fresh` (bool, wants a brand-new idea), `date` (ISO date). "
    "If the text is gibberish or not about dinner, reply with action null. "
    'Reply with ONLY a JSON object: {"action": <action|null>, "params": {...}}.'
)


@dataclass
class RouteResult:
    action: Action | None
    via: str  # "fast_path" | "llm" | "unmatched"
    params: dict = field(default_factory=dict)


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _extract_json(raw: str) -> dict | None:
    text = _FENCE_RE.sub("", raw).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _llm_route(text: str, llm: LLMProvider) -> RouteResult | None:
    examples = "\n".join(f"Request: {t}\nJSON: {json.dumps(r)}" for t, r in _FEWSHOT)
    prompt = f"{examples}\n\nRequest: {text}\nJSON:"
    data = _extract_json(llm.complete(system=_SYSTEM, user=prompt))
    if not data:
        return None
    action = data.get("action")
    if action in Action._value2member_map_:
        params = data.get("params") or {}
        return RouteResult(action=Action(action), via="llm", params=params)
    return None


def route(text: str, llm: LLMProvider | None = None) -> RouteResult:
    low = text.lower()
    # Recipe-edit requests skip the navigation fast path (they need the LLM to build a recipe).
    if not any(h in low for h in _CUSTOMIZE_HINTS):
        for action, hints in _FAST_PATH.items():
            if any(h in low for h in hints):
                return RouteResult(action=action, via="fast_path")

    if llm is not None:
        result = _llm_route(text, llm)
        if result is not None:
            return result

    return RouteResult(action=None, via="unmatched")
