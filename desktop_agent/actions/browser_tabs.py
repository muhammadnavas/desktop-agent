"""Guarded browser-tab shortcuts for the currently focused browser window."""

from __future__ import annotations

import os


_BROWSER_MARKERS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi")


def _active_browser() -> dict:
    from desktop_agent.actions.windows import get_active_window

    active = get_active_window()
    title = str(active.get("title") or "")
    if not any(marker in title.casefold() for marker in _BROWSER_MARKERS):
        raise RuntimeError(
            "A supported browser must be the active window. Supported browsers: Chrome, Edge, Firefox, Brave, Opera, and Vivaldi."
        )
    return active


def open_new_tab() -> dict:
    """Open a new tab in the currently focused supported browser."""
    if os.name != "nt":
        raise RuntimeError("Browser-tab shortcuts are supported on Windows only.")
    active = _active_browser()
    try:
        import pyautogui
    except ImportError as exc:
        raise RuntimeError('Install desktop support with: pip install -e ".[desktop]"') from exc
    pyautogui.hotkey("ctrl", "t")
    return {"success": True, "action": "open_new_tab", "window": active["title"]}


def close_current_tab() -> dict:
    """Close the active tab in the currently focused supported browser."""
    if os.name != "nt":
        raise RuntimeError("Browser-tab shortcuts are supported on Windows only.")
    active = _active_browser()
    try:
        import pyautogui
    except ImportError as exc:
        raise RuntimeError('Install desktop support with: pip install -e ".[desktop]"') from exc
    pyautogui.hotkey("ctrl", "w")
    return {"success": True, "action": "close_current_tab", "window": active["title"]}
