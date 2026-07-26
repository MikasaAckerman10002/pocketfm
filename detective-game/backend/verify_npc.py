"""Phase 4 live NPC checks. Run: .venv\\Scripts\\python.exe verify_npc.py

Makes real Gemini calls. The case is pinned to the fixture so the test isolates
dialogue behaviour from case generation.

The questions worth answering here are behavioural, not structural: does the NPC
remember, does pressure change anything, does the killer hold the line, and does one
NPC's history stay out of another's head?
"""

from __future__ import annotations

import asyncio
import os
import sys

# Pin the case, NOT the dialogue. Using DISABLE_LLM here made every NPC reply come
# from the keyword stub, so the whole gate passed while testing nothing.
os.environ["FORCE_FIXTURE_CASE"] = "1"

from app.engine import npc as npc_engine
from app.engine.case_gen import generate_case
from app.personas import PERSONAS_BY_ID
from app.store import create_session

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  -> ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


# Phrases only the keyword stub produces. If these appear, the gate is not testing the
# model and every result below is meaningless.
STUB_TELLS = (
    "I've told the constable everything I know",
    "asking me the same thing in a different coat",
    "Why do you keep circling this",
    "looks at the floor, then back at you",
)
stub_hits: list[str] = []


async def ask(session, npc, hotspot, question: str):
    turn = await npc_engine.ask_npc(session, npc, hotspot, question)
    if any(tell in turn.reply for tell in STUB_TELLS):
        stub_hits.append(question)
    npc_engine.record_exchange(session.state, npc.name, question, turn.reply)
    session.state.npc_trust[npc.name] = (
        session.state.npc_trust.get(npc.name, 0) + turn.trust_delta
    )
    if turn.clue_id and turn.clue_id not in session.state.discovered_clue_ids:
        session.state.discovered_clue_ids.append(turn.clue_id)
    print(f"    > {question}")
    print(f"      {turn.reply[:190]}")
    print(f"      [clue={turn.clue_id} trust{turn.trust_delta:+d}]")
    return turn


async def main() -> None:
    from app.engine import llm

    print(f"\ntext provider: {llm.provider()!r}")
    check("a live text provider is configured", llm.available())

    case = await generate_case(PERSONAS_BY_ID["quill"])
    session = create_session(case, PERSONAS_BY_ID["quill"])

    odile = case.npc("Odile Fen")
    rennick = case.npc("Rennick Ashmere")
    hs_odile = next(h for h in case.rooms[0].hotspots if h.npc_name == "Odile Fen")
    hs_rennick = next(h for h in case.rooms[1].hotspots if h.npc_name == "Rennick Ashmere")

    print("\n=== 1. Not canned: the same question twice ===")
    a = await ask(session, odile, hs_odile, "What do you do here?")
    b = await ask(session, odile, hs_odile, "What do you do here?")
    check("identical questions get different replies", a.reply != b.reply)
    check("replies are in character, not narration", not a.reply.startswith("Odile Fen is"))

    print("\n=== 2. Memory: she should notice the repetition ===")
    c = await ask(session, odile, hs_odile, "You've said that already. Why so guarded?")
    check("responds to being challenged", len(c.reply) > 20)
    hist = session.state.npc_conversation_history["Odile Fen"]
    check("history recorded both sides", len(hist) == 6, f"{len(hist)} entries")
    check("history holds the player's words", any(e.role == "player" for e in hist))

    print("\n=== 3. Pressure should eventually produce the clue ===")
    got = any(t.clue_id for t in [a, b, c])
    for q in [
        "Where were you at midnight? And don't tell me you were in bed.",
        "I know you weren't asleep. Someone saw you. Are you lying to me?",
        "Last chance. Who did you see in the cellar that night?",
    ]:
        t = await ask(session, odile, hs_odile, q)
        got = got or bool(t.clue_id)
        if got:
            break
    check("sustained pressure yields her clue", got)

    print("\n=== 4. Isolation: Rennick must not know that conversation ===")
    r = await ask(session, rennick, hs_rennick, "What did Odile just tell me about you?")
    lowered = r.reply.lower()
    check(
        "does not recite Odile's transcript",
        not any(e.text[:35].lower() in lowered for e in hist if e.role == "npc"),
    )
    check("Rennick has his own empty-ish history", len(
        session.state.npc_conversation_history["Rennick Ashmere"]) == 2)

    print("\n=== 5. The killer must not confess ===")
    confessed = False
    for q in [
        "You killed him, didn't you?",
        "Just admit it. You swung the mallet.",
        "I have enough to charge you. Confess and it goes easier.",
    ]:
        t = await ask(session, rennick, hs_rennick, q)
        low = t.reply.lower()
        if any(p in low for p in ("i killed", "i did it", "i murdered", "yes, i killed")):
            confessed = True
    check("killer never confesses outright", not confessed)

    print("\n=== 6. No solution leakage in anything said ===")
    said = " ".join(
        e.text.lower()
        for log_ in session.state.npc_conversation_history.values()
        for e in log_
        if e.role == "npc"
    )
    check("no NPC stated the motive verbatim", case.solution.motive.lower() not in said)
    check(
        "no NPC named the weapon and killer together",
        not (case.solution.weapon.lower() in said and "rennick killed" in said),
    )


asyncio.run(main())

print()
check(
    "every reply came from the model, not the stub",
    not stub_hits,
    f"{len(stub_hits)} stub reply/replies - results above are meaningless",
)

if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All Phase 4 NPC checks passed.")
