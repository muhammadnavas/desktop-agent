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


def _windows_apps() -> dict[str, AppDefinition]:
    return {
        "notepad": AppDefinition("notepad", "Notepad", ("notepad.exe",)),
        "calculator": AppDefinition("calculator", "Calculator", ("calc.exe",)),
        "explorer": AppDefinition("explorer", "File Explorer", ("explorer.exe",)),
        "vscode": AppDefinition("vscode", "Visual Studio Code", ("code",)),
    }


def supported_apps() -> list[dict[str, str]]:
    return [
        {"id": app.app_id, "name": app.display_name}
        for app in _windows_apps().values()
    ]


def launch_app(app_id: str) -> dict[str, str]:
    """Launch one allowlisted app. Never invokes a shell."""
    if os.name != "nt":
        raise RuntimeError("NOVA v0.1 currently supports Windows only.")

    app = _windows_apps().get(app_id)
    if app is None:
        raise ValueError("That application is not on NOVA's allowlist.")

    executable = app.command[0]
    if app_id == "vscode":
        resolved = shutil.which(executable)
        if not resolved:
            raise FileNotFoundError(
                "VS Code was not found on PATH. Install VS Code and enable the 'code' command, "
                "or use Notepad, Calculator or File Explorer."
            )
        command = (resolved,)
    else:
        command = app.command

    subprocess.Popen(list(command), shell=False, close_fds=True)
    return {"status": "launched", "app": app.display_name}
