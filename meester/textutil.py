"""Turning board HTML into text an LLM can read cheaply."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")
_ENTITY = re.compile(r"&(?:[a-zA-Z][a-zA-Z0-9]{1,31}|#\d{1,7}|#[xX][0-9a-fA-F]{1,6});")


def html_to_text(raw: str | None, max_chars: int = 20000) -> str:
    """Strip HTML to readable text.

    Greenhouse serves its ``content`` field **double-escaped** - the payload
    literally starts ``&lt;div class=&quot;content-intro&quot;&gt;``. Unescaping
    once yields HTML, not text, so this unescapes repeatedly until stable before
    parsing. Skipping that step feeds a wall of ``&lt;p&gt;`` to the scorer and
    silently degrades every fit score.
    """
    if not raw:
        return ""

    text = raw
    for _ in range(3):
        if not _ENTITY.search(text):
            break
        text = html.unescape(text)

    parser = _TextExtractor()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        # Malformed markup: fall back to a crude tag strip rather than losing the
        # posting entirely.
        parser.parts = [re.sub(r"<[^>]+>", " ", text)]

    out = "".join(parser.parts)
    out = _WS.sub(" ", out)
    out = "\n".join(line.strip() for line in out.split("\n"))
    out = _NL.sub("\n\n", out).strip()

    if len(out) > max_chars:
        out = out[:max_chars].rsplit(" ", 1)[0] + " ..."
    return out
