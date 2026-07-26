"""In-memory session store. No Redis, no Postgres — hackathon scope.

This module owns every live `GameCase`. Nothing outside it should hold a reference
to one, and no route may return one. See view.py for the single crossing point.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException

from .models import GameCase, GameState, Persona

# Clues required in the current room before the next one unlocks.
CLUES_TO_UNLOCK = 2


@dataclass
class Session:
    id: str
    case: GameCase
    state: GameState
    persona: Persona
    # Background room-image tasks. Held so the event loop cannot collect them
    # mid-flight while the player is in room one.
    image_tasks: list[asyncio.Task[None]] = field(default_factory=list)

    @property
    def images_pending(self) -> bool:
        return any(not t.done() for t in self.image_tasks)


SESSIONS: dict[str, Session] = {}


def create_session(case: GameCase, persona: Persona) -> Session:
    first = case.rooms[0]
    state = GameState(
        current_room=first.id,
        rooms_unlocked=[first.id],
        npc_trust={n.name: 0 for n in case.npcs},
        npc_conversation_history={n.name: [] for n in case.npcs},
    )
    session = Session(id=uuid.uuid4().hex, case=case, state=state, persona=persona)
    SESSIONS[session.id] = session
    return session


def get_session(session_id: str) -> Session:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    return session


def maybe_unlock_next_room(session: Session) -> str | None:
    """Unlock the next room if the current one has yielded enough clues.

    Returns the newly unlocked room id, or None if nothing changed.
    """
    case, state = session.case, session.state
    room = case.room(state.current_room)
    if room is None:
        return None

    found = sum(1 for cid in room.clue_ids if cid in state.discovered_clue_ids)
    # A final room may hold fewer clues than the threshold; don't deadlock on it.
    needed = min(CLUES_TO_UNLOCK, len(room.clue_ids))
    if found < needed:
        return None

    index = case.rooms.index(room)
    if index + 1 >= len(case.rooms):
        return None

    nxt = case.rooms[index + 1]
    if nxt.id in state.rooms_unlocked:
        return None

    state.rooms_unlocked.append(nxt.id)
    return nxt.id
