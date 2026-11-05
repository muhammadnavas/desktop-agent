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


def _launch_app(app_id: str) -> dict[str, Any]:
    from desktop_agent.actions.apps import launch_app

    return launch_app(app_id)


registry = ToolRegistry()
registry.register(
    ToolDefinition(
        name="launch_app",
        description="Launch one application from the approved Windows application allowlist.",
        handler=_launch_app,
        required_arguments=("app_id",),
    )
)


def available_tools() -> list[dict[str, Any]]:
    """Return public metadata for the currently registered tools."""
    return registry.describe()


def execute_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a tool only after registry and argument validation."""
    return registry.execute(name, arguments)
