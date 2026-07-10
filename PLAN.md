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

1. **STT engine** — `faster-whisper` (Python, easy streaming, CTranslate2) vs
   `whisper.cpp` (C++, lighter deps, needs subprocess wrapper). Leaning
   faster-whisper with `small`/`base` model; benchmark both on this machine
   (no GPU assumptions).
2. **Keybinding mechanism** — extension-registered keybinding (simplest, works
   today) vs XDG GlobalShortcuts portal (survives without the extension, more
   moving parts). Start with the extension keybinding.
3. **Session model** — one long-lived `claude` session resumed forever, vs
   "new conversation" menu action that rotates the session id. Probably both:
   resume by default, menu item to start fresh.
4. **Interruption** — should speaking stop when you press PTT again? (Probably
   yes: barge-in = cancel TTS + start recording.)
5. **Coexistence with the existing Stop hook** — the user's global Stop hook
   already speaks responses in terminal sessions. The daemon must not
   double-speak: run `claude -p` with hooks disabled for its sessions, or
   detect and skip.

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
    `NewConversation()`
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

- **M1 — pipeline proof, no UI.** A single script: record N seconds → STT →
  `claude -p` → Piper speaks. Validates latency and the STT choice. Exit
  criterion: ask "what lights are on?" and hear a correct answer (via the HA
  MCP server) in acceptable time.
- **M2 — daemon.** Proper state machine, D-Bus interface, systemd user service,
  config file. Controllable entirely with `gdbus call`.
- **M3 — extension.** Top-bar indicator + keybinding wired to the daemon.
  This is the "it's a real app" moment.
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
