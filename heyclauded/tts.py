"""Speech output: Piper → paplay, plus tiny generated earcons for state feedback."""

import asyncio
import contextlib
import json
import logging
import math
import os
import struct
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)


class Speaker:
    def __init__(self, cfg: Config):
        self._cfg = cfg
        self._procs: list[asyncio.subprocess.Process] = []
        self._rate = self._voice_rate()

    def _voice_rate(self) -> int:
        # the voice's .onnx.json declares its sample rate; amy-medium is 22050
        try:
            meta = json.loads(Path(self._cfg.piper_voice + ".json").read_text())
            return int(meta["audio"]["sample_rate"])
        except (OSError, KeyError, ValueError):
            return 22050

    async def speak(self, text: str) -> None:
        """Synthesize and play; returns when playback ends or stop() is called."""
        await self.start_stream()
        await self.feed(text)
        await self.finish()

    async def start_stream(self) -> None:
        """Open a piper→paplay pipeline that speaks each fed line in turn."""
        read_fd, write_fd = os.pipe()
        try:
            piper = await asyncio.create_subprocess_exec(
                self._cfg.piper_bin, "-m", self._cfg.piper_voice, "--output-raw",
                stdin=asyncio.subprocess.PIPE, stdout=write_fd,
                stderr=asyncio.subprocess.DEVNULL,
            )
            play = await asyncio.create_subprocess_exec(
                "paplay", "--raw", f"--rate={self._rate}",
                "--format=s16le", "--channels=1",
                stdin=read_fd,
            )
        finally:
            os.close(read_fd)
            os.close(write_fd)
        self._procs = [piper, play]

    async def feed(self, sentence: str) -> None:
        """Queue one utterance (piper synthesizes per input line)."""
        piper = self._procs[0] if self._procs else None
        if not piper or piper.returncode is not None:
            return
        piper.stdin.write(sentence.replace("\n", " ").encode() + b"\n")
        with contextlib.suppress(ConnectionResetError, BrokenPipeError):
            await piper.stdin.drain()

    async def finish(self) -> None:
        """Signal end of input and wait for playback to complete."""
        if not self._procs:
            return
        piper, play = self._procs
        try:
            if piper.returncode is None:
                piper.stdin.close()
            await play.wait()
        finally:
            self.stop()

    def stop(self) -> None:
        procs, self._procs = self._procs, []
        for proc in procs:
            if proc.returncode is None:
                proc.kill()


async def earcon(kind: str, enabled: bool = True) -> None:
    """Fire-and-forget feedback tone: 'listen', 'done', or 'error'."""
    if not enabled:
        return
    freq, ms = {"listen": (880, 120), "done": (587, 100), "error": (220, 300)}[kind]
    rate = 44100
    n = int(rate * ms / 1000)
    fade = max(1, int(rate * 0.008))
    samples = bytearray()
    for i in range(n):
        amp = 0.25 * min(1.0, i / fade, (n - 1 - i) / fade)
        samples += struct.pack("<h", int(32767 * amp * math.sin(2 * math.pi * freq * i / rate)))
    try:
        play = await asyncio.create_subprocess_exec(
            "paplay", "--raw", f"--rate={rate}", "--format=s16le", "--channels=1",
            stdin=asyncio.subprocess.PIPE,
        )
        play.stdin.write(bytes(samples))
        await play.stdin.drain()
        play.stdin.close()
        await play.wait()
    except OSError as e:
        log.warning("earcon playback failed: %s", e)
