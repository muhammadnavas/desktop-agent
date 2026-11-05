import pytest

from desktop_agent.actions.registry import ToolDefinition, ToolRegistry, available_tools, execute_tool


def test_default_registry_exposes_approved_desktop_tools():
    tools = available_tools()
    by_name = {tool["name"]: tool for tool in tools}
    assert set(by_name) == {"launch_app", "get_active_window", "list_open_windows", "get_window_controls"}
    assert by_name["launch_app"]["required_arguments"] == ["app_id"]
    assert by_name["get_active_window"]["required_arguments"] == []
    assert by_name["list_open_windows"]["required_arguments"] == []
    assert by_name["get_window_controls"]["required_arguments"] == ["window_title"]


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


@pytest.mark.parametrize("app_id", [None, 42, [], ""])
def test_launch_tool_rejects_invalid_app_id_type(app_id):
    with pytest.raises(ValueError, match="non-empty string"):
        execute_tool("launch_app", {"app_id": app_id})
