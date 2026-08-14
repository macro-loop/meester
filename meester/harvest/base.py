"""Shared HTTP plumbing for the board harvesters."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

log = logging.getLogger("meester.harvest")


@dataclass
class FetchResult:
    token: str
    ok: bool
    payload: Any = None
    status: int | None = None
    error: str = ""


class BoardClient:
    """Polite, bounded-concurrency fetcher.

    These are free unauthenticated endpoints that the whole design depends on.
    Hammering them is both rude and the fastest way to get the IP blocked, so
    concurrency is capped and failures back off rather than retry tightly.
    """

    def __init__(
        self,
        concurrency: int = 8,
        timeout: float = 45.0,
        retries: int = 2,
        user_agent: str = "Meester/0.1",
    ) -> None:
        self.retries = retries
        self._sem = asyncio.Semaphore(concurrency)
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )

    async def __aenter__(self) -> "BoardClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def get_json(self, token: str, url: str) -> FetchResult:
        last = ""
        status: int | None = None
        for attempt in range(self.retries + 1):
            try:
                async with self._sem:
                    resp = await self._client.get(url)
                status = resp.status_code
                if resp.status_code == 404:
                    # A dead board token is a config problem, not a transient
                    # failure. Retrying it wastes time on every single run.
                    return FetchResult(token, False, status=404, error="board not found")
                if resp.status_code == 429:
                    await asyncio.sleep(2 ** attempt * 3)
                    last = "rate limited"
                    continue
                resp.raise_for_status()
                return FetchResult(token, True, payload=resp.json(), status=status)
            except Exception as exc:  # noqa: BLE001 - one bad board must not kill the run
                last = f"{type(exc).__name__}: {exc}"
                if attempt < self.retries:
                    await asyncio.sleep(2 ** attempt)
        return FetchResult(token, False, status=status, error=last)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def parse_epoch_ms(value: int | float | None) -> datetime | None:
    """Lever stamps ``createdAt`` as epoch milliseconds."""
    if not value:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    except (ValueError, TypeError, OSError, OverflowError):
        return None
