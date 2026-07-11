"""Configuration: ~/.config/hey-claude/config.toml over dataclass defaults."""

import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def default_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(xdg) / "hey-claude" / "config.toml"


def _default_piper() -> str:
    """Piper binary: $HEY_CLAUDE_PIPER, an existing ~/.claude/tts install,
    or piper installed alongside this interpreter (pip install piper-tts)."""
    if env := os.environ.get("HEY_CLAUDE_PIPER"):
        return env
    legacy = Path.home() / ".claude/tts/venv/bin/piper"
    if legacy.exists():
        return str(legacy)
    return str(Path(sys.executable).with_name("piper"))


def _default_piper_voice() -> str:
    if env := os.environ.get("HEY_CLAUDE_PIPER_MODEL"):
        return env
    return str(Path.home() / ".claude/tts/en_US-amy-medium.onnx")


@dataclass
class Config:
    # [stt]
    whisper_model: str = "small"
    whisper_compute: str = "int8"
    language: str = "en"
    preload_stt: bool = True
    # [audio]
    audio_target: str = ""  # pw-record --target; empty = default source
    max_record_seconds: float = 60.0
    silence_seconds: float = 1.5  # auto-stop after this much post-speech silence; 0 = off
    silence_threshold: float = 0.015  # RMS (0..1) below which audio counts as silence
    earcons: bool = True
    # [claude]
    claude_bin: str = "claude"
    claude_args: list[str] = field(default_factory=list)
    claude_cwd: str = ""
    # [tts]
    piper_bin: str = field(default_factory=_default_piper)
    piper_voice: str = field(default_factory=_default_piper_voice)
    speech_limit: int = 1200
    stream_tts: bool = True  # start speaking while claude is still writing


# (section, key in file) -> Config attribute
_KEYMAP = {
    ("stt", "model"): "whisper_model",
    ("stt", "compute"): "whisper_compute",
    ("stt", "language"): "language",
    ("stt", "preload"): "preload_stt",
    ("audio", "target"): "audio_target",
    ("audio", "max_record_seconds"): "max_record_seconds",
    ("audio", "silence_seconds"): "silence_seconds",
    ("audio", "silence_threshold"): "silence_threshold",
    ("audio", "earcons"): "earcons",
    ("claude", "bin"): "claude_bin",
    ("claude", "args"): "claude_args",
    ("claude", "cwd"): "claude_cwd",
    ("tts", "piper"): "piper_bin",
    ("tts", "voice"): "piper_voice",
    ("tts", "speech_limit"): "speech_limit",
    ("tts", "stream"): "stream_tts",
}


def load(path: Path | None = None) -> Config:
    path = path or default_config_path()
    cfg = Config()
    if not path.exists():
        return cfg
    data = tomllib.loads(path.read_text())
    for section, keys in data.items():
        if not isinstance(keys, dict):
            continue
        for key, value in keys.items():
            attr = _KEYMAP.get((section, key))
            if attr is None:
                raise ValueError(f"unknown config key [{section}] {key} in {path}")
            if value != "" and value != []:
                setattr(cfg, attr, value)
    return cfg
