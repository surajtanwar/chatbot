"""LLM factory — provider-swappable, defaults to OpenAI.

Set ``LLM_PROVIDER=anthropic`` (and ``ANTHROPIC_API_KEY``) in ``.env`` to swap.
Everything else in the app talks to ``get_llm()`` and never imports a provider
directly, so switching models is a one-line env change.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def get_llm(temperature: float = 0.7):
    """Return a chat model instance for the configured provider."""
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        return ChatAnthropic(model=model, temperature=temperature)

    from langchain_openai import ChatOpenAI

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return ChatOpenAI(model=model, temperature=temperature)
