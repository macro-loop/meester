"""Lever job board harvester.

Endpoint: https://api.lever.co/v0/postings/{token}?mode=json

Returns a bare JSON list (not an object). Useful fields:
  * ``workplaceType``  - "remote" | "hybrid" | "onsite"
  * ``categories``     - {commitment, department, team, location, allLocations}
  * ``createdAt``      - epoch milliseconds
  * ``salaryRange`` / ``salaryDescriptionPlain`` - compensation, when published
  * ``applyUrl`` is distinct from ``hostedUrl`` and is the one to automate against.
"""

from __future__ import annotations

from ..models import Job
from ..remote import classify_location_text, combine, workplace_from_enum
from ..textutil import html_to_text
from .base import BoardClient, parse_epoch_ms

API = "https://api.lever.co/v0/postings/{token}?mode=json"


async def fetch(client: BoardClient, token: str) -> tuple[list[Job], str]:
    res = await client.get_json(token, API.format(token=token))
    if not res.ok:
        return [], res.error
    payload = res.payload
    if not isinstance(payload, list):
        return [], "unexpected payload shape"
    return [_parse(token, j) for j in payload], ""


def _salary_text(j: dict) -> str:
    desc = (j.get("salaryDescriptionPlain") or j.get("salaryDescription") or "").strip()
    if desc:
        return desc
    rng = j.get("salaryRange") or {}
    if rng.get("min") and rng.get("max"):
        cur = rng.get("currency") or ""
        interval = rng.get("interval") or ""
        return f"{cur} {rng['min']}-{rng['max']} {interval}".strip()
    return ""


def _parse(token: str, j: dict) -> Job:
    cats = j.get("categories") or {}
    location_raw = (cats.get("location") or "").strip()
    all_locations = [str(x) for x in (cats.get("allLocations") or []) if x]
    location_text = "; ".join([p for p in [location_raw, *all_locations] if p])

    workplace, countries = combine(
        (workplace_from_enum(j.get("workplaceType")), set()),
        classify_location_text(location_text),
    )
    if j.get("country"):
        countries |= classify_location_text(str(j["country"]))[1]

    # descriptionPlain is the body only; `text` is the title. Prefer the plain
    # variants Lever already provides over re-parsing its HTML.
    body = j.get("descriptionPlain") or html_to_text(j.get("description"))
    extra = j.get("additionalPlain") or html_to_text(j.get("additional"))
    description = "\n\n".join([p for p in [body, extra] if p]).strip()

    return Job(
        source="lever",
        company=token,
        company_token=token,
        external_id=str(j.get("id") or ""),
        title=(j.get("text") or "").strip(),
        url=j.get("hostedUrl") or "",
        apply_url=j.get("applyUrl") or j.get("hostedUrl") or "",
        description=description[:20000],
        location_raw=location_raw,
        locations=all_locations or ([location_raw] if location_raw else []),
        workplace=workplace,
        remote_countries=sorted(countries),
        department=cats.get("department") or "",
        team=cats.get("team") or "",
        employment_type=cats.get("commitment") or "",
        posted_at=parse_epoch_ms(j.get("createdAt")),
        salary_raw=_salary_text(j),
    )
