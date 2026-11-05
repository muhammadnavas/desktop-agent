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


_BLOCKED_CONTROL_NAMES = (
    "delete", "remove", "purchase", "checkout", "pay", "payment",
    "transfer", "send", "submit order", "format", "reset password",
)


def _find_button(window_title: str, button_name: str):
    """Resolve one exact, visible, enabled Button control."""
    if os.name != "nt":
        raise RuntimeError("Windows UI Automation is supported on Windows only.")
    if not isinstance(window_title, str) or not window_title.strip() or len(window_title) > 200:
        raise ValueError("window_title must be a non-empty string of at most 200 characters.")
    if not isinstance(button_name, str) or not button_name.strip() or len(button_name) > 120:
        raise ValueError("button_name must be a non-empty string of at most 120 characters.")
    if any(term in button_name.casefold() for term in _BLOCKED_CONTROL_NAMES):
        raise ValueError("This button label is considered sensitive or destructive and is blocked.")
    try:
        from pywinauto import Desktop
    except ImportError as exc:
        raise RuntimeError("UI Automation is not installed. Run: pip install -e .[desktop]") from exc

    title_matches = []
    for window in Desktop(backend="uia").windows():
        try:
            title = window.window_text()
            if title and title.casefold() == window_title.strip().casefold() and window.is_visible():
                title_matches.append(window)
        except Exception:
            continue
    if len(title_matches) != 1:
        raise ValueError("The exact window title must identify one visible window.")
    window = title_matches[0]
    matches = []
    try:
        descendants = window.descendants(control_type="Button")
    except Exception as exc:
        raise RuntimeError(f"Could not inspect buttons in '{window_title}': {exc}") from exc
    for control in descendants:
        try:
            info = control.element_info
            name = str(getattr(info, "name", "") or "").strip()
            if name.casefold() == button_name.strip().casefold() and control.is_visible() and control.is_enabled():
                matches.append(control)
        except Exception:
            continue
    if len(matches) != 1:
        raise ValueError(
            "The button must match exactly one visible, enabled Button control; "
            f"found {len(matches)} matches."
        )
    return title_matches[0], matches[0]


def click_button(window_title: str, button_name: str) -> dict[str, Any]:
    """Click one exact accessible Button; caller must enforce explicit approval."""
    window, button = _find_button(window_title, button_name)
    button.click_input()
    return {
        "success": True,
        "window_title": window.window_text(),
        "button_name": button_name.strip(),
        "action": "click",
    }


def inspect_button_target(window_title: str, button_name: str) -> dict[str, Any]:
    """Resolve a unique button and return a confirmation preview without clicking."""
    window, button = _find_button(window_title, button_name)
    return {
        "available": True,
        "window_title": window.window_text(),
        "button_name": str(button.element_info.name).strip(),
        "control_type": "Button",
        "enabled": True,
        "action": "click",
    }
