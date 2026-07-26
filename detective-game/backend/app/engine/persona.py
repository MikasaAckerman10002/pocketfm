"""Persona narration.

Phase 5: the host is written live from `personality_prompt`. The templates on the
Persona config stay as the fallback, so a failed call still narrates in roughly the
right voice instead of showing an error.

The rule this module exists to enforce: only `ending` may see the solution, and only
after the player has committed an accusation. Every other call is given the public
setup and, at most, a clue the player already holds.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from ..models import Clue, GameCase, Hotspot, Persona, Solution
from . import llm

log = logging.getLogger(__name__)


class Narration(BaseModel):
    text: str


def _victim_name(victim: str) -> str:
    """'Halloran Ashmere, master distiller' -> 'Halloran Ashmere'."""
    return victim.split(",")[0].strip()


def _system(persona: Persona) -> str:
    return f"""{persona.personality_prompt}

You are hosting a detective game. You narrate; you never play the suspects and never
speak for the player.

Hard rules:
- Stay in voice. Your personality is the whole point of you.
- Never invent case facts. You may only refer to what you are told below.
- Never state or hint at who the killer is, why they did it, or what the weapon was,
  unless you are explicitly told this is the final reveal.
- No markdown, no stage directions in asterisks, no headings. Just spoken narration.
- Plain, everyday English. Short sentences and common words. Keep your personality in
  the rhythm and attitude, not in difficult vocabulary — many players are not native
  English speakers, and the voice should be easy to follow out loud."""


async def _narrate(persona: Persona, prompt: str, fallback: str, words: int) -> str:
    if not llm.available():
        return fallback
    try:
        out = await llm.generate_json(
            f"{prompt}\n\nKeep it under {words} words. Write only what you say aloud.",
            Narration,
            role="npc",  # short and frequent, same latency profile as dialogue
            system=_system(persona),
            temperature=1.1,
        )
        text = out.text.strip()
        return text or fallback
    except Exception as e:
        log.warning("Persona narration failed (%s: %s); using template.", type(e).__name__, e)
        return fallback


async def intro(persona: Persona, case: GameCase) -> str:
    fallback = persona.intro_template.format(
        victim=_victim_name(case.victim),
        setting=case.setting,
        public_setup=case.public_setup,
    )
    return await _narrate(
        persona,
        f"""Open the case. This is the first thing the player hears from you.

THE SETTING: {case.setting}
THE VICTIM: {case.victim}
WHAT IS PUBLICLY KNOWN: {case.public_setup}

Set the scene, say who died, and send the player off to start looking. You do not
know who did it — you are as much in the dark as they are.""",
        fallback,
        160,
    )


async def react_to_clue(persona: Persona, clue: Clue, found_count: int) -> str:
    templates = persona.clue_react_templates
    fallback = templates[(found_count - 1) % len(templates)].format(clue=clue.name)
    return await _narrate(
        persona,
        f"""The player just uncovered something. React to it, briefly, in character.

WHAT THEY FOUND: {clue.name} — {clue.text}
THIS IS DISCOVERY NUMBER {found_count}.

React to this one fact only. Do not speculate about who is guilty, and do not
connect it to any other evidence.""",
        fallback,
        45,
    )


async def examine(persona: Persona, hotspot: Hotspot, clue: Clue | None, seen: int) -> str:
    if clue is not None:
        # The clue text is the payload; the host frames it rather than replacing it.
        fallback = clue.text
        return await _narrate(
            persona,
            f"""The player is examining "{hotspot.label}" and it yields something.

WHAT THEY FIND: {clue.text}

Describe them finding it, in your voice. The full fact above must survive — do not
summarise it away.""",
            fallback,
            80,
        )

    templates = persona.examine_templates
    fallback = templates[seen % len(templates)].format(object=hotspot.label.lower())
    return await _narrate(
        persona,
        f"""The player is examining "{hotspot.label}". There is nothing useful here.

They have looked at it {seen + 1} time(s). Say so in your voice — bored, wry, or
impatient as suits you. Do not invent evidence. Do not hint that anything is hidden
here, because nothing is.""",
        fallback,
        40,
    )


async def ending(
    persona: Persona, case: GameCase, solution: Solution, correct: bool
) -> str:
    """The only narration permitted to know the solution."""
    template = persona.win_template if correct else persona.lose_template
    fallback = template.format(
        killer=solution.killer,
        motive=solution.motive,
        weapon=solution.weapon,
        victim=_victim_name(case.victim),
    )
    verdict = (
        "They named the right person. Confirm it and give them credit in your own way."
        if correct
        else "They accused the wrong person. Tell them so, then reveal the truth."
    )
    return await _narrate(
        persona,
        f"""THIS IS THE FINAL REVEAL. You may now say everything.

THE TRUTH: {solution.killer} killed {_victim_name(case.victim)}, {solution.motive},
using {solution.weapon}.

{verdict}

Name the killer, the reason, and the weapon plainly, then close the case in your
voice.""",
        fallback,
        200,
    )
