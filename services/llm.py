"""Ollama integration for character responses."""

import os

from openai import OpenAI
from dotenv import load_dotenv

from agents.barbie import BARBIE_PROMPT


MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

load_dotenv()


class LLMConfigurationError(RuntimeError):
    """Raised when required language model configuration is unavailable."""


class LLMResponseError(RuntimeError):
    """Raised when the language model returns no usable text."""


def generate_response(
    user_message: str,
    history: list[dict] | None = None,
    system_prompt: str = BARBIE_PROMPT,
) -> str:
    """Return a character reply for a user's message.

    Parameters
    ----------
    user_message:
        The latest text from the user.
    history:
        A mutable list of prior ``{"role": ..., "content": ...}`` turns for this
        session.  Pass ``None`` (or omit) for a stateless single-turn call.
        The caller is responsible for appending the new user/assistant pair after
        this function returns so that future calls see the full context.
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    completion = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=120,
    )

    reply = completion.choices[0].message.content
    if not reply:
        raise LLMResponseError("The language model returned an empty response.")

    return reply.strip()
