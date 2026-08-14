"""Local append-only store.

Airtable is the eventual system of record, but a JSONL file on disk is the right
first store: it costs nothing, it makes the "re-run adds zero rows" property
trivially testable, and it means the harvester can be developed and verified
before any credentials exist.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Job


class JobStore:
    def __init__(self, path: str | Path, seen_path: str | Path) -> None:
        self.path = Path(path)
        self.seen_path = Path(seen_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.seen_path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: dict[str, str] = self._load_seen()

    def _load_seen(self) -> dict[str, str]:
        if not self.seen_path.exists():
            return {}
        try:
            return json.loads(self.seen_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt seen-set would cause a re-application storm, so fail loud
            # rather than silently treating every known job as new.
            raise RuntimeError(
                f"{self.seen_path} is unreadable. Refusing to run: every previously "
                "seen job would be treated as new. Inspect or delete it deliberately."
            )

    def is_new(self, job: Job) -> bool:
        return (job.fingerprint or job.compute_fingerprint()) not in self._seen

    def add_new(self, jobs: list[Job]) -> list[Job]:
        """Append only unseen jobs. Returns what was actually added."""
        fresh = [j for j in jobs if self.is_new(j)]
        if not fresh:
            return []
        stamp = datetime.now(timezone.utc).isoformat()
        with self.path.open("a", encoding="utf-8") as fh:
            for job in fresh:
                fp = job.fingerprint or job.compute_fingerprint()
                record = job.to_dict()
                record["first_seen"] = stamp
                record["fingerprint"] = fp
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                self._seen[fp] = stamp
        self._flush_seen()
        return fresh

    def _flush_seen(self) -> None:
        tmp = self.seen_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._seen, indent=0), encoding="utf-8")
        tmp.replace(self.seen_path)

    def __len__(self) -> int:
        return len(self._seen)
