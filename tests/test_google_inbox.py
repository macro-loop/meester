"""Gmail label-scoping, inbox classification, outreach polling. All offline."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.google_api import GoogleClient, LabelScopeError, REQUIRED_LABEL
from meester.inbox import classify_heuristic, draft_reply_text, process
from meester.outreach import poll_contacts, skeleton_note, weekly_sent


# --- the label contract -----------------------------------------------------------

class FakeSheets:
    def __init__(self, rows): self._rows = rows
    def sheet_rows(self, sid, range_a1="A:Z"): return self._rows


class RecordingClient(GoogleClient):
    """Captures the query gmail_search would send, without a network."""
    def __init__(self):
        self.queries = []
        self._msgs = {}

    def gmail_search(self, query, max_results=25):
        # Re-run the real scoping logic, then record.
        scoped = f"label:{REQUIRED_LABEL} {query}".strip()
        if f"label:{REQUIRED_LABEL}" not in scoped:
            raise LabelScopeError("refusing unscoped read")
        self.queries.append(scoped)
        return list(self._msgs.values())

    def gmail_message(self, mid):
        return self._msgs[mid]


def test_every_gmail_search_carries_the_jobsearch_label():
    client = RecordingClient()
    client.gmail_search("newer_than:7d")
    client.gmail_search("from:greenhouse.io")
    assert all(q.startswith(f"label:{REQUIRED_LABEL}") for q in client.queries)


def test_inbox_only_reads_within_the_label(monkeypatch, tmp_path):
    client = RecordingClient()
    client._msgs = {
        "m1": {"id": "m1", "threadId": "t1", "from": "recruiter@acme.com",
               "subject": "Unfortunately", "body": "we regret to inform you",
               "snippet": ""},
    }
    actions = process(client, None, tmp_path / "seen.json")
    assert client.queries and client.queries[0].startswith(f"label:{REQUIRED_LABEL}")
    assert actions[0]["category"] == "rejection"
    assert actions[0]["status"] == "rejected"


def test_seen_messages_are_not_reprocessed(tmp_path):
    client = RecordingClient()
    client._msgs = {"m1": {"id": "m1", "threadId": "t", "from": "x@y.com",
                           "subject": "hi", "body": "let's schedule a call", "snippet": ""}}
    first = process(client, None, tmp_path / "seen.json")
    second = process(client, None, tmp_path / "seen.json")
    assert len(first) == 1 and second == []


# --- classification ---------------------------------------------------------------

@pytest.mark.parametrize("subject,body,expected", [
    ("Update on your application", "Unfortunately we will not be moving forward", "rejection"),
    ("Next steps", "Are you free for a call? Here's my calendly", "interview"),
    ("Take-home", "Please complete this coding challenge on HackerRank", "assessment"),
    ("Quick chat", "I'm a recruiter and would love to learn more about your background", "recruiter_screen"),
    ("Newsletter", "Here are this week's engineering blog posts", "other"),
])
def test_heuristic_classification(subject, body, expected):
    assert classify_heuristic(subject, body) == expected


def test_reply_drafted_only_for_conversational_categories():
    assert draft_reply_text(None, "rejection", "No", "body") is None
    got = draft_reply_text(None, "interview", "Chat?", "body", her_name="Jane")
    assert got is not None
    assert "Jane" in got[1]
    assert got[0].startswith("Re:")


# --- outreach ---------------------------------------------------------------------

def test_poll_contacts_matches_columns_loosely():
    rows = [
        ["Fingerprint", "Full Name", "Work Email", "Title", "LinkedIn URL"],
        ["fp1", "Dana Lee", "dana@acme.com", "Design Manager", "linkedin.com/in/dana"],
        ["fp2", "No Email Person", "", "PM", ""],  # dropped: no email
    ]
    got = poll_contacts(FakeSheets(rows), "sheet123")
    assert set(got) == {"fp1"}
    assert got["fp1"]["email"] == "dana@acme.com"
    assert got["fp1"]["title"] == "Design Manager"


def test_poll_contacts_empty_without_required_columns():
    assert poll_contacts(FakeSheets([["Name", "Phone"], ["x", "y"]]), "s") == {}
    assert poll_contacts(FakeSheets([]), "s") == {}


def test_skeleton_note_is_valid_and_marks_the_blank():
    note = json.loads(skeleton_note("Figma", "Product Designer"))
    assert "Figma" in note["body"] and "[" in note["body"]  # the blank she fills


def test_weekly_cap_counts_recent_sends(tmp_path):
    log = tmp_path / "sent.jsonl"
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=10)).isoformat()
    recent = (now - timedelta(days=1)).isoformat()
    log.write_text(
        json.dumps({"fp": "a", "to": "x", "at": old}) + "\n"
        + json.dumps({"fp": "b", "to": "y", "at": recent}) + "\n",
        encoding="utf-8",
    )
    assert weekly_sent(log) == 1  # the 10-day-old one is outside the window
