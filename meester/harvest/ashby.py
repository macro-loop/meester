"""Ashby job board harvester.

Endpoint: https://api.ashbyhq.com/posting-api/job-board/{token}

Ashby gives the richest signal of the three, but only if you read
``secondaryLocations``. Real example from Ramp's board:

    location:           "New York, NY (HQ)"
    isRemote:           true
    workplaceType:      "Hybrid"
    secondaryLocations: ["Remote (Canada)", "Remote (US)", "Miami, FL"]

Reading the primary location alone classifies that as a New York office job and
throws away a genuine US-remote role. Reading ``workplaceType`` alone calls it
hybrid. Both signals plus the secondaries have to be merged.
"""

from __future__ import annotations

from ..models import Job
from ..remote import classify_location_text, combine, workplace_from_enum
from ..models import Workplace
from ..textutil import html_to_text
from .base import BoardClient, parse_iso

API = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"


async def fetch(client: BoardClient, token: str) -> tuple[list[Job], str]:
    res = await client.get_json(token, API.format(token=token))
    if not res.ok:
        return [], res.error
    payload = res.payload or {}
    jobs = payload.get("jobs") or []
    # `isListed` false means the posting is unpublished/internal. Applying to one
    # is at best noise and at worst reaches a role that was deliberately hidden.
    return [_parse(token, j) for j in jobs if j.get("isListed", True)], ""


def _secondary_location_strings(j: dict) -> list[str]:
    out: list[str] = []
    for sec in j.get("secondaryLocations") or []:
        if not isinstance(sec, dict):
            continue
        if sec.get("location"):
            out.append(str(sec["location"]))
        postal = ((sec.get("address") or {}).get("postalAddress") or {})
        country = postal.get("addressCountry")
        if country:
            out.append(str(country))
    return out


def _compensation_text(j: dict) -> str:
    comp = j.get("compensation") or {}
    summary = comp.get("compensationTierSummary") or comp.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    tiers = comp.get("compensationTiers") or []
    if tiers and isinstance(tiers[0], dict):
        return str(tiers[0].get("tierSummary") or "").strip()
    return ""


def _classify(j: dict, location_text: str) -> tuple[Workplace, set[str]]:
    """Merge Ashby's three location signals.

    ``isRemote`` is corroborating evidence, NOT authority. Measured on OpenAI's
    live board: 438 of 734 postings carry ``isRemote: true`` while also being
    ``workplaceType: "Hybrid"``, located "San Francisco", with no remote entry in
    ``secondaryLocations``. Those are office jobs. Treating the boolean as
    authoritative admitted 438 false positives from a single employer.

    So the ordering is:
      1. ``workplaceType == "Remote"`` - the employer's explicit declaration, trusted.
      2. Any location string (primary or secondary) that reads as remote - this is
         the Ramp case, primary "New York, NY (HQ)" with "Remote (US)" secondary.
      3. ``isRemote`` alone, but only when there is no location text to contradict it.
      4. Otherwise fall back to workplaceType / location text, boolean ignored.
    """
    declared = workplace_from_enum(j.get("workplaceType"))
    loc_mode, countries = classify_location_text(location_text)

    if declared == Workplace.REMOTE:
        return Workplace.REMOTE, countries
    if loc_mode == Workplace.REMOTE:
        return Workplace.REMOTE, countries
    if j.get("isRemote") and loc_mode == Workplace.UNKNOWN:
        return Workplace.REMOTE, countries
    return combine((declared, set()), (loc_mode, countries))


def _parse(token: str, j: dict) -> Job:
    primary = (j.get("location") or "").strip()
    secondaries = _secondary_location_strings(j)
    location_text = "; ".join([p for p in [primary, *secondaries] if p])

    workplace, countries = _classify(j, location_text)

    return Job(
        source="ashby",
        company=token,
        company_token=token,
        external_id=str(j.get("id") or ""),
        title=(j.get("title") or "").strip(),
        url=j.get("jobUrl") or "",
        apply_url=j.get("applyUrl") or j.get("jobUrl") or "",
        description=(j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")))[:20000],
        location_raw=primary,
        locations=[p for p in [primary, *secondaries] if p],
        workplace=workplace,
        remote_countries=sorted(countries),
        department=j.get("department") or "",
        team=j.get("team") or "",
        employment_type=j.get("employmentType") or "",
        posted_at=parse_iso(j.get("publishedAt")),
        salary_raw=_compensation_text(j),
    )
