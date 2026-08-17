"""Company lookup: URL parsing and slug generation. All offline."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.lookup import parse_board_url, slug_candidates

URL_CASES = [
    ("https://jobs.lever.co/brex", "lever", "brex"),
    ("https://jobs.eu.lever.co/wise", "lever", "wise"),
    ("https://boards.greenhouse.io/stripe", "greenhouse", "stripe"),
    ("https://job-boards.greenhouse.io/anthropic/jobs/5101378008", "greenhouse", "anthropic"),
    ("https://boards.greenhouse.io/embed/job_board?for=gitlab", "greenhouse", "gitlab"),
    ("https://jobs.ashbyhq.com/ramp", "ashby", "ramp"),
    ("jobs.ashbyhq.com/linear/abc-123", "ashby", "linear"),
    # Uppercase and trailing whitespace are what a real paste looks like.
    ("  HTTPS://JOBS.LEVER.CO/Brex  ", "lever", "brex"),
]


def test_board_urls_are_parsed():
    for url, ats, token in URL_CASES:
        m = parse_board_url(url)
        assert m is not None, f"{url!r} did not parse"
        assert (m.ats, m.token) == (ats, token), f"{url!r} -> {m.ats}/{m.token}"


def test_non_board_urls_are_rejected():
    # A company's own careers page is not a board we can read, and pretending
    # otherwise would save a slug that never returns anything.
    for text in [
        "https://acme.com/careers",
        "https://www.linkedin.com/jobs",
        "not a url",
        "",
        "figma",
    ]:
        assert parse_board_url(text) is None, f"{text!r} should not parse"


def test_path_noise_is_not_mistaken_for_a_slug():
    m = parse_board_url("https://boards.greenhouse.io/embed/job_board?for=gitlab")
    assert m.token == "gitlab"


def test_descriptive_words_are_kept_in_the_first_candidate():
    # Grafana Labs really is `grafanalabs` and Match Group really is `matchgroup`,
    # so stripping "Labs"/"Group" would probe the wrong slug first.
    assert slug_candidates("Grafana Labs")[0] == "grafanalabs"
    assert slug_candidates("Match Group")[0] == "matchgroup"


def test_legal_suffixes_are_stripped():
    assert slug_candidates("GitLab, Inc.")[0] == "gitlab"
    assert slug_candidates("Acme Ltd")[0] == "acme"


def test_multiword_names_produce_joined_and_hyphenated_forms():
    got = slug_candidates("Applied Intuition")
    assert got[0] == "appliedintuition"
    assert "applied-intuition" in got


def test_ampersand_becomes_and():
    assert slug_candidates("Weights & Biases")[0] == "weightsandbiases"


def test_accents_are_folded():
    assert slug_candidates("Nestlé")[0] == "nestle"


def test_single_word_is_just_itself():
    assert slug_candidates("Brex") == ["brex"]


def test_empty_and_punctuation_only_names_are_safe():
    assert slug_candidates("") == []
    assert slug_candidates("!!!") == []


def test_candidate_list_is_bounded():
    # Each candidate costs a live HTTP probe, so this must not grow with input.
    many = slug_candidates("One Two Three Four Five Six Seven Eight")
    assert len(many) <= 6
