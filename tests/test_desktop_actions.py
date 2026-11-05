import pytest

from desktop_agent.actions.desktop import validate_steps


def test_accepts_safe_click_and_type_steps():
    steps = validate_steps([
        {"action": "click", "x": 200, "y": 300},
        {"action": "type", "text": "hello"},
        {"action": "press", "keys": ["enter"]},
    ])
    assert [step["action"] for step in steps] == ["click", "type", "press"]


@pytest.mark.parametrize("keys", [
    ["ctrl", "alt", "delete"],
    ["alt", "ctrl", "delete"],
    ["ctrl", "shift", "esc"],
    ["win", "r"],
])
def test_rejects_sensitive_shortcuts(keys):
    with pytest.raises(ValueError):
        validate_steps([{"action": "press", "keys": keys}])


def test_rejects_unknown_action():
    with pytest.raises(ValueError):
        validate_steps([{"action": "shell", "command": "whoami"}])


def test_rejects_out_of_range_scroll():
    with pytest.raises(ValueError):
        validate_steps([{"action": "scroll", "amount": 100}])


def test_rejects_empty_plan():
    with pytest.raises(ValueError):
        validate_steps([])
