"""Applications-tab sync: append-only, idempotent, and never guesses 'how'."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.sheet_track import HEADER, TAB, applied_rows, sync

STATUSES = {
    "fp-auto": {"state": "applied", "at": "2026-08-15T10:00:00+00:00"},
    "fp-hand": {"state": "applied", "at": "2026-08-16T10:00:00+00:00"},
    "fp-tick": {"state": "applied", "at": "2026-08-17T10:00:00+00:00"},
    "fp-star": {"state": "starred", "at": "2026-08-17T11:00:00+00:00"},
}
STORE = {
    "fp-auto": {"company": "Acme", "title": "Analyst", "url": "https://a"},
    "fp-hand": {"company": "Bmce", "title": "Senior Analyst", "url": "https://b"},
    "fp-tick": {"company": "Cmce", "title": "Data Analyst", "url": "https://c"},
}
QUEUE = {
    "fp-auto": {"kind": "application", "state": "submitted", "note": ""},
    "fp-hand": {"kind": "application", "state": "submitted",
                "note": "applied by hand"},
    # fp-tick: no queue item at all - she ticked Applied on the jobs list.
}


class FakeClient:
    def __init__(self, tabs=None):
        self.tabs = tabs if tabs is not None else {}
        self.appends = []

    def sheet_tab_rows(self, sheet_id, tab):
        return self.tabs.get(tab)  # None = tab missing, like the real API

    def sheet_add_tab(self, sheet_id, tab):
        self.tabs.setdefault(tab, [])

    def sheet_append(self, sheet_id, tab, rows):
        self.appends.append(rows)
        self.tabs.setdefault(tab, []).extend(rows)


def test_how_covers_all_three_paths():
    rows = applied_rows(STATUSES, STORE, QUEUE)
    how = {r[-1]: r[3] for r in rows}
    assert how == {"fp-auto": "automatic", "fp-hand": "by hand",
                   "fp-tick": "marked applied"}
    assert len(rows) == 3, "starred-but-not-applied must not become a row"


def test_first_sync_creates_tab_header_and_rows():
    client = FakeClient()
    written = sync(client, "sheet1", STATUSES, STORE, QUEUE)
    assert written == 3
    assert client.tabs[TAB][0] == HEADER
    companies = [r[1] for r in client.tabs[TAB][1:]]
    assert companies == ["Acme", "Bmce", "Cmce"], "oldest application first"


def test_second_sync_writes_nothing(tmp_path):
    client = FakeClient()
    sync(client, "sheet1", STATUSES, STORE, QUEUE)
    before = len(client.appends)
    assert sync(client, "sheet1", STATUSES, STORE, QUEUE) == 0
    assert len(client.appends) == before, "an unchanged world must append zero rows"


def test_her_reordered_columns_still_dedupe():
    # She is free to rearrange the sheet; a fingerprint anywhere in a row
    # still counts as known.
    client = FakeClient(tabs={TAB: [HEADER, ["fp-auto", "moved", "around"]]})
    written = sync(client, "sheet1", STATUSES, STORE, QUEUE)
    assert written == 2
    fps = {r[-1] for rows in client.appends for r in rows}
    assert "fp-auto" not in fps


def test_no_applied_jobs_touches_nothing():
    client = FakeClient()
    assert sync(client, "sheet1", {"fp": {"state": "hidden"}}, {}, {}) == 0
    assert client.appends == [] and client.tabs == {}


def test_job_gone_from_store_still_tracked():
    rows = applied_rows({"fp-x": {"state": "applied", "at": "2026-08-01T00:00:00"}},
                        {}, {})
    assert rows == [["2026-08-01", "", "", "marked applied", "", "fp-x"]]
