"""Splitting a book into passages: short enough to quote, and carrying their source with them."""
import re

MAX_CHARS = 1_200
_PARAGRAPH = re.compile(r"\r?\n[ \t\n\x0b\f\r]*\r?\n")
_SPACE = re.compile(r"[ \t\n\x0b\f\r]+")


def split(text: str) -> list[str]:
    """Paragraphs, with any paragraph longer than MAX_CHARS split at word boundaries."""
    out = []
    for para in _PARAGRAPH.split(text):
        para = _SPACE.sub(" ", para).strip()
        chunk = ""
        for word in para.split(" "):
            if chunk and len(chunk) + len(word) + 1 > MAX_CHARS:
                out.append(chunk)
                chunk = ""
            chunk = f"{chunk} {word}" if chunk else word
        if chunk:
            out.append(chunk)
    return out


def title(text: str, fallback: str) -> str:
    first = text.split("\n", 1)[0].strip()
    return first.strip("[]").strip() or fallback
