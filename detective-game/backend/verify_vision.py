"""Hotspot detection checks. Run: .venv\\Scripts\\python.exe verify_vision.py

Uses room art already on disk, so it costs detection calls only — no image credits.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from app import config
from app.engine import vision
from app.engine.case_gen import _load_fixture
from app.engine.images import STATIC_ROOT

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  -> ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def newest_art() -> Path | None:
    shots = sorted(STATIC_ROOT.glob("*/r1.jpg"), key=lambda p: p.stat().st_mtime)
    return shots[-1] if shots else None


async def main() -> None:
    print(f"\ndetectors (in order): {', '.join(config.VISION_MODELS)}")
    print(f"enabled: {vision.available()}")
    check("detection is configured", vision.available())

    art = newest_art()
    if art is None:
        print("  no generated room art on disk — run a case first")
        sys.exit(1)
    print(f"art: {art.parent.name}/{art.name}")

    # The art on disk belongs to some earlier case, not the fixture, so asking for
    # "cask 47" in a picture of a pub tests nothing. Relabel the hotspots to things
    # actually in this frame — what is under test is the placement mechanism, not
    # whether a detector can find objects that were never painted.
    case = _load_fixture()
    room = case.rooms[0]
    room.hotspots[0].label = "the person"          # every room is painted with one
    room.hotspots[1].label = "a bottle"
    room.hotspots[2].label = "a wooden chair or stool"
    before = [(h.label, h.x, h.y, h.w, h.h) for h in room.hotspots]

    moved = await vision.relocate_hotspots(case, room, art)
    check("hotspots were placed from the picture", moved > 0, f"{moved}/{len(room.hotspots)}")

    print("\n  label                     written box            detected box")
    changed = 0
    for (label, x, y, w, h), hs in zip(before, room.hotspots):
        same = (x, y, w, h) == (hs.x, hs.y, hs.w, hs.h)
        changed += 0 if same else 1
        print(f"    {label[:22]:24} x{x:.2f} y{y:.2f} {w:.2f}x{h:.2f}   "
              f"{'(unchanged)' if same else f'x{hs.x:.2f} y{hs.y:.2f} {hs.w:.2f}x{hs.h:.2f}'}")

    check("at least one box actually moved", changed > 0, f"{changed} moved")
    check(
        "every box stays inside the frame",
        all(0 <= h.x and 0 <= h.y and h.x + h.w <= 1.001 and h.y + h.h <= 1.001
            for h in room.hotspots),
    )
    check(
        "no box swallows the whole frame",
        all(h.w < 0.9 and h.h < 0.98 for h in room.hotspots),
        "a full-frame box means detection failed but was trusted",
    )

    print("\n  Detection is best-effort by design: if the quota is gone or a call fails,")
    print("  the written coordinates stand and the game still plays.")


asyncio.run(main())

print()
if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("Hotspot detection checks passed.")
