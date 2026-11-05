"""Allowlisted, read-only diagnostic commands. No arbitrary shell execution."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


_DIAGNOSTICS = {
    "ipconfig": ("ipconfig",),
    "tasklist": ("tasklist",),
    "whoami": ("whoami",),
    "systeminfo": ("systeminfo",),
    "python_version": (sys.executable, "--version"),
    "node_version": ("node", "--version"),
    "git_version": ("git", "--version"),
    "docker_version": ("docker", "--version"),
}


def available_diagnostics() -> list[str]:
    """Return stable diagnostic IDs; availability is checked during execution."""
    return sorted(_DIAGNOSTICS)


def run_diagnostic_command(command_id: str) -> dict:
    """Run one fixed read-only diagnostic command without a shell or user arguments."""
    if command_id not in _DIAGNOSTICS:
        raise ValueError("That diagnostic command is not allowlisted.")
    if os.name != "nt" and command_id not in {"python_version", "node_version", "git_version", "docker_version"}:
        raise RuntimeError("This diagnostic is supported on Windows only.")
    command = list(_DIAGNOSTICS[command_id])
    executable = command[0]
    if command_id != "python_version":
        resolved = shutil.which(executable)
        if not resolved:
            raise FileNotFoundError(f"{executable} was not found on PATH.")
        command[0] = resolved
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            shell=False,
            check=False,
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{command_id} timed out after 15 seconds.") from exc
    output = (completed.stdout or completed.stderr or "").strip()
    return {
        "success": completed.returncode == 0,
        "command_id": command_id,
        "exit_code": completed.returncode,
        "output": output[:12000],
        "truncated": len(output) > 12000,
    }
