"""Small local SQLite memory store for explicit, user-approved facts."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "agent_memory.sqlite3"
DB_PATH = Path(os.getenv("DESKTOP_AGENT_MEMORY_DB", str(DEFAULT_DB)))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL
        )
        """
    )
    return connection


def remember(content: str, category: str = "general") -> dict[str, Any]:
    content = content.strip()
    category = category.strip().lower() or "general"
    if not content:
        raise ValueError("Memory content cannot be empty.")
    if len(content) > 1000:
        raise ValueError("Memory content must be 1000 characters or fewer.")
    if len(category) > 40:
        raise ValueError("Memory category must be 40 characters or fewer.")
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        cursor = connection.execute(
            "INSERT INTO memories(content, category, created_at) VALUES (?, ?, ?)",
            (content, category, created_at),
        )
        memory_id = cursor.lastrowid
    return {"id": memory_id, "content": content, "category": category, "created_at": created_at}


def list_memories(query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    with _connect() as connection:
        if query and query.strip():
            rows = connection.execute(
                "SELECT id, content, category, created_at FROM memories "
                "WHERE content LIKE ? OR category LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{query.strip()}%", f"%{query.strip()}%", limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT id, content, category, created_at FROM memories ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def delete_memory(memory_id: int) -> bool:
    with _connect() as connection:
        cursor = connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return cursor.rowcount > 0


def memory_context(limit: int = 10) -> str:
    """Return concise user-approved facts for prompt context."""
    items = list_memories(limit=limit)
    return "\n".join(f"- [{item['category']}] {item['content']}" for item in reversed(items))
