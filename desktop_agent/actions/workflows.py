"""Allowlisted local development workflows."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


DEFAULT_PROJECT_ROOT = Path(r"D:\Projects\Python\ai-browser-automation-agent")


def is_code_autometa_command(text: str) -> bool:
    """Recognize the explicit voice phrase without sending it to Ollama."""
    normalized = " ".join(text.lower().strip().split())
    return normalized in {
        "code autometa",
        "code autometa project",
        "start code autometa",
        "start autometa",
        "open code autometa",
    }


def _antigravity_launch(root: Path) -> tuple[list[str], str]:
    """Prefer the Antigravity desktop IDE; fall back to its official agy CLI."""
    ide = shutil.which("antigravity")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if ide:
        return [ide, str(root)], str(root)

    if local_app_data:
        ide_candidate = Path(local_app_data) / "Programs" / "Antigravity" / "Antigravity.exe"
        if ide_candidate.is_file():
            return [str(ide_candidate), str(root)], str(root)

        agy_candidate = Path(local_app_data) / "agy" / "bin" / "agy.exe"
        if agy_candidate.is_file():
            return ["cmd.exe", "/k", f'"{agy_candidate}"'], str(root)

    agy = shutil.which("agy")
    if agy:
        return ["cmd.exe", "/k", f'"{agy}"'], str(root)

    raise FileNotFoundError(
        "Antigravity IDE or CLI was not found. Install Antigravity, or install its CLI and add agy to PATH."
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

    # Each process gets its own terminal window. Commands and paths are fixed
    # by this allowlisted workflow; voice input is never interpolated.
    antigravity = subprocess.Popen(
        antigravity_command,
        cwd=antigravity_cwd,
        shell=False,
        creationflags=new_console,
    )
    frontend_terminal = subprocess.Popen(
        ["cmd.exe", "/k", 'npm run dev'],
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
