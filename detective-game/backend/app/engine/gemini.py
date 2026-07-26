"""Thin async wrapper over the Gemini client.

One place that knows how to talk to the API, so the engine modules stay about the
game. Every call is async because Phase 3 fires all room images concurrently.

Gemini is a fallback now — Groq handles text and OpenRouter handles detection — so
google-genai is imported lazily. It used to be imported at module scope, which meant a
machine without that package could not start the server at all, even though nothing on
the default path would ever have called it.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel

from ..config import GEMINI_API_KEY, TEXT_MODEL

if TYPE_CHECKING:
    from google import genai

T = TypeVar("T", bound=BaseModel)

# The client's underlying async transport binds to the event loop that first uses it.
# Reusing it from a second loop raises "Event loop is closed" — uvicorn keeps one loop
# so the server never sees this, but scripts that call asyncio.run() more than once do.
# Rebuilding when the loop changes costs nothing and removes the whole failure mode.
_cached: tuple[asyncio.AbstractEventLoop, Any] | None = None


def _genai():
    try:
        from google import genai
    except ImportError as e:  # pragma: no cover - depends on install
        raise RuntimeError(
            "google-genai is not installed. It is only needed to use Gemini; "
            "the default setup runs on Groq and OpenRouter."
        ) from e
    return genai


def _types():
    from google.genai import types

    return types


def available() -> bool:
    if not GEMINI_API_KEY:
        return False
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False
    return True


def _client() -> genai.Client:
    global _cached
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    loop = asyncio.get_running_loop()
    if _cached is None or _cached[0] is not loop:
        _cached = (loop, _genai().Client(api_key=GEMINI_API_KEY))
    return _cached[1]


async def generate_json(
    prompt: str,
    schema: type[T],
    system: str | None = None,
    temperature: float = 1.0,
    model: str | None = None,
    thinking_budget: int | None = None,
) -> T:
    """Structured generation. Returns a validated instance of `schema`.

    thinking_budget=0 is the difference between an 11s case and a 36s one. Note that
    some models (gemini-3.6-flash) reject 0 with a 400, so leave it None for those.
    """
    types = _types()
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        system_instruction=system,
        temperature=temperature,
    )
    if thinking_budget is not None:
        config.thinking_config = types.ThinkingConfig(thinking_budget=thinking_budget)

    response = await _client().aio.models.generate_content(
        model=model or TEXT_MODEL,
        contents=prompt,
        config=config,
    )
    parsed = response.parsed
    if parsed is None:
        raise ValueError(f"Model returned unparseable JSON: {response.text!r:.300}")
    return parsed  # type: ignore[return-value]


async def generate_text(
    prompt: str,
    system: str | None = None,
    temperature: float = 1.0,
    max_output_tokens: int | None = None,
) -> str:
    types = _types()
    response = await _client().aio.models.generate_content(
        model=TEXT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
    )
    return (response.text or "").strip()
