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

## Install

What's usable today is the **M1 pipeline script**: the full voice loop
(record → transcribe → Claude → spoken reply) in one command, no daemon or
top-bar UI yet. The daemon and GNOME extension are milestones M2/M3 in
[PLAN.md](PLAN.md).

### Prerequisites

- Linux with PipeWire and PulseAudio utilities — you need `pw-record` and
  `paplay`, both standard on Fedora and most GNOME desktops
  (Debian/Ubuntu: `apt install pipewire-bin pulseaudio-utils`).
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and
  logged in — `claude` must work in your terminal.
- Python 3.10+ (tested on 3.14) with the `venv` module.
- A working microphone and speakers.

### Setup

```bash
git clone https://github.com/ianpogi5/hey-claude.git
cd hey-claude

python3 -m venv .venv
.venv/bin/pip install faster-whisper piper-tts

# Download a TTS voice (~60 MB, one time). Browse voices at
# https://rhasspy.github.io/piper-samples/
mkdir -p voices
.venv/bin/python -m piper.download_voices --download-dir voices en_US-amy-medium
export HEY_CLAUDE_PIPER_MODEL=$PWD/voices/en_US-amy-medium.onnx
```

If you already have Piper elsewhere, skip the download and point
`HEY_CLAUDE_PIPER` (binary) and `HEY_CLAUDE_PIPER_MODEL` (voice `.onnx`)
at your install.

### Use

```bash
.venv/bin/python scripts/m1-pipeline.py
```

Speak your question, press Enter to stop recording, and the reply is read
aloud. The first run downloads the Whisper `small` model (~460 MB) from
Hugging Face; later runs start instantly.

Useful flags:

| Flag | Effect |
|---|---|
| `--seconds 5` | record a fixed duration instead of Enter-to-stop |
| `--new` | start a fresh Claude session (default resumes the last one) |
| `--text "…"` | skip the microphone and send text (pipeline smoke test) |
| `--model base` | smaller/faster Whisper model, slightly less accurate |

Conversations continue across runs: the session id is kept in
`~/.local/state/hey-claude/session-id`, and Claude Code's own permission
prompts still apply to anything the session tries to do.

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
