"""ElevenLabs Speech-to-Text integration."""

import json
import mimetypes
import os
import uuid
from urllib import request

from dotenv import load_dotenv

from services.llm import LLMConfigurationError


load_dotenv()


def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Transcribe audio bytes to text using ElevenLabs STT."""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise LLMConfigurationError(
            "ELEVENLABS_API_KEY is not configured. Add it to your environment before starting the API."
        )

    boundary = f"----BobBoundary{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="model_id"\r\n\r\n',
            b"scribe_v1\r\n",
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode(),
            audio_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    req = request.Request(
        url="https://api.elevenlabs.io/v1/speech-to-text",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "xi-api-key": api_key,
        },
        method="POST",
    )

    with request.urlopen(req) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("text", "").strip()
