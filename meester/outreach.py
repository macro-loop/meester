"""Warm outreach: the ~11x lever the master plan is built around.

When an application lands at a target-tier company, a hiring-manager contact is
sought through Clay (POST to a webhook table in the Clay workspace; the Clay
workflow enriches and exports to a Google Sheet her Mac can read), a short note
is drafted, and it becomes a queue item of kind `outreach` on the same approve
surface as applications. Nothing sends without her tap, and the weekly cap keeps
this lane quality-only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

DEFAULT_WEEKLY_CAP = 5
CONTACT_WAIT_DAYS = 2  # let the application settle before reaching out


def _now() -> datetime:
    return datetime.now(timezone.utc)


def request_contact(webhook_url: str, company: str, role: str, job_url: str,
                    fingerprint: str) -> bool:
    """Ask Clay to find a contact. Fire-and-forget; results arrive via the Sheet.

    The fingerprint is echoed so the returned Sheet row can be matched back to
    the application that triggered it."""
    if not webhook_url:
        return False
    try:
        resp = httpx.post(webhook_url, json={
            "fingerprint": fingerprint, "company": company,
            "role": role, "job_url": job_url,
            "requested_at": _now().isoformat(),
        }, timeout=30)
        return resp.status_code < 400
    except httpx.HTTPError:
        return False


def poll_contacts(client, spreadsheet_id: str) -> dict[str, dict]:
    """Read the Clay export sheet -> {fingerprint: {name, email, title, linkedin}}.

    Expects a header row; column names are matched loosely so the exact Clay
    column labels don't have to be perfect."""
    rows = client.sheet_rows(spreadsheet_id)
    if not rows:
        return {}
    header = [h.strip().lower() for h in rows[0]]

    def col(*names: str) -> int | None:
        for name in names:
            for i, h in enumerate(header):
                if name in h:
                    return i
        return None

    idx = {
        "fp": col("fingerprint", "fp"),
        "name": col("name", "full name", "contact"),
        "email": col("email", "work email"),
        "title": col("title", "role", "position"),
        "linkedin": col("linkedin", "profile"),
    }
    if idx["fp"] is None or idx["email"] is None:
        return {}

    out: dict[str, dict] = {}
    for row in rows[1:]:
        def get(key: str) -> str:
            i = idx[key]
            return row[i].strip() if i is not None and i < len(row) else ""

        fp, email = get("fp"), get("email")
        if fp and email and "@" in email:
            out[fp] = {"name": get("name"), "email": email,
                       "title": get("title"), "linkedin": get("linkedin")}
    return out


def draft_note(llm, contact: dict, company: str, role: str,
               job_description: str, ledger: dict | None) -> str | None:
    """Four sentences, specific and true. Returns None without a key - the
    queue card then shows a skeleton she completes herself."""
    if llm is None:
        return None
    who = contact.get("name") or "there"
    latest = ((ledger or {}).get("employment") or [{}])[0]
    background = f"{latest.get('title', '')} at {latest.get('employer', '')}".strip(" at")
    try:
        out = llm.call_json(
            f"Write a 4-sentence note to {who}, a {contact.get('title', 'contact')} "
            f"at {company}, from a candidate who just applied for their {role} role. "
            f"The candidate's background: {background}. Reference something specific "
            f"and true from this posting; no flattery, no invented facts, warm but "
            f"brief.\n\nPosting:\n{job_description[:2500]}\n\n"
            'Reply as JSON: {"subject": "<short>", "body": "<4 sentences>"}',
            max_tokens=400,
        )
        subject = str(out.get("subject", f"Just applied for the {role} role")).strip()
        body = str(out.get("body", "")).strip()
        return json.dumps({"subject": subject[:150], "body": body[:1500]})
    except Exception:  # noqa: BLE001
        return None


def skeleton_note(company: str, role: str) -> str:
    return json.dumps({
        "subject": f"Just applied for the {role} role",
        "body": f"Hi,\n\nI just applied for the {role} role at {company} and wanted "
                "to introduce myself briefly.\n\n[one specific, true sentence about "
                "why this role and why you]\n\nWould you be open to a short chat?\n\n"
                "Best,\n[your name]",
    })


def weekly_sent(sent_log: Path) -> int:
    """Outreach emails sent in the last 7 days, from the send log."""
    if not sent_log.exists():
        return 0
    cutoff = _now().timestamp() - 7 * 86400
    count = 0
    try:
        for line in sent_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                when = datetime.fromisoformat(json.loads(line)["at"]).timestamp()
                if when >= cutoff:
                    count += 1
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    except OSError:
        pass
    return count


def record_sent(sent_log: Path, fingerprint: str, to: str) -> None:
    sent_log.parent.mkdir(parents=True, exist_ok=True)
    with sent_log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"fp": fingerprint, "to": to,
                             "at": _now().isoformat()}) + "\n")
