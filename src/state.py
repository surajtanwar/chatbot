"""State and the structured response envelope for the Pathfinder agent.

The envelope (``AgentResponse``) is the core contract of this project: every
agent turn returns one, never bare text. A frontend renders it like so:

    - ``form``               -> a form (radios / multiselects / text inputs)
    - ``quick_replies``      -> tappable answer chips for the current question
    - ``suggested_questions``-> tappable chips of what the USER might ask next
    - ``plan_markdown``      -> a rendered markdown panel (present only with a plan)
    - ``message``            -> the spoken text of the turn
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# The structured response envelope (core requirement)
# ---------------------------------------------------------------------------
FieldType = Literal["single_choice", "multi_choice", "short_text"]


class FormField(BaseModel):
    """One question in an onboarding/intake form."""

    key: str = Field(description="Maps to a user_profile field.")
    label: str = Field(description="Friendly question text shown to the user.")
    type: FieldType = "short_text"
    options: list[str] = Field(
        default_factory=list,
        description="Choices for choice fields; always include an 'Other' / "
        "'Not sure' option.",
    )
    required: bool = False


class Form(BaseModel):
    """A short set of questions the user answers in one pass."""

    title: str
    fields: list[FormField]


class AgentResponse(BaseModel):
    """What every agent turn returns — rendered by the frontend, not printed raw."""

    message: str  # what the agent says
    form: Optional[Form] = None  # render as a form if present
    quick_replies: list[str] = Field(default_factory=list)  # 2-5 answer choices
    suggested_questions: list[str] = Field(default_factory=list)  # 2-4 next asks
    plan_markdown: Optional[str] = None  # present only when a plan is delivered/updated


# ---------------------------------------------------------------------------
# Structured extraction — fills the user_profile from free text
# ---------------------------------------------------------------------------
# The eight profile areas we track. All optional; skipping is always OK.
PROFILE_AREAS = [
    "age_stage",
    "interests",
    "strengths",
    "working_style",
    "values",
    "situation",
    "goals",
    "constraints",
]

# Areas that matter most before we're comfortable building a plan.
KEY_AREAS = ["strengths", "values", "goals"]


class ProfileExtraction(BaseModel):
    """Structured read of the conversation into user_profile fields.

    Every field is optional — the model fills what the text reveals and leaves
    the rest ``None`` so we never overwrite a known value with a guess.
    """

    age_stage: Optional[Literal["child", "teen", "adult"]] = Field(
        default=None,
        description="'child' (in school up to ~12), 'teen' (teen student), or "
        "'adult' (college/training or working/job-hunting).",
    )
    interests: Optional[str] = Field(default=None, description="What they enjoy / are curious about.")
    strengths: Optional[str] = Field(default=None, description="What they are naturally good at.")
    working_style: Optional[str] = Field(
        default=None,
        description="With people / ideas / things (hands-on) / data & numbers; alone vs teams.",
    )
    values: Optional[str] = Field(default=None, description="What matters to them in work/life.")
    situation: Optional[str] = Field(
        default=None, description="Age/grade or career stage, current education or job."
    )
    goals: Optional[str] = Field(default=None, description="Careers or dreams they've imagined.")
    constraints: Optional[str] = Field(
        default=None, description="Time, budget, location, education access, family/health."
    )


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------
class CounselingState(TypedDict):
    """Checkpointed per ``thread_id``; each user turn re-enters the graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    user_profile: dict  # keys from PROFILE_AREAS, all optional
    form_sent: bool  # onboarding form has been emitted
    form_completed: bool  # user has submitted the onboarding form
    intake_complete: bool  # enough gathered to reflect + plan
    profile_confirmed: bool  # user confirmed the reflected summary
    awaiting_confirm: bool  # reflect asked; next turn interprets yes/no/change
    gapfill_count: int  # number of follow-ups asked (capped at 3)
    plan: Optional[str]  # the delivered plan markdown
    response: Optional[dict]  # latest AgentResponse.model_dump() — frontends read this
