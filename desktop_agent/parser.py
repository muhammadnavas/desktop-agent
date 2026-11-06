"""Deterministic fallback intent parser."""

import re
from urllib.parse import urlsplit
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


_WEBSITE_ALIASES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "chatgpt": "https://chatgpt.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "stackoverflow": "https://stackoverflow.com",
    "stackoverflow.com": "https://stackoverflow.com",
}


def parse_open_website_command(text: str) -> str | None:
    """Resolve an explicit website-opening request to a validated HTTP(S) URL."""
    if not isinstance(text, str) or not text.strip():
        return None
    normalized = normalize_spoken_command(text)
    match = re.search(r"\b(?:open|visit|browse to|go to|navigate to)\s+(.+?)\s*$", normalized)
    if not match:
        return None
    target = match.group(1).strip().strip(" .,!?")
    target = re.sub(r"^(?:the website|website|site)\s+", "", target)
    if target in _WEBSITE_ALIASES:
        return _WEBSITE_ALIASES[target]
    if target.startswith("www."):
        target = "https://" + target
    elif re.match(r"^[a-z0-9.-]+\.[a-z]{2,}(?::[0-9]{1,5})?(?:/.*)?$", target):
        target = "https://" + target
    try:
        parsed = urlsplit(target)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None
        if any(ch.isspace() for ch in target) or len(target) > 2048:
            return None
        return target
    except ValueError:
        return None


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
    normalized = re.sub(r"^(alexa|and|please|let.s|can we|we should)\s+", "", normalized)
    if not re.search(r"\b(close|quit|exit)\b", normalized):
        return None
    for app_id, patterns in _APP_PATTERNS.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            return LaunchIntent(app_id)
    return None


@dataclass(frozen=True)
class CreateFolderIntent:
    folder_name: str | None
    destination: str | None


def normalize_spoken_command(text: str) -> str:
    """Normalize common Whisper renderings without guessing application names."""
    normalized = re.sub(r"\s+", " ", (text or "").lower()).strip()
    normalized = re.sub(r"\b(k(e|a)n(a|u)\s+)?kred(a|er|it)\b", "create", normalized)
    normalized = re.sub(r"\bcreat(e|ed|ing)\b", "create", normalized)
    normalized = re.sub(r"\bname it as\s+", "called ", normalized)
    normalized = re.sub(r"\bcall it\s+", "called ", normalized)
    normalized = re.sub(r"\bname it\s+", "called ", normalized)
    return normalized


def parse_create_folder_command(text: str) -> CreateFolderIntent | None:
    """Extract folder name and optional absolute or relative destination."""
    normalized = normalize_spoken_command(text)
    if not re.search(r"\b(create|make)\b", normalized) or not re.search(r"\bfolder\b", normalized):
        return None
    name_match = re.search(r"\b(?:called|named)\s+([a-z0-9][a-z0-9 _-]{0,79}?)(?=\s+(?:in|inside|under|within|at)\s+|$)", normalized)
    if not name_match:
        return CreateFolderIntent(None, None)
    folder_name = name_match.group(1).strip(" .")
    destination_match = re.search(r"\b(?:in|inside|under|within|at)\s+(?:the\s+)?(?:directory|folder)?\s*([a-z0-9][a-z0-9 _:/\.-]{0,499})$", normalized)
    destination = destination_match.group(1).strip(" .") if destination_match else None
    return CreateFolderIntent(folder_name or None, destination or None)
