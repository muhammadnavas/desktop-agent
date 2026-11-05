"""Optional local speech input and spoken responses."""

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)
_model = None


def voice_dependencies_status() -> dict:
    """Report optional voice package availability without importing heavy models."""
    from importlib.util import find_spec

    packages = {
        "faster_whisper": "faster-whisper",
        "av": "av",
        "openwakeword": "openwakeword",
        "sounddevice": "sounddevice",
        "numpy": "numpy",
        "onnxruntime": "onnxruntime",
        "pyttsx3": "pyttsx3",
    }
    installed = {name: find_spec(name) is not None for name in packages}
    missing = [packages[name] for name, available in installed.items() if not available]
    return {
        "installed": not missing,
        "packages": installed,
        "missing": missing,
        "install_command": "pip install -e .[voice]" if missing else None,
    }


def transcribe_audio(audio_bytes: bytes, suffix: str = ".webm") -> str:
    global _model

    if not audio_bytes:
        raise ValueError("No audio was received.")
    if len(audio_bytes) > 20 * 1024 * 1024:
        raise ValueError("Audio file is too large (20 MB limit).")

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Local voice support is not installed. Run: pip install -e .[voice]"
        ) from exc

    if _model is None:
        model_size = os.getenv("WHISPER_MODEL", "base")
        logger.info("Loading faster-whisper model '%s' on CPU (int8)", model_size)
        try:
            _model = WhisperModel(model_size, device="cpu", compute_type="int8")
        except Exception as exc:
            raise RuntimeError(
                f"Could not load Whisper model '{model_size}': {exc}. "
                "Check your internet connection for the first model download "
                "or choose a smaller WHISPER_MODEL."
            ) from exc

    safe_suffix = suffix if suffix in {".webm", ".wav", ".mp3", ".m4a", ".ogg"} else ".webm"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=safe_suffix) as handle:
            handle.write(audio_bytes)
            temp_path = Path(handle.name)
        segments, _ = _model.transcribe(str(temp_path), vad_filter=True)
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        if not transcript:
            raise ValueError("I couldn't hear any speech. Please try again.")
        return transcript
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Audio transcription failed: {exc}") from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def speak_text(text: str) -> None:
    """Speak a concise response locally using Windows SAPI via pyttsx3."""
    message = " ".join(str(text).split()).strip()
    if not message:
        return
    if len(message) > 450:
        message = message[:447].rsplit(" ", 1)[0] + "..."
    try:
        import pyttsx3
    except ImportError as exc:
        raise RuntimeError(
            "Offline speech output is not installed. Run: pip install -e .[voice]"
        ) from exc

    engine = pyttsx3.init()
    try:
        rate = int(os.getenv("VOICE_RESPONSE_RATE", "175"))
        engine.setProperty("rate", max(120, min(rate, 220)))
        engine.setProperty("volume", 1.0)
        engine.say(message)
        engine.runAndWait()
    finally:
        engine.stop()
