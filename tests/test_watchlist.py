import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.watchlist import add, load_local, merge, remove, save_local

BASE = {"greenhouse": ["stripe", "coinbase"], "lever": ["spotify"], "ashby": ["ramp"]}


def test_merge_with_no_local_changes_is_the_base_list():
    assert merge(BASE, {"added": {}, "removed": {}}) == BASE


def test_added_companies_appear():
    local = {"added": {"greenhouse": ["faire"]}, "removed": {}}
    assert merge(BASE, local)["greenhouse"] == ["stripe", "coinbase", "faire"]


def test_removed_companies_disappear():
    local = {"added": {}, "removed": {"greenhouse": ["coinbase"]}}
    assert merge(BASE, local)["greenhouse"] == ["stripe"]


def test_adding_something_already_in_the_base_list_does_not_duplicate():
    # She has no way of knowing what is already watched, so this must be a no-op
    # rather than causing the board to be fetched twice.
    local = {"added": {"lever": ["spotify"]}, "removed": {}}
    assert merge(BASE, local)["lever"] == ["spotify"]


def test_tokens_are_case_and_space_insensitive():
    local = {"added": {"greenhouse": ["  FAIRE "]}, "removed": {}}
    assert "faire" in merge(BASE, local)["greenhouse"]


def test_removing_her_own_addition_drops_it_rather_than_tombstoning():
    local = {"added": {"greenhouse": ["faire"]}, "removed": {}}
    remove(local, "greenhouse", "faire")
    assert local["added"]["greenhouse"] == []
    assert not (local.get("removed") or {}).get("greenhouse")
    # Re-adding must work cleanly afterwards.
    add(local, "greenhouse", "faire")
    assert "faire" in merge(BASE, local)["greenhouse"]


def test_re_adding_a_hidden_base_company_unhides_it():
    local = {"added": {}, "removed": {"greenhouse": ["coinbase"]}}
    add(local, "greenhouse", "coinbase")
    assert "coinbase" in merge(BASE, local)["greenhouse"]


def test_empty_ats_keys_are_omitted():
    local = {"added": {}, "removed": {"lever": ["spotify"]}}
    assert "lever" not in merge(BASE, local)


def test_round_trip_through_disk(tmp_path):
    path = tmp_path / "companies.local.yaml"
    local = {"added": {"ashby": ["linear"]}, "removed": {"greenhouse": ["stripe"]}}
    save_local(path, local)
    back = load_local(path)
    assert back["added"]["ashby"] == ["linear"]
    assert back["removed"]["greenhouse"] == ["stripe"]


def test_missing_file_is_not_an_error(tmp_path):
    assert load_local(tmp_path / "nope.yaml") == {"added": {}, "removed": {}}


def test_corrupt_file_falls_back_to_the_tracked_list(tmp_path):
    # A mangled local file must not take the harvester down - the tracked list
    # is a safe fallback, unlike the seen-set where silence would cause re-applies.
    path = tmp_path / "companies.local.yaml"
    path.write_text("added: [this is not\n  valid: yaml: {{", encoding="utf-8")
    assert load_local(path) == {"added": {}, "removed": {}}


def test_unknown_ats_keys_are_ignored(tmp_path):
    path = tmp_path / "companies.local.yaml"
    path.write_text("added:\n  workday:\n    - acme\n", encoding="utf-8")
    assert load_local(path)["added"] == {}
