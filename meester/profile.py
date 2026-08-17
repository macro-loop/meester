"""Her profile: preferences schema, load/save, validation.

One schema, defined as data, drives everything - the form the UI renders, the
client-side hints, and the authoritative server-side validation. Adding a
preference means adding one entry here; no template edits.

The schema mirrors profile/preferences.example.yaml exactly, because that file
is the documented contract and some people will still edit YAML by hand.
"""

from __future__ import annotations

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


def schema_for_client() -> list[dict]:
    """What the form-rendering JS needs; excludes nothing today but keeps the
    server free to add private schema fields later."""
    return [
        {k: f[k] for k in ("key", "section", "type", "label", "help", "options", "placeholder", "min", "max") if k in f}
        for f in PREF_FIELDS
    ]
