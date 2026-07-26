"""Find where things actually are in the finished room art.

Hotspot rectangles are invented by a text model that never sees the image, so they only
ever approximate the picture. This closes the loop: once a room is painted, locate each
clickable thing in the real pixels and rewrite the coordinates from what is there.

Measured on real room art against boxes read by eye (mean IoU over three objects):
    nvidia/nemotron-nano-12b-v2-vl:free              0.94   free
    nvidia/nemotron-3-nano-omni-30b-a3b-reasoning    0.90   free, ~2x faster
    google/gemma-4-26b-a4b-it:free                   0.89   free
    gemini-3.5-flash                                 0.91   capped at 20 calls/day
    qwen/qwen3.6-27b                                 0.13   misses standing people

So detection runs on OpenRouter's free tier and costs nothing. Free endpoints do get
rate-limited (gemma-4-31b returned 429 mid-benchmark), hence the fallback chain.

Never raises and never blocks a room: if every model fails, the written coordinates
stand and the game plays exactly as before.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path

import httpx

from .. import config
from ..models import GameCase, Hotspot, Room

log = logging.getLogger(__name__)

PROMPT = """Detect each of these numbered things in the image:
{items}

Return ONLY a JSON object, no explanation:
{{"items":[{{"id":1,"x1":0.0,"y1":0.0,"x2":0.0,"y2":0.0}}]}}

"id" is the number of the thing from the list above — this is how the answer is
matched, so it must be right.
x1,y1 = top-left corner, x2,y2 = bottom-right corner of a TIGHT box around the object,
as fractions of image width and height (0.0 to 1.0).
If something on the list is not visible in the image, omit that entry entirely rather
than guessing a box for it."""


def available() -> bool:
    return config.VISION_ENABLED and bool(config.OPENROUTER_API_KEY)


def _search_term(case: GameCase, hotspot: Hotspot) -> str:
    """What to ask the detector for.

    A hotspot's label is a person's name, which means nothing to a detector. There is
    exactly one NPC per room, so "the person standing in the room" is both describable
    and unambiguous.
    """
    if hotspot.kind != "npc":
        return hotspot.label.lower()
    npc = case.npc(hotspot.npc_name or "")
    if npc and npc.role:
        return f"the person standing in the room ({npc.role.split(',')[0].strip()[:40]})"
    return "the person standing in the room"


async def _detect(client: httpx.AsyncClient, model: str, b64: str, terms: list[str]):
    r = await client.post(
        f"{config.OPENROUTER_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": PROMPT.format(
                                items="\n".join(
                                    f"{i}. {t}" for i, t in enumerate(terms, 1)
                                )
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 3000,
        },
        timeout=config.VISION_TIMEOUT,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code}: {r.text[:160]}")
    text = r.json()["choices"][0]["message"]["content"] or ""
    match = re.search(r"\{[\s\S]*\}", text)  # reasoning models wrap the JSON in prose
    if not match:
        raise ValueError("no JSON in reply")
    return json.loads(match.group(0)).get("items", [])


def _as_fractions(box: tuple[float, float, float, float]):
    """Some models answer in 0-1000 or pixels regardless of the instruction."""
    if max(box) <= 1.5:
        return box
    divisor = 1000.0 if max(box) <= 1000 else 2048.0
    return tuple(v / divisor for v in box)


async def relocate_hotspots(case: GameCase, room: Room, image_path: Path) -> int:
    """Rewrite this room's hotspot boxes from the painted image. Returns how many moved."""
    if not available() or not room.hotspots or not image_path.exists():
        return 0

    terms = [_search_term(case, hs) for hs in room.hotspots]
    b64 = base64.b64encode(image_path.read_bytes()).decode()

    items = None
    async with httpx.AsyncClient() as client:
        for model in config.VISION_MODELS:
            try:
                items = await _detect(client, model, b64, terms)
                break
            except Exception as e:
                log.warning("Detection via %s failed (%s); trying next.", model, e)

    if not items:
        log.warning("No detector answered for %s; keeping written coordinates.", room.name)
        return 0

    # Matched on the list position the model was given. Matching on echoed label text
    # was too brittle — models paraphrase the label and every hotspot silently missed.
    found: dict[int, tuple] = {}
    for row in items:
        try:
            index = int(row["id"]) - 1
            box = (float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"]))
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= index < len(terms):
            found[index] = _as_fractions(box)

    moved = 0
    for index, hotspot in enumerate(room.hotspots):
        box = found.get(index)
        if not box:
            continue
        x1, y1, x2, y2 = box
        w, h = x2 - x1, y2 - y1
        # A degenerate or near-full-frame box is what a detector returns when it did
        # not really find the thing. Trusting it would cover the screen in a hotspot.
        if not (0.02 < w < 0.9 and 0.02 < h < 0.98):
            log.debug("Ignoring implausible box for %r: %.2fx%.2f", terms[index], w, h)
            continue
        hotspot.x = max(0.0, min(1.0, x1))
        hotspot.y = max(0.0, min(1.0, y1))
        hotspot.w = min(w, 1.0 - hotspot.x)
        hotspot.h = min(h, 1.0 - hotspot.y)
        moved += 1

    log.info("Placed %d/%d hotspots from the art in %s", moved, len(room.hotspots), room.name)
    return moved
