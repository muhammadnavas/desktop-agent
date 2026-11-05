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
