import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.models import Job, Workplace
from meester.store import JobStore


def make(title="Senior Software Engineer", **kw) -> Job:
    base = dict(
        source="greenhouse",
        company="Stripe",
        company_token="stripe",
        external_id="1",
        title=title,
        url="https://example.com/1",
        workplace=Workplace.REMOTE,
    )
    base.update(kw)
    return Job(**base)


def store_at(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "jobs.jsonl", tmp_path / "seen.json")


def test_second_run_adds_nothing(tmp_path):
    """The property the whole pipeline depends on: harvesting twice must not
    queue the same role twice. A duplicate here becomes a duplicate application."""
    jobs = [make("Engineer A"), make("Engineer B", external_id="2")]
    for j in jobs:
        j.fingerprint = j.compute_fingerprint()

    s1 = store_at(tmp_path)
    assert len(s1.add_new(jobs)) == 2

    # Fresh instance, to prove persistence rather than in-memory state.
    s2 = store_at(tmp_path)
    assert s2.add_new(jobs) == []
    assert len(s2) == 2

    lines = (tmp_path / "jobs.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_new_job_appended_alongside_known_ones(tmp_path):
    s = store_at(tmp_path)
    s.add_new([make("Engineer A")])
    added = s.add_new([make("Engineer A"), make("Engineer B", external_id="2")])
    assert len(added) == 1
    assert added[0].title == "Engineer B"


def test_written_rows_are_valid_json_with_provenance(tmp_path):
    s = store_at(tmp_path)
    s.add_new([make()])
    row = json.loads((tmp_path / "jobs.jsonl").read_text(encoding="utf-8").strip())
    assert row["fingerprint"]
    assert row["first_seen"]
    assert row["workplace"] == "remote"


def test_corrupt_seen_file_fails_loudly(tmp_path):
    """Silently treating a corrupt seen-set as empty would re-apply to everything
    already applied to, so this must raise rather than degrade."""
    (tmp_path / "seen.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Refusing to run"):
        store_at(tmp_path)
