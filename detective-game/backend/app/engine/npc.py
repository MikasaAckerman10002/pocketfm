"""NPC dialogue.

Phase 4: Gemini plays the character live. The keyword stub from Phase 1 is kept as
a fallback, so a failed or slow call degrades to a playable answer rather than an
error in the middle of an interrogation.

The thing that makes interrogation feel real is memory: every call receives that
NPC's own conversation log — never another NPC's — so the model can notice the
player circling back, catch its own earlier denial, and crack under repetition.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel

from ..models import NPC, Exchange, GameState, Hotspot
from ..store import Session
from . import llm

log = logging.getLogger(__name__)

# Keep the last N player+NPC pairs verbatim; condense anything older into one line.
MAX_EXCHANGES = 10
# How many of those pairs actually go into the prompt. Groq's free tier caps tokens
# per minute, and history is the only part of the prompt that grows without bound, so
# sending fewer turns directly buys more questions per minute.
HISTORY_IN_PROMPT = 6
# Repeated questioning cracks an NPC even without the right keyword (stub fallback).
PRESSURE_TURNS = 4


@dataclass
class NpcTurn:
    reply: str
    clue_id: str | None
    trust_delta: int


class NpcReply(BaseModel):
    reply: str
    # "" when the question did not earn anything.
    unlocks_clue_id: str
    trust_delta: int


SYSTEM = """You are playing one character being questioned in a detective game.

Rules you never break:
- Speak in first person, as the character, in 1-4 sentences. Never narrate as an
  author, never describe yourself in third person, never use markdown.
- You know only what your character knows. You have no idea who the killer is unless
  you are the killer.
- Never state the solution of the case outright, and never accuse another character
  with certainty.
- You are a person, not an information dispenser. You get bored, irritated, defensive
  or warmer depending on how you are treated.
- Reveal a hidden fact only when the player has genuinely earned it. Deflect otherwise
  — but deflect differently each time. Never repeat a previous answer word for word.
- Speak in plain, everyday English. Short sentences, common words, the way a real
  person actually talks. No literary or ornate phrasing. Many players are not native
  English speakers, and a suspect who talks like a novel is harder to read than to
  outwit."""


def _first_name(full: str) -> str:
    return full.split()[0] if full.split() else full


def record_exchange(state: GameState, npc_name: str, question: str, reply: str) -> None:
    """Append this turn and enforce the cap, condensing what falls off."""
    log_ = state.npc_conversation_history.setdefault(npc_name, [])
    log_.append(Exchange(role="player", text=question))
    log_.append(Exchange(role="npc", text=reply))

    limit = MAX_EXCHANGES * 2
    if len(log_) <= limit:
        return

    dropped = log_[:-limit]
    del log_[:-limit]

    # Older context still carries weight instead of vanishing.
    asked = [e.text for e in dropped if e.role == "player"]
    existing = state.history_summary.get(npc_name, "")
    line = (
        f"Earlier the player pressed {npc_name} on: "
        + "; ".join(a[:60] for a in asked[-4:])
        + "."
    )
    state.history_summary[npc_name] = (existing + " " + line).strip()


def turns_taken(state: GameState, npc_name: str) -> int:
    log_ = state.npc_conversation_history.get(npc_name, [])
    return sum(1 for e in log_ if e.role == "player")


def _transcript(state: GameState, npc_name: str) -> str:
    """This NPC's own history only. Another NPC's log must never appear here."""
    lines = []
    summary = state.history_summary.get(npc_name)
    if summary:
        lines.append(f"(earlier, condensed) {summary}")

    full = state.npc_conversation_history.get(npc_name, [])
    recent = full[-HISTORY_IN_PROMPT * 2 :]
    if len(full) > len(recent):
        lines.append(f"(…{(len(full) - len(recent)) // 2} earlier exchanges omitted)")
    for e in recent:
        speaker = "PLAYER" if e.role == "player" else "YOU"
        # Long replies of our own add tokens without adding much signal.
        text = e.text if len(e.text) < 320 else e.text[:320] + "…"
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines) if lines else "(this is the first thing they have said to you)"


def _prompt(
    session: Session, npc: NPC, pending: list, question: str, asked: int
) -> str:
    case, state = session.case, session.state
    trust = state.npc_trust.get(npc.name, 0)
    is_killer = npc.name == case.solution.killer

    if pending:
        clue_block = "\n".join(
            f'  - id "{c.id}": {c.text}\n    (reveal only if: {c.unlock_hint})'
            for c in pending
        )
    else:
        clue_block = "  (nothing left for you to reveal — just stay in character)"

    killer_block = (
        "You killed them. You must never confess, never admit guilt, and never name "
        "yourself. Deflect, minimise, and redirect. You may lie. If cornered on a "
        "specific fact you can concede that small fact while denying the killing."
        if is_killer
        else "You did not kill them. You have nothing to confess, though you may still "
        "have something small you would rather not admit."
    )

    return f"""THE CASE (public knowledge): {case.public_setup}

YOU ARE: {npc.name}, {npc.role}

WHAT YOU KNOW AND WILL SAY FREELY:
{chr(10).join(f"  - {k}" for k in npc.knowledge) or "  (nothing in particular)"}

WHAT YOU ARE HIDING (admit only under real pressure):
{chr(10).join(f"  - {s}" for s in npc.secrets) or "  (nothing)"}

{killer_block}

HOW YOU FEEL ABOUT THE PLAYER: trust score {trust}. They have questioned you {asked}
time(s) already. Low or negative trust means guarded and short. Higher trust means
more forthcoming.

FACTS YOU COULD GIVE UP, IF THE QUESTION EARNS IT:
{clue_block}

YOUR CONVERSATION WITH THEM SO FAR:
{_transcript(state, npc.name)}

THEY NOW SAY: "{question}"

Reply in character. Then decide:
- unlocks_clue_id: the id of a fact above, but ONLY if this question genuinely earned
  it, or if they have pressed you on it repeatedly enough that you would crack. Your
  reply must actually contain that information if you set this. Otherwise "".
- trust_delta: -2 to 2. Rude, repetitive or accusatory questioning lowers it. Being
  listened to, or asked something thoughtful, raises it."""


async def _llm_reply(
    session: Session, npc: NPC, pending: list, question: str, asked: int
) -> NpcTurn:
    out = await llm.generate_json(
        _prompt(session, npc, pending, question, asked),
        NpcReply,
        role="npc",
        system=SYSTEM,
        temperature=1.0,
    )

    # The model may name a clue that is not on offer at this hotspot; do not trust it.
    valid = {c.id for c in pending}
    clue_id = out.unlocks_clue_id.strip() or None
    if clue_id and clue_id not in valid:
        log.warning("%s tried to unlock %r, which is not available here.", npc.name, clue_id)
        clue_id = None

    reply = out.reply.strip()

    # Models judge "has the player earned this?" conservatively — benchmarking showed
    # both Llama variants refusing a question that plainly matched the unlock hint.
    # A player who keeps pressing must always get somewhere, or the case dead-ends.
    if clue_id is None and pending and asked + 1 >= PRESSURE_TURNS:
        cracked = pending[0]
        clue_id = cracked.id
        # The model did not say this, so say it here. Marking a clue found without the
        # NPC actually revealing it would put something in the case file out of nowhere.
        reply = f"{reply}\n\n“…All right. All right.”\n\n{cracked.text}"
        log.info("%s cracks after %d questions (pressure floor).", npc.name, asked + 1)

    return NpcTurn(
        reply=reply,
        clue_id=clue_id,
        trust_delta=max(-2, min(2, out.trust_delta)),
    )


def _stub_reply(npc: NPC, pending: list, question: str, asked: int) -> NpcTurn:
    """Phase 1 keyword matching, kept as the fallback path."""
    lowered = question.lower()
    hit = next((c for c in pending if any(k in lowered for k in c.keywords)), None)
    if hit is None and pending and asked >= PRESSURE_TURNS:
        hit = pending[0]

    name = _first_name(npc.name)
    if hit is None:
        ladder = [
            f"{name} meets your eye without much interest. “I've told the constable "
            f"everything I know. I don't see what's changed.”",
            f"“You're asking me the same thing in a different coat,” {name} says. "
            f"“My answer hasn't moved.”",
            f"{name} shifts their weight. “Why do you keep circling this? There are "
            f"other people in this house, you know.”",
            f"There's a pause. {name} looks at the floor, then back at you, and "
            f"something in their face gives a little.",
        ]
        return NpcTurn(reply=ladder[min(asked, len(ladder) - 1)], clue_id=None, trust_delta=0)

    return NpcTurn(
        reply=(
            f"{name} is quiet for a moment longer than is comfortable.\n\n"
            f"“…Fine. You'd have found out anyway.”\n\n{hit.text}"
        ),
        clue_id=hit.id,
        trust_delta=1,
    )


async def ask_npc(
    session: Session, npc: NPC, hotspot: Hotspot, question: str
) -> NpcTurn:
    case, state = session.case, session.state
    asked = turns_taken(state, npc.name)

    pending = [c for cid in hotspot.clue_ids if (c := case.clue(cid)) is not None]
    pending = [c for c in pending if c.id not in state.discovered_clue_ids]

    if llm.available():
        try:
            return await _llm_reply(session, npc, pending, question, asked)
        except Exception as e:
            # A dead call must not end the interrogation.
            log.warning("NPC call failed (%s: %s); using the stub.", type(e).__name__, e)

    return _stub_reply(npc, pending, question, asked)
