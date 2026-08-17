import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.profile import (
    STARTER_LETTERS,
    lint_placeholders,
    load_letters,
    save_letters,
    validate_letters,
)


def test_first_visit_is_seeded_not_blank(tmp_path):
    letters = load_letters(tmp_path / "cover_letters.yaml")
    assert len(letters) == len(STARTER_LETTERS)
    assert letters[0]["body"]


def test_starters_only_use_known_placeholders():
    for letter in STARTER_LETTERS:
        assert lint_placeholders(letter["body"]) == [], letter["name"]


def test_lint_flags_typos_but_validation_does_not_block_them():
    body = "Dear {company}, I love {their_produkt}."
    assert lint_placeholders(body) == ["their_produkt"]
    clean, errors = validate_letters({"letters": [{"name": "x", "body": body}]})
    assert errors == {}
    assert clean[0]["body"] == body


def test_empty_letter_is_a_field_error_and_saves_nothing(tmp_path):
    path = tmp_path / "cover_letters.yaml"
    _, errors = save_letters(path, {"letters": [{"name": "Empty", "body": "   "}]})
    assert errors
    assert not path.exists()


def test_duplicate_names_are_disambiguated_not_lost():
    clean, _ = validate_letters(
        {"letters": [{"name": "Formal", "body": "a"}, {"name": "Formal", "body": "b"}]}
    )
    assert [l["name"] for l in clean] == ["Formal", "Formal (2)"]
    assert [l["body"] for l in clean] == ["a", "b"]


def test_round_trip(tmp_path):
    path = tmp_path / "cover_letters.yaml"
    save_letters(path, {"letters": [{"name": "Mine", "body": "Hello {company}"}]})
    back = load_letters(path)
    assert back == [{"name": "Mine", "body": "Hello {company}"}]


def test_corrupt_file_falls_back_to_starters(tmp_path):
    path = tmp_path / "cover_letters.yaml"
    path.write_text("letters: [broken", encoding="utf-8")
    assert load_letters(path) == STARTER_LETTERS


def test_caps_letter_count_and_length(tmp_path):
    many = {"letters": [{"name": f"L{i}", "body": "x" * 10_000} for i in range(40)]}
    clean, errors = validate_letters(many)
    assert errors == {}
    assert len(clean) == 12
    assert len(clean[0]["body"]) == 3000
