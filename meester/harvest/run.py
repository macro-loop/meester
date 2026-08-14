"""Harvest orchestration: fan out across every board, normalise, filter, dedupe."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from ..dedupe import dedupe
from ..models import Job
from ..remote import is_acceptable
from . import ashby, greenhouse, lever
from .base import BoardClient

log = logging.getLogger("meester.harvest")

FETCHERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
}


@dataclass
class HarvestReport:
    raw: int = 0
    after_remote_filter: int = 0
    after_age_filter: int = 0
    after_dedupe: int = 0
    boards_ok: int = 0
    boards_failed: list[tuple[str, str, str]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.boards_ok} boards ok, {len(self.boards_failed)} failed | "
            f"{self.raw} raw -> {self.after_remote_filter} remote -> "
            f"{self.after_age_filter} fresh -> {self.after_dedupe} unique"
        )


async def harvest(
    companies: dict[str, list[str]],
    settings: dict,
) -> tuple[list[Job], HarvestReport]:
    hcfg = settings.get("harvest", {})
    rcfg = settings.get("remote", {})
    report = HarvestReport()

    async with BoardClient(
        concurrency=hcfg.get("concurrency", 8),
        timeout=hcfg.get("timeout_seconds", 45),
        retries=hcfg.get("retries", 2),
        user_agent=hcfg.get("user_agent", "Meester/0.1"),
    ) as client:
        tasks = [
            (ats, token, FETCHERS[ats](client, token))
            for ats, tokens in companies.items()
            if ats in FETCHERS
            for token in tokens
        ]
        results = await asyncio.gather(*(t[2] for t in tasks), return_exceptions=True)

    jobs: list[Job] = []
    for (ats, token, _), result in zip(tasks, results):
        if isinstance(result, BaseException):
            report.boards_failed.append((ats, token, f"{type(result).__name__}: {result}"))
            continue
        board_jobs, err = result
        if err:
            report.boards_failed.append((ats, token, err))
            continue
        report.boards_ok += 1
        jobs.extend(board_jobs)

    report.raw = len(jobs)

    if rcfg.get("require_remote", True):
        accept = rcfg.get("accept_countries", ["ANY"])
        accept_hybrid = rcfg.get("accept_hybrid", False)
        jobs = [
            j
            for j in jobs
            if is_acceptable(j.workplace, set(j.remote_countries), accept, accept_hybrid)
        ]
    report.after_remote_filter = len(jobs)

    max_age = hcfg.get("max_age_days")
    if max_age:
        # Keep postings with no date. Ashby and Greenhouse always stamp one, but
        # a missing date is not evidence of staleness and dropping it would bias
        # the pipeline against whichever source is least generous with metadata.
        jobs = [j for j in jobs if (j.age_days() is None or j.age_days() <= max_age)]
    report.after_age_filter = len(jobs)

    jobs = dedupe(jobs)
    report.after_dedupe = len(jobs)

    jobs.sort(key=lambda j: (j.posted_at is None, j.posted_at), reverse=True)
    return jobs, report


async def verify_tokens(
    companies: dict[str, list[str]], settings: dict
) -> dict[str, dict[str, str]]:
    """Probe every configured board token. Returns {ats: {token: ''|error}}."""
    hcfg = settings.get("harvest", {})
    out: dict[str, dict[str, str]] = {ats: {} for ats in companies if ats in FETCHERS}

    async with BoardClient(
        concurrency=hcfg.get("concurrency", 8),
        timeout=hcfg.get("timeout_seconds", 45),
        retries=0,  # a verification pass should not retry; 404 is the answer
        user_agent=hcfg.get("user_agent", "Meester/0.1"),
    ) as client:
        tasks = [
            (ats, token, FETCHERS[ats](client, token))
            for ats, tokens in companies.items()
            if ats in FETCHERS
            for token in tokens
        ]
        results = await asyncio.gather(*(t[2] for t in tasks), return_exceptions=True)

    for (ats, token, _), result in zip(tasks, results):
        if isinstance(result, BaseException):
            out[ats][token] = f"{type(result).__name__}: {result}"
            continue
        board_jobs, err = result
        if err:
            out[ats][token] = err
        elif not board_jobs:
            out[ats][token] = "resolved but empty"
        else:
            out[ats][token] = ""
    return out
