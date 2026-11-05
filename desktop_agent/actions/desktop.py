"""Guarded desktop interaction primitives. Coordinates are screen-relative."""

import base64
import io
import os
import time
from typing import Any


_ALLOWED_SINGLE_KEYS = {
    "enter", "tab", "esc", "space", "backspace", "up", "down", "left",
    "right", "home", "end", "pageup", "pagedown",
}
_ALLOWED_COMBINATIONS = {
    ("ctrl", "l"),       # Focus browser address bar.
    ("ctrl", "a"),       # Select current field/document.
    ("alt", "left"),     # Browser back.
    ("alt", "right"),    # Browser forward.
    ("shift", "tab"),    # Previous form control.
}
_BLOCKED_TEXT_TERMS = (
    "password", "passcode", "one-time code", "otp", "credit card",
    "bank account", "secret key", "delete", "erase", "format drive",
    "payment", "purchase", "checkout",
)


def capture_screenshot() -> dict[str, Any]:
    """Capture the primary display and return a data URL plus dimensions."""
    if os.name != "nt":
        raise RuntimeError("Desktop interaction is currently supported on Windows only.")
    try:
        import pyautogui
    except ImportError as exc:
        raise RuntimeError("Desktop controls are not installed. Run: pip install -e .[desktop]") from exc

    image = pyautogui.screenshot()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "image": f"data:image/png;base64,{encoded}",
        "width": image.width,
        "height": image.height,
        "captured_at": time.time(),
    }


def validate_steps(steps: Any) -> list[dict[str, Any]]:
    """Validate a small, explicit action vocabulary before showing a plan."""
    if not isinstance(steps, list) or not 1 <= len(steps) <= 12:
        raise ValueError("A task must contain between 1 and 12 steps.")

    validated: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"Step {index + 1} is invalid.")
        action = step.get("action")
        if action in {"click", "move"}:
            x, y = step.get("x"), step.get("y")
            if type(x) is not int or type(y) is not int or not (0 <= x < 100000 and 0 <= y < 100000):
                raise ValueError(f"Step {index + 1} has invalid pointer coordinates.")
            target = step.get("target", "visible screen location")
            if not isinstance(target, str) or not target.strip() or len(target) > 100:
                raise ValueError(f"Step {index + 1} has an invalid target description.")
            if action == "move":
                duration = step.get("duration", 0.2)
                if type(duration) not in (int, float) or not 0 <= duration <= 2:
                    raise ValueError(f"Step {index + 1} has invalid movement duration.")
                validated.append({
                    "action": "move", "x": x, "y": y,
                    "target": target.strip(), "duration": float(duration),
                })
            else:
                validated.append({
                    "action": "click", "x": x, "y": y,
                    "target": target.strip(), "button": "left",
                })
        elif action == "type":
            value = step.get("text")
            if not isinstance(value, str) or not value or len(value) > 2000:
                raise ValueError(f"Step {index + 1} has invalid text.")
            if any(term in value.lower() for term in _BLOCKED_TEXT_TERMS):
                raise ValueError(f"Step {index + 1} contains sensitive or destructive text and is blocked.")
            validated.append({"action": "type", "text": value})
        elif action == "press":
            keys = step.get("keys")
            if not isinstance(keys, list) or not 1 <= len(keys) <= 2:
                raise ValueError(f"Step {index + 1} has invalid keys.")
            normalized = tuple(str(key).lower() for key in keys)
            if len(normalized) == 1:
                if normalized[0] not in _ALLOWED_SINGLE_KEYS:
                    raise ValueError(f"Step {index + 1} contains a blocked or unsupported key.")
            elif normalized not in _ALLOWED_COMBINATIONS:
                raise ValueError(f"Step {index + 1} contains a blocked or unsupported key combination.")
            validated.append({"action": "press", "keys": list(normalized)})
        elif action == "scroll":
            amount = step.get("amount")
            if type(amount) is not int or not -5 <= amount <= 5 or amount == 0:
                raise ValueError(f"Step {index + 1} has invalid scroll amount.")
            validated.append({"action": "scroll", "amount": amount})
        elif action == "wait":
            seconds = step.get("seconds", 1)
            if type(seconds) not in (int, float) or not 0 <= seconds <= 3:
                raise ValueError(f"Step {index + 1} has invalid wait duration.")
            validated.append({"action": "wait", "seconds": float(seconds)})
        else:
            raise ValueError(f"Step {index + 1} uses an unsupported action.")
    return validated


def execute_steps(steps: list[dict[str, Any]], screen_width: int, screen_height: int) -> list[dict[str, str]]:
    """Execute an already-approved plan, stopping immediately if an action fails."""
    if os.name != "nt":
        raise RuntimeError("Desktop interaction is currently supported on Windows only.")
    try:
        import pyautogui
    except ImportError as exc:
        raise RuntimeError("Desktop controls are not installed. Run: pip install -e .[desktop]") from exc

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.15
    results = []
    for index, step in enumerate(steps):
        action = step["action"]
        if action in {"click", "move"}:
            if step["x"] >= screen_width or step["y"] >= screen_height:
                raise ValueError(f"Step {index + 1} points outside the captured screen.")
            if action == "move":
                pyautogui.moveTo(step["x"], step["y"], duration=step["duration"])
            else:
                pyautogui.click(step["x"], step["y"], button="left")
        elif action == "type":
            pyautogui.write(step["text"], interval=0.01)
        elif action == "press":
            if len(step["keys"]) == 1:
                pyautogui.press(step["keys"][0])
            else:
                pyautogui.hotkey(*step["keys"])
        elif action == "scroll":
            pyautogui.scroll(step["amount"])
        elif action == "wait":
            time.sleep(step["seconds"])
        results.append({"step": str(index + 1), "status": "completed"})
    return results
