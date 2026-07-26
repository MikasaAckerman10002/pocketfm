from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from ..config import FIRST_ROOM_WAIT_SECONDS
from ..engine import (
    case_gen,
    images as image_engine,
    npc as npc_engine,
    persona as persona_engine,
    tts as tts_engine,
)
from ..models import (
    AskRequest,
    AskResponse,
    EnterRoomRequest,
    NewCaseRequest,
    NewCaseResponse,
    PublicClue,
    PublicPersona,
    SessionResponse,
    SolveRequest,
    SolveResponse,
    SpeakRequest,
    SpeakResponse,
)
from ..personas import PERSONAS, PERSONAS_BY_ID
from ..store import create_session, get_session, maybe_unlock_next_room
from ..view import view_of

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/personas", response_model=list[PublicPersona])
async def list_personas() -> list[PublicPersona]:
    return [
        PublicPersona(
            id=p.id,
            name=p.name,
            tagline=p.tagline,
            visual_style=p.visual_style,
            accent_color=p.accent_color,
        )
        for p in PERSONAS
    ]


@router.post("/case/new", response_model=NewCaseResponse)
async def new_case(req: NewCaseRequest) -> NewCaseResponse:
    persona = PERSONAS_BY_ID.get(req.persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="Unknown persona.")

    case = await case_gen.generate_case(persona)
    session = create_session(case, persona)

    # Every room is requested at once, so total time is the slowest room rather than
    # the sum. We wait only for room one; the rest land while the player reads the
    # intro, which is what makes moving to room two feel instant.
    session.image_tasks = image_engine.start_generation(case)
    if session.image_tasks:
        try:
            await asyncio.wait_for(
                asyncio.shield(session.image_tasks[0]), timeout=FIRST_ROOM_WAIT_SECONDS
            )
        except asyncio.TimeoutError:
            # Room one keeps generating and will appear on a later poll; the player
            # starts on the colour plate rather than staring at a spinner.
            log.warning("Room one art exceeded %ss; starting anyway.", FIRST_ROOM_WAIT_SECONDS)

    return NewCaseResponse(
        session_id=session.id,
        view=view_of(session),
        intro=await persona_engine.intro(persona, case),
    )


@router.get("/session/{session_id}", response_model=SessionResponse)
async def read_session(session_id: str) -> SessionResponse:
    return SessionResponse(view=view_of(get_session(session_id)))


@router.post("/room/enter", response_model=SessionResponse)
async def enter_room(req: EnterRoomRequest) -> SessionResponse:
    session = get_session(req.session_id)
    if req.room_id not in session.state.rooms_unlocked:
        raise HTTPException(status_code=403, detail="That room is still locked.")
    session.state.current_room = req.room_id
    return SessionResponse(view=view_of(session))


@router.post("/hotspot/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    session = get_session(req.session_id)
    case, state = session.case, session.state

    found = case.find_hotspot(req.hotspot_id)
    if found is None:
        raise HTTPException(status_code=404, detail="No such hotspot.")
    room, hotspot = found
    if room.id not in state.rooms_unlocked:
        raise HTTPException(status_code=403, detail="That room is still locked.")

    if hotspot.kind == "npc":
        character = case.npc(hotspot.npc_name or "")
        if character is None:
            raise HTTPException(status_code=500, detail="Hotspot references a missing NPC.")

        turn = await npc_engine.ask_npc(session, character, hotspot, req.question)
        npc_engine.record_exchange(state, character.name, req.question, turn.reply)
        state.npc_trust[character.name] = (
            state.npc_trust.get(character.name, 0) + turn.trust_delta
        )
        speaker, reply, clue_id, trust_delta = (
            character.name,
            turn.reply,
            turn.clue_id,
            turn.trust_delta,
        )
    else:
        # Object hotspots are narrated by the persona; the first look yields the clue.
        pending = [
            c
            for cid in hotspot.clue_ids
            if (c := case.clue(cid)) is not None and c.id not in state.discovered_clue_ids
        ]
        clue = pending[0] if pending else None
        seen = state.examine_counts.get(hotspot.id, 0)
        reply = await persona_engine.examine(session.persona, hotspot, clue, seen)
        state.examine_counts[hotspot.id] = seen + 1
        speaker, clue_id, trust_delta = session.persona.name, (clue.id if clue else None), 0

    unlocked_clue = None
    persona_reaction = None
    room_unlocked = None

    if clue_id is not None and clue_id not in state.discovered_clue_ids:
        state.discovered_clue_ids.append(clue_id)
        clue = case.clue(clue_id)
        if clue is not None:
            unlocked_clue = PublicClue(id=clue.id, name=clue.name, text=clue.text)
            persona_reaction = await persona_engine.react_to_clue(
                session.persona, clue, len(state.discovered_clue_ids)
            )
        room_unlocked = maybe_unlock_next_room(session)

    return AskResponse(
        speaker=speaker,
        reply=reply,
        clue_unlocked=unlocked_clue,
        trust_delta=trust_delta,
        persona_reaction=persona_reaction,
        room_unlocked=room_unlocked,
        view=view_of(session),
    )


@router.post("/speak", response_model=SpeakResponse)
async def speak(req: SpeakRequest) -> SpeakResponse:
    """Synthesize a line that has already been shown to the player.

    Deliberately separate from the endpoints that produce the text. Speech takes about
    as long as the reply itself, and making the player wait to *read* an answer until
    it can be *spoken* would give back the latency won in Phase 4.
    """
    session = get_session(req.session_id)

    if req.speaker == "npc":
        character = session.case.npc(req.npc_name or "")
        voice = (
            tts_engine.voice_for_npc(character)
            if character
            else tts_engine.voice_for_npc(None)
        )
    else:
        voice = tts_engine.voice_for_persona(session.persona)

    return SpeakResponse(audio_url=await tts_engine.speak(req.text, voice))


@router.post("/solve", response_model=SolveResponse)
async def solve(req: SolveRequest) -> SolveResponse:
    session = get_session(req.session_id)
    solution = session.case.solution

    correct = (
        req.suspect == solution.killer
        and req.motive == solution.motive
        and req.weapon == solution.weapon
    )
    session.state.solved = True
    session.state.solved_correctly = correct

    return SolveResponse(
        correct=correct,
        narration=await persona_engine.ending(
            session.persona, session.case, solution, correct
        ),
        truth=solution,
    )
