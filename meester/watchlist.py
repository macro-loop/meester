"""The company watchlist, and her local additions to it.

Two sources, deliberately kept in separate files:

  config/companies.yaml        tracked in git, maintained by whoever runs the repo
  config/companies.local.yaml  gitignored, written by her from the Companies screen

Merging rather than editing the tracked file matters for two reasons. Her
additions survive every `git pull` untouched, and a push from the other machine
can never silently wipe a company she added. It also keeps her choices off a
public GitHub repo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ATS_CHOICES = ("greenhouse", "lever", "ashby")

_HEADER = """# Companies added or hidden from the Companies screen.
#
# Written automatically - safe to edit by hand, but it will be rewritten.
# Never committed: this file is gitignored so her watchlist stays on her machine
# and survives every update pulled from GitHub.
"""


def _empty() -> dict[str, dict[str, list[str]]]:
    return {"added": {}, "removed": {}}


def load_local(path: Path) -> dict[str, dict[str, list[str]]]:
    if not path.exists():
        return _empty()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        # A hand-mangled file must not take the harvester down; fall back to the
        # tracked list rather than refusing to run.
        return _empty()
    out = _empty()
    for key in ("added", "removed"):
        section = data.get(key) or {}
        if isinstance(section, dict):
            for ats, tokens in section.items():
                if ats in ATS_CHOICES and isinstance(tokens, list):
                    out[key][ats] = [str(t).strip().lower() for t in tokens if str(t).strip()]
    return out


def save_local(path: Path, local: dict[str, dict[str, list[str]]]) -> None:
    payload = {
        key: {ats: sorted(set(tokens)) for ats, tokens in (local.get(key) or {}).items() if tokens}
        for key in ("added", "removed")
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(_HEADER + "\n" + yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def merge(base: dict[str, Any], local: dict[str, dict[str, list[str]]]) -> dict[str, list[str]]:
    """(base + added) - removed, per ATS, order-stable and de-duplicated."""
    out: dict[str, list[str]] = {}
    added = local.get("added") or {}
    removed = local.get("removed") or {}
    for ats in ATS_CHOICES:
        seen: list[str] = []
        for token in list(base.get(ats) or []) + list(added.get(ats) or []):
            t = str(token).strip().lower()
            if t and t not in seen:
                seen.append(t)
        drop = {str(t).strip().lower() for t in (removed.get(ats) or [])}
        kept = [t for t in seen if t not in drop]
        if kept:
            out[ats] = kept
    return out


def add(local: dict, ats: str, token: str) -> None:
    token = token.strip().lower()
    local.setdefault("added", {}).setdefault(ats, [])
    if token not in local["added"][ats]:
        local["added"][ats].append(token)
    # Adding something previously hidden should un-hide it.
    rem = (local.get("removed") or {}).get(ats) or []
    if token in rem:
        rem.remove(token)


def remove(local: dict, ats: str, token: str) -> None:
    token = token.strip().lower()
    added = (local.get("added") or {}).get(ats) or []
    if token in added:
        # Only ever her own addition: drop it outright rather than recording a
        # tombstone, so re-adding later behaves predictably.
        added.remove(token)
        return
    local.setdefault("removed", {}).setdefault(ats, [])
    if token not in local["removed"][ats]:
        local["removed"][ats].append(token)
