# hey-claude

Push-to-talk voice conversations with Claude Code, native to the GNOME desktop.

A small top-bar indicator (GNOME Shell extension) drives a background daemon that
records your voice, transcribes it locally, sends it to the `claude` CLI, and speaks
the reply aloud with Piper TTS.

**Status:** planning. See [PLAN.md](PLAN.md).

## Why

- GNOME has no system tray; the native pattern is a top-bar indicator backed by a
  D-Bus service. The indicator stays tiny and disposable; the daemon does the work.
- The pieces already exist and work: local Whisper STT, Claude Code headless mode
  (`claude -p`), Piper TTS. This project just wires them into a desktop-native,
  one-keypress loop.
- Claude Code brings its own superpowers along: MCP servers (e.g. Home Assistant),
  tools, and persistent sessions — so this is less "voice assistant" and more
  "Jarvis for your desktop".

## Architecture (short version)

```
┌────────────────────────┐   D-Bus    ┌──────────────────────────────┐
│ GNOME Shell extension  │ ─────────► │ hey-claude daemon (Python)   │
│ top-bar icon + states  │ ◄───────── │ record → STT → claude -p     │
│ click / keybinding     │  signals   │        → Piper TTS → speaker │
└────────────────────────┘            └──────────────────────────────┘
```

## Security & privacy

This assistant runs commands with **your** user account and Claude Code
configuration, so the security posture is the same as running `claude` in a
terminal — plus a microphone. Design rules the project follows:

- **Audio never leaves your machine.** Recording (PipeWire) and transcription
  (local Whisper) are fully local; only the transcribed *text* is sent to the
  Claude API, exactly as if you had typed it.
- **No recordings are kept.** Captured audio is a temp file deleted right after
  transcription, and `.gitignore` blocks WAV files from ever being committed.
- **Claude runs with its normal permission system.** The daemon invokes plain
  `claude -p` and will never pass `--dangerously-skip-permissions`. Restrict
  what a voice session may touch via `--allowedTools` in the daemon config.
- **Per-user control surface.** The D-Bus name lives on the *session* bus, so
  only your own logged-in session can trigger listening — nothing is exposed
  system-wide or over the network.
- **No secrets in this repo.** Configuration (model paths, claude args) lives
  in `~/.config/hey-claude/`, session state in `~/.local/state/hey-claude/` —
  both outside the source tree.

Found a vulnerability? See [SECURITY.md](SECURITY.md).

## License

[Apache-2.0](LICENSE).
