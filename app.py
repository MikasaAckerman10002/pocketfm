"""FastAPI entry point for the AI Character backend."""

import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import APIConnectionError, APIError, AuthenticationError, RateLimitError
from pydantic import BaseModel, ConfigDict, Field

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
