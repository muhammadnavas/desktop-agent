from desktop_agent.parser import parse_command


def test_notepad():
    assert parse_command("Please open Notepad").app_id == "notepad"


def test_calculator():
    assert parse_command("launch calculator").app_id == "calculator"


def test_explorer():
    assert parse_command("Open File Explorer").app_id == "explorer"


def test_vscode():
    assert parse_command("Start VS Code").app_id == "vscode"


def test_rejects_arbitrary_command():
    assert parse_command("delete all my files") is None


def test_requires_launch_verb():
    assert parse_command("Notepad") is None


def test_empty_input():
    assert parse_command("   ") is None
