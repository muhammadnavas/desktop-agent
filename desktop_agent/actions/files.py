"""Full-filesystem file operations for the local desktop agent."""

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


def resolve_file_path(path: str) -> Path:
    """Resolve an absolute path anywhere on this PC or a relative path from the default root.

    DESKTOP_AGENT_WORKSPACE remains an optional convenience for relative paths only.
    Absolute drive paths, UNC paths, and parent-directory traversal are supported.
    """
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path must be non-empty text.")
    if len(path) > 1000:
        raise ValueError("path is too long.")
    expanded = Path(path.strip()).expanduser()
    if not expanded.is_absolute() and not expanded.drive:
        expanded = workspace_root() / expanded
    return expanded.resolve()


_resolve_workspace_file = resolve_file_path


def read_file(path: str) -> dict[str, Any]:
    """Read a bounded UTF-8 text file from any accessible local path."""
    target = _resolve_workspace_file(path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File not found in workspace: {path}")
    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError("File is larger than the 1 MB read limit.")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Only UTF-8 text files can be read by this tool.") from exc
    return {"success": True, "path": str(target),
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
        "path": str(target),
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
    # Resolve again immediately before writing to follow the final on-disk target.
    target = resolve_file_path(str(target))
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
        "path": str(target),
        "size_bytes": len(pending["content"].encode("utf-8")),
        "overwrote_existing": pending["overwrites_existing"],
    }


def create_folder(path: str) -> dict[str, Any]:
    """Create a directory at any accessible local path; never overwrite an existing file."""
    target = _resolve_workspace_file(path)
    if target.exists():
        if target.is_dir():
            return {"success": True, "created": False, "already_exists": True,
                    "path": str(target)}
        raise FileExistsError(f"A file already exists at this path: {path}")
    target.mkdir(parents=True, exist_ok=False)
    return {"success": True, "created": True, "already_exists": False,
            "path": str(target)}
