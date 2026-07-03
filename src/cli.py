"""Terminal rendering of the AgentResponse envelope.

Renders forms as numbered questions answered in one pass (Enter skips optional
ones), and quick replies / suggested questions as numbered pickable options
that also accept free text.
"""

from __future__ import annotations

from .state import AgentResponse, Form

DIV = "-" * 60


def _render_form(form: Form) -> str:
    """Prompt the user through a form; return one labeled text block."""
    print(f"\n📋 {form.title}")
    answers: list[str] = []
    for i, field in enumerate(form.fields, 1):
        star = " *" if field.required else " (optional — Enter to skip)"
        print(f"\n{i}. {field.label}{star}")

        if field.type in ("single_choice", "multi_choice"):
            for j, opt in enumerate(field.options, 1):
                print(f"   {j}) {opt}")
            hint = (
                "   Pick numbers separated by commas: "
                if field.type == "multi_choice"
                else "   Pick a number: "
            )
            while True:
                raw = input(hint).strip()
                if not raw:
                    if field.required:
                        print("   (this one's needed)")
                        continue
                    break
                picked = _resolve_choices(raw, field.options)
                if picked:
                    answers.append(f"{field.key}: {', '.join(picked)}")
                    break
                print("   (didn't catch that — try a number, or type your own)")
                answers.append(f"{field.key}: {raw}")
                break
        else:  # short_text
            raw = input("   Your answer: ").strip()
            if raw:
                answers.append(f"{field.key}: {raw}")

    if not answers:
        return "(skipped the form)"
    return "Here are my answers:\n" + "\n".join(answers)


def _resolve_choices(raw: str, options: list[str]) -> list[str]:
    """Map '1,3' or free text to option labels."""
    picked: list[str] = []
    for token in raw.split(","):
        token = token.strip()
        if token.isdigit() and 1 <= int(token) <= len(options):
            picked.append(options[int(token) - 1])
    return picked


def _render_chips(label: str, items: list[str], start: int) -> int:
    """Print numbered pickable options; return the next available number."""
    if not items:
        return start
    print(f"\n{label}")
    for i, item in enumerate(items, start):
        print(f"   [{i}] {item}")
    return start + len(items)


def render_and_prompt(resp: AgentResponse) -> str:
    """Show the envelope, then collect the user's next input as text."""
    print(f"\n🧭 Pathfinder: {resp.message}")

    if resp.plan_markdown:
        print(f"\n{DIV}\n{resp.plan_markdown}\n{DIV}")

    if resp.form:
        return _render_form(resp.form)

    # Build a pick-list from quick replies + suggested questions.
    pick_map: dict[int, str] = {}
    n = 1
    if resp.quick_replies:
        end = _render_chips("You can tap:", resp.quick_replies, n)
        for idx, val in enumerate(resp.quick_replies, n):
            pick_map[idx] = val
        n = end
    if resp.suggested_questions:
        end = _render_chips("Or ask:", resp.suggested_questions, n)
        for idx, val in enumerate(resp.suggested_questions, n):
            pick_map[idx] = val
        n = end

    raw = input("\nYou (type, or pick a number): ").strip()
    if raw.isdigit() and int(raw) in pick_map:
        chosen = pick_map[int(raw)]
        print(f"   → {chosen}")
        return chosen
    return raw
