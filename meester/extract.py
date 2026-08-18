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
import unicodedata
import zipfile
from typing import Any

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"


def _normalize(text: str) -> str:
    """Fold compatibility ligatures (ﬁ->fi, ﬂ->fl) without stripping accents.

    NFKC is deliberate over NFKD: it repairs the ligature glyphs some PDF fonts
    embed while leaving accented names (é, ü) composed rather than shredding
    them into base + combining marks.
    """
    return unicodedata.normalize("NFKC", text or "")


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
    """Prefer pymupdf, fall back to pypdf.

    pymupdf resolves embedded-font character maps that pypdf gets wrong - real
    resumes routinely came through pypdf as "BalBmore"/"SeaQle" (Baltimore/
    Seattle) because a broken ToUnicode map mangled ligature glyphs, corruption
    that no post-processing can reverse. pymupdf reads them correctly.

    (pymupdf is AGPL; fine here - the repo is public and this is a personal
    tool. pypdf remains the permissive fallback if pymupdf is unavailable.)
    """
    try:
        import pymupdf

        doc = pymupdf.open(stream=data, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            return _normalize(text)
    except Exception:  # noqa: BLE001 - not installed, or a file it dislikes
        pass

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - one bad page must not lose the rest
            continue
    return _normalize("\n".join(pages))


_TAG = re.compile(rb"<[^>]+>")


def docx_to_text(data: bytes) -> str:
    """A .docx is a zip of XML; paragraphs end in </w:p>. Stdlib only."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml")
    xml = xml.replace(b"</w:p>", b"\n").replace(b"<w:tab/>", b" ")
    text = _TAG.sub(b"", xml).decode("utf-8", errors="replace")
    return _normalize("\n".join(line.strip() for line in text.splitlines()))


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
# \s* not \s+ between month and year: real resumes write "Sep2024" and
# "May2023" with no space, and requiring one dropped the month, split the date,
# and leaked the stray month into the title.
_DATE_RANGE = re.compile(
    rf"((?:{_MONTH}\s*)?(?:19|20)\d\d|\d{{1,2}}/(?:19|20)\d\d)\s*[-–—]+\s*"
    rf"((?:{_MONTH}\s*)?(?:19|20)\d\d|\d{{1,2}}/(?:19|20)\d\d|present|current|now)",
    re.I,
)
_BULLET = re.compile(r"^\s*[•●▪◦‣·*–-]\s+")
_BULLET_ALONE = re.compile(r"^\s*[•●▪◦‣]\s*$")  # marker on its own line
# Unicode bullets may hug their text (•text); dash/asterisk bullets need a
# following space so a hyphenated word or a date fragment isn't taken as one.
_LEADS_BULLET = re.compile(r"^\s*(?:[•●▪◦‣·]\s*|[*\-–—]\s+)")


def _merge_lone_bullets(lines: list[str]) -> list[str]:
    """pymupdf often emits the bullet glyph and its text on separate lines.
    Rejoin '•' + next line so the bullet detector below sees '• text'."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        if _BULLET_ALONE.match(lines[i]) and i + 1 < len(lines) and lines[i + 1].strip():
            out.append("• " + lines[i + 1].strip())
            i += 2
        else:
            out.append(lines[i])
            i += 1
    return out
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
    """Entries anchored on date-range lines - the one thing CVs of every layout
    reliably contain. Around each date, the title and employer sit on the same
    line, the line above, or the line below, depending on the template; this
    checks all three. It will still misfile some - that is why she reviews and
    corrects the draft."""
    rows = _merge_lone_bullets([ln.strip() for ln in lines if ln.strip()])
    date_idx = [i for i, ln in enumerate(rows) if _DATE_RANGE.search(ln)]
    entries: list[dict] = []

    for n, i in enumerate(date_idx):
        m = _DATE_RANGE.search(rows[i])
        remainder = _DATE_RANGE.sub("", rows[i]).strip(" \t,|-–—@")

        above = rows[i - 1] if i > 0 and not _LEADS_BULLET.match(rows[i - 1]) else ""
        below = rows[i + 1] if i + 1 < len(rows) and not _LEADS_BULLET.match(rows[i + 1]) \
            and not _DATE_RANGE.search(rows[i + 1]) else ""

        # Candidates for the entry's title + employer, in likely order.
        if remainder:
            title, employer = _employer_title([remainder])
            if not employer:
                employer = below or above
        else:
            # Vertical layout: title on the line above, employer on the line
            # below (the common modern resume shape).
            title, employer = above, below

        # Bullets: from just after the header block until the next date anchor.
        start_body = i + 1 + (1 if below and below == rows[i + 1] else 0) \
            if i + 1 < len(rows) else i + 1
        end_body = date_idx[n + 1] if n + 1 < len(date_idx) else len(rows)
        bullets = [
            _LEADS_BULLET.sub("", rows[j]).strip()[:300]
            for j in range(start_body, end_body)
            if _LEADS_BULLET.match(rows[j])
        ]

        if title or employer:
            entries.append({
                "employer": (employer or "")[:80],
                "title": (title or "")[:80],
                "start": m.group(1).strip(),
                "end": m.group(2).strip(),
                "bullets": bullets[:20],
            })
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


# --- optional LLM structuring -----------------------------------------------------
# When a key is present this parses the (already clean) text into structure far
# more reliably than the regex heuristics, especially employer/title placement.
# It is STRUCTURING, not writing: instructed to use only what is present and to
# leave blank anything the text does not contain. She still reviews the result -
# the ledger is only ever trusted once she has verified it.

_LLM_SYSTEM = (
    "You convert already-extracted resume text into structured JSON. Use ONLY "
    "information present in the text. Never invent employers, titles, dates, "
    "degrees, or metrics. If a field is not in the text, leave it empty. Keep "
    "bullet wording close to the original."
)


def llm_structure(text: str, llm) -> dict[str, Any] | None:
    """Return a ledger dict via the LLM, or None to fall back to heuristics."""
    if llm is None:
        return None
    try:
        out = llm.call_json(
            "Convert this resume text to JSON with keys: name, email, phone, "
            "location, links (list), summary, employment (list of {employer, "
            "title, start, end, bullets:list}), education (list of {school, "
            "degree, start, end}), skills (list), certifications (list). Use "
            "only what appears in the text.\n\n" + text[:12000],
            system=_LLM_SYSTEM, max_tokens=2000,
        )
    except Exception:  # noqa: BLE001 - any failure: fall back to heuristics
        return None
    if not isinstance(out, dict) or not out.get("employment"):
        return None
    out.setdefault("verified", False)
    return out
