"""Skill router tests."""

from __future__ import annotations

import json

from toddler_dinner.routing import Action, route


class FakeLLM:
    """Returns a canned JSON classification; records the prompt it saw."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.seen_system: str | None = None
        self.seen_user: str | None = None

    def complete(self, system: str, user: str) -> str:
        self.seen_system, self.seen_user = system, user
        return json.dumps(self._payload)

    def generate_recipe(self, prompt): ...  # unused


# --- fast path --------------------------------------------------------------

def test_fast_path_matches_without_llm():
    assert route("what's for dinner tonight?").action == Action.TONIGHT
    assert route("plan tomorrow please").action == Action.PLAN_TOMORROW
    assert route("he's bored, something else").action == Action.ANOTHER_IDEA


def test_fast_path_is_free_no_llm_call():
    llm = FakeLLM({"action": "tonight"})
    result = route("what's for dinner tonight?", llm=llm)
    assert result.via == "fast_path"
    assert llm.seen_user is None  # LLM never consulted


def test_refresh_availability_is_gone():
    # descoped action must not exist in the vocabulary
    assert not hasattr(Action, "REFRESH_AVAILABILITY")
    assert "refresh_availability" not in {a.value for a in Action}


# --- llm fallback + few-shot + params ---------------------------------------

def test_llm_fallback_extracts_params():
    llm = FakeLLM({"action": "another_idea", "params": {"exclude": ["pasta"]}})
    result = route("she's completely sick of the usual noodles", llm=llm)
    assert result.action == Action.ANOTHER_IDEA
    assert result.via == "llm"
    assert result.params == {"exclude": ["pasta"]}
    # few-shot examples are present in the prompt
    assert "Request:" in llm.seen_user and "JSON:" in llm.seen_user


def test_llm_reply_tolerates_fences_and_prose():
    class FencedLLM(FakeLLM):
        def complete(self, system, user):
            return 'Sure!\n```json\n{"action": "plan_tomorrow", "params": {"fresh": true}}\n```'

    result = route("organise a brand new dinner for the weekend", llm=FencedLLM({}))
    assert result.action == Action.PLAN_TOMORROW
    assert result.params == {"fresh": True}


def test_unknown_action_from_llm_is_unmatched():
    llm = FakeLLM({"action": "make_coffee"})
    result = route("brew me an espresso", llm=llm)
    assert result.action is None
    assert result.via == "unmatched"


# --- issue #2: customize classification + gibberish -------------------------

def test_llm_classifies_customize_with_include():
    llm = FakeLLM({"action": "customize",
                   "params": {"include": ["broccoli"], "target": "today"}})
    result = route("add some broccoli to tonight's dinner", llm=llm)
    assert result.action == Action.CUSTOMIZE
    assert result.params == {"include": ["broccoli"], "target": "today"}
    assert result.via == "llm"


def test_edit_signal_suppresses_navigation_fast_path():
    # "tonight" alone -> fast path; with an edit signal it must defer to the LLM/customize.
    assert route("what's for dinner tonight?").via == "fast_path"
    llm = FakeLLM({"action": "customize", "params": {"exclude": ["cheese"], "target": "today"}})
    assert route("make tonight's dinner dairy-free", llm=llm).action == Action.CUSTOMIZE


def test_llm_null_action_is_unmatched():
    llm = FakeLLM({"action": None, "params": {}})
    result = route("asdfghjkl", llm=llm)
    assert result.action is None
    assert result.via == "unmatched"


def test_no_match_no_llm_is_unmatched():
    result = route("tell me a joke")
    assert result.action is None
    assert result.via == "unmatched"
