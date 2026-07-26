# Persona-Driven Infinite Detective Game — Design

Date: 2026-07-25
Status: approved, Phase 1 in progress

## What this is

A static, visual-novel-style detective game. Point-and-click, not movement-based.
An original host character (a "Persona") narrates a murder mystery that an LLM
generates fresh each time. The case-generation and investigation engine is
persona-agnostic: swapping the Persona config changes the host's voice and look,
not the game.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Backend | Python + FastAPI | User's call. `response_model` gives runtime-enforced field stripping. |
| Frontend | Vite + React + TypeScript + Tailwind | Hotspots are absolutely-positioned divs over an image. No physics engine. |
| State ownership | Server-authoritative, in-memory `dict[session_id, Session]` | Client cannot forge progress. One auditable leak surface. No Redis/Postgres. |
| Object hotspots | Persona narrates the examination | Reuses the persona layer; no second dialogue system. |
| Player input | Text only | Output TTS still happens. Keeps the input path deterministic for a 36h build. |
| Rooms per case | 3 | Halves Phase 3 image cost; demo bar is "explore 2 rooms". |
| Room unlock rule | 2 clues found in current room (`CLUES_TO_UNLOCK`) | Single tunable constant. |

## The redaction boundary

This is the load-bearing constraint of the whole build.

`GameCase` is the immutable hidden truth. It is constructed inside `store.py` and
never leaves it. Exactly one function crosses the boundary:

```
to_public(case, state) -> PublicView
```

Every route declares a public Pydantic `response_model`. FastAPI strips any field
not on the declared schema at serialization time, so a careless `return case`
drops the solution on the way out rather than shipping it.

Two non-obvious leaks designed out up front:

- `PublicRoom` carries no `clue_ids` and no unlock threshold. Otherwise the client
  can count how many clues remain in a room.
- `PublicHotspot` carries no `clue_ids`. Otherwise inspecting the DOM reveals which
  objects are load-bearing and which are set dressing, which gut the game.

`POST /api/solve` is the only route permitted to reveal solution fields, and only
after the player has committed an accusation.

## Data model

Hidden, server-only:

- `Clue` — `id, name, text, unlock_hint, keywords[]`
  `unlock_hint` describes what line of questioning surfaces the clue. Phase 1
  keyword-matches; Phase 4 hands `unlock_hint` to the LLM as the judgment
  criterion. Same field, two implementations, no schema churn between phases.
- `Hotspot` — `id, kind("npc"|"object"), label, x, y, w, h, npc_name?, clue_ids[]`
  Coordinates are normalized 0–1 over the scene image so they position correctly
  at any viewport size.
- `Room` — `id, name, image_prompt, image_url?, hotspots[], clue_ids[]`
- `NPC` — `name, role, voice_id, knowledge[], secrets[]`
  `secrets` are what the NPC admits only under pressure — the payload for the
  "are you lying?" beat.
- `GameCase` — `id, title, setting, victim, public_setup, timeline[], rooms[],
  npcs[], clues[], motive_options[], weapon_options[], solution`

`motive_options` and `weapon_options` exist because "picks suspect / motive /
weapon" implies menus, which require plausible decoys alongside the true answer.
Suspects are derived from NPC names.

Mutable progress:

- `GameState` — `discovered_clue_ids[], npc_trust{}, rooms_unlocked[],
  current_room, npc_conversation_history{}, history_summary{}, solved,
  solved_correctly`

## NPC memory

`npc_conversation_history[npc_name]` is a running log of `{role, text}` exchanges.
Only that NPC's own history goes into their prompt — never another NPC's.

Capped at the last 10 exchanges. When older exchanges fall off, they are condensed
into a one-line `history_summary[npc_name]` rather than dropped, so early
contradictions still have weight late in a long interrogation.

## Endpoints

| Route | Returns |
|---|---|
| `GET /api/personas` | the three hosts |
| `POST /api/case/new` | `{session_id, view, intro}` |
| `GET /api/session/{id}` | `{view}` |
| `POST /api/hotspot/ask` | `{speaker, reply, clue_unlocked?, trust_delta, persona_reaction?, view}` |
| `POST /api/solve` | `{correct, narration, truth}` |

Room unlocking rides along in the `ask` response rather than getting its own
endpoint — the state change already happens there.

## Personas (original characters)

- **Inspector Vesper Quill** — clipped, dry, treats the player as a promising but
  sloppy protégé.
- **Bix Marrow** — over-caffeinated true-crime podcaster, narrates everything as a
  cliffhanger.
- **Madame Corvina Ashgrave** — theatrical spiritualist who claims the dead whisper
  to her; she is in fact just very observant.

Deliberately far apart in register so that swapping personas is visibly a different
show — that is the persona-agnostic claim the demo has to make.

## Build order

1. **Scaffold + dummy case.** Full click → hotspot → chat → clue-unlock → accuse
   loop with a hardcoded fixture and keyword-matched replies. No LLM.
2. **Gemini case generation.** Verify hidden JSON never reaches the frontend.
3. **Gemini image generation**, all rooms in parallel via `asyncio.gather`, loading
   state while in flight, first room revealed as soon as it is ready.
4. **Live NPC chat** with `npc_conversation_history` in the prompt.
5. **Persona layer** — intro, post-clue reactions, final reveal.
6. **Solve flow + ending narration.**

Pause after each phase for the user to test.

## Phase 1 success criteria

1. `POST /api/case/new` response contains zero occurrences of the killer's name or
   the string `solution`.
2. Asking an NPC a triggering question moves `discovered_clues` 0 → 1 and renders
   it in the clue tray.
3. Finding 2 clues in room 1 flips room 2 to `locked: false` and makes it clickable.
4. Correct accusation renders a win ending; incorrect renders a loss ending.
5. "New Case" fully resets state with no bleed from the prior session.

Rooms render as flat colored panels with labeled hotspot rectangles. Real images
are Phase 3; placeholder art now would be thrown away.

## Deferred / flagged risks

- **Image generation is the schedule risk**, not the LLM. Parallel generation makes
  total ≈ slowest room rather than the sum, but cost and failure handling scale
  with room count. Hence 3 rooms.
- **TTS on every NPC reply will feel slow.** Plan: render NPC text immediately with
  audio streaming behind it, and reserve guaranteed TTS for persona beats (intro,
  clue reactions, final reveal) where the voice actually sells the character.
- API keys via env vars only, never committed.
