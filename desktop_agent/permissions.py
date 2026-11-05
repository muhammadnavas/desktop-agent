"""Risk-based execution policy for Desktop Agent commands."""

from __future__ import annotations

from dataclasses import dataclass

SAFE_TOOLS = frozenset({
    "launch_app",
    "read_file", "list_directory", "list_project_files", "search_project",
    "get_active_window",
    "list_open_windows",
    "get_window_controls",
    "open_new_tab",
    "get_system_status",
    "run_diagnostic_command",
})
APPROVAL_TOOLS = frozenset({"close_app", "close_current_tab", "create_folder", "prepare_file_write"})

# These operations are intentionally unavailable through natural-language routing.
BLOCKED_COMMAND_PATTERNS = (
    "delete ", "delete all", "erase ", "wipe ", "format drive",
    "format disk", "factory reset", "disable defender", "disable antivirus",
    "turn off firewall", "change password", "reveal password",
    "show api key", "show secret", "send money", "make a payment",
    "purchase ", "buy ",
)


@dataclass(frozen=True)
class PermissionDecision:
    level: str
    reason: str


def classify_command_text(text: str) -> PermissionDecision:
    """Block high-impact requests before the language model can route them."""
    normalized = " ".join((text or "").casefold().split())
    for pattern in BLOCKED_COMMAND_PATTERNS:
        if pattern in normalized:
            return PermissionDecision(
                "blocked",
                "This operation is disabled by the default safety policy. "
                "No action was performed.",
            )
    return PermissionDecision("continue", "No blocked command pattern detected.")


def classify_tool(tool_name: str) -> PermissionDecision:
    """Return the default risk tier for a registered tool."""
    if tool_name in SAFE_TOOLS:
        return PermissionDecision("safe", "Read-only or low-impact local action.")
    if tool_name == "prepare_file_write":
        return PermissionDecision(
            "approval",
            "File changes must be reviewed and explicitly confirmed before writing.",
        )
    if tool_name in APPROVAL_TOOLS:
        return PermissionDecision(
            "approval",
            "This action may interrupt work or change local state and needs approval.",
        )
    return PermissionDecision(
        "blocked",
        "This tool is not approved by the execution policy.",
    )
