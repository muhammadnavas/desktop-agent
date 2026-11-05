from desktop_agent.parser import parse_command


def test_notepad():
    assert parse_command("Please open Notepad").app_id == "notepad"


def test_calculator():
    assert parse_command("launch calculator").app_id == "calculator"


def test_explorer():
    assert parse_command("Open File Explorer").app_id == "explorer"


def test_vscode():
    assert parse_command("Start VS Code").app_id == "vscode"


def test_whatsapp():
    assert parse_command("Open WhatsApp").app_id == "whatsapp"
    assert parse_command("Launch Whats App").app_id == "whatsapp"


def test_rejects_arbitrary_command():
    assert parse_command("delete all my files") is None


def test_requires_launch_verb():
    assert parse_command("Notepad") is None


def test_empty_input():
    assert parse_command("   ") is None


def test_close_whatsapp_is_not_a_launch_command():
    assert parse_command("Alexa close WhatsApp") is None
    assert parse_command("close WhatsApp") is None

from desktop_agent.parser import parse_close_command, parse_create_folder_command, normalize_spoken_command


def test_close_parser_handles_natural_voice_phrasing():
    assert parse_close_command("Let's close WhatsApp").app_id == "whatsapp"
    assert parse_close_command("and exit close whatsapp").app_id == "whatsapp"
    assert parse_close_command("Alexa close WhatsApp").app_id == "whatsapp"


def test_folder_parser_normalizes_common_whisper_misrecognition():
    assert normalize_spoken_command("kena kreda folder") == "create folder"
    intent = parse_create_folder_command("Alexa can you create a folder")
    assert intent is not None
    assert intent.folder_name is None


def test_folder_parser_extracts_name_and_destination():
    intent = parse_create_folder_command("create a folder called Projects in Documents")
    assert intent.folder_name == "projects"
    assert intent.destination == "documents"
