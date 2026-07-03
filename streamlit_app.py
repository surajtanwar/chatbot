"""Envelope-aware Streamlit UI for Pathfinder.

Renders each AgentResponse the way a real web UI would: forms as widgets,
quick replies & suggested questions as buttons, and the plan as a rendered
markdown panel with a download button. Replaces the v1 counseling_frontend.py.
"""

from __future__ import annotations

import uuid

import streamlit as st
from langchain_core.messages import HumanMessage

from src.graph import chatbot, initial_state, make_config
from src.state import AgentResponse

st.set_page_config(page_title="Pathfinder — Career Counselor", page_icon="🧭")
st.title("🧭 Pathfinder — Career Counselor")

# ---------------------------------------------------------------------------
# Session bootstrap
# ---------------------------------------------------------------------------
if "thread_id" not in st.session_state:
    st.session_state.thread_id = "web-" + uuid.uuid4().hex[:8]
    st.session_state.history = []  # list of {"role", "content"}
    st.session_state.latest = None  # latest AgentResponse
    st.session_state.pending = None  # user text to send on next run
    st.session_state.started = False

config = make_config(st.session_state.thread_id)


def send(text: str) -> None:
    """Queue user text and rerun so it's processed at the top of the script."""
    st.session_state.pending = text
    st.rerun()


def advance(payload: dict) -> None:
    result = chatbot.invoke(payload, config=config)
    resp = AgentResponse(**result["response"])
    st.session_state.latest = resp
    st.session_state.history.append({"role": "assistant", "content": resp.message})


# ---------------------------------------------------------------------------
# Process a queued user message (or kick off the first turn)
# ---------------------------------------------------------------------------
if not st.session_state.started:
    st.session_state.started = True
    advance({**initial_state(), "messages": [HumanMessage(content="Hi!")]})
elif st.session_state.pending is not None:
    text = st.session_state.pending
    st.session_state.pending = None
    st.session_state.history.append({"role": "user", "content": text})
    advance({"messages": [HumanMessage(content=text)]})

# ---------------------------------------------------------------------------
# Render conversation history
# ---------------------------------------------------------------------------
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

resp = st.session_state.latest

# ---------------------------------------------------------------------------
# Render the latest envelope's interactive bits
# ---------------------------------------------------------------------------
if resp is not None:
    if resp.plan_markdown:
        with st.chat_message("assistant"):
            st.markdown(resp.plan_markdown)
            st.download_button(
                "⬇️ Download plan",
                data=resp.plan_markdown,
                file_name=f"plan_{st.session_state.thread_id}.md",
                mime="text/markdown",
            )

    if resp.form:
        with st.form("onboarding"):
            st.subheader(resp.form.title)
            widget_vals: dict[str, object] = {}
            for field in resp.form.fields:
                if field.type == "single_choice":
                    widget_vals[field.key] = st.radio(
                        field.label, field.options, index=None
                    )
                elif field.type == "multi_choice":
                    widget_vals[field.key] = st.multiselect(field.label, field.options)
                else:
                    widget_vals[field.key] = st.text_input(field.label)
            if st.form_submit_button("Submit"):
                lines = []
                for key, val in widget_vals.items():
                    if not val:
                        continue
                    if isinstance(val, list):
                        val = ", ".join(val)
                    lines.append(f"{key}: {val}")
                send("Here are my answers:\n" + ("\n".join(lines) or "(skipped)"))

    # Quick replies + suggested questions as buttons.
    chips = [("💬", q) for q in resp.quick_replies] + [
        ("❓", q) for q in resp.suggested_questions
    ]
    if chips:
        cols = st.columns(min(len(chips), 3))
        for i, (icon, label) in enumerate(chips):
            if cols[i % len(cols)].button(f"{icon} {label}", key=f"chip-{i}-{label}"):
                send(label)

# Free-text input is always available.
user_input = st.chat_input("Type your answer...")
if user_input:
    send(user_input)
