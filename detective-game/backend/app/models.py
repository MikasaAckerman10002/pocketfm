"""Data model.

The split that matters: everything under "Hidden" lives only on the server and is
never serialized to the client. Everything under "Public" is what the player is
allowed to know. `to_public` is the single crossing point between them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Hidden — server-only. Never returned from a route.
# --------------------------------------------------------------------------


class Clue(BaseModel):
    id: str
    name: str
    text: str
    # What line of questioning surfaces this clue. Phase 1 keyword-matches against
    # `keywords`; Phase 4 hands `unlock_hint` to the LLM as the judgment criterion.
    unlock_hint: str
    keywords: list[str] = Field(default_factory=list)


class Hotspot(BaseModel):
    id: str
    kind: Literal["npc", "object"]
    label: str
    # Normalized 0-1 over the scene image so hotspots land correctly at any viewport.
    x: float
    y: float
    w: float
    h: float
    npc_name: str | None = None
    clue_ids: list[str] = Field(default_factory=list)


class Room(BaseModel):
    id: str
    name: str
    image_prompt: str
    image_url: str | None = None
    hotspots: list[Hotspot] = Field(default_factory=list)
    clue_ids: list[str] = Field(default_factory=list)


class NPC(BaseModel):
    name: str
    role: str
    voice_id: str
    knowledge: list[str] = Field(default_factory=list)
    # What they admit only under pressure — the payload for the "are you lying?" beat.
    secrets: list[str] = Field(default_factory=list)


class Solution(BaseModel):
    killer: str
    motive: str
    weapon: str


class GameCase(BaseModel):
    """Immutable hidden truth. Constructed in store.py, never leaves the server."""

    id: str
    title: str
    setting: str
    victim: str
    # The only narrative the persona intro is allowed to see.
    public_setup: str
    timeline: list[str] = Field(default_factory=list)
    rooms: list[Room]
    npcs: list[NPC]
    clues: list[Clue]
    # Accusation menus need plausible decoys alongside the true answer.
    motive_options: list[str]
    weapon_options: list[str]
    solution: Solution

    def clue(self, clue_id: str) -> Clue | None:
        return next((c for c in self.clues if c.id == clue_id), None)

    def room(self, room_id: str) -> Room | None:
        return next((r for r in self.rooms if r.id == room_id), None)

    def npc(self, name: str) -> NPC | None:
        return next((n for n in self.npcs if n.name == name), None)

    def find_hotspot(self, hotspot_id: str) -> tuple[Room, Hotspot] | None:
        for room in self.rooms:
            for hs in room.hotspots:
                if hs.id == hotspot_id:
                    return room, hs
        return None


# --------------------------------------------------------------------------
# Mutable progress
# --------------------------------------------------------------------------


class Exchange(BaseModel):
    role: Literal["player", "npc"]
    text: str


class GameState(BaseModel):
    discovered_clue_ids: list[str] = Field(default_factory=list)
    npc_trust: dict[str, int] = Field(default_factory=dict)
    rooms_unlocked: list[str] = Field(default_factory=list)
    current_room: str = ""
    # Each NPC's own log only — never another NPC's.
    npc_conversation_history: dict[str, list[Exchange]] = Field(default_factory=dict)
    # One-line condensation of exchanges that aged out of the cap.
    history_summary: dict[str, str] = Field(default_factory=dict)
    # How many times each object hotspot has been examined, so repeat looks rotate
    # narration instead of repeating verbatim.
    examine_counts: dict[str, int] = Field(default_factory=dict)
    solved: bool = False
    solved_correctly: bool | None = None


class Persona(BaseModel):
    id: str
    name: str
    tagline: str
    personality_prompt: str
    voice_id: str
    visual_style: str
    accent_color: str
    # Phase 1 canned narration. Phase 5 replaces these with LLM calls.
    intro_template: str
    clue_react_templates: list[str]
    examine_templates: list[str]
    win_template: str
    lose_template: str


# --------------------------------------------------------------------------
# Public — the only shapes a route may return.
# --------------------------------------------------------------------------


class PublicPersona(BaseModel):
    id: str
    name: str
    tagline: str
    visual_style: str
    accent_color: str


class PublicHotspot(BaseModel):
    # Deliberately no clue_ids: that would tell the DOM which objects matter.
    id: str
    kind: Literal["npc", "object"]
    label: str
    x: float
    y: float
    w: float
    h: float


class PublicRoom(BaseModel):
    # Deliberately no clue_ids and no unlock threshold: that would let the client
    # count how many clues remain in a room.
    id: str
    name: str
    image_url: str | None
    locked: bool
    hotspots: list[PublicHotspot]


class PublicClue(BaseModel):
    id: str
    name: str
    text: str


class AccusationOptions(BaseModel):
    suspects: list[str]
    motives: list[str]
    weapons: list[str]


class PublicView(BaseModel):
    case_id: str
    title: str
    setting: str
    victim: str
    public_setup: str
    persona: PublicPersona
    rooms: list[PublicRoom]
    current_room: str
    discovered_clues: list[PublicClue]
    npc_trust: dict[str, int]
    accusation_options: AccusationOptions
    solved: bool
    # True while room art is still generating in the background, so the client knows
    # to keep polling. Says nothing about the case itself.
    images_pending: bool = False


# --------------------------------------------------------------------------
# Route payloads
# --------------------------------------------------------------------------


class NewCaseRequest(BaseModel):
    persona_id: str


class NewCaseResponse(BaseModel):
    session_id: str
    view: PublicView
    intro: str


class SessionResponse(BaseModel):
    view: PublicView


class EnterRoomRequest(BaseModel):
    session_id: str
    room_id: str


class SpeakRequest(BaseModel):
    session_id: str
    text: str
    # Which character's voice. "npc" needs npc_name to pick that suspect's voice.
    speaker: Literal["persona", "npc"] = "persona"
    npc_name: str | None = None


class SpeakResponse(BaseModel):
    # None when voice is unavailable — the client just stays silent.
    audio_url: str | None = None


class AskRequest(BaseModel):
    session_id: str
    hotspot_id: str
    question: str


class AskResponse(BaseModel):
    speaker: str
    reply: str
    clue_unlocked: PublicClue | None = None
    trust_delta: int = 0
    persona_reaction: str | None = None
    room_unlocked: str | None = None
    view: PublicView


class SolveRequest(BaseModel):
    session_id: str
    suspect: str
    motive: str
    weapon: str


class SolveResponse(BaseModel):
    correct: bool
    narration: str
    # The only place solution fields are ever permitted to cross the boundary,
    # and only after the player has committed an accusation.
    truth: Solution
