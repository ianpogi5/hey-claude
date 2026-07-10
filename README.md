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

## License

Apache-2.0 (intended; not finalized).
