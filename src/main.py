"""CLI entry point — run with ``python -m src.main``.

Starts a Pathfinder session, renders each turn's envelope in the terminal, and
feeds the user's next input back into the checkpointed graph.
"""

from __future__ import annotations

import sys
import uuid

from langchain_core.messages import HumanMessage

from .cli import render_and_prompt
from .graph import chatbot, initial_state, make_config
from .state import AgentResponse

SAVE_COMMANDS = {"save", "save plan", "/save"}


def run() -> None:
    thread_id = "cli-" + uuid.uuid4().hex[:8]
    config = make_config(thread_id)

    print("=" * 60)
    print("🧭  Pathfinder — your friendly career guide")
    print("     Type 'quit' to exit, 'save' to save your plan.")
    print("=" * 60)

    # Kick off the conversation (a greeting triggers the onboarding form).
    payload = {**initial_state(), "messages": [HumanMessage(content="Hi!")]}

    while True:
        result = chatbot.invoke(payload, config=config)
        resp = AgentResponse(**result["response"])

        user_text = render_and_prompt(resp).strip()

        if user_text.lower() in {"quit", "exit", "q"}:
            print("\n🧭 Pathfinder: Take care — you've got this. 👋")
            break

        # Save is a local command — handle it without advancing the graph.
        while user_text.lower() in SAVE_COMMANDS:
            _save_plan(result, thread_id)
            user_text = input("\nYou (type, or 'quit'): ").strip()
            if user_text.lower() in {"quit", "exit", "q"}:
                return

        payload = {"messages": [HumanMessage(content=user_text)]}


def _save_plan(result: dict, thread_id: str) -> None:
    plan = (result.get("response") or {}).get("plan_markdown") or result.get("plan")
    if not plan:
        print("\n(no plan to save yet — let's finish building it first)")
        return
    path = f"plan_{thread_id}.md"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(plan)
    print(f"\n💾 Saved your plan to {path}")


if __name__ == "__main__":
    try:
        run()
    except (KeyboardInterrupt, EOFError):
        print("\n\n🧭 Pathfinder: Bye for now! 👋")
        sys.exit(0)
