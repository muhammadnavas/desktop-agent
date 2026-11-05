"""Small deterministic intent parser for NOVA v0.1."""

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
}


def parse_command(text: str) -> LaunchIntent | None:
    """Return a supported launch intent, or None for unsupported requests."""
    if not isinstance(text, str) or not text.strip():
        return None

    normalized = text.lower().strip()
    # Require an explicit launch-style verb to avoid accidental activation.
    if not re.search(r"\b(open|launch|start|run)\b", normalized):
        return None

    for app_id, patterns in _APP_PATTERNS.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            return LaunchIntent(app_id=app_id)

    return None
