"""Her profile: preferences schema, load/save, validation.

One schema, defined as data, drives everything - the form the UI renders, the
client-side hints, and the authoritative server-side validation. Adding a
preference means adding one entry here; no template edits.

The schema mirrors profile/preferences.example.yaml exactly, because that file
is the documented contract and some people will still edit YAML by hand.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

# type: text | number | bool | select | list | longtext
PREF_FIELDS: list[dict] = [
    # --- What she's looking for -------------------------------------------------
    {
        "key": "titles", "section": "What you're looking for", "type": "list",
        "label": "Job titles you'd accept",
        "help": "One per line. Include the boring variants - boards use wildly "
                "different names for the same job.",
        "placeholder": "Product Designer\nSenior Product Designer\nUX Designer",
    },
    {
        "key": "seniority", "section": "What you're looking for", "type": "select",
        "label": "Seniority",
        "options": ["", "junior", "mid", "senior", "staff", "lead", "manager", "director"],
        "help": "Leave blank for no preference.",
    },
    {
        "key": "functions", "section": "What you're looking for", "type": "list",
        "label": "Fields you're open to", "placeholder": "design\nuser research",
        "help": "Plain words, one per line.",
    },
    # --- Money ------------------------------------------------------------------
    {
        "key": "salary_floor", "section": "Money", "type": "number",
        "label": "Lowest yearly salary you'd seriously consider (USD)",
        "min": 0, "max": 2_000_000, "placeholder": "120000",
        "help": "Postings below this are pushed down. Postings that publish no "
                "salary are kept. Answer honestly - an inflated floor produces "
                "an empty list.",
    },
    # --- Where ------------------------------------------------------------------
    {
        "key": "work_authorization", "section": "Where", "type": "list",
        "label": "Countries where you can work without sponsorship",
        "placeholder": "US", "help": "Country codes or names, one per line.",
    },
    {
        "key": "needs_sponsorship", "section": "Where", "type": "bool",
        "label": "You would need visa sponsorship",
    },
    {
        "key": "timezone", "section": "Where", "type": "text",
        "label": "Your timezone", "placeholder": "America/New_York",
    },
    {
        "key": "max_timezone_offset_hours", "section": "Where", "type": "number",
        "label": "Furthest timezone difference you'd work across (hours)",
        "min": 0, "max": 12, "placeholder": "6",
    },
    # --- Hard limits ------------------------------------------------------------
    {
        "key": "exclude_companies", "section": "Hard limits", "type": "list",
        "label": "Companies never to show", "placeholder": "Meta",
    },
    {
        "key": "exclude_industries", "section": "Hard limits", "type": "list",
        "label": "Industries never to show", "placeholder": "gambling\ndefense\ntobacco",
    },
    {
        "key": "exclude_agencies", "section": "Hard limits", "type": "bool",
        "label": "Hide postings from staffing agencies and recruiters",
    },
    # --- Priorities -------------------------------------------------------------
    {
        "key": "dream_companies", "section": "Priorities", "type": "list",
        "label": "Companies you'd be genuinely excited by",
        "help": "These are pinned in your list and never auto-applied to.",
        "placeholder": "Figma\nLinear",
    },
    {
        "key": "moving_away_from", "section": "Priorities", "type": "longtext",
        "label": "What you're deliberately moving away from",
        "help": "Free text. Used to push these down rather than exclude them.",
        "placeholder": "Large agencies, heavy client-services work...",
    },
    {
        "key": "priorities", "section": "Priorities", "type": "list",
        "label": "What matters most, in order",
        "placeholder": "interesting product\nsenior scope and autonomy\ncompensation",
    },
    # --- Practicalities ---------------------------------------------------------
    {
        "key": "notice_period_weeks", "section": "Practicalities", "type": "number",
        "label": "Notice period (weeks)", "min": 0, "max": 52, "placeholder": "4",
    },
    {
        "key": "target_applications_per_week", "section": "Practicalities", "type": "number",
        "label": "Applications per week that feels right",
        "min": 1, "max": 100, "placeholder": "10",
        "help": "Quality beats volume - the realistic useful range is 5 to 25.",
    },
    # --- Application answers ------------------------------------------------------
    # Used only to fill application forms. The rule the applier lives by: a
    # question is answered from here by exact match or the application stops
    # and asks her. "Always ask me" is therefore the safe default everywhere.
    {
        "key": "app_first_name", "section": "Application answers", "type": "text",
        "label": "First name, as it should appear on applications",
    },
    {
        "key": "app_last_name", "section": "Application answers", "type": "text",
        "label": "Last name",
    },
    {
        "key": "app_email", "section": "Application answers", "type": "text",
        "label": "Email on applications", "placeholder": "you@example.com",
    },
    {
        "key": "app_phone", "section": "Application answers", "type": "text",
        "label": "Phone", "placeholder": "+1 555 010 1234",
    },
    {
        "key": "app_location", "section": "Application answers", "type": "text",
        "label": "Location as forms should see it", "placeholder": "Austin, TX, United States",
    },
    {
        "key": "app_linkedin", "section": "Application answers", "type": "text",
        "label": "LinkedIn URL", "placeholder": "https://linkedin.com/in/...",
    },
    {
        "key": "app_portfolio", "section": "Application answers", "type": "text",
        "label": "Portfolio / website URL",
    },
    {
        "key": "app_github", "section": "Application answers", "type": "text",
        "label": "GitHub URL (if relevant to your field)",
    },
    {
        "key": "auth_us", "section": "Application answers", "type": "select",
        "label": "Are you legally authorized to work in the United States?",
        "options": ["", "yes", "no"], "empty_label": "Always ask me",
        "help": "Left as 'Always ask me', every application with this question "
                "waits for you. Answer it here once and they don't.",
    },
    {
        "key": "eeo_gender", "section": "Application answers", "type": "select",
        "label": "Gender (voluntary EEO question on US forms)",
        "options": ["", "male", "female", "non-binary", "prefer not to say"],
        "empty_label": "Always ask me",
    },
    {
        "key": "eeo_race", "section": "Application answers", "type": "select",
        "label": "Race / ethnicity (voluntary EEO question)",
        "options": ["", "american indian or alaska native", "asian",
                    "black or african american", "hispanic or latino",
                    "native hawaiian or other pacific islander", "white",
                    "two or more races", "prefer not to say"],
        "empty_label": "Always ask me",
    },
    {
        "key": "eeo_veteran", "section": "Application answers", "type": "select",
        "label": "Veteran status (voluntary EEO question)",
        "options": ["", "i am not a protected veteran",
                    "i identify as one or more of the classes of protected veteran",
                    "prefer not to say"],
        "empty_label": "Always ask me",
    },
    {
        "key": "eeo_disability", "section": "Application answers", "type": "select",
        "label": "Disability (voluntary EEO question)",
        "options": ["", "no, i do not have a disability",
                    "yes, i have a disability", "prefer not to say"],
        "empty_label": "Always ask me",
    },
]

_BY_KEY = {f["key"]: f for f in PREF_FIELDS}

_MAX_LIST_ITEMS = 50
_MAX_ITEM_CHARS = 80
_MAX_TEXT_CHARS = 120
_MAX_LONGTEXT_CHARS = 2000

_PREFS_HEADER = """# Written by the Profile screen. Safe to edit by hand; it will be rewritten.
# The documented reference for every field is preferences.example.yaml.
"""


def default_preferences() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in PREF_FIELDS:
        if f["type"] == "list":
            out[f["key"]] = []
        elif f["type"] == "bool":
            out[f["key"]] = False
        else:
            out[f["key"]] = None
    return out


def _clean_value(field: dict, raw: Any) -> tuple[Any, str]:
    """Coerce one value to its schema type. Returns (value, error)."""
    kind = field["type"]

    if kind == "list":
        if raw is None:
            return [], ""
        if isinstance(raw, str):
            raw = [line for line in raw.splitlines()]
        if not isinstance(raw, list):
            return [], "expected a list"
        items = [str(x).strip()[:_MAX_ITEM_CHARS] for x in raw]
        items = [x for x in items if x]
        return items[:_MAX_LIST_ITEMS], ""

    if kind == "bool":
        return bool(raw), ""

    if kind == "number":
        if raw in (None, ""):
            return None, ""
        try:
            value = int(float(str(raw).replace(",", "").replace("$", "").strip()))
        except (ValueError, TypeError):
            return None, "must be a number, like " + str(field.get("placeholder", "10"))
        lo, hi = field.get("min"), field.get("max")
        if lo is not None and value < lo:
            return None, f"must be at least {lo}"
        if hi is not None and value > hi:
            return None, f"must be at most {hi}"
        return value, ""

    if kind == "select":
        value = str(raw or "").strip().lower()
        if value not in field["options"]:
            return None, "pick one of the listed options"
        return value or None, ""

    # text / longtext
    cap = _MAX_LONGTEXT_CHARS if kind == "longtext" else _MAX_TEXT_CHARS
    value = str(raw or "").strip()[:cap]
    return (value or None), ""


def validate_preferences(data: Any) -> tuple[dict[str, Any], dict[str, str]]:
    """Coerce arbitrary input to a clean preferences dict. Unknown keys drop."""
    clean = default_preferences()
    errors: dict[str, str] = {}
    if not isinstance(data, dict):
        return clean, {}
    for key, raw in data.items():
        field = _BY_KEY.get(key)
        if field is None:
            continue
        value, err = _clean_value(field, raw)
        if err:
            errors[key] = err
        else:
            clean[key] = value
    return clean, errors


def load_preferences(path: Path) -> dict[str, Any]:
    """Read preferences.yaml, tolerating absence and hand-mangling."""
    if not path.exists():
        return default_preferences()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        # A hand-broken file must not take the server or scorer down.
        return default_preferences()
    clean, _ = validate_preferences(raw)
    return clean


def save_preferences(path: Path, data: Any) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate then atomically write. On field errors, nothing is written."""
    clean, errors = validate_preferences(data)
    if errors:
        return clean, errors
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        _PREFS_HEADER + "\n" + yaml.safe_dump(clean, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    tmp.replace(path)
    return clean, {}


# --- facts ledger -----------------------------------------------------------------
# The human-verified record of her actual history. Later stages may rephrase
# what is in here but never invent beyond it; that contract is why validation
# is strict about shape and why save stamps verified: True - the only path to
# a saved ledger runs through her looking at it.

import json
from datetime import datetime, timezone

_L_STR = 120
_L_BULLET = 300
_L_SUMMARY = 1000


def _s(value: Any, cap: int = _L_STR) -> str:
    return str(value or "").strip()[:cap]


def _slist(value: Any, cap_items: int, cap_chars: int = _L_STR) -> list[str]:
    if isinstance(value, str):
        value = value.splitlines()
    if not isinstance(value, list):
        return []
    items = [_s(x, cap_chars) for x in value]
    return [x for x in items if x][:cap_items]


def validate_ledger(data: Any) -> dict[str, Any]:
    """Coerce arbitrary input into a well-shaped ledger. Never raises."""
    if not isinstance(data, dict):
        data = {}
    out = {
        "name": _s(data.get("name"), 80),
        "email": _s(data.get("email"), 120),
        "phone": _s(data.get("phone"), 40),
        "location": _s(data.get("location"), 120),
        "links": _slist(data.get("links"), 6, 200),
        "summary": _s(data.get("summary"), _L_SUMMARY),
        "employment": [],
        "education": [],
        "skills": _slist(data.get("skills"), 60, 60),
        "certifications": _slist(data.get("certifications"), 15, 120),
        "verified": bool(data.get("verified")),
        "saved_at": _s(data.get("saved_at"), 40),
    }
    for e in (data.get("employment") or [])[:30]:
        if not isinstance(e, dict):
            continue
        entry = {
            "employer": _s(e.get("employer"), 80),
            "title": _s(e.get("title"), 80),
            "start": _s(e.get("start"), 20),
            "end": _s(e.get("end"), 20),
            "bullets": _slist(e.get("bullets"), 20, _L_BULLET),
        }
        if entry["employer"] or entry["title"]:
            out["employment"].append(entry)
    for e in (data.get("education") or [])[:10]:
        if not isinstance(e, dict):
            continue
        entry = {
            "school": _s(e.get("school"), 100),
            "degree": _s(e.get("degree"), 100),
            "start": _s(e.get("start"), 20),
            "end": _s(e.get("end"), 20),
        }
        if entry["school"] or entry["degree"]:
            out["education"].append(entry)
    return out


def load_ledger(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return validate_ledger(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return None


def save_ledger(path: Path, data: Any) -> dict[str, Any]:
    """Validate, stamp as human-verified, atomically write."""
    clean = validate_ledger(data)
    clean["verified"] = True
    clean["saved_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return clean


# --- cover letter templates -------------------------------------------------------
# Named variations the tailoring stage will pick from and fill. Placeholders are
# the contract between what she writes now and what gets generated per job later.

KNOWN_PLACEHOLDERS = {"company", "role", "their_product", "why_them"}
_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_MAX_LETTERS = 12
_MAX_LETTER_CHARS = 3000

STARTER_LETTERS = [
    {
        "name": "Straightforward",
        "body": (
            "I'm applying for the {role} role at {company}.\n\n"
            "{why_them}\n\n"
            "My background fits what you're looking for, and I'd be glad to show "
            "how in a conversation. Thanks for reading.\n"
        ),
    },
    {
        "name": "Warmer",
        "body": (
            "Hello {company} team,\n\n"
            "I've been following {their_product} for a while, so seeing the "
            "{role} opening was an easy yes. {why_them}\n\n"
            "I'd love to talk.\n"
        ),
    },
]


def lint_placeholders(body: str) -> list[str]:
    """Unknown {placeholders} in a template - warned about, never blocked,
    because a stray {typo} reaching a real application is embarrassing but a
    blocked save that eats her writing is worse."""
    return sorted({m for m in _PLACEHOLDER.findall(body or "") if m not in KNOWN_PLACEHOLDERS})


def validate_letters(data: Any) -> tuple[list[dict], dict[str, str]]:
    raw = data.get("letters") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return [], {"letters": "expected a list of letters"}
    clean: list[dict] = []
    errors: dict[str, str] = {}
    seen_names: set[str] = set()
    for i, item in enumerate(raw[:_MAX_LETTERS]):
        if not isinstance(item, dict):
            continue
        name = _s(item.get("name"), 60) or f"Letter {i + 1}"
        body = str(item.get("body") or "")[:_MAX_LETTER_CHARS]
        if not body.strip():
            errors[str(i)] = "this letter is empty - write it or remove it"
            continue
        base, n = name, 2
        while name.lower() in seen_names:
            name = f"{base} ({n})"
            n += 1
        seen_names.add(name.lower())
        clean.append({"name": name, "body": body})
    return clean, errors


def load_letters(path: Path) -> list[dict]:
    """Seeded with two starters on first read, so she edits instead of facing
    a blank page."""
    if not path.exists():
        return [dict(x) for x in STARTER_LETTERS]
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return [dict(x) for x in STARTER_LETTERS]
    clean, _ = validate_letters(raw)
    return clean or [dict(x) for x in STARTER_LETTERS]


def save_letters(path: Path, data: Any) -> tuple[list[dict], dict[str, str]]:
    clean, errors = validate_letters(data)
    if errors:
        return clean, errors
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        "# Cover letter templates, edited from the Letters screen.\n"
        "# {company} {role} {their_product} {why_them} are filled per job later.\n\n"
        + yaml.safe_dump({"letters": clean}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    tmp.replace(path)
    return clean, {}


def schema_for_client() -> list[dict]:
    """What the form-rendering JS needs; excludes nothing today but keeps the
    server free to add private schema fields later."""
    return [
        {k: f[k] for k in ("key", "section", "type", "label", "help", "options",
                           "placeholder", "min", "max", "empty_label") if k in f}
        for f in PREF_FIELDS
    ]
