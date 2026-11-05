"""Workspace-scoped file operations for the local desktop agent."""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from threading import Lock
from typing import Any

MAX_READ_BYTES = 1_000_000
MAX_WRITE_BYTES = 1_000_000
_CONFIRMATION_TTL = 120
_pending_writes: dict[str, dict[str, Any]] = {}
_pending_lock = Lock()


def workspace_root() -> Path:
    """Return the configured file workspace (defaults to the process directory)."""
    configured = os.getenv("DESKTOP_AGENT_WORKSPACE")
    root = Path(configured).expanduser() if configured else Path.cwd()
    return root.resolve()


def _resolve_workspace_file(relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("path must be a non-empty relative path.")
    if len(relative_path) > 500:
        raise ValueError("path is too long.")
    candidate = Path(relative_path)
    if candidate.is_absolute() or candidate.drive or any(part == ".." for part in candidate.parts):
        raise ValueError("Only relative paths inside the configured workspace are allowed.")
    root = workspace_root()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("The requested path is outside the configured workspace.") from exc
    return resolved


def read_file(path: str) -> dict[str, Any]:
    """Read a bounded UTF-8 text file inside the configured workspace."""
    target = _resolve_workspace_file(path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File not found in workspace: {path}")
    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError("File is larger than the 1 MB read limit.")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Only UTF-8 text files can be read by this tool.") from exc
    return {"success": True, "path": target.relative_to(workspace_root()).as_posix(),
            "content": content, "size_bytes": len(content.encode("utf-8"))}


def prepare_file_write(path: str, content: str) -> dict[str, Any]:
    """Stage a workspace text-file write; never write until explicit confirmation."""
    if not isinstance(content, str):
        raise ValueError("content must be text.")
    size = len(content.encode("utf-8"))
    if size > MAX_WRITE_BYTES:
        raise ValueError("File writes are limited to 1 MB.")
    target = _resolve_workspace_file(path)
    if target.exists() and not target.is_file():
        raise ValueError("The target path is not a regular file.")
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _pending_lock:
        for key in list(_pending_writes):
            if now - _pending_writes[key]["created_at"] > _CONFIRMATION_TTL:
                _pending_writes.pop(key, None)
        _pending_writes[token] = {
            "path": target,
            "content": content,
            "created_at": now,
            "overwrites_existing": target.exists(),
        }
    return {
        "success": True,
        "requires_confirmation": True,
        "confirmation_token": token,
        "path": target.relative_to(workspace_root()).as_posix(),
        "size_bytes": size,
        "overwrites_existing": target.exists(),
        "preview": content[:2000],
        "preview_truncated": len(content) > 2000,
        "expires_in_seconds": _CONFIRMATION_TTL,
        "message": "File write staged. Nothing has been written yet; explicit confirmation is required.",
    }


def confirm_file_write(token: str) -> dict[str, Any]:
    """Consume a one-time approval and atomically write its staged UTF-8 content."""
    with _pending_lock:
        pending = _pending_writes.pop(token, None)
    if not pending:
        raise KeyError("This file-write approval is invalid, expired, or already used.")
    if time.monotonic() - pending["created_at"] > _CONFIRMATION_TTL:
        raise TimeoutError("This file-write approval expired. Stage the write again.")
    target: Path = pending["path"]
    # Re-resolve to detect workspace changes or symlink substitution after staging.
    relative = target.relative_to(workspace_root())
    target = _resolve_workspace_file(relative.as_posix())
    if target.exists() and not target.is_file():
        raise ValueError("The target path is no longer a regular file.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
    try:
        temporary.write_text(pending["content"], encoding="utf-8", newline="")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "success": True,
        "path": relative.as_posix(),
        "size_bytes": len(pending["content"].encode("utf-8")),
        "overwrote_existing": pending["overwrites_existing"],
    }
