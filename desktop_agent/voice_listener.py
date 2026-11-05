"""Always-on local Alexa wake-word listener and post-wake command capture."""

from __future__ import annotations

import io
import logging
import queue
import threading
import time
import wave
from typing import Callable

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # openWakeWord expects 80 ms frames at 16 kHz.
SILENCE_SECONDS = 1.4
MAX_COMMAND_SECONDS = 15.0
WAKE_THRESHOLD = 0.5


class WakeWordListener:
    """Listen locally for 'Alexa', then capture one spoken command.

    All hardware/ML imports are deliberately lazy: the API can start even
    when the optional voice extra is not installed.
    """

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
                "available": self._state in {
                    "listening", "command_listening", "processing"
                },
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
        # NumPy is an optional voice dependency, so import it only when needed.
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

    def _run(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
            import openwakeword
            from openwakeword.model import Model
            from desktop_agent.voice import transcribe_audio

            # openWakeWord's PyPI package does not bundle pretrained weights.
            # Its downloader caches the models and skips files already present.
            openwakeword.utils.download_models()
            model = Model(
                wakeword_models=["alexa"],
                inference_framework="onnx",
            )
            audio_queue: queue.Queue = queue.Queue(maxsize=80)

            def audio_callback(indata, _frames, _time_info, status):
                if status:
                    logger.warning("Microphone stream status: %s", status)
                try:
                    audio_queue.put_nowait(indata[:, 0].copy())
                except queue.Full:
                    # Drop the oldest frame so the listener never builds
                    # unbounded latency when inference is temporarily busy.
                    try:
                        audio_queue.get_nowait()
                        audio_queue.put_nowait(indata[:, 0].copy())
                    except queue.Empty:
                        pass

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=FRAME_SAMPLES,
                callback=audio_callback,
            ):
                self._started_at = time.time()
                self._set_state("listening")
                recording: list = []
                command_started = False
                speech_seen = False
                last_voice_at = 0.0
                command_started_at = 0.0

                while not self._stop.is_set():
                    try:
                        frame = audio_queue.get(timeout=0.25)
                    except queue.Empty:
                        continue

                    if not command_started:
                        scores = model.predict(frame)
                        if any(float(score) >= WAKE_THRESHOLD for score in scores.values()):
                            recording = [frame]
                            command_started = True
                            speech_seen = False
                            command_started_at = time.monotonic()
                            last_voice_at = command_started_at
                            self._set_state("command_listening")
                        continue

                    recording.append(frame)
                    now = time.monotonic()
                    rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
                    if rms >= 350:
                        speech_seen = True
                        last_voice_at = now

                    elapsed = now - command_started_at
                    silence_elapsed = now - last_voice_at
                    if (
                        (speech_seen and silence_elapsed >= SILENCE_SECONDS)
                        or elapsed >= MAX_COMMAND_SECONDS
                    ):
                        command_started = False
                        self._set_state("processing")
                        if speech_seen:
                            try:
                                transcript = transcribe_audio(
                                    self._wav_bytes(recording), ".wav"
                                )
                                with self._state_lock:
                                    self._last_transcript = transcript
                                self._on_command(transcript)
                            except Exception as exc:
                                logger.exception("Voice command processing failed")
                                self._set_state(
                                    "listening",
                                    f"Voice processing failed: {exc}",
                                )
                            else:
                                self._set_state("listening")
                        else:
                            self._set_state("listening")
                        recording = []

                        # Discard audio buffered while transcription/command
                        # processing was running.
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
