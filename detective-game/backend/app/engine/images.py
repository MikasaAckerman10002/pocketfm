"""Room scene art.

Every room's image is requested at once via asyncio.gather, so total time is the
slowest room rather than the sum. `/api/case/new` waits only for the first room and
lets the rest land in the background, which is what makes later rooms feel instant.

Two providers behind one interface:
  nanobanana - task-based. POST returns a taskId, then poll until it reports success.
  gemini     - direct, returns image bytes inline. Currently 429s on a free-tier key.

Images are downloaded and served from our own /static rather than hotlinked, so the
game does not depend on a third-party CDN staying up or allowing cross-origin loads
mid-demo.
"""

from __future__ import annotations

import asyncio
import logging
import struct
from pathlib import Path

import httpx

from .. import config
from ..models import GameCase, Hotspot, Room

log = logging.getLogger(__name__)

STATIC_ROOT = Path(__file__).resolve().parent.parent / "static" / "generated"

# Art direction appended to every room prompt. Text is excluded because generated
# lettering comes out garbled; people are now included deliberately — see _placement.
# No "16:9" in the text: the ratio is set by the aspectRatio parameter, and asking for
# it in the prompt as well tends to make the model paint letterbox bars into the art.
STYLE = (
    "Detective game scene art, moody cinematic lighting, deep shadows, "
    "rich colour, painterly realism, wide establishing shot. "
    "No text, no words, no letters, no watermark, no UI, no speech bubbles."
)


def _zone(hs: Hotspot) -> str:
    """Turn a hotspot's box into words a painter can act on.

    Hotspot coordinates are invented before the picture exists, so the picture has to
    be painted around them rather than the other way round. Describing where each
    thing belongs is what keeps the clickable boxes and the art in register.
    """
    cx, cy = hs.x + hs.w / 2, hs.y + hs.h / 2
    across = (
        "far left" if cx < 0.2
        else "left" if cx < 0.4
        else "centre" if cx < 0.6
        else "right" if cx < 0.8
        else "far right"
    )
    depth = "background" if cy < 0.35 else "middle distance" if cy < 0.65 else "foreground"
    return f"{across} of frame, {depth}"


def _short_role(role: str) -> str:
    """'Cellar hand and apprentice distiller, twenty-three, worked here…' -> the job."""
    return role.split(",")[0].strip()[:70]


def _placement(case: GameCase, room: Room) -> str:
    """Tell the artist where the clickable things are, so they get painted there."""
    people, things = [], []
    for hs in room.hotspots:
        if hs.kind == "npc":
            npc = case.npc(hs.npc_name or "")
            who = _short_role(npc.role) if npc else "a bystander"
            people.append(f"{who} standing at the {_zone(hs)}, full body in shot")
        else:
            things.append(f"{hs.label.lower()} at the {_zone(hs)}")

    parts = []
    if people:
        parts.append(
            f"Exactly {len(people)} character(s) present, painted clearly and facing "
            "the viewer: " + "; ".join(people) + "."
        )
    else:
        parts.append("No people in this room.")
    if things:
        parts.append("Clearly visible: " + "; ".join(things) + ".")
    return " ".join(parts)


def _prompt_for(case: GameCase, room: Room) -> str:
    return f"{room.image_prompt.rstrip('.')}. {_placement(case, room)} {STYLE}"


def dimensions(path: Path) -> tuple[int, int]:
    """Width/height from a PNG or JPEG header, without pulling in Pillow."""
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    i = 2  # JPEG: walk segment markers to the SOFn frame header
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker, length = data[i + 1], struct.unpack(">H", data[i + 2 : i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        i += 2 + length
    raise ValueError(f"Could not read dimensions from {path.name}")


async def _download(client: httpx.AsyncClient, url: str, dest: Path) -> str | None:
    try:
        r = await client.get(url, timeout=60)
        r.raise_for_status()
    except Exception as e:
        log.warning("Could not download %s: %s", url, e)
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return config.static_url("generated", dest.parent.name, dest.name)


async def _nanobanana(
    client: httpx.AsyncClient, case: GameCase, room: Room, dest: Path
) -> str | None:
    headers = {"Authorization": f"Bearer {config.NANOBANANA_API_KEY}"}
    # generate-2 rather than generate: it accepts aspectRatio, which the older endpoint
    # ignores. callBackUrl is omitted because localhost cannot receive a webhook.
    body = {
        "prompt": _prompt_for(case, room),
        "imageUrls": [],  # empty = pure text-to-image
        "aspectRatio": config.IMAGE_ASPECT_RATIO,
        "resolution": config.IMAGE_RESOLUTION,
        "outputFormat": config.IMAGE_FORMAT,
    }

    r = await client.post(
        f"{config.NANOBANANA_BASE}/generate-2", json=body, headers=headers, timeout=60
    )
    r.raise_for_status()
    payload = r.json()

    # 402 is worth calling out by name: nothing in the code is wrong, the account is
    # simply out of credits, and every room will fail identically until it is topped up.
    if payload.get("code") == 402:
        log.error(
            "Nano Banana account is out of credits - room art disabled, falling back "
            "to colour plates. Top up at nanobananaapi.ai or set IMAGE_PROVIDER=off."
        )
        return None

    task_id = (payload.get("data") or {}).get("taskId")
    if not task_id:
        log.warning("No taskId for %s: %s", room.name, str(payload)[:200])
        return None

    deadline = asyncio.get_running_loop().time() + config.IMAGE_TIMEOUT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(config.IMAGE_POLL_SECONDS)
        try:
            s = await client.get(
                f"{config.NANOBANANA_BASE}/record-info",
                params={"taskId": task_id},
                headers=headers,
                timeout=30,
            )
            s.raise_for_status()
            data = s.json()
        except Exception as e:
            log.warning("Poll failed for %s: %s", room.name, e)
            continue

        # The status fields are documented at the top level but some responses nest
        # them under "data", so accept either shape.
        body_ = data.get("data") if isinstance(data.get("data"), dict) else data
        flag = body_.get("successFlag")
        if flag == 1:
            url = (body_.get("response") or {}).get("resultImageUrl")
            if not url:
                log.warning("Success without an image url for %s", room.name)
                return None
            return await _download(client, url, dest)
        if flag in (2, 3):
            log.warning("Generation failed for %s: %s", room.name, body_.get("errorMessage"))
            return None

    log.warning("Timed out waiting for %s", room.name)
    return None


async def _gemini(case: GameCase, room: Room, dest: Path) -> str | None:
    from google.genai import types

    from .gemini import _client

    r = await _client().aio.models.generate_content(
        model=config.IMAGE_MODEL,
        contents=_prompt_for(case, room),
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    for candidate in r.candidates or []:
        for part in candidate.content.parts or []:
            blob = getattr(part, "inline_data", None)
            if blob and blob.data:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(blob.data)
                return f"/static/generated/{dest.parent.name}/{dest.name}"
    log.warning("No image part returned for %s", room.name)
    return None


async def _one_room(case: GameCase, room: Room) -> None:
    """Generate a single room's art and attach it. Never raises."""
    provider = config.image_provider()
    ext = "png" if provider == "gemini" else config.IMAGE_FORMAT
    dest = STATIC_ROOT / case.id / f"{room.id}.{ext}"
    started = asyncio.get_running_loop().time()
    try:
        async with httpx.AsyncClient() as client:
            if provider == "nanobanana":
                url = await _nanobanana(client, case, room, dest)
            elif provider == "gemini":
                url = await _gemini(case, room, dest)
            else:
                url = None
    except Exception as e:
        # One room failing must not take down the case; it falls back to its plate.
        log.warning("Image failed for %s: %s: %s", room.name, type(e).__name__, e)
        url = None

    room.image_url = url

    # Now that the art exists, move the hotspots onto what was actually painted. This
    # is part of the room's task rather than a later pass, so a room is only revealed
    # once its boxes match its picture.
    if url:
        from . import vision

        await vision.relocate_hotspots(case, room, dest)

    # Per-room timing, because this provider appears to serialize concurrent requests
    # (one room alone ~33s, three together ~107s) and that is worth watching.
    elapsed = asyncio.get_running_loop().time() - started
    log.info("Room %-28s %5.1fs  %s", room.name, elapsed, url or "no image (using plate)")


def start_generation(case: GameCase) -> list[asyncio.Task[None]]:
    """Fire every room at once and return the tasks, first room first.

    The caller awaits only tasks[0] before revealing the game; the rest finish while
    the player is reading the intro, which is what makes room two feel instant.
    Tasks must be kept referenced by the caller or the loop may garbage-collect them.
    """
    if config.image_provider() == "off":
        log.info("Image generation disabled; using colour plates.")
        return []
    return [asyncio.create_task(_one_room(case, room)) for room in case.rooms]


async def generate_all(case: GameCase) -> None:
    """Blocking variant, for scripts and verification."""
    tasks = start_generation(case)
    if tasks:
        await asyncio.gather(*tasks)
