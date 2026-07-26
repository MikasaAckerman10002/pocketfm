"""Case generation.

Phase 2: Gemini writes the mystery. The engine does not trust it.

A generated case can be structurally valid JSON and still be an unplayable game —
a clue no hotspot points to is unfindable, a killer who is not one of the suspects is
unaccusable. `_build` repairs what is cheap to repair and raises on what is not, and
`generate_case` retries before falling back to the Phase 1 fixture so a rate limit
mid-demo degrades to a working game instead of a stack trace.
"""

from __future__ import annotations

import logging
import random
import uuid
from collections import deque
from pathlib import Path

from ..config import FORCE_FIXTURE_CASE, USE_LLM
from ..models import NPC, Clue, GameCase, Hotspot, Persona, Room, Solution
from . import llm
from .schema import GeneratedCase

log = logging.getLogger(__name__)

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "dummy_case.json"

# ElevenLabs voice ids, assigned per NPC. Empty means "use the configured default",
# which is where things stand until a host backend supplies a voice per character.
# Distinct ids here give each suspect a distinct voice with no other code change.
VOICES: list[str] = [""]

ROOMS_PER_CASE = 3
NPCS_PER_CASE = 3
CLUES_PER_CASE = 5

# Left to itself the model writes the same fog-bound manor every time. Seeding the
# prompt is what makes "New Case" visibly different rather than subtly different.
SEEDS = [
    "a struggling seaside amusement pier out of season",
    "a high-altitude weather research station in winter",
    "a family-run competitive bakery the night before a televised final",
    "a restored steam railway during a collectors' convention",
    "a boutique perfume house on the eve of a launch",
    "an isolated desert observatory during a meteor shower",
    "a floating fish market before dawn",
    "a taxidermy museum hosting a private auction",
    "a vineyard during a disastrous harvest",
    "a suburban curling club during a regional tournament",
    "a lighthouse converted into a writers' retreat",
    "a nightshift at a vinyl pressing plant",
]

# Unprompted, the model returns the same cast every time — three consecutive runs all
# had a victim named Arthur Pendelton and an NPC surnamed Finch. Naming has to be
# seeded and the defaults banned, or "New Case" stops feeling like a new case.
NAME_WORLDS = [
    "Nigerian and Ghanaian",
    "Korean and Japanese",
    "Brazilian and Portuguese",
    "Polish and Czech",
    "Scottish and Irish",
    "Mexican and Colombian",
    "Egyptian and Lebanese",
    "Vietnamese and Filipino",
    "Greek and Turkish",
    "Swedish and Finnish",
    "Punjabi and Tamil",
    "Kenyan and Somali",
]

BANNED_NAMES = [
    "Pendelton", "Finch", "Vance", "Sterling", "Blackwood", "Ashmere",
    "Ravenswood", "Thorne", "Blackwell", "Hawthorne", "Ashford", "Whitlock",
]

SYSTEM = """You are a mystery designer for a point-and-click detective game.
You produce fair, solvable murder mysteries: every fact the player needs to name the
killer is discoverable in the rooms you define. You never write a clue that cannot be
reached.

LANGUAGE — this matters as much as the plot. Players read this quickly, on screen,
and many are not native English speakers. Write in plain, everyday English:
- Short sentences. One idea per sentence.
- Common words. Say "found" not "discovered to be", "money" not "pecuniary gain",
  "argument" not "altercation", "broken" not "compromised".
- No literary, archaic, or ornate vocabulary. No purple metaphors. No poetic phrasing.
- A clue should read like a police note, not a novel.
Aim for language a fifteen-year-old reads without pausing. The mystery should be
clever; the sentences should be simple.

SIMPLE IS NOT VAGUE. Easy words, hard facts. Every clue must contain something
specific a detective could act on — a name, a time, a number, an object, a place.
  BAD:  "Akira was acting suspiciously before the murder."
  GOOD: "Akira left the dining car at 9:40pm and came back with wet shoes."
  BAD:  "A valuable item was found near the scene."
  GOOD: "A gold pocket watch was under the seat. The chain was snapped."
Never write a clue that only says someone seemed nervous, odd, or suspicious. Say what
they actually did."""


def _prompt(seed: str, name_world: str) -> str:
    return f"""Design one original murder mystery set in {seed}.

CAST NAMING (this matters — repeated casts make the game feel canned):
- Draw all character names from {name_world} naming traditions.
- Do not use any of these names or anything close to them:
  {", ".join(BANNED_NAMES)}.
- The victim's name must not be a generic English manor-mystery name.

STRUCTURE (exact counts, non-negotiable):
- Exactly {NPCS_PER_CASE} NPCs. One of them is the killer. All are plausible suspects.
- Exactly {CLUES_PER_CASE} clues, with ids "c1" through "c5".
- Exactly {ROOMS_PER_CASE} rooms, with ids "r1", "r2", "r3", in the order the player
  visits them.
- Room r1 owns clues c1 and c2. Room r2 owns c3 and c4. Room r3 owns c5.

HOTSPOTS — the clickable things in each room:
- Each room has 3 hotspots: exactly one "npc" and two "object".
- Put a different NPC in each room, so r1, r2 and r3 each hold one.
- For an npc hotspot set npc_name to that NPC's exact name. For object hotspots set
  npc_name to "" (empty string).
- Every clue must be attached to exactly one hotspot via that hotspot's clue_ids, and
  the hotspot must be in the room that owns the clue. In each room, attach one clue to
  the NPC hotspot and one to an object hotspot. In r3 attach c5 to the NPC hotspot.
  Leave the remaining object hotspot's clue_ids empty — it is set dressing.
- x, y, w, h are normalized 0-1 rectangles over a 16:9 scene image. They must be the
  size of the THING, not a share of the frame. Do not spread them out to fill space.
  A person standing in a wide shot:  w 0.10-0.16,  h 0.45-0.70,  y 0.20-0.35.
  An object sitting in the scene:    w 0.10-0.20,  h 0.10-0.22.
  Keep every rectangle inside 0.04-0.96 and do not let two rectangles in one room
  overlap. Place them where that thing would plausibly be: people stand on the floor
  in the middle distance, wall fixtures sit high, furniture sits low.

CLUES:
- text: what the player learns, one or two concrete sentences, third person.
- unlock_hint: what line of questioning or examination reveals it.
- keywords: 8-14 lowercase single words a player might type that should reveal it.
  Include obvious synonyms. No punctuation.

NPCs:
- knowledge: 3 things they will say freely.
- secrets: 2 things they admit only under pressure. Write these as third-person
  descriptive facts, not as quoted dialogue.

ACCUSATION MENUS — these become the player's multiple-choice options:
- motive_options: 4 motives. Each must be a lowercase phrase that reads naturally
  after "He did it ..." or "She did it ...", e.g. "to hide a forged inheritance".
  Do not capitalise. Do not end with a period.
- weapon_options: 4 weapons. Each a lowercase noun phrase beginning with an article,
  e.g. "a brass letter opener". Do not capitalise. Do not end with a period.
- solution.killer must be EXACTLY one of the NPC names.
- solution.motive must be EXACTLY one of the motive_options strings.
- solution.weapon must be EXACTLY one of the weapon_options strings.

OTHER FIELDS:
- victim: "Name, their role" — the victim is NOT one of the {NPCS_PER_CASE} NPCs.
- public_setup: 2-3 sentences the player is told at the start. It must NOT hint at
  the killer, the motive or the weapon.
- timeline: 5-6 timestamped lines of what really happened, for the engine only.
- image_prompt per room: a vivid art-direction sentence for a still scene with no
  people in it, describing the space, lighting and mood."""


# random.choice alone picked the same seed twice in a row during testing, producing
# two vinyl-pressing-plant murders back to back. The one moment the demo has to look
# infinite is the second click of "New Case", so don't repeat a recent setting.
_recent_seeds: deque[str] = deque(maxlen=max(1, len(SEEDS) // 2))
_recent_worlds: deque[str] = deque(maxlen=max(1, len(NAME_WORLDS) // 2))


def _pick(options: list[str], recent: deque[str]) -> str:
    choice = random.choice([o for o in options if o not in recent] or options)
    recent.append(choice)
    return choice


class CaseInvalid(Exception):
    """The generated case cannot be repaired into a playable game."""


def _shuffle_accusation_options(case: GameCase) -> None:
    """Order is a leak.

    The menus must contain the true answer, so absence is not the protection —
    indistinguishability is. A model reliably lists the real motive first, which makes
    "always pick option one" a winning strategy for anyone reading the network tab.
    """
    random.shuffle(case.motive_options)
    random.shuffle(case.weapon_options)


def _match_name(candidate: str, names: list[str]) -> str | None:
    """Tolerate 'Dr. Iris Vale' vs 'Iris Vale' without accepting a different person."""
    target = candidate.strip().lower()
    for name in names:
        if name.lower() == target:
            return name
    for name in names:
        if target and (target in name.lower() or name.lower() in target):
            return name
    return None


def _build(gen: GeneratedCase) -> GameCase:
    """Convert and repair. Raises CaseInvalid when the case is not salvageable."""
    if len(gen.rooms) < 2 or len(gen.npcs) < 2 or len(gen.clues) < 3:
        raise CaseInvalid(
            f"too small: {len(gen.rooms)} rooms, {len(gen.npcs)} npcs, {len(gen.clues)} clues"
        )

    rooms_in = gen.rooms[:ROOMS_PER_CASE]
    npcs_in = gen.npcs[:NPCS_PER_CASE]
    npc_names = [n.name.strip() for n in npcs_in]

    clues = [
        Clue(
            id=c.id.strip(),
            name=c.name.strip(),
            text=c.text.strip(),
            unlock_hint=c.unlock_hint.strip(),
            keywords=[k.strip().lower() for k in c.keywords if k.strip()],
        )
        for c in gen.clues
    ]
    # Duplicate ids would make a clue permanently ambiguous to unlock.
    seen: set[str] = set()
    clues = [c for c in clues if not (c.id in seen or seen.add(c.id))]
    clue_ids = {c.id for c in clues}
    if len(clues) < 3:
        raise CaseInvalid("fewer than 3 distinct clues after de-duplication")

    rooms: list[Room] = []
    for r_index, r in enumerate(rooms_in):
        hotspots: list[Hotspot] = []
        for h_index, h in enumerate(r.hotspots):
            matched = _match_name(h.npc_name, npc_names) if h.kind == "npc" else None
            # An npc hotspot pointing at nobody would 500 on click; demote it.
            kind = "npc" if matched else "object"
            hotspots.append(
                Hotspot(
                    id=f"r{r_index + 1}-h{h_index + 1}",
                    kind=kind,
                    label=h.label.strip() or (matched or "Something"),
                    x=min(max(h.x, 0.02), 0.95),
                    y=min(max(h.y, 0.02), 0.95),
                    w=min(max(h.w, 0.08), 0.4),
                    h=min(max(h.h, 0.12), 0.6),
                    npc_name=matched,
                    clue_ids=[cid for cid in h.clue_ids if cid in clue_ids],
                )
            )
        if not hotspots:
            raise CaseInvalid(f"room {r.name!r} has no hotspots")
        rooms.append(
            Room(
                id=f"r{r_index + 1}",
                name=r.name.strip(),
                image_prompt=r.image_prompt.strip(),
                hotspots=hotspots,
                clue_ids=[],
            )
        )

    # The softlock check. A clue attached to no hotspot can never be found, and the
    # room-unlock gate counts clues per room, so an orphan can strand the player in
    # room one with no way forward. Re-home orphans onto real hotspots.
    attached = {cid for room in rooms for hs in room.hotspots for cid in hs.clue_ids}
    orphans = [c.id for c in clues if c.id not in attached]
    if orphans:
        log.warning("re-homing %d unreachable clue(s): %s", len(orphans), orphans)
        targets = [
            hs
            for room in rooms
            for hs in room.hotspots
            if hs.kind == "object" and not hs.clue_ids
        ] or [hs for room in rooms for hs in room.hotspots]
        for i, cid in enumerate(orphans):
            targets[i % len(targets)].clue_ids.append(cid)

    # Room ownership is derived, never trusted, so the unlock gate always agrees with
    # what is actually clickable in the room.
    for room in rooms:
        room.clue_ids = [cid for hs in room.hotspots for cid in hs.clue_ids]

    killer = _match_name(gen.solution.killer, npc_names)
    if killer is None:
        raise CaseInvalid(f"killer {gen.solution.killer!r} is not one of {npc_names}")

    motives = [m.strip() for m in gen.motive_options if m.strip()]
    weapons = [w.strip() for w in gen.weapon_options if w.strip()]
    motive, weapon = gen.solution.motive.strip(), gen.solution.weapon.strip()
    # The true answer must be selectable, or the case is unwinnable.
    if motive not in motives:
        motives.append(motive)
    if weapon not in weapons:
        weapons.append(weapon)
    if len(motives) < 3 or len(weapons) < 3:
        raise CaseInvalid("not enough accusation decoys")

    case = GameCase(
        id=f"case-{uuid.uuid4().hex[:8]}",
        title=gen.title.strip(),
        setting=gen.setting.strip(),
        victim=gen.victim.strip(),
        public_setup=gen.public_setup.strip(),
        timeline=[t.strip() for t in gen.timeline],
        rooms=rooms,
        npcs=[
            NPC(
                name=n.name.strip(),
                role=n.role.strip(),
                voice_id=VOICES[i % len(VOICES)],
                knowledge=[k.strip() for k in n.knowledge],
                secrets=[s.strip() for s in n.secrets],
            )
            for i, n in enumerate(npcs_in)
        ],
        clues=clues,
        motive_options=motives,
        weapon_options=weapons,
        solution=Solution(killer=killer, motive=motive, weapon=weapon),
    )
    _shuffle_accusation_options(case)
    return case


def _load_fixture() -> GameCase:
    case = GameCase.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    case.id = f"case-fixture-{uuid.uuid4().hex[:6]}"
    _shuffle_accusation_options(case)
    return case


async def generate_case(persona: Persona, attempts: int = 3) -> GameCase:
    """Generate a fresh mystery.

    `persona` is intentionally unused: the engine is persona-agnostic, so the host
    narrates the case but never shapes it.
    """
    if FORCE_FIXTURE_CASE or not USE_LLM or not llm.available():
        log.info("Serving the fixture case.")
        return _load_fixture()

    seed = _pick(SEEDS, _recent_seeds)
    name_world = _pick(NAME_WORLDS, _recent_worlds)
    for attempt in range(1, attempts + 1):
        try:
            gen = await llm.generate_json(
                _prompt(seed, name_world),
                GeneratedCase,
                role="case",
                system=SYSTEM,
                temperature=1.15,
            )
            case = _build(gen)
            log.info("Generated %r (%s)", case.title, case.id)
            return case
        except CaseInvalid as e:
            log.warning("Attempt %d produced an unplayable case: %s", attempt, e)
        except Exception as e:
            log.warning("Attempt %d failed: %s: %s", attempt, type(e).__name__, e)

    log.error("Generation failed %d times; falling back to the fixture.", attempts)
    return _load_fixture()
