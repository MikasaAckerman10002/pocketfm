"""Groq backend.

OpenAI-compatible chat completions over httpx — no extra SDK. Groq is used for text
because the Gemini free tier caps at 20 requests per model per day, and NPC dialogue
spends one call per turn, which a single playthrough exhausts.

Structured output is attempted with a strict json_schema first and falls back to plain
JSON mode, because schema support varies by model and a refused request would
otherwise cost a turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from .. import config

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Most Groq models reject strict json_schema. Remember which, so we stop paying an
# extra failed round-trip on every single NPC turn.
_no_strict_schema: set[str] = set()


def available() -> bool:
    return bool(config.GROQ_API_KEY)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }


def _strictify(schema: dict[str, Any]) -> dict[str, Any]:
    """Strict json_schema mode requires every object to forbid extra keys and to list
    every property as required. Pydantic does neither by default."""
    if not isinstance(schema, dict):
        return schema
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        props = schema.get("properties")
        if isinstance(props, dict):
            schema["required"] = list(props.keys())
    for key in ("properties", "$defs", "definitions"):
        section = schema.get(key)
        if isinstance(section, dict):
            for value in section.values():
                _strictify(value)
    for key in ("items", "additionalItems"):
        if isinstance(schema.get(key), dict):
            _strictify(schema[key])
    for key in ("anyOf", "oneOf", "allOf"):
        if isinstance(schema.get(key), list):
            for value in schema[key]:
                _strictify(value)
    return schema


def _retry_after(text: str) -> float | None:
    """Groq's 429 body says how long to wait, in either unit:
    'try again in 5.425s' or 'try again in 269.999999ms'."""
    match = re.search(r"try again in ([\d.]+)(ms|s)\b", text)
    if not match:
        return None
    value = float(match.group(1))
    return value / 1000 if match.group(2) == "ms" else value


async def _post(body: dict[str, Any], timeout: float) -> str:
    async with httpx.AsyncClient() as client:
        for attempt in (1, 2):
            r = await client.post(
                f"{config.GROQ_BASE}/chat/completions",
                json=body,
                headers=_headers(),
                timeout=timeout,
            )
            if r.status_code < 400:
                return r.json()["choices"][0]["message"]["content"]

            # The free tier caps tokens per minute, and it tells us when it will
            # clear. Waiting a few seconds beats dropping the turn to a canned reply.
            wait = _retry_after(r.text) if r.status_code == 429 else None
            if wait is not None and attempt == 1 and wait <= config.GROQ_MAX_RETRY_WAIT:
                log.info("Groq rate limited; retrying in %.1fs.", wait)
                await asyncio.sleep(wait + 0.4)
                continue
            raise RuntimeError(f"Groq {r.status_code}: {r.text[:300]}")
    raise RuntimeError("unreachable")


async def generate_json(
    prompt: str,
    schema: type[T],
    system: str | None = None,
    temperature: float = 1.0,
    model: str | None = None,
    timeout: float = 120.0,
) -> T:
    name = model or config.GROQ_CASE_MODEL
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    base = {"model": name, "messages": messages, "temperature": temperature}

    def loose_request() -> dict[str, Any]:
        # Plain JSON mode still yields parseable output, and Pydantic validation is
        # the real gate either way. The schema goes in the prompt instead.
        body = dict(base)
        body["response_format"] = {"type": "json_object"}
        body["messages"] = [
            *messages[:-1],
            {
                "role": "user",
                "content": prompt
                + "\n\nRespond with JSON matching exactly this schema:\n"
                + json.dumps(schema.model_json_schema()),
            },
        ]
        return body

    if name in _no_strict_schema:
        return schema.model_validate_json(await _post(loose_request(), timeout))

    strict = dict(base)
    strict["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__.lower(),
            "schema": _strictify(schema.model_json_schema()),
            "strict": True,
        },
    }

    try:
        text = await _post(strict, timeout)
    except RuntimeError as e:
        _no_strict_schema.add(name)
        log.info("%s does not accept strict schemas; using json_object from now on.", name)
        log.debug("strict schema refusal: %s", e)
        text = await _post(loose_request(), timeout)

    return schema.model_validate_json(text)


async def generate_text(
    prompt: str,
    system: str | None = None,
    temperature: float = 1.0,
    model: str | None = None,
    timeout: float = 60.0,
) -> str:
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    return (
        await _post(
            {
                "model": model or config.GROQ_NPC_MODEL,
                "messages": messages,
                "temperature": temperature,
            },
            timeout,
        )
    ).strip()


async def list_models() -> list[str]:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{config.GROQ_BASE}/models", headers=_headers(), timeout=30
        )
        r.raise_for_status()
        return sorted(m["id"] for m in r.json().get("data", []))
