"""The LLM fit judge - Phase 5b of the master plan.

Runs at HARVEST time on gate survivors only, never at render, and every verdict
is cached by (job fingerprint, preferences hash, ledger version). Re-rendering
the report a hundred times bills nothing; only a genuinely new job, or a change
to her preferences or verified history, triggers a call.

Keyless behaviour: judge_survivors returns the cache as-is and the report
renders exactly as the deterministic gates left it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..llm import LLM, MODEL_STRONG, LLMBudgetExceeded, LLMUnavailable
from .gates import score_job

MAX_JUDGED_PER_RUN = 40
CACHE_KEEP_LINES = 2000

# The preference fields that change what "fit" means. Cosmetic fields
# (notice period, application volume) deliberately excluded so editing them
# does not re-bill every cached verdict.
_FIT_PREF_KEYS = (
    "titles", "functions", "seniority", "salary_floor",
    "priorities", "moving_away_from",
)


def prefs_hash(prefs: dict) -> str:
    basis = {k: prefs.get(k) for k in _FIT_PREF_KEYS}
    return hashlib.sha1(
        json.dumps(basis, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]


def cache_key(fingerprint: str, prefs: dict, ledger: dict | None) -> str:
    version = (ledger or {}).get("saved_at", "no-ledger")
    return f"{fingerprint}|{prefs_hash(prefs)}|{version}"


def load_cache(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if isinstance(row, dict) and "k" in row:
                    out[row["k"]] = row
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return out


def _append(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    # Prune occasionally so an unattended machine never grows this unbounded.
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > CACHE_KEEP_LINES * 2:
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines[-CACHE_KEEP_LINES:]) + "\n", encoding="utf-8")
        tmp.replace(path)


def _ledger_summary(ledger: dict) -> str:
    parts: list[str] = []
    for e in (ledger.get("employment") or [])[:8]:
        bullets = "; ".join((e.get("bullets") or [])[:4])
        parts.append(
            f"- {e.get('title') or '?'} at {e.get('employer') or '?'} "
            f"({e.get('start')}-{e.get('end')}): {bullets}"
        )
    if ledger.get("skills"):
        parts.append("Skills: " + ", ".join(ledger["skills"][:25]))
    return "\n".join(parts) or "(no verified history)"


def _prompt(job: dict, prefs: dict, ledger: dict) -> str:
    return (
        "CANDIDATE\n"
        f"Wants: {', '.join(prefs.get('titles') or []) or 'unspecified'}, "
        f"{prefs.get('seniority') or 'any'} level, "
        f"in {', '.join(prefs.get('functions') or []) or 'unspecified'}.\n"
        f"Priorities, in order: {', '.join(prefs.get('priorities') or []) or 'unspecified'}.\n"
        f"Moving away from: {prefs.get('moving_away_from') or 'nothing stated'}.\n"
        "Verified history:\n"
        f"{_ledger_summary(ledger)}\n\n"
        "JOB\n"
        f"{job.get('title')} at {job.get('company')}\n"
        f"{(job.get('description') or '')[:6000]}\n\n"
        "Score the fit 0-100:\n"
        "- 80+: the verified history covers the core requirements at the right level\n"
        "- 50-79: real overlap, one or two material requirements unsupported\n"
        "- below 50: the posting wants a different person\n\n"
        'Reply with JSON only: {"fit": <int>, "evidence": [up to 3 strings, each '
        '"her <specific thing from the record> ~ their <specific requirement>"], '
        '"gaps": [up to 3 requirements her record does not support]}'
    )


_SYSTEM = (
    "You judge how well one job posting fits one specific candidate. You are "
    "strict and concrete. Evidence means pairing something the candidate has "
    "actually done, from their verified record, with something the posting "
    "actually asks for. Never invent experience, never soften gaps. If the "
    "record does not support a claim, it is a gap, not evidence."
)


def _clean_verdict(raw: dict) -> dict | None:
    try:
        fit = max(0, min(100, int(raw.get("fit"))))
    except (TypeError, ValueError):
        return None
    evidence = [str(x).strip()[:200] for x in (raw.get("evidence") or []) if str(x).strip()][:3]
    gaps = [str(x).strip()[:200] for x in (raw.get("gaps") or []) if str(x).strip()][:3]
    return {"fit": fit, "evidence": evidence, "gaps": gaps}


def judge_survivors(
    rows: list[dict],
    prefs: dict,
    ledger: dict | None,
    cache_path: Path,
    llm: LLM,
) -> dict[str, dict]:
    """Judge uncached gate survivors. Returns {fingerprint: verdict} for ALL
    cached-or-new survivors under the current prefs/ledger version."""
    cache = load_cache(cache_path)
    if ledger is None or not ledger.get("verified"):
        # Judging against no verified history would produce confident nonsense;
        # the deterministic gates remain the whole story until the ledger exists.
        return {}

    survivors = []
    for row in rows:
        verdict = score_job(row, prefs, ledger)
        if verdict["match"]:
            survivors.append((verdict["score"], row))
    survivors.sort(key=lambda x: -x[0])
    survivors = [row for _, row in survivors[:MAX_JUDGED_PER_RUN]]

    results: dict[str, dict] = {}
    fresh: list[dict] = []
    for row in survivors:
        fp = row.get("fingerprint") or ""
        if not fp:
            continue
        key = cache_key(fp, prefs, ledger)
        if key in cache:
            results[fp] = cache[key]
            continue
        try:
            raw = llm.call_json(_prompt(row, prefs, ledger), system=_SYSTEM,
                                model=MODEL_STRONG, max_tokens=700)
        except (LLMUnavailable, LLMBudgetExceeded):
            break  # keyless or capped: keep what we have, stop cleanly
        except RuntimeError:
            continue  # one flaky call must not sink the batch
        verdict = _clean_verdict(raw)
        if verdict is None:
            continue
        entry = {"k": key, **verdict}
        cache[key] = entry
        results[fp] = entry
        fresh.append(entry)

    if fresh:
        _append(cache_path, fresh)
    return results


def judged_for_report(
    rows: list[dict], prefs: dict, ledger: dict | None, cache_path: Path
) -> dict[str, dict]:
    """Cache-only lookup for render time - never bills."""
    if ledger is None:
        return {}
    cache = load_cache(cache_path)
    out: dict[str, dict] = {}
    for row in rows:
        fp = row.get("fingerprint") or ""
        entry = cache.get(cache_key(fp, prefs, ledger))
        if entry:
            out[fp] = entry
    return out
