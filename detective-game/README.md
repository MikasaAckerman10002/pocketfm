# The Case Engine

A persona-driven infinite detective game. A hidden murder mystery is generated per
case; an original host character narrates it. The engine is persona-agnostic —
swapping the host changes the voice, not the game.

**All six phases complete.** Pick a host → a fresh mystery is written → rooms are
painted → explore, question suspects in free text, unlock clues → accuse → hear the
host narrate the ending. Cases, dialogue, narration, room art and voices are all
generated live.

Measured end to end: **9s from click to playable**, NPC replies in **0.7–1.4s**,
voice lines in **1.3–2.0s**.

## Running it

Needs **Python 3.11+** and **Node 18+**. Nothing else — no database, no Docker, no
Redis. State lives in memory.

Two processes. Backend first.

```bash
# backend  -> http://127.0.0.1:8000
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Linux/macOS: .venv/bin/python
cp .env.example .env                                          # then add your keys
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

# frontend -> http://localhost:5173
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to the backend, so the browser
stays on one origin and the network tab shows exactly what the game sends.

**It runs with no keys at all.** A fresh clone with an empty `.env` still plays a full
case end to end — fixture mystery, keyword-matched dialogue, colour plates, silent.
Add keys to turn each layer on. See `backend/.env.example` for what each one does and
what degrades without it.

```
GROQ_API_KEY=...          # cases + NPC dialogue + persona narration
OPENROUTER_API_KEY=...    # puts hotspot boxes on what was actually painted
NANOBANANA_API_KEY=...    # room art
ELEVENLABS_API_KEY=...    # voices
GEMINI_API_KEY=...        # optional fallback for text/images, unused by default
```

Every one of these is optional. Missing keys degrade rather than break: no text
provider serves the built-in fixture case with keyword-matched dialogue, no image key
falls back to colour plates, no voice key runs the game silently.

## Verifying

```bash
cd backend
.venv/Scripts/python.exe verify.py           # offline, deterministic, ~2s
.venv/Scripts/python.exe verify_llm.py       # live: case generation
.venv/Scripts/python.exe verify_npc.py       # live: dialogue, memory, killer deception
.venv/Scripts/python.exe verify_persona.py   # live: three voices, solution containment
.venv/Scripts/python.exe verify_images.py    # live: room art, 16:9, parallel
.venv/Scripts/python.exe verify_tts.py       # live: audio, caching, voice routing
```

Two flags control what is live. `DISABLE_LLM=1` turns off every model call.
`FORCE_FIXTURE_CASE=1` pins the case while leaving dialogue live — they are separate
because using the first for the second made the whole NPC gate run against the keyword
stub and pass without testing anything.

`verify.py` pins itself to the fixture (`DISABLE_LLM=1`) so it stays fast and
repeatable: leak boundary, clue unlocking, room gating, NPC memory, both solve
outcomes, session reset.

`verify_llm.py` answers what the offline gate cannot — is a *generated* case actually
playable? It generates three cases concurrently, then plays one to completion through
the API, asserting every clue is reachable, every room unlocks, and the correct
accusation wins.

> **Do not** write leak checks as `grep -iF`. This machine's GNU grep 3.0 silently
> returns zero matches when `-i` and `-F` are combined, so an absence-assertion passes
> unconditionally. `verify.py` audits parsed JSON in Python for this reason.

## Architecture

```
backend/app/
  models.py     GameCase / GameState / Persona + the public DTOs
  store.py      in-memory sessions; the only place a GameCase lives
  view.py       to_public() — the single redaction boundary
  personas.py   three original hosts
  engine/       case_gen · npc · persona   (stubs now, Gemini later)
  routes/game.py
frontend/src/
  App.tsx       orchestrator
  components/   PersonaSelect · RoomView · ChatPanel · Sidebar · SolveModal · EndingOverlay
```

### The one rule

`GameCase` holds the solution and never crosses the wire. Every route declares a
public Pydantic `response_model`, so FastAPI strips undeclared fields at
serialization time — a careless `return case` drops the solution rather than shipping
it. `POST /api/solve` is the only route permitted to reveal the truth, and only after
the player commits an accusation.

Two subtler leaks are designed out: `PublicRoom` omits clue counts (or you could tell
how many clues remain), and `PublicHotspot` omits `clue_ids` (or the DOM would reveal
which objects matter). Accusation options are shuffled per case, because listing the
true motive first makes "always pick option one" a winning strategy.

## Roadmap

| Phase | Status |
|---|---|
| 1. Scaffold + dummy case, full loop | done |
| 2. Case generation | done |
| 3. Room images, all rooms in parallel | done |
| 4. Live NPC chat with conversation memory | done |
| 5. Persona narration layer | done |
| 6. Voices | done |

### Voice, and integrating with a host backend

Voice ids are treated as data, not constants. A `Persona` carries its own `voice_id`
and an `NPC` carries theirs; `tts.voice_for_persona` / `voice_for_npc` fall back to
`PERSONA_VOICE_ID` / `NPC_VOICE_ID` only when the character has none. A backend that
owns persona identity can supply a real ElevenLabs voice per persona without touching
game code — that fallback is the whole integration seam.

Speech is a separate `POST /api/speak` call rather than part of the reply. Synthesis
takes roughly as long as generating the line itself, and making the player wait to
*read* an answer until it can be *spoken* would give back the latency the engine works
hard for. Text renders immediately; audio catches up. Output is cached by
(voice, model, text) because ElevenLabs bills per character.

Note that an ElevenLabs key can be permission-scoped: ours returns 401 on
`/user/subscription` and `/models` while `/text-to-speech` works fine. Do not conclude
a key is invalid from the metadata endpoints — test the endpoint you actually need.

### Model notes (verified live, 2026-07-25)

`gemini-2.5-flash` returns **404 "no longer available to new users"** for new API
keys, even though `models.list()` still reports it.

Case generation uses `gemini-3.5-flash` with `thinking_budget=0`. Measured on a full
case JSON: `gemini-3.6-flash` spends ~4.7k thinking tokens for **36.5s** and rejects
`thinking_budget=0` with a 400; `gemini-3.5-flash` with thinking off produces an
equally playable case in **11.5s**. Override with `GEMINI_TEXT_MODEL`.

### Generated cases are not trusted

A case can be valid JSON and still be an unplayable game. `_build` in
`engine/case_gen.py` repairs what it can and rejects what it cannot: clues attached to
no hotspot are re-homed (otherwise they are unfindable and can strand the player in
room one), NPC hotspots pointing at nobody are demoted to objects, room clue lists are
derived rather than believed, and a killer who is not one of the suspects fails the
case. Three attempts, then the fixture — a rate limit mid-demo degrades to a working
game instead of a stack trace.

The prompt also seeds the setting and the naming tradition, and avoids recently used
seeds. Left alone the model returned a victim named Arthur Pendelton in three
consecutive runs, and picked the same setting twice in a row.

Design doc: [docs/superpowers/specs/2026-07-25-persona-detective-game-design.md](docs/superpowers/specs/2026-07-25-persona-detective-game-design.md)

API keys will be read from env vars (`.env`, gitignored) starting in Phase 2. None
are needed to run Phase 1.
