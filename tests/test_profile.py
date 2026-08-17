import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.profile import (
    PREF_FIELDS,
    default_preferences,
    load_preferences,
    save_preferences,
    schema_for_client,
    validate_preferences,
)


def test_schema_covers_every_field_and_is_json_shaped():
    keys = {f["key"] for f in schema_for_client()}
    assert keys == {f["key"] for f in PREF_FIELDS}
    for f in schema_for_client():
        assert f["type"] in ("text", "number", "bool", "select", "list", "longtext")
        assert f["label"]


def test_lists_accept_textarea_strings_one_per_line():
    clean, errors = validate_preferences({"titles": "Product Designer\n\n  UX Designer  \n"})
    assert errors == {}
    assert clean["titles"] == ["Product Designer", "UX Designer"]


def test_numbers_tolerate_human_formatting():
    clean, errors = validate_preferences({"salary_floor": "$120,000"})
    assert errors == {}
    assert clean["salary_floor"] == 120000


def test_bad_number_reports_a_field_error_and_saves_nothing(tmp_path):
    path = tmp_path / "preferences.yaml"
    clean, errors = save_preferences(path, {"salary_floor": "a lot"})
    assert "salary_floor" in errors
    assert not path.exists(), "a failed validation must not write the file"


def test_number_range_is_enforced():
    _, errors = validate_preferences({"max_timezone_offset_hours": 99})
    assert "max_timezone_offset_hours" in errors


def test_select_rejects_off_list_values():
    _, errors = validate_preferences({"seniority": "supreme leader"})
    assert "seniority" in errors
    clean, errors = validate_preferences({"seniority": "Senior"})
    assert errors == {} and clean["seniority"] == "senior"


def test_unknown_keys_are_dropped_not_stored(tmp_path):
    path = tmp_path / "preferences.yaml"
    save_preferences(path, {"titles": "Designer", "evil": "payload"})
    text = path.read_text(encoding="utf-8")
    assert "evil" not in text


def test_round_trip(tmp_path):
    path = tmp_path / "preferences.yaml"
    save_preferences(
        path,
        {"titles": "Designer\nResearcher", "salary_floor": "90000",
         "needs_sponsorship": True, "moving_away_from": "agencies"},
    )
    back = load_preferences(path)
    assert back["titles"] == ["Designer", "Researcher"]
    assert back["salary_floor"] == 90000
    assert back["needs_sponsorship"] is True
    assert back["moving_away_from"] == "agencies"


def test_missing_and_corrupt_files_fall_back_to_defaults(tmp_path):
    assert load_preferences(tmp_path / "nope.yaml") == default_preferences()
    bad = tmp_path / "preferences.yaml"
    bad.write_text("titles: [unclosed", encoding="utf-8")
    assert load_preferences(bad) == default_preferences()


def test_oversized_input_is_capped_not_rejected():
    clean, errors = validate_preferences(
        {"titles": "\n".join(f"title {i}" for i in range(500)),
         "moving_away_from": "x" * 50_000}
    )
    assert errors == {}
    assert len(clean["titles"]) == 50
    assert len(clean["moving_away_from"]) == 2000
