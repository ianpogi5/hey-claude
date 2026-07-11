"""Talk to Claude Code headless (`claude -p`), one resumable session at a time.

Uses --output-format stream-json so the caller can act on text as it is
generated (see Daemon._process: sentences are spoken while Claude is still
writing) and so the session id is known from the first event, which keeps
--resume working even if the run is cancelled mid-reply.
"""

import asyncio
import json
import logging
import os
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "hey-claude"
SESSION_FILE = STATE_DIR / "session-id"

# stream-json lines carrying big tool results can be long
_LINE_LIMIT = 8 * 1024 * 1024

OnText = Callable[[str], Awaitable[None]]


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

    async def ask(self, text: str, on_text: OnText | None = None) -> str:
        """Run claude; await on_text(chunk) for each streamed text delta.

        Returns the final reply. If resuming the saved session fails before
        any text arrived, retries once with a fresh session.
        """
        reply, ok, streamed = await self._run(text, resume=self.session_id, on_text=on_text)
        if not ok and self.session_id and not streamed:
            log.warning("resume of session %s failed, starting fresh", self.session_id)
            self.reset()
            reply, ok, streamed = await self._run(text, resume="", on_text=on_text)
        if not ok:
            raise ClaudeError(reply)
        return reply

    def _save_session(self, sid: str) -> None:
        if not sid or sid == self.session_id:
            return
        self.session_id = sid
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(sid)

    async def _run(self, text: str, resume: str,
                   on_text: OnText | None) -> tuple[str, bool, bool]:
        """Returns (reply_or_error, ok, streamed_any_text)."""
        cmd = [self._bin, "-p", text, "--output-format", "stream-json",
               "--include-partial-messages", "--verbose"]
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
            limit=_LINE_LIMIT,
        )
        parts: list[str] = []
        result_text: str | None = None
        is_error = False
        stderr_task = asyncio.create_task(self._proc.stderr.read())
        try:
            async for raw in self._proc.stdout:
                try:
                    data = json.loads(raw)
                except ValueError:
                    continue
                kind = data.get("type")
                if kind == "system" and data.get("subtype") == "init":
                    self._save_session(data.get("session_id", ""))
                elif kind == "stream_event":
                    delta = data.get("event", {}).get("delta", {})
                    if delta.get("type") == "text_delta" and (chunk := delta.get("text", "")):
                        parts.append(chunk)
                        if on_text:
                            await on_text(chunk)
                elif kind == "result":
                    self._save_session(data.get("session_id", ""))
                    is_error = bool(data.get("is_error"))
                    result_text = data.get("result")
            stderr = (await stderr_task).decode(errors="replace")
            returncode = await self._proc.wait()
        finally:
            stderr_task.cancel()
            self._proc = None
        streamed = bool(parts)
        if returncode != 0:
            return stderr.strip() or "claude exited non-zero", False, streamed
        if is_error:
            return result_text or "claude reported an error", False, streamed
        return result_text if result_text is not None else "".join(parts), True, streamed
