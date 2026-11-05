"""Typed, allowlisted registry for actions the assistant may execute."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from desktop_agent.actions.apps import launch_app

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., dict[str, str]]
    required_arguments: frozenset[str]


def _launch_app(*, app_id: str) -> dict[str, str]:
    if not isinstance(app_id, str) or not app_id.strip():
        raise ValueError("app_id must be a non-empty string.")
    return launch_app(app_id)


_TOOL_REGISTRY: dict[str, ToolSpec] = {
    "launch_app": ToolSpec(
        name="launch_app",
        description="Launch an application from the approved Windows application list.",
        handler=_launch_app,
        required_arguments=frozenset({"app_id"}),
    )
}


def list_tools() -> list[dict[str, Any]]:
    """Return safe tool metadata for diagnostics and prompt construction."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "required_arguments": sorted(spec.required_arguments),
        }
        for spec in _TOOL_REGISTRY.values()
    ]


def execute_tool(name: str, arguments: object) -> dict[str, str]:
    """Validate a tool call and dispatch only to a registered handler."""
    spec = _TOOL_REGISTRY.get(name)
    if spec is None:
        raise ValueError(f"Tool '{name}' is not registered.")

    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object.")

    supplied = set(arguments)
    missing = spec.required_arguments - supplied
    unexpected = supplied - spec.required_arguments
    if missing:
        raise ValueError(f"Missing required tool arguments: {', '.join(sorted(missing))}.")
    if unexpected:
        raise ValueError(f"Unexpected tool arguments: {', '.join(sorted(unexpected))}.")

    logger.info("Executing tool=%s arguments=%s", name, arguments)
    result = spec.handler(**arguments)
    logger.info("Tool completed: %s", name)
    return result
