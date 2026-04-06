import io
import logging
import os
import struct
import wave

import httpx
import numpy as np

log = logging.getLogger(__name__)


def _resolve_device_and_compute(device: str, compute_type: str) -> tuple[str, str]:
    if device == "auto":
        try:
            import ctranslate2
            if "cuda" in ctranslate2.get_supported_compute_types("cuda"):
                device = "cuda"
            else:
                device = "cpu"
        except Exception:
            device = "cpu"
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type


class LocalTranscriber:
    def __init__(self, model_size="base", device="auto", compute_type="auto", language="en"):
        self.model_size = model_size
        self.device, self.compute_type = _resolve_device_and_compute(device, compute_type)
        self.language = language
        self._model = None

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            log.info("Loading model '%s' on %s (%s)", self.model_size, self.device, self.compute_type)
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)

    def transcribe(self, audio: np.ndarray) -> str:
        self._load_model()
        lang = None if self.language == "auto" else self.language
        segments, _ = self._model.transcribe(audio, language=lang)
        return " ".join(seg.text.strip() for seg in segments)


class GroqTranscriber:
    def __init__(self, api_key: str, language="en"):
        self.api_key = api_key
        self.language = language

    def _to_wav(self, audio: np.ndarray) -> bytes:
        int16 = (audio * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(int16.tobytes())
        return buf.getvalue()

    def transcribe(self, audio: np.ndarray) -> str:
        wav_bytes = self._to_wav(audio)
        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
        data = {"model": "whisper-large-v3"}
        if self.language != "auto":
            data["language"] = self.language

        resp = httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            files=files,
            data=data,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["text"]


def create_transcriber(config: dict):
    tc = config["transcription"]
    if tc["backend"] == "groq":
        api_key = config["groq"]["api_key"] or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("Groq API key not configured")
        return GroqTranscriber(api_key=api_key, language=tc["language"])
    return LocalTranscriber(
        model_size=tc["model"],
        device=tc["device"],
        compute_type=tc["compute_type"],
        language=tc["language"],
    )
