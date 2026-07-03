"""Router and node functions for the Pathfinder graph.

Every node returns a partial state update that ALWAYS includes ``response``
(an ``AgentResponse.model_dump()``) except the two "pass-through" cases where a
node finishes intake/confirmation and hands off to the next node in the SAME
turn (``intake_node`` -> ``reflect_node``, ``confirm_node`` -> ``plan_node``).

The graph is entered fresh on every user turn with checkpointed state, so the
router reads the current flags + latest human message to decide where to go.
"""

from __future__ import annotations

from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .llm import get_llm
from .prompts import (
    EARLY_PLAN,
    EXTRACTION,
    GAPFILL,
    PERSONA,
    PLAN,
    REFINE,
    REFLECT,
)
from .state import (
    KEY_AREAS,
    PROFILE_AREAS,
    AgentResponse,
    Form,
    FormField,
    ProfileExtraction,
)

llm = get_llm()

# Phrases that mean "just give me the plan already".
_PLAN_KEYWORDS = [
    "just give me the plan",
    "give me the plan",
    "the plan now",
    "skip to the plan",
    "just the plan",
    "show me the plan",
]


# ---------------------------------------------------------------------------
# Narrow structured-output models (envelope generation)
# ---------------------------------------------------------------------------
class ConvReply(BaseModel):
    """A conversational envelope the LLM fills (no form / no plan)."""

    message: str
    quick_replies: list[str] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)


class PlanReply(BaseModel):
    """A plan-delivering envelope."""

    message: str
    plan_markdown: str
    suggested_questions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _last_human_text(messages) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return str(m.content)
    return ""


def _profile_context(profile: dict) -> str:
    known = {k: v for k, v in profile.items() if v}
    return f"Profile known so far (fill the gaps, don't re-ask): {known or '{}'}"


def _merge_profile(profile: dict, extraction: ProfileExtraction) -> dict:
    """Merge newly captured, non-null fields into the running profile."""
    updated = dict(profile)
    for area in PROFILE_AREAS:
        value = getattr(extraction, area, None)
        if value:
            updated[area] = value
    return updated


def _safe_extract(profile: dict, messages) -> dict:
    """Run structured extraction, retry once, else keep existing profile."""
    extractor = llm.with_structured_output(ProfileExtraction)
    sys = SystemMessage(content=PERSONA + "\n\n" + EXTRACTION + "\n\n" + _profile_context(profile))
    for _ in range(2):
        try:
            result = extractor.invoke([sys] + list(messages))
            return _merge_profile(profile, result)
        except Exception:  # noqa: BLE001 — malformed output: retry, then give up
            continue
    return profile


def _intake_ready(profile: dict) -> bool:
    """True once the high-value areas (strengths, values, goals) are covered."""
    return all(profile.get(area) for area in KEY_AREAS)


def _emit(resp: AgentResponse, **flags) -> dict:
    """Package an AgentResponse into a state update."""
    return {
        "response": resp.model_dump(),
        "messages": [AIMessage(content=resp.message)],
        **flags,
    }


def _wants_plan_now(messages) -> bool:
    text = _last_human_text(messages).lower()
    return any(kw in text for kw in _PLAN_KEYWORDS)


# ---------------------------------------------------------------------------
# Router (conditional entry point)
# ---------------------------------------------------------------------------
def route(state) -> str:
    plan = state.get("plan")
    if _wants_plan_now(state["messages"]) and not plan:
        return "plan"
    if not state.get("form_sent"):
        return "form"
    if not state.get("form_completed"):
        return "intake"
    if state.get("awaiting_confirm"):
        return "confirm"
    if not state.get("intake_complete"):
        return "intake"
    if not state.get("profile_confirmed"):
        return "reflect"
    if not plan:
        return "plan"
    return "refine"


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def form_node(state):
    """Turn 1 — warm welcome + the onboarding form."""
    form = Form(
        title="Let's get to know you (about 60 seconds — skip anything you like)",
        fields=[
            FormField(
                key="age_stage",
                label="Where are you right now?",
                type="single_choice",
                options=[
                    "In school (up to ~12)",
                    "Teen student",
                    "College or training",
                    "Working or job-hunting",
                ],
                required=True,
            ),
            FormField(
                key="interests",
                label="What kinds of things pull you in? (pick any)",
                type="multi_choice",
                options=[
                    "Making & building",
                    "Helping people",
                    "Art & design",
                    "Science & nature",
                    "Technology & computers",
                    "Business & money",
                    "Sports & movement",
                    "Writing & stories",
                    "Other",
                ],
            ),
            FormField(
                key="working_style",
                label="What feels most like you?",
                type="single_choice",
                options=[
                    "With people",
                    "With ideas",
                    "With things (hands-on)",
                    "With data & numbers",
                    "Not sure",
                ],
            ),
            FormField(
                key="goals",
                label="Any career you've already dreamed about? (totally fine to skip)",
                type="short_text",
            ),
            FormField(
                key="constraints",
                label="Anything to plan around — time, budget, location? (optional)",
                type="short_text",
            ),
        ],
    )
    resp = AgentResponse(
        message=(
            "Hi there — I'm Pathfinder, and I'm here to help you find a direction that fits you. "
            "Let's start with a few quick taps. Skip anything you're not sure about."
        ),
        form=form,
        suggested_questions=["Just give me the plan", "How does this work?"],
    )
    return _emit(resp, form_sent=True)


def intake_node(state):
    """Parse the form submission and/or ask ONE gap-fill follow-up.

    Runs extraction on the latest reply, decides whether enough is known, and
    either asks the next quick-reply question (and ends the turn) or marks
    intake complete (handing off to ``reflect_node`` in the same turn).
    """
    profile = state.get("user_profile", {}) or {}
    profile = _safe_extract(profile, state["messages"])

    form_completed = True  # reaching intake means the form has been submitted
    gapfill_count = state.get("gapfill_count", 0)

    complete = _intake_ready(profile) or gapfill_count >= 3
    if complete:
        # Hand off to reflect_node this same turn — clear response so the
        # after_intake edge can distinguish handoff from a gap-fill question.
        return {
            "user_profile": profile,
            "form_completed": form_completed,
            "intake_complete": True,
            "response": None,
        }

    # Ask the single most valuable follow-up with quick replies.
    sys = SystemMessage(content=PERSONA + "\n\n" + GAPFILL + "\n\n" + _profile_context(profile))
    try:
        reply: ConvReply = llm.with_structured_output(ConvReply).invoke(
            [sys] + list(state["messages"])
        )
    except Exception:  # noqa: BLE001
        reply = ConvReply(
            message="Thanks for sharing! One more quick thing and I'll build your plan — "
            "what would you say you're naturally good at?",
            quick_replies=["Explaining things", "Fixing/building", "Creating art", "Not sure"],
        )
    resp = AgentResponse(message=reply.message, quick_replies=reply.quick_replies)
    return _emit(
        resp,
        user_profile=profile,
        form_completed=form_completed,
        gapfill_count=gapfill_count + 1,
    )


def reflect_node(state):
    """Warm summary + confirm. Fixed quick replies; sets awaiting_confirm."""
    profile = state.get("user_profile", {})
    sys = SystemMessage(content=PERSONA + "\n\n" + REFLECT + "\n\n" + _profile_context(profile))
    try:
        message = llm.invoke([sys] + list(state["messages"])).content
    except Exception:  # noqa: BLE001
        message = "Here's what I'm hearing about you. Does this sound right?"
    resp = AgentResponse(
        message=str(message),
        quick_replies=["Yes, that's me!", "Mostly — let me add something", "Change something"],
    )
    return _emit(resp, awaiting_confirm=True)


def confirm_node(state):
    """Interpret the user's reaction to the reflected summary."""
    text = _last_human_text(state["messages"]).lower()
    confirmed = any(w in text for w in ["yes", "that's me", "thats me", "correct", "yep", "yeah"])
    wants_change = any(w in text for w in ["change", "add", "mostly", "not quite", "wrong", "fix"])

    if confirmed and not wants_change:
        # Hand off to plan_node this same turn (response cleared for the edge).
        return {"awaiting_confirm": False, "profile_confirmed": True, "response": None}

    # They want to adjust — capture anything new and ask what to change.
    profile = _safe_extract(state.get("user_profile", {}) or {}, state["messages"])
    resp = AgentResponse(
        message="No problem — what should I add or change? Tell me in your own words.",
        quick_replies=[
            "My interests",
            "What I'm good at",
            "What matters to me",
            "My goals",
        ],
    )
    return _emit(
        resp,
        user_profile=profile,
        awaiting_confirm=False,
        intake_complete=False,
        gapfill_count=max(0, state.get("gapfill_count", 0) - 1),
    )


def plan_node(state):
    """Deliver the 6-section plan. Handles the early-plan path too."""
    profile = state.get("user_profile", {})
    early = not (state.get("intake_complete") and state.get("profile_confirmed"))
    extra = ("\n\n" + EARLY_PLAN) if early else ""
    sys = SystemMessage(content=PERSONA + "\n\n" + PLAN + extra + "\n\n" + _profile_context(profile))
    try:
        reply: PlanReply = llm.with_structured_output(PlanReply).invoke(
            [sys] + list(state["messages"])
        )
        message, plan_md, suggestions = reply.message, reply.plan_markdown, reply.suggested_questions
    except Exception:  # noqa: BLE001
        message = "Here's your plan!"
        plan_md = llm.invoke([sys] + list(state["messages"])).content
        suggestions = [
            "Tell me more about the first career",
            "What can I start this week?",
            "Make the plan simpler",
        ]
    if not suggestions:
        suggestions = [
            "Tell me more about the first career",
            "What can I start this week?",
            "Add more free resources",
        ]
    resp = AgentResponse(
        message=str(message),
        plan_markdown=str(plan_md),
        suggested_questions=suggestions,
    )
    return _emit(resp, plan=str(plan_md), profile_confirmed=True, intake_complete=True)


def refine_node(state):
    """All post-plan follow-ups. Always ships fresh suggested questions."""
    profile = state.get("user_profile", {})
    current_plan = state.get("plan") or ""
    context = (
        _profile_context(profile)
        + "\n\nThe current plan (update it only if they ask you to):\n"
        + current_plan
    )
    sys = SystemMessage(content=PERSONA + "\n\n" + REFINE + "\n\n" + context)
    try:
        reply: PlanReply = llm.with_structured_output(PlanReply).invoke(
            [sys] + list(state["messages"])
        )
        message = reply.message
        plan_md: Optional[str] = reply.plan_markdown or None
        suggestions = reply.suggested_questions
    except Exception:  # noqa: BLE001
        message = str(llm.invoke([sys] + list(state["messages"])).content)
        plan_md = None
        suggestions = []
    if not suggestions:
        suggestions = [
            "What can I start this week?",
            "Tell me more about one of these careers",
            "I did the first step — what's next?",
        ]
    resp = AgentResponse(
        message=str(message),
        plan_markdown=plan_md,
        suggested_questions=suggestions,
    )
    flags = {}
    if plan_md:
        flags["plan"] = plan_md
    return _emit(resp, **flags)


# ---------------------------------------------------------------------------
# Same-turn hand-off routers
# ---------------------------------------------------------------------------
def after_intake(state) -> str:
    # response is cleared to None only on the intake->reflect handoff.
    return "reflect" if state.get("response") is None else "end"


def after_confirm(state) -> str:
    return "plan" if state.get("response") is None else "end"
