"""Voice, via ElevenLabs.

Speech is requested on its own endpoint rather than inline with the reply, so text
appears the instant the model returns it and audio catches up. Making a player wait
on synthesis before they can read an answer would undo the latency work in Phase 4.

Voice ids are data, not constants. A Persona carries its own, an NPC carries theirs,
and this module only resolves and calls — so a host backend that owns persona
identity can supply real per-persona voices without touching game code.

Output is cached by (voice, model, text) because ElevenLabs bills per character and
the persona repeats a lot of narration across a session.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import httpx

from .. import config

log = logging.getLogger(__name__)

AUDIO_ROOT = Path(__file__).resolve().parent.parent / "static" / "audio"


def available() -> bool:
    return config.TTS_ENABLED


def voice_for_persona(persona) -> str:
    """A persona's own voice if it has one, otherwise the configured default."""
    return (persona.voice_id or "").strip() or config.PERSONA_VOICE_ID


def voice_for_npc(npc) -> str:
    return (getattr(npc, "voice_id", "") or "").strip() or config.NPC_VOICE_ID


def _cache_path(text: str, voice_id: str) -> Path:
    digest = hashlib.sha256(
        f"{voice_id}|{config.TTS_MODEL_ID}|{text}".encode("utf-8")
    ).hexdigest()[:20]
    return AUDIO_ROOT / f"{digest}.mp3"


def _clean(text: str) -> str:
    """Strip the few characters that get read aloud as noise."""
    out = text.replace("—", ", ").replace("…", "...").replace("*", "")
    return " ".join(out.split())[: config.TTS_MAX_CHARS]


async def speak(text: str, voice_id: str) -> str | None:
    """Synthesize and return a served URL, or None if voice is unavailable.

    Never raises: a missing voice line must not break the turn that produced it.
    """
    if not available() or not text.strip() or not voice_id:
        return None

    body = _clean(text)
    dest = _cache_path(body, voice_id)
    if dest.exists():
        return config.static_url("audio", dest.name)

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{config.ELEVENLABS_BASE}/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": config.ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                },
                params={"output_format": config.TTS_OUTPUT_FORMAT},
                json={"text": body, "model_id": config.TTS_MODEL_ID},
                timeout=60,
            )
            if r.status_code == 401:
                log.error(
                    "ElevenLabs rejected the API key (401). Voice is disabled for this "
                    "run; the game continues silently."
                )
                return None
            if r.status_code >= 400:
                log.warning("ElevenLabs %s: %s", r.status_code, r.text[:200])
                return None

            AUDIO_ROOT.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            return config.static_url("audio", dest.name)
    except Exception as e:
        log.warning("TTS failed (%s: %s); continuing without audio.", type(e).__name__, e)
        return None
