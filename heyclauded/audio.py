"""Microphone capture via pw-record (PipeWire), 16 kHz mono s16 WAV."""

import array
import asyncio
import math
import os
import signal
import tempfile

from .config import Config

_WAV_HEADER = 44  # pw-record (libsndfile) writes a plain PCM RIFF header
_POLL = 0.2


class Recorder:
    def __init__(self, cfg: Config):
        self._cfg = cfg
        self._proc: asyncio.subprocess.Process | None = None
        self._path: str | None = None

    @property
    def active(self) -> bool:
        return self._proc is not None

    async def start(self) -> None:
        fd, self._path = tempfile.mkstemp(prefix="hey-claude-", suffix=".wav")
        os.close(fd)
        cmd = ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16"]
        if self._cfg.audio_target:
            cmd += ["--target", self._cfg.audio_target]
        cmd.append(self._path)
        self._proc = await asyncio.create_subprocess_exec(*cmd)

    async def stop(self) -> str:
        """Finish the capture and return the WAV path (caller deletes it)."""
        assert self._proc and self._path
        proc, path = self._proc, self._path
        self._proc = self._path = None
        proc.send_signal(signal.SIGINT)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        return path

    async def abort(self) -> None:
        if self._proc:
            path = await self.stop()
            _unlink(path)

    async def wait_for_silence(self, silence_seconds: float, threshold: float) -> None:
        """Return once `silence_seconds` of silence follows detected speech.

        Tails the WAV file as pw-record grows it, RMS per poll interval.
        Also returns if the capture stops underneath us; the caller bounds
        the total wait (max_record_seconds).
        """
        path = self._path
        offset = _WAV_HEADER
        silent_for = 0.0
        heard_speech = False
        while self.active and path == self._path:
            await asyncio.sleep(_POLL)
            try:
                with open(path, "rb") as f:
                    f.seek(offset)
                    data = f.read()
            except OSError:
                return
            offset += len(data) - (len(data) % 2)
            if len(data) < 2:
                continue
            if _rms(data) >= threshold:
                heard_speech = True
                silent_for = 0.0
            elif heard_speech:
                silent_for += _POLL
                if silent_for >= silence_seconds:
                    return


def _rms(data: bytes) -> float:
    """RMS of s16le samples, normalized to 0..1."""
    samples = array.array("h", data[: len(data) - (len(data) % 2)])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
