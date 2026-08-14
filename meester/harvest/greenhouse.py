"""Greenhouse job board harvester.

Endpoint: https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

Greenhouse is the weakest of the three for our purposes and needs the most care:

  * ``content=true`` is required or postings come back with no description at all.
  * ``content`` is **double HTML-escaped** (see textutil.html_to_text).
  * There is no remote flag. ``location.name`` is free text, often multi-valued
    and semicolon-joined: "Remote, Canada; Remote, United States".
  * ``metadata`` is per-employer custom and cannot be used as a remote signal.

It is still the highest-value source, because it hosts the largest share of
remote-friendly tech employers.
"""

from __future__ import annotations

from ..models import Job, Workplace
from ..remote import classify_location_text
from ..textutil import html_to_text
from .base import BoardClient, parse_iso

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


async def fetch(client: BoardClient, token: str) -> tuple[list[Job], str]:
    res = await client.get_json(token, API.format(token=token))
    if not res.ok:
        return [], res.error
    payload = res.payload or {}
    raw_jobs = payload.get("jobs") or []
    return [_parse(token, j) for j in raw_jobs], ""


def _parse(token: str, j: dict) -> Job:
    location_raw = ((j.get("location") or {}).get("name") or "").strip()

    # `offices` sometimes carries geography the location string omits.
    office_names = [
        (o or {}).get("name", "") for o in (j.get("offices") or []) if isinstance(o, dict)
    ]
    combined = "; ".join([p for p in [location_raw, *office_names] if p])

    workplace, countries = classify_location_text(combined)

    departments = [
        (d or {}).get("name", "") for d in (j.get("departments") or []) if isinstance(d, dict)
    ]

    return Job(
        source="greenhouse",
        company=j.get("company_name") or token,
        company_token=token,
        external_id=str(j.get("id") or j.get("internal_job_id") or ""),
        title=(j.get("title") or "").strip(),
        url=j.get("absolute_url") or "",
        apply_url=j.get("absolute_url") or "",
        description=html_to_text(j.get("content")),
        location_raw=location_raw,
        locations=[p.strip() for p in location_raw.split(";") if p.strip()],
        workplace=workplace,
        remote_countries=sorted(countries),
        department=departments[0] if departments else "",
        posted_at=parse_iso(j.get("first_published")),
        updated_at=parse_iso(j.get("updated_at")),
    )
