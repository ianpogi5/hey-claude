"""Markdown → speakable text. Ported from the speak-response.sh Stop hook."""

import re


def clean_for_speech(t: str, limit: int = 1200) -> str:
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
