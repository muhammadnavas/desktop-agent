from desktop_agent.actions.workflows import is_code_autometa_command


def test_matches_typed_code_autometa_phrase():
    assert is_code_autometa_command("Code Autometa")


def test_matches_wake_word_and_speech_recognition_variant():
    assert is_code_autometa_command("Alexa, Code Automata")


def test_matches_wake_word_with_project_suffix():
    assert is_code_autometa_command("Hey Alexa, start Code Autometa project")


def test_does_not_match_unrelated_or_extra_commands():
    assert not is_code_autometa_command("Alexa, open Notepad")
    assert not is_code_autometa_command("Code Autometa and delete all files")


def test_matches_common_autometa_speech_variants():
    assert is_code_autometa_command("Alexa, Code Automate")
    assert is_code_autometa_command("Hey Alexa, Code Auto Meta")
    assert is_code_autometa_command("Please launch Code Autometa")
