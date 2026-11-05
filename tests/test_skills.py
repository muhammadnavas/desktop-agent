import pytest

from desktop_agent.skills import get_skill, list_skills


def test_builtin_skills_are_discoverable():
    ids = {item["id"] for item in list_skills()}
    assert {"open_app", "code_autometa", "desktop_task", "voice_command"} <= ids


def test_skill_includes_instructions():
    assert "explicit approval" in get_skill("desktop_task")["instructions"]


def test_unknown_skill_is_rejected():
    with pytest.raises(KeyError):
        get_skill("run_arbitrary_script")
