"""Environment configuration. Keys come from backend/.env, never from source."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}

# Sub-path the app is served under, e.g. "/detective" when mounted inside a
# larger site. Leave empty when it owns the root.
_root = os.environ.get("ROOT_PATH", "").strip().strip("/")
ROOT_PATH = f"/{_root}" if _root else ""





def static_url(*parts: str) -> str:
    """URL for a file we serve ourselves, correct under any mount point."""
    tail = "/".join(p.strip("/") for p in parts if p)
    return f"{ROOT_PATH}/static/{tail}"


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Verified live against this key on 2026-07-25: gemini-2.5-flash returns 404
# "no longer available to new users" even though models.list() still reports it.
#
# gemini-3.5-flash over gemini-3.6-flash on measured latency for a full case JSON:
# 3.6 spends ~4.7k thinking tokens and takes 36.5s, and rejects thinking_budget=0
# with a 400. 3.5 with thinking off produces an equally playable case in 11.5s.
TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.5-flash")

# NPC dialogue runs on a different model from case generation, for two reasons.
# Quota is per-model on the free tier (gemini-3.5-flash allows only 20 requests), and
# every NPC turn costs one call, so a single playthrough would exhaust the same pool
# case generation needs. Dialogue also wants speed over depth: flash-lite answered a
# trivial prompt in 0.9s against 1.8s for the larger models.
NPC_MODEL = os.environ.get("GEMINI_NPC_MODEL", "gemini-3.1-flash-lite")

# Groq. Preferred for text: the Gemini free tier allows 20 requests per model per day,
# and NPC dialogue spends one per turn, so a single playthrough exhausts it. Groq is
# also markedly faster, which matters most for the per-turn call.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_BASE = os.environ.get("GROQ_BASE", "https://api.groq.com/openai/v1")
# Benchmarked against both real workloads on 2026-07-25. For case generation
# llama-3.3-70b-versatile was the only candidate that produced a playable case (6.0s);
# gpt-oss-120b omitted required fields and gpt-oss-20b, qwen3.6-27b and
# llama-3.1-8b-instant all failed JSON validation. It also answers an NPC turn in
# 1.54s, so one model covers both roles.
GROQ_CASE_MODEL = os.environ.get("GROQ_CASE_MODEL", "llama-3.3-70b-versatile")
# Same model as case generation, on measurement. Splitting roles across models to get
# separate token-per-minute pools backfired: gpt-oss-20b caps at 8k TPM against
# llama-3.3-70b's 12k, so the "cheaper" model ran out sooner. In a real game the two
# roles barely overlap anyway - one case call, then dialogue.
GROQ_NPC_MODEL = os.environ.get("GROQ_NPC_MODEL", "llama-3.3-70b-versatile")

# Longest pause worth taking to rescue a rate-limited call before dropping to the stub.
GROQ_MAX_RETRY_WAIT = float(os.environ.get("GROQ_MAX_RETRY_WAIT", "12"))

# --- Hotspot detection (OpenRouter) ---------------------------------------
# Locating the clickable things in the finished art, so the boxes sit on the objects
# instead of near them. Measured mean IoU against boxes read by eye:
#   nvidia/nemotron-nano-12b-v2-vl:free              0.94  free
#   nvidia/nemotron-3-nano-omni-30b-a3b-reasoning    0.90  free, roughly twice as fast
#   google/gemma-4-26b-a4b-it:free                   0.89  free
#   gemini-3.5-flash                                 0.91  but only 20 calls/day
#   qwen/qwen3.6-27b                                 0.13  misses standing people
# The free Nemotron VL model beats Gemini outright, so detection costs nothing and has
# no daily ceiling. Free endpoints do get rate-limited, so this is a fallback chain
# tried in order; if every one fails the written coordinates stand.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE = os.environ.get("OPENROUTER_BASE", "https://openrouter.ai/api/v1")
VISION_MODELS = [
    m.strip()
    for m in os.environ.get(
        "VISION_MODELS",
        "nvidia/nemotron-nano-12b-v2-vl:free,"
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free,"
        "google/gemma-4-26b-a4b-it:free",
    ).split(",")
    if m.strip()
]
VISION_TIMEOUT = float(os.environ.get("VISION_TIMEOUT", "90"))
VISION_ENABLED = not _flag("DISABLE_VISION")

# --- Voice (ElevenLabs) ---------------------------------------------------
# Voice ids are per-character, not global. This engine treats them as data: a Persona
# carries its own voice_id, and an NPC carries theirs, so the host backend that owns
# persona identities can supply real ids per persona without touching this code.
# The values below are placeholders until that mapping exists.
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_BASE = os.environ.get("ELEVENLABS_BASE", "https://api.elevenlabs.io/v1")
PERSONA_VOICE_ID = os.environ.get("PERSONA_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
NPC_VOICE_ID = os.environ.get("NPC_VOICE_ID", "pFZP5JQG7iQjIQuC4Bku")
# flash is the low-latency model; dialogue is spoken as it appears, so latency wins.
TTS_MODEL_ID = os.environ.get("TTS_MODEL_ID", "eleven_flash_v2_5")
TTS_OUTPUT_FORMAT = os.environ.get("TTS_OUTPUT_FORMAT", "mp3_44100_128")
# ElevenLabs bills per character, so keep a hard ceiling on any single utterance.
TTS_MAX_CHARS = int(os.environ.get("TTS_MAX_CHARS", "700"))
TTS_ENABLED = bool(ELEVENLABS_API_KEY) and not _flag("DISABLE_TTS")

# auto | groq | gemini
TEXT_PROVIDER = os.environ.get("TEXT_PROVIDER", "auto").strip().lower()
IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")

# Room art. Google's image models return 429 RESOURCE_EXHAUSTED on this free-tier key,
# so nanobananaapi.ai (a paid third-party Nano Banana proxy) is the primary provider.
# It is task-based: POST for a taskId, then poll until it reports success.
NANOBANANA_API_KEY = os.environ.get("NANOBANANA_API_KEY", "").strip()
NANOBANANA_BASE = os.environ.get(
    "NANOBANANA_BASE", "https://api.nanobananaapi.ai/api/v1/nanobanana"
)

# auto | nanobanana | gemini | off  ("off" keeps the Phase 1 colour plates)
IMAGE_PROVIDER = os.environ.get("IMAGE_PROVIDER", "auto").strip().lower()

# The older /generate endpoint returns whatever ratio it feels like — measured 1024x1024
# on five of six calls and 1344x768 on the sixth, with no request parameter changing it.
# /generate-2 takes aspectRatio explicitly, which matters because hotspot rectangles are
# normalized over a 16:9 frame and a square image would crop them onto the wrong content.
IMAGE_ASPECT_RATIO = os.environ.get("IMAGE_ASPECT_RATIO", "16:9")
# 1K, not 2K. Measured: 2K returns 2752x1536 at 2.8MB after 80s, which would put
# click-to-playable near 95s and make three rooms an 8MB download. These are
# background plates behind a hotspot layer, not art the player inspects closely.
IMAGE_RESOLUTION = os.environ.get("IMAGE_RESOLUTION", "1K")
IMAGE_FORMAT = os.environ.get("IMAGE_FORMAT", "jpg").lower()

IMAGE_POLL_SECONDS = float(os.environ.get("IMAGE_POLL_SECONDS", "2.5"))
IMAGE_TIMEOUT_SECONDS = float(os.environ.get("IMAGE_TIMEOUT_SECONDS", "150"))
# How long /api/case/new waits for room one before answering. The rest keep going in
# the background, so this bounds the click-to-playable time, not total generation.
FIRST_ROOM_WAIT_SECONDS = float(os.environ.get("FIRST_ROOM_WAIT_SECONDS", "60"))


def image_provider() -> str:
    if IMAGE_PROVIDER != "auto":
        return IMAGE_PROVIDER
    if NANOBANANA_API_KEY:
        return "nanobanana"
    if GEMINI_API_KEY:
        return "gemini"
    return "off"

# DISABLE_LLM turns off every model call, not just case generation. It previously
# gated only the case, which let verify.py make live NPC calls and made a gate that
# is supposed to be deterministic depend on what a model felt like saying.
LLM_DISABLED = _flag("DISABLE_LLM")

# Pins the case to the fixture while leaving NPC dialogue live. Needed because
# verify_npc.py wants a deterministic case and real conversation; using DISABLE_LLM
# for that made the whole NPC gate run against the stub and pass without testing
# anything.
FORCE_FIXTURE_CASE = _flag("FORCE_FIXTURE_CASE")

# With no provider the engine falls back to the Phase 1 fixture and the keyword stub,
# so the demo still runs.
USE_LLM = bool(GEMINI_API_KEY or GROQ_API_KEY) and not LLM_DISABLED
