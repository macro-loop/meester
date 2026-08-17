"""Pulling text and a draft facts ledger out of an uploaded CV.

The extraction here is heuristic and will be mediocre on purpose. Its job is
not to be right; it is to give her something concrete to correct, because the
correcting is the point - the human-verified result becomes the facts ledger
that every later stage treats as the only source of truth about her history.
A wrong draft she fixes is safe. A wrong draft that skipped review is not.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"


def sniff_kind(data: bytes) -> str:
    """'pdf', 'docx' or ''. Trusts bytes, never the filename."""
    if data.startswith(PDF_MAGIC):
        return "pdf"
    if data.startswith(ZIP_MAGIC):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if "word/document.xml" in z.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            return ""
    return ""


def pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - one bad page must not lose the rest
            continue
    return "\n".join(pages)


_TAG = re.compile(rb"<[^>]+>")


def docx_to_text(data: bytes) -> str:
    """A .docx is a zip of XML; paragraphs end in </w:p>. Stdlib only."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml")
    xml = xml.replace(b"</w:p>", b"\n").replace(b"<w:tab/>", b" ")
    text = _TAG.sub(b"", xml).decode("utf-8", errors="replace")
    return "\n".join(line.strip() for line in text.splitlines())


def to_text(data: bytes) -> tuple[str, str]:
    """Returns (kind, text). Empty kind means unrecognised."""
    kind = sniff_kind(data)
    if kind == "pdf":
        return kind, pdf_to_text(data)
    if kind == "docx":
        return kind, docx_to_text(data)
    return "", ""


# --- heuristic ledger drafting ---------------------------------------------------

_SECTION_HEADS = {
    "employment": re.compile(
        r"^\s*(work\s+)?(experience|employment|history|professional\s+experience|career)\s*:?\s*$", re.I
    ),
    "education": re.compile(r"^\s*(education|academic|qualifications)\s*:?\s*$", re.I),
    "skills": re.compile(r"^\s*(skills|technologies|tools|competencies|expertise)\s*:?\s*$", re.I),
    "certifications": re.compile(r"^\s*(certifications?|licenses?|awards)\s*:?\s*$", re.I),
    "summary": re.compile(r"^\s*(summary|profile|about|objective)\s*:?\s*$", re.I),
}

# Non-capturing on purpose: a group inside _MONTH would shift the group numbers
# of the range pattern below, and .group(2) would silently become the month.
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_DATE_RANGE = re.compile(
    rf"((?:{_MONTH}\s+)?(?:19|20)\d\d|\d{{1,2}}/(?:19|20)\d\d)\s*[-–—to]+\s*"
    rf"((?:{_MONTH}\s+)?(?:19|20)\d\d|\d{{1,2}}/(?:19|20)\d\d|present|current|now)",
    re.I,
)
_BULLET = re.compile(r"^\s*[•●▪◦‣·*–-]\s+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_URL = re.compile(r"(?:https?://|www\.|linkedin\.com/|github\.com/)\S+", re.I)


def empty_ledger() -> dict[str, Any]:
    return {
        "name": "", "email": "", "phone": "", "location": "", "links": [],
        "summary": "", "employment": [], "education": [], "skills": [],
        "certifications": [], "verified": False,
    }


def _classify_line(line: str) -> str | None:
    if len(line) > 48:  # headers are short
        return None
    for section, rx in _SECTION_HEADS.items():
        if rx.match(line):
            return section
    return None


def _split_employment(lines: list[str]) -> list[dict]:
    """Entries are anchored on date-range lines - the one thing CVs of every
    layout reliably contain."""
    entries: list[dict] = []
    current: dict | None = None
    context: list[str] = []  # non-bullet lines seen since the previous entry

    for line in lines:
        if not line.strip():
            continue
        m = _DATE_RANGE.search(line)
        if m:
            if current:
                entries.append(current)
            remainder = _DATE_RANGE.sub("", line).strip(" \t,|-–—@")
            # Employer/title usually sit on the date line or just above it.
            nearby = [x for x in ([remainder] + context[-2:]) if x]
            employer, title = _employer_title(nearby)
            current = {
                "employer": employer,
                "title": title,
                "start": m.group(1).strip(),
                "end": m.group(2).strip(),
                "bullets": [],
            }
            context = []
        elif _BULLET.match(line):
            if current:
                current["bullets"].append(_BULLET.sub("", line).strip()[:300])
        else:
            # Deliberately never treated as a bullet: a plain line after one
            # entry is very often the NEXT entry's header ("Beta Industries -
            # Product Designer"), and swallowing it as a bullet both pollutes
            # this entry and leaves the next one nameless. Prose-style CVs lose
            # their paragraphs in the draft; she pastes those in while editing.
            context.append(line.strip())

    if current:
        entries.append(current)
    return entries[:30]


_SPLIT_DASH = re.compile(r"\s+[-–—|]\s+")


def _employer_title(nearby: list[str]) -> tuple[str, str]:
    """'Acme Corp - Senior Product Designer' on one line, or employer and title
    on adjacent lines - both layouts are everywhere."""
    if not nearby:
        return "", ""
    if len(nearby) == 1:
        parts = _SPLIT_DASH.split(nearby[0], maxsplit=1)
        if len(parts) == 2:
            return parts[0].strip()[:80], parts[1].strip()[:80]
        return nearby[0][:80], ""
    return nearby[-1][:80], nearby[0][:80]


def _split_education(lines: list[str]) -> list[dict]:
    out: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        m = _DATE_RANGE.search(line)
        years = re.findall(r"(?:19|20)\d\d", line)
        text = _DATE_RANGE.sub("", line).strip(" \t,|-–—")
        if not text:
            continue
        out.append({
            "school": text[:100],
            "degree": "",
            "start": m.group(1).strip() if m else (years[0] if years else ""),
            "end": m.group(2).strip() if m else (years[-1] if len(years) > 1 else ""),
        })
    # Pair up school/degree when they landed on alternating lines.
    return out[:10]


def draft_ledger(text: str) -> dict[str, Any]:
    ledger = empty_ledger()
    lines = [ln.rstrip() for ln in text.splitlines()]

    head = "\n".join(lines[:12])
    if m := _EMAIL.search(head):
        ledger["email"] = m.group(0)
    if m := _PHONE.search(head):
        ledger["phone"] = m.group(0).strip()
    ledger["links"] = list(dict.fromkeys(u.rstrip(".,)") for u in _URL.findall(head)))[:6]
    for ln in lines[:5]:
        candidate = ln.strip()
        if candidate and not _EMAIL.search(candidate) and not _URL.search(candidate) \
                and not _PHONE.search(candidate) and len(candidate.split()) <= 5:
            ledger["name"] = candidate[:80]
            break

    # Bucket lines by section.
    buckets: dict[str, list[str]] = {}
    section = "summary"
    for ln in lines:
        found = _classify_line(ln.strip())
        if found:
            section = found
            continue
        buckets.setdefault(section, []).append(ln)

    ledger["summary"] = " ".join(
        x.strip() for x in buckets.get("summary", [])[:8] if x.strip()
    )[:600]
    ledger["employment"] = _split_employment(buckets.get("employment", []))
    ledger["education"] = _split_education(buckets.get("education", []))

    skills: list[str] = []
    for ln in buckets.get("skills", []):
        skills.extend(s.strip() for s in re.split(r"[,•|;·]", ln) if s.strip())
    ledger["skills"] = [s[:60] for s in skills if 1 < len(s) <= 60][:60]

    ledger["certifications"] = [
        ln.strip()[:120] for ln in buckets.get("certifications", []) if ln.strip()
    ][:15]
    return ledger
