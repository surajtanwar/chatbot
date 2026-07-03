# Build Prompt v2 — Career Counseling LangGraph Agent (for Claude Code)
# Focus: effortless user interaction (form-first intake + suggested questions)

> Paste everything below into Claude Code as your first message.

---

Build me a **career counseling agent** using **LangGraph** in Python. It helps kids, teens, and adults find career direction and gives them a detailed, personalized, actionable plan.

**The #1 design priority is ease of interaction:** the user should almost never face a blank prompt or a long interrogation. Achieve this with (a) a short structured **onboarding form** at the start, (b) **quick-reply choices** on every agent question, and (c) **suggested questions** the user can pick at every stage.

## Tech stack
- Python 3.11+; `langgraph`, `langchain-core`, `langchain-anthropic` (easy to swap provider), `pydantic`
- LangGraph checkpointer for session memory (`MemorySaver` for dev, `SqliteSaver` option, keyed by `thread_id`)
- CLI chat loop for testing now, but **all agent turns return a structured envelope** (below) so a web/mobile frontend can render forms, buttons, and chips without changing graph logic
- `.env` for the API key, with `.env.example`

## The structured response envelope (core requirement)
Every agent turn returns a Pydantic object, not just text:

```python
class AgentResponse(BaseModel):
    message: str                          # what the agent says
    form: Form | None = None              # render as a form if present
    quick_replies: list[str] = []         # 2-5 short answer choices for the current question
    suggested_questions: list[str] = []   # 2-4 things the USER might want to ask/say next
    plan_markdown: str | None = None      # present only when a plan is delivered/updated

class Form(BaseModel):
    title: str
    fields: list[FormField]

class FormField(BaseModel):
    key: str                              # maps to a user_profile field
    label: str                            # friendly question text
    type: Literal["single_choice", "multi_choice", "short_text"]
    options: list[str] = []               # for choice fields; always include an "Other" / "Not sure" option
    required: bool = False                # keep most fields optional — skipping must be OK
```

The CLI must render this envelope: forms as numbered questions the user answers in one pass (Enter to skip optional ones), quick replies and suggested questions as numbered pickable options alongside free text.

## Project structure
```
career_counselor/
  requirements.txt
  .env.example
  README.md
  src/
    state.py      # State, user_profile, AgentResponse/Form models
    prompts.py    # All system prompts
    nodes.py      # Node functions
    graph.py      # Graph assembly + checkpointer
    cli.py        # Envelope rendering for terminal
    main.py       # Entry point / chat loop
```

## State
- `messages` (LangGraph message annotation)
- `user_profile`: `age_stage` ("child"|"teen"|"adult"), `interests`, `strengths`, `working_style`, `values`, `situation`, `goals`, `constraints` — all optional
- `form_completed: bool`, `intake_complete: bool`, `plan: str | None`

## Interaction flow

**Turn 1 — Welcome + onboarding form.** Warm one-line greeting, then present ONE short form (~5 fields, ≤60 seconds to complete, mostly choice-based):
1. `age_stage` (single_choice): "In school (up to ~12) / Teen student / College or training / Working or job-hunting"
2. `interests` (multi_choice): ~8 broad options (Making & building, Helping people, Art & design, Science & nature, Technology & computers, Business & money, Sports & movement, Writing & stories) + Other
3. `working_style` (single_choice): "With people / With ideas / With things (hands-on) / With data & numbers / Not sure"
4. `goals` (short_text, optional): "Any career you've already dreamed about? (totally fine to skip)"
5. `constraints` (short_text, optional, adults shown only): "Anything to plan around — time, budget, location?"

Every field skippable except age_stage. After submission, parse answers into `user_profile`. **Adapt all later language to age_stage.**

**Turns 2–4 — Short conversational gap-fill (not an interrogation).** The form gives most of the profile; now ask at most 2–3 follow-ups, one at a time, ONLY for missing/vague high-value fields (usually strengths and values). Every question ships with `quick_replies`. Rules:
- If the user picked "Not sure" anywhere or says "I don't know": never re-ask — offer concrete examples or a mini choice set.
- Give a light progress cue ("one more quick thing and I'll build your plan").
- One-line "why I'm asking" before personal questions.
- Run structured extraction on every free-text reply and fill EVERY field it reveals, so follow-ups shrink automatically.

**Reflect (one turn).** Summarize the profile warmly, ask to confirm/correct. `quick_replies`: ["Yes, that's me!", "Mostly — let me add something", "Change something"].

**Plan.** Deliver the plan in `plan_markdown` (sections below) with a short spoken intro in `message`, plus `suggested_questions` like: "Tell me more about the first career", "Make the plan simpler", "What can I start this week?", "Add more free resources".

**Refine loop (all later turns).** Handle follow-ups using stored profile+plan. ALWAYS include fresh, contextual `suggested_questions` so the user never has to invent what to ask. Support "I did step 1, what's next?" via session memory. Offer to save the plan to `plan_<thread_id>.md` on request.

**Early-plan path.** At ANY point, if the user asks for the plan ("just give me the plan"), generate a best-guess plan from whatever is known, noting one or two answers that would sharpen it. `suggested_questions` should include those sharpening answers as options.

## Plan format (checklist Markdown)
1. **Your snapshot** — affirming summary of who they are
2. **Career directions that fit** — 2–4 options, each: why it fits *them*, and what the role actually does day to day
3. **Roadmap** — Right now / Short term (6–12 mo) / Long term (1–5 yr), as `- [ ]` checkbox items, every step specific and actionable
4. **Skills to build** — each with one concrete way to start
5. **Ways to explore & learn** — free/accessible resources, activities, people to talk to, things to try
6. **Encouragement** — genuine and tailored
Adapt depth and vocabulary to age_stage (playful/simple for kids; relatable for teens; practical for adults).

## Graph shape
Router-based so each user turn re-enters the graph with checkpointed state:
- `router`: no form done → `form_node`; user asked for plan → `plan_node`; intake incomplete → `gapfill_node`; profile confirmed but no plan → `plan_node` (via `reflect_node`); else → `refine_node`
- `form_node` → emits the onboarding form; next turn parses submission into `user_profile`
- `gapfill_node` → asks one follow-up with quick_replies; runs extraction; sets `intake_complete` when strengths/values/goals are reasonably covered (or after 3 follow-ups max — don't hold the plan hostage)
- `reflect_node` → confirm summary → `plan_node`
- `plan_node` → fills `plan_markdown` → `refine_node`
- `refine_node` → all post-plan interaction

## Safety (implement in prompts and logic)
- child/teen: encourage sharing the plan with parents, guardians, teachers, or a school counselor; never encourage secrecy from trusted adults
- Never collect sensitive PII (full name, address, contact details, financial info) — the form must not ask for any
- Stay in scope: career exploration only; not a substitute for licensed counselors, therapists, doctors, or financial advisors
- On serious distress or crisis signs: pause career talk, respond with empathy, encourage reaching out to a trusted adult or local support service; do not diagnose or counsel through a crisis
- Supportive, judgment-free; never pressure

## Prompts to embed (src/prompts.py)
- `PERSONA`: Pathfinder — warm, patient, encouraging counselor for all ages; adapts tone to age_stage; asks at most one thing at a time; always offers choices and suggestions so replying is effortless; honest but encouraging; assumes nothing about gender/background/means; includes the safety rules above.
- `EXTRACTION`: read the conversation, return ONLY JSON matching the user_profile schema; fill inferable fields, null otherwise.
- `GAPFILL`: pick the single most valuable missing field; ask with quick_replies; handle "not sure" with examples; include progress cue and "why I'm asking" when personal.
- `REFLECT`, `PLAN`, `REFINE`: per the flow above; PLAN and REFINE must always populate `suggested_questions`.

## Deliverables
- Runnable: `pip install -r requirements.txt` → `python -m src.main`
- README: setup, running, how the envelope maps to a future web UI, session memory / thread_id, swapping providers
- Robust handling of malformed extraction output (retry once, else keep existing profile values)
- 2–3 scripted demo conversations in the README (a kid, a teen, an adult career-changer) showing form → gap-fill → plan → refine

Start by showing me the file layout and the state + envelope models for approval, then build the graph and nodes, then the CLI.
