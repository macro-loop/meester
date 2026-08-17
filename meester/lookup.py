"""Finding a company's job board from what a person actually knows.

The raw watchlist needs two facts: which ATS a company uses, and its exact slug
in that ATS's URLs. Nobody knows either. People know the company's name, and they
can find its careers page.

So this accepts both:

  * a pasted board URL  - jobs.lever.co/brex, boards.greenhouse.io/stripe, ...
    which is exact, and the most reliable thing she can give us
  * a plain name        - "Applied Intuition", which is turned into candidate
    slugs and probed against all three boards

Probing is deliberately cheap: candidates are tried in order per ATS and stop at
the first hit, with the three boards checked concurrently. The usual cost of a
search is three requests, not eighteen.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

from .harvest.base import BoardClient

# Existence probes, chosen to be the smallest response each API offers.
# Greenhouse without content=true is a fraction of the size; Lever accepts a
# limit; Ashby has no such option and returns the whole board.
PROBE_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json&limit=1",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}",
}

_URL_PATTERNS = [
    ("greenhouse", re.compile(r"(?:job-)?boards(?:-api)?\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/(?:embed/)?([A-Za-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"(?:jobs|api)(?:\.eu)?\.lever\.co/([A-Za-z0-9_-]+)", re.I)),
    ("ashby", re.compile(r"(?:jobs|api)\.ashbyhq\.com/(?:posting-api/job-board/)?([A-Za-z0-9_-]+)", re.I)),
]

# Legal suffixes only. Descriptive words are deliberately NOT here: "Group",
# "Labs" and "Technologies" are usually part of the real slug - Grafana Labs is
# `grafanalabs`, Match Group is `matchgroup` - so stripping them would probe the
# wrong candidate first.
_SUFFIXES = {
    "inc", "llc", "ltd", "limited", "corp", "corporation",
    "gmbh", "bv", "nv", "plc", "ag", "the",
}


@dataclass
class Match:
    ats: str
    token: str

    def as_dict(self) -> dict:
        return {"ats": self.ats, "token": self.token}


def parse_board_url(text: str) -> Match | None:
    """Pull the ATS and slug out of a pasted job-board link."""
    text = (text or "").strip()
    if "." not in text:
        return None
    probe = text if "//" in text else f"https://{text}"
    try:
        host = (urlparse(probe).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None
    for ats, pattern in _URL_PATTERNS:
        m = pattern.search(text)
        if m:
            token = m.group(1).lower()
            # "boards.greenhouse.io/embed" and similar path noise are not slugs.
            if token in {"embed", "job_board", "posting-api", "v1", "v0", "www"}:
                continue
            return Match(ats, token)
    return None


def slug_candidates(name: str, limit: int = 6) -> list[str]:
    """Turn a display name into plausible board slugs, most likely first.

    "Applied Intuition" -> appliedintuition, applied-intuition, applied
    "Weights & Biases"  -> weightsandbiases, weights-and-biases, weights
    """
    if not name:
        return []
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("&", " and ").replace("+", " plus ")
    words = [w for w in re.split(r"[^a-z0-9]+", text) if w]
    if not words:
        return []

    core = [w for w in words if w not in _SUFFIXES] or words

    out: list[str] = []

    def push(value: str) -> None:
        if value and value not in out:
            out.append(value)

    push("".join(core))
    push("-".join(core))
    if len(core) > 1:
        push(core[0])
        push("".join(core[:2]))
        push("-".join(core[:2]))
    if core != words:
        push("".join(words))
    return out[:limit]


async def _probe_one(client: BoardClient, ats: str, token: str) -> bool:
    res = await client.get_json(token, PROBE_URLS[ats].format(token=token))
    if not res.ok:
        return False
    payload = res.payload
    if ats == "lever":
        return isinstance(payload, list)
    if isinstance(payload, dict):
        # A board that exists but has published nothing is indistinguishable from
        # a wrong slug for our purposes, so require at least one posting.
        return bool(payload.get("jobs"))
    return False


async def _first_hit(client: BoardClient, ats: str, candidates: list[str]) -> Match | None:
    for token in candidates:
        try:
            if await _probe_one(client, ats, token):
                return Match(ats, token)
        except Exception:  # noqa: BLE001 - one dead board must not end the search
            continue
    return None


async def find_boards(
    query: str, user_agent: str = "Meester/0.1", timeout: float = 25.0
) -> tuple[list[Match], list[str]]:
    """Resolve a name or URL to live boards. Returns (matches, candidates tried)."""
    query = (query or "").strip()
    if not query:
        return [], []

    exact = parse_board_url(query)
    async with BoardClient(concurrency=6, timeout=timeout, retries=0, user_agent=user_agent) as client:
        if exact:
            # A pasted link is a statement of fact; still confirm it is live so a
            # dead or mistyped link fails here rather than silently later.
            return ([exact] if await _probe_one(client, exact.ats, exact.token) else []), [exact.token]

        candidates = slug_candidates(query)
        if not candidates:
            return [], []
        found = await asyncio.gather(
            *(_first_hit(client, ats, candidates) for ats in PROBE_URLS),
            return_exceptions=True,
        )

    matches = [m for m in found if isinstance(m, Match)]
    return matches, candidates
