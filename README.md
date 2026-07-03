# 🧭 Pathfinder — Career Counseling Agent (v2)

A warm, all-ages career counselor built on **LangGraph**. The design priority is
**effortless interaction**: the user almost never faces a blank prompt. Every
turn ships a short **onboarding form**, **quick-reply choices**, and **suggested
questions**, so replying is usually a single tap.

Pathfinder guides a person from a 60-second intake form → a couple of light
follow-ups → a warm reflection → a detailed, personalized, actionable plan →
open-ended refinement — adapting tone and depth to whether they're a kid, teen,
or adult.

## The structured envelope (core idea)

Every agent turn returns an `AgentResponse` object, never bare text:

```python
class AgentResponse(BaseModel):
    message: str                       # what the agent says
    form: Form | None = None           # render as a form if present
    quick_replies: list[str] = []      # 2-5 answer choices for the current question
    suggested_questions: list[str] = []# 2-4 things the user might ask next
    plan_markdown: str | None = None   # present only when a plan is delivered/updated
```

Any frontend renders this without knowing anything about the graph:

| Envelope field        | Web/mobile UI                          |
|-----------------------|----------------------------------------|
| `form`                | a form (radios, multiselects, inputs)  |
| `quick_replies`       | tappable answer chips for this question |
| `suggested_questions` | tappable "what to ask next" chips      |
| `plan_markdown`       | a rendered markdown panel + download    |
| `message`             | the spoken text of the turn            |

The CLI and Streamlit UI in this repo are just two renderers of that one contract.

## Graph shape

Router-based — each user turn re-enters the graph with checkpointed state:

```
START ─(route)─> form | intake | confirm | reflect | plan | refine
intake  ─(after_intake)─> reflect | END
confirm ─(after_confirm)─> plan | END
form | reflect | plan | refine ─> END
```

- **`form_node`** — turn 1: welcome + the ~5-field onboarding form.
- **`intake_node`** — parses the form / a follow-up via structured extraction,
  then asks at most **one** more quick-reply question. Marks intake complete once
  strengths + values + goals are covered, or after 3 follow-ups (never holds the
  plan hostage). Hands off to `reflect` in the same turn when done.
- **`reflect_node`** — warm summary + "does this sound right?" confirm.
- **`confirm_node`** — interprets yes / change; on "yes" hands off to `plan`.
- **`plan_node`** — the 6-section plan in `plan_markdown`. Also serves the
  **early-plan** path: ask "just give me the plan" any time for a best-guess plan.
- **`refine_node`** — all post-plan Q&A; always ships fresh suggested questions;
  supports "I did step 1, what's next?" via session memory.

State persists per `thread_id` via the checkpointer (in-memory by default).

## Files

| File | Purpose |
|------|---------|
| `src/state.py` | State + `AgentResponse` / `Form` / `FormField` / `ProfileExtraction` |
| `src/prompts.py` | Pathfinder persona + phase prompts |
| `src/llm.py` | `get_llm()` provider factory (OpenAI default, swappable) |
| `src/nodes.py` | Router + node functions |
| `src/graph.py` | Graph assembly + checkpointer |
| `src/cli.py` | Envelope → terminal rendering |
| `src/main.py` | CLI chat loop (`python -m src.main`) |
| `streamlit_app.py` | Envelope-aware Streamlit UI |

## Setup

> Use **Python 3.12**. 3.14 lacks prebuilt wheels for some deps.

```bash
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

cp .env.example .env      # then set OPENAI_API_KEY=sk-...
```

## Run

**CLI:**
```bash
.venv/Scripts/python.exe -m src.main
```

**Streamlit:**
```bash
.venv/Scripts/python.exe -m streamlit run streamlit_app.py
```
Then open http://localhost:8501.

## Session memory

State is checkpointed by `thread_id`. In-memory by default (lost on restart).
To persist across restarts, set `PATHFINDER_DB=pathfinder.sqlite` in `.env`
(uses LangGraph's `SqliteSaver`).

## Swapping the LLM provider

Everything talks to `get_llm()`; nothing imports a provider directly. To use
Anthropic instead of OpenAI, set in `.env`:

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```
(and `pip install langchain-anthropic`).

## Demo conversations

### A kid (age ~10)
```
Pathfinder: Hi there — I'm Pathfinder... [onboarding form]
You:        age_stage: In school; interests: Making & building, Sports & movement;
            working_style: With things (hands-on); goals: (skip); constraints: (skip)
Pathfinder: You love building things and moving around! One more quick thing —
            what are you really good at?  [Building stuff] [Sports] [Drawing] [Not sure]
You:        [Building stuff]
Pathfinder: Here's what I'm hearing about you... does this sound right?
            [Yes, that's me!] [Mostly...] [Change something]
You:        [Yes, that's me!]
Pathfinder: Here's your plan! 🎉
            ## Your snapshot ...  ## Career directions that fit (Maker, Builder,
            Sports coach) ... ## Roadmap  - [ ] Build a cardboard model this week ...
            (playful, simple, "share this with a grown-up you trust!")
            Suggested: [Tell me more about being a builder] [What can I try this week?]
```

### A teen (age ~15)
```
You:        age_stage: Teen student; interests: Technology & computers, Art & design;
            working_style: With ideas; goals: maybe game design
Pathfinder: Nice — tech + art is a great combo. Quick one: what matters most to
            you in a future job?  [Creativity] [Helping people] [Good money] [Freedom]
You:        [Creativity]
Pathfinder: [reflect] ... [Yes, that's me!]
Pathfinder: [plan] directions: Game designer, UX designer, Technical artist;
            roadmap with - [ ] items (learn Godot, build a tiny game, join a club);
            nudge to talk to a school counselor.
            Suggested: [How do I start with game design?] [Make the plan simpler]
```

### An adult career-changer
```
You:        age_stage: Working or job-hunting; interests: Helping people, Business & money;
            working_style: With people; goals: move out of retail;
            constraints: full-time job, tight budget
Pathfinder: Follow-up on strengths → [reflect] → [Yes, that's me!]
Pathfinder: [plan] directions: HR coordinator, Customer success, Community manager;
            roadmap with - [ ] free-first steps that fit a tight budget & evenings;
            practical tone, real constraints respected.
            Suggested: [What can I start this week for free?] [Add more free resources]
You:        just give me the plan   # early-plan path also works at any point
```

## Notes

- Malformed extraction output is retried once, then the existing profile is kept
  (no crashes, no lost data).
- Pathfinder never collects sensitive PII, stays in career-exploration scope,
  encourages minors to involve trusted adults, and redirects on signs of crisis.
- Keep your `.env` out of git (a `.gitignore` is included).
