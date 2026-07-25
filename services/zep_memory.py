"""Zep Cloud graph-memory integration for story-aware characters.

Usage
-----
- ``ingest_story(story_id, text)``  — push story transcript chunks into a
  named graph (idempotent: skipped if already seeded).
- ``search_story(story_id, query)`` — retrieve the most relevant facts/edges
  from the graph to inject into the agent's system prompt.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from zep_cloud import Zep

load_dotenv(override=True)

# ── constants ──────────────────────────────────────────────────────────────

_CHUNK_SIZE = 1800          # characters per text chunk pushed to Zep
_SEARCH_LIMIT = 8           # max graph edges/facts returned per query
_MAX_CONTEXT_CHARS = 1400   # cap on total injected context

# Sentinel file: once a story is seeded we write a small marker so we don't
# re-ingest every time the server restarts.
_SEED_DIR = Path("data") / "zep_seeds"

# ── client factory ─────────────────────────────────────────────────────────

def _client() -> Zep:
    api_key = os.getenv("ZEP_API_KEY", "")
    if not api_key:
        raise RuntimeError("ZEP_API_KEY is not set in the environment.")
    return Zep(api_key=api_key)


# ── internal helpers ───────────────────────────────────────────────────────

def _sentinel_path(story_id: str) -> Path:
    return _SEED_DIR / f"{story_id}.seeded"


def _is_seeded(story_id: str) -> bool:
    return _sentinel_path(story_id).exists()


def _mark_seeded(story_id: str) -> None:
    _SEED_DIR.mkdir(parents=True, exist_ok=True)
    _sentinel_path(story_id).touch()


# ── public API ─────────────────────────────────────────────────────────────

def _ensure_graph(zep: Zep, story_id: str) -> None:
    """Create the named graph if it doesn't already exist."""
    try:
        zep.graph.get(story_id)
    except Exception:
        # Graph doesn't exist — create it
        zep.graph.create(
            graph_id=story_id,
            name=f"story_{story_id}",
            description=f"Knowledge graph for the '{story_id}' story transcript.",
        )


def ingest_story(story_id: str, text: str) -> None:
    """Push the full story transcript into a Zep graph as text episodes.

    Uses ``graph_id=story_id`` so every story gets its own isolated graph.
    Skips silently if the sentinel file already exists (idempotent).
    """
    if _is_seeded(story_id):
        return

    zep = _client()
    _ensure_graph(zep, story_id)

    chunks = textwrap.wrap(text, _CHUNK_SIZE, break_long_words=False, replace_whitespace=False)

    for i, chunk in enumerate(chunks):
        zep.graph.add(
            graph_id=story_id,
            data=chunk,
            type="text",
            source_description=f"story_transcript_chunk_{i}",
        )

    _mark_seeded(story_id)
    print(f"[Zep] Ingested {len(chunks)} chunks for story '{story_id}'")


def search_story(story_id: str, query: str, limit: int = _SEARCH_LIMIT) -> str:
    """Search the story graph and return a concise fact block for the agent.

    Returns an empty string if Zep is unavailable or the graph is empty.
    """
    try:
        zep = _client()
        results = zep.graph.search(
            graph_id=story_id,
            query=query,
            limit=limit,
            scope="edges",
        )
        facts: list[str] = []
        if results.edges:
            for edge in results.edges:
                fact = edge.fact or ""
                if fact:
                    facts.append(fact.strip())

        if not facts:
            return ""

        block = "\n".join(f"- {f}" for f in facts)
        # Cap total length to avoid blowing the context window
        if len(block) > _MAX_CONTEXT_CHARS:
            block = block[:_MAX_CONTEXT_CHARS] + "…"
        return block
    except Exception as exc:
        print(f"[Zep] search_story failed: {exc}")
        return ""
