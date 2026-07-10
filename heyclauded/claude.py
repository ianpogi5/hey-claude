"""Talk to Claude Code headless (`claude -p`), one resumable session at a time."""

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "hey-claude"
SESSION_FILE = STATE_DIR / "session-id"


class ClaudeError(RuntimeError):
    pass


class ClaudeSession:
    def __init__(self, cfg: Config):
        self._cfg = cfg
        # under systemd --user, PATH lacks ~/.local/bin where claude usually lives
        self._bin = cfg.claude_bin
        if "/" not in self._bin:
            self._bin = (shutil.which(self._bin)
                         or str(Path.home() / ".local/bin" / self._bin))
        self._proc: asyncio.subprocess.Process | None = None
        self.session_id = ""
        if SESSION_FILE.exists():
            self.session_id = SESSION_FILE.read_text().strip()

    def reset(self) -> None:
        self.session_id = ""
        SESSION_FILE.unlink(missing_ok=True)

    def cancel(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.kill()

    async def ask(self, text: str) -> str:
        reply, ok = await self._run(text, resume=self.session_id)
        if not ok and self.session_id:
            log.warning("resume of session %s failed, starting fresh", self.session_id)
            self.reset()
            reply, ok = await self._run(text, resume="")
        if not ok:
            raise ClaudeError(reply)
        return reply

    async def _run(self, text: str, resume: str) -> tuple[str, bool]:
        """Returns (reply_or_error, ok)."""
        cmd = [self._bin, "-p", text, "--output-format", "json"]
        if resume:
            cmd += ["--resume", resume]
        cmd += self._cfg.claude_args
        env = os.environ | {"HEY_CLAUDE_SUPPRESS_TTS": "1"}
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self._cfg.claude_cwd or None,
        )
        try:
            stdout, stderr = await self._proc.communicate()
        finally:
            proc, self._proc = self._proc, None
        if proc.returncode != 0:
            return stderr.decode(errors="replace").strip() or "claude exited non-zero", False

        data = json.loads(stdout)
        if sid := data.get("session_id"):
            self.session_id = sid
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            SESSION_FILE.write_text(sid)
        if data.get("is_error"):
            return data.get("result", "claude reported an error"), False
        return data.get("result", ""), True
