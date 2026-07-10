# hey-claude

Push-to-talk voice assistant for GNOME that talks to Claude Code. Read PLAN.md
first — it holds the architecture, open decisions, and milestones.

## Ground rules

- Two components: Python daemon (`heyclauded`, all logic) + GJS Shell extension
  (dumb indicator). Never put logic in the extension.
- Reuse the user's existing voice stack; don't duplicate it:
  - Piper TTS: `~/.claude/tts/venv/bin/piper`, model `~/.claude/tts/en_US-amy-medium.onnx`
  - Markdown→speech cleanup logic lives in `~/.claude/hooks/speak-response.sh` (port it into the daemon)
- Target GNOME Shell 49 (Fedora 43, Wayland). Extension API churn is expected;
  keep the extension minimal.
- D-Bus name: `org.kdc.HeyClaude` (session bus).
- The user's global Claude Code Stop hook speaks responses aloud — daemon-driven
  `claude -p` calls must not trigger double-speech (open decision in PLAN.md).
