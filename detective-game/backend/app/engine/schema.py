"""What the LLM is asked to produce.

Deliberately separate from models.GameCase. The engine owns fields the model should
never invent — hotspot ids, voice ids, image_url — so they are absent here and
assigned during conversion. Gemini's structured output also dislikes Optional and
dict types, which this shape avoids entirely (objects use npc_name="").
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class GenClue(BaseModel):
    id: str
    name: str
    text: str
    unlock_hint: str
    keywords: list[str]


class GenHotspot(BaseModel):
    kind: Literal["npc", "object"]
    label: str
    npc_name: str  # "" for objects
    x: float
    y: float
    w: float
    h: float
    clue_ids: list[str]


class GenRoom(BaseModel):
    id: str
    name: str
    image_prompt: str
    hotspots: list[GenHotspot]
    clue_ids: list[str]


class GenNPC(BaseModel):
    name: str
    role: str
    knowledge: list[str]
    secrets: list[str]


class GenSolution(BaseModel):
    killer: str
    motive: str
    weapon: str


class GeneratedCase(BaseModel):
    title: str
    setting: str
    victim: str
    public_setup: str
    timeline: list[str]
    npcs: list[GenNPC]
    clues: list[GenClue]
    rooms: list[GenRoom]
    motive_options: list[str]
    weapon_options: list[str]
    solution: GenSolution
