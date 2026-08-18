"""The approve queue: everything that wants to act in her name waits here.

Applications and (later) outreach notes are both queue items; nothing reaches
the outside world except by an item moving through `approved`, and in the
launch configuration every single approval is her tap. States:

    proposed -> approved -> submitting -> submitted | failed | needs_human
    proposed | approved -> skipped | expired

Expiry is 48h for anything not yet acted on: postings go stale, and an
application fired at a three-week-old approval looks strange (master plan).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

STATES = (
    "proposed", "approved", "submitting", "submitted",
    "failed", "needs_human", "skipped", "expired",
)
# Which transitions a caller may request. `submitting` is engine-internal.
_ALLOWED: dict[str, set[str]] = {
    "proposed": {"approved", "skipped", "expired", "needs_human"},
    "approved": {"submitting", "skipped", "expired", "needs_human"},
    "submitting": {"submitted", "failed", "needs_human"},
    "needs_human": {"approved", "skipped", "submitted"},  # 'submitted' = she did it by hand
    "failed": {"approved", "skipped"},  # retry after a fix
}
EXPIRY_HOURS = 48


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Queue:
    def __init__(self, path: Path):
        self.path = path
        self.items: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {k: v for k, v in raw.items() if isinstance(v, dict)}
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.items, ensure_ascii=False, indent=0), encoding="utf-8"
        )
        tmp.replace(self.path)

    # --- lifecycle --------------------------------------------------------------

    def propose(self, item_id: str, kind: str, payload: dict) -> dict | None:
        """Add a proposed item. Refuses silently if the id ever existed - a
        skipped or expired application must not resurrect itself every harvest."""
        if item_id in self.items:
            return None
        item = {
            "id": item_id,
            "kind": kind,  # "application" | "outreach"
            "state": "proposed",
            "created": _now(),
            "updated": _now(),
            **payload,
        }
        self.items[item_id] = item
        self._save()
        return item

    def transition(self, item_id: str, new_state: str, **extra: Any) -> dict:
        item = self.items.get(item_id)
        if item is None:
            raise KeyError(f"no queue item {item_id}")
        if new_state not in STATES:
            raise ValueError(f"unknown state {new_state}")
        current = item.get("state", "")
        if new_state not in _ALLOWED.get(current, set()):
            raise ValueError(f"cannot go {current} -> {new_state}")
        item["state"] = new_state
        item["updated"] = _now()
        for key, value in extra.items():
            if value is not None:
                item[key] = value
        self._save()
        return item

    def update_fields(self, item_id: str, **fields: Any) -> dict:
        """Edit item content (her letter tweak, a note) without a state change.
        Only allowed before anything has been sent."""
        item = self.items.get(item_id)
        if item is None:
            raise KeyError(f"no queue item {item_id}")
        if item.get("state") not in ("proposed", "approved", "needs_human"):
            raise ValueError("this item is past editing")
        for key, value in fields.items():
            if key in ("letter_body", "note", "why_them", "note_body") and value is not None:
                item[key] = str(value)[:4000]
        item["updated"] = _now()
        self._save()
        return item

    def expire_stale(self) -> int:
        """Proposed/approved items older than EXPIRY_HOURS expire. Returns count."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=EXPIRY_HOURS)
        expired = 0
        for item in self.items.values():
            if item.get("state") not in ("proposed", "approved"):
                continue
            try:
                updated = datetime.fromisoformat(item["updated"])
            except (KeyError, ValueError):
                continue
            if updated < cutoff:
                item["state"] = "expired"
                item["updated"] = _now()
                expired += 1
        if expired:
            self._save()
        return expired

    # --- views ------------------------------------------------------------------

    def by_state(self, *states: str) -> list[dict]:
        out = [i for i in self.items.values() if i.get("state") in states]
        out.sort(key=lambda i: i.get("updated", ""), reverse=True)
        return out

    def submitted_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return sum(
            1 for i in self.items.values()
            if i.get("state") == "submitted" and str(i.get("updated", "")).startswith(today)
        )

    def has(self, item_id: str) -> bool:
        return item_id in self.items
