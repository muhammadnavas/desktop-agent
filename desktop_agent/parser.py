"""Deterministic fallback intent parser."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LaunchIntent:
    app_id: str


_APP_PATTERNS = {
    "notepad": (r"\bnotepad\b", r"\btext editor\b"),
    "calculator": (r"\bcalculator\b", r"\bcalc\b"),
    "explorer": (r"\bfile explorer\b", r"\bwindows explorer\b", r"\bexplorer\b"),
    "vscode": (r"\bvs\s*code\b", r"\bvisual studio code\b", r"\bcode editor\b"),
    "whatsapp": (r"\bwhats\s*app\b", r"\bwhatsapp\b"),
}


def parse_command(text: str) -> LaunchIntent | None:
    if not isinstance(text, str) or not text.strip():
        return None
    normalized = text.lower().strip()
    if not re.search(r"\b(open|launch|start|run)\b", normalized) or re.search(r"\b(close|quit|exit|terminate)\b", normalized):
        return None
    for app_id, patterns in _APP_PATTERNS.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            return LaunchIntent(app_id)
    return None


def parse_close_command(text: str) -> LaunchIntent | None:
    """Recognize explicit close/quit requests for allowlisted applications."""
    if not isinstance(text, str) or not text.strip():
        return None
    normalized = text.lower().strip()
    if not re.search(r"\\b(close|quit|exit)\\b", normalized):
        return None
    for app_id, patterns in _APP_PATTERNS.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            return LaunchIntent(app_id)
    return None
