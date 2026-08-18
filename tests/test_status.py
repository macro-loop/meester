import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.status import load_statuses, set_status


def test_set_and_clear_round_trip(tmp_path):
    path = tmp_path / "status.json"
    set_status(path, "abc123", "starred")
    assert load_statuses(path)["abc123"]["state"] == "starred"
    set_status(path, "abc123", "applied")  # a job moves star -> applied
    assert load_statuses(path)["abc123"]["state"] == "applied"
    set_status(path, "abc123", None)
    assert load_statuses(path) == {}


def test_invalid_inputs_raise_rather_than_store_garbage(tmp_path):
    path = tmp_path / "status.json"
    with pytest.raises(ValueError):
        set_status(path, "", "starred")
    with pytest.raises(ValueError):
        set_status(path, "abc", "favourite")
    with pytest.raises(ValueError):
        set_status(path, "x" * 100, "starred")


def test_corrupt_file_reads_as_empty_not_crash(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("{broken", encoding="utf-8")
    assert load_statuses(path) == {}
    # And writing on top of the corruption works.
    set_status(path, "abc", "hidden")
    assert load_statuses(path)["abc"]["state"] == "hidden"


def test_unknown_states_in_file_are_dropped_on_read(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"a": {"state": "starred", "at": "x"},
                                "b": {"state": "exploded", "at": "x"}}), encoding="utf-8")
    got = load_statuses(path)
    assert "a" in got and "b" not in got


def test_statuses_flow_into_the_report_payload(tmp_path):
    from meester.report import _prepare

    rows = [{"fingerprint": "fp1", "title": "T", "company": "C"},
            {"fingerprint": "fp2", "title": "U", "company": "D"}]
    prepared = _prepare(rows, statuses={"fp1": {"state": "applied", "at": ""}})
    by_id = {j["id"]: j for j in prepared}
    assert by_id["fp1"]["st"] == "applied"
    assert "st" not in by_id["fp2"]
