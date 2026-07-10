"""Local speech-to-text with faster-whisper. Model loads once and stays warm."""

import asyncio
import logging
import threading

from .config import Config

log = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, cfg: Config):
        self._cfg = cfg
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        # under the lock so a preload racing a first transcribe loads once
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                log.info("loading whisper model %r (%s)…",
                         self._cfg.whisper_model, self._cfg.whisper_compute)
                self._model = WhisperModel(
                    self._cfg.whisper_model, device="cpu",
                    compute_type=self._cfg.whisper_compute,
                )
                log.info("whisper model ready")
        return self._model

    async def preload(self) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self._load)

    async def transcribe(self, wav_path: str) -> str:
        def run() -> str:
            model = self._load()
            # vad_filter drops non-speech so silent recordings return ""
            # instead of whisper hallucinating a phrase
            segments, _info = model.transcribe(
                wav_path, language=self._cfg.language, beam_size=5,
                vad_filter=True,
            )
            return " ".join(seg.text.strip() for seg in segments).strip()

        return await asyncio.get_running_loop().run_in_executor(None, run)
