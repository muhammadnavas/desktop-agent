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



def test_matches_conversational_voice_transcription():
    assert is_code_autometa_command("it is a code automata")
    assert is_code_autometa_command("This is Code Automate")
    assert is_code_autometa_command("Alexa, please start Code Automata")


def test_matches_multiple_filler_phrases_before_command():
    assert is_code_autometa_command("Like this. Like so. Code automata.")
    assert is_code_autometa_command("Alexa, like this, code automate")
    assert is_code_autometa_command("Well, please, code auto meta")


def test_rejects_extra_instruction_after_workflow_phrase():
    assert not is_code_autometa_command("Code Autometa and delete all files")
    assert not is_code_autometa_command("Code Automata then open Notepad")


def test_recognizes_noisy_phonetic_transcripts():
    assert is_code_autometa_command("good potter meta")
    assert is_code_autometa_command("x 4 automaker")
    assert is_code_autometa_command("next time good potter meta")


def test_ignores_wake_word_without_a_command():
    assert not is_code_autometa_command("Alexa")
    assert not is_code_autometa_command("Hey Alexa")
