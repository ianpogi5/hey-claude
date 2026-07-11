"""Markdown → speakable text. Ported from the speak-response.sh Stop hook."""

import re

TRUNCATION_NOTICE = "The rest is on screen."
CODE_NOTICE = "Code is on screen."

# sentence end: terminal punctuation (+ closing quotes/brackets) then whitespace,
# or a paragraph break
_BOUNDARY = re.compile(r'[.!?:;][)\]"\'’”]*\s+|\n{2,}')


def _clean_inline(t: str) -> str:
    """Everything clean_for_speech does except code blocks and truncation."""
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"https?://\S+", " (link) ", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*+]\s+", " ", t, flags=re.M)
    t = re.sub(r"\|", " ", t)
    t = re.sub(r"[*_#>]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def clean_for_speech(t: str, limit: int = 1200) -> str:
    t = re.sub(r"```.*?```", f" {CODE_NOTICE} ", t, flags=re.S)
    t = _clean_inline(t)
    if len(t) > limit:
        cut = t[:limit]
        cut = cut[: cut.rfind(". ") + 1] or cut
        t = f"{cut} {TRUNCATION_NOTICE}"
    return t


class SentenceSplitter:
    """Incrementally turn streamed markdown into speakable sentences.

    feed() returns complete cleaned sentences as they become available;
    flush() returns whatever remains. Code fences are elided to CODE_NOTICE,
    and output stops with TRUNCATION_NOTICE once `limit` characters have
    been emitted.
    """

    def __init__(self, limit: int = 1200):
        self._buf = ""
        self._in_fence = False
        self._emitted = 0
        self._limit = limit
        self._truncated = False

    def feed(self, chunk: str) -> list[str]:
        self._buf += chunk
        out: list[str] = []
        while True:
            if self._in_fence:
                end = self._buf.find("```", 3)
                if end < 0:
                    # drop fence innards; keep the opener plus a possible
                    # partial closing marker split across chunks
                    if len(self._buf) > 5:
                        self._buf = self._buf[:3] + self._buf[-2:]
                    break
                self._buf = self._buf[end + 3:]
                self._in_fence = False
                continue

            fence = self._buf.find("```")
            m = _BOUNDARY.search(self._buf)
            if fence >= 0 and (not m or fence < m.start()):
                self._emit(self._buf[:fence], out)
                self._emit(CODE_NOTICE, out, literal=True)
                self._buf = self._buf[fence:]
                self._in_fence = True
                continue
            if not m:
                break
            self._emit(self._buf[:m.end()], out)
            self._buf = self._buf[m.end():]
        return out

    def flush(self) -> list[str]:
        out: list[str] = []
        if not self._in_fence:
            self._emit(self._buf, out)
        self._buf = ""
        if self._truncated:
            out.append(TRUNCATION_NOTICE)
        return out

    def _emit(self, text: str, out: list[str], literal: bool = False) -> None:
        if self._truncated:
            return
        text = text if literal else _clean_inline(text)
        if not text:
            return
        if self._emitted + len(text) > self._limit:
            self._truncated = True
            return
        self._emitted += len(text)
        out.append(text)
