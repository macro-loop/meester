"""The inbox loop: read JobSearch mail, classify it, move the tracker.

Reads only through GoogleClient.gmail_search, so the JobSearch-label restriction
is structural. Classification uses the LLM when a key is present and a keyword
heuristic otherwise - both good enough to move a job's status from applied to
rejected / screen / interview and to draft (never send) a reply.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

CATEGORIES = ("rejection", "interview", "assessment", "recruiter_screen", "other")

_HEURISTICS: list[tuple[str, re.Pattern]] = [
    ("rejection", re.compile(
        r"\b(unfortunately|regret to inform|not (moving|move) forward|decided (not|to pursue "
        r"other)|will not be (proceeding|moving)|other candidates|no longer under "
        r"consideration)\b", re.I)),
    ("interview", re.compile(
        r"\b(schedule.{0,20}(call|interview|chat)|calendly|book.{0,15}time|availability|"
        r"would love to (chat|talk|meet)|set up.{0,15}(call|time)|next round)\b", re.I)),
    ("assessment", re.compile(
        r"\b(take[- ]home|coding (challenge|exercise|assessment)|hackerrank|codesignal|"
        r"complete.{0,20}assessment|technical (screen|test))\b", re.I)),
    ("recruiter_screen", re.compile(
        r"\b(recruiter|talent (partner|acquisition)|initial (call|chat|conversation)|"
        r"learn more about (you|your background)|quick (call|chat))\b", re.I)),
]

# Category -> the job status it implies. `other` never moves the tracker.
STATUS_FOR = {
    "rejection": "rejected", "interview": "interview",
    "assessment": "assessment", "recruiter_screen": "screen",
}


def classify_heuristic(subject: str, body: str) -> str:
    text = f"{subject}\n{body}"
    for category, pattern in _HEURISTICS:
        if pattern.search(text):
            return category
    return "other"


def classify(llm, subject: str, body: str) -> str:
    """LLM classification with the heuristic as fallback."""
    if llm is None:
        return classify_heuristic(subject, body)
    try:
        out = llm.call_json(
            "Classify this email from a hiring process into exactly one of: "
            "rejection, interview, assessment, recruiter_screen, other.\n\n"
            f"Subject: {subject}\n\n{body[:2500]}\n\n"
            'Reply as JSON: {"category": "<one>"}',
            max_tokens=60,
        )
        category = str(out.get("category", "")).strip().lower()
        return category if category in CATEGORIES else classify_heuristic(subject, body)
    except Exception:  # noqa: BLE001
        return classify_heuristic(subject, body)


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()


def save_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    # Bound the set so it cannot grow forever on an unattended machine.
    tmp.write_text(json.dumps(sorted(seen)[-5000:]), encoding="utf-8")
    tmp.replace(path)


def process(client, llm, seen_path: Path, max_messages: int = 25) -> list[dict]:
    """Fetch new JobSearch mail, classify, return actions for the caller.

    Returns [{id, category, from, subject, thread_id, needs_reply}]. The caller
    owns the side effects (status updates, draft creation, notification) so this
    stays testable without a live account.
    """
    seen = load_seen(seen_path)
    messages = client.gmail_search("newer_than:30d", max_results=max_messages)
    actions: list[dict] = []
    for stub in messages:
        mid = stub.get("id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        msg = client.gmail_message(mid)
        category = classify(llm, msg["subject"], msg["body"])
        actions.append({
            "id": mid, "thread_id": msg.get("threadId"),
            "from": msg["from"], "subject": msg["subject"],
            "category": category,
            "status": STATUS_FOR.get(category),
            "needs_reply": category in ("interview", "recruiter_screen"),
            "at": datetime.now(timezone.utc).isoformat(),
        })
    save_seen(seen_path, seen)
    return actions


def draft_reply_text(llm, category: str, subject: str, body: str,
                     her_name: str = "") -> tuple[str, str] | None:
    """A reply draft for interview/screen mail. None means no draft warranted."""
    if category not in ("interview", "recruiter_screen"):
        return None
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if llm is None:
        body_text = (
            "Hi,\n\nThank you for reaching out - I'd be glad to talk. "
            "I'm generally free [add your availability here]. "
            "Let me know what works on your end.\n\n"
            f"Best,\n{her_name or '[your name]'}"
        )
        return reply_subject, body_text
    try:
        out = llm.call_json(
            "Write a brief, warm reply accepting an invitation to talk about a job. "
            "Leave a clear placeholder for the candidate's availability. Do not "
            f"invent specific times.\n\nTheir message:\n{body[:2000]}\n\n"
            'Reply as JSON: {"body": "<reply>"}',
            max_tokens=300,
        )
        text = str(out.get("body", "")).strip()
        return (reply_subject, text) if text else None
    except Exception:  # noqa: BLE001
        return None
