"""Her verdicts on individual jobs: applied, starred, hidden.

Small on purpose, and load-bearing later: `applied` becomes the guard against
ever double-applying to a fingerprint, and the trigger for warm outreach;
`starred` marks outreach-priority roles; `hidden` is her way of saying "stop
showing me this" and must be honoured everywhere except its own chip.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STATES = ("applied", "starred", "hidden")


def load_statuses(path: Path) -> dict[str, dict]:
    """fingerprint -> {"state": ..., "at": iso}. Tolerates absence and damage:
    losing her stars is annoying, crashing the report over them is worse."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for fp, entry in raw.items():
        if isinstance(entry, dict) and entry.get("state") in STATES:
            out[str(fp)] = {"state": entry["state"], "at": str(entry.get("at") or "")}
    return out


def set_status(path: Path, fingerprint: str, state: str | None) -> dict[str, dict]:
    """Set or clear (state=None) one job's status. Atomic; returns the new map."""
    fingerprint = str(fingerprint).strip()
    if not fingerprint or len(fingerprint) > 64:
        raise ValueError("bad fingerprint")
    if state is not None and state not in STATES:
        raise ValueError(f"state must be one of {', '.join(STATES)} or null")

    statuses = load_statuses(path)
    if state is None:
        statuses.pop(fingerprint, None)
    else:
        statuses[fingerprint] = {
            "state": state,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(statuses, indent=0, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return statuses
