import pytest

from desktop_agent import tool_registry


def test_registry_exposes_only_allowlisted_tool():
    tools = tool_registry.list_tools()
    assert [item["name"] for item in tools] == ["launch_app"]


def test_execute_tool_dispatches_registered_handler(monkeypatch):
    monkeypatch.setattr(
        tool_registry,
        "launch_app",
        lambda app_id: {"status": "launched", "app": app_id},
    )
    result = tool_registry.execute_tool("launch_app", {"app_id": "notepad"})
    assert result == {"status": "launched", "app": "notepad"}


def test_execute_tool_rejects_unknown_tool():
    with pytest.raises(ValueError, match="not registered"):
        tool_registry.execute_tool("run_shell", {"command": "whoami"})


def test_execute_tool_rejects_extra_arguments():
    with pytest.raises(ValueError, match="Unexpected"):
        tool_registry.execute_tool("launch_app", {"app_id": "notepad", "command": "calc"})


def test_execute_tool_rejects_missing_arguments():
    with pytest.raises(ValueError, match="Missing"):
        tool_registry.execute_tool("launch_app", {})
