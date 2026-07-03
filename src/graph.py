"""Graph assembly + checkpointer.

Router-based: every user turn re-enters the graph and the router picks the
right node from checkpointed state. Two nodes hand off within the same turn
(intake -> reflect, confirm -> plan) via conditional edges; all nodes end the
turn at ``END``.

    START ->(route)-> form | intake | confirm | reflect | plan | refine
    intake  ->(after_intake)-> reflect | END
    confirm ->(after_confirm)-> plan | END
    reflect | plan | refine | form -> END
"""

from __future__ import annotations

import os

from langgraph.graph import END, START, StateGraph

from .nodes import (
    after_confirm,
    after_intake,
    confirm_node,
    form_node,
    intake_node,
    plan_node,
    refine_node,
    reflect_node,
    route,
)
from .state import CounselingState


def _make_checkpointer():
    """InMemorySaver by default; SqliteSaver if PATHFINDER_DB is set."""
    db_path = os.getenv("PATHFINDER_DB")
    if db_path:
        from langgraph.checkpoint.sqlite import SqliteSaver

        # SqliteSaver.from_conn_string is a context manager; enter it and keep
        # it open for the process lifetime.
        cm = SqliteSaver.from_conn_string(db_path)
        return cm.__enter__()

    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver()


def build_graph():
    graph = StateGraph(CounselingState)

    graph.add_node("form", form_node)
    graph.add_node("intake", intake_node)
    graph.add_node("confirm", confirm_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("plan", plan_node)
    graph.add_node("refine", refine_node)

    graph.add_conditional_edges(
        START,
        route,
        {
            "form": "form",
            "intake": "intake",
            "confirm": "confirm",
            "reflect": "reflect",
            "plan": "plan",
            "refine": "refine",
        },
    )
    graph.add_conditional_edges("intake", after_intake, {"reflect": "reflect", "end": END})
    graph.add_conditional_edges("confirm", after_confirm, {"plan": "plan", "end": END})

    graph.add_edge("form", END)
    graph.add_edge("reflect", END)
    graph.add_edge("plan", END)
    graph.add_edge("refine", END)

    return graph.compile(checkpointer=_make_checkpointer())


# Default initial state — every flag off, empty profile.
def initial_state() -> dict:
    return {
        "user_profile": {},
        "form_sent": False,
        "form_completed": False,
        "intake_complete": False,
        "profile_confirmed": False,
        "awaiting_confirm": False,
        "gapfill_count": 0,
        "plan": None,
        "response": None,
    }


def make_config(thread_id: str = "thread-1") -> dict:
    return {"configurable": {"thread_id": thread_id}}


# Compiled graph, imported by the frontends.
chatbot = build_graph()
