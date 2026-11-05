"""Allowlisted Windows application launching."""

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class AppDefinition:
    app_id: str
    display_name: str
    command: tuple[str, ...]


def _apps() -> dict[str, AppDefinition]:
    return {
        "notepad": AppDefinition("notepad", "Notepad", ("notepad.exe",)),
        "calculator": AppDefinition("calculator", "Calculator", ("calc.exe",)),
        "explorer": AppDefinition("explorer", "File Explorer", ("explorer.exe",)),
        "vscode": AppDefinition("vscode", "Visual Studio Code", ("code",)),
        "whatsapp": AppDefinition("whatsapp", "WhatsApp", ("whatsapp:",)),
    }


def supported_apps() -> list[dict[str, str]]:
    return [{"id": app.app_id, "name": app.display_name} for app in _apps().values()]


def close_app(app_id: str) -> dict[str, str]:
    """Request a graceful close for an allowlisted application process."""
    if os.name != "nt":
        raise RuntimeError("Desktop Agent currently supports Windows only.")
    process_images = {
        "notepad": "Notepad.exe",
        "calculator": "CalculatorApp.exe",
        "explorer": "explorer.exe",
        "vscode": "Code.exe",
        "whatsapp": "WhatsApp.exe",
    }
    image = process_images.get(app_id)
    if image is None:
        raise ValueError("That application is not on the approved app list.")
    completed = subprocess.run(
        ["taskkill.exe", "/IM", image, "/T"],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        if "not found" in detail.lower() or "no running instance" in detail.lower():
            raise ProcessLookupError(f"{app_id} is not currently running.")
        raise RuntimeError(detail or f"Windows could not close {app_id}.")
    return {"status": "close_requested", "app": _apps()[app_id].display_name}


def launch_app(app_id: str) -> dict[str, str]:
    if os.name != "nt":
        raise RuntimeError("Desktop Agent currently supports Windows only.")
    app = _apps().get(app_id)
    if app is None:
        raise ValueError("That application is not on the approved app list.")
    executable = app.command[0]
    if app_id == "whatsapp":
        # Use the registered Windows URI handler instead of executing a shell command.
        try:
            os.startfile("whatsapp:")  # type: ignore[attr-defined]
        except OSError as exc:
            raise FileNotFoundError(
                "WhatsApp could not be opened. Install WhatsApp Desktop and try again."
            ) from exc
        return {"status": "launched", "app": app.display_name}
    if app_id == "vscode":
        resolved = shutil.which(executable)
        if not resolved:
            raise FileNotFoundError(
                "VS Code was not found on PATH. Enable the 'code' command or use another supported app."
            )
        command = [resolved]
    else:
        command = list(app.command)
    subprocess.Popen(command, shell=False, close_fds=True)
    return {"status": "launched", "app": app.display_name}
