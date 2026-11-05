import pytest

from desktop_agent.ollama_client import OllamaError, validate_command_intent


APPS = [{"id": "notepad", "name": "Notepad"}, {"id": "calculator", "name": "Calculator"}]


def test_valid_launch_intent_is_preserved():
    result = validate_command_intent(
        {"action": "launch_app", "app_id": "notepad", "response": "Opening Notepad"},
        APPS,
    )
    assert result == {"action": "launch_app", "app_id": "notepad", "response": "Opening Notepad"}


def test_unsupported_intent_is_normalized():
    result = validate_command_intent(
        {"action": "unsupported", "app_id": None, "response": "Not supported"},
        APPS,
    )
    assert result["action"] == "unsupported"
    assert result["app_id"] is None


@pytest.mark.parametrize("payload", [None, [], "launch_app", 42])
def test_non_object_intent_is_rejected(payload):
    with pytest.raises(OllamaError, match="JSON object"):
        validate_command_intent(payload, APPS)


def test_unknown_action_is_rejected():
    with pytest.raises(OllamaError, match="unsupported intent action"):
        validate_command_intent({"action": "run_shell", "response": "ok"}, APPS)


def test_unknown_application_is_rejected():
    with pytest.raises(OllamaError, match="outside the approved allowlist"):
        validate_command_intent({"action": "launch_app", "app_id": "powershell", "response": "ok"}, APPS)


def test_non_string_response_is_rejected():
    with pytest.raises(OllamaError, match="must be text"):
        validate_command_intent({"action": "unsupported", "response": {"text": "bad"}}, APPS)


def test_unexpected_intent_fields_are_rejected():
    with pytest.raises(OllamaError, match="unexpected intent fields"):
        validate_command_intent(
            {
                "action": "launch_app",
                "app_id": "notepad",
                "response": "Opening",
                "command": "whoami",
            },
            APPS,
        )


def test_unsupported_intent_cannot_smuggle_an_app_id():
    with pytest.raises(OllamaError, match="must not include an application id"):
        validate_command_intent(
            {"action": "unsupported", "app_id": "powershell", "response": "No"},
            APPS,
        )


TOOLS = [
    {"name": "launch_app", "required_arguments": ["app_id"]},
    {"name": "get_active_window", "required_arguments": []},
    {"name": "list_open_windows", "required_arguments": []},
]


def test_valid_tool_intent_is_accepted():
    from desktop_agent.ollama_client import validate_tool_intent

    result = validate_tool_intent(
        {"tool": "launch_app", "arguments": {"app_id": "notepad"}, "response": "Opening"},
        TOOLS,
    )
    assert result == {
        "tool": "launch_app",
        "arguments": {"app_id": "notepad"},
        "response": "Opening",
    }


def test_read_only_window_tool_accepts_empty_arguments():
    from desktop_agent.ollama_client import validate_tool_intent

    result = validate_tool_intent(
        {"tool": "get_active_window", "arguments": {}, "response": "Checking"},
        TOOLS,
    )
    assert result["tool"] == "get_active_window"


def test_unregistered_tool_is_rejected():
    from desktop_agent.ollama_client import validate_tool_intent

    with pytest.raises(OllamaError, match="not registered"):
        validate_tool_intent(
            {"tool": "run_shell", "arguments": {"command": "whoami"}, "response": "Running"},
            TOOLS,
        )


def test_tool_arguments_must_match_registered_schema():
    from desktop_agent.ollama_client import validate_tool_intent

    with pytest.raises(OllamaError, match="schema"):
        validate_tool_intent(
            {"tool": "get_active_window", "arguments": {"path": "C:\\\\"}, "response": "Inspect"},
            TOOLS,
        )


def test_tool_launch_rejects_non_allowlisted_app():
    from desktop_agent.ollama_client import validate_tool_intent

    with pytest.raises(OllamaError, match="allowlist"):
        validate_tool_intent(
            {"tool": "launch_app", "arguments": {"app_id": "powershell"}, "response": "Open"},
            TOOLS,
        )
