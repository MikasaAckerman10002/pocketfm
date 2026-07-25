"""FastAPI entry point for the AI Character backend."""

import base64
import json
import os
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

# Load .env FIRST — before any service module is imported so every os.getenv
# call across the entire app sees the correct values.
from dotenv import load_dotenv
load_dotenv(override=True)

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import APIConnectionError, APIError, AuthenticationError, RateLimitError
from pydantic import BaseModel, ConfigDict, Field
from typing import AsyncIterator, List

from services.characters import Character, get_character, list_characters
from services.llm import LLMConfigurationError, LLMResponseError, generate_response
from services.memory import (
    add_message,
    authenticate_user,
    clear_memory,
    create_user,
    get_long_term_memory,
    get_profile,
    get_short_term_memory,
    init_db,
    save_long_term_memory,
    update_user_profile,
)
from services.stt import transcribe
from services.tts import tts_bytes


app = FastAPI(title="AI Character API", version="0.6.0")
init_db()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
app.mount("/posters", StaticFiles(directory="posters"), name="posters")


class UserProfile(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=120)
    gender: str = Field(default="")
    basics: str = Field(default="", max_length=500)


class AuthRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=3, max_length=200)
    name: str = Field(default="Guest", min_length=1, max_length=120)
    gender: str = Field(default="")
    basics: str = Field(default="", max_length=500)


class AuthResponse(BaseModel):
    user_id: str
    email: str
    name: str
    gender: str
    basics: str


def _openai_http_errors(error: Exception) -> HTTPException:
    if isinstance(error, AuthenticationError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="The language model service could not authenticate.")
    if isinstance(error, RateLimitError):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="The language model service is busy. Please try again shortly.")
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="The language model service is temporarily unavailable.")


def _get_character_or_404(character_id: str) -> Character:
    character = get_character(character_id)
    if not character:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found.")
    return character


def _memory_prompt(profile: dict, character_id: str) -> str:
    short_term = get_short_term_memory(profile["id"], character_id) if profile else []
    long_term = get_long_term_memory(profile["id"], character_id) if profile else ""
    return (
        f"User profile: {json.dumps(profile)}\n"
        f"Short-term memory: {json.dumps(short_term)}\n"
        f"Long-term memory: {long_term}\n"
        "Only use memories for this specific character."
    )


def _update_memories(user_id: str, character_id: str, user_text: str, reply: str) -> None:
    add_message(user_id, character_id, "user", user_text)
    add_message(user_id, character_id, "assistant", reply)
    short_term = get_short_term_memory(user_id, character_id)
    recent_user_points = [item["content"] for item in short_term if item["role"] == "user"][-3:]
    if recent_user_points:
        save_long_term_memory(user_id, character_id, " | ".join(recent_user_points)[:1000])


@app.get("/")
def frontend_index() -> FileResponse:
    return FileResponse(Path("frontend/index.html"))


@app.get("/characters")
def characters() -> list[dict]:
    return [character.model_dump() for character in list_characters()]


@app.post("/signup", response_model=AuthResponse)
def signup(request: AuthRequest) -> AuthResponse:
    user_id = str(uuid4())
    try:
        user = create_user(user_id, request.email, request.password, request.name, request.gender, request.basics)
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists.") from error
    return AuthResponse(user_id=user["id"], email=user["email"], name=user["name"], gender=user["gender"], basics=user["basics"])


@app.post("/login", response_model=AuthResponse)
def login(request: AuthRequest) -> AuthResponse:
    user = authenticate_user(request.email, request.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    return AuthResponse(user_id=user["id"], email=user["email"], name=user["name"], gender=user["gender"], basics=user["basics"])


@app.post("/profiles", response_model=UserProfile)
def save_user_profile(profile: UserProfile) -> UserProfile:
    user = update_user_profile(profile.user_id, profile.name, profile.gender, profile.basics)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return UserProfile(user_id=user["id"], name=user["name"], gender=user["gender"], basics=user["basics"])


@app.post("/voice-chat")
async def voice_chat(audio: UploadFile = File(...), user_id: str = "default", character_id: str = "barbie") -> StreamingResponse:
    character = _get_character_or_404(character_id)
    profile = get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    raw = await audio.read()
    filename = audio.filename or "audio.webm"
    try:
        transcript = transcribe(raw, filename)
        reply = generate_response(
            transcript,
            get_short_term_memory(user_id, character_id),
            f"{character.prompt}\n\n{_memory_prompt(profile, character_id)}",
        )
        response_audio = tts_bytes(reply, character.voice_id)
    except LLMConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error
    except (AuthenticationError, RateLimitError, APIConnectionError, APIError) as error:
        raise _openai_http_errors(error) from error
    except LLMResponseError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="The language model service returned an invalid response.") from error
    _update_memories(user_id, character_id, transcript, reply)
    return StreamingResponse(
        iter([response_audio]),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f"inline; filename={character.id}-reply.mp3",
            "X-Transcript": quote(transcript, safe=""),
            "X-Reply": quote(reply, safe=""),
            "X-Character-Id": character_id,
        },
    )


@app.delete("/session/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def clear_session(user_id: str, character_id: str = "barbie") -> None:
    clear_memory(user_id, character_id)


class DebateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    character_ids: List[str] = Field(..., min_length=2)
    rounds: int = Field(default=2, ge=1, le=4)


def _build_instruction(
    topic: str,
    round_turns: list[dict],
    rolling_summary: str,
    char_name: str,
    position_anchor: str,
) -> str:
    """Build the per-turn debate instruction for one character.

    Context (all bounded):
    - ``position_anchor`` — this character's own round-1 argument, injected every turn
                            so they stay consistent and never contradict themselves
    - ``rolling_summary`` — moderator's compact recap of completed rounds
    - ``round_turns``     — full transcript of THIS round so far (resets every round)
    """
    if not round_turns and not position_anchor:
        # Very first speaker of the entire debate
        return (
            f"You are the first to speak in a debate on: \"{topic}\".\n"
            "State your opening position clearly and confidently in character. Under 80 words."
        )

    context_parts: list[str] = []

    # Anchor: remind the character of their own stated position
    if position_anchor:
        context_parts.append(
            f"YOUR POSITION (what you said in round 1 — stay consistent with this):\n"
            f"  \"{position_anchor}\""
        )

    if rolling_summary:
        context_parts.append(f"Summary of previous rounds:\n{rolling_summary}")

    if round_turns:
        transcript = "\n".join(f"  {t['name']}: {t['argument']}" for t in round_turns)
        context_parts.append(f"This round so far:\n{transcript}")

    last = round_turns[-1] if round_turns else None
    context = "\n\n".join(context_parts)

    reaction = (
        f"React to what has been said — you can push back on {last['name']}'s point, "
        f"agree with someone, or steer the debate. "
        if last else
        "State your opening position on this topic. "
    )

    return (
        f"You are debating the topic: \"{topic}\".\n\n"
        f"{context}\n\n"
        f"Now it is YOUR turn as {char_name}.\n"
        f"{reaction}"
        f"Speak naturally, as if mid-conversation. "
        f"Do NOT open with someone's name as a formal address. "
        f"Do NOT start with 'I'. "
        f"IMPORTANT: Do not contradict your own position stated above — you may refine it, "
        f"but your core stance must stay the same. "
        f"Under 80 words. Stay fully in character."
    )


def _moderator_pick_with_intro(
    topic: str, round_turns: list[dict], remaining: list[str]
) -> tuple[str, str]:
    """Decide who speaks next and return (name, spoken_intro).

    The spoken intro is a short sentence the moderator says aloud to hand
    over to the next speaker — e.g. "Victor, you have been quiet. What is
    your take?" Returns a fallback if the LLM call fails.
    """
    transcript = "\n".join(f"  {t['name']}: {t['argument']}" for t in round_turns)
    names_str = ", ".join(remaining)
    system = (
        "You are Alex, a debate moderator. "
        "Reply in EXACTLY this format — two lines, nothing else:\n"
        "NEXT: <name>\n"
        "INTRO: <sentence of 10 words or fewer handing the floor to them>\n"
        f"Choose NEXT from: {names_str}. "
        "The INTRO must be a plain handover, e.g. 'Over to Victor.' or 'Francis, your thoughts?'"
    )
    try:
        raw = generate_response(
            f"Topic: \"{topic}\"\n\nExchange:\n{transcript}\n\nWho speaks next?",
            None,
            system,
            max_tokens=40,
        )
        next_name = remaining[0]
        intro = ""
        for line in raw.splitlines():
            line = line.strip()
            if line.upper().startswith("NEXT:"):
                candidate = line[5:].strip().rstrip(".,!?")
                for name in remaining:
                    if name.lower() in candidate.lower() or candidate.lower() in name.lower():
                        next_name = name
                        break
            elif line.upper().startswith("INTRO:"):
                intro = line[6:].strip()
        return next_name, intro or f"Over to {next_name}."
    except Exception:
        return remaining[0], f"Over to {remaining[0]}."


def _moderator_summary(topic: str, round_turns: list[dict], round_num: int) -> str:
    """One-sentence-per-speaker summary spoken by the moderator to close the round."""
    names = [t["name"] for t in round_turns]
    transcript = "\n".join(f"  {t['name']}: {t['argument']}" for t in round_turns)
    system = (
        "You are Alex, a concise debate moderator. "
        f"Write EXACTLY {len(names)} short sentences — one per speaker — "
        "each stating that speaker's main point in plain English. "
        "Total reply must be under 50 words. No names as labels, weave them in naturally. "
        "No headings, no bullet points, no extra commentary."
    )
    try:
        return generate_response(
            f"Summarise round {round_num} on \"{topic}\":\n{transcript}",
            None,
            system,
            max_tokens=80,
        )
    except Exception:
        return " ".join(f"{t['name']} argued {t['argument'][:40]}…" for t in round_turns)


def _tts_safe(text: str, voice_id: str) -> str | None:
    """Generate TTS and return base64 string, or None on failure."""
    try:
        return base64.b64encode(tts_bytes(text, voice_id)).decode("ascii")
    except Exception as exc:
        print(f"[TTS] failed for voice={voice_id}: {exc}")
        return None

# Moderator voice — Daniel (Steady Broadcaster), falls back to env override
_MODERATOR_VOICE = os.getenv("MODERATOR_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")


async def _debate_event_stream(req: DebateRequest) -> AsyncIterator[str]:
    """Stream SSE events: moderator intros, character turns, round summaries, done."""
    char_map: dict[str, object] = {}
    for cid in req.character_ids:
        char = get_character(cid)
        if char is None:
            yield f"event: error\ndata: {json.dumps({'detail': f'Character {cid!r} not found.'})}\n\n"
            return
        char_map[char.name] = char

    rolling_summary: str = ""
    # Stores each character's round-1 argument — injected into all later prompts
    # so they never contradict their opening position
    position_anchors: dict[str, str] = {}

    for round_num in range(req.rounds):
        yield f"event: round\ndata: {json.dumps({'round': round_num + 1})}\n\n"

        round_turns: list[dict] = []
        remaining: list[str] = list(char_map.keys())

        while remaining:
            # ── Moderator decides who goes next (with a spoken intro) ──
            if len(remaining) == len(char_map) and not round_turns:
                # Very first turn of the whole debate — no intro needed
                next_name = remaining[0]
                intro_text: str | None = None
            elif len(remaining) == 1:
                next_name = remaining[0]
                intro_text = None
            else:
                next_name, intro_text = _moderator_pick_with_intro(
                    req.topic, round_turns, remaining
                )

            # ── Emit moderator_intro before the speaker if we have one ──
            if intro_text:
                intro_audio = _tts_safe(intro_text, _MODERATOR_VOICE)
                yield (
                    f"event: moderator_intro\n"
                    f"data: {json.dumps({'text': intro_text, 'audio_b64': intro_audio})}\n\n"
                )

            remaining.remove(next_name)
            char = char_map[next_name]

            # ── Build instruction — include this character's anchor if available ──
            instruction = _build_instruction(
                req.topic, round_turns, rolling_summary, next_name,
                position_anchors.get(next_name, ""),
            )
            prompt = f"{char.prompt}\n\n{instruction}"

            # ── Generate character argument ───────────────────────
            try:
                argument = generate_response(
                    f"Respond now as {next_name}.",
                    None,
                    prompt,
                )
            except (LLMConfigurationError, LLMResponseError) as exc:
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
                return
            except (AuthenticationError, RateLimitError, APIConnectionError, APIError) as exc:
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
                return

            round_turns.append({"name": next_name, "argument": argument})

            # Save round-1 argument as this character's position anchor
            if round_num == 0 and next_name not in position_anchors:
                position_anchors[next_name] = argument

            # ── TTS for character ─────────────────────────────────
            audio_b64 = _tts_safe(argument, char.voice_id)

            # ── Emit turn event ───────────────────────────────────
            yield (
                f"event: turn\n"
                f"data: {json.dumps({'round': round_num + 1, 'character_id': char.id, 'character_name': next_name, 'avatar': char.avatar, 'argument': argument, 'audio_b64': audio_b64})}\n\n"
            )

        # ── End of round: moderator gives a spoken summary ───────
        summary_text = _moderator_summary(req.topic, round_turns, round_num + 1)
        summary_audio = _tts_safe(summary_text, _MODERATOR_VOICE)
        yield (
            f"event: moderator_summary\n"
            f"data: {json.dumps({'round': round_num + 1, 'text': summary_text, 'audio_b64': summary_audio})}\n\n"
        )

        # Update rolling summary for next round's context
        rolling_summary = (
            f"{rolling_summary} {summary_text}".strip() if rolling_summary else summary_text
        )

    yield f"event: done\ndata: {{}}\n\n"


@app.post("/debate/stream")
async def debate_stream(req: DebateRequest) -> StreamingResponse:
    """Stream debate turns as Server-Sent Events. Each turn includes LLM text + TTS audio."""
    return StreamingResponse(
        _debate_event_stream(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
