"""Allowlisted local development workflows."""

from __future__ import annotations

import os
import re
from difflib import SequenceMatcher
import shutil
import subprocess
from pathlib import Path


DEFAULT_PROJECT_ROOT = Path(r"D:\Projects\Python\ai-browser-automation-agent")


def is_code_autometa_command(text: str) -> bool:
    """Recognize the user's Code Autometa trigger despite noisy speech-to-text."""
    normalized = re.sub(r"[^a-z0-9 ]+", " ", str(text).lower())
    words = normalized.split()
    if not words:
        return False

    # A wake-word detection can occasionally produce only "Alexa". That is
    # not a command and must not be sent to Ollama as one.
    words = [word for word in words if word not in {"alexa", "hey"}]
    if not words:
        return False

    aliases = {
        "automata": "autometa",
        "automate": "autometa",
        "automaker": "autometa",
        "auto": "autometa",
        "meta": "autometa",
        "metta": "autometa",
    }
    words = [aliases.get(word, word) for word in words]

    # Strip conversational filler and command verbs wherever they precede
    # the trigger. Keep only a short tail so unrelated speech is not treated
    # as permission to launch a workflow.
    fillers = {
        "it", "is", "a", "this", "that", "like", "so", "just", "please",
        "can", "could", "you", "well", "now", "okay", "ok", "the",
        "start", "open", "launch", "run", "do", "for", "me",
    }
    meaningful = [word for word in words if word not in fillers]
    if not meaningful:
        return False

    tail = meaningful[-4:]
    phrase = " ".join(tail)
    if phrase in {"code autometa", "autometa", "code autometa project"}:
        return True

    # Fuzzy matching is limited to the final one-to-three words and requires
    # a high similarity to the known trigger. This helps with transcripts
    # such as "good potter meta" without treating arbitrary speech as a command.
    candidates = [
        " ".join(tail[-size:])
        for size in (1, 2, 3)
        if len(tail) >= size
    ]
    targets = ("codeautometa", "autometa")
    compact_candidates = [candidate.replace(" ", "") for candidate in candidates]
    # Known Whisper mishearing observed during this user's live tests.
    if any(candidate.endswith("goodpottermeta") for candidate in compact_candidates):
        return True
    return any(
        SequenceMatcher(None, candidate, target).ratio() >= 0.68
        for candidate in compact_candidates
        for target in targets
    )


def _registered_antigravity_path() -> Path | None:
    """Read the Windows App Paths registration when available."""
    if os.name != "nt":
        return None
    try:
        import winreg

        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Antigravity.exe"
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, None)
                    candidate = Path(value)
                    if candidate.is_file():
                        return candidate
            except OSError:
                continue
    except ImportError:
        pass
    return None


def _uninstall_registry_paths() -> list[Path]:
    """Find Antigravity install locations registered by Windows installers."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    locations: list[Path] = []
    uninstall_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0)):
            try:
                with winreg.OpenKey(hive, uninstall_key, 0, winreg.KEY_READ | view) as root_key:
                    count = winreg.QueryInfoKey(root_key)[0]
                    for index in range(count):
                        try:
                            sub_name = winreg.EnumKey(root_key, index)
                            with winreg.OpenKey(root_key, sub_name) as item:
                                display, _ = winreg.QueryValueEx(item, "DisplayName")
                                if "antigravity" not in str(display).casefold():
                                    continue
                                for value_name in ("InstallLocation", "DisplayIcon"):
                                    try:
                                        value, _ = winreg.QueryValueEx(item, value_name)
                                        candidate = Path(str(value).strip().strip('"').split(",")[0])
                                        if candidate.is_file() and candidate.name.casefold() == "antigravity.exe":
                                            locations.append(candidate)
                                        elif candidate.is_dir():
                                            locations.extend((candidate / "Antigravity.exe", candidate / "Application" / "Antigravity.exe"))
                                    except OSError:
                                        continue
                        except OSError:
                            continue
            except OSError:
                continue
    return locations


def _find_antigravity_exe() -> Path | None:
    """Locate Antigravity across PATH, Windows registry, and common per-user installs."""
    override = os.environ.get("ANTIGRAVITY_EXE")
    if override:
        candidate = Path(os.path.expandvars(override)).expanduser()
        if candidate.is_file():
            return candidate.resolve()

    for command in ("Antigravity.exe", "antigravity.exe", "antigravity"):
        located = shutil.which(command)
        if located and Path(located).is_file():
            return Path(located).resolve()

    registered = _registered_antigravity_path()
    if registered:
        return registered.resolve()
    for candidate in _uninstall_registry_paths():
        if candidate.is_file():
            return candidate.resolve()

    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    user_profile = Path(os.environ.get("USERPROFILE", str(Path.home())))

    candidates = [
        local / "Programs" / "Antigravity" / "Antigravity.exe",
        local / "Programs" / "Antigravity" / "Application" / "Antigravity.exe",
        local / "Programs" / "Google" / "Antigravity" / "Antigravity.exe",
        local / "Google" / "Antigravity" / "Antigravity.exe",
        local / "Google" / "Antigravity" / "Application" / "Antigravity.exe",
        roaming / "Antigravity" / "Antigravity.exe",
        program_files / "Antigravity" / "Antigravity.exe",
        program_files / "Google" / "Antigravity" / "Antigravity.exe",
        program_files_x86 / "Antigravity" / "Antigravity.exe",
        user_profile / "AppData" / "Local" / "Programs" / "Antigravity" / "Antigravity.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    # Installer layouts change over time. Search only likely install roots,
    # prune unrelated/cache directories, and cap traversal to avoid a slow
    # full-disk scan on every voice command.
    search_roots = (local / "Programs", program_files, program_files_x86)
    ignored = {"node_modules", ".git", "cache", "cacheddata", "temp", "tmp"}
    visited = 0
    for search_root in search_roots:
        if not search_root.is_dir():
            continue
        for current, dirs, names in os.walk(search_root):
            depth = len(Path(current).relative_to(search_root).parts)
            dirs[:] = [name for name in dirs if name.casefold() not in ignored]
            if depth >= 5:
                dirs[:] = []
            visited += 1
            if visited > 3000:
                return None
            if "antigravity.exe" in {name.casefold() for name in names}:
                match = Path(current) / next(name for name in names if name.casefold() == "antigravity.exe")
                if match.is_file():
                    return match.resolve()
    return None

def _antigravity_launch(root: Path) -> tuple[list[str], str]:
    """Prefer the Antigravity desktop IDE; fall back to its official agy CLI."""
    ide = _find_antigravity_exe()
    if ide:
        return [str(ide), str(root)], str(root)

    local_app_data = os.environ.get("LOCALAPPDATA")
    cli_candidates = []
    if local_app_data:
        cli_candidates.append(Path(local_app_data) / "agy" / "bin" / "agy.exe")

    for candidate in cli_candidates:
        if candidate.is_file():
            return ["cmd.exe", "/k", f'"{candidate}"'], str(root)

    agy = shutil.which("agy")
    if agy:
        return ["cmd.exe", "/k", f'"{agy}"'], str(root)

    raise FileNotFoundError(
        "Antigravity was not found. Set ANTIGRAVITY_EXE to the full path of Antigravity.exe, "
        "or install its CLI and add agy to PATH."
    )


def start_code_autometa_workflow() -> dict[str, object]:
    """Open Antigravity in the project and start frontend/backend in separate consoles."""
    if os.name != "nt":
        raise RuntimeError("The Code Autometa workflow currently supports Windows only.")

    root = Path(
        os.environ.get("AI_BROWSER_AGENT_ROOT", str(DEFAULT_PROJECT_ROOT))
    ).expanduser()

    frontend = root / "frontend"
    backend = root / "backend"

    if not root.is_dir():
        raise FileNotFoundError(f"Project folder was not found: {root}")
    if not (frontend / "package.json").is_file():
        raise FileNotFoundError(f"Frontend package.json was not found: {frontend}")
    if not (backend / "main.py").is_file():
        raise FileNotFoundError(f"Backend main.py was not found: {backend}")

    antigravity_command, antigravity_cwd = _antigravity_launch(root)
    new_console = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

    # Fixed, allowlisted commands only; voice input is never interpolated.
    antigravity = subprocess.Popen(
        antigravity_command,
        cwd=antigravity_cwd,
        shell=False,
        creationflags=new_console,
    )
    frontend_terminal = subprocess.Popen(
        ["cmd.exe", "/k", "npm run dev"],
        cwd=str(frontend),
        shell=False,
        creationflags=new_console,
    )
    backend_terminal = subprocess.Popen(
        ["cmd.exe", "/k", "uvicorn main:app --reload"],
        cwd=str(backend),
        shell=False,
        creationflags=new_console,
    )

    return {
        "status": "started",
        "workflow": "code_autometa",
        "project_root": str(root),
        "antigravity_pid": antigravity.pid,
        "frontend_pid": frontend_terminal.pid,
        "backend_pid": backend_terminal.pid,
        "message": "Antigravity, frontend dev server, and backend Uvicorn were opened in separate windows.",
    }
