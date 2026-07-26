"""Phase 1 acceptance checks. Run: .venv\\Scripts\\python.exe verify.py

These stay useful in later phases — especially the leak check, which should keep
passing once real Gemini-generated cases replace the fixture.
"""

from __future__ import annotations

import json
import os
import sys

# Pin to the fixture so this gate stays deterministic and offline. Live generation is
# checked separately by verify_llm.py.
os.environ["DISABLE_LLM"] = "1"
# And no room art. This gate drives the real routes, which start image generation on
# every new case — so an "offline" test was quietly spending image credits and waiting
# out the polling loop. DISABLE_LLM never covered images; it only looked harmless
# while the account had no credit and failed instantly.
os.environ["IMAGE_PROVIDER"] = "off"
os.environ["DISABLE_TTS"] = "1"
os.environ["DISABLE_VISION"] = "1"

from fastapi.testclient import TestClient

from app.main import app
from app.store import SESSIONS

client = TestClient(app)
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  -> ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


print("\n[1] Hidden case never reaches the client")
r = client.post("/api/case/new", json={"persona_id": "quill"})
r.raise_for_status()
payload = r.json()
session_id = payload["session_id"]
raw = json.dumps(payload).lower()

case = SESSIONS[session_id].case
view = payload["view"]

check("no 'solution' key in response", "solution" not in raw)

# The accusation menus must contain the true answers or the case is unwinnable, so
# absence is not the protection. Indistinguishability is: the true answer has to sit
# among decoys, and must not be pinnable by position.
opts = view["accusation_options"]
check("all NPCs offered as suspects", sorted(opts["suspects"]) == sorted(n.name for n in case.npcs))
check("killer not singled out", len(opts["suspects"]) >= 3)
check("true motive is among decoys", case.solution.motive in opts["motives"] and len(opts["motives"]) >= 3)
check("true weapon is among decoys", case.solution.weapon in opts["weapons"] and len(opts["weapons"]) >= 3)

positions = set()
for _ in range(30):
    p = client.post("/api/case/new", json={"persona_id": "quill"}).json()
    o = p["view"]["accusation_options"]
    s = SESSIONS[p["session_id"]].case.solution
    positions.add((o["motives"].index(s.motive), o["weapons"].index(s.weapon)))
check("answer position varies across cases", len(positions) > 1, f"{len(positions)} distinct positions in 30 cases")

check("timeline absent", case.timeline[0][:20].lower() not in raw)
check("npc secrets absent", case.npcs[1].secrets[0][:30].lower() not in raw)
check("clue keywords absent", "unlock_hint" not in raw and "keywords" not in raw)
check("hotspot clue_ids absent", "clue_ids" not in raw)
check("intro narration present", len(payload["intro"]) > 50)

check("starts in first room", view["current_room"] == case.rooms[0].id)
check("later rooms locked", view["rooms"][1]["locked"] is True)
check("no clues yet", view["discovered_clues"] == [])


print("\n[2] Clue unlock via hotspot")
# Object hotspot: examining the ledger yields its clue.
r = client.post(
    "/api/hotspot/ask",
    json={"session_id": session_id, "hotspot_id": "hs-ledger", "question": "look"},
)
r.raise_for_status()
d = r.json()
check("object examine unlocked a clue", d["clue_unlocked"] is not None)
check("persona reacted", bool(d["persona_reaction"]))
check("clue tray has 1", len(d["view"]["discovered_clues"]) == 1)

# NPC hotspot: a question that misses yields a deflection, not a clue.
r = client.post(
    "/api/hotspot/ask",
    json={"session_id": session_id, "hotspot_id": "hs-odile", "question": "nice weather"},
)
d = r.json()
check("irrelevant question unlocks nothing", d["clue_unlocked"] is None)
check("still 1 clue", len(d["view"]["discovered_clues"]) == 1)

# NPC hotspot: a question that lands unlocks.
r = client.post(
    "/api/hotspot/ask",
    json={
        "session_id": session_id,
        "hotspot_id": "hs-odile",
        "question": "Were you really in bed at midnight, or are you lying?",
    },
)
d = r.json()
check("targeted question unlocked a clue", d["clue_unlocked"] is not None)
check("trust moved", d["trust_delta"] == 1)
check("clue tray has 2", len(d["view"]["discovered_clues"]) == 2)


print("\n[3] Room unlock at 2 clues")
check("room 2 reported unlocked", d["room_unlocked"] == "stillhouse")
check("room 2 no longer locked", d["view"]["rooms"][1]["locked"] is False)
check("room 3 still locked", d["view"]["rooms"][2]["locked"] is True)

r = client.post(
    "/api/room/enter", json={"session_id": session_id, "room_id": "stillhouse"}
)
check("can enter unlocked room", r.status_code == 200)
r = client.post(
    "/api/room/enter", json={"session_id": session_id, "room_id": "tasting"}
)
check("cannot enter locked room", r.status_code == 403)


print("\n[4] NPC memory: pressure cracks them without the keyword")
r2 = client.post("/api/case/new", json={"persona_id": "bix"})
sid2 = r2.json()["session_id"]
replies = []
for _ in range(5):
    rr = client.post(
        "/api/hotspot/ask",
        json={"session_id": sid2, "hotspot_id": "hs-odile", "question": "hm"},
    ).json()
    replies.append(rr)
check("no clue on early vague questions", replies[0]["clue_unlocked"] is None)
check("cracks under sustained pressure", replies[4]["clue_unlocked"] is not None)
check("deflections escalate (not identical)", replies[0]["reply"] != replies[2]["reply"])
history = SESSIONS[sid2].state.npc_conversation_history["Odile Fen"]
check("exchanges recorded", len(history) == 10, f"{len(history)} entries")


print("\n[5] Solve flow, both outcomes")
sol = case.solution
r = client.post(
    "/api/solve",
    json={
        "session_id": session_id,
        "suspect": sol.killer,
        "motive": sol.motive,
        "weapon": sol.weapon,
    },
)
d = r.json()
check("correct accusation wins", d["correct"] is True)
check("win narration present", len(d["narration"]) > 50)
check("truth revealed only now", d["truth"]["killer"] == sol.killer)
check("no leftover format placeholders", "{" not in d["narration"])

r = client.post(
    "/api/solve",
    json={
        "session_id": sid2,
        "suspect": "Odile Fen",
        "motive": sol.motive,
        "weapon": sol.weapon,
    },
)
d = r.json()
check("wrong accusation loses", d["correct"] is False)
check("lose narration present", len(d["narration"]) > 50)
check("no leftover format placeholders", "{" not in d["narration"])


print("\n[6] New Case resets cleanly")
r3 = client.post("/api/case/new", json={"persona_id": "corvina"})
v3 = r3.json()["view"]
check("fresh session has no clues", v3["discovered_clues"] == [])
check("fresh session back in room 1", v3["current_room"] == "cellar")
check("fresh session rooms relocked", v3["rooms"][1]["locked"] is True)
check("distinct session id", r3.json()["session_id"] != session_id)
check("persona swapped", v3["persona"]["name"].startswith("Madame"))

# Every persona's templates must render without leftover placeholders.
for pid in ("quill", "bix", "corvina"):
    p = client.post("/api/case/new", json={"persona_id": pid}).json()
    check(f"{pid} intro renders clean", "{" not in p["intro"])


print("\n" + "=" * 60)
if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All Phase 1 checks passed.")
