from desktop_agent.voice_listener import should_finish_capture


def policy(**overrides):
    values = {
        "elapsed": 1.0,
        "silence_elapsed": 0.1,
        "speech_seen": True,
        "speech_duration": 0.5,
        "silence_seconds": 1.1,
        "max_command_seconds": 12.0,
        "speech_start_timeout": 5.0,
    }
    values.update(overrides)
    return should_finish_capture(**values)


def test_capture_waits_while_user_is_speaking():
    assert policy() == (False, "continue")


def test_capture_finishes_after_silence_following_speech():
    assert policy(silence_elapsed=1.2) == (True, "speech_complete")


def test_capture_discards_wake_word_when_no_command_follows():
    assert policy(elapsed=5.0, speech_seen=False, speech_duration=0.0) == (
        True,
        "no_speech",
    )


def test_capture_discards_too_short_noise():
    assert policy(
        elapsed=2.0,
        silence_elapsed=1.2,
        speech_duration=0.08,
    ) == (True, "speech_complete")


def test_capture_has_hard_maximum_duration():
    assert policy(elapsed=12.0, silence_elapsed=0.1) == (
        True,
        "max_duration",
    )
