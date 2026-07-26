from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes.game import router as game_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Persona Detective Engine", version="0.1.0")

STATIC_DIR = Path(__file__).resolve().parent / "static"
(STATIC_DIR / "generated").mkdir(parents=True, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Generated room art is served from our own origin rather than hotlinked, so the game
# does not depend on a third-party CDN staying reachable mid-demo.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(game_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
