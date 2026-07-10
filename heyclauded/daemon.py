"""State machine and D-Bus service.

States: idle → recording → transcribing → thinking → speaking → idle.
Cancel from any state returns to idle; Toggle while speaking is barge-in
(stop playback, start recording).
"""

import asyncio
import contextlib
import logging
import os

from dbus_fast.service import ServiceInterface, method, dbus_property, signal as dbus_signal
from dbus_fast.constants import PropertyAccess

from . import BUS_NAME
from .audio import Recorder
from .claude import ClaudeError, ClaudeSession
from .config import Config
from .speech import clean_for_speech
from .stt import Transcriber
from .tts import Speaker, earcon

log = logging.getLogger(__name__)

IDLE, RECORDING, TRANSCRIBING, THINKING, SPEAKING = (
    "idle", "recording", "transcribing", "thinking", "speaking")


class Daemon:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.state = IDLE
        self.recorder = Recorder(cfg)
        self.stt = Transcriber(cfg)
        self.claude = ClaudeSession(cfg)
        self.speaker = Speaker(cfg)
        self.iface: "HeyClaudeInterface | None" = None
        self.stopped = asyncio.Event()
        self._pipeline: asyncio.Task | None = None
        self._auto_stop: asyncio.Task | None = None
        self._noise: set[asyncio.Task] = set()

    # -- helpers -------------------------------------------------------

    def _set_state(self, state: str) -> None:
        if state == self.state:
            return
        log.info("state: %s → %s", self.state, state)
        self.state = state
        if self.iface:
            self.iface.StateChanged(state)
            self.iface.emit_properties_changed({"State": state})

    def _transcript(self, who: str, text: str) -> None:
        if self.iface:
            self.iface.Transcript(who, text)

    def _beep(self, kind: str) -> None:
        task = asyncio.create_task(earcon(kind, self.cfg.earcons))
        self._noise.add(task)
        task.add_done_callback(self._noise.discard)

    async def _cancel_pipeline(self) -> None:
        if self._pipeline and not self._pipeline.done():
            self._pipeline.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pipeline
        self._pipeline = None

    # -- commands (D-Bus methods land here) ----------------------------

    async def toggle(self) -> None:
        if self.state == IDLE:
            await self.start_listening()
        elif self.state == RECORDING:
            await self.stop_listening()
        elif self.state == SPEAKING:  # barge-in
            await self._cancel_pipeline()
            self._set_state(IDLE)
            await self.start_listening()
        # transcribing/thinking: ignore — Cancel is the escape hatch

    async def start_listening(self) -> None:
        if self.state != IDLE:
            return
        self._set_state(RECORDING)
        self._beep("listen")
        await self.recorder.start()
        self._auto_stop = asyncio.create_task(self._auto_stop_timer())

    async def _auto_stop_timer(self) -> None:
        await asyncio.sleep(self.cfg.max_record_seconds)
        log.info("max record time reached, stopping capture")
        await self.stop_listening()

    async def stop_listening(self) -> None:
        if self.state != RECORDING:
            return
        if self._auto_stop and not self._auto_stop.done():
            self._auto_stop.cancel()
        wav = await self.recorder.stop()
        self._pipeline = asyncio.create_task(self._process(wav=wav))

    async def ask(self, text: str) -> None:
        """Text entry point: same pipeline, skipping recording/STT."""
        if self.state == SPEAKING:
            await self._cancel_pipeline()
            self._set_state(IDLE)
        if self.state != IDLE:
            return
        self._pipeline = asyncio.create_task(self._process(text=text))

    async def cancel(self) -> None:
        await self.recorder.abort()
        await self._cancel_pipeline()
        self._set_state(IDLE)

    async def new_conversation(self) -> None:
        self.claude.reset()
        if self.iface:
            self.iface.emit_properties_changed({"SessionId": ""})
        self._beep("done")

    async def quit(self) -> None:
        await self.cancel()
        # let the Quit reply flush before the bus goes away
        asyncio.get_running_loop().call_later(0.2, self.stopped.set)

    # -- the pipeline ---------------------------------------------------

    async def _process(self, wav: str | None = None, text: str | None = None) -> None:
        try:
            if wav is not None:
                self._set_state(TRANSCRIBING)
                try:
                    text = await self.stt.transcribe(wav)
                finally:
                    with contextlib.suppress(OSError):
                        os.unlink(wav)
            if not text:
                log.info("no speech detected")
                self._beep("error")
                self._set_state(IDLE)
                return

            self._transcript("you", text)
            self._set_state(THINKING)
            reply = await self.claude.ask(text)
            if self.iface:
                self.iface.emit_properties_changed({"SessionId": self.claude.session_id})
            self._transcript("claude", reply)

            speech = clean_for_speech(reply, self.cfg.speech_limit)
            if speech:
                self._set_state(SPEAKING)
                await self.speaker.speak(speech)
            self._set_state(IDLE)
        except asyncio.CancelledError:
            self.claude.cancel()
            self.speaker.stop()
            raise
        except ClaudeError as e:
            log.error("claude failed: %s", e)
            self._beep("error")
            self._set_state(IDLE)
        except Exception:
            log.exception("pipeline failed")
            self._beep("error")
            self._set_state(IDLE)


class HeyClaudeInterface(ServiceInterface):
    def __init__(self, daemon: Daemon):
        super().__init__(BUS_NAME)
        self._d = daemon
        daemon.iface = self

    @method()
    async def Toggle(self):
        await self._d.toggle()

    @method()
    async def StartListening(self):
        await self._d.start_listening()

    @method()
    async def StopListening(self):
        await self._d.stop_listening()

    @method()
    async def Cancel(self):
        await self._d.cancel()

    @method()
    async def NewConversation(self):
        await self._d.new_conversation()

    @method()
    async def Ask(self, text: 's'):
        await self._d.ask(text)

    @method()
    async def Quit(self):
        await self._d.quit()

    @dbus_signal()
    def StateChanged(self, state: 's') -> 's':
        return state

    @dbus_signal()
    def Transcript(self, who: 's', text: 's') -> 'ss':
        return [who, text]

    @dbus_property(access=PropertyAccess.READ)
    def State(self) -> 's':
        return self._d.state

    @dbus_property(access=PropertyAccess.READ)
    def SessionId(self) -> 's':
        return self._d.claude.session_id
