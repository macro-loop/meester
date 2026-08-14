"""Collapsing the same role arriving from several sources."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Job, normalize_company, normalize_title

# Source preference when two records describe the same role. The company's own
# board is authoritative: it has the real apply URL and the freshest state.
_SOURCE_RANK = {
    "greenhouse": 0,
    "ashby": 0,
    "lever": 0,
    "remoteok": 1,
    "remotive": 1,
    "himalayas": 1,
    "weworkremotely": 1,
    "hn": 2,
}

_NEAR_DUP_RATIO = 0.92
_WORD = re.compile(r"[a-z0-9]+")


def _richness(job: Job) -> tuple:
    """Prefer the record we can actually act on."""
    return (
        -_SOURCE_RANK.get(job.source, 5),
        1 if job.apply_url else 0,
        len(job.description or ""),
        1 if job.salary_raw else 0,
        1 if job.posted_at else 0,
    )


def _fill_gaps(primary: Job, other: Job) -> Job:
    """Fill empty scalar fields in the winner from the loser.

    Deliberately does NOT touch locations or countries - see _merge_identical.
    """
    if not primary.description and other.description:
        primary.description = other.description
    if not primary.salary_raw and other.salary_raw:
        primary.salary_raw = other.salary_raw
    if not primary.posted_at and other.posted_at:
        primary.posted_at = other.posted_at
    if not primary.apply_url and other.apply_url:
        primary.apply_url = other.apply_url
    return primary


def _merge_identical(primary: Job, other: Job) -> Job:
    """Merge two records of the *same* role seen through different sources.

    Only here is unioning geography correct: it is one posting, and each source
    saw a different slice of its locations.
    """
    _fill_gaps(primary, other)
    for loc in other.locations:
        if loc not in primary.locations:
            primary.locations.append(loc)
    primary.remote_countries = sorted(
        set(primary.remote_countries) | set(other.remote_countries)
    )
    return primary


def _title_similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    # Cheap guard before the O(n*m) comparison.
    if abs(len(a) - len(b)) > max(len(a), len(b)) * 0.4:
        return False
    return SequenceMatcher(None, a, b).ratio() >= _NEAR_DUP_RATIO


def dedupe(jobs: list[Job]) -> list[Job]:
    """Two passes: exact fingerprint, then fuzzy title within the same employer.

    The fuzzy pass exists because "Senior Software Engineer, Backend" and
    "Senior Software Engineer - Backend" survive normalisation as distinct keys
    but are obviously one role. It is scoped to a single employer so the
    quadratic comparison stays cheap.
    """
    by_fingerprint: dict[str, Job] = {}
    for job in jobs:
        fp = job.compute_fingerprint()
        job.fingerprint = fp
        existing = by_fingerprint.get(fp)
        if existing is None:
            by_fingerprint[fp] = job
            continue
        winner, loser = (
            (job, existing) if _richness(job) > _richness(existing) else (existing, job)
        )
        # Same fingerprint from *different* sources means one role seen twice, so
        # each source's slice of the geography is worth keeping. Same fingerprint
        # from the *same* board usually means the employer posted one title once
        # per city; unioning those yields a country list that describes no actual
        # posting (a Lisbon role advertised as open in five other countries).
        by_fingerprint[fp] = (
            _fill_gaps(winner, loser)
            if winner.source == loser.source
            else _merge_identical(winner, loser)
        )

    # Fuzzy pass, grouped by employer.
    groups: dict[str, list[Job]] = {}
    for job in by_fingerprint.values():
        groups.setdefault(normalize_company(job.company), []).append(job)

    out: list[Job] = []
    for group in groups.values():
        kept: list[Job] = []
        for job in sorted(group, key=_richness, reverse=True):
            norm = normalize_title(job.title)
            match = next(
                (
                    k
                    for k in kept
                    if k.workplace == job.workplace
                    and _title_similar(normalize_title(k.title), norm)
                ),
                None,
            )
            if match is not None:
                # Fuzzy match only means "near-identical title at the same
                # employer" - it may well be two separate postings in two cities.
                # Unioning their geography invents a location set that matches
                # neither, so only empty scalar fields are filled here.
                _fill_gaps(match, job)
            else:
                kept.append(job)
        out.extend(kept)
    return out
