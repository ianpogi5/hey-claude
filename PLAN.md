# hey-claude — Plan

Goal: press a key (or click the top-bar icon), speak, and have Claude answer out
loud. Low friction, desktop-native, everything local except the Claude API call.

## Decisions made

| Decision | Choice | Rationale |
|---|---|---|
| Desktop surface | GNOME Shell extension (top-bar indicator) | GNOME has no tray; top-bar + D-Bus service is the native pattern. AppIndicator would need a third-party extension anyway. |
| Split | Dumb extension + smart daemon | Extensions break across GNOME majors (Fedora ships two per year). Keep the GJS part ~100 lines so porting is trivial; all logic lives in the daemon. |
| Activation | Push-to-talk (toggle), not wake-word | Always-on listening is heavy, finicky, and a privacy smell. PTT via keybinding + icon click. |
| Brain | `claude -p` (headless Claude Code CLI) | Gets sessions, tools, and the user's MCP servers (Home Assistant etc.) for free. Agent SDK is the later upgrade path if we outgrow the CLI. |
| TTS | Piper, `en_US-amy-medium` | Already installed and proven at `~/.claude/tts/` (venv + model). Same voice as the existing Claude Code Stop hook. |
| Language | Daemon in Python, extension in GJS | Python: best STT/audio library support, easy D-Bus (dasbus/gdbus). GJS: mandatory for Shell extensions. |

## Decisions still open

1. **STT engine** — ~~faster-whisper vs whisper.cpp~~ **Resolved: faster-whisper.**
   Installs clean on Python 3.14; `small`/int8 on CPU transcribes a short
   utterance in ~1.5 s with perfect accuracy (M1 test). Keep the model warm in
   the daemon to hide the ~2 s load. Revisit only if daemon RSS is a problem.
2. **Keybinding mechanism** — ~~open~~ **Resolved: extension keybinding**
   (`toggle-shortcut`, default `<Super>backslash` — `<Super>space` collides
   with GNOME input-source switching). Portal shortcuts remain the fallback
   if the extension ever lags a GNOME release.
3. **Session model** — ~~open~~ **Resolved: both.** The daemon resumes the
   saved session by default; `NewConversation()` rotates it.
4. **Interruption** — ~~open~~ **Resolved: barge-in.** `Toggle()` while
   speaking kills playback and starts recording.
5. **Coexistence with the existing Stop hook** — ~~open~~ **Resolved: detect
   and skip.** `~/.claude/hooks/speak-response.sh` now exits early when
   `HEY_CLAUDE_SUPPRESS_TTS=1`, which the pipeline sets in the environment of
   every `claude -p` it spawns.

## Components

### 1. `heyclauded` — the daemon (Python, systemd user service)

State machine: `idle → recording → transcribing → thinking → speaking → idle`
(any state → `idle` on Cancel).

- **Audio in:** PipeWire capture (`sounddevice` or `pw-record` subprocess),
  16 kHz mono WAV. Record while PTT active; stop on toggle/silence timeout.
- **STT:** local Whisper (open decision #1). Model loaded once, kept warm.
- **Claude:** `claude -p <text> --output-format json` with `--resume <session>`;
  working directory and allowed tools configurable. Capture the response text.
- **TTS:** pipe response through the same markdown-stripping cleanup as the
  existing `speak-response.sh` hook, then Piper → `paplay`. Reuse, don't fork,
  the cleanup logic (extract it into the daemon).
- **D-Bus:** own `org.kdc.HeyClaude` on the session bus.
  - Methods: `Toggle()`, `StartListening()`, `StopListening()`, `Cancel()`,
    `NewConversation()`, `Ask(s text)` (text entry / testing), `Quit()`
  - Signals: `StateChanged(s state)`, `Transcript(s who, s text)`
  - Properties: `State`, `SessionId`
- **Config:** `~/.config/hey-claude/config.toml` (model paths, claude args,
  audio device, silence timeout).

### 2. GNOME Shell extension (GJS, targets GNOME 49)

- Top-bar `PanelMenu.Button` with a microphone icon; icon/color reflects
  `StateChanged` (idle / recording / thinking / speaking).
- Click = `Toggle()`. Keybinding (e.g. `<Super>space`, configurable) = `Toggle()`.
- Popup menu: New conversation · Show last transcript · Settings · Quit daemon.
- Spawns/activates the daemon via D-Bus activation if not running.
- Zero business logic. If the extension breaks on GNOME 50, everything still
  works via keybinding-less D-Bus calls (`gdbus call`).

### 3. Packaging (later)

- systemd user unit + D-Bus service file for activation.
- Extension zip for extensions.gnome.org; RPM/copr for the daemon eventually.

## Milestones

- **M1 — pipeline proof, no UI.** ✅ Done: `scripts/m1-pipeline.py` (record →
  STT → `claude -p` → Piper, with per-stage timings and session resume via
  `~/.local/state/hey-claude/session-id`). Verified end-to-end 2026-07-11 with
  a Piper-synthesized question: transcribe 1.5 s, `claude -p` ~14 s (warm),
  TTS ~2 s. `claude -p` dominates latency → M2/M4 must add instant earcon
  feedback and look at streaming. Still to do: live-mic run + the "what lights
  are on?" HA test.
- **M2 — daemon.** ✅ Done 2026-07-11: `heyclauded` package (asyncio +
  dbus-fast), full state machine incl. barge-in, warm Whisper model, earcons,
  TOML config, systemd user unit + D-Bus activation
  (`scripts/install-daemon.sh`). Verified over `gdbus`: Ask, Toggle w/ silent
  mic (VAD → idle), Cancel mid-thinking, NewConversation, Quit, activation
  from cold. Notes: dbus-broker needs `ReloadConfig` to see new service files;
  systemd user env lacks `~/.local/bin` so the claude binary is resolved
  explicitly. Silence auto-stop deferred to M4 (safety cap:
  `max_record_seconds`).
- **M3 — extension.** ✅ Done 2026-07-11: `extension/` (GJS ESM, GNOME 49) —
  PanelMenu.Button with per-state icon+color, primary-click/keybinding →
  `Toggle()`, menu (last exchange, New conversation, Cancel, Edit config,
  Quit), D-Bus proxy with `DO_NOT_AUTO_START_AT_CONSTRUCTION` so login
  doesn't spawn the daemon but the first action does. ~140 lines, zero
  business logic. Verified ACTIVE with no JS errors in a nested headless
  gnome-shell 49; enabled for the real session (visible after next login).
  `scripts/install-extension.sh` installs + compiles schemas.
- **M4 — polish.** Barge-in, transcript window/notifications, settings UI
  (or just the config file + a menu entry that opens it), packaging.

## Risks

- **Extension churn:** GNOME 50 lands in Fedora ~April; mitigated by the
  dumb-extension design.
- **Latency:** `claude -p` cold start + model thinking can be seconds. Mitigate
  with instant audio feedback (earcon on PTT), streaming output → start TTS on
  first sentence (Agent SDK upgrade path if CLI streaming is awkward).
- **Wayland audio/global-shortcut quirks:** PipeWire capture is solid; extension
  keybindings sidestep portal complexity for now.
- **Double-speak with the existing Stop hook** (open decision #5).

## Environment facts (this machine, 2026-07-11)

- Fedora 43, GNOME Shell 49.8 (Wayland), zsh.
- Piper venv: `~/.claude/tts/venv/bin/piper`; model `~/.claude/tts/en_US-amy-medium.onnx`.
- Existing speech-out reference implementation: `~/.claude/hooks/speak-response.sh`.
- `claude` CLI 2.1.206 at `~/.local/bin/claude`; MCP servers include Home Assistant.
- No whisper/STT installed yet.
