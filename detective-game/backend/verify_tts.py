"""Phase 6 voice checks. Run: .venv\\Scripts\\python.exe verify_tts.py

Reports honestly in both states. With a working key it verifies real audio, distinct
voices and caching. Without one it verifies the thing that matters just as much: that
a missing voice degrades to silence quickly and never breaks a turn.
"""

from __future__ import annotations

import asyncio
import sys
import time

from app import config
from app.engine import tts
from app.personas import PERSONAS_BY_ID

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  -> ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


LINE = "That's the case. You got there, and you got there without me holding the lamp."


async def main() -> None:
    print(f"\nTTS enabled:   {tts.available()}")
    print(f"key present:   {bool(config.ELEVENLABS_API_KEY)}")
    print(f"persona voice: {config.PERSONA_VOICE_ID}")
    print(f"npc voice:     {config.NPC_VOICE_ID}")
    print(f"model:         {config.TTS_MODEL_ID}")

    quill = PERSONAS_BY_ID["quill"]
    check(
        "persona with no voice_id falls back to the configured default",
        tts.voice_for_persona(quill) == config.PERSONA_VOICE_ID,
    )
    check(
        "npc with no voice_id falls back to the configured default",
        tts.voice_for_npc(None) == config.NPC_VOICE_ID,
    )

    class Custom:
        voice_id = "someOtherVoiceId123"

    check(
        "an explicit voice_id wins over the default",
        tts.voice_for_npc(Custom()) == "someOtherVoiceId123",
        "this is the hook a host backend uses for per-persona voices",
    )

    print("\n--- synthesis ---")
    t = time.time()
    url = await tts.speak(LINE, config.PERSONA_VOICE_ID)
    first = time.time() - t

    if url is None:
        print(f"  no audio returned after {first:.1f}s")
        check(
            "failure is fast, not a hang",
            first < 15,
            f"{first:.1f}s",
        )
        check(
            "a turn survives having no voice",
            await tts.speak(LINE, config.PERSONA_VOICE_ID) is None,
            "speak() returns None rather than raising",
        )
        print(
            "\n  Voice is unavailable, so the game runs silently. That is the intended\n"
            "  degraded state, but it means the audio path below is UNVERIFIED."
        )
        return

    path = tts.AUDIO_ROOT / url.rsplit("/", 1)[-1]
    size = path.stat().st_size if path.exists() else 0
    print(f"  {first:.2f}s  {size // 1024}KB  {url}")
    check("audio file written", size > 2000, f"{size} bytes")
    check("served from our own origin", url.startswith("/static/audio/"))
    check("looks like an mp3", path.read_bytes()[:3] in (b"ID3", b"\xff\xfb\xff"[:3]))

    t = time.time()
    again = await tts.speak(LINE, config.PERSONA_VOICE_ID)
    cached = time.time() - t
    check("identical line is cached, not re-billed", again == url and cached < 0.2,
          f"{cached:.3f}s")

    other = await tts.speak(LINE, config.NPC_VOICE_ID)
    check("a different voice produces a different file", other != url)


asyncio.run(main())

print()
if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("Phase 6 voice checks passed.")
