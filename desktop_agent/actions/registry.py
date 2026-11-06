"""Explicit registry for safe, allowlisted desktop-agent tools."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolDefinition:
    """A named action exposed to the local agent."""

    name: str
    description: str
    handler: Callable[..., dict[str, Any]]
    required_arguments: tuple[str, ...] = ()


class ToolRegistry:
    """Register and execute only explicitly approved local actions."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if not tool.name or not tool.name.replace("_", "").isalnum():
            raise ValueError("Tool names must contain only letters, numbers, and underscores.")
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "required_arguments": list(tool.required_arguments),
            }
            for tool in self._tools.values()
        ]

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Tool is not registered: {name}")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object.")
        missing = [key for key in tool.required_arguments if key not in arguments]
        if missing:
            raise ValueError("Missing required tool arguments: " + ", ".join(missing))
        unexpected = set(arguments) - set(tool.required_arguments)
        if unexpected:
            raise ValueError("Unexpected tool arguments: " + ", ".join(sorted(unexpected)))

        logger.info("Executing registered tool: %s", name)
        try:
            result = tool.handler(**arguments)
            if not isinstance(result, dict):
                raise TypeError("Tool handlers must return a dictionary.")
            logger.info("Registered tool completed: %s", name)
            return result
        except Exception:
            logger.exception("Registered tool failed: %s", name)
            raise


def _read_file(path: str) -> dict[str, Any]:
    from desktop_agent.actions.files import read_file
    return read_file(path)


def _prepare_file_write(path: str, content: str) -> dict[str, Any]:
    from desktop_agent.actions.files import prepare_file_write
    return prepare_file_write(path, content)


def _create_folder(path: str) -> dict[str, Any]:
    from desktop_agent.actions.files import create_folder
    return create_folder(path)


def _list_directory(path: str, limit: int = 100) -> dict[str, Any]:
    from desktop_agent.actions.files import list_directory
    return list_directory(path, limit)


def _list_project_files(root: str, limit: int = 100) -> dict[str, Any]:
    from desktop_agent.actions.files import list_project_files
    return list_project_files(root, limit)


def _search_project(root: str, query: str, limit: int = 30) -> dict[str, Any]:
    from desktop_agent.actions.files import search_project
    return search_project(root, query, limit)


def _close_app(app_id: str) -> dict[str, Any]:
    from desktop_agent.actions.apps import close_app
    return close_app(app_id)


def _launch_app(app_id: str) -> dict[str, Any]:
    from desktop_agent.actions.apps import launch_app

    if not isinstance(app_id, str) or not app_id.strip():
        raise ValueError("app_id must be a non-empty string.")
    return launch_app(app_id)


registry = ToolRegistry()
def _get_active_window() -> dict[str, Any]:
    from desktop_agent.actions.windows import get_active_window

    return get_active_window()


def _list_open_windows() -> dict[str, Any]:
    from desktop_agent.actions.windows import list_open_windows

    return list_open_windows()


def _open_website(url: str) -> dict[str, Any]:
    from desktop_agent.actions.websites import open_website
    return open_website(url)


def _open_new_tab() -> dict[str, Any]:
    from desktop_agent.actions.browser_tabs import open_new_tab
    return open_new_tab()


def _close_current_tab() -> dict[str, Any]:
    from desktop_agent.actions.browser_tabs import close_current_tab
    return close_current_tab()


def _get_system_status() -> dict[str, Any]:
    from desktop_agent.actions.system import get_system_status
    return get_system_status()


def _run_diagnostic_command(command_id: str) -> dict[str, Any]:
    from desktop_agent.actions.diagnostics import run_diagnostic_command
    return run_diagnostic_command(command_id)


registry.register(
    ToolDefinition(
        name="read_file",
        description="Read a UTF-8 text file from any accessible local path; maximum 1 MB.",
        handler=_read_file,
        required_arguments=("path",),
    )
)
registry.register(
    ToolDefinition(
        name="prepare_file_write",
        description="Stage creation or editing of a UTF-8 text file anywhere on the local filesystem; returns a preview and one-time approval token and does not write until confirmed.",
        handler=_prepare_file_write,
        required_arguments=("path", "content"),
    )
)
registry.register(
    ToolDefinition(
        name="create_folder",
        description="Create a new folder at any accessible local filesystem path.",
        handler=_create_folder,
        required_arguments=("path",),
    )
)
registry.register(
    ToolDefinition(
        name="close_app",
        description="Request a graceful close of one allowlisted running Windows application.",
        handler=_close_app,
        required_arguments=("app_id",),
    )
)
registry.register(
    ToolDefinition(
        name="launch_app",
        description="Launch one application from the approved Windows application allowlist.",
        handler=_launch_app,
        required_arguments=("app_id",),
    )
)
registry.register(
    ToolDefinition(
        name="get_active_window",
        description="Read the title and handle of the currently focused top-level window.",
        handler=_get_active_window,
    )
)
def _get_window_controls(window_title: str, limit: int = 60) -> dict[str, Any]:
    from desktop_agent.actions.windows_uia import get_window_controls
    return get_window_controls(window_title, limit)


registry.register(
    ToolDefinition(
        name="get_window_controls",
        description="Read accessible control names and types in a visible window; does not read field values or perform actions.",
        handler=_get_window_controls,
        required_arguments=("window_title",),
    )
)
registry.register(
    ToolDefinition(
        name="list_open_windows",
        description="List up to 30 visible top-level Windows windows and their titles.",
        handler=_list_open_windows,
    )
)


def available_tools() -> list[dict[str, Any]]:
    """Return public metadata for the currently registered tools."""
    return registry.describe()


def execute_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a tool only after registry and argument validation."""
    return registry.execute(name, arguments)


registry.register(
    ToolDefinition(
        name="open_new_tab",
        description="Open a new tab in the currently focused supported browser.",
        handler=_open_new_tab,
    )
)
registry.register(
    ToolDefinition(
        name="close_current_tab",
        description="Close the active tab in a supported browser; requires explicit approval.",
        handler=_close_current_tab,
    )
)
registry.register(
    ToolDefinition(
        name="get_system_status",
        description="Read basic Windows host, Python, CPU and disk usage information.",
        handler=_get_system_status,
    )
)


registry.register(
    ToolDefinition(
        name="list_project_files",
        description="List source and configuration files in a project, skipping common generated folders.",
        handler=_list_project_files,
        required_arguments=("root",),
    )
)
registry.register(
    ToolDefinition(
        name="search_project",
        description="Search literal text in bounded UTF-8 source files within a project.",
        handler=_search_project,
        required_arguments=("root", "query"),
    )
)


registry.register(
    ToolDefinition(
        name="list_directory",
        description="List files and subfolders in a directory with sensitive credential files filtered out.",
        handler=_list_directory,
        required_arguments=("path",),
    )
)


registry.register(
    ToolDefinition(
        name="run_diagnostic_command",
        description="Run a fixed read-only diagnostic such as ipconfig, tasklist, whoami, systeminfo, or a tool version check. Arbitrary commands and arguments are not accepted.",
        handler=_run_diagnostic_command,
        required_arguments=("command_id",),
    )
)
