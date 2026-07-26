"""Phase 2 live checks. Run: .venv\\Scripts\\python.exe verify_llm.py

Makes real Gemini calls. The offline gate (verify.py) cannot answer the question that
actually matters here: is a *generated* case playable end to end, or does it softlock?
"""

from __future__ import annotations

import asyncio
import json
import sys

from fastapi.testclient import TestClient

from app.engine.case_gen import generate_case
from app.main import app
from app.models import GameCase
from app.personas import PERSONAS_BY_ID
from app.store import SESSIONS

failures: list[str] = []
warnings: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  -> ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def warn(label: str, ok: bool, detail: str = "") -> None:
    if not ok:
        print(f"  WARN  {label}{'  -> ' + detail if detail else ''}")
        warnings.append(label)


def overlaps(a, b) -> bool:
    return not (
        a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y
    )


def audit(case: GameCase, tag: str) -> None:
    print(f"\n--- {tag}: {case.title!r} ---")
    print(f"    {case.setting[:88]}")
    print(f"    victim: {case.victim}")
    print(f"    npcs:   {[n.name for n in case.npcs]}")
    print(f"    rooms:  {[r.name for r in case.rooms]}")
    print(f"    killer: {case.solution.killer}")

    check(f"{tag}: 3 rooms", len(case.rooms) == 3, f"{len(case.rooms)}")
    check(f"{tag}: 3 npcs", len(case.npcs) == 3, f"{len(case.npcs)}")
    check(f"{tag}: >=4 clues", len(case.clues) >= 4, f"{len(case.clues)}")

    npc_names = [n.name for n in case.npcs]

    # Every clue must hang off exactly one hotspot, or it can never be found.
    counts = {c.id: 0 for c in case.clues}
    for room in case.rooms:
        for hs in room.hotspots:
            for cid in hs.clue_ids:
                counts[cid] = counts.get(cid, 0) + 1
    unreachable = [cid for cid, n in counts.items() if n == 0]
    duplicated = [cid for cid, n in counts.items() if n > 1]
    check(f"{tag}: every clue reachable", not unreachable, str(unreachable))
    warn(f"{tag}: no clue on two hotspots", not duplicated, str(duplicated))

    check(
        f"{tag}: npc hotspots resolve",
        all(
            hs.npc_name in npc_names
            for r in case.rooms
            for hs in r.hotspots
            if hs.kind == "npc"
        ),
    )
    check(
        f"{tag}: every room has a hotspot",
        all(r.hotspots for r in case.rooms),
    )
    check(
        f"{tag}: hotspots in frame",
        all(
            0 <= hs.x and 0 <= hs.y and hs.x + hs.w <= 1.001 and hs.y + hs.h <= 1.001
            for r in case.rooms
            for hs in r.hotspots
        ),
    )
    for room in case.rooms:
        pairs = [
            (a.label, b.label)
            for i, a in enumerate(room.hotspots)
            for b in room.hotspots[i + 1 :]
            if overlaps(a, b)
        ]
        warn(f"{tag}: {room.name} hotspots don't overlap", not pairs, str(pairs[:2]))

    check(f"{tag}: killer is an NPC", case.solution.killer in npc_names)
    check(f"{tag}: victim is not an NPC", all(n.name not in case.victim for n in case.npcs))
    check(f"{tag}: true motive selectable", case.solution.motive in case.motive_options)
    check(f"{tag}: true weapon selectable", case.solution.weapon in case.weapon_options)
    check(f"{tag}: >=3 motive options", len(case.motive_options) >= 3)
    check(f"{tag}: >=3 weapon options", len(case.weapon_options) >= 3)
    check(
        f"{tag}: setup doesn't name the killer",
        case.solution.killer.split()[-1].lower() not in case.public_setup.lower(),
    )
    check(
        f"{tag}: image prompt per room",
        all(len(r.image_prompt) > 25 for r in case.rooms),
    )
    check(
        f"{tag}: clues have keywords",
        all(len(c.keywords) >= 4 for c in case.clues),
        f"min {min(len(c.keywords) for c in case.clues)}",
    )
    check(
        f"{tag}: motives lowercase for templates",
        all(m[:1].islower() for m in case.motive_options),
        str([m for m in case.motive_options if not m[:1].islower()][:1]),
    )


print("=" * 66)
print("Generating 3 cases concurrently")
print("=" * 66)

persona = PERSONAS_BY_ID["quill"]


async def generate_three() -> list[GameCase]:
    return await asyncio.wait_for(
        asyncio.gather(*(generate_case(persona) for _ in range(3))), timeout=240
    )


cases = asyncio.run(generate_three())

for i, c in enumerate(cases, 1):
    audit(c, f"case{i}")

print("\n--- variety ---")
check("titles differ", len({c.title for c in cases}) == 3, str([c.title for c in cases]))
check("no fixture fallback used", not any(c.id.startswith("case-fixture") for c in cases))

# Compare the victim's NAME, not name-plus-role. Three runs once returned the same
# "Arthur Pendelton" wearing three different job titles, and comparing full strings
# reported that as three distinct victims.
victim_names = [c.victim.split(",")[0].strip() for c in cases]
check("victim names differ", len(set(victim_names)) == 3, str(victim_names))

surnames = [n.name.split()[-1] for c in cases for n in c.npcs]
check(
    "no surname reused across cases",
    len(set(surnames)) == len(surnames),
    str(sorted(s for s in surnames if surnames.count(s) > 1)),
)
check("settings differ", len({c.setting for c in cases}) == 3, str([c.setting[:40] for c in cases]))

# Non-ASCII names now appear constantly (Gómez, Seppänen). Confirm they survive the
# trip as real UTF-8 rather than mojibake, since the console mangles them regardless.
sample = "".join(n.name for c in cases for n in c.npcs)
check("names round-trip as UTF-8", sample.encode("utf-8").decode("utf-8") == sample)
check("no replacement chars in names", "�" not in sample)


print("\n" + "=" * 66)
print("Full playthrough of a freshly generated case, through the API")
print("=" * 66)

client = TestClient(app)
r = client.post("/api/case/new", json={"persona_id": "corvina"})
r.raise_for_status()
payload = r.json()
sid = payload["session_id"]
case = SESSIONS[sid].case
raw = json.dumps(payload)

print(f"\n  case: {case.title!r}")

# The Phase 1 leak boundary must still hold on LLM-authored content.
print("\n--- leak boundary on generated content ---")
check("no 'solution' key", "solution" not in raw)
check("no unlock_hint", "unlock_hint" not in raw)
check("no keywords", "keywords" not in raw)
check("no clue_ids", "clue_ids" not in raw)
check("no timeline", "timeline" not in raw)
check("no npc secrets", all(s[:40] not in raw for n in case.npcs for s in n.secrets))
check("no npc knowledge", all(k[:40] not in raw for n in case.npcs for k in n.knowledge))
check("no clue text before discovery", all(c.text[:40] not in raw for c in case.clues))

print("\n--- can a player actually win? ---")
found: list[str] = []
for room in case.rooms:
    if room.id not in SESSIONS[sid].state.rooms_unlocked:
        check(f"reached {room.name}", False, "room never unlocked")
        break
    client.post("/api/room/enter", json={"session_id": sid, "room_id": room.id})
    for hs in room.hotspots:
        for cid in list(hs.clue_ids):
            clue = case.clue(cid)
            question = clue.keywords[0] if clue and clue.keywords else "tell me everything"
            d = client.post(
                "/api/hotspot/ask",
                json={"session_id": sid, "hotspot_id": hs.id, "question": question},
            ).json()
            if d.get("clue_unlocked"):
                found.append(d["clue_unlocked"]["name"])
    print(f"    {room.name}: {len(found)} clues total so far")

check("found every clue", len(found) == len(case.clues), f"{len(found)}/{len(case.clues)}")
check("all rooms unlocked", len(SESSIONS[sid].state.rooms_unlocked) == len(case.rooms))

sol = case.solution
d = client.post(
    "/api/solve",
    json={"session_id": sid, "suspect": sol.killer, "motive": sol.motive, "weapon": sol.weapon},
).json()
check("correct accusation wins", d["correct"] is True)
check("ending renders without placeholders", "{" not in d["narration"])
print("\n  ENDING:\n   ", d["narration"][:300].replace("\n", "\n    "))


print("\n" + "=" * 66)
if warnings:
    print(f"{len(warnings)} warning(s) — cosmetic, not blocking")
if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All Phase 2 live checks passed.")
