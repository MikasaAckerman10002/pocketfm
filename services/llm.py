"""Ollama integration for character responses."""

import os

from openai import OpenAI
from dotenv import load_dotenv

from agents.barbie import BARBIE_PROMPT


load_dotenv(override=True)

MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")


class LLMConfigurationError(RuntimeError):
    """Raised when required language model configuration is unavailable."""


class LLMResponseError(RuntimeError):
    """Raised when the language model returns no usable text."""


def generate_response(
    user_message: str,
    history: list[dict] | None = None,
    system_prompt: str = BARBIE_PROMPT,
    max_tokens: int = 120,
) -> str:
    """Return a character reply for a user's message."""
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    completion = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=max_tokens,
    )

    reply = completion.choices[0].message.content
    if not reply:
        raise LLMResponseError("The language model returned an empty response.")

    return reply.strip()
