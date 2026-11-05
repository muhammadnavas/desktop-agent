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
    resolved = expanded.resolve()
    sensitive_names = {".ssh", ".aws", ".azure", ".gnupg", "id_rsa", "id_ed25519"}
    if any(
        part.casefold() in sensitive_names
        or part.casefold().startswith(".env")
        or "credential" in part.casefold()
        or "secret" in part.casefold()
        or part.casefold().endswith((".pem", ".key"))
        for part in resolved.parts
    ):
        raise ValueError("Access to secret, credential, and private-key paths is blocked.")
    return resolved


_resolve_workspace_file = resolve_file_path


def read_file(path: str) -> dict[str, Any]:
    """Read a bounded UTF-8 text file from any accessible local path."""
    target = _resolve_workspace_file(path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File not found: {path}")
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


PROJECT_TEXT_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".sql", ".java", ".go", ".rs", ".cs"}
PROJECT_IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".next", "dist", "build"}


def _project_root(root: str) -> Path:
    target = resolve_file_path(root)
    if not target.exists() or not target.is_dir():
        raise FileNotFoundError(f"Project directory not found: {target}")
    return target


def list_project_files(root: str, limit: int = 100) -> dict[str, Any]:
    """List source/configuration files while skipping generated directories."""
    import os
    base = _project_root(root)
    if not isinstance(limit, int) or not 1 <= limit <= 120:
        raise ValueError("limit must be between 1 and 120.")
    found = []
    for current, dirs, names in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d.casefold() not in PROJECT_IGNORED_DIRS)
        for name in sorted(names):
            path = Path(current) / name
            if path.suffix.casefold() in PROJECT_TEXT_EXTENSIONS:
                found.append(path.relative_to(base).as_posix())
                if len(found) >= limit:
                    return {"success": True, "root": str(base), "files": found, "count": len(found), "truncated": True}
    return {"success": True, "root": str(base), "files": found, "count": len(found), "truncated": False}


def search_project(root: str, query: str, limit: int = 30) -> dict[str, Any]:
    """Search literal text in bounded UTF-8 source files."""
    import os
    base = _project_root(root)
    if not isinstance(query, str) or not query.strip() or len(query) > 200:
        raise ValueError("query must contain 1–200 characters.")
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")
    matches = []
    inspected = 0
    for current, dirs, names in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d.casefold() not in PROJECT_IGNORED_DIRS)
        for name in sorted(names):
            path = Path(current) / name
            if path.suffix.casefold() not in PROJECT_TEXT_EXTENSIONS:
                continue
            try:
                resolved = resolve_file_path(str(path))
                if resolved.stat().st_size > 80000:
                    continue
                content = resolved.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError, ValueError):
                continue
            inspected += 1
            for number, line in enumerate(content.splitlines(), 1):
                if query.casefold() in line.casefold():
                    matches.append({"file": resolved.relative_to(base).as_posix(), "line": number, "text": line[:500]})
                    if len(matches) >= limit:
                        return {"success": True, "root": str(base), "query": query, "files_inspected": inspected, "matches": matches, "truncated": True}
    return {"success": True, "root": str(base), "query": query, "files_inspected": inspected, "matches": matches, "truncated": False}


def list_directory(path: str, limit: int = 100) -> dict[str, Any]:
    """List a bounded set of files and folders in one directory."""
    target = _resolve_workspace_file(path)
    if not target.exists() or not target.is_dir():
        raise FileNotFoundError(f"Directory not found: {path}")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("limit must be an integer between 1 and 200.")
    sensitive_names = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519", ".ssh", ".aws", ".azure", ".gnupg"}
    entries = []
    truncated = False
    for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold())):
        name = child.name.casefold()
        if name in sensitive_names or name.startswith(".env") or "credential" in name or "secret" in name or name.endswith((".pem", ".key")):
            continue
        try:
            is_dir = child.is_dir()
            entries.append({
                "name": child.name,
                "type": "directory" if is_dir else "file",
                "size_bytes": None if is_dir else child.stat().st_size,
            })
        except OSError:
            continue
        if len(entries) >= limit:
            truncated = True
            break
    return {"success": True, "path": str(target), "entries": entries,
            "count": len(entries), "truncated": truncated}



def cancel_file_write(confirmation_token: str) -> dict[str, Any]:
    """Discard a staged write without changing the target file."""
    if not isinstance(confirmation_token, str) or not confirmation_token:
        raise ValueError("A confirmation token is required.")
    with _pending_lock:
        pending = _pending_writes.pop(confirmation_token, None)
    if pending is None:
        raise KeyError("This staged write is invalid, expired, or already used.")
    return {"success": True, "cancelled": True, "path": str(pending["path"])}
