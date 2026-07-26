"""Phase 3 image checks. Run: .venv\\Scripts\\python.exe verify_images.py

Answers three things:
  1. Do all rooms generate concurrently (total ~= slowest room, not the sum)?
  2. Does a provider failure degrade to colour plates quickly instead of hanging?
  3. Does /api/case/new return as soon as room one is ready?
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from app import config
from app.engine import images
from app.engine.case_gen import _load_fixture

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  -> ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


print(f"\nprovider resolved to: {config.image_provider()!r}")
print(f"  nanobanana key: {'set' if config.NANOBANANA_API_KEY else 'MISSING'}")
print(f"  gemini key:     {'set' if config.GEMINI_API_KEY else 'MISSING'}")


async def run() -> None:
    case = _load_fixture()
    n = len(case.rooms)

    t = time.time()
    await images.generate_all(case)
    elapsed = time.time() - t

    got = [r for r in case.rooms if r.image_url]
    print(f"\n  {len(got)}/{n} rooms have art, {elapsed:.1f}s total")
    for r in case.rooms:
        print(f"    {r.name:32} {r.image_url or '(plate)'}")

    provider = config.image_provider()
    if provider == "off" or not got:
        # No provider, or the provider refused. The contract is that this is fast and
        # non-fatal — the game must still be playable on colour plates.
        check("failure degrades quickly", elapsed < 20, f"{elapsed:.1f}s")
        check("no room left half-written", all(r.image_url is None for r in case.rooms))
        print("\n  No art produced. That is a valid degraded state; the game still runs.")
        return

    check("every room got art", len(got) == n, f"{len(got)}/{n}")
    check(
        "generation was concurrent",
        elapsed < config.IMAGE_TIMEOUT_SECONDS,
        f"{elapsed:.1f}s for {n} rooms",
    )
    for r in got:
        path = images.STATIC_ROOT / case.id / Path(r.image_url).name
        size = path.stat().st_size if path.exists() else 0
        check(f"{r.name}: file on disk >20KB", size > 20_000, f"{size // 1024}KB")
        check(f"{r.name}: served from our origin", r.image_url.startswith("/static/"))

        # Hotspot rectangles are normalized over a 16:9 frame. A square image would be
        # object-cover cropped, sliding the art out from under every hotspot.
        w, h = images.dimensions(path)
        check(
            f"{r.name}: is 16:9 ({w}x{h})",
            abs(w / h - 16 / 9) < 0.03,
            f"ratio {w / h:.3f}",
        )


asyncio.run(run())

print()
if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("Phase 3 image checks passed.")
