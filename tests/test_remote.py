"""Tests for the remote classifier.

Cases are drawn from real strings observed on live Greenhouse, Lever and Ashby
boards, not invented ones.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.models import Workplace
from meester.remote import (
    classify_location_text,
    extract_countries,
    is_acceptable,
    workplace_from_enum,
)

REMOTE_CASES = [
    ("Remote, US", {"US"}),
    ("Remote, United States", {"US"}),
    ("Remote, Canada; Remote, United States", {"US", "CA"}),
    ("Remote, Canada; Remote, US", {"US", "CA"}),
    ("Remote - United States", {"US"}),
    ("US Remote", {"US"}),
    ("Remote (US)", {"US"}),
    ("Remote (Canada)", {"CA"}),
    ("Anywhere", {"ANYWHERE"}),
    ("Remote - Worldwide", {"ANYWHERE"}),
    ("Remote, United Kingdom", {"GB"}),
    ("Work from home", set()),
]

NOT_REMOTE_CASES = [
    "San Francisco, CA",
    "New York, NY (HQ)",
    "Bangalore, India",
    "London",
    "Sydney, Australia",
    "Munich, Germany",
]

HYBRID_CASES = [
    "New York, NY (Hybrid)",
    "Hybrid - San Francisco",
    "Hybrid Remote - Austin, TX",  # 'hybrid' must beat a co-occurring 'remote'
]


def test_remote_strings_classify_as_remote():
    for text, expected in REMOTE_CASES:
        mode, countries = classify_location_text(text)
        assert mode == Workplace.REMOTE, f"{text!r} -> {mode}"
        assert countries == expected, f"{text!r} -> {countries}, wanted {expected}"


def test_onsite_strings_are_not_remote():
    for text in NOT_REMOTE_CASES:
        mode, _ = classify_location_text(text)
        assert mode == Workplace.ONSITE, f"{text!r} -> {mode}"


def test_hybrid_is_not_remote():
    for text in HYBRID_CASES:
        mode, _ = classify_location_text(text)
        assert mode == Workplace.HYBRID, f"{text!r} -> {mode}"


def test_mixed_locations_take_the_most_permissive():
    # A role offered both remote and in an office is remote-eligible.
    mode, countries = classify_location_text("Remote, US; New York, NY")
    assert mode == Workplace.REMOTE
    assert "US" in countries


def test_negated_remote_is_onsite():
    mode, _ = classify_location_text("Austin, TX - no remote")
    assert mode == Workplace.ONSITE


def test_us_state_abbreviation_implies_us():
    assert "US" in extract_countries("Austin, TX")
    assert "US" in extract_countries("Remote, WA")
    # A two-letter token that is not a state must not be read as one.
    assert "US" not in extract_countries("Cambridge, ZZ")


def test_regions_stay_distinct_from_countries():
    # 'EMEA remote' is not US-eligible; conflating them wastes applications.
    _, countries = classify_location_text("Remote - EMEA")
    assert "EU" in countries
    assert "US" not in countries


def test_workplace_enum_normalisation():
    assert workplace_from_enum("Remote") == Workplace.REMOTE
    assert workplace_from_enum("Hybrid") == Workplace.HYBRID
    assert workplace_from_enum("On-site") == Workplace.ONSITE
    assert workplace_from_enum("onsite") == Workplace.ONSITE
    assert workplace_from_enum(None) == Workplace.UNKNOWN
    assert workplace_from_enum("Unspecified") == Workplace.UNKNOWN


def test_policy_accepts_us_remote_and_rejects_india_remote():
    accept = ["US", "CA", "GB", "EU", "ANYWHERE"]
    assert is_acceptable(Workplace.REMOTE, {"US"}, accept)
    assert not is_acceptable(Workplace.REMOTE, {"IN"}, accept)
    assert not is_acceptable(Workplace.ONSITE, {"US"}, accept)


def test_policy_accepts_unscoped_remote():
    # Boards very often write just "Remote"; rejecting those discards real roles.
    assert is_acceptable(Workplace.REMOTE, set(), ["US"])


def test_policy_hybrid_gated_by_flag():
    assert not is_acceptable(Workplace.HYBRID, {"US"}, ["US"], accept_hybrid=False)
    assert is_acceptable(Workplace.HYBRID, {"US"}, ["US"], accept_hybrid=True)


def test_policy_anywhere_satisfies_any_country():
    assert is_acceptable(Workplace.REMOTE, {"ANYWHERE"}, ["US"])
