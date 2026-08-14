"""Unified job posting model shared across every source."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Workplace(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


# Suffixes stripped when normalising a company name for dedupe. The same employer
# shows up as "Stripe", "Stripe, Inc." and "Stripe Inc" across three sources.
_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|gmbh|bv|nv|plc|sa|ag|co|company|holdings|group|labs?|technologies|technology|software)\b",
    re.I,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Requisition ids, trailing location parens and seniority noise that make the same
# role look like three different roles.
# NOTE: the '#' characters below MUST stay escaped. Under re.VERBOSE an unescaped
# '#' opens a comment, which silently turned the last alternative into a bare
# '\s*' - it then matched the space in every title, so "Backend Engineer"
# normalised to "backendengineer" and unrelated roles began merging in dedupe.
_TITLE_NOISE = re.compile(
    r"""
    \s*[\(\[][^)\]]*[\)\]]\s*      # (Remote), [US], (R-12345)
    | \s*[-–—,|]\s*(remote|hybrid|onsite|on-site|us|usa|united\s+states|emea|apac|amer(icas)?)\b.*$
    | \s*\b(req|requisition)\s*\#?\s*\d+\b
    | \s*\#\s*\d+\s*$
    """,
    re.I | re.X,
)


def normalize_company(name: str) -> str:
    """'Stripe, Inc.' and 'stripe' collapse to the same key."""
    if not name:
        return ""
    s = name.lower()
    s = _COMPANY_SUFFIXES.sub(" ", s)
    s = _NON_ALNUM.sub("", s)
    return s


def normalize_title(title: str) -> str:
    """Strip req ids and location decorations so cross-source titles match."""
    if not title:
        return ""
    s = title.strip()
    prev = None
    # Repeat: titles routinely carry two decorations, e.g. "Engineer (Remote) [R-9]".
    while prev != s:
        prev = s
        s = _TITLE_NOISE.sub("", s).strip()
    s = s.lower()
    s = _NON_ALNUM.sub(" ", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


@dataclass
class Job:
    # Provenance
    source: str  # "greenhouse" | "lever" | "ashby" | "remoteok" | ...
    company: str
    company_token: str
    external_id: str

    # Content
    title: str
    url: str
    apply_url: str = ""
    description: str = ""

    # Placement
    location_raw: str = ""
    locations: list[str] = field(default_factory=list)
    workplace: Workplace = Workplace.UNKNOWN
    remote_countries: list[str] = field(default_factory=list)

    # Classification helpers
    department: str = ""
    team: str = ""
    employment_type: str = ""

    # Timing
    posted_at: datetime | None = None
    updated_at: datetime | None = None

    # Compensation, when the board exposes it
    salary_raw: str = ""

    # Populated by the dedupe pass
    fingerprint: str = ""

    def compute_fingerprint(self) -> str:
        """Identity for dedupe: same employer + same role + same working mode.

        Deliberately excludes the URL and external id, because the entire point is
        to collapse the same role arriving from Greenhouse, an aggregator and a
        remote feed into one row.
        """
        key = "|".join(
            [
                normalize_company(self.company),
                normalize_title(self.title),
                self.workplace.value,
            ]
        )
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    def age_days(self, now: datetime | None = None) -> float | None:
        stamp = self.posted_at or self.updated_at
        if stamp is None:
            return None
        now = now or datetime.now(timezone.utc)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return (now - stamp).total_seconds() / 86400.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["workplace"] = self.workplace.value
        for k in ("posted_at", "updated_at"):
            d[k] = self.__dict__[k].isoformat() if self.__dict__[k] else None
        return d
