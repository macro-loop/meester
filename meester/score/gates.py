"""Deterministic scoring: her preferences and verified history against each job.

No model, no API key, no running cost - and every judgement carries a reason
string a person can check ("Title matches 'Product Designer'", "Pay below your
floor"). If a reason can't be written in plain words, the rule doesn't belong
here; that keeps this layer auditable and keeps the trust that the later LLM
judge will have to earn rather than inherit.

Scores are computed at report time, not harvest time, so editing preferences
re-ranks everything on the next page load rather than waiting a harvest cycle.
"""

from __future__ import annotations

import re
from typing import Any

from ..models import normalize_company, normalize_title

MATCH_THRESHOLD = 30

_SENIORITY_TOKENS: list[tuple[str, str]] = [
    ("director", r"\b(director|vp|vice\s+president|head\s+of)\b"),
    ("manager", r"\b(manager|management)\b"),
    ("lead", r"\b(lead|principal)\b"),
    ("staff", r"\bstaff\b"),
    ("senior", r"\b(senior|sr\.?)\b"),
    ("junior", r"\b(junior|jr\.?|intern|graduate|entry[- ]level|associate)\b"),
]
_SENIORITY_ORDER = ["junior", "mid", "senior", "staff", "lead", "manager", "director"]

_AGENCY_RX = re.compile(
    r"\b(staffing|recruitment\s+agency|recruiting\s+agency|talent\s+(agency|solutions|partners)"
    r"|on\s+behalf\s+of\s+our\s+client|our\s+client\s+is\s+(seeking|looking))\b",
    re.I,
)

_MONEY_RX = re.compile(r"[$€£]?\s*(\d{1,3}(?:[,.]\d{3})+|\d+(?:\.\d+)?)\s*([kK])?")


def parse_salary_max(raw: str) -> int | None:
    """Best yearly figure in a posted range, or None when not comparable.

    Handles "$218K – $300K", "USD 100,000-150,000". Amounts under 20k are
    ambiguous (hourly? monthly?) and comparing them against a yearly floor
    would be confidently wrong, so they return None.
    """
    if not raw:
        return None
    best = 0
    for m in _MONEY_RX.finditer(raw):
        digits = m.group(1).replace(",", "")
        if digits.count(".") > 1:  # "100.000.000" style thousand separators
            digits = digits.replace(".", "")
        try:
            value = float(digits)
        except ValueError:
            continue
        if m.group(2):  # 218K
            value *= 1000
        best = max(best, int(value))
    return best if best >= 20_000 else None


def _title_seniority(title: str) -> str | None:
    low = title.lower()
    for band, pattern in _SENIORITY_TOKENS:
        if re.search(pattern, low):
            return band
    return None


def _norm_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def score_job(job: dict, prefs: dict, ledger: dict | None = None) -> dict[str, Any]:
    """Returns {score, match, dream, reasons, why_not}.

    reasons explain a match; why_not explains a rejection or down-rank. Both
    are for her eyes, so they name her own preference, not internals.
    """
    reasons: list[str] = []
    why_not: list[str] = []
    score = 0

    title = job.get("title") or ""
    company = job.get("company") or ""
    description = (job.get("description") or "")[:8000]
    norm_co = normalize_company(company)
    title_words = _norm_words(normalize_title(title))

    # --- hard exclusions --------------------------------------------------------
    for excluded in prefs.get("exclude_companies") or []:
        if normalize_company(excluded) and normalize_company(excluded) == norm_co:
            return {"score": -999, "match": False, "dream": False,
                    "reasons": [], "why_not": [f"You excluded {excluded}"]}

    for industry in prefs.get("exclude_industries") or []:
        word = industry.strip().lower()
        if word and (word in company.lower() or word in title.lower()):
            return {"score": -999, "match": False, "dream": False,
                    "reasons": [], "why_not": [f"Looks like {word} - you excluded that industry"]}
        if word and re.search(rf"\b{re.escape(word)}\b", description, re.I):
            score -= 20
            why_not.append(f"Mentions {word}, which you excluded")

    if prefs.get("exclude_agencies") and _AGENCY_RX.search(company + " " + description):
        return {"score": -999, "match": False, "dream": False,
                "reasons": [], "why_not": ["Reads like a staffing agency posting"]}

    # --- title and function -----------------------------------------------------
    matched_title = ""
    for wanted in prefs.get("titles") or []:
        wanted_words = _norm_words(normalize_title(wanted))
        if wanted_words and wanted_words <= title_words:
            matched_title = wanted
            break
    if matched_title:
        score += 40
        reasons.append(f"Title matches '{matched_title}'")
    else:
        for func in prefs.get("functions") or []:
            if func.strip() and _norm_words(func) <= title_words:
                score += 20
                reasons.append(f"In {func.strip()}, your field")
                break

    # --- seniority --------------------------------------------------------------
    want = (prefs.get("seniority") or "").strip().lower()
    have = _title_seniority(title)
    if want and have:
        gap = abs(_SENIORITY_ORDER.index(want) - _SENIORITY_ORDER.index(have)) \
            if want in _SENIORITY_ORDER and have in _SENIORITY_ORDER else 0
        if gap == 0:
            score += 10
            reasons.append(f"{have.capitalize()} level, as you wanted")
        elif gap >= 2:
            score -= 25
            why_not.append(f"Looks {have}-level; you're after {want}")

    # --- pay --------------------------------------------------------------------
    floor = prefs.get("salary_floor")
    posted_max = parse_salary_max(job.get("salary_raw") or "")
    if floor and posted_max:
        if posted_max >= floor:
            score += 15
            reasons.append("Pay meets your floor")
        else:
            score -= 40
            why_not.append(f"Top of range ~{posted_max:,} is under your {floor:,} floor")

    # --- her verified skills ----------------------------------------------------
    if ledger and ledger.get("verified"):
        hits = []
        desc_low = description.lower()
        for skill in (ledger.get("skills") or [])[:40]:
            s = skill.strip().lower()
            if len(s) > 2 and re.search(rf"\b{re.escape(s)}\b", desc_low):
                hits.append(skill.strip())
            if len(hits) == 3:
                break
        if hits:
            score += 5 * len(hits)
            reasons.append("Asks for " + ", ".join(hits) + " - on your CV")

    # --- what she's moving away from --------------------------------------------
    away = _norm_words(prefs.get("moving_away_from") or "")
    away_hits = [w for w in away if len(w) >= 5 and w in title_words]
    if away_hits:
        score -= 10
        why_not.append(f"Mentions {away_hits[0]}, which you're moving away from")

    # --- dream list --------------------------------------------------------------
    dream = any(
        normalize_company(d) == norm_co for d in prefs.get("dream_companies") or [] if d.strip()
    )
    if dream:
        score += 15
        reasons.append("On your dream-company list")

    return {
        "score": score,
        "match": score >= MATCH_THRESHOLD,
        "dream": dream,
        "reasons": reasons,
        "why_not": why_not,
    }


def has_usable_preferences(prefs: dict) -> bool:
    """Whether scoring can say anything meaningful. With a blank profile the
    For-you view is hidden entirely - an empty tab reads as 'nothing fits you',
    which would be a lie."""
    return bool(
        (prefs.get("titles") or [])
        or (prefs.get("functions") or [])
        or (prefs.get("dream_companies") or [])
    )
