"""Provider-agnostic text generation.

case_gen and npc call this, not a specific vendor. Which backend answers is a config
decision, so swapping providers does not touch game logic.

Three roles rather than one model, because they want different things:
  "case"    - one call per game, complex nested JSON, quality matters most
  "npc"     - one call per turn, short reply, latency matters most (Groq preferred)
  "persona" - narrator lines, short and infrequent (Gemini preferred to save Groq TPD)
"""

from __future__ import annotations

import logging
from typing import Literal, TypeVar

from pydantic import BaseModel

from .. import config
from . import gemini, groq

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

Role = Literal["case", "npc", "persona"]


def provider() -> str:
    if config.LLM_DISABLED:
        return "none"
    if config.TEXT_PROVIDER != "auto":
        return config.TEXT_PROVIDER
    if groq.available():
        return "groq"
    if gemini.available():
        return "gemini"
    return "none"


def available() -> bool:
    return provider() != "none"


def _model_for(role: Role, backend: str) -> str:
    if backend == "groq":
        return config.GROQ_CASE_MODEL if role == "case" else config.GROQ_NPC_MODEL
    # "persona" uses the faster NPC model on Gemini — lines are short.
    return config.TEXT_MODEL if role == "case" else config.NPC_MODEL


async def generate_json(
    prompt: str,
    schema: type[T],
    role: Role,
    system: str | None = None,
    temperature: float = 1.0,
) -> T:
    backend = provider()
    if backend == "none":
        raise RuntimeError("No text provider configured (set GROQ_API_KEY or GEMINI_API_KEY).")

    # Persona narration is short and infrequent. Route it to Gemini first so it
    # draws from a separate quota pool and does not eat Groq's tokens-per-day
    # limit that NPC dialogue depends on for a full playthrough.
    if role == "persona" and gemini.available():
        try:
            return await gemini.generate_json(
                prompt,
                schema,
                system=system,
                temperature=temperature,
                model=_model_for(role, "gemini"),
                thinking_budget=0,
            )
        except Exception as e:
            log.warning("Gemini persona narration failed (%s); falling back to Groq.", e)
            if not groq.available():
                raise
            return await groq.generate_json(
                prompt,
                schema,
                system=system,
                temperature=temperature,
                model=_model_for(role, "groq"),
            )

    if backend == "groq":
        return await groq.generate_json(
            prompt,
            schema,
            system=system,
            temperature=temperature,
            model=_model_for(role, "groq"),
        )

    return await gemini.generate_json(
        prompt,
        schema,
        system=system,
        temperature=temperature,
        model=_model_for(role, "gemini"),
        # Thinking triples case latency for no gain in playability.
        thinking_budget=0,
    )
