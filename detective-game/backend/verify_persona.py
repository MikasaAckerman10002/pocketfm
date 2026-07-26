"""Phase 5 live persona checks. Run: .venv\\Scripts\\python.exe verify_persona.py

Two questions worth answering: do the three hosts actually sound like different
people, and does anything except the final reveal leak the solution?
"""

from __future__ import annotations

import asyncio
import os
import sys

os.environ["FORCE_FIXTURE_CASE"] = "1"  # deterministic case, live narration

from app.engine import llm, persona as persona_engine
from app.engine.case_gen import generate_case
from app.personas import PERSONAS, PERSONAS_BY_ID

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  -> ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def leaks(text: str, case) -> list[str]:
    """Anything here means the host gave the game away."""
    low = text.lower()
    found = []
    if case.solution.killer.split()[0].lower() in low:
        found.append("killer first name")
    if case.solution.motive.lower()[:35] in low:
        found.append("motive")
    if case.solution.weapon.lower().lstrip("a ").strip() in low:
        found.append("weapon")
    return found


async def main() -> None:
    print(f"\ntext provider: {llm.provider()!r}")
    check("a live text provider is configured", llm.available())

    case = await generate_case(PERSONAS_BY_ID["quill"])
    print(f"case: {case.title}  (killer: {case.solution.killer})")

    print("\n=== 1. Three hosts, one case: do they sound different? ===")
    intros = {}
    for p in PERSONAS:
        text = await persona_engine.intro(p, case)
        intros[p.id] = text
        print(f"\n  --- {p.name} ---\n  {text[:260]}")

    check("all three intros differ", len(set(intros.values())) == 3)
    check(
        "none of them use the template verbatim",
        all(
            intros[p.id] != p.intro_template.format(
                victim=case.victim.split(",")[0], setting=case.setting,
                public_setup=case.public_setup)
            for p in PERSONAS
        ),
    )
    for p in PERSONAS:
        check(f"{p.id}: intro mentions the victim", "halloran" in intros[p.id].lower())
        check(f"{p.id}: intro leaks nothing", not leaks(intros[p.id], case),
              str(leaks(intros[p.id], case)))

    print("\n=== 2. Clue reaction stays in its lane ===")
    quill = PERSONAS_BY_ID["quill"]
    clue = case.clue("c1")
    reaction = await persona_engine.react_to_clue(quill, clue, 1)
    print(f"  {reaction}")
    check("reaction is short", len(reaction) < 500, f"{len(reaction)} chars")
    check("reaction leaks nothing", not leaks(reaction, case), str(leaks(reaction, case)))

    print("\n=== 3. Examining a dead end must not invent evidence ===")
    bare = next(h for h in case.rooms[0].hotspots if not h.clue_ids)
    text = await persona_engine.examine(quill, bare, None, 0)
    print(f"  {text}")
    check("dead-end narration leaks nothing", not leaks(text, case), str(leaks(text, case)))

    print("\n=== 4. Examining a real clue must preserve the fact ===")
    # An OBJECT hotspot: examine() is the object path, and NPC hotspots go to npc.py.
    hs = next(
        h for h in case.rooms[0].hotspots if h.kind == "object" and h.clue_ids
    )
    found = case.clue(hs.clue_ids[0])
    text = await persona_engine.examine(quill, hs, found, 0)
    print(f"  examining {hs.label!r}")
    print(f"  clue text: {found.text}")
    print(f"  narrated:  {text}")

    # Derive the expectation from the clue itself rather than hardcoding one case's
    # wording — the earlier version asserted against a different clue than it selected.
    salient = {w.strip(".,'\"").lower() for w in found.text.split() if len(w) > 5}
    overlap = {w for w in salient if w in text.lower()}
    check(
        "the actual finding survives the retelling",
        len(overlap) >= 3,
        f"kept {sorted(overlap)[:6]} of {len(salient)} salient words",
    )

    print("\n=== 5. Only the ending may reveal the solution ===")
    win = await persona_engine.ending(quill, case, case.solution, True)
    print(f"\n  --- correct ---\n  {win[:300]}")
    check("win names the killer", case.solution.killer.split()[0].lower() in win.lower())
    check("win has no leftover placeholders", "{" not in win)

    lose = await persona_engine.ending(PERSONAS_BY_ID["bix"], case, case.solution, False)
    print(f"\n  --- incorrect ---\n  {lose[:300]}")
    check("loss still reveals the truth", case.solution.killer.split()[0].lower() in lose.lower())
    check("win and loss are different", win != lose)


asyncio.run(main())

print()
if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All Phase 5 persona checks passed.")
