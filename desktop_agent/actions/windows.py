"""Read-only Windows window inspection tools.

These functions expose window metadata only; they do not click, type, or execute commands.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Any


def _user32():
    if os.name != "nt":
        raise RuntimeError("Window inspection is supported on Windows only.")
    return ctypes.WinDLL("user32", use_last_error=True)


def get_active_window() -> dict[str, Any]:
    """Return the foreground window handle and visible title."""
    user32 = _user32()
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return {"available": False, "title": "", "handle": None}
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(max(1, min(length + 1, 2048)))
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return {"available": True, "title": buffer.value, "handle": int(hwnd)}


def list_open_windows(limit: int = 30) -> dict[str, Any]:
    """List visible top-level windows with non-empty titles."""
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("limit must be an integer between 1 and 50.")

    user32 = _user32()
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    windows: list[dict[str, Any]] = []

    @callback_type
    def callback(hwnd, _lparam):
        if len(windows) >= limit:
            return False
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(min(length + 1, 2048))
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        title = buffer.value.strip()
        if title:
            windows.append({"title": title, "handle": int(hwnd)})
        return True

    user32.EnumWindows(callback, 0)
    return {"windows": windows, "count": len(windows), "limit": limit}
