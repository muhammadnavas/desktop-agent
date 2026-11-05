"""Local MongoDB memory store for explicit, user-approved facts."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("DESKTOP_AGENT_MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DATABASE = os.getenv("DESKTOP_AGENT_MONGO_DATABASE", "desktop_agent")
MONGO_COLLECTION = os.getenv("DESKTOP_AGENT_MONGO_COLLECTION", "memories")
_SERVER_SELECTION_TIMEOUT_MS = 2000
_client: MongoClient | None = None


def _collection() -> Collection:
    """Connect to the local MongoDB service and return the memories collection."""
    global _client
    try:
        if _client is None:
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=_SERVER_SELECTION_TIMEOUT_MS)
        _client.admin.command("ping")
        collection = _client[MONGO_DATABASE][MONGO_COLLECTION]
        collection.create_index("created_at")
        return collection
    except PyMongoError as exc:
        raise RuntimeError(
            f"Cannot connect to MongoDB at {MONGO_URI}. Start the local MongoDB service and try again."
        ) from exc


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
    document = {"content": content, "category": category, "created_at": created_at}
    try:
        result = _collection().insert_one(document)
    except PyMongoError as exc:
        raise RuntimeError(f"Could not save memory to MongoDB: {exc}") from exc
    return {"id": str(result.inserted_id), **document}


def list_memories(query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    filters: dict[str, Any] = {}
    if query and query.strip():
        pattern = re.escape(query.strip())
        filters["$or"] = [
            {"content": {"$regex": pattern, "$options": "i"}},
            {"category": {"$regex": pattern, "$options": "i"}},
        ]
    try:
        documents = _collection().find(filters).sort("created_at", -1).limit(limit)
        return [
            {"id": str(item["_id"]), "content": item["content"],
             "category": item["category"], "created_at": item["created_at"]}
            for item in documents
        ]
    except PyMongoError as exc:
        raise RuntimeError(f"Could not read memories from MongoDB: {exc}") from exc


def delete_memory(memory_id: str) -> bool:
    if not ObjectId.is_valid(memory_id):
        return False
    try:
        result = _collection().delete_one({"_id": ObjectId(memory_id)})
        return result.deleted_count > 0
    except PyMongoError as exc:
        raise RuntimeError(f"Could not delete memory from MongoDB: {exc}") from exc


def memory_context(limit: int = 10) -> str:
    """Return concise user-approved facts for prompt context."""
    items = list_memories(limit=limit)
    return "\n".join(
        f"- [{item['category']}] {item['content']}" for item in reversed(items)
    )


def mongo_status() -> dict[str, Any]:
    """Check the configured MongoDB connection without exposing credentials."""
    try:
        _collection()
        # Do not return the URI because it may contain credentials.
        return {
            "connected": True,
            "database": MONGO_DATABASE,
            "collection": MONGO_COLLECTION,
            "host": "local" if MONGO_URI.startswith(("mongodb://127.0.0.1", "mongodb://localhost")) else "configured",
        }
    except RuntimeError as exc:
        return {
            "connected": False,
            "database": MONGO_DATABASE,
            "collection": MONGO_COLLECTION,
            "error": str(exc),
        }
