"""Optional fully local speech-to-text using faster-whisper."""

import os
import tempfile
from pathlib import Path

_model = None


def transcribe_audio(audio_bytes: bytes, suffix: str = ".webm") -> str:
    global _model
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Local voice support is not installed. Run: pip install -e .[voice]"
        ) from exc

    if not audio_bytes:
        raise ValueError("No audio was received.")
    if len(audio_bytes) > 20 * 1024 * 1024:
        raise ValueError("Audio file is too large (20 MB limit).")

    if _model is None:
        model_size = os.getenv("WHISPER_MODEL", "base")
        _model = WhisperModel(model_size, device="cpu", compute_type="int8")

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
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
