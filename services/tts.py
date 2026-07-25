"""ElevenLabs Text-to-Speech integration."""

import json
import os
from pathlib import Path
from urllib import request

from dotenv import load_dotenv, dotenv_values

from services.llm import LLMConfigurationError

load_dotenv(override=True)

TTS_VOICE = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")

# Read the API key once at import time — dotenv_values reads directly from the
# .env file so it is never affected by os.environ caching or load order issues.
_ENV_FILE = Path(__file__).parent.parent / ".env"
_env_values = dotenv_values(_ENV_FILE) if _ENV_FILE.exists() else {}


def _get_api_key() -> str:
    """Return the ElevenLabs API key, checking every possible source."""
    # 1. Already in os.environ (set externally or by a previous load_dotenv)
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    # 2. Read directly from .env file values (bypasses os.environ caching)
    key = _env_values.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    return ""


def tts_bytes(text: str, voice_id: str = TTS_VOICE) -> bytes:
    """Convert text to MP3 audio bytes using ElevenLabs TTS."""
    api_key = _get_api_key()
    if not api_key:
        raise LLMConfigurationError(
            "ELEVENLABS_API_KEY is not configured. Add it to your .env file."
        )

    body = json.dumps(
        {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "output_format": "mp3_44100_128",
        }
    ).encode("utf-8")
    req = request.Request(
        url=f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        data=body,
        headers={
            "Content-Type": "application/json",
            "xi-api-key": api_key,
        },
        method="POST",
    )

    with request.urlopen(req) as response:
        return response.read()
