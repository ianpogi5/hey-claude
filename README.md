# hey-claude

Push-to-talk voice conversations with Claude Code, native to the GNOME desktop.

A small top-bar indicator (GNOME Shell extension) drives a background daemon that
records your voice, transcribes it locally, sends it to the `claude` CLI, and speaks
the reply aloud with Piper TTS.

**Status:** M3 — daemon + GNOME Shell extension work: top-bar mic icon,
push-to-talk keybinding, barge-in. Polish (M4) remains. See
[PLAN.md](PLAN.md).

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

### Prerequisites

- Linux with PipeWire and PulseAudio utilities — you need `pw-record` and
  `paplay`, both standard on Fedora and most GNOME desktops
  (Debian/Ubuntu: `apt install pipewire-bin pulseaudio-utils`).
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and
  logged in — `claude` must work in your terminal.
- Python 3.11+ (tested on 3.14) with the `venv` module.
- A working microphone and speakers.

### Setup

```bash
git clone https://github.com/ianpogi5/hey-claude.git
cd hey-claude

python3 -m venv .venv
.venv/bin/pip install -e . piper-tts

# Download a TTS voice (~60 MB, one time). Browse voices at
# https://rhasspy.github.io/piper-samples/
mkdir -p voices
.venv/bin/python -m piper.download_voices --download-dir voices en_US-amy-medium
export HEY_CLAUDE_PIPER_MODEL=$PWD/voices/en_US-amy-medium.onnx
```

If you already have Piper elsewhere, skip the download and point
`HEY_CLAUDE_PIPER` (binary) and `HEY_CLAUDE_PIPER_MODEL` (voice `.onnx`)
at your install. To make settings permanent (voice path, whisper model,
Claude tool restrictions, audio device …), copy
[config.example.toml](config.example.toml) to
`~/.config/hey-claude/config.toml` and edit.

### Run the daemon

```bash
./scripts/install-daemon.sh
```

That installs a systemd user service plus D-Bus activation: the daemon starts
on demand at the first call and keeps the Whisper model warm between
questions. Push-to-talk is one D-Bus call — press once, speak, press again:

```bash
gdbus call --session --dest org.kdc.HeyClaude \
    --object-path /org/kdc/HeyClaude --method org.kdc.HeyClaude.Toggle
```

You get a beep when it starts listening, a lower beep when it stops, and the
answer is read aloud. Pressing the key while Claude is speaking interrupts
and listens again (barge-in). You rarely need `gdbus` by hand though — install
the extension:

### GNOME Shell extension (GNOME 49)

```bash
./scripts/install-extension.sh
```

Log out and back in once (Wayland can't reload the shell), and you get:

- a microphone icon in the top bar that changes with state —
  red while recording, orange transcribing, yellow thinking, blue speaking;
- **left-click** or **`Super+\`** = push-to-talk (start / stop / barge-in);
- right-click menu: the last exchange, New conversation, Cancel,
  Edit configuration, Quit daemon.

Change the shortcut with:

```bash
gsettings --schemadir ~/.local/share/gnome-shell/extensions/hey-claude@kdc.org/schemas \
    set org.gnome.shell.extensions.hey-claude toggle-shortcut "['<Super>backslash']"
```

(The default is `Super+\`; `Super+Space` is taken by GNOME's input-source
switcher.) Without the extension — or on a GNOME release it hasn't been
ported to yet — everything still works via `gdbus` and a GNOME custom
keyboard shortcut bound to the Toggle command above.

The rest of the interface, for scripts and the future extension:

| D-Bus | Purpose |
|---|---|
| `Toggle()` | push-to-talk: start/stop recording, or interrupt speech |
| `Ask(s text)` | skip the microphone, send text through the same pipeline |
| `Cancel()` | abandon whatever is happening, back to idle |
| `NewConversation()` | forget the session, start fresh next question |
| `Quit()` | stop the daemon (D-Bus activation restarts it on demand) |
| `StateChanged(s)` / `Transcript(s,s)` signals | drive UIs: idle/recording/transcribing/thinking/speaking; what you said and what Claude replied |

The first question after install downloads the Whisper `small` model
(~460 MB) from Hugging Face; after that the model loads from disk at daemon
start. Conversations persist across questions and daemon restarts (session id
in `~/.local/state/hey-claude/session-id`); Claude Code's own permission
prompts still apply to anything the session tries to do.

### One-shot script (no daemon)

`scripts/m1-pipeline.py` is the original milestone-1 proof: the same loop as
a single foreground command, printing per-stage timings — useful for testing
your audio/STT setup. `--text "…"` skips the microphone, `--new` starts a
fresh session, `--seconds 5` records a fixed duration.

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
