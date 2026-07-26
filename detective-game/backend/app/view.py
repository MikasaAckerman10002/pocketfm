"""The redaction boundary.

`to_public` is the only function permitted to read a GameCase and produce something
a route may return. If you find yourself adding a field here, ask whether the player
is allowed to know it.

Deliberately omitted:
  - Room.clue_ids / any clue count  -> would let the client count remaining clues.
  - Hotspot.clue_ids                -> would reveal via the DOM which objects matter.
  - Clue.unlock_hint / keywords     -> would hand over the answers to the questioning.
  - solution, timeline, npc.knowledge, npc.secrets -> the case itself.
"""

from __future__ import annotations

from .models import (
    AccusationOptions,
    GameCase,
    GameState,
    Persona,
    PublicClue,
    PublicHotspot,
    PublicPersona,
    PublicRoom,
    PublicView,
)
from .store import Session


def to_public(
    case: GameCase, state: GameState, persona: Persona, images_pending: bool = False
) -> PublicView:
    rooms = [
        PublicRoom(
            id=room.id,
            name=room.name,
            image_url=room.image_url,
            locked=room.id not in state.rooms_unlocked,
            hotspots=[
                PublicHotspot(
                    id=hs.id,
                    kind=hs.kind,
                    label=hs.label,
                    x=hs.x,
                    y=hs.y,
                    w=hs.w,
                    h=hs.h,
                )
                for hs in room.hotspots
            ],
        )
        for room in case.rooms
    ]

    # Preserve discovery order so the clue tray reads as a running case file.
    discovered = [
        PublicClue(id=c.id, name=c.name, text=c.text)
        for cid in state.discovered_clue_ids
        if (c := case.clue(cid)) is not None
    ]

    return PublicView(
        case_id=case.id,
        title=case.title,
        setting=case.setting,
        victim=case.victim,
        public_setup=case.public_setup,
        persona=PublicPersona(
            id=persona.id,
            name=persona.name,
            tagline=persona.tagline,
            visual_style=persona.visual_style,
            accent_color=persona.accent_color,
        ),
        rooms=rooms,
        current_room=state.current_room,
        discovered_clues=discovered,
        npc_trust=dict(state.npc_trust),
        accusation_options=AccusationOptions(
            suspects=[n.name for n in case.npcs],
            motives=list(case.motive_options),
            weapons=list(case.weapon_options),
        ),
        solved=state.solved,
        images_pending=images_pending,
    )


def view_of(session: Session) -> PublicView:
    return to_public(
        session.case, session.state, session.persona, session.images_pending
    )
