"""Read-only local Windows system information."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path


def get_system_status() -> dict:
    """Return basic host, Python, CPU and disk information without changing state."""
    root = Path.home().anchor or str(Path.home())
    try:
        disk = shutil.disk_usage(root)
        disk_info = {
            "root": root,
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
        }
    except OSError as exc:
        disk_info = {"root": root, "error": str(exc)}
    return {
        "success": True,
        "os": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "hostname": platform.node(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "home_directory": str(Path.home()),
        "disk": disk_info,
    }
