"""SQLite-backed user and memory storage."""

import sqlite3
from pathlib import Path


_DB_PATH = Path("data") / "memory.db"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                gender TEXT NOT NULL DEFAULT '',
                basics TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                character_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS long_term_memories (
                user_id TEXT NOT NULL,
                character_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                PRIMARY KEY (user_id, character_id)
            );
            """
        )


def create_user(user_id: str, email: str, password: str, name: str, gender: str, basics: str) -> dict:
    with _connect() as connection:
        connection.execute(
            "INSERT INTO users (id, email, password, name, gender, basics) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, email, password, name, gender, basics),
        )
    return authenticate_user(email, password)


def authenticate_user(email: str, password: str) -> dict:
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, email, name, gender, basics FROM users WHERE email = ? AND password = ?",
            (email, password),
        ).fetchone()
    return dict(row) if row else {}


def update_user_profile(user_id: str, name: str, gender: str, basics: str) -> dict:
    with _connect() as connection:
        connection.execute(
            "UPDATE users SET name = ?, gender = ?, basics = ? WHERE id = ?",
            (name, gender, basics, user_id),
        )
        row = connection.execute(
            "SELECT id, email, name, gender, basics FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else {}


def get_profile(user_id: str) -> dict:
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, email, name, gender, basics FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else {}


def add_message(user_id: str, character_id: str, role: str, content: str) -> None:
    with _connect() as connection:
        connection.execute(
            "INSERT INTO messages (user_id, character_id, role, content) VALUES (?, ?, ?, ?)",
            (user_id, character_id, role, content),
        )


def get_short_term_memory(user_id: str, character_id: str, limit: int = 12) -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT role, content FROM messages WHERE user_id = ? AND character_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, character_id, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def get_long_term_memory(user_id: str, character_id: str) -> str:
    with _connect() as connection:
        row = connection.execute(
            "SELECT summary FROM long_term_memories WHERE user_id = ? AND character_id = ?",
            (user_id, character_id),
        ).fetchone()
    return row[0] if row else ""


def save_long_term_memory(user_id: str, character_id: str, summary: str) -> None:
    with _connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO long_term_memories (user_id, character_id, summary) VALUES (?, ?, ?)",
            (user_id, character_id, summary),
        )


def clear_memory(user_id: str, character_id: str) -> None:
    with _connect() as connection:
        connection.execute("DELETE FROM messages WHERE user_id = ? AND character_id = ?", (user_id, character_id))
        connection.execute(
            "DELETE FROM long_term_memories WHERE user_id = ? AND character_id = ?",
            (user_id, character_id),
        )
