"""Read-only Windows UI Automation inspection using the UIA accessibility tree."""

from __future__ import annotations

import os
from typing import Any


def get_window_controls(window_title: str, limit: int = 60) -> dict[str, Any]:
    """Return accessible control metadata without exposing field values."""
    if os.name != "nt":
        raise RuntimeError("Windows UI Automation is supported on Windows only.")
    if not isinstance(window_title, str) or not window_title.strip() or len(window_title) > 200:
        raise ValueError("window_title must be a non-empty string of at most 200 characters.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100.")
    try:
        from pywinauto import Desktop
    except ImportError as exc:
        raise RuntimeError("UI Automation is not installed. Run: pip install -e .[desktop]") from exc

    needle = window_title.strip().casefold()
    matches = []
    for window in Desktop(backend="uia").windows():
        try:
            title = window.window_text()
            if title and needle in title.casefold() and window.is_visible():
                matches.append((title, window))
        except Exception:
            continue
    if not matches:
        return {"available": False, "window_title": window_title.strip(), "controls": [], "count": 0}

    title, window = matches[0]
    try:
        descendants = window.descendants()
    except Exception as exc:
        raise RuntimeError(f"Could not inspect UI controls for '{title}': {exc}") from exc

    controls = []
    for control in descendants:
        if len(controls) >= limit:
            break
        try:
            info = control.element_info
            name = str(getattr(info, "name", "") or "").strip()
            control_type = str(getattr(info, "control_type", "") or "").strip()
            automation_id = str(getattr(info, "automation_id", "") or "").strip()
            if not name and not control_type and not automation_id:
                continue
            controls.append({
                "name": name[:200],
                "control_type": control_type[:80],
                "automation_id": automation_id[:120],
                "visible": bool(control.is_visible()),
                "enabled": bool(control.is_enabled()),
            })
        except Exception:
            continue

    return {
        "available": True,
        "window_title": title,
        "controls": controls,
        "count": len(controls),
        "truncated": len(descendants) > len(controls),
        "limit": limit,
    }
