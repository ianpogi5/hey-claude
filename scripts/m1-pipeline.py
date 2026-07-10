#!/usr/bin/env python3
"""M1 pipeline proof: record → Whisper STT → `claude -p` → Piper TTS.

No UI, no daemon — just the full voice loop once, with per-stage timings.
Run from the project venv: .venv/bin/python scripts/m1-pipeline.py

Exit criterion (PLAN.md): ask "what lights are on?" and hear a correct
answer in acceptable time.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PIPER = Path.home() / ".claude/tts/venv/bin/piper"
PIPER_MODEL = Path.home() / ".claude/tts/en_US-amy-medium.onnx"
STATE_DIR = Path.home() / ".local/state/hey-claude"
SESSION_FILE = STATE_DIR / "session-id"


def record(wav_path: str, seconds: float | None) -> float:
    """Capture 16 kHz mono s16 audio with pw-record. Returns capture duration."""
    cmd = [
        "pw-record", "--rate", "16000", "--channels", "1", "--format", "s16",
        wav_path,
    ]
    proc = subprocess.Popen(cmd)
    start = time.monotonic()
    try:
        if seconds:
            print(f"● recording for {seconds:g}s … speak now")
            time.sleep(seconds)
        else:
            print("● recording … press Enter to stop")
            input()
    except KeyboardInterrupt:
        pass
    finally:
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=5)
    return time.monotonic() - start


def transcribe(wav_path: str, model_name: str) -> tuple[str, float, float]:
    """Whisper STT. Returns (text, model_load_seconds, transcribe_seconds)."""
    from faster_whisper import WhisperModel

    t0 = time.monotonic()
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    t_load = time.monotonic() - t0

    t0 = time.monotonic()
    segments, _info = model.transcribe(wav_path, language="en", beam_size=5)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return text, t_load, time.monotonic() - t0


def ask_claude(prompt: str, new_session: bool) -> tuple[str, str]:
    """Run `claude -p`, resuming the saved session when possible.

    Returns (response_text, session_id).
    """
    env = os.environ | {"HEY_CLAUDE_SUPPRESS_TTS": "1"}

    def run(resume: str | None) -> subprocess.CompletedProcess:
        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        if resume:
            cmd += ["--resume", resume]
        return subprocess.run(cmd, capture_output=True, text=True, env=env)

    resume = None
    if not new_session and SESSION_FILE.exists():
        resume = SESSION_FILE.read_text().strip() or None

    result = run(resume)
    if result.returncode != 0 and resume:
        print(f"  (resume of {resume} failed, starting fresh session)")
        result = run(None)
    if result.returncode != 0:
        sys.exit(f"claude failed: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    session_id = data.get("session_id", "")
    if session_id:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(session_id)
    return data.get("result", ""), session_id


def clean_for_speech(t: str, limit: int = 1200) -> str:
    """Markdown → speakable text. Ported from ~/.claude/hooks/speak-response.sh."""
    t = re.sub(r"```.*?```", " Code is on screen. ", t, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"https?://\S+", " (link) ", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*+]\s+", " ", t, flags=re.M)
    t = re.sub(r"\|", " ", t)
    t = re.sub(r"[*_#>]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limit:
        cut = t[:limit]
        cut = cut[: cut.rfind(". ") + 1] or cut
        t = cut + " The rest is on screen."
    return t


def speak(text: str) -> float:
    """Piper → paplay. Returns seconds until audio playback finished."""
    t0 = time.monotonic()
    piper = subprocess.Popen(
        [str(PIPER), "-m", str(PIPER_MODEL), "--output-raw"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    play = subprocess.Popen(
        ["paplay", "--raw", "--rate=22050", "--format=s16le", "--channels=1"],
        stdin=piper.stdout,
    )
    piper.stdin.write(text.encode())
    piper.stdin.close()
    piper.stdout.close()
    play.wait()
    return time.monotonic() - t0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=None,
                    help="record a fixed duration instead of Enter-to-stop")
    ap.add_argument("--model", default="small",
                    help="faster-whisper model (default: small)")
    ap.add_argument("--new", action="store_true",
                    help="start a fresh claude session")
    ap.add_argument("--text", default=None,
                    help="skip recording/STT and send this text to claude")
    ap.add_argument("--wav", default=None,
                    help="skip recording and transcribe this WAV file")
    args = ap.parse_args()

    timings: list[tuple[str, float]] = []

    if args.text:
        prompt = args.text
    else:
        if args.wav:
            wav = args.wav
        else:
            wav = tempfile.mktemp(suffix=".wav", prefix="hey-claude-m1-")
            timings.append(("record", record(wav, args.seconds)))
        prompt, t_load, t_stt = transcribe(wav, args.model)
        timings += [("whisper load", t_load), ("transcribe", t_stt)]
        if not args.wav:
            os.unlink(wav)
        if not prompt:
            sys.exit("heard nothing — no transcript")
        print(f"you: {prompt}")

    t0 = time.monotonic()
    response, session_id = ask_claude(prompt, args.new)
    timings.append(("claude", time.monotonic() - t0))
    print(f"claude ({session_id}): {response}")

    speech = clean_for_speech(response)
    if speech:
        timings.append(("speak (incl. playback)", speak(speech)))

    print("\ntimings:")
    for name, secs in timings:
        print(f"  {name:24s} {secs:6.2f}s")


if __name__ == "__main__":
    main()
