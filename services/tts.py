"""ElevenLabs Text-to-Speech integration."""

import json
import os
from urllib import request

from dotenv import load_dotenv

from services.llm import LLMConfigurationError


TTS_VOICE = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")

load_dotenv()


def tts_bytes(text: str, voice_id: str = TTS_VOICE) -> bytes:
    """Convert text to MP3 audio bytes using ElevenLabs TTS."""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise LLMConfigurationError(
            "ELEVENLABS_API_KEY is not configured. Add it to your environment before starting the API."
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
