"""Microphone capture via pw-record (PipeWire), 16 kHz mono s16 WAV."""

import asyncio
import os
import signal
import tempfile

from .config import Config


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


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
