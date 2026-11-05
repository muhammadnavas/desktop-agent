"""Always-on local Alexa wake-word listener and post-wake command capture."""

from __future__ import annotations

import io
import logging
import os
import queue
import threading
import time
import wave
from collections import deque
from typing import Callable

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # openWakeWord expects 80 ms frames at 16 kHz.
DEFAULT_SILENCE_SECONDS = 1.1
DEFAULT_MAX_COMMAND_SECONDS = 12.0
DEFAULT_SPEECH_START_TIMEOUT = 5.0
DEFAULT_MIN_SPEECH_SECONDS = 0.24
DEFAULT_SPEECH_RMS_THRESHOLD = 350.0
PRE_ROLL_FRAMES = 4
WAKE_THRESHOLD = 0.5


def _setting(name: str, default: float, minimum: float) -> float:
    """Read a positive numeric voice setting without breaking startup."""
    try:
        value = float(os.getenv(name, str(default)))
        if value >= minimum:
            return value
    except (TypeError, ValueError):
        pass
    logger.warning("Invalid %s setting; using default %s", name, default)
    return default


def frame_rms(frame) -> float:
    """Return the root-mean-square amplitude of an audio frame."""
    import numpy as np

    samples = np.asarray(frame, dtype=np.float32)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def should_finish_capture(
    *,
    elapsed: float,
    silence_elapsed: float,
    speech_seen: bool,
    speech_duration: float,
    silence_seconds: float,
    max_command_seconds: float,
    speech_start_timeout: float,
) -> tuple[bool, str]:
    """Pure capture policy, separated from microphone I/O for unit testing."""
    if not speech_seen and elapsed >= speech_start_timeout:
        return True, "no_speech"
    if speech_seen and silence_elapsed >= silence_seconds:
        return True, "speech_complete"
    if elapsed >= max_command_seconds:
        return True, "max_duration"
    return False, "continue"


class WakeWordListener:
    """Listen locally for Alexa, then capture one spoken command."""

    def __init__(self, on_command: Callable[[str], None]):
        self._on_command = on_command
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._state_lock = threading.Lock()
        self._state = "starting"
        self._last_error: str | None = None
        self._last_transcript = ""
        self._started_at: float | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._set_state("starting")
        self._thread = threading.Thread(
            target=self._run,
            name="desktop-agent-wakeword",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._set_state("stopped")

    def status(self) -> dict:
        with self._state_lock:
            return {
                "available": self._state in {"listening", "command_listening", "processing"},
                "state": self._state,
                "wake_word": "Alexa",
                "last_error": self._last_error,
                "last_transcript": self._last_transcript,
                "thread_alive": bool(self._thread and self._thread.is_alive()),
                "started_at": self._started_at,
            }

    def _set_state(self, state: str, error: str | None = None) -> None:
        with self._state_lock:
            self._state = state
            self._last_error = error

    @staticmethod
    def _wav_bytes(frames: list) -> bytes:
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError(
                "NumPy is missing. Install voice support with: pip install -e .[voice]"
            ) from exc

        audio = np.concatenate(frames).astype(np.int16, copy=False)
        output = io.BytesIO()
        with wave.open(output, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio.tobytes())
        return output.getvalue()

    def _run_once(self) -> None:
        try:
            import sounddevice as sd
            import openwakeword
            from openwakeword.model import Model
            from desktop_agent.voice import transcribe_audio

            openwakeword.utils.download_models()
            model = Model(wakeword_models=["alexa"], inference_framework="onnx")
            audio_queue: queue.Queue = queue.Queue(maxsize=80)

            silence_seconds = _setting("VOICE_SILENCE_SECONDS", DEFAULT_SILENCE_SECONDS, 0.3)
            max_command_seconds = _setting("VOICE_MAX_COMMAND_SECONDS", DEFAULT_MAX_COMMAND_SECONDS, 2.0)
            speech_start_timeout = _setting("VOICE_SPEECH_START_TIMEOUT", DEFAULT_SPEECH_START_TIMEOUT, 1.0)
            min_speech_seconds = _setting("VOICE_MIN_SPEECH_SECONDS", DEFAULT_MIN_SPEECH_SECONDS, 0.08)
            speech_rms_threshold = _setting("VOICE_SPEECH_RMS_THRESHOLD", DEFAULT_SPEECH_RMS_THRESHOLD, 20.0)

            def audio_callback(indata, _frames, _time_info, status):
                if status:
                    logger.warning("Microphone stream status: %s", status)
                frame = indata[:, 0].copy()
                try:
                    audio_queue.put_nowait(frame)
                except queue.Full:
                    try:
                        audio_queue.get_nowait()
                        audio_queue.put_nowait(frame)
                    except queue.Empty:
                        pass

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=FRAME_SAMPLES,
                callback=audio_callback,
            ):
                with self._state_lock:
                    self._started_at = time.time()
                self._set_state("listening")
                pre_roll: deque = deque(maxlen=PRE_ROLL_FRAMES)
                recording: list = []
                command_started = False
                speech_seen = False
                last_voice_at = 0.0
                command_started_at = 0.0
                speech_duration = 0.0

                while not self._stop.is_set():
                    try:
                        frame = audio_queue.get(timeout=0.25)
                    except queue.Empty:
                        continue

                    if not command_started:
                        scores = model.predict(frame)
                        if any(float(score) >= WAKE_THRESHOLD for score in scores.values()):
                            recording = list(pre_roll)
                            recording.append(frame)
                            command_started = True
                            speech_seen = False
                            speech_duration = 0.0
                            command_started_at = time.monotonic()
                            last_voice_at = command_started_at
                            pre_roll.clear()
                            self._set_state("command_listening")
                        else:
                            pre_roll.append(frame)
                        continue

                    recording.append(frame)
                    now = time.monotonic()
                    elapsed = now - command_started_at
                    rms = frame_rms(frame)
                    if rms >= speech_rms_threshold:
                        speech_seen = True
                        speech_duration += FRAME_SAMPLES / SAMPLE_RATE
                        last_voice_at = now

                    finish, reason = should_finish_capture(
                        elapsed=elapsed,
                        silence_elapsed=now - last_voice_at,
                        speech_seen=speech_seen,
                        speech_duration=speech_duration,
                        silence_seconds=silence_seconds,
                        max_command_seconds=max_command_seconds,
                        speech_start_timeout=speech_start_timeout,
                    )
                    if not finish:
                        continue

                    command_started = False
                    self._set_state("processing")
                    if reason != "no_speech" and speech_seen and speech_duration >= min_speech_seconds:
                        try:
                            transcript = transcribe_audio(self._wav_bytes(recording), ".wav")
                            if transcript.strip():
                                with self._state_lock:
                                    self._last_transcript = transcript.strip()
                                self._on_command(transcript.strip())
                        except Exception as exc:
                            logger.exception("Voice command processing failed")
                            self._set_state("listening", f"Voice processing failed: {exc}")
                        else:
                            self._set_state("listening")
                    else:
                        logger.debug("Discarding wake-word capture: %s", reason)
                        self._set_state("listening")
                    recording = []
                    speech_seen = False
                    speech_duration = 0.0
                    pre_roll.clear()

                    # Discard frames queued while transcription/action processing ran.
                    while True:
                        try:
                            audio_queue.get_nowait()
                        except queue.Empty:
                            break

        except ImportError as exc:
            message = (
                "Voice dependencies are missing. Install them with: "
                "pip install -e .[voice]"
            )
            logger.warning("%s Details: %s", message, exc)
            self._set_state("unavailable", message)
        except Exception as exc:
            logger.exception("Alexa wake-word listener could not start")
            self._set_state("unavailable", str(exc))


    def _run(self) -> None:
        """Supervise the microphone worker and recover after device/model failures."""
        retry_delay = _setting("VOICE_RESTART_DELAY", 5.0, 2.0)
        max_retry_delay = 60.0
        while not self._stop.is_set():
            worker = threading.Thread(
                target=self._run_once,
                name="desktop-agent-audio-worker",
                daemon=True,
            )
            worker.start()
            while worker.is_alive() and not self._stop.is_set():
                worker.join(timeout=0.5)
            if self._stop.is_set():
                break
            with self._state_lock:
                previous_error = self._last_error or "Voice listener stopped unexpectedly."
            logger.warning(
                "Alexa listener stopped; retrying microphone/model initialization in %.1f seconds",
                retry_delay,
            )
            self._set_state("restarting", previous_error)
            if self._stop.wait(retry_delay):
                break
            retry_delay = min(retry_delay * 2, max_retry_delay)
