import pytest

from desktop_agent.actions.registry import ToolDefinition, ToolRegistry, available_tools, execute_tool


def test_default_registry_exposes_only_approved_app_launcher():
    tools = available_tools()
    assert [tool["name"] for tool in tools] == ["launch_app"]
    assert tools[0]["required_arguments"] == ["app_id"]


def test_registry_executes_registered_handler():
    registry = ToolRegistry()
    registry.register(ToolDefinition("echo", "Return a value", lambda value: {"value": value}, ("value",)))
    assert registry.execute("echo", {"value": "hello"}) == {"value": "hello"}


def test_registry_rejects_unknown_tool():
    with pytest.raises(ValueError, match="not registered"):
        execute_tool("run_shell", {})


def test_registry_rejects_missing_arguments():
    with pytest.raises(ValueError, match="Missing required"):
        execute_tool("launch_app", {})


def test_registry_rejects_unexpected_arguments():
    with pytest.raises(ValueError, match="Unexpected"):
        execute_tool("launch_app", {"app_id": "notepad", "command": "whoami"})


def test_registry_rejects_non_object_arguments():
    with pytest.raises(ValueError, match="JSON object"):
        execute_tool("launch_app", ["notepad"])
