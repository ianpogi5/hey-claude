# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately via
[GitHub security advisories](https://github.com/ianpogi5/hey-claude/security/advisories/new)
rather than opening a public issue. You should get a response within a week.

## Scope notes

hey-claude is a per-user desktop assistant. Things we consider security bugs:

- Any way for another user or process outside your session to trigger
  recording, read transcripts, or drive the daemon (the D-Bus service must be
  session-bus only).
- Audio or transcript data written anywhere other than the documented temp
  file (deleted after transcription) and `~/.local/state/hey-claude/`.
- The daemon invoking `claude` with broader permissions than the user
  configured (e.g. bypassing the permission system).

Prompt-injection through spoken input has the same trust model as typing into
`claude` yourself: constrain the blast radius with `--allowedTools` in the
daemon config.
