import threading

import numpy as np
import sounddevice as sd


class Recorder:
    """Records audio from the default input device at 16kHz mono float32."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._recording = False

    def start(self) -> None:
        """Begin recording, discarding any previously captured data."""
        with self._lock:
            self._chunks = []
            self._recording = True

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        """Stop recording and return all captured samples as a 1-D float32 array."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            self._recording = False
            if self._chunks:
                audio = np.concatenate(self._chunks).flatten()
            else:
                audio = np.empty(0, dtype=np.float32)
            self._chunks = []

        return audio

    @property
    def is_recording(self) -> bool:
        return self._recording

    def _callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        if status:
            print(f"sounddevice status: {status}")
        with self._lock:
            self._chunks.append(indata.copy())
